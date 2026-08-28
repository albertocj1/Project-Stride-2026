import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, status, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from supabase import Client, create_client

from email_module import send_approval_email, send_pending_reminder_email

EVENT_CAPACITY = int(os.getenv("EVENT_CAPACITY", "2000"))  # 2,000 bib cap
HOLD_MINUTES = int(os.getenv("HOLD_MINUTES", "15"))        # Unpaid booking hold time

# Receipt upload validation
ALLOWED_RECEIPT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}
MAX_RECEIPT_SIZE = 10 * 1024 * 1024  # 10 MB

# Project Stride Packages & Pricing
PACKAGES = {
    "3KM Individual":       {"price": 500,  "max_guests": 1},
    "5KM Individual":       {"price": 750,  "max_guests": 1},
    "10KM Individual":      {"price": 1000, "max_guests": 1},
    "Duathlon (5K-20K-3K)": {"price": 2000, "max_guests": 1},
}

def _is_valid_file_signature(data: bytes, content_type: str) -> bool:
    """Check magic bytes to prevent malicious file uploads."""
    signatures = {
        "image/jpeg": [b"\xff\xd8\xff"],
        "image/png": [b"\x89PNG\r\n\x1a\n"],
        "image/webp": [b"RIFF"], 
        "application/pdf": [b"%PDF-"],
    }
    expected = signatures.get(content_type, [])
    return any(data.startswith(sig) for sig in expected)

_client: Optional[Client] = None
def db() -> Client:
    global _client
    if _client is None:
        _client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    return _client

# --- PYDANTIC SCHEMAS ---
class BookingCreate(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    phone: str = Field(..., min_length=7, max_length=20)
    emergency_contact: str = Field(..., min_length=2, max_length=120)
    package: str
    shirt_size: str
    guests: int = Field(..., ge=1, le=14)
    guest_names: list[str] = Field(default_factory=list)
    team_name: Optional[str] = None
    total_amount: int
    accept_terms: bool

    @field_validator("guest_names")
    @classmethod
    def _clean_names(cls, v):
        return [str(n).strip() for n in (v or []) if str(n).strip()]

    @field_validator("accept_terms")
    @classmethod
    def _terms(cls, v):
        if not v:
            raise ValueError("Must confirm terms.")
        return v

    @field_validator("package")
    @classmethod
    def _known_package(cls, v):
        if v not in PACKAGES:
            raise ValueError(f"Unknown package: {v}")
        return v

    @model_validator(mode="after")
    def _validate_booking(self):
        cfg = PACKAGES[self.package]
        if self.guests > cfg["max_guests"]:
            raise ValueError(f"{self.package} allows at most {cfg['max_guests']} runner(s).")
        if len(self.guest_names) != self.guests:
            raise ValueError(f"Please provide a name for each runner.")
        
        expected_total = cfg["price"] * self.guests
        if self.total_amount != expected_total:
            raise ValueError(f"Total amount mismatch. Expected {expected_total}, got {self.total_amount}")
        return self

class Booking(BaseModel):
    id: str
    full_name: str
    email: EmailStr
    phone: str
    emergency_contact: str
    package: str
    shirt_size: str
    guests: int
    guest_names: list[str]
    team_name: Optional[str] = None
    total_amount: int
    status: str
    receipt_url: Optional[str] = None
    bib_code: Optional[str] = None
    created_at: datetime

class BookingUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=120)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, min_length=7, max_length=20)
    emergency_contact: Optional[str] = Field(None, min_length=2, max_length=120)
    package: Optional[str] = None
    shirt_size: Optional[str] = None
    guests: Optional[int] = Field(None, ge=1, le=14)
    guest_names: Optional[list[str]] = None
    team_name: Optional[str] = None

class CheckinBody(BaseModel):
    kits_claimed: int = Field(..., ge=1, le=50)

class RemindPayload(BaseModel):
    booking_ids: Optional[list[str]] = None


app = FastAPI()

@app.on_event("startup")
def startup_event():
    db()

origins_str = os.environ.get("ALLOWED_ORIGINS", "*")
origins_list = ["*"] if origins_str == "*" else [o.strip() for o in origins_str.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- AUTH DEPENDENCIES ---
def require_admin(x_admin_key: str = Header(default="")):
    if not secrets.compare_digest(x_admin_key, os.environ.get("ADMIN_API_KEY", "")):
        raise HTTPException(status_code=401, detail="Invalid admin key.")

_reception_bearer = HTTPBearer(auto_error=False)

def _require_supabase_session(cred: Optional[HTTPAuthorizationCredentials], label: str):
    if cred is None or not cred.credentials:
        raise HTTPException(status_code=401, detail=f"{label} login required.")
    try:
        user_resp = db().auth.get_user(cred.credentials)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")
    if not getattr(user_resp, "user", None):
        raise HTTPException(status_code=401, detail="Invalid session.")
    return user_resp.user

def require_reception(cred: Optional[HTTPAuthorizationCredentials] = Depends(_reception_bearer)):
    return _require_supabase_session(cred, "Reception")

# --- IN-MEMORY QUERY OPTIMIZATIONS ---
def _get_booking(booking_id: str):
    res = db().table("stride_bookings").select("*").eq("id", booking_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Not found.")
    return res.data[0]

def _committed_runner_count() -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=HOLD_MINUTES)).isoformat()
    res = db().table("stride_bookings").select("guests, status, created_at").in_("status", ["confirmed", "verifying", "pending"]).execute()
    
    taken = 0
    for r in (res.data or []):
        st = r.get("status")
        g = r.get("guests", 0)
        if st in ["confirmed", "verifying"]:
            taken += g
        elif st == "pending" and r.get("created_at") >= cutoff:
            taken += g
    return taken

# --- PUBLIC ENDPOINTS ---
@app.get("/api/availability")
def availability():
    taken = _committed_runner_count()
    left = max(0, EVENT_CAPACITY - taken)
    return {
        "capacity": EVENT_CAPACITY,
        "taken": taken,
        "spots_left": left,
        "sold_out": left <= 0,
    }

@app.post("/api/bookings", response_model=Booking)
def create_booking(payload: BookingCreate):
    taken = _committed_runner_count()
    left = max(0, EVENT_CAPACITY - taken)
    
    if left <= 0:
        raise HTTPException(status_code=409, detail="The race is sold out. No bibs remain.")
    if payload.guests > left:
        raise HTTPException(status_code=409, detail=f"Only {left} bib(s) left.")

    res = db().table("stride_bookings").insert({
        "full_name": payload.full_name, 
        "email": payload.email, 
        "phone": payload.phone,
        "emergency_contact": payload.emergency_contact, 
        "package": payload.package,
        "shirt_size": payload.shirt_size,
        "guests": payload.guests,
        "guest_names": payload.guest_names,
        "team_name": payload.team_name,
        "total_amount": payload.total_amount, 
        "status": "pending",
    }).execute()
    
    return Booking(**res.data[0])

@app.post("/api/bookings/{booking_id}/submit-payment", response_model=Booking)
async def submit_payment(booking_id: str, receipt: UploadFile = File(...)):
    booking = _get_booking(booking_id)
    if booking["status"] != "pending":
        raise HTTPException(status_code=400, detail="Cannot submit payment for this booking.")

    content_type = (receipt.content_type or "").lower()
    if content_type not in ALLOWED_RECEIPT_TYPES:
        raise HTTPException(status_code=400, detail="Invalid file type. Please upload a JPG, PNG, WEBP, or PDF.")

    file_bytes = await receipt.read()
    if len(file_bytes) > MAX_RECEIPT_SIZE or len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="File must be between 1 byte and 10MB.")

    if not _is_valid_file_signature(file_bytes, content_type):
        raise HTTPException(status_code=400, detail="File content doesn't match its type.")

    file_ext = ALLOWED_RECEIPT_TYPES[content_type]
    file_name = f"{booking_id}_{secrets.token_hex(4)}{file_ext}"

    try:
        db().storage.from_("stride_receipts").upload(file_name, file_bytes, {"content-type": content_type})
        receipt_url = db().storage.from_("stride_receipts").get_public_url(file_name)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not upload receipt: {str(e)}")

    res = db().table("stride_bookings").update({
        "status": "verifying", "receipt_url": receipt_url
    }).eq("id", booking_id).execute()
    
    return Booking(**res.data[0])

# --- ADMIN ENDPOINTS ---
@app.get("/api/bookings", dependencies=[Depends(require_admin)])
def list_bookings():
    return db().table("stride_bookings").select("*").order("created_at", desc=True).limit(1000).execute().data

@app.patch("/api/bookings/{booking_id}", response_model=Booking, dependencies=[Depends(require_admin)])
def update_booking(booking_id: str, payload: BookingUpdate):
    existing = _get_booking(booking_id)
    if existing["status"] == "cancelled":
        raise HTTPException(status_code=400, detail="Cannot edit a cancelled booking.")

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update.")

    merged = {**existing, **updates}
    package = merged.get("package")
    if package not in PACKAGES:
        raise HTTPException(status_code=400, detail=f"Unknown package: {package}")

    guests = merged.get("guests")
    guest_names = merged.get("guest_names") or []
    if len(guest_names) != guests:
        raise HTTPException(status_code=400, detail=f"Please provide a name for each guest.")

    cfg = PACKAGES[package]
    update_payload = {
        "full_name": merged.get("full_name"),
        "email": merged.get("email"),
        "phone": merged.get("phone"),
        "emergency_contact": merged.get("emergency_contact"),
        "team_name": merged.get("team_name"),
        "package": package,
        "shirt_size": merged.get("shirt_size"),
        "guests": guests,
        "guest_names": guest_names,
        "total_amount": cfg["price"] * guests,
    }

    res = db().table("stride_bookings").update(update_payload).eq("id", booking_id).execute()
    if not res.data:
        raise HTTPException(status_code=502, detail="Failed to update booking.")
    return Booking(**res.data[0])

@app.post("/api/bookings/{booking_id}/approve", dependencies=[Depends(require_admin)])
def approve_booking(booking_id: str, background_tasks: BackgroundTasks):
    b = _get_booking(booking_id)
    if b["status"] != "verifying":
        raise HTTPException(status_code=400, detail="Not awaiting verification.")

    res = db().table("stride_bookings").update({
        "status": "confirmed",
        "bib_code": "STR-" + secrets.token_hex(3).upper(),
        "confirmed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", booking_id).execute()

    if res.data:
        booking_data = res.data[0]
        background_tasks.add_task(
            send_approval_email,
            to_email=booking_data["email"],
            guest_name=booking_data["full_name"],
            bib_code=booking_data["bib_code"],
            package_name=booking_data["package"],
            shirt_size=booking_data["shirt_size"],
            guests=booking_data["guests"]
        )
        return Booking(**booking_data)
    raise HTTPException(status_code=502, detail="Failed to issue bib.")

@app.post("/api/bookings/{booking_id}/cancel", dependencies=[Depends(require_admin)])
def cancel_booking(booking_id: str):
    res = db().table("stride_bookings").update({"status": "cancelled"}).eq("id", booking_id).execute()
    return Booking(**res.data[0])

@app.post("/api/bookings/remind-pending", dependencies=[Depends(require_admin)])
def remind_pending_bookings(payload: RemindPayload, background_tasks: BackgroundTasks):
    query = db().table("stride_bookings").select("*").eq("status", "pending")
    if payload.booking_ids:
        query = query.in_("id", payload.booking_ids)
    res = query.execute()
    pending_rows = res.data or []

    unique_pending = {}
    for row in pending_rows:
        email_key = row["email"].lower().strip()
        if email_key not in unique_pending:
            unique_pending[email_key] = row

    reminded_count = 0
    for email, b in unique_pending.items():
        background_tasks.add_task(
            send_pending_reminder_email,
            to_email=email,
            guest_name=b["full_name"],
            package_name=b["package"],
            guests=b["guests"],
            total_amount=b["total_amount"],
        )
        reminded_count += 1

    return {
        "status": "success",
        "reminded_count": reminded_count,
        "total_pending_rows": len(pending_rows),
        "duplicates_skipped": len(pending_rows) - reminded_count,
    }

# --- RECEPTION / KIT PICKUP ENDPOINTS ---
@app.get("/api/reception/search", dependencies=[Depends(require_reception)])
def reception_search(q: str):
    query_str = (q or "").strip().lower()
    if len(query_str) < 2:
        raise HTTPException(status_code=400, detail="Search query must be at least 2 characters.")

    all_rows = db().table("stride_bookings").select("*").neq("status", "cancelled").execute().data or []
    matches = []
    
    for b in all_rows:
        if query_str in (b.get("full_name") or "").lower() or \
           query_str in (b.get("bib_code") or "").lower() or \
           any(query_str in str(n).lower() for n in (b.get("guest_names") or [])):
            matches.append({
                "id": b["id"],
                "bib_code": b.get("bib_code"),
                "full_name": b["full_name"],
                "package": b["package"],
                "shirt_size": b["shirt_size"],
                "guests": b["guests"],
                "status": b["status"],
                "bib_claimed": b.get("bib_claimed", False),
                "kits_claimed": b.get("kits_claimed", 0),
            })
    matches.sort(key=lambda m: 0 if m["status"] == "confirmed" else 1)
    return {"results": matches}

@app.get("/api/reception/lookup/{bib_code}", dependencies=[Depends(require_reception)])
def reception_lookup(bib_code: str):
    code = (bib_code or "").strip().upper()
    res = db().table("stride_bookings").select("*").eq("bib_code", code).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Bib code not found.")
    b = res.data[0]
    return {
        "id": b["id"],
        "bib_code": b.get("bib_code"),
        "full_name": b["full_name"],
        "package": b["package"],
        "shirt_size": b["shirt_size"],
        "guests": b["guests"],
        "status": b["status"],
        "bib_claimed": b.get("bib_claimed", False),
        "kits_claimed": b.get("kits_claimed", 0),
        "guest_names": b.get("guest_names") or [],
    }

@app.post("/api/reception/checkin/{booking_id}", dependencies=[Depends(require_reception)])
def reception_checkin(booking_id: str, body: CheckinBody):
    b = _get_booking(booking_id)
    if b["status"] != "confirmed":
        raise HTTPException(status_code=400, detail="This registration is not confirmed.")

    max_heads = b.get("guests") or 0
    if body.kits_claimed > max_heads:
        raise HTTPException(status_code=400, detail=f"Booking only has {max_heads} runner(s).")

    already = bool(b.get("bib_claimed"))
    update = {"bib_claimed": True, "kits_claimed": body.kits_claimed}
    if not already:
        update["bib_claimed_at"] = datetime.now(timezone.utc).isoformat()

    res = db().table("stride_bookings").update(update).eq("id", booking_id).execute()
    row = res.data[0]
    return {
        "id": row["id"],
        "full_name": row["full_name"],
        "package": row["package"],
        "guests": row["guests"],
        "kits_claimed": row.get("kits_claimed", 0),
        "bib_claimed": row.get("bib_claimed", False),
        "already_claimed": already,
    }
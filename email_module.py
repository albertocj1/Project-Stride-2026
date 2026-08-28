# ============================================================================
#  QR + HTML EMAIL — Project Stride 2026 Boarding Pass & Reminder System
#  Requires: qrcode, pillow
# ============================================================================
import os, io, json, base64
from email.message import EmailMessage
from email.utils import make_msgid

import qrcode
from qrcode.constants import ERROR_CORRECT_M

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/gmail.send']

EVENT_DATE_LONG = "Saturday, November 28, 2026"
EVENT_DATE_SHORT = "Nov 28, 2026 &middot; 5:00 AM"

# The filename of the logo you provided
LOGO_PATH = os.environ.get("LOGO_PATH", "442497274_419117694308411_2751438522990521029_n.jpg")
LOGO_URL = None # Leave None to embed the image directly into the email

def get_gmail_service():
    creds = None
    token_json_str = os.environ.get("GMAIL_TOKEN_JSON")
    if token_json_str:
        creds = Credentials.from_authorized_user_info(json.loads(token_json_str), SCOPES)
    elif os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    if not creds or not creds.valid:
        raise Exception("Gmail credentials are not valid. Ensure GMAIL_TOKEN_JSON env var or token.json is present.")

    return build('gmail', 'v1', credentials=creds)

def _make_qr_png(data: str) -> bytes:
    """Branded PNG QR encoding the bib_code."""
    qr = qrcode.QRCode(version=None, error_correction=ERROR_CORRECT_M, box_size=10, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    # Using your deep navy blue for the QR code
    img = qr.make_image(fill_color="#152243", back_color="white").convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def _load_logo_bytes() -> bytes | None:
    try:
        with open(LOGO_PATH, "rb") as f:
            return f.read()
    except FileNotFoundError:
        print(f"WARNING: logo not found at {LOGO_PATH}; falling back to text wordmark.")
        return None

def _build_approval_html(guest_name, bib_code, package_name, shirt_size, guests, qr_cid, logo_cid=None):
    guest_word = "runner" if str(guests) == "1" else "runners"

    if logo_cid:
        wordmark_html = f"""
      <img src="cid:{logo_cid}" alt="Project Stride" width="160" style="display:block; width:160px; max-width:60%; height:auto; border:0; margin:0 auto; border-radius: 50%;">
      <div class="gmail-blend-screen"><div class="gmail-blend-difference">
        <div class="text-muted" style="font-family:'Courier New', monospace; font-size:9px; letter-spacing:3px; color:#7A8C99; text-transform:uppercase; margin-top:10px;">LIMA ESTATE &middot; MALVAR</div>
      </div></div>"""
    else:
        wordmark_html = """
      <div class="gmail-blend-screen"><div class="gmail-blend-difference">
        <span class="text-gold" style="font-family:'Courier New', monospace; font-size:16px; letter-spacing:4px; color:#FCD116; text-transform:uppercase; font-weight:bold;">PROJECT STRIDE</span>
        <div class="text-muted" style="font-family:'Courier New', monospace; font-size:9px; letter-spacing:3px; color:#7A8C99; text-transform:uppercase; margin-top:6px;">LIMA ESTATE &middot; MALVAR</div>
      </div></div>"""

    html = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="color-scheme" content="dark">
<meta name="supported-color-schemes" content="dark">
<style>
  :root { color-scheme: dark; supported-color-schemes: dark; }
  u + .body .gmail-blend-screen     { background:#000000; mix-blend-mode:screen; }
  u + .body .gmail-blend-difference { background:#000000; mix-blend-mode:difference; }
  u + .body .text-gold  { color:#FCD116 !important; border-color:#FCD116 !important; }
  u + .body .text-cream { color:#FFFFFF !important; }
  u + .body .text-muted { color:#7A8C99 !important; }
  @media (prefers-color-scheme: dark) {
    .body-bg    { background-color:#152243 !important; }
    .card-edge  { background-color:#C1121F !important; }
    .card-bg    { background-color:#0F2043 !important; }
    .qr-card-bg { background-color:#FFFFFF !important; }
    .notice-edge{ background-color:#1A3668 !important; }
    .notice-bg  { background-color:#0F2043 !important; }
    .text-cream { color:#FFFFFF !important; }
    .text-muted { color:#7A8C99 !important; }
    .text-gold  { color:#FCD116 !important; }
  }
</style>
</head>
<body class="body body-bg" style="margin:0; padding:0; background-color:#152243; font-family:Arial, Helvetica, sans-serif;">

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="body-bg" style="background-color:#152243; background-image:linear-gradient(#152243,#152243); padding:32px 12px;">
<tr><td align="center">
  <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="max-width:480px; width:100%;">
    <tr><td align="center" style="padding-bottom:28px;">__WORDMARK__</td></tr>
    <tr><td class="card-edge" style="background-color:#C1121F; background-image:linear-gradient(#C1121F,#C1121F); border-radius:24px; padding:2px;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="card-bg" style="background-color:#0F2043; background-image:linear-gradient(#0F2043,#0F2043); border-radius:22px;">
        <tr><td align="center" style="padding:36px 32px 8px 32px;">
          <div class="gmail-blend-screen"><div class="gmail-blend-difference">
            <div class="text-gold" style="width:52px; height:52px; line-height:52px; margin:0 auto 18px auto; border:2px solid #FCD116; border-radius:50%; color:#FCD116; font-size:22px; text-align:center;">&#10003;</div>
            <div class="text-cream" style="font-family:Arial, sans-serif; font-size:28px; font-weight:bold; color:#FFFFFF; letter-spacing:-0.5px;">You're on the start list</div>
            <div class="text-muted" style="font-size:13px; color:#7A8C99; line-height:1.6; padding:14px 8px 0 8px;">
              Hi __GUEST_NAME__, your payment is verified and your race registration is confirmed. Present the QR code below at Lima Estate to claim your race kit.
            </div>
          </div></div>
        </td></tr>
        <tr><td align="center" style="padding:28px 32px 8px 32px;">
          <table role="presentation" cellpadding="0" cellspacing="0" class="qr-card-bg" style="background-color:#FFFFFF; background-image:linear-gradient(#FFFFFF,#FFFFFF); border-radius:18px;">
            <tr><td align="center" style="padding:16px;">
              <img src="cid:__QR_CID__" alt="Kit Pickup QR code" width="180" height="180" style="display:block; width:180px; height:180px; border:0;">
            </td></tr>
          </table>
          <div class="gmail-blend-screen"><div class="gmail-blend-difference">
            <div class="text-muted" style="font-family:'Courier New', monospace; font-size:11px; letter-spacing:2px; color:#7A8C99; text-transform:uppercase; padding-top:16px;">Scan at Kit Pickup</div>
          </div></div>
        </td></tr>
        <tr><td align="center" style="padding:8px 32px 24px 32px;">
          <div class="gmail-blend-screen"><div class="gmail-blend-difference">
            <div class="text-gold" style="font-family:'Courier New', monospace; font-size:24px; letter-spacing:3px; color:#FCD116; font-weight:bold;">__BIB_CODE__</div>
          </div></div>
        </td></tr>
        <tr><td style="padding:0 32px;">
          <div class="gmail-blend-screen"><div class="gmail-blend-difference">
            <div style="border-top:2px dashed #1A3668; font-size:0; line-height:0;">&nbsp;</div>
          </div></div>
        </td></tr>
        <tr><td style="padding:24px 32px 8px 32px;">
          <div class="gmail-blend-screen"><div class="gmail-blend-difference">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="font-family:'Courier New', monospace; font-size:12px;">
              <tr><td class="text-muted" style="color:#7A8C99; text-transform:uppercase; letter-spacing:1px; padding:8px 0;">Lead Runner</td>
                  <td align="right" class="text-cream" style="color:#FFFFFF; font-weight:bold; padding:8px 0;">__GUEST_NAME__</td></tr>
              <tr><td class="text-muted" style="color:#7A8C99; text-transform:uppercase; letter-spacing:1px; padding:8px 0; border-top:1px solid #1A3668;">Category</td>
                  <td align="right" class="text-cream" style="color:#FFFFFF; padding:8px 0; border-top:1px solid #1A3668;">__PACKAGE__</td></tr>
              <tr><td class="text-muted" style="color:#7A8C99; text-transform:uppercase; letter-spacing:1px; padding:8px 0; border-top:1px solid #1A3668;">Runners</td>
                  <td align="right" class="text-cream" style="color:#FFFFFF; padding:8px 0; border-top:1px solid #1A3668;">__GUESTS__ __GUEST_WORD__</td></tr>
              <tr><td class="text-muted" style="color:#7A8C99; text-transform:uppercase; letter-spacing:1px; padding:8px 0; border-top:1px solid #1A3668;">Shirt Size</td>
                  <td align="right" class="text-cream" style="color:#FFFFFF; padding:8px 0; border-top:1px solid #1A3668;">__SHIRT_SIZE__</td></tr>
              <tr><td class="text-muted" style="color:#7A8C99; text-transform:uppercase; letter-spacing:1px; padding:8px 0; border-top:1px solid #1A3668;">Date</td>
                  <td align="right" class="text-cream" style="color:#FFFFFF; padding:8px 0; border-top:1px solid #1A3668;">__DATE_SHORT__</td></tr>
              <tr><td class="text-muted" style="color:#7A8C99; text-transform:uppercase; letter-spacing:1px; padding:8px 0; border-top:1px solid #1A3668;">Venue</td>
                  <td align="right" class="text-cream" style="color:#FFFFFF; padding:8px 0; border-top:1px solid #1A3668;">Lima Estate, Malvar</td></tr>
            </table>
          </div></div>
        </td></tr>
        <tr><td style="padding:16px 32px 36px 32px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="notice-edge" style="background-color:#1A3668; background-image:linear-gradient(#1A3668,#1A3668); border-radius:14px;">
            <tr><td style="padding:1px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="notice-bg" style="background-color:#0F2043; background-image:linear-gradient(#0F2043,#0F2043); border-radius:13px;">
                <tr><td style="padding:16px;">
                  <div class="gmail-blend-screen"><div class="gmail-blend-difference">
                    <div class="text-muted" style="font-size:12px; color:#7A8C99; line-height:1.6;">
                      <span class="text-gold" style="color:#FCD116; font-weight:bold;">__DATE_LONG__.</span> Kit pickup opens at 4:00 AM. Gun start varies per category. Registrations are final and non-transferable.
                    </div>
                  </div></div>
                </td></tr>
              </table>
            </td></tr>
          </table>
        </td></tr>
      </table>
    </td></tr>
    <tr><td align="center" style="padding:28px 20px 8px 20px;">
      <div class="gmail-blend-screen"><div class="gmail-blend-difference">
        <div class="text-muted" style="font-size:11px; color:#7A8C99; line-height:1.7;">
          Project Stride &middot; Lima Estate, Malvar, Batangas<br>
          Questions? Reply to this email.
        </div>
      </div></div>
    </td></tr>
  </table>
</td></tr>
</table>
</body>
</html>"""

    return (html.replace("__WORDMARK__", wordmark_html)
                .replace("__GUEST_NAME__", str(guest_name))
                .replace("__BIB_CODE__", str(bib_code))
                .replace("__PACKAGE__", str(package_name))
                .replace("__SHIRT_SIZE__", str(shirt_size))
                .replace("__GUESTS__", str(guests))
                .replace("__GUEST_WORD__", guest_word)
                .replace("__DATE_LONG__", EVENT_DATE_LONG)
                .replace("__DATE_SHORT__", EVENT_DATE_SHORT)
                .replace("__QR_CID__", str(qr_cid)))


def send_approval_email(to_email, guest_name, bib_code, package_name, shirt_size, guests=1):
    try:
        service = get_gmail_service()
        qr_msgid = make_msgid(domain="projectstride.ph")
        qr_cid = qr_msgid[1:-1]

        logo_bytes = _load_logo_bytes()
        logo_msgid = None
        logo_cid = None
        if logo_bytes:
            logo_msgid = make_msgid(domain="projectstride.ph")
            logo_cid = logo_msgid[1:-1]

        qr_png = _make_qr_png(bib_code)
        html_body = _build_approval_html(guest_name, bib_code, package_name, shirt_size, guests, qr_cid, logo_cid)

        text_body = (
            f"Hi {guest_name},\n\n"
            f"Your payment is verified and your registration for '{package_name}' is confirmed.\n\n"
            f"Bib Code: {bib_code}\n"
            f"Runners: {guests}\n"
            f"Shirt Size: {shirt_size}\n"
            f"Date: {EVENT_DATE_LONG} - 5:00 AM\n"
            f"Venue: Lima Estate, Malvar, Batangas\n\n"
            f"Present your QR code (in the HTML version of this email) at the kit pickup tent.\n\n"
            f"Project Stride"
        )

        msg = EmailMessage()
        msg['To'] = to_email
        msg['From'] = os.environ.get("SENDER_EMAIL", "hello@projectstride.ph")
        msg['Subject'] = "You're on the start list — Project Stride 2026"
        msg.set_content(text_body)
        msg.add_alternative(html_body, subtype='html')

        html_part = msg.get_payload()[1]
        html_part.add_related(qr_png, maintype='image', subtype='png', cid=qr_msgid, filename='ticket-qr.png', disposition='inline')
        if logo_bytes:
            html_part.add_related(logo_bytes, maintype='image', subtype='jpeg', cid=logo_msgid, filename='logo.jpg', disposition='inline')

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId="me", body={'raw': raw}).execute()
        print(f"Successfully sent confirmation email to {to_email}")
    except Exception as e:
        print(f"ERROR sending email to {to_email}: {str(e)}")


def send_pending_reminder_email(to_email, guest_name, package_name, guests, total_amount):
    """Sends a friendly reminder to complete payment for a pending race registration."""
    try:
        service = get_gmail_service()
        logo_bytes = _load_logo_bytes()
        logo_msgid = None
        logo_cid = None
        if logo_bytes:
            logo_msgid = make_msgid(domain="projectstride.ph")
            logo_cid = logo_msgid[1:-1]

        guest_word = "runner" if str(guests) == "1" else "runners"

        if logo_cid:
            wordmark_html = f"""
          <img src="cid:{logo_cid}" alt="Project Stride" width="160" style="display:block; width:160px; max-width:60%; height:auto; border:0; margin:0 auto; border-radius: 50%;">
          <div class="gmail-blend-screen"><div class="gmail-blend-difference">
            <div class="text-muted" style="font-family:'Courier New', monospace; font-size:9px; letter-spacing:3px; color:#7A8C99; text-transform:uppercase; margin-top:10px;">LIMA ESTATE &middot; MALVAR</div>
          </div></div>"""
        else:
            wordmark_html = """
          <div class="gmail-blend-screen"><div class="gmail-blend-difference">
            <span class="text-gold" style="font-family:'Courier New', monospace; font-size:16px; letter-spacing:4px; color:#FCD116; text-transform:uppercase; font-weight:bold;">PROJECT STRIDE</span>
            <div class="text-muted" style="font-family:'Courier New', monospace; font-size:9px; letter-spacing:3px; color:#7A8C99; text-transform:uppercase; margin-top:6px;">LIMA ESTATE &middot; MALVAR</div>
          </div></div>"""

        html_body = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="color-scheme" content="dark">
<meta name="supported-color-schemes" content="dark">
<style>
  :root {{ color-scheme: dark; supported-color-schemes: dark; }}
  u + .body .gmail-blend-screen     {{ background:#000000; mix-blend-mode:screen; }}
  u + .body .gmail-blend-difference {{ background:#000000; mix-blend-mode:difference; }}
  u + .body .text-gold  {{ color:#FCD116 !important; border-color:#FCD116 !important; }}
  u + .body .text-cream {{ color:#FFFFFF !important; }}
  u + .body .text-muted {{ color:#7A8C99 !important; }}
  u + .body .text-amount {{ color:#FCD116 !important; }}
  @media (prefers-color-scheme: dark) {{
    .body-bg {{ background-color:#152243 !important; }}
    .card-edge {{ background-color:#C1121F !important; }}
    .card-bg {{ background-color:#0F2043 !important; }}
    .amount-box-bg {{ background-color:#152243 !important; }}
    .text-cream {{ color:#FFFFFF !important; }}
    .text-muted {{ color:#7A8C99 !important; }}
    .text-gold  {{ color:#FCD116 !important; }}
    .text-amount {{ color:#FCD116 !important; }}
  }}
</style>
</head>
<body class="body body-bg" style="margin:0; padding:0; background-color:#152243; font-family:Arial, Helvetica, sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="body-bg" style="background-color:#152243; background-image:linear-gradient(#152243,#152243); padding:32px 12px;">
<tr><td align="center">
  <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="max-width:480px; width:100%;">
    <tr><td align="center" style="padding-bottom:28px;">{wordmark_html}</td></tr>
    <tr><td class="card-edge" style="background-color:#C1121F; background-image:linear-gradient(#C1121F,#C1121F); border-radius:24px; padding:2px;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="card-bg" style="background-color:#0F2043; background-image:linear-gradient(#0F2043,#0F2043); border-radius:22px;">
        <tr><td align="center" style="padding:36px 32px 24px 32px;">
          <div class="gmail-blend-screen"><div class="gmail-blend-difference">
            <div class="text-gold" style="font-family:'Courier New', monospace; font-size:11px; letter-spacing:3px; color:#FCD116; text-transform:uppercase; margin-bottom:12px;">Payment Reminder</div>
            <div class="text-cream" style="font-family:Arial, sans-serif; font-weight:bold; font-size:26px; color:#FFFFFF; letter-spacing:-0.5px;">Complete Your Registration</div>
            <div class="text-muted" style="font-size:13px; color:#7A8C99; line-height:1.6; padding:16px 8px 0 8px;">
              Hi {guest_name}, we noticed you requested a spot for <strong>{package_name}</strong> ({guests} {guest_word}) but haven't uploaded your payment receipt yet. Since bibs are strictly capped, unpaid holds are released automatically.
            </div>
          </div></div>
        </td></tr>
        <tr><td style="padding:0 32px 28px 32px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="amount-box-bg" style="background-color:#152243; background-image:linear-gradient(#152243,#152243); border:1px solid #1A3668; border-radius:16px;">
            <tr><td align="center" style="padding:20px;">
              <div class="gmail-blend-screen"><div class="gmail-blend-difference">
                <div class="text-muted" style="font-family:'Courier New', monospace; font-size:10px; letter-spacing:2px; color:#7A8C99; text-transform:uppercase;">Amount Due</div>
                <div class="text-amount" style="font-family:Arial, sans-serif; font-size:28px; color:#FCD116; font-weight:bold; margin-top:4px;">₱{total_amount:,}</div>
              </div></div>
            </td></tr>
          </table>
        </td></tr>
        <tr><td align="center" style="padding:0 32px 36px 32px;">
          <div class="gmail-blend-screen"><div class="gmail-blend-difference">
            <div class="text-muted" style="font-size:12px; color:#7A8C99; line-height:1.6;">
              To finalize your entry, please complete your transfer via GCash or Bank Transfer and upload your screenshot on our website.
            </div>
          </div></div>
        </td></tr>
      </table>
    </td></tr>
    <tr><td align="center" style="padding:28px 20px 8px 20px;">
      <div class="gmail-blend-screen"><div class="gmail-blend-difference">
        <div class="text-muted" style="font-size:11px; color:#7A8C99; line-height:1.7;">
          Project Stride &middot; Lima Estate, Malvar, Batangas<br>
          Questions? Reply directly to this email.
        </div>
      </div></div>
    </td></tr>
  </table>
</td></tr>
</table>
</body>
</html>"""

        text_body = (
            f"Hi {guest_name},\n\n"
            f"We noticed you requested a registration for '{package_name}' ({guests} {guest_word}) but haven't uploaded your payment receipt yet.\n\n"
            f"Amount Due: ₱{total_amount:,}\n\n"
            f"Since bibs are strictly capped, unpaid reservations are released automatically. To secure your slot, please transfer your payment and upload your receipt on our website.\n\n"
            f"Project Stride"
        )

        msg = EmailMessage()
        msg['To'] = to_email
        msg['From'] = os.environ.get("SENDER_EMAIL", "hello@projectstride.ph")
        msg['Subject'] = "Action Required: Complete your Project Stride registration"
        msg.set_content(text_body)
        msg.add_alternative(html_body, subtype='html')

        if logo_bytes:
            html_part = msg.get_payload()[1]
            html_part.add_related(logo_bytes, maintype='image', subtype='jpeg', cid=logo_msgid, filename='logo.jpg', disposition='inline')

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId="me", body={'raw': raw}).execute()
        print(f"Successfully sent pending reminder email to {to_email}")
    except Exception as e:
        print(f"ERROR sending reminder email to {to_email}: {str(e)}")
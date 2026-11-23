# ============================================================================
#  QR + HTML EMAIL — Project Stride 2026 Boarding Pass & Reminder System
#  Requires: qrcode, pillow
# ============================================================================
import os, io, json, base64, traceback
from email.message import EmailMessage
from email.utils import make_msgid

import qrcode
from qrcode.constants import ERROR_CORRECT_M

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/gmail.send']

EVENT_DATE_LONG = "Saturday, January 23, 2027"
EVENT_DATE_SHORT = "Jan 23, 2027 &middot; 5:00 AM"

# The filename of the logo you provided
LOGO_PATH = os.environ.get("LOGO_PATH", "442497274_419117694308411_2751438522990521029_n.jpg")
LOGO_URL = None # Leave None to embed the image directly into the email

# Shared styles for every email. The design is LIGHT on purpose, and uses plain
# background-color (no background-image tricks) so phone dark modes can convert it
# as a whole: Gmail iOS darkens the backgrounds AND lightens the text together.
# Blocking background inversion while text still inverts leaves white-on-white.
EMAIL_STYLE = """<style>
  :root { color-scheme: light dark; supported-color-schemes: light dark; }
</style>"""

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

def _fmt_amount(value) -> str:
    """Format an amount like 1,500 whether it arrives as int, float, str or None."""
    try:
        return f"{float(str(value).replace(',', '')):,.0f}"
    except (TypeError, ValueError):
        return str(value or 0)

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
        <div class="text-muted" style="font-family:'Courier New', monospace; font-size:9px; letter-spacing:3px; color:#5B6B7A; text-transform:uppercase; margin-top:10px;">LIMA ESTATE &middot; MALVAR</div>
      </div></div>"""
    else:
        wordmark_html = """
      <div class="gmail-blend-screen"><div class="gmail-blend-difference">
        <span class="text-gold" style="font-family:'Courier New', monospace; font-size:16px; letter-spacing:4px; color:#C1121F; text-transform:uppercase; font-weight:bold;">PROJECT STRIDE</span>
        <div class="text-muted" style="font-family:'Courier New', monospace; font-size:9px; letter-spacing:3px; color:#5B6B7A; text-transform:uppercase; margin-top:6px;">LIMA ESTATE &middot; MALVAR</div>
      </div></div>"""

    html = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="color-scheme" content="light dark">
<meta name="supported-color-schemes" content="light dark">
__STYLE__
</head>
<body class="body body-bg" style="margin:0; padding:0; background-color:#F1F4F8; font-family:Arial, Helvetica, sans-serif;">

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="body-bg" style="background-color:#F1F4F8; padding:32px 12px;">
<tr><td align="center">
  <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="max-width:480px; width:100%;">
    <tr><td align="center" style="padding-bottom:28px;">__WORDMARK__</td></tr>
    <tr><td class="card-edge" style="background-color:#C1121F; border-radius:24px; padding:2px;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="card-bg" style="background-color:#FFFFFF; border-radius:22px;">
        <tr><td align="center" style="padding:36px 32px 8px 32px;">
          <div class="gmail-blend-screen"><div class="gmail-blend-difference">
            <div class="text-gold" style="width:52px; height:52px; line-height:52px; margin:0 auto 18px auto; border:2px solid #C1121F; border-radius:50%; color:#C1121F; font-size:22px; text-align:center;">&#10003;</div>
            <div class="text-cream" style="font-family:Arial, sans-serif; font-size:28px; font-weight:bold; color:#152243; letter-spacing:-0.5px;">You're on the start list</div>
            <div class="text-muted" style="font-size:13px; color:#5B6B7A; line-height:1.6; padding:14px 8px 0 8px;">
              Hi __GUEST_NAME__, your payment is verified and your race registration is confirmed. Present the QR code below at Lima Estate to claim your race kit.
            </div>
          </div></div>
        </td></tr>
        <tr><td align="center" style="padding:28px 32px 8px 32px;">
          <table role="presentation" cellpadding="0" cellspacing="0" class="qr-card-bg" style="background-color:#FFFFFF; border:1px solid #E2E7EF; border-radius:18px;">
            <tr><td align="center" style="padding:16px;">
              <img src="cid:__QR_CID__" alt="Kit Pickup QR code" width="180" height="180" style="display:block; width:180px; height:180px; border:0;">
            </td></tr>
          </table>
          <div class="gmail-blend-screen"><div class="gmail-blend-difference">
            <div class="text-muted" style="font-family:'Courier New', monospace; font-size:11px; letter-spacing:2px; color:#5B6B7A; text-transform:uppercase; padding-top:16px;">Scan at Kit Pickup</div>
          </div></div>
        </td></tr>
        <tr><td align="center" style="padding:8px 32px 24px 32px;">
          <div class="gmail-blend-screen"><div class="gmail-blend-difference">
            <div class="text-gold" style="font-family:'Courier New', monospace; font-size:24px; letter-spacing:3px; color:#C1121F; font-weight:bold;">__BIB_CODE__</div>
          </div></div>
        </td></tr>
        <tr><td style="padding:0 32px;">
          <div class="gmail-blend-screen"><div class="gmail-blend-difference">
            <div style="border-top:2px dashed #E2E7EF; font-size:0; line-height:0;">&nbsp;</div>
          </div></div>
        </td></tr>
        <tr><td style="padding:24px 32px 8px 32px;">
          <div class="gmail-blend-screen"><div class="gmail-blend-difference">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="font-family:'Courier New', monospace; font-size:12px;">
              <tr><td class="text-muted" style="color:#5B6B7A; text-transform:uppercase; letter-spacing:1px; padding:8px 0;">Lead Runner</td>
                  <td align="right" class="text-cream" style="color:#152243; font-weight:bold; padding:8px 0;">__GUEST_NAME__</td></tr>
              <tr><td class="text-muted" style="color:#5B6B7A; text-transform:uppercase; letter-spacing:1px; padding:8px 0; border-top:1px solid #E2E7EF;">Category</td>
                  <td align="right" class="text-cream" style="color:#152243; padding:8px 0; border-top:1px solid #E2E7EF;">__PACKAGE__</td></tr>
              <tr><td class="text-muted" style="color:#5B6B7A; text-transform:uppercase; letter-spacing:1px; padding:8px 0; border-top:1px solid #E2E7EF;">Runners</td>
                  <td align="right" class="text-cream" style="color:#152243; padding:8px 0; border-top:1px solid #E2E7EF;">__GUESTS__ __GUEST_WORD__</td></tr>
              <tr><td class="text-muted" style="color:#5B6B7A; text-transform:uppercase; letter-spacing:1px; padding:8px 0; border-top:1px solid #E2E7EF;">Shirt Size</td>
                  <td align="right" class="text-cream" style="color:#152243; padding:8px 0; border-top:1px solid #E2E7EF;">__SHIRT_SIZE__</td></tr>
              <tr><td class="text-muted" style="color:#5B6B7A; text-transform:uppercase; letter-spacing:1px; padding:8px 0; border-top:1px solid #E2E7EF;">Date</td>
                  <td align="right" class="text-cream" style="color:#152243; padding:8px 0; border-top:1px solid #E2E7EF;">__DATE_SHORT__</td></tr>
              <tr><td class="text-muted" style="color:#5B6B7A; text-transform:uppercase; letter-spacing:1px; padding:8px 0; border-top:1px solid #E2E7EF;">Venue</td>
                  <td align="right" class="text-cream" style="color:#152243; padding:8px 0; border-top:1px solid #E2E7EF;">Lima Estate, Malvar</td></tr>
            </table>
          </div></div>
        </td></tr>
        <tr><td style="padding:16px 32px 36px 32px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="notice-edge" style="background-color:#F2D45C; border-radius:14px;">
            <tr><td style="padding:1px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="notice-bg" style="background-color:#FFF9E0; border-radius:13px;">
                <tr><td style="padding:16px;">
                  <div class="gmail-blend-screen"><div class="gmail-blend-difference">
                    <div class="text-muted" style="font-size:12px; color:#5B6B7A; line-height:1.6;">
                      <span class="text-gold" style="color:#C1121F; font-weight:bold;">__DATE_LONG__.</span> Kit pickup opens at 4:00 AM. Gun start varies per category. Registrations are final and non-transferable.
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
        <div class="text-muted" style="font-size:11px; color:#5B6B7A; line-height:1.7;">
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

    return (html.replace("__STYLE__", EMAIL_STYLE)
                .replace("__WORDMARK__", wordmark_html)
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
    """Sends the confirmation ticket (QR + bib). Returns True if Gmail accepted it."""
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
        return True
    except Exception as e:
        print(f"ERROR sending email to {to_email}: {str(e)}")
        traceback.print_exc()
        return False


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
            <div class="text-muted" style="font-family:'Courier New', monospace; font-size:9px; letter-spacing:3px; color:#5B6B7A; text-transform:uppercase; margin-top:10px;">LIMA ESTATE &middot; MALVAR</div>
          </div></div>"""
        else:
            wordmark_html = """
          <div class="gmail-blend-screen"><div class="gmail-blend-difference">
            <span class="text-gold" style="font-family:'Courier New', monospace; font-size:16px; letter-spacing:4px; color:#C1121F; text-transform:uppercase; font-weight:bold;">PROJECT STRIDE</span>
            <div class="text-muted" style="font-family:'Courier New', monospace; font-size:9px; letter-spacing:3px; color:#5B6B7A; text-transform:uppercase; margin-top:6px;">LIMA ESTATE &middot; MALVAR</div>
          </div></div>"""

        html_body = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="color-scheme" content="light dark">
<meta name="supported-color-schemes" content="light dark">
{EMAIL_STYLE}
</head>
<body class="body body-bg" style="margin:0; padding:0; background-color:#F1F4F8; font-family:Arial, Helvetica, sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="body-bg" style="background-color:#F1F4F8; padding:32px 12px;">
<tr><td align="center">
  <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="max-width:480px; width:100%;">
    <tr><td align="center" style="padding-bottom:28px;">{wordmark_html}</td></tr>
    <tr><td class="card-edge" style="background-color:#C1121F; border-radius:24px; padding:2px;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="card-bg" style="background-color:#FFFFFF; border-radius:22px;">
        <tr><td align="center" style="padding:36px 32px 24px 32px;">
          <div class="gmail-blend-screen"><div class="gmail-blend-difference">
            <div class="text-gold" style="font-family:'Courier New', monospace; font-size:11px; letter-spacing:3px; color:#C1121F; text-transform:uppercase; margin-bottom:12px;">Payment Reminder</div>
            <div class="text-cream" style="font-family:Arial, sans-serif; font-weight:bold; font-size:26px; color:#152243; letter-spacing:-0.5px;">Complete Your Registration</div>
            <div class="text-muted" style="font-size:13px; color:#5B6B7A; line-height:1.6; padding:16px 8px 0 8px;">
              Hi {guest_name}, we noticed you requested a spot for <strong>{package_name}</strong> ({guests} {guest_word}) but haven't uploaded your payment receipt yet. Since bibs are strictly capped, unpaid holds are released automatically.
            </div>
          </div></div>
        </td></tr>
        <tr><td style="padding:0 32px 28px 32px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="amount-box-bg" style="background-color:#F1F4F8; border:1px solid #E2E7EF; border-radius:16px;">
            <tr><td align="center" style="padding:20px;">
              <div class="gmail-blend-screen"><div class="gmail-blend-difference">
                <div class="text-muted" style="font-family:'Courier New', monospace; font-size:10px; letter-spacing:2px; color:#5B6B7A; text-transform:uppercase;">Amount Due</div>
                <div class="text-amount" style="font-family:Arial, sans-serif; font-size:28px; color:#C1121F; font-weight:bold; margin-top:4px;">₱{_fmt_amount(total_amount)}</div>
              </div></div>
            </td></tr>
          </table>
        </td></tr>
        <tr><td align="center" style="padding:0 32px 36px 32px;">
          <div class="gmail-blend-screen"><div class="gmail-blend-difference">
            <div class="text-muted" style="font-size:12px; color:#5B6B7A; line-height:1.6;">
              To finalize your entry, please complete your transfer via GCash or Bank Transfer and upload your screenshot on our website.
            </div>
          </div></div>
        </td></tr>
      </table>
    </td></tr>
    <tr><td align="center" style="padding:28px 20px 8px 20px;">
      <div class="gmail-blend-screen"><div class="gmail-blend-difference">
        <div class="text-muted" style="font-size:11px; color:#5B6B7A; line-height:1.7;">
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
            f"Amount Due: ₱{_fmt_amount(total_amount)}\n\n"
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
        traceback.print_exc()

def send_reschedule_email(to_email, guest_name, bib_code=None, package_name=None, guests=1):
    """Notifies a confirmed participant that the event moved to January 23, 2027."""
    from html import escape
    try:
        service = get_gmail_service()
        logo_bytes = _load_logo_bytes()
        logo_msgid = None
        logo_cid = None
        if logo_bytes:
            logo_msgid = make_msgid(domain="projectstride.ph")
            logo_cid = logo_msgid[1:-1]

        name = escape(str(guest_name or "Runner"))
        bib = escape(str(bib_code or "—"))
        pkg = escape(str(package_name or "—"))

        # blend() wrappers are inert now that the design is light (the dark-mode
        # blend CSS was removed); kept so the markup stays simple to edit.
        def blend(inner):
            return f'<div class="gmail-blend-screen"><div class="gmail-blend-difference">{inner}</div></div>'

        if logo_cid:
            wordmark_html = f"""
          <img src="cid:{logo_cid}" alt="Project Stride" width="140" style="display:block; width:140px; max-width:60%; height:auto; border:0; margin:0 auto; border-radius:50%;">
          {blend('<div class="text-muted" style="font-family:Courier New, monospace; font-size:9px; letter-spacing:3px; color:#5B6B7A; text-transform:uppercase; margin-top:10px;">LIMA ESTATE &middot; MALVAR</div>')}"""
        else:
            wordmark_html = blend(
                '<span class="text-gold" style="font-family:Courier New, monospace; font-size:16px; letter-spacing:4px; color:#C1121F; text-transform:uppercase; font-weight:bold;">PROJECT STRIDE</span>'
                '<div class="text-muted" style="font-family:Courier New, monospace; font-size:9px; letter-spacing:3px; color:#5B6B7A; text-transform:uppercase; margin-top:6px;">LIMA ESTATE &middot; MALVAR</div>')

        def perk(title, body):
            return f"""
            <tr><td style="padding:10px 0; border-top:1px solid #E2E7EF;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
                <td width="30" valign="top">{blend('<div class="text-gold" style="color:#C1121F; font-size:16px; font-weight:bold;">&#10003;</div>')}</td>
                <td>{blend(f'<div class="text-cream" style="font-size:13px; line-height:1.5; color:#152243; font-weight:bold;">{title}</div><div class="text-muted" style="color:#5B6B7A; font-size:12px; line-height:1.5;">{body}</div>')}</td>
              </tr></table>
            </td></tr>"""

        perks_html = (
            perk("&#8369;500 cash incentive", "Given upon participation on the rescheduled event date.")
            + perk("Priority race kit claiming", "Skip the line when you pick up your kit.")
            + perk("Automatic registration transfer", "Your existing registration moves to January 23, 2027 at no additional cost.")
        )

        def detail_row(label, value, value_class="text-cream", value_color="#152243", first=False):
            border = "" if first else " border-top:1px solid #E2E7EF;"
            return (f'<tr><td class="text-muted" style="color:#5B6B7A; text-transform:uppercase; letter-spacing:1px; padding:8px 0;{border}">{label}</td>'
                    f'<td align="right" class="{value_class}" style="color:{value_color}; font-weight:bold; padding:8px 0;{border}">{value}</td></tr>')

        html_body = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="color-scheme" content="light dark">
<meta name="supported-color-schemes" content="light dark">
{EMAIL_STYLE}
</head>
<body class="body body-bg" style="margin:0; padding:0; background-color:#F1F4F8; font-family:Arial, Helvetica, sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="body-bg" style="background-color:#F1F4F8; padding:32px 12px;">
<tr><td align="center">
  <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="max-width:480px; width:100%;">
    <tr><td align="center" style="padding-bottom:28px;">{wordmark_html}</td></tr>
    <tr><td class="card-edge" style="background-color:#C1121F; border-radius:24px; padding:2px;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="card-bg" style="background-color:#FFFFFF; border-radius:22px;">

        <tr><td align="center" style="padding:36px 28px 8px 28px;">
          {blend(f'''<div class="text-gold" style="font-family:Courier New, monospace; font-size:11px; letter-spacing:3px; color:#C1121F; text-transform:uppercase; margin-bottom:12px;">Important Event Update</div>
          <div class="text-cream" style="font-size:26px; font-weight:bold; color:#152243; letter-spacing:-0.5px; line-height:1.2;">We&rsquo;ve Moved the Date</div>
          <div class="text-muted" style="font-size:13px; color:#5B6B7A; line-height:1.6; padding:14px 4px 0 4px;">Dear {name}, thank you for registering for Project Stride 2026: Fun Run &amp; Duathlon.</div>''')}
        </td></tr>

        <tr><td style="padding:24px 28px 8px 28px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="panel-bg" style="background-color:#F1F4F8; border-radius:16px;">
            <tr>
              <td align="center" width="50%" style="padding:18px 6px;">
                {blend('''<div class="text-muted" style="font-family:Courier New, monospace; font-size:10px; letter-spacing:2px; color:#5B6B7A; text-transform:uppercase;">Original</div>
                <div class="text-muted" style="font-size:15px; color:#5B6B7A; text-decoration:line-through; margin-top:6px;">Nov 28, 2026</div>''')}
              </td>
              <td align="center" width="50%" style="padding:18px 6px; border-left:1px solid #E2E7EF;">
                {blend('''<div class="text-gold" style="font-family:Courier New, monospace; font-size:10px; letter-spacing:2px; color:#C1121F; text-transform:uppercase;">New Date</div>
                <div class="text-gold" style="font-size:20px; color:#C1121F; font-weight:bold; margin-top:6px;">Jan 23, 2027</div>''')}
              </td>
            </tr>
          </table>
        </td></tr>

        <tr><td style="padding:16px 28px 0 28px;">
          {blend('<div class="text-muted" style="font-size:13px; color:#5B6B7A; line-height:1.7;">The event has been rescheduled to <span class="text-cream" style="color:#152243; font-weight:bold;">January 23, 2027</span>. The adjustment allows us to accommodate an expanded race course in conjunction with the Lima Outlets&rsquo; Car-Free Saturday initiative.</div>')}
        </td></tr>

        <tr><td style="padding:24px 28px 0 28px;">
          {blend('''<div class="text-gold" style="font-family:Courier New, monospace; font-size:11px; letter-spacing:3px; color:#C1121F; text-transform:uppercase; margin-bottom:8px;">Founding Participant Privilege Package</div>
          <div class="text-muted" style="font-size:12px; color:#5B6B7A; line-height:1.6; margin-bottom:6px;">In recognition of your early registration, we are extending an exclusive package:</div>''')}
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0">{perks_html}</table>
        </td></tr>

        <tr><td style="padding:20px 28px 0 28px;">
          {blend(f'''<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="font-family:Courier New, monospace; font-size:12px;">
            {detail_row("Bib Code", bib, "text-gold", "#C1121F", first=True)}
            {detail_row("Category", pkg)}
            {detail_row("Status", "Registration valid")}
          </table>''')}
        </td></tr>

        <tr><td style="padding:20px 28px 36px 28px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="notice-edge" style="background-color:#F2D45C; border-radius:14px;"><tr><td style="padding:1px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="notice-bg" style="background-color:#FFF9E0; border-radius:13px;"><tr><td style="padding:16px;">
              {blend('''<div class="text-muted" style="font-size:12px; color:#5B6B7A; line-height:1.7;">
                <span class="text-gold" style="color:#C1121F; font-weight:bold;">Payments &amp; refunds.</span> All existing registrations and payments are automatically carried over to the new date and are non-refundable. However, should the event be postponed again and fail to proceed on the subsequent rescheduled date, the corresponding registration payments shall be refunded.<br><br>
                <span class="text-cream" style="color:#152243; font-weight:bold;">No further action is required on your part.</span>
              </div>''')}
            </td></tr></table>
          </td></tr></table>
        </td></tr>

      </table>
    </td></tr>
    <tr><td align="center" style="padding:28px 20px 8px 20px;">
      {blend('''<div class="text-cream" style="font-size:12px; color:#152243; line-height:1.7;">We appreciate your understanding and continued support.</div>
      <div class="text-muted" style="font-size:11px; color:#5B6B7A; line-height:1.7; margin-top:8px;">Respectfully, Project Stride 2026 Organizing Committee<br>Lima Estate, Malvar, Batangas &middot; Questions? Reply to this email.</div>''')}
    </td></tr>
  </table>
</td></tr>
</table>
</body>
</html>"""

        text_body = (
            f"Dear {guest_name},\n\n"
            "Thank you for registering for Project Stride 2026: Fun Run & Duathlon.\n\n"
            "Please be informed that the event, originally scheduled for November 28, 2026, has been rescheduled to January 23, 2027.\n\n"
            "The adjustment will allow us to accommodate an expanded race course in conjunction with the Lima Outlets' Car-Free Saturday initiative.\n\n"
            "In recognition of your early registration, we are extending an exclusive Founding Participant Privilege Package, which includes:\n"
            "* P500 cash incentive upon participation on the rescheduled event date;\n"
            "* Priority race kit claiming; and\n"
            "* Automatic transfer of your existing registration to January 23, 2027, at no additional cost.\n\n"
            "Please be advised that all existing registrations and payments shall automatically be carried over to the rescheduled event date and shall be considered non-refundable. "
            "However, should the event be postponed again and fail to proceed on the subsequent rescheduled date, the corresponding registration payments shall be refunded.\n\n"
            "Your registration shall remain valid for the rescheduled event. No further action is required on your part.\n\n"
            "We appreciate your understanding and continued support.\n\n"
            "Respectfully,\nProject Stride 2026 Organizing Committee"
        )

        msg = EmailMessage()
        msg['To'] = to_email
        msg['From'] = os.environ.get("SENDER_EMAIL", "hello@projectstride.ph")
        msg['Subject'] = "Important Update: Project Stride 2026 is now January 23, 2027"
        msg.set_content(text_body)
        msg.add_alternative(html_body, subtype='html')

        if logo_bytes:
            html_part = msg.get_payload()[1]
            html_part.add_related(logo_bytes, maintype='image', subtype='jpeg', cid=logo_msgid, filename='logo.jpg', disposition='inline')

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId="me", body={'raw': raw}).execute()
        print(f"Successfully sent reschedule email to {to_email}")
    except Exception as e:
        print(f"ERROR sending reschedule email to {to_email}: {str(e)}")
        traceback.print_exc()

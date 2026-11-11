"""
Gmail API diagnostic for Project Stride email automation.

Usage (run where the app runs, with the same env vars):
    python check_gmail.py                 # check credentials only
    python check_gmail.py you@example.com # also send a real test email

It loads credentials exactly like email_module.get_gmail_service() and
reports which step fails and why.
"""
import json
import os
import sys

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError

SCOPES = ['https://www.googleapis.com/auth/gmail.send']


def fail(msg):
    print(f"\n[FAIL] {msg}")
    sys.exit(1)


def main():
    print("== 1. Locating credentials ==")
    token_json_str = os.environ.get("GMAIL_TOKEN_JSON")
    if token_json_str:
        print("Using GMAIL_TOKEN_JSON env var")
        try:
            info = json.loads(token_json_str)
        except json.JSONDecodeError as e:
            fail(f"GMAIL_TOKEN_JSON is not valid JSON ({e}). "
                 "Paste the whole token.json content as one line, no extra quotes.")
    elif os.path.exists("token.json"):
        print("Using token.json in current directory")
        with open("token.json") as f:
            info = json.load(f)
    else:
        fail("No credentials: set GMAIL_TOKEN_JSON or put token.json next to the app.")

    print("\n== 2. Checking token contents ==")
    for key in ("client_id", "client_secret", "refresh_token"):
        print(f"  {key:14} {'present' if info.get(key) else 'MISSING'}")
    if not info.get("refresh_token"):
        fail("No refresh_token. Re-run the OAuth flow with access_type='offline' "
             "and prompt='consent' to get one.")
    scopes = info.get("scopes") or info.get("scope") or []
    if isinstance(scopes, str):
        scopes = scopes.split()
    print(f"  scopes         {scopes or '(not recorded)'}")
    if scopes and not any(s in scopes for s in (SCOPES[0], "https://mail.google.com/",
                                                "https://www.googleapis.com/auth/gmail.compose",
                                                "https://www.googleapis.com/auth/gmail.modify")):
        fail("Token was not granted a scope that allows sending mail (gmail.send).")

    creds = Credentials.from_authorized_user_info(info, SCOPES)

    print("\n== 3. Refreshing access token with Google ==")
    try:
        creds.refresh(Request())
    except RefreshError as e:
        msg = str(e)
        print(f"  Google said: {msg}")
        if "invalid_grant" in msg:
            fail("invalid_grant: the refresh token is expired or revoked.\n"
                 "  Most common cause: your OAuth consent screen is in 'Testing' mode,\n"
                 "  so refresh tokens expire after 7 days. Fix: Google Cloud Console ->\n"
                 "  APIs & Services -> OAuth consent screen -> Publish app, then\n"
                 "  generate a new token.json and update GMAIL_TOKEN_JSON.")
        if "invalid_client" in msg:
            fail("invalid_client: client_id/client_secret are wrong or the OAuth "
                 "client was deleted in Google Cloud Console.")
        if "unauthorized_client" in msg:
            fail("unauthorized_client: token was issued for a different OAuth client.")
        fail("Token refresh failed (see message above).")
    except Exception as e:
        fail(f"Could not reach Google to refresh token: {e}")
    print(f"  OK, new access token valid until {creds.expiry} UTC")

    sender = os.environ.get("SENDER_EMAIL", "hello@projectstride.ph")
    print(f"\n== 4. Sender ==\n  From header will be: {sender}")
    print("  This must be the Gmail account that authorized the token, or a verified\n"
          "  'Send mail as' alias in that account's Gmail settings. Otherwise Gmail\n"
          "  rewrites or rejects the From address.")

    to = sys.argv[1] if len(sys.argv) > 1 else None
    if not to:
        print("\n[OK] Credentials work. Pass an address to send a real test email:\n"
              "     python check_gmail.py you@example.com")
        return

    print(f"\n== 5. Sending test email to {to} ==")
    import base64
    from email.message import EmailMessage
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError

    msg = EmailMessage()
    msg["To"] = to
    msg["From"] = sender
    msg["Subject"] = "Project Stride Gmail API test"
    msg.set_content("If you can read this, the Gmail API is working.")
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    try:
        service = build("gmail", "v1", credentials=creds)
        sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    except HttpError as e:
        print(f"  HTTP {e.resp.status}: {e}")
        if e.resp.status == 403 and ("has not been used" in str(e) or "disabled" in str(e)):
            fail("Gmail API is not enabled for this Google Cloud project. Enable it at\n"
                 "  APIs & Services -> Library -> Gmail API -> Enable.")
        if e.resp.status == 403:
            fail("Permission denied: scope missing or sending blocked for this account.")
        if e.resp.status == 429:
            fail("Rate limit / daily sending quota exceeded. Wait and retry.")
        fail("Gmail send failed (see message above).")
    print(f"  Sent. Gmail message id: {sent.get('id')}")
    print("\n[OK] Everything works. Check the inbox (and spam folder).")


if __name__ == "__main__":
    main()

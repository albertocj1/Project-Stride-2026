"""
Generate a fresh Gmail API token.json for Project Stride email automation.

Run this on your own computer (it opens a browser to sign in):
    pip install google-auth-oauthlib
    python generate_token.py

Needs credentials.json (an OAuth client of type "Desktop app" downloaded from
Google Cloud Console -> Google Auth Platform -> Clients) in this folder.
Writes token.json and prints a one-line version to paste into the
GMAIL_TOKEN_JSON environment variable on Render.
"""
import json
import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/gmail.send']


def main():
    if not os.path.exists("credentials.json"):
        sys.exit("credentials.json not found. Download it from Google Cloud Console -> "
                 "Google Auth Platform -> Clients (type: Desktop app) and put it here.")

    flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
    # offline + consent guarantees a refresh_token is issued, even if you authorized before
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    if not creds.refresh_token:
        sys.exit("Google did not return a refresh_token. Remove the app at "
                 "myaccount.google.com/connections and run this again.")

    token_json = creds.to_json()
    with open("token.json", "w") as f:
        f.write(token_json)

    print("\nSaved token.json")
    print("\nPaste this single line into GMAIL_TOKEN_JSON on Render:\n")
    print(json.dumps(json.loads(token_json), separators=(",", ":")))
    print("\nKeep it secret: anyone with it can send email as this account.")


if __name__ == "__main__":
    main()

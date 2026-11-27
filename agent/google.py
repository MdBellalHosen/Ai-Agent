"""Read-only Gmail and Google Calendar. Mira can read, never send or delete.

Setup (once): see README "Gmail ar Calendar". The sign-in token stays in data/.
"""
import datetime as dt

from . import config

CREDENTIALS = config.DATA / "google_credentials.json"
TOKEN = config.DATA / "google_token.json"
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly",
          "https://www.googleapis.com/auth/calendar.readonly"]
SETUP = ("Gmail/Calendar is not set up yet. Tell the user to follow the 'Gmail ar Calendar' part "
         "of the README and put google_credentials.json in the data folder.")


def credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES) if TOKEN.exists() else None
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            creds = None
    if not creds or not creds.valid:
        if not CREDENTIALS.exists():
            return None
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS), SCOPES)
        creds = flow.run_local_server(port=0, timeout_seconds=180, open_browser=True)  # one-time sign in
    config.DATA.mkdir(exist_ok=True)
    TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return creds


def service(name, version):
    creds = credentials()
    if not creds:
        return None
    from googleapiclient.discovery import build
    return build(name, version, credentials=creds, cache_discovery=False)


def emails(query, count):
    gmail = service("gmail", "v1")
    if not gmail:
        return SETUP
    found = gmail.users().messages().list(userId="me", q=query,
                                          maxResults=max(1, min(int(count or 5), 15))).execute()
    lines = []
    for item in found.get("messages", []):
        msg = gmail.users().messages().get(userId="me", id=item["id"], format="metadata",
                                           metadataHeaders=["From", "Subject", "Date"]).execute()
        head = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
        lines.append(f"- From: {head.get('From', '?')} | Subject: {head.get('Subject', '(none)')} | "
                     f"{head.get('Date', '')[:22]}\n  {msg.get('snippet', '')[:300]}")
    return "\n".join(lines) or "No emails found"


def unread_emails(count=5):
    """Newest unread emails in the inbox (sender, subject, short preview)."""
    return emails("is:unread in:inbox", count)


def search_emails(query, count=5):
    """Gmail search, e.g. 'from:teacher exam' or 'subject:invoice newer_than:7d'."""
    return emails(query, count)


def calendar_events(days=1):
    """Events from now until N days ahead."""
    cal = service("calendar", "v3")
    if not cal:
        return SETUP
    now = dt.datetime.now(dt.timezone.utc)
    end = now + dt.timedelta(days=max(1, min(int(days or 1), 30)))
    found = cal.events().list(calendarId="primary", timeMin=now.isoformat(), timeMax=end.isoformat(),
                              singleEvents=True, orderBy="startTime", maxResults=20).execute()
    lines = []
    for event in found.get("items", []):
        start = event["start"].get("dateTime", event["start"].get("date", ""))
        lines.append(f"- {start[:16].replace('T', ' ')}: {event.get('summary', '(no title)')}"
                     + (f" @ {event['location']}" if event.get("location") else ""))
    return "\n".join(lines) or "No events"


def ready():
    return TOKEN.exists() or CREDENTIALS.exists()

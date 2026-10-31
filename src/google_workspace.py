"""Opt-in Google Calendar sync and Gmail deadline reminders."""
from __future__ import annotations

import base64
from datetime import date, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CREDENTIALS_FILE = ROOT / "credentials.json"
TOKEN_FILE = ROOT / "data" / "google_token.json"
SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.send",
]


def google_dependencies():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError("Install the optional Google integration packages from requirements.txt.") from exc
    return Request, Credentials, InstalledAppFlow, build


def load_credentials():
    if not TOKEN_FILE.exists():
        return None
    Request, Credentials, _, _ = google_dependencies()
    try:
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    except (OSError, ValueError):
        return None
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
        try:
            TOKEN_FILE.chmod(0o600)
        except OSError:
            pass
    return creds if creds and creds.valid else None


def connect_google():
    if not CREDENTIALS_FILE.exists():
        raise FileNotFoundError("Add your Google OAuth desktop client file as credentials.json in the project folder first.")
    _, _, InstalledAppFlow, _ = google_dependencies()
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True)
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    try:
        TOKEN_FILE.chmod(0o600)
    except OSError:
        pass
    return creds


def services(creds=None):
    _, _, _, build = google_dependencies()
    creds = creds or load_credentials()
    if creds is None:
        raise RuntimeError("Connect your Google account in Settings first.")
    return (build("calendar", "v3", credentials=creds, cache_discovery=False),
            build("gmail", "v1", credentials=creds, cache_discovery=False))


def sync_deadlines(calendar, tasks: list[dict[str, Any]], event_ids: dict[str, str]) -> tuple[dict[str, str], int]:
    """Create/update active deadline events and delete synced events for completed tasks."""
    updated = dict(event_ids)
    changes = 0
    for task in tasks:
        task_id = str(task.get("id"))
        due = task.get("due")
        if task.get("status") == "completed" or not due:
            old_id = updated.pop(task_id, None)
            if old_id:
                try:
                    calendar.events().delete(calendarId="primary", eventId=old_id).execute()
                except Exception as exc:
                    if getattr(exc, "resp", None) is None or exc.resp.status != 404:
                        updated[task_id] = old_id
                        raise
                changes += 1
            continue
        next_day = (date.fromisoformat(due) + timedelta(days=1)).isoformat()
        body = {
            "summary": f"Deadline: {task.get('title', 'Coursework')}",
            "description": (f"Course: {task.get('category', 'General')}\n"
                           f"Priority: {task.get('priority', 'medium')}\n"
                           f"Estimated study time: {task.get('estimated_minutes', 30)} minutes\n"
                           "Managed by Academic Study Planner."),
            "start": {"date": due}, "end": {"date": next_day},
            "extendedProperties": {"private": {"academicPlannerTaskId": task_id}},
        }
        event_id = updated.get(task_id)
        if event_id:
            try:
                calendar.events().update(calendarId="primary", eventId=event_id, body=body).execute()
            except Exception as exc:
                if getattr(exc, "resp", None) is None or exc.resp.status != 404:
                    raise
                result = calendar.events().insert(calendarId="primary", body=body).execute()
                updated[task_id] = result["id"]
        else:
            result = calendar.events().insert(calendarId="primary", body=body).execute()
            updated[task_id] = result["id"]
        changes += 1
    return updated, changes


def send_deadline_reminders(gmail, tasks: list[dict[str, Any]], recipient: str,
                            days_before: int, sent: dict[str, str], today: date | None = None) -> tuple[dict[str, str], list[str]]:
    """Send at most one reminder for each task deadline, when it enters the configured window."""
    if not recipient.strip() or "@" not in recipient:
        raise ValueError("Enter a valid reminder email address.")
    today = today or date.today()
    updated = dict(sent)
    delivered: list[str] = []
    for task in tasks:
        if task.get("status") == "completed" or not task.get("due"):
            continue
        due = date.fromisoformat(task["due"])
        days_left = (due - today).days
        if not 0 <= days_left <= days_before:
            continue
        task_id, due_text = str(task.get("id")), due.isoformat()
        if updated.get(task_id) == due_text:
            continue
        message = EmailMessage()
        message["To"] = recipient.strip()
        message["Subject"] = f"Study planner deadline in {days_left} day(s): {task.get('title', 'Coursework')}"
        message.set_content(
            f"Your coursework deadline is approaching.\n\n"
            f"Task: {task.get('title', 'Coursework')}\n"
            f"Course: {task.get('category', 'General')}\n"
            f"Deadline: {due_text}\n"
            f"Estimated study time: {task.get('estimated_minutes', 30)} minutes\n\n"
            "This reminder was sent by your Academic Study Planner."
        )
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        gmail.users().messages().send(userId="me", body={"raw": raw}).execute()
        updated[task_id] = due_text
        delivered.append(str(task.get("title", "Coursework")))
    return updated, delivered

"""Persistent reminder scheduler backed by SQLite's APScheduler job store."""
from __future__ import annotations

import json
import sqlite3
import urllib.parse
import urllib.request
from datetime import date, datetime, time
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH = ROOT / "data" / "academic_planner.db"


def _send_telegram(bot_token: str, chat_id: str, text: str) -> None:
    if not bot_token or not chat_id:
        return
    endpoint = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    body = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    request = urllib.request.Request(endpoint, data=body, method="POST")
    with urllib.request.urlopen(request, timeout=10) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not result.get("ok"):
        raise RuntimeError("Telegram did not confirm the reminder delivery.")


def _check_deadline_reminders_unlocked() -> None:
    """Persist in-app alerts and deliver configured email/Telegram reminders."""
    import agent
    from academic.deadlines import countdown

    data = agent.load_data()
    today = date.today()
    sent_keys = set(data.get("reminder_history", []))
    email_keys = set(data.get("reminder_email_sent", []))
    telegram_keys = set(data.get("reminder_telegram_sent", []))
    settings = data["settings"]
    mail = settings.get("gmail_reminders", {})
    telegram = settings.get("telegram_reminders", {})
    new_notifications = []
    alert_candidates = []
    due_mail = []
    due_telegram = []
    pending = [task for task in data["tasks"]
               if task.get("status") not in {"completed", "submitted"} and task.get("due")]
    for task in pending:
        try:
            days_left = (date.fromisoformat(task["due"]) - today).days
        except ValueError:
            continue
        intervals = sorted({int(day) for day in task.get("reminder_days", [7, 3, 1, 0])
                            if 0 <= int(day) <= 365}, reverse=True)
        eligible = [day for day in intervals if days_left <= day and days_left >= 0]
        if not eligible:
            if days_left < 0:
                alert_key = f"{task['id']}:{task['due']}:overdue"
                alert_candidates.append((alert_key, task, "overdue"))
                if alert_key not in sent_keys:
                    new_notifications.append((alert_key, task, "overdue"))
            continue
        interval = min(eligible)
        alert_key = f"{task['id']}:{task['due']}:{interval}"
        alert_candidates.append((alert_key, task, f"{interval} day(s)"))
        if alert_key in sent_keys:
            continue
        new_notifications.append((alert_key, task, f"{interval} day(s)"))

    now = datetime.now().astimezone()
    for session in data.get("study_sessions", []):
        if session.get("status") not in {"planned", "rescheduled"} or session.get("kind") == "break":
            continue
        try:
            starts = datetime.combine(date.fromisoformat(session["date"]),
                time.fromisoformat(session.get("start", "00:00"))).astimezone()
        except (KeyError, ValueError):
            continue
        if 0 <= (starts - now).total_seconds() <= 15 * 60:
            alert_key = f"session:{session['id']}:before"
            session_task = {"id": session.get("task_id", session["id"]),
                "title": session.get("title", "Study session"), "due": session["date"],
                "due_time": session.get("start", ""), "category": "Study session",
                "work_status": "planned", "estimated_minutes": session.get("duration_minutes", 30)}
            alert_candidates.append((alert_key, session_task, "study session"))
            if alert_key not in sent_keys:
                new_notifications.append((alert_key, session_task, "study session"))

    if mail.get("enabled") and mail.get("recipient"):
        due_mail = [item for item in alert_candidates if item[0] not in email_keys]
    if telegram.get("enabled") and telegram.get("bot_token") and telegram.get("chat_id"):
        due_telegram = [item for item in alert_candidates if item[0] not in telegram_keys]

    if due_mail:
        try:
            from google_workspace import services
            _, gmail = services()
            for alert_key, task, when in due_mail:
                from email.message import EmailMessage
                import base64
                message = EmailMessage()
                message["To"] = mail["recipient"]
                message["Subject"] = f"Academic deadline {when}: {task.get('title', 'Coursework')}"
                message.set_content(f"{task.get('title', 'Coursework')} is due {task['due']} at {task.get('due_time', '23:59')}.\n"
                    f"Course: {task.get('category', 'General')}\nStatus: {task.get('work_status', 'not_started')}\n"
                    f"Remaining work estimate: {task.get('estimated_minutes', 30) * (100 - float(task.get('percent_complete', 0))) / 100:.0f} minutes.")
                raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
                gmail.users().messages().send(userId="me", body={"raw": raw}).execute()
                email_keys.add(alert_key)
        except Exception as exc:
            agent.log_event(f"Gmail reminder delivery failed: {exc}")

    for alert_key, task, when in due_telegram:
        try:
            _send_telegram(telegram["bot_token"], telegram["chat_id"],
                f"Academic deadline {when}: {task.get('title', 'Coursework')} — due {task['due']}.")
            telegram_keys.add(alert_key)
        except Exception as exc:
            agent.log_event(f"Telegram reminder delivery failed: {exc}")

    for alert_key, task, when in new_notifications:
        if alert_key in sent_keys:
            continue
        data["notifications"].append({"id": len(data["notifications"]) + 1,
            "task_id": task.get("id"), "title": task.get("title", "Coursework"),
            "alert_key": alert_key,
            "message": (f"Overdue since {task['due']}" if when == "overdue"
                        else f"Deadline in {when} · due {task['due']}"),
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "read": False, "in_app": True,
            "email_sent": alert_key in email_keys, "telegram_sent": alert_key in telegram_keys})
        sent_keys.add(alert_key)
    for notification in data["notifications"]:
        alert_key = notification.get("alert_key")
        if alert_key:
            notification["email_sent"] = alert_key in email_keys
            notification["telegram_sent"] = alert_key in telegram_keys
    data["reminder_history"] = sorted(sent_keys)
    data["reminder_email_sent"] = sorted(email_keys)
    data["reminder_telegram_sent"] = sorted(telegram_keys)
    agent.save_data(data)


def check_deadline_reminders() -> None:
    """Use a SQLite lease so the dashboard and standalone service cannot double-send."""
    owner = uuid4().hex
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    try:
        connection.execute("CREATE TABLE IF NOT EXISTS scheduler_lease (name TEXT PRIMARY KEY, owner TEXT NOT NULL, expires REAL NOT NULL)")
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT owner, expires FROM scheduler_lease WHERE name='reminders'").fetchone()
        now = datetime.now().timestamp()
        if row and float(row[1]) > now:
            connection.rollback()
            return
        connection.execute("INSERT OR REPLACE INTO scheduler_lease(name, owner, expires) VALUES ('reminders', ?, ?)",
                           (owner, now + 600))
        connection.commit()
    finally:
        connection.close()
    try:
        _check_deadline_reminders_unlocked()
    finally:
        with sqlite3.connect(DATABASE_PATH, timeout=10) as connection:
            connection.execute("DELETE FROM scheduler_lease WHERE name='reminders' AND owner=?", (owner,))


def create_daily_briefing() -> None:
    import agent
    from academic.deadlines import assess_deadline_risk, optimize_workload

    data = agent.load_data()
    today = date.today()
    if any(row.get("date") == today.isoformat() for row in data.get("briefings", [])):
        return
    settings = data["settings"]
    top = optimize_workload(data["tasks"], int(settings.get("daily_focus_minutes", 120)), settings)[:3]
    week_end = (today.fromordinal(today.toordinal() + 7)).isoformat()
    upcoming = [task for task in data["tasks"] if task.get("status") not in {"completed", "submitted"}
                and task.get("due") and today.isoformat() <= task["due"] <= week_end]
    risks = assess_deadline_risk(data["tasks"], int(settings.get("daily_focus_minutes", 120)), settings=settings)
    risky = [row for row in risks if row["risk"] == "high"]
    today_sessions = [row for row in data.get("study_sessions", [])
        if row.get("date") == today.isoformat() and row.get("kind") != "break"
        and row.get("status") in {"planned", "rescheduled"}]
    next_action = top[0]["title"] if top else "Add coursework or review your syllabus."
    summary = (f"Top priorities: {', '.join(task['title'] for task in top) or 'none saved'}. "
        f"{len(upcoming)} deadline(s) within 7 days. {len(today_sessions)} study session(s) scheduled. "
        f"{len(risky)} high-risk item(s). Next action: {next_action}.")
    briefing = {"date": today.isoformat(), "summary": summary,
        "top_task_ids": [task.get("id") for task in top],
        "upcoming_task_ids": [task.get("id") for task in upcoming],
        "risk_task_ids": [row["task_id"] for row in risky],
        "session_ids": [row.get("id") for row in today_sessions]}
    data["briefings"].append(briefing)
    data["notifications"].append({"id": max([int(row.get("id", 0)) for row in data["notifications"]] + [0]) + 1,
        "title": "Daily academic briefing", "message": summary,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"), "read": False, "in_app": True})
    agent.save_data(data)


def start_scheduler(database_path: Path, briefing_hour: int = 7):
    """Start a process-wide recurring job; job definitions survive restarts in SQLite."""
    try:
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError as exc:
        raise RuntimeError("Install APScheduler and SQLAlchemy from requirements.txt to enable persistent reminders.") from exc
    scheduler = BackgroundScheduler(jobstores={"default": SQLAlchemyJobStore(url=f"sqlite:///{database_path}")},
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600})
    scheduler.add_job(check_deadline_reminders, "interval", minutes=15,
                      next_run_time=datetime.now().astimezone(),
                      id="academic-deadline-reminders", replace_existing=True)
    scheduler.add_job(create_daily_briefing, "cron", hour=min(max(int(briefing_hour), 0), 23), minute=0,
                      id="daily-academic-briefing", replace_existing=True)
    scheduler.start()
    return scheduler

"""Availability-aware daily, weekly, and monthly study plan generation."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from academic.deadlines import optimize_workload, remaining_minutes


def _windows_for_day(day: date, events: list[dict[str, Any]], availability: dict[str, Any],
                     fallback_start: str, fallback_end: str) -> list[tuple[datetime, datetime]]:
    weekdays = availability.get("available_weekdays")
    if weekdays is not None and day.weekday() not in {int(value) for value in weekdays}:
        return []
    daily = availability.get(str(day.weekday()), [])
    if not daily:
        daily = [{"start": fallback_start, "end": fallback_end}]
    windows: list[tuple[datetime, datetime]] = []
    for block in daily:
        try:
            start = datetime.combine(day, time.fromisoformat(block["start"]))
            end = datetime.combine(day, time.fromisoformat(block["end"]))
        except (KeyError, ValueError, TypeError):
            continue
        if end > start:
            windows.append((start, end))
    busy = []
    for event in events:
        if event.get("date") != day.isoformat():
            continue
        try:
            start = datetime.combine(day, time.fromisoformat(event["start"]))
            end = datetime.combine(day, time.fromisoformat(event["end"]))
        except (KeyError, ValueError):
            continue
        if end > start:
            busy.append((start, end))
    for busy_start, busy_end in sorted(busy):
        next_windows = []
        for start, end in windows:
            if busy_end <= start or busy_start >= end:
                next_windows.append((start, end))
                continue
            if busy_start > start:
                next_windows.append((start, busy_start))
            if busy_end < end:
                next_windows.append((busy_end, end))
        windows = next_windows
    return sorted(windows)


def build_study_plan(tasks: list[dict[str, Any]], events: list[dict[str, Any]],
                     settings: dict[str, Any], study_sessions: list[dict[str, Any]],
                     topics: list[dict[str, Any]], exams: list[dict[str, Any]],
                     start_day: date | None = None, horizon_days: int = 1) -> dict[str, Any]:
    """Schedule realistic task chunks only inside the student's available windows."""
    if not 1 <= horizon_days <= 31:
        raise ValueError("Plan horizon must be between 1 and 31 days.")
    first_day = start_day or date.today()
    daily_budget = int(settings.get("daily_focus_minutes", 120))
    session_length = min(max(int(settings.get("study_session_minutes", 60)), 15), 180)
    break_minutes = min(max(int(settings.get("break_minutes", 10)), 0), 60)
    fallback_start = str(settings.get("availability_start", "09:00"))
    fallback_end = str(settings.get("availability_end", "18:00"))
    availability = {**settings.get("weekly_availability", {}),
                    "available_weekdays": settings.get("available_weekdays")}
    busy_events = list(events) + [{"date": session.get("date"), "start": session.get("start"),
        "end": session.get("end"), "title": session.get("title", "Planned session")}
        for session in study_sessions if session.get("source") != "generated_plan"
        and session.get("kind") != "break" and session.get("status") in {"planned", "rescheduled", "completed"}]
    study_sessions = [session for session in study_sessions
                      if not (session.get("source") == "generated_plan"
                              and session.get("status") in {"planned", "rescheduled"}
                              and session.get("date", "") >= first_day.isoformat())]

    exam_by_id = {str(exam.get("id")): exam for exam in exams}
    work = []
    for task in optimize_workload(tasks, daily_budget, settings):
        remaining = remaining_minutes(task)
        if remaining > 0:
            work.append({"kind": "task", "task_id": task.get("id"), "title": task.get("title", "Study task"),
                         "course_id": task.get("course_id"), "remaining": remaining,
                         "due": task.get("due"), "difficulty": task.get("difficulty", 3)})
    for topic in topics:
        if topic.get("status") in {"mastered"}:
            continue
        exam = exam_by_id.get(str(topic.get("exam_id")))
        if not exam or not exam.get("date"):
            continue
        next_review = topic.get("next_review") or first_day.isoformat()
        if next_review <= (first_day + timedelta(days=horizon_days - 1)).isoformat():
            review_due = max(date.fromisoformat(next_review), first_day)
            work.append({"kind": "revision", "topic_id": topic.get("id"),
                         "title": f"Revise {topic.get('title', 'exam topic')} · {exam.get('title', 'Exam')}",
                         "course_id": topic.get("course_id"), "remaining": int(topic.get("study_minutes", 30)),
                         "due": min(exam["date"], review_due.isoformat()),
                         "difficulty": topic.get("difficulty", 3),
                         "weakness": topic.get("status") == "weak"})
    work.sort(key=lambda item: (item.get("due") or "9999-12-31",
                                not item.get("weakness", False),
                                -int(item.get("difficulty", 3)),
                                -int(item.get("remaining", 30))))

    next_session_id = max([int(item.get("id", 0)) for item in study_sessions] + [0]) + 1
    new_sessions: list[dict[str, Any]] = []
    daily_summary = []
    for day_offset in range(horizon_days):
        day = first_day + timedelta(days=day_offset)
        windows = _windows_for_day(day, busy_events, availability, fallback_start, fallback_end)
        day_sessions = []
        remaining_budget = daily_budget
        for window_start, window_end in windows:
            cursor = window_start
            for item in work:
                if item["remaining"] <= 0 or remaining_budget <= 0:
                    continue
                if item.get("due") and item["due"] < day.isoformat():
                    continue
                if day.isoformat() > (item.get("due") or "9999-12-31"):
                    continue
                duration = min(int(item["remaining"]), session_length, remaining_budget)
                end = cursor + timedelta(minutes=duration)
                if end > window_end:
                    continue
                session = {"id": next_session_id, "date": day.isoformat(),
                    "start": cursor.strftime("%H:%M"), "end": end.strftime("%H:%M"),
                    "duration_minutes": duration, "title": item["title"],
                    "kind": item["kind"], "task_id": item.get("task_id"),
                    "topic_id": item.get("topic_id"), "course_id": item.get("course_id"),
                    "status": "planned", "source": "generated_plan"}
                next_session_id += 1
                day_sessions.append(session)
                new_sessions.append(session)
                item["remaining"] -= duration
                remaining_budget -= duration
                cursor = end
                if break_minutes:
                    break_end = cursor + timedelta(minutes=break_minutes)
                    if break_end <= window_end:
                        rest = {"id": next_session_id, "date": day.isoformat(),
                            "start": cursor.strftime("%H:%M"), "end": break_end.strftime("%H:%M"),
                            "duration_minutes": break_minutes, "title": "Break", "kind": "break",
                            "status": "planned", "source": "generated_plan"}
                        new_sessions.append(rest)
                        day_sessions.append(rest)
                        next_session_id += 1
                        cursor = break_end
            if remaining_budget <= 0:
                break
        daily_summary.append({"date": day.isoformat(), "sessions": day_sessions,
            "planned_minutes": sum(session["duration_minutes"] for session in day_sessions
                                    if session.get("kind") != "break"),
            "remaining_budget_minutes": remaining_budget,
            "unavailable_message": "No study time available" if not windows else ""})
    return {"start_date": first_day.isoformat(), "horizon_days": horizon_days,
            "days": daily_summary, "sessions": new_sessions,
            "unscheduled": [{"kind": item["kind"], "title": item["title"],
                             "remaining_minutes": round(item["remaining"]),
                             "due": item.get("due")} for item in work if item["remaining"] > 0],
            "basis": "Deadlines, work estimates, progress, exam review dates, daily budget, availability windows, and class commitments."}


def reschedule_missed_sessions(sessions: list[dict[str, Any]], tasks: list[dict[str, Any]],
                               events: list[dict[str, Any]], settings: dict[str, Any],
                               now: datetime | None = None) -> tuple[list[dict[str, Any]], list[int]]:
    """Move missed planned sessions to the next available slots before their task deadline."""
    current = now or datetime.now()
    missed = [item for item in sessions if item.get("status") in {"planned", "missed"}
              and datetime.combine(date.fromisoformat(item["date"]),
                  time.fromisoformat(item.get("end", "23:59"))) < current]
    updated = [dict(item) for item in sessions]
    moved = []
    daily_budget = int(settings.get("daily_focus_minutes", 120))
    session_length = int(settings.get("study_session_minutes", 60))
    availability = {**settings.get("weekly_availability", {}),
                    "available_weekdays": settings.get("available_weekdays")}
    for original in missed:
        deadline = next((task.get("due") for task in tasks
                         if str(task.get("id")) == str(original.get("task_id"))), None)
        for day_offset in range(0, 31):
            day = current.date() + timedelta(days=day_offset)
            if deadline and day.isoformat() > deadline:
                break
            other_sessions = [session for session in updated
                if session.get("id") != original.get("id")
                and session.get("kind") != "break"
                and session.get("status") in {"planned", "rescheduled", "completed"}]
            occupied = list(events) + other_sessions
            windows = _windows_for_day(day, occupied, availability,
                settings.get("availability_start", "09:00"), settings.get("availability_end", "18:00"))
            for start, end in windows:
                start = max(start, current.replace(second=0, microsecond=0)) if day == current.date() else start
                duration = min(int(original.get("duration_minutes", 30)), session_length, daily_budget)
                if start + timedelta(minutes=duration) <= end:
                    target = next(item for item in updated if item.get("id") == original.get("id"))
                    target["date"] = day.isoformat()
                    target["start"] = start.strftime("%H:%M")
                    target["end"] = (start + timedelta(minutes=duration)).strftime("%H:%M")
                    target["status"] = "rescheduled"
                    target["rescheduled_from"] = original["date"]
                    moved.append(int(target["id"]))
                    break
            if original.get("id") in moved:
                break
    return updated, moved

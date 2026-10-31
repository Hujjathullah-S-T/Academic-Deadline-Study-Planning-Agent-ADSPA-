"""Deterministic deadline countdown, workload risk, and priority scoring."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any

DEFAULT_WEIGHTS = {"urgency": 0.35, "importance": 0.25, "risk": 0.20,
                   "difficulty": 0.10, "blocking": 0.10,
                   "consequence": 0.0, "completion": 0.0}


def deadline_datetime(task: dict[str, Any]) -> datetime | None:
    if not task.get("due"):
        return None
    try:
        due_day = date.fromisoformat(str(task["due"])[:10])
        due_time = time.fromisoformat(str(task.get("due_time") or "23:59"))
    except ValueError:
        return None
    return datetime.combine(due_day, due_time).astimezone()


def countdown(task: dict[str, Any], now: datetime | None = None) -> dict[str, Any] | None:
    deadline = deadline_datetime(task)
    if deadline is None:
        return None
    current = now or datetime.now().astimezone()
    if current.tzinfo is None:
        current = current.astimezone()
    seconds = int((deadline - current).total_seconds())
    if seconds < 0:
        seconds = abs(seconds)
        return {"overdue": True, "days": seconds // 86400,
                "hours": (seconds % 86400) // 3600,
                "minutes": (seconds % 3600) // 60,
                "label": f"Overdue by {seconds // 86400}d {(seconds % 86400) // 3600}h"}
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    return {"overdue": False, "days": days, "hours": hours, "minutes": minutes,
            "label": f"{days}d {hours}h remaining"}


def remaining_minutes(task: dict[str, Any]) -> float:
    estimate = max(float(task.get("estimated_minutes", 30)), 0)
    completion = min(max(float(task.get("percent_complete", 0)), 0), 100)
    return estimate * (100 - completion) / 100


def available_minutes_until(deadline: datetime, daily_minutes: int,
                           settings: dict[str, Any] | None = None,
                           now: datetime | None = None) -> int:
    current = now or datetime.now().astimezone()
    prefs = settings or {}
    available_days = prefs.get("available_weekdays", [0, 1, 2, 3, 4, 5, 6])
    start_text = prefs.get("availability_start", "09:00")
    end_text = prefs.get("availability_end", "18:00")
    configured = prefs.get("weekly_availability", {})
    total = 0
    day = current.date()
    while day <= deadline.date():
        if day.weekday() in {int(value) for value in available_days}:
            windows = configured.get(str(day.weekday()), [])
            if not windows:
                windows = [{"start": start_text, "end": end_text}]
            day_capacity = 0
            for window in windows:
                try:
                    start = datetime.combine(day, time.fromisoformat(window["start"])).astimezone()
                    end = datetime.combine(day, time.fromisoformat(window["end"])).astimezone()
                except (ValueError, KeyError, TypeError):
                    continue
                left = max(start, current) if day == current.date() else start
                right = min(end, deadline) if day == deadline.date() else end
                if right > left:
                    day_capacity += int((right - left).total_seconds() // 60)
            total += min(max(daily_minutes, 0), day_capacity)
        day += timedelta(days=1)
    return total


def assess_deadline_risk(tasks: list[dict[str, Any]], daily_minutes: int,
                         now: datetime | None = None,
                         settings: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    current = now or datetime.now().astimezone()
    results = []
    pending = [task for task in tasks if task.get("status") not in {"completed", "submitted"}]
    for task in pending:
        deadline = deadline_datetime(task)
        if deadline is None:
            continue
        hours_left = (deadline - current).total_seconds() / 3600
        mins_left = remaining_minutes(task)
        difficulty = min(max(int(task.get("difficulty", 3)), 1), 5)
        mins_left *= 1 + 0.12 * (difficulty - 3)
        available = available_minutes_until(deadline, daily_minutes, settings, current)
        competing = sum(remaining_minutes(other) for other in pending
                        if other is not task and deadline_datetime(other) is not None
                        and current <= deadline_datetime(other) <= deadline)
        ratio = mins_left / max(available, 1)
        if hours_left < 0 or ratio >= 1.25:
            risk = "high"
        elif ratio >= 0.7 or competing + mins_left > available:
            risk = "medium"
        else:
            risk = "low"
        causes = []
        if hours_left < 0:
            causes.append("deadline has passed")
        elif mins_left > available:
            causes.append(f"{mins_left:.0f} minutes remain but only {available:.0f} study minutes are available")
        if competing:
            causes.append(f"{competing:.0f} minutes of other work is due by then")
        if difficulty >= 4:
            causes.append(f"difficulty is {difficulty}/5")
        if not causes:
            causes.append("remaining work fits the estimated study capacity")
        results.append({
            "task_id": task.get("id"), "title": task.get("title", "Untitled"),
            "due": deadline.isoformat(timespec="minutes"), "hours_left": round(hours_left, 1),
            "remaining_minutes": round(mins_left), "available_minutes": round(available),
            "competing_minutes": round(competing), "risk": risk,
            "explanation": "; ".join(causes),
            "recovery_plan": recovery_plan(task, round(mins_left), round(available)),
        })
    return sorted(results, key=lambda row: (row["hours_left"],
        {"high": 0, "medium": 1, "low": 2}[row["risk"]]))


def recovery_plan(task: dict[str, Any], remaining: int, available: int) -> list[str]:
    if remaining <= 0:
        return ["Confirm the final file or answers, then submit and save the confirmation."]
    if available < remaining:
        return ["Complete the essential requirements first.",
                f"Use the next available {max(1, available // 60)} study hour(s) on the highest-value work.",
                "Reserve the final available block for checking, documentation, and submission.",
                "Move lower-priority study sessions to a later open slot."]
    return ["Start with the next incomplete checklist item.",
            f"Reserve about {remaining} minutes for the remaining work.",
            "Keep a final review and submission block before the deadline."]


def priority_score(task: dict[str, Any], risk_by_id: dict[Any, dict[str, Any]],
                   weights: dict[str, float] | None = None, now: datetime | None = None) -> float:
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    total = sum(max(float(value), 0) for value in weights.values()) or 1
    weights = {key: max(float(value), 0) / total for key, value in weights.items()}
    countdown_data = countdown(task, now)
    days = countdown_data["days"] if countdown_data else 365
    if countdown_data and countdown_data.get("overdue"):
        urgency = 100
    else:
        urgency = max(0, 100 - min(days, 30) * (100 / 30))
    importance = min(max(float(task.get("importance", 3)), 1), 5) * 20
    risk = {"high": 100, "medium": 60, "low": 20}.get(
        risk_by_id.get(task.get("id"), {}).get("risk"), 20)
    difficulty = min(max(float(task.get("difficulty", 3)), 1), 5) * 20
    blocking = 100 if task.get("blocks_other_tasks") else 0
    consequence = min(max(float(task.get("consequence", 3)), 1), 5) * 20
    completion = min(max(float(task.get("percent_complete", 0)), 0), 100)
    factors = {"urgency": urgency, "importance": importance, "risk": risk,
               "difficulty": difficulty, "blocking": blocking,
               "consequence": consequence, "completion": completion}
    return round(sum(factors[key] * weights[key] for key in weights), 1)


def optimize_workload(tasks: list[dict[str, Any]], daily_minutes: int,
                      settings: dict[str, Any] | None = None,
                      now: datetime | None = None) -> list[dict[str, Any]]:
    risks = {row["task_id"]: row for row in assess_deadline_risk(tasks, daily_minutes, now, settings)}
    pending = [task for task in tasks if task.get("status") not in {"completed", "submitted"}]
    return sorted(pending, key=lambda task: (
        -priority_score(task, risks, (settings or {}).get("priority_weights"), now),
        deadline_datetime(task) or datetime.max.replace(tzinfo=timezone.utc)))


def deadline_collisions(tasks: list[dict[str, Any]], window_hours: int = 48,
                        daily_minutes: int = 240, now: datetime | None = None,
                        settings: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    current = now or datetime.now().astimezone()
    dated = [(deadline_datetime(task), task) for task in tasks
             if task.get("status") not in {"completed", "submitted"}]
    dated = sorted(((due, task) for due, task in dated if due and due >= current),
                   key=lambda item: item[0])
    groups: list[list[tuple[datetime, dict[str, Any]]]] = []
    for item in dated:
        if not groups or item[0] - groups[-1][0][0] > timedelta(hours=window_hours):
            groups.append([item])
        else:
            groups[-1].append(item)
    results = []
    for group in groups:
        if len(group) < 2:
            continue
        workload = sum(remaining_minutes(task) for _, task in group)
        first, last = group[0][0], group[-1][0]
        capacity = available_minutes_until(last, daily_minutes, settings, current)
        results.append({"start": first.isoformat(timespec="minutes"),
            "end": last.isoformat(timespec="minutes"), "task_titles": [task["title"] for _, task in group],
            "workload_minutes": round(workload), "available_minutes": round(capacity),
            "risk": "high" if workload > capacity else "medium",
            "recommendation": "Split work into essential milestones and move lower-priority study blocks." if workload > capacity
                              else "Reserve separate work blocks for each deadline."})
    return results

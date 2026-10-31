"""Deterministic personal-agent modules used by the local dashboard.

These modules contain no network access and do not execute operating-system
actions. They make estimates explicit so the UI can distinguish facts from
recommendations.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Callable
import re
import zipfile
import xml.etree.ElementTree as ET


def _parse_iso_day(value: str) -> date | None:
    try:
        return date.fromisoformat(value[:10]) if value else None
    except (TypeError, ValueError):
        return None


def predict_deadline_risk(tasks: list[dict[str, Any]], daily_minutes: int,
                          as_of: date | None = None) -> list[dict[str, Any]]:
    """Estimate deadline risk from remaining work and available focus days."""
    today = as_of or date.today()
    pending = [t for t in tasks if t.get("status") != "completed"]
    due_tasks = [t for t in pending if _parse_iso_day(t.get("due", ""))]
    results = []
    for task in due_tasks:
        due = _parse_iso_day(task["due"])
        assert due is not None
        days_left = max((due - today).days, 0)
        capacity = max(daily_minutes, 1) * max(days_left + 1, 1)
        workload = sum(int(t.get("estimated_minutes", 30)) for t in due_tasks
                       if (_parse_iso_day(t.get("due", "")) or date.max) <= due)
        ratio = workload / capacity
        if due < today or ratio >= 1:
            level = "high"
        elif ratio >= 0.7:
            level = "medium"
        else:
            level = "low"
        results.append({
            "task_id": task.get("id"), "title": task.get("title", "Untitled"),
            "due": due.isoformat(), "days_left": (due - today).days,
            "remaining_minutes": int(task.get("estimated_minutes", 30)),
            "workload_due_by_then_minutes": workload,
            "available_focus_minutes": capacity,
            "risk": level,
            "confidence": "medium" if task.get("estimated_minutes") else "low",
            "reason": ("Overdue" if due < today else
                       f"{workload} estimated minutes are due by this date against {capacity} available focus minutes"),
        })
    return sorted(results, key=lambda item: (item["days_left"], {"high": 0, "medium": 1, "low": 2}[item["risk"]]))


def build_smart_schedule(tasks: list[dict[str, Any]], events: list[dict[str, Any]],
                         schedule_day: date | None = None, start_at: str = "09:00",
                         end_at: str = "18:00", break_minutes: int = 10) -> dict[str, Any]:
    """Place whole task blocks into free windows around user-entered events."""
    day = schedule_day or date.today()
    start = datetime.combine(day, time.fromisoformat(start_at))
    end = datetime.combine(day, time.fromisoformat(end_at))
    if end <= start:
        raise ValueError("Schedule end must be after its start.")
    if break_minutes < 0 or break_minutes > 60:
        raise ValueError("Break duration must be between 0 and 60 minutes.")

    busy: list[tuple[datetime, datetime, str, str]] = []
    for event in events:
        if event.get("date") != day.isoformat():
            continue
        try:
            event_start = datetime.combine(day, time.fromisoformat(event["start"]))
            event_end = datetime.combine(day, time.fromisoformat(event["end"]))
        except (KeyError, ValueError):
            continue
        if event_end > event_start and event_end > start and event_start < end:
            busy.append((max(event_start, start), min(event_end, end), event.get("title", "Commitment"), "commitment"))
    busy.sort(key=lambda block: block[0])

    windows: list[tuple[datetime, datetime]] = []
    cursor = start
    for busy_start, busy_end, _, _ in busy:
        if busy_start > cursor:
            windows.append((cursor, busy_start))
        cursor = max(cursor, busy_end)
    if cursor < end:
        windows.append((cursor, end))

    blocks: list[dict[str, Any]] = [
        {"kind": kind, "title": title, "start": a.strftime("%H:%M"), "end": b.strftime("%H:%M"), "date": day.isoformat()}
        for a, b, title, kind in busy
    ]
    queue = sorted([t for t in tasks if t.get("status") != "completed"],
                   key=lambda t: (t.get("due") or "9999-12-31",
                                  {"urgent": 0, "high": 1, "medium": 2, "low": 3}.get(t.get("priority"), 2)))
    scheduled_ids: set[Any] = set()
    for window_start, window_end in windows:
        cursor = window_start
        for task in queue:
            task_id = task.get("id")
            if task_id in scheduled_ids:
                continue
            duration = max(int(task.get("estimated_minutes", 30)), 1)
            task_end = cursor + timedelta(minutes=duration)
            if task_end > window_end:
                continue
            blocks.append({"kind": "task", "task_id": task_id, "title": task.get("title", "Untitled"),
                           "start": cursor.strftime("%H:%M"), "end": task_end.strftime("%H:%M"),
                           "duration_minutes": duration, "date": day.isoformat(),
                           "reason": f"{task.get('priority', 'medium')} priority; deadline-ranked"})
            scheduled_ids.add(task_id)
            cursor = task_end
            if break_minutes and cursor + timedelta(minutes=break_minutes) <= window_end:
                break_end = cursor + timedelta(minutes=break_minutes)
                blocks.append({"kind": "break", "title": "Break", "start": cursor.strftime("%H:%M"),
                               "end": break_end.strftime("%H:%M"), "date": day.isoformat()})
                cursor = break_end
    blocks.sort(key=lambda block: block["start"])
    unscheduled = [t.get("id") for t in queue if t.get("id") not in scheduled_ids]
    return {
        "date": day.isoformat(), "start_at": start_at, "end_at": end_at,
        "blocks": blocks, "unscheduled_task_ids": unscheduled,
        "confidence": "estimated", "basis": "Saved task estimates and manually entered commitments; confirm before relying on this schedule.",
    }


def weekly_productivity_report(tasks: list[dict[str, Any]], now: datetime | None = None) -> dict[str, Any]:
    """Summarize task completion in the current Monday-to-Sunday week."""
    current = now or datetime.now().astimezone()
    monday = (current.date() - timedelta(days=current.weekday()))
    next_monday = monday + timedelta(days=7)
    week_tasks = []
    for task in tasks:
        stamp = task.get("completed_at") or task.get("created_at") or ""
        try:
            task_day = datetime.fromisoformat(stamp.replace("Z", "+00:00")).date()
        except ValueError:
            continue
        if monday <= task_day < next_monday:
            week_tasks.append(task)
    completed = [t for t in week_tasks if t.get("status") == "completed"]
    pending = [t for t in tasks if t.get("status") != "completed"]
    total = len(week_tasks)
    return {
        "week_start": monday.isoformat(), "week_end": (next_monday - timedelta(days=1)).isoformat(),
        "created_or_completed": total, "completed": len(completed), "unfinished": len(pending),
        "completion_rate_percent": round(100 * len(completed) / total) if total else 0,
        "completed_on_time": sum(1 for t in completed if not t.get("due") or
                                  (t.get("completed_at", "")[:10] <= t["due"])),
        "overdue_now": sum(1 for t in pending if _parse_iso_day(t.get("due", "")) and _parse_iso_day(t["due"]) < current.date()),
        "by_category": {category: sum(1 for t in completed if t.get("category", "personal") == category)
                        for category in sorted({t.get("category", "personal") for t in completed})},
        "basis": "Counts use task creation and completion timestamps saved by this app.",
    }


def search_personal_knowledge(query: str, collections: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Simple offline ranked search across approved saved text collections."""
    terms = [term for term in re.findall(r"[\w'-]+", query.lower()) if len(term) > 1]
    if not terms:
        return []
    hits = []
    for kind, rows in collections.items():
        for row in rows:
            text = " ".join(str(row.get(key, "")) for key in ("title", "text", "name", "reason", "outcome", "content"))
            normalized = text.lower()
            score = sum(normalized.count(term) for term in terms)
            if score:
                hits.append({"kind": kind, "id": row.get("id"), "title": row.get("title") or row.get("name") or text[:80],
                             "excerpt": text[:320], "score": score})
    return sorted(hits, key=lambda hit: (-hit["score"], hit["kind"]))[:30]


def read_selected_document(path: str, allowed_roots: list[str], max_bytes: int = 2_000_000) -> dict[str, Any]:
    """Extract text from a user-selected, allow-listed document; read-only."""
    target = Path(path).expanduser().resolve(strict=True)
    roots = [Path(root).expanduser().resolve(strict=True) for root in allowed_roots]
    if not any(target == root or root in target.parents for root in roots):
        raise PermissionError("Select a document inside one of the approved folders.")
    if not target.is_file() or target.stat().st_size > max_bytes:
        raise ValueError("Document must be a file smaller than 2 MB.")
    suffix = target.suffix.lower()
    if suffix in {".txt", ".md", ".csv", ".json", ".py", ".html", ".rtf"}:
        text = target.read_text(encoding="utf-8", errors="replace")
    elif suffix == ".docx":
        with zipfile.ZipFile(target) as archive:
            xml = ET.fromstring(archive.read("word/document.xml"))
        text = " ".join(node.text or "" for node in xml.iter() if node.tag.endswith("}t"))
    elif suffix == ".pdf":
        try:
            from pypdf import PdfReader  # optional dependency
        except ImportError as exc:
            raise RuntimeError("PDF text extraction needs the optional pypdf package. Install it with: pip install pypdf") from exc
        text = "\n".join(page.extract_text() or "" for page in PdfReader(str(target)).pages)
    else:
        raise ValueError("Supported files: TXT, Markdown, CSV, JSON, Python, HTML, RTF, DOCX and PDF.")
    return {"path": str(target), "name": target.name, "text": text[:50000], "truncated": len(text) > 50000}


class PluginRegistry:
    """Small explicit registry; plugins are registered in code, never auto-imported."""
    def __init__(self) -> None:
        self._plugins: dict[str, Callable[..., Any]] = {}

    def register(self, name: str, handler: Callable[..., Any]) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", name):
            raise ValueError("Invalid plugin name.")
        self._plugins[name] = handler

    def names(self) -> list[str]:
        return sorted(self._plugins)

    def run(self, name: str, **kwargs: Any) -> Any:
        if name not in self._plugins:
            raise KeyError(f"Plugin not registered: {name}")
        return self._plugins[name](**kwargs)


class PlanningAgent:
    def propose(self, tasks: list[dict[str, Any]], daily_minutes: int) -> dict[str, Any]:
        queue = sorted([t for t in tasks if t.get("status") != "completed"],
                       key=lambda t: (t.get("due") or "9999-12-31", t.get("priority", "medium")))
        chosen, used = [], 0
        for task in queue:
            minutes = max(int(task.get("estimated_minutes", 30)), 1)
            if used + minutes <= daily_minutes or not chosen:
                chosen.append(task)
                used += minutes
        return {"agent": "planning", "task_ids": [t.get("id") for t in chosen], "minutes": used,
                "opinion": f"Schedule {len(chosen)} ranked tasks in {used} focus minutes."}


class RiskAgent:
    def review(self, tasks: list[dict[str, Any]], daily_minutes: int) -> dict[str, Any]:
        risks = predict_deadline_risk(tasks, daily_minutes)
        return {"agent": "risk", "high_risk_task_ids": [r["task_id"] for r in risks if r["risk"] == "high"],
                "risks": risks, "opinion": f"{sum(r['risk'] == 'high' for r in risks)} deadlines are high risk by the saved workload estimate."}


class ReviewAgent:
    def summarize(self, tasks: list[dict[str, Any]]) -> dict[str, Any]:
        pending = [t for t in tasks if t.get("status") != "completed"]
        completed = [t for t in tasks if t.get("status") == "completed"]
        return {"agent": "review", "pending": len(pending), "completed": len(completed),
                "opinion": f"{len(pending)} tasks remain; {len(completed)} are complete."}


class AgentCoordinator:
    """Run focused deterministic agents and preserve each opinion for display."""
    def __init__(self) -> None:
        self.agents = [PlanningAgent(), RiskAgent(), ReviewAgent()]

    def review(self, tasks: list[dict[str, Any]], daily_minutes: int) -> dict[str, Any]:
        results = [self.agents[0].propose(tasks, daily_minutes),
                   self.agents[1].review(tasks, daily_minutes),
                   self.agents[2].summarize(tasks)]
        return {"coordinator": "ADSPA", "agents": results,
                "summary": " ".join(result["opinion"] for result in results),
                "confidence": "medium; deterministic estimates from saved tasks"}

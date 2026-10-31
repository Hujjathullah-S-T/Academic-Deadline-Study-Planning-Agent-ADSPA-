"""Exam countdown, syllabus coverage, topic mastery, and spaced repetition."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

TOPIC_STATES = {"not_started", "learning", "revised", "mastered", "weak"}
DEFAULT_PHASES = {"14": "Complete remaining syllabus", "7": "Revise key concepts and solve practice questions",
                  "3": "Focus on weak topics and take a mock test", "1": "Light revision and review key notes"}


def exam_phase(exam: dict[str, Any], today: date | None = None,
               phases: dict[str, str] | None = None) -> dict[str, Any]:
    today = today or date.today()
    remaining = (date.fromisoformat(exam["date"]) - today).days
    rules = {**DEFAULT_PHASES, **(phases or {})}
    if remaining < 0:
        return {"days_remaining": remaining, "phase": "past", "action": "Record the result and review what to improve."}
    threshold = next((int(day) for day in sorted(rules, key=int)
                      if remaining <= int(day)), None)
    if threshold is None:
        return {"days_remaining": remaining, "phase": "coverage", "action": "Build syllabus coverage steadily."}
    labels = {"14": "coverage", "7": "practice", "3": "weak_topics", "1": "light_review"}
    return {"days_remaining": remaining, "phase": labels.get(str(threshold), "configured"),
            "action": rules[str(threshold)]}


def syllabus_coverage(topics: list[dict[str, Any]], exam_id: int | str) -> dict[str, Any]:
    selected = [topic for topic in topics if str(topic.get("exam_id")) == str(exam_id)]
    weights = {"not_started": 0, "learning": 0.25, "weak": 0.1, "revised": 0.75, "mastered": 1}
    covered = sum(weights.get(topic.get("status", "not_started"), 0) for topic in selected)
    return {"total": len(selected), "covered_percent": round(covered * 100 / len(selected)) if selected else 0,
            "mastered": sum(topic.get("status") == "mastered" for topic in selected),
            "weak": sum(topic.get("status") == "weak" for topic in selected),
            "not_started": sum(topic.get("status", "not_started") == "not_started" for topic in selected)}


def update_topic_quiz(topic: dict[str, Any], score_percent: float,
                      now: date | None = None) -> dict[str, Any]:
    if not 0 <= score_percent <= 100:
        raise ValueError("Quiz score must be between 0 and 100.")
    today = now or date.today()
    results = list(topic.get("quiz_results", []))
    results.append({"date": today.isoformat(), "score_percent": round(score_percent, 1)})
    previous_interval = int(topic.get("review_interval_days", 1))
    if score_percent < 60:
        status, interval = "weak", 1
    elif score_percent < 80:
        status, interval = "learning", max(2, previous_interval)
    elif score_percent < 95:
        status, interval = "revised", min(30, max(3, previous_interval * 2))
    else:
        status, interval = "mastered", min(60, max(7, previous_interval * 2))
    return {**topic, "quiz_results": results, "last_quiz_score": round(score_percent, 1),
            "status": status, "review_interval_days": interval,
            "next_review": (today + timedelta(days=interval)).isoformat()}


def exam_revision_plan(exam: dict[str, Any], topics: list[dict[str, Any]],
                       daily_minutes: int, today: date | None = None,
                       phases: dict[str, str] | None = None) -> dict[str, Any]:
    phase = exam_phase(exam, today, phases or exam.get("phase_rules"))
    coverage = syllabus_coverage(topics, exam.get("id"))
    selected = [topic for topic in topics if str(topic.get("exam_id")) == str(exam.get("id"))]
    rank = {"weak": 0, "not_started": 1, "learning": 2, "revised": 3, "mastered": 4}
    priority_topics = sorted(selected, key=lambda topic: (
        rank.get(topic.get("status", "not_started"), 1),
        date.fromisoformat(topic["next_review"]) if topic.get("next_review") else date.min,
        -int(topic.get("difficulty", 3))))
    minutes_each = max(15, min(60, daily_minutes // max(1, min(3, len(priority_topics)))))
    return {"exam": exam.get("title"), "phase": phase, "coverage": coverage,
            "next_topics": [{"id": topic.get("id"), "unit": topic.get("unit", ""),
                "title": topic.get("title"), "status": topic.get("status", "not_started"),
                "minutes": minutes_each} for topic in priority_topics[:3]],
            "practice_action": "Schedule a practice test" if exam.get("format") in {"written", "practical", "mixed"} else "Use active recall and oral rehearsal"}

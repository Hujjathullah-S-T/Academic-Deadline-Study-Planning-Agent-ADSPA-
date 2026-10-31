"""Deterministic academic command parsing with explicit clarifications."""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
                "eleven": 11, "twelve": 12, "fourteen": 14, "fifteen": 15,
                "twenty": 20, "thirty": 30}
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def parse_due_date(text: str, today: date | None = None) -> date | None:
    today = today or date.today()
    iso = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
    if iso:
        try: return date.fromisoformat(iso.group(1))
        except ValueError: return None
    if re.search(r"\btoday\b", text, re.I): return today
    if re.search(r"\bday after tomorrow\b", text, re.I): return today + timedelta(days=2)
    if re.search(r"\btomorrow\b", text, re.I): return today + timedelta(days=1)
    relative = re.search(r"\b(?:in|within)\s+(\d+|[a-z]+)\s+days?\b", text, re.I)
    if relative:
        value = relative.group(1).lower()
        days = int(value) if value.isdigit() else NUMBER_WORDS.get(value)
        if days is not None: return today + timedelta(days=days)
    weekday = re.search(r"\b(?:next\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", text, re.I)
    if weekday:
        target = WEEKDAYS.index(weekday.group(1).lower())
        return today + timedelta(days=(target - today.weekday()) % 7 or 7)
    if re.search(r"\bnext week\b", text, re.I): return today + timedelta(days=7)
    return None


def detect_deadline_capture(text: str) -> dict[str, Any] | None:
    lower = text.casefold()
    if not any(word in lower for word in ("assignment", "quiz", "exam", "test", "lab", "laboratory", "project", "submission")):
        return None
    due = parse_due_date(text)
    if due is None:
        return None
    kind = "examination" if re.search(r"\b(exam|examination|test|ct\s*\d|midterm|end[- ]semester)\b", lower) else (
        "quiz" if "quiz" in lower else "laboratory" if re.search(r"\b(lab|laboratory)\b", lower) else
        "project" if "project" in lower else "assignment")
    title = text
    title = re.sub(r"\b(?:i have|i've got|there is|there's|add|create|schedule)\b", "", title, flags=re.I)
    title = re.sub(r"\b(?:due|by)\s+(?:today|tomorrow|day after tomorrow|next\s+week|in\s+(?:\d+|[a-z]+)\s+days?|within\s+(?:\d+|[a-z]+)\s+days?|next\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)?\b", "", title, flags=re.I)
    title = re.sub(r"\b(?:today|tomorrow|day after tomorrow|next week|in\s+(?:\d+|[a-z]+)\s+days?|within\s+(?:\d+|[a-z]+)\s+days?|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", "", title, flags=re.I)
    title = re.sub(r"\s+", " ", title).strip(" ,.!?-")
    generic = {"assignment", "quiz", "exam", "test", "lab", "laboratory", "project", "submission",
               "an assignment", "a quiz", "an exam", "a test", "a lab", "a project"}
    if title.casefold() in generic:
        title = ""
    return {"kind": kind, "due": due.isoformat(), "title": title}


def continue_deadline_capture(agent, pending: dict[str, Any], reply: str) -> dict[str, Any]:
    data = agent.load_data()
    text = reply.strip()
    if not text:
        return {"reply": "Please tell me the course or subject and assignment title.", "pending_capture": pending}
    minutes_match = re.search(r"(\d+(?:\.\d+)?)\s*(hours?|hrs?|minutes?|mins?)", text, re.I)
    minutes = int(float(minutes_match.group(1)) * (60 if minutes_match.group(2).lower().startswith(("h", "hr")) else 1)) if minutes_match else 60
    marks_match = re.search(r"(\d+(?:\.\d+)?)\s*marks?", text, re.I)
    course = next((row for row in data["courses"]
                   if row["title"].casefold() in text.casefold()
                   or (row.get("course_code") and row["course_code"].casefold() in text.casefold())), None)
    if course:
        subject = course["title"]
        title = re.sub(re.escape(subject), "", text, flags=re.I).strip(" ,:-")
    elif ":" in text:
        subject, title = [part.strip() for part in text.split(":", 1)]
        if subject and title:
            course = agent.add_course(subject, subject=subject)
    elif "," in text:
        subject, title = [part.strip() for part in text.split(",", 1)]
        if subject and title:
            course = next((row for row in data["courses"] if row["title"].casefold() == subject.casefold()), None)
            if not course:
                course = agent.add_course(subject, subject=subject)
    else:
        return {"reply": "Tell me both the course/subject and a specific assignment title, for example: `Computer Vision, Assignment 2, 3 hours`.", "pending_capture": pending}
    title = re.sub(r"\b\d+(?:\.\d+)?\s*(?:hours?|hrs?|minutes?|mins?|marks?)\b", "", title, flags=re.I)
    title = re.sub(r"\s+", " ", title).strip(" ,:-")
    if not title:
        return {"reply": f"What is the assignment or exam title for {subject}?", "pending_capture": pending}
    kind = pending.get("kind", "assignment")
    if kind == "examination":
        from academic.records import add_exam
        add_exam(data, title, pending["due"], course.get("id") if course else None,
                 study_minutes=minutes)
        return {"reply": f"Added {title} for {subject} on {pending['due']} and created an exam countdown."}
    if course:
        task = agent.add_course_task(course["id"], title, pending["due"], "high", minutes, kind)
    else:
        task = agent.add_task(title, pending["due"], "high", minutes, subject, task_type=kind)
    if marks_match:
        agent.update_task_metadata(task["id"], marks_possible=float(marks_match.group(1)))
    return {"reply": f"Added {kind} **{title}** for {subject}, due {pending['due']}, estimated {minutes} minutes. Add a materials brief in Courses to build its workflow checklist.", "task": task}


def handle_academic_command(agent, text: str, pending_capture: dict[str, Any] | None = None) -> dict[str, Any] | None:
    lower = text.casefold().strip()
    if pending_capture:
        if lower in {"cancel", "never mind", "nevermind", "stop"}:
            return {"reply": "Cancelled adding that academic deadline.", "pending_capture": None}
        return continue_deadline_capture(agent, pending_capture, text)
    capture = detect_deadline_capture(text)
    if capture:
        if not capture["title"]:
            return {"reply": f"I heard a {capture['kind']} due {capture['due']}. What course/subject and title should I save?", "pending_capture": capture}
        data = agent.load_data()
        course = next((row for row in data["courses"] if row["title"].casefold() in capture["title"].casefold()), None)
        if not course:
            return {"reply": f"I heard **{capture['title']}**, due {capture['due']}. Which course/subject is this for, and about how long will it take? Reply like `Computer Vision, Assignment 2, 3 hours`.", "pending_capture": capture}
        task = agent.add_course_task(course["id"], capture["title"], capture["due"], "high", 60, capture["kind"])
        return {"reply": f"Added {capture['kind']} **{capture['title']}** to {course['title']}, due {capture['due']}.", "task": task}

    if "completed unit" in lower or "finished unit" in lower or "revised unit" in lower:
        match = re.search(r"(?:completed|finished|revised)\s+(unit\s*\w+|chapter\s*\w+)", lower)
        if match:
            data = agent.load_data()
            matches = [topic for topic in data["topics"] if match.group(1).replace(" ", "") in
                       (topic.get("unit", "") + topic.get("title", "")).casefold().replace(" ", "")]
            if len(matches) == 1:
                from academic.records import update_topic
                update_topic(data, matches[0]["id"], "revised")
                agent.save_data(data)
                return {"reply": f"Marked {matches[0].get('unit')} · {matches[0]['title']} as revised. Its next review is {matches[0].get('next_review', 'not scheduled')}."}
            if len(matches) > 1:
                return {"reply": "I found several matching units. Please include the exam or course name so I update the right topic."}
            return {"reply": "I couldn't find that unit in your saved exam syllabus. Add it in Exam prep, then I can track its revision."}

    if "couldn't study" in lower or "could not study" in lower or "missed my study" in lower:
        from planning.study_planner import reschedule_missed_sessions
        data = agent.load_data()
        for session in data["study_sessions"]:
            if session.get("date") == date.today().isoformat() and session.get("status") in {"planned", "rescheduled"}:
                session["status"] = "missed"
        sessions, moved = reschedule_missed_sessions(data["study_sessions"], data["tasks"], data["events"], data["settings"])
        data["study_sessions"] = sessions
        agent.save_data(data)
        return {"reply": f"I marked today's unfinished sessions as missed and moved {len(moved)} to open study slots where deadlines allow. Review them in Study planner."}

    if "pending assignment" in lower or "show my assignments" in lower:
        data = agent.load_data()
        rows = [task for task in data["tasks"] if task.get("status") not in {"completed", "submitted"}
                and task.get("task_type", task.get("academic_type")) in {"assignment", "laboratory", "quiz", "project"}]
        rows.sort(key=agent.task_rank)
        if not rows:
            return {"reply": "You have no pending assignments."}
        return {"reply": "Pending assignments: " + "; ".join(f"{row['title']} · {row.get('category', 'General')} · {row.get('due') or 'no deadline'} · {row.get('work_status', 'not_started')}" for row in rows[:12])}

    if re.search(r"\bplan\b.*\b(today|tomorrow|week|month)\b", lower):
        from planning.study_planner import build_study_plan
        data = agent.load_data()
        horizon = 30 if "month" in lower else 7 if "week" in lower else 1
        start = date.today() + timedelta(days=1) if "tomorrow" in lower else date.today()
        plan = build_study_plan(data["tasks"], data["events"], data["settings"],
            data["study_sessions"], data["topics"], data["exams"], start, horizon)
        old = [row for row in data["study_sessions"] if not
            (row.get("source") == "generated_plan" and row.get("status") in {"planned", "rescheduled"}
             and row.get("date", "") >= start.isoformat())]
        data["study_sessions"] = old + plan["sessions"]
        agent.save_data(data)
        return {"reply": f"I planned {sum(day['planned_minutes'] for day in plan['days'])} study minutes over {horizon} day(s). {len(plan['unscheduled'])} item(s) still need a slot. See Study planner for the schedule.", "plan": plan}

    if "prepare me" in lower and ("quiz" in lower or "exam" in lower or "test" in lower):
        data = agent.load_data()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        exams = [exam for exam in data["exams"] if exam.get("date") in {date.today().isoformat(), tomorrow}]
        if not exams:
            return {"reply": "I couldn't find an exam or quiz scheduled for tomorrow. Add it in Exam prep so I can target the right syllabus."}
        exam = exams[0]
        topics = [topic for topic in data["topics"] if str(topic.get("exam_id")) == str(exam["id"])]
        prompts = [f"Explain and apply {topic.get('unit', '')} {topic['title']} (5 marks)." for topic in topics[:10]]
        from learning.exams import exam_revision_plan
        plan = exam_revision_plan(exam, data["topics"], data["settings"]["daily_focus_minutes"], phases=data["settings"].get("exam_phase_rules", {}))
        return {"reply": f"For {exam['title']}: {plan['phase']['action']}\n\nPractice prompts:\n" + ("\n".join(f"{i+1}. {question}" for i, question in enumerate(prompts)) if prompts else "Add syllabus topics in Exam prep first."), "exam_plan": plan}

    if "what did i accomplish this week" in lower or "weekly progress" in lower:
        data = agent.load_data()
        from modules import weekly_productivity_report
        report = weekly_productivity_report(data["tasks"])
        minutes = sum(int(row.get("duration_minutes", 0)) for row in data["study_sessions"]
                      if row.get("status") == "completed" and row.get("date", "") >= report["week_start"])
        return {"reply": f"This week: {report['completed']} coursework items completed, {report['unfinished']} open, {report['overdue_now']} overdue, and {minutes} minutes of study sessions recorded."}

    if "due this week" in lower and ("assignments" in lower or "workload" in lower):
        data = agent.load_data()
        from academic.deadlines import assess_deadline_risk, deadline_collisions
        end = (date.today() + timedelta(days=7)).isoformat()
        due = [task for task in data["tasks"] if task.get("status") not in {"completed", "submitted"}
               and task.get("due") and date.today().isoformat() <= task["due"] <= end]
        collisions = deadline_collisions(due, daily_minutes=data["settings"]["daily_focus_minutes"])
        risks = {row["task_id"]: row for row in assess_deadline_risk(due, data["settings"]["daily_focus_minutes"])}
        summary = "; ".join(f"{task['title']} ({risks.get(task['id'], {}).get('risk', 'unrated')} risk)" for task in due)
        return {"reply": (f"{len(due)} pending item(s) are due this week: {summary}. "
            + (f"I found {len(collisions)} deadline collision(s); prioritize the high-risk items and protect separate work blocks." if collisions else "No close deadline collision was detected."))}
    if any(phrase in lower for phrase in ("what should i do next", "what's next", "whats next", "next task", "what next")):
        from academic.deadlines import optimize_workload
        data = agent.load_data()
        ranked = optimize_workload(data["tasks"], data["settings"]["daily_focus_minutes"], data["settings"])
        if not ranked:
            return {"reply": "You have no open academic tasks. Add an assignment or study item to get a recommendation."}
        task = ranked[0]
        return {"reply": f"Start with **{task['title']}** for {task.get('category', 'General')} — {task.get('priority', 'medium')} priority, {task.get('estimated_minutes', 30)} minutes estimated, {float(task.get('percent_complete', 0)):.0f}% complete, due {task.get('due') or 'no deadline'}. This is based on urgency, workload risk, importance, difficulty, and blocking impact."}
    return None

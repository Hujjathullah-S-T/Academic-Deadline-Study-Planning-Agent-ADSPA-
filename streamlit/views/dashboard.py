"""Personal academic overview and common shortcuts."""
from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from academic.deadlines import assess_deadline_risk, deadline_collisions, optimize_workload
from modules import weekly_productivity_report


def render(agent, navigate) -> None:
    data = agent.load_data()
    today = date.today()
    today_iso = today.isoformat()
    tasks = data.get("tasks", [])
    pending = [task for task in tasks if task.get("status") not in {"completed", "submitted"}]
    overdue = [task for task in pending if task.get("due") and task["due"] < today_iso]
    due_today = [task for task in pending if task.get("due") == today_iso]
    upcoming_exams = [exam for exam in data.get("exams", [])
        if today_iso <= exam.get("date", "") <= (today + timedelta(days=30)).isoformat()]
    weekly = weekly_productivity_report(tasks)
    weekly_progress = f"{weekly['completion_rate_percent']}%" if weekly["created_or_completed"] else "—"
    monday = today - timedelta(days=today.weekday())
    study_minutes = sum(
        int(session.get("duration_minutes", 0)) for session in data.get("study_sessions", [])
        if monday.isoformat() <= session.get("date", "") <= today_iso
        and session.get("kind") != "break" and session.get("status") == "completed"
    )
    planned_today = sum(
        int(session.get("duration_minutes", 0)) for session in data.get("study_sessions", [])
        if session.get("date") == today_iso and session.get("kind") != "break"
        and session.get("status") in {"planned", "rescheduled", "in_progress"}
    )
    study_left = max(0, int(data["settings"].get("daily_focus_minutes", 120)) - planned_today)

    st.subheader("Your academic overview")
    st.caption("Here’s what needs your attention today.")

    metrics = st.columns(4)
    metrics[0].metric("Pending tasks", len(pending))
    metrics[1].metric("Upcoming exams", len(upcoming_exams), help="Exams scheduled in the next 30 days")
    metrics[2].metric("Study time this week", f"{study_minutes / 60:.1f}h")
    metrics[3].metric("Weekly progress", weekly_progress,
                      help="Completion rate for tasks created or completed this week")

    st.markdown("#### Quick actions")
    actions = st.columns(4)
    actions[0].button("＋ Add task", use_container_width=True,
                      on_click=navigate, args=("My Learning", "Assignments and coursework"))
    actions[1].button("▦ Plan study", use_container_width=True,
                      on_click=navigate, args=("Study Planner", "Daily and weekly plans"))
    actions[2].button("✎ Add notes", use_container_width=True,
                      on_click=navigate, args=("My Learning", "Notes and resources"))
    actions[3].button("✦ Ask AI", use_container_width=True,
                      on_click=navigate, args=("AI Study Assistant", None), type="primary")

    if overdue:
        st.error("Overdue · " + " · ".join(task["title"] for task in overdue[:5]))
    if due_today:
        st.warning("Due today · " + " · ".join(task["title"] for task in due_today[:5]))

    left, right = st.columns([3, 2])
    with left:
        st.markdown("#### Today's priorities")
        ranked = optimize_workload(pending, int(data["settings"].get("daily_focus_minutes", 120)), data["settings"])
        if ranked:
            for task in ranked[:5]:
                due = task.get("due") or "No deadline"
                task_col, action_col = st.columns([5, 1])
                task_col.write(f"**{task['title']}** · {task.get('priority', 'normal').title()} · due {due}")
                action_col.button("Open", key=f"dashboard-open-task-{task['id']}",
                                  on_click=navigate,
                                  args=("My Learning", "Assignments and coursework", task["id"]))
        else:
            st.success("You’re all caught up. Add a task when something new comes up.")

        st.markdown("#### Upcoming deadlines")
        upcoming_tasks = sorted(
            (task for task in pending if task.get("due") and task["due"] >= today_iso),
            key=lambda task: task["due"],
        )[:6]
        if upcoming_tasks:
            for task in upcoming_tasks:
                st.write(f"**{task['due']}** · {task['title']} · {task.get('category', 'General')}")
        else:
            st.caption("No upcoming deadlines.")

    with right:
        st.markdown("#### Study sessions today")
        sessions = sorted(
            (session for session in data.get("study_sessions", [])
             if session.get("date") == today_iso and session.get("kind") != "break"
             and session.get("status") in {"planned", "rescheduled", "in_progress"}),
            key=lambda session: session.get("start", ""),
        )
        if sessions:
            for session in sessions:
                st.write(f"{session.get('start', '')}–{session.get('end', '')} · **{session['title']}** · {session.get('duration_minutes', 0)} min")
        else:
            st.caption("No sessions planned for today. Choose **Plan study** to create one.")
        st.metric("Available study time", f"{study_left} min")

        if upcoming_exams:
            st.markdown("#### Exam preparation")
            from learning.exams import exam_phase, syllabus_coverage
            topics = data.get("topics", [])
            for exam in sorted(upcoming_exams, key=lambda row: row["date"])[:4]:
                phase = exam_phase(exam, phases=data["settings"].get("exam_phase_rules", {}))
                coverage = syllabus_coverage(topics, exam["id"])
                st.write(f"**{exam['title']}** · {phase['days_remaining']} days · {coverage['covered_percent']}% covered")
        else:
            st.markdown("#### Exams")
            st.caption("No exams in the next 30 days.")

    risks = assess_deadline_risk(tasks, int(data["settings"].get("daily_focus_minutes", 120)), settings=data["settings"])
    high_risk = [risk for risk in risks if risk["risk"] == "high"]
    collisions = deadline_collisions(tasks, daily_minutes=int(data["settings"].get("daily_focus_minutes", 120)), settings=data["settings"])
    if high_risk or collisions:
        st.markdown("#### Needs attention")
        for risk in high_risk[:3]:
            st.warning(f"**{risk['title']}** · {risk['explanation']} Suggested next step: " + " → ".join(risk["recovery_plan"]))
        for collision in collisions[:3]:
            st.warning(f"{collision['start'][:10]}–{collision['end'][:10]} · {', '.join(collision['task_titles'])} · {collision['recommendation']}")

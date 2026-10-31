"""Daily, weekly, monthly study scheduling and session execution UI."""
from __future__ import annotations

from datetime import date

import streamlit as st

from planning.study_planner import build_study_plan, reschedule_missed_sessions

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def render(agent) -> None:
    data = agent.load_data()
    settings = data["settings"]
    st.subheader("Study planner")
    st.caption("Plans use your actual availability, class commitments, task progress, deadlines, exam topics, and focus budget.")
    with st.expander("Set weekly availability", expanded=not bool(settings.get("available_weekdays"))):
        with st.form("weekly-availability"):
            selected_days = st.multiselect("Days available for study", WEEKDAYS,
                default=[WEEKDAYS[int(day)] for day in settings.get("available_weekdays", [0, 1, 2, 3, 4])])
            c1, c2 = st.columns(2)
            start_at = c1.time_input("Study availability starts", value=agent.datetime.strptime(settings.get("availability_start", "09:00"), "%H:%M").time())
            end_at = c2.time_input("Study availability ends", value=agent.datetime.strptime(settings.get("availability_end", "18:00"), "%H:%M").time())
            c1, c2 = st.columns(2)
            session_length = c1.number_input("Study block length (minutes)", 15, 180, int(settings.get("study_session_minutes", 60)), step=15)
            break_length = c2.number_input("Break between blocks (minutes)", 0, 60, int(settings.get("break_minutes", 10)), step=5)
            if st.form_submit_button("Save availability"):
                settings["available_weekdays"] = [WEEKDAYS.index(day) for day in selected_days]
                settings["availability_start"] = start_at.strftime("%H:%M")
                settings["availability_end"] = end_at.strftime("%H:%M")
                settings["study_session_minutes"] = int(session_length)
                settings["break_minutes"] = int(break_length)
                agent.save_data(data)
                st.success("Weekly study availability saved.")
                st.rerun()

    with st.form("generate-study-plan"):
        c1, c2 = st.columns(2)
        start_day = c1.date_input("Plan starting date", value=date.today())
        period = c2.selectbox("Plan length", ["Today", "Next 7 days", "Next 30 days"])
        generate = st.form_submit_button("Generate study plan", type="primary")
    if generate:
        days = {"Today": 1, "Next 7 days": 7, "Next 30 days": 30}[period]
        try:
            plan = build_study_plan(data["tasks"], data["events"], settings,
                data.get("study_sessions", []), data.get("topics", []),
                data.get("exams", []), start_day, days)
            old_sessions = [session for session in data.get("study_sessions", [])
                if not (session.get("source") == "generated_plan"
                    and session.get("status") in {"planned", "rescheduled"}
                    and session.get("date", "") >= start_day.isoformat())]
            data["study_sessions"] = old_sessions + plan["sessions"]
            data["last_study_plan"] = {"start_date": plan["start_date"],
                "horizon_days": days, "basis": plan["basis"]}
            agent.save_data(data)
            st.session_state["generated_study_plan"] = plan
        except ValueError as exc:
            st.error(str(exc))

    if st.button("Reschedule missed study sessions"):
        sessions, moved = reschedule_missed_sessions(data.get("study_sessions", []),
            data["tasks"], data["events"], settings)
        data["study_sessions"] = sessions
        agent.save_data(data)
        st.success(f"Rescheduled {len(moved)} missed session(s)." if moved else "No missed sessions could be moved into available time before their deadlines.")
        st.rerun()

    plan = st.session_state.get("generated_study_plan")
    if plan:
        st.markdown(f"### Plan · {plan['start_date']} · {plan['horizon_days']} day(s)")
        for day in plan["days"]:
            with st.expander(f"{day['date']} · {day['planned_minutes']} study minutes", expanded=plan["horizon_days"] == 1):
                for session in day["sessions"]:
                    st.write(f"{session['start']}–{session['end']} · **{session['title']}** · {session['duration_minutes']} min · {session['kind']}")
                if day["unavailable_message"]:
                    st.caption(day["unavailable_message"])
        if plan["unscheduled"]:
            st.warning("Some work did not fit the available study time:")
            for item in plan["unscheduled"]:
                st.write(f"• {item['title']} · {item['remaining_minutes']} minutes remaining · due {item.get('due') or 'no deadline'}")
        st.caption(plan["basis"])

    st.divider()
    st.markdown("### Scheduled sessions")
    upcoming = [session for session in data.get("study_sessions", [])
                if session.get("kind") != "break" and session.get("status") in {"planned", "rescheduled", "in_progress"}]
    upcoming.sort(key=lambda session: (session.get("date", ""), session.get("start", "")))
    if not upcoming:
        st.caption("Generate a plan to create study sessions.")
    for session in upcoming[:30]:
        label = f"{session['date']} · {session.get('start', '')}–{session.get('end', '')} · {session['title']} · {session.get('duration_minutes', 0)} min"
        c1, c2, c3 = st.columns([6, 1, 1])
        c1.write(label)
        if c2.button("Done", key=f"session-done-{session['id']}"):
            current = next(row for row in data["study_sessions"] if row.get("id") == session.get("id"))
            current["status"] = "completed"
            task = next((row for row in data["tasks"] if str(row.get("id")) == str(session.get("task_id"))), None)
            if task:
                estimate = max(1, int(task.get("estimated_minutes", 30)))
                task["percent_complete"] = min(99, float(task.get("percent_complete", 0)) + 100 * int(session.get("duration_minutes", 0)) / estimate)
                task["work_status"] = "in_progress"
            data["notifications"].append({"id": max([int(item.get("id", 0)) for item in data.get("notifications", [])] + [0]) + 1,
                "title": "Study session complete", "message": f"You completed {session['title']}. Progress was saved.",
                "created_at": agent.now_iso(), "read": False, "in_app": True})
            agent.save_data(data)
            agent.log_event(f"Completed study session: {session['title']}")
            st.rerun()
        if c3.button("Missed", key=f"session-missed-{session['id']}"):
            current = next(row for row in data["study_sessions"] if row.get("id") == session.get("id"))
            current["status"] = "missed"
            sessions, moved = reschedule_missed_sessions(data["study_sessions"], data["tasks"], data["events"], settings)
            data["study_sessions"] = sessions
            agent.save_data(data)
            st.info("Session moved to the next available slot." if int(session["id"]) in moved else "No available slot found before the deadline; adjust your availability or plan.")
            st.rerun()

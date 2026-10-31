"""Exam schedule and syllabus revision UI."""
from __future__ import annotations

import streamlit as st
from datetime import time

from learning.exams import exam_phase, exam_revision_plan, syllabus_coverage
from academic.deadlines import countdown
from academic.records import add_exam, add_topic, update_topic


def render(agent) -> None:
    data = agent.load_data()
    st.subheader("Examination schedule")
    with st.form("add-exam", clear_on_submit=True):
        title = st.text_input("Examination", placeholder="CT1 · Computer Vision")
        courses = data.get("courses", [])
        course_names = {"General / not linked": None}
        course_names.update({f"{course['title']} · {course.get('course_code', '')}": course["id"] for course in courses})
        c1, c2, c3, c4 = st.columns(4)
        exam_date = c1.date_input("Exam date")
        exam_time = c2.time_input("Start time", value=time(9, 0))
        exam_format = c3.selectbox("Format", ["written", "practical", "oral", "online", "mixed"])
        study_minutes = c4.number_input("Prep minutes", 15, 1440, 180, step=15)
        course_label = st.selectbox("Course", list(course_names))
        if st.form_submit_button("Add examination", type="primary"):
            try:
                add_exam(data, title, exam_date.isoformat(), course_names[course_label],
                    exam_format, int(study_minutes), exam_time.isoformat(timespec="minutes"))
                st.success("Exam and deadline added.")
                st.rerun()
            except (ValueError, TypeError) as exc:
                st.error(str(exc))

    if not data.get("exams"):
        st.info("Add an examination to build a countdown and topic revision plan.")
    for exam in sorted(data.get("exams", []), key=lambda row: row.get("date", "9999-12-31")):
        phase = exam_phase(exam, phases=data["settings"].get("exam_phase_rules", {}))
        coverage = syllabus_coverage(data.get("topics", []), exam["id"])
        with st.expander(f"{exam['title']} · {phase['days_remaining']} day(s) · {coverage['covered_percent']}% covered", expanded=phase["days_remaining"] <= 14):
            exam_task = next((row for row in data["tasks"] if row.get("exam_id") == exam["id"]), None)
            timing = countdown(exam_task) if exam_task else None
            if timing:
                st.info(f"Exam countdown: {timing['label']}")
            st.write(f"**Countdown mode:** {phase['action']}")
            st.caption(f"{exam['date']} at {exam.get('time', '09:00')} · {exam.get('format', 'written')} · syllabus: {coverage['mastered']} mastered, {coverage['weak']} weak, {coverage['not_started']} not started")
            revision = exam_revision_plan(exam, data.get("topics", []), int(data["settings"].get("daily_focus_minutes", 120)), phases=data["settings"].get("exam_phase_rules", {}))
            st.write("**Next revision topics:** " + (", ".join(topic["title"] for topic in revision["next_topics"]) or "Add syllabus units below."))
            if revision["next_topics"]:
                st.caption(revision["practice_action"])
            with st.form(f"add-topic-{exam['id']}", clear_on_submit=True):
                c1, c2, c3 = st.columns(3)
                unit = c1.text_input("Unit / chapter", key=f"unit-{exam['id']}")
                topic_title = c2.text_input("Topic", key=f"topic-{exam['id']}")
                difficulty = c3.selectbox("Difficulty", [1, 2, 3, 4, 5], index=2, key=f"topic-difficulty-{exam['id']}")
                study_minutes = st.number_input("Study minutes", 15, 180, 30, key=f"topic-minutes-{exam['id']}")
                if st.form_submit_button("Add syllabus topic"):
                    try:
                        add_topic(data, exam["id"], unit, topic_title, difficulty, int(study_minutes))
                        agent.save_data(data)
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
            topic_rows = [topic for topic in data.get("topics", []) if int(topic.get("exam_id", -1)) == int(exam["id"])]
            for topic in topic_rows:
                st.markdown(f"**{topic.get('unit') or 'Topic'} · {topic['title']}** — {topic.get('status', 'not_started').replace('_', ' ')} · next review {topic.get('next_review', 'not scheduled')}")
                with st.form(f"topic-update-{topic['id']}"):
                    c1, c2, c3 = st.columns([2, 1, 1])
                    state = c1.selectbox("Preparation", ["not_started", "learning", "revised", "mastered", "weak"], index=["not_started", "learning", "revised", "mastered", "weak"].index(topic.get("status", "not_started")), key=f"state-{topic['id']}")
                    score = c2.number_input("Latest quiz score %", min_value=0.0, max_value=100.0, value=float(topic.get("last_quiz_score", 0)), key=f"score-{topic['id']}")
                    scored = c3.checkbox("Record quiz", key=f"record-score-{topic['id']}")
                    if st.form_submit_button("Update topic"):
                        try:
                            update_topic(data, topic["id"], None if scored else state,
                                         score if scored else None)
                            agent.save_data(data)
                            st.rerun()
                        except ValueError as exc:
                            st.error(str(exc))
            if topic_rows:
                if st.button("Generate mock test prompts", key=f"mock-{exam['id']}"):
                    prompts = [f"Explain and apply {topic.get('unit') or ''} {topic['title']} (5 marks)." for topic in topic_rows[:10]]
                    st.session_state[f"mock-{exam['id']}-questions"] = prompts
                for number, prompt in enumerate(st.session_state.get(f"mock-{exam['id']}-questions", []), 1):
                    st.write(f"{number}. {prompt}")
                st.caption("These are practice prompts generated from your entered syllabus topics, not official exam questions.")

"""Streamlit interface for academic deadline and study planning."""
from __future__ import annotations

import json
import importlib
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import agent
importlib.reload(agent)
from views import assignments as assignment_workflow_view
from views import dashboard as dashboard_view
from views import exams as exam_view
from views import materials as material_view
from views import planner as planner_view
from views import research as research_view
from views import notifications as notification_view
from google_workspace import (CREDENTIALS_FILE, TOKEN_FILE, connect_google,
                              google_dependencies, load_credentials,
                              services, sync_deadlines)
from modules import weekly_productivity_report
from academic.deadlines import (assess_deadline_risk, deadline_collisions,
                                countdown, optimize_workload, priority_score)

voice_input = components.declare_component(
    "academic_planner_voice", path=str(ROOT / "streamlit" / "voice_component"))
notification_component = components.declare_component(
    "academic_planner_notifications", path=str(ROOT / "streamlit" / "notification_component"))

st.set_page_config(page_title="Academic Study Planner", page_icon="📚", layout="wide")
st.markdown("""
<style>
    .block-container {max-width: 1320px; padding-top: 2rem; padding-bottom: 3rem;}
    [data-testid="stSidebar"] {border-right: 1px solid rgba(120, 130, 145, .18);}
    [data-testid="stSidebar"] div[data-testid="stRadio"] label:has(input:checked) {
        background: rgba(49, 51, 63, .09); border-radius: .55rem; font-weight: 650;
    }
    [data-testid="stSidebar"] div[data-testid="stRadio"] label {padding: .35rem .5rem;}
    [data-testid="stMetric"] {background: rgba(120, 130, 145, .07); padding: 1rem; border-radius: .75rem;}
    div[data-testid="stExpander"] {border-radius: .65rem;}
    h1, h2, h3 {letter-spacing: -.02em;}
</style>
""", unsafe_allow_html=True)
st.title("Study Planner")
st.caption("A clear view of your coursework, deadlines, and study time")

@st.cache_resource
def persistent_reminder_scheduler():
    from notifications.scheduler import check_deadline_reminders, create_daily_briefing, start_scheduler
    check_deadline_reminders()
    create_daily_briefing()
    return start_scheduler(agent.DATABASE_FILE,
        int(agent.load_data()["settings"].get("daily_briefing_hour", 7)))

try:
    persistent_reminder_scheduler()
except RuntimeError:
    pass

main_sections = ["Dashboard", "My Learning", "Study Planner", "Exams & Assessments", "Research & Projects", "AI Study Assistant"]

def navigate(section: str, subsection: str | None = None, task_id: int | None = None) -> None:
    st.session_state["workspace_section"] = section
    st.session_state.pop("coursework_focus_id", None)
    if task_id is not None:
        st.session_state["coursework_focus_id"] = task_id
        st.session_state["task_status_filter"] = "Open"
        st.session_state["task_course_filter"] = "All courses"
    subsection_key = {
        "My Learning": "learning_subsection",
        "Study Planner": "planner_subsection",
        "Exams & Assessments": "assessment_subsection",
    }.get(section)
    if subsection_key and subsection is not None:
        st.session_state[subsection_key] = subsection

def open_settings() -> None:
    st.session_state["workspace_settings"] = True

def leave_settings() -> None:
    st.session_state.pop("workspace_settings", None)

with st.sidebar:
    st.markdown("### 📚 Study Planner")
    st.caption("YOUR ACADEMIC WORKSPACE")
    selected_section = st.radio("Workspace", main_sections, key="workspace_section",
                                label_visibility="collapsed", on_change=leave_settings)
    section_descriptions = {
        "Dashboard": "Today’s priorities, deadlines, and progress",
        "My Learning": "Courses, coursework, notes, and materials",
        "Study Planner": "Study plans, sessions, and reminders",
        "Exams & Assessments": "Exam dates, revision, quizzes, and progress",
        "Research & Projects": "Projects, milestones, and research notes",
        "AI Study Assistant": "Ask questions and plan your next step",
    }
    st.caption("Preferences, reminders, integrations, and planner data" if st.session_state.get("workspace_settings")
               else section_descriptions[selected_section])
    st.button("⚙ Settings", use_container_width=True, on_click=open_settings)
    if st.session_state.get("workspace_settings"):
        st.button("← Back to workspace", use_container_width=True, on_click=leave_settings)
    st.divider()
    unread_count = sum(not item.get("read") for item in agent.load_data().get("notifications", []))
    reminder_label = f"Reminders · {unread_count}" if unread_count else "Reminders"
    with st.expander(reminder_label, expanded=False):
        notification_view.live_reminder_panel(agent, notification_component)

settings_open = st.session_state.get("workspace_settings", False)
current_page = "settings" if settings_open else {
    "Dashboard": "dashboard", "My Learning": "learning", "Study Planner": "planner",
    "Exams & Assessments": "exams", "Research & Projects": "research",
    "AI Study Assistant": "assistant",
}[selected_section]
if current_page == "learning":
    subsection = st.radio("My Learning", ["Courses and materials", "Assignments and coursework", "Notes and resources"],
                          horizontal=True, key="learning_subsection")
    current_page = {"Courses and materials": "courses", "Assignments and coursework": "coursework",
                    "Notes and resources": "notes"}[subsection]
elif current_page == "planner":
    subsection = st.radio("Study Planner", ["Daily and weekly plans", "Reminders"],
                          horizontal=True, key="planner_subsection")
    current_page = "plan" if subsection == "Daily and weekly plans" else "reminders"
elif current_page == "exams":
    subsection = st.radio("Exams and assessments", ["Exam schedule and preparation", "Progress and grades"],
                          horizontal=True, key="assessment_subsection")
    current_page = "exam_schedule" if subsection == "Exam schedule and preparation" else "progress"

if current_page == "dashboard":
    dashboard_view.render(agent, navigate)

if current_page == "coursework":
    st.subheader("Add coursework")
    with st.form("add_task", clear_on_submit=True):
        title = st.text_input("Coursework / task")
        c1, c2, c3 = st.columns(3)
        due = c1.date_input("Deadline (optional)", value=None)
        priority = c2.selectbox("Priority", ["low", "medium", "high", "urgent"], index=1)
        minutes = c3.number_input("Estimated minutes", min_value=1, max_value=1440, value=30)
        category = st.text_input("Course or subject", value="General")
        item_type = st.selectbox("Type", ["assignment", "quiz", "laboratory", "project", "examination", "study", "other"])
        submitted = st.form_submit_button("Add to planner", type="primary")
    with st.expander("More options"):
        c1, c2 = st.columns(2)
        due_time = c1.time_input("Deadline time", value=datetime.strptime("23:59", "%H:%M").time())
        difficulty = c2.selectbox("Difficulty (1–5)", [1, 2, 3, 4, 5], index=2)
        c1, c2 = st.columns(2)
        importance = c1.selectbox("Academic importance (1–5)", [1, 2, 3, 4, 5], index=2)
        consequence = c2.selectbox("Consequence if late (1–5)", [1, 2, 3, 4, 5], index=2)
        blocks_other_tasks = st.checkbox("Other coursework depends on this")
        reminder_days = st.multiselect("Remind me this many days before", [30, 14, 7, 3, 1, 0], default=[7, 3, 1, 0])
    if submitted:
        try:
            agent.add_task(title, due.isoformat() if due else None, priority, int(minutes), category,
                task_type=item_type, due_time=due_time.isoformat(timespec="minutes"),
                difficulty=int(difficulty), importance=int(importance), reminder_days=reminder_days,
                consequence=int(consequence), blocks_other_tasks=blocks_other_tasks)
            st.success("Added to your planner.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))

    data = agent.load_data()
    today = agent.date.today().isoformat()
    overdue = [t for t in data["tasks"] if t["status"] != "completed" and t.get("due") and t["due"] < today]
    due_today = [t for t in data["tasks"] if t["status"] != "completed" and t.get("due") == today]
    if overdue: st.warning("Overdue: " + ", ".join(t["title"] for t in overdue))
    if due_today: st.info("Due today: " + ", ".join(t["title"] for t in due_today))
    filter_columns = st.columns(2)
    task_filter = filter_columns[0].selectbox("Status", ["Open", "All", "Completed"], key="task_status_filter")
    categories = sorted({str(task.get("category", "General")) for task in data["tasks"]}, key=str.casefold)
    course_filter = filter_columns[1].selectbox("Course / subject", ["All courses", *categories], key="task_course_filter")
    visible = [t for t in data["tasks"]
               if (task_filter == "All" or (task_filter == "Completed") == (t["status"] == "completed"))
               and (course_filter == "All courses" or t.get("category", "General") == course_filter)]
    if st.button("Export deadlines to calendar (.ics)"):
        dated = [t for t in data["tasks"] if t["status"] != "completed" and t.get("due")]
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        def ics_escape(value: str) -> str:
            return value.replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")
        events = []
        for t in dated:
            end = (agent.parse_date(t["due"]) + agent.timedelta(days=1)).strftime("%Y%m%d")
            events.append(f"BEGIN:VEVENT\r\nUID:adspa-task-{t['id']}@local\r\nDTSTAMP:{stamp}\r\nDTSTART;VALUE=DATE:{t['due'].replace('-', '')}\r\nDTEND;VALUE=DATE:{end}\r\nSUMMARY:{ics_escape(t['title'])}\r\nEND:VEVENT")
        ics = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//ADSPA//Academic Planner//EN\r\n" + "\r\n".join(events) + "\r\nEND:VCALENDAR\r\n"
        st.download_button("Download .ics calendar", ics, "academic-deadlines.ics", "text/calendar", key="ics-download")
    if not visible:
        st.info("No coursework yet. Add an assignment or study task above." if not data["tasks"]
                else "No tasks match these filters. Try showing all statuses or courses.")
    focus_id = st.session_state.get("coursework_focus_id")
    for task in sorted(visible, key=lambda t: (t["status"] == "completed", agent.task_rank(t))):
        with st.container(border=True):
            cols = st.columns([8, 1])
            due_info = countdown(task)
            due_label = f" · deadline {task['due']} {task.get('due_time', '23:59')} · {due_info['label']}" if task.get("due") and due_info else ""
            cols[0].markdown(f"**{task['title']}**  \n{task.get('task_type', 'assignment').title()} · {task.get('category', 'General')} · {task['priority'].title()} · {task.get('work_status', 'not_started').replace('_', ' ').title()}{due_label}")
            if task["status"] != "completed" and cols[1].button("Complete", key=f"complete-{task['id']}", use_container_width=True):
                agent.complete_task(task["id"]); st.rerun()
            with st.expander("Edit details" if focus_id != task["id"] else "Task details", expanded=focus_id == task["id"]):
                with st.form(f"edit-task-{task['id']}"):
                    new_title = st.text_input("Title", task["title"], key=f"title-{task['id']}")
                    due_value = agent.parse_date(task["due"]) if task.get("due") else None
                    new_due = st.date_input("Deadline (optional)", value=due_value, key=f"due-{task['id']}")
                    c1, c2, c3 = st.columns(3)
                    new_due_time = c1.time_input("Deadline time", value=datetime.strptime(task.get("due_time", "23:59"), "%H:%M").time(), key=f"due-time-{task['id']}")
                    new_priority = c2.selectbox("Priority", ["low", "medium", "high", "urgent"], index=["low", "medium", "high", "urgent"].index(task["priority"]), key=f"priority-{task['id']}")
                    new_minutes = c3.number_input("Study minutes", 1, 1440, int(task["estimated_minutes"]), key=f"minutes-{task['id']}")
                    new_category = st.text_input("Course or subject", task.get("category", "General"), key=f"category-{task['id']}")
                    c1, c2 = st.columns(2)
                    new_difficulty = c1.selectbox("Difficulty", [1, 2, 3, 4, 5], index=min(4, max(0, int(task.get("difficulty", 3)) - 1)), key=f"difficulty-{task['id']}")
                    new_importance = c2.selectbox("Importance", [1, 2, 3, 4, 5], index=min(4, max(0, int(task.get("importance", 3)) - 1)), key=f"importance-{task['id']}")
                    new_percent = st.slider("Work completed (%)", 0, 100, int(task.get("percent_complete", 0)), key=f"percent-{task['id']}")
                    new_status = st.selectbox("Submission status", ["not_started", "in_progress", "reviewed", "submitted"], index=["not_started", "in_progress", "reviewed", "submitted"].index(task.get("work_status", "not_started")), key=f"work-status-{task['id']}")
                    new_reminders = st.multiselect("Reminder days", [30, 14, 7, 3, 1, 0], default=task.get("reminder_days", [7, 3, 1, 0]), key=f"reminders-{task['id']}")
                    save_task = st.form_submit_button("Save changes", type="primary")
                if save_task:
                    agent.update_task(task["id"], new_title, new_due.isoformat() if new_due else None, new_priority, int(new_minutes), new_category)
                    agent.update_task_metadata(task["id"], due_time=new_due_time.isoformat(timespec="minutes"), difficulty=new_difficulty,
                        importance=new_importance, percent_complete=new_percent,
                        work_status=new_status, reminder_days=new_reminders)
                    st.rerun()
                if st.button("Delete task", key=f"delete-{task['id']}"):
                    agent.delete_task(task["id"]); st.rerun()
    st.divider()
    assignment_workflow_view.render(agent)

if current_page == "courses":
    st.subheader("Your courses")
    with st.expander("Add a course", expanded=False):
        with st.form("add-course", clear_on_submit=True):
            course_title = st.text_input("Course title", placeholder="Introduction to Biology")
            c1, c2, c3 = st.columns(3)
            course_subject = c1.text_input("Subject / department")
            course_code = c2.text_input("Course code", placeholder="BIO 101")
            course_term = c3.text_input("Term", placeholder="Fall 2026")
            course_instructor = st.text_input("Instructor")
            course_description = st.text_area("Course overview / notes")
            create_course = st.form_submit_button("Add course", type="primary")
        if create_course:
            try:
                agent.add_course(course_title, course_subject, course_code,
                                 course_instructor, course_term, course_description)
                st.success("Course added.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    data = agent.load_data()
    data.setdefault("courses", [])
    data.setdefault("course_materials", [])
    if not data["courses"]:
        st.info("Add a course to organize its assignments, projects, and study materials.")
    else:
        course_query = st.text_input("Find a course", placeholder="Search title, subject, code, or term")
        query = course_query.strip().casefold()
        visible_courses = [course for course in data["courses"]
            if not query or query in " ".join(str(course.get(field, ""))
                for field in ("title", "subject", "course_code", "term")).casefold()]
        visible_courses.sort(key=lambda course: (course.get("term", "").casefold(), course["title"].casefold()))
        st.caption(f"Showing {len(visible_courses)} of {len(data['courses'])} course(s)")
    for course in (visible_courses if data["courses"] else []):
        course_id = int(course["id"])
        linked_tasks = [task for task in data["tasks"] if int(task.get("course_id", -1)) == course_id]
        materials = [material for material in data["course_materials"] if int(material.get("course_id", -1)) == course_id]
        code_label = f" · {course['course_code']}" if course.get("course_code") else ""
        with st.expander(f"{course['title']}{code_label} · {len(linked_tasks)} coursework item(s)", expanded=False):
            details = [value for value in (course.get("subject"), course.get("term"), course.get("instructor")) if value]
            if details:
                st.caption(" · ".join(details))
            if course.get("description"):
                st.write(course["description"])
            assignment_tab, project_tab, material_tab, course_details_tab = st.tabs(
                ["Assignments", "Projects", "Study materials", "Course details"])

            for tab, kind in ((assignment_tab, "assignment"), (project_tab, "project")):
                with tab:
                    with st.form(f"course-{kind}-{course_id}", clear_on_submit=True):
                        st.markdown(f"Add a {kind}")
                        work_title = st.text_input("Title", key=f"{kind}-title-{course_id}")
                        c1, c2, c3, c4 = st.columns(4)
                        work_due = c1.date_input("Deadline (optional)", value=None, key=f"{kind}-due-{course_id}")
                        work_time = c2.time_input("Due time", value=datetime.strptime("23:59", "%H:%M").time(), key=f"{kind}-time-{course_id}")
                        work_priority = c3.selectbox("Priority", ["low", "medium", "high", "urgent"], index=1, key=f"{kind}-priority-{course_id}")
                        work_minutes = c4.number_input("Estimated minutes", min_value=1, max_value=1440, value=60, key=f"{kind}-minutes-{course_id}")
                        if st.form_submit_button(f"Add {kind}"):
                            try:
                                agent.add_course_task(course_id, work_title,
                                    work_due.isoformat() if work_due else None,
                                    work_priority, int(work_minutes), kind,
                                    work_time.isoformat(timespec="minutes"))
                                st.success(f"{kind.title()} added to your study plan.")
                                st.rerun()
                            except ValueError as exc:
                                st.error(str(exc))
                    kind_tasks = [task for task in linked_tasks if task.get("academic_type") == kind]
                    if not kind_tasks:
                        st.caption(f"No {kind}s added yet.")
                    for task in sorted(kind_tasks, key=agent.task_rank):
                        due_text = f" · due {task['due']} ({agent.due_state(task)})" if task.get("due") else " · no deadline"
                        st.write(f"{'✓' if task['status'] == 'completed' else '○'} **{task['title']}** · {task['priority']} · {task['estimated_minutes']} min{due_text}")
                        c1, c2 = st.columns(2)
                        if task["status"] != "completed" and c1.button("Complete", key=f"course-complete-{task['id']}"):
                            agent.complete_task(task["id"])
                            st.rerun()
                        if c2.button("Delete", key=f"course-delete-{task['id']}"):
                            agent.delete_task(task["id"])
                            st.rerun()

            with material_tab:
                with st.form(f"course-material-{course_id}", clear_on_submit=True):
                    material_title = st.text_input("Material title (optional for uploaded files)", key=f"material-title-{course_id}", placeholder="Lecture slides, textbook chapter…")
                    material_unit = st.text_input("Unit / topic", key=f"material-unit-{course_id}", placeholder="Unit 4")
                    material_reference = st.text_input("Link or file location", key=f"material-ref-{course_id}", placeholder="https://… or local path")
                    material_notes = st.text_area("Notes", key=f"material-notes-{course_id}")
                    material_file = st.file_uploader("Upload study material (25 MB max)", type=["pdf", "docx", "pptx", "txt", "md", "csv", "png", "jpg", "jpeg"], key=f"material-file-{course_id}")
                    if st.form_submit_button("Save study material"):
                        try:
                            agent.add_course_material(course_id, material_title, material_reference,
                                material_notes, material_file.name if material_file else "",
                                material_file.getvalue() if material_file else None,
                                material_unit)
                            st.rerun()
                        except ValueError as exc:
                            st.error(str(exc))
                if not materials:
                    st.caption("No study materials saved yet.")
                for material in materials:
                    st.markdown(f"**{material['title']}**" + (f" · {material['unit']}" if material.get("unit") else ""))
                    if material.get("reference"):
                        if material["reference"].startswith(("https://", "http://")):
                            st.link_button("Open study material", material["reference"])
                        else:
                            st.code(material["reference"], language=None)
                    if material.get("notes"):
                        st.write(material["notes"])
                    if material.get("stored_path"):
                        material_path = agent.DATA_DIR / material["stored_path"]
                        if material_path.is_file():
                            st.download_button("Download file", material_path.read_bytes(),
                                material.get("file_name") or material_path.name,
                                key=f"material-download-{material['id']}")
                    if st.button("Remove material", key=f"material-remove-{material['id']}"):
                        agent.delete_course_material(material["id"])
                        st.rerun()

            with course_details_tab:
                with st.form(f"edit-course-{course_id}"):
                    edit_title = st.text_input("Course title", course["title"], key=f"edit-course-title-{course_id}")
                    c1, c2, c3 = st.columns(3)
                    edit_subject = c1.text_input("Subject / department", course.get("subject", ""), key=f"edit-course-subject-{course_id}")
                    edit_code = c2.text_input("Course code", course.get("course_code", ""), key=f"edit-course-code-{course_id}")
                    edit_term = c3.text_input("Term", course.get("term", ""), key=f"edit-course-term-{course_id}")
                    edit_instructor = st.text_input("Instructor", course.get("instructor", ""), key=f"edit-course-instructor-{course_id}")
                    edit_description = st.text_area("Course overview / notes", course.get("description", ""), key=f"edit-course-description-{course_id}")
                    if st.form_submit_button("Save course details"):
                        try:
                            agent.update_course(course_id, edit_title, edit_subject,
                                edit_code, edit_instructor, edit_term, edit_description)
                            st.success("Course details saved.")
                            st.rerun()
                        except ValueError as exc:
                            st.error(str(exc))
    st.divider()
    material_view.render(agent)

if current_page == "plan":
    planner_view.render(agent)

if current_page == "reminders":
    notification_view.render(agent, notification_component)

if current_page == "exam_schedule":
    exam_view.render(agent)

if current_page == "research":
    research_view.render(agent)

if current_page == "notes":
    st.subheader("Course and study notes")
    with st.form("add_note", clear_on_submit=True):
        note_text = st.text_area("Note, concept, or reminder")
        if st.form_submit_button("Save note"):
            try: agent.add_note(note_text); st.success("Note saved."); st.rerun()
            except ValueError as exc: st.error(str(exc))
    for note in reversed(agent.load_data()["notes"]):
        st.write(note["text"]); st.caption(note["created_at"])

if current_page == "assistant":
    st.info("Ask for help organizing coursework, prioritizing deadlines, or planning a study session. Chat may use the configured AI provider and a summary of open tasks.")
    for item in st.session_state.get("chat_history", []):
        with st.chat_message(item["role"]): st.write(item["content"])
    last_reply = next((item["content"] for item in reversed(st.session_state.get("chat_history", []))
                       if item["role"] == "assistant"), "")
    voice_result = voice_input(response=last_reply, key="study-voice-input")
    voice_prompt = ""
    if isinstance(voice_result, dict) and voice_result.get("nonce") != st.session_state.get("used_voice_nonce"):
        voice_prompt = str(voice_result.get("transcript", "")).strip()
        if voice_prompt:
            st.session_state["used_voice_nonce"] = voice_result["nonce"]
            st.caption(f"Voice input: {voice_prompt}")
    prompt = st.chat_input("Ask about your coursework or study plan") or voice_prompt
    if prompt:
        history = st.session_state.setdefault("chat_history", [])
        history.append({"role": "user", "content": prompt})
        try:
            pending_capture = st.session_state.get("pending_academic_capture")
            local_result = agent.web_chat_reply(prompt, history, pending_capture)
            reply = local_result["reply"] if local_result else agent.openai_chat_reply(prompt, history)
            if local_result is not None and "pending_capture" in local_result:
                st.session_state["pending_academic_capture"] = local_result["pending_capture"]
            elif local_result is not None:
                st.session_state.pop("pending_academic_capture", None)
        except Exception as exc: reply = f"I couldn't complete that request: {exc}"
        history.append({"role": "assistant", "content": reply}); st.rerun()

if current_page == "progress":
    data = agent.load_data()
    st.subheader("Progress and grades")
    weekly = weekly_productivity_report(data["tasks"])
    topics = data.get("topics", [])
    syllabus_coverage_percent = round(100 * sum(topic.get("status") in {"revised", "mastered"} for topic in topics) / max(1, len(topics)))
    quiz_scores = [float(result["score_percent"]) for topic in topics
                   for result in topic.get("quiz_results", []) if result.get("score_percent") is not None]
    current_week = date.today() - timedelta(days=date.today().weekday())
    week_starts = [current_week - timedelta(weeks=offset) for offset in (3, 2, 1, 0)]
    minutes_by_week = {week: 0 for week in week_starts}
    for session in data.get("study_sessions", []):
        if session.get("kind") == "break" or session.get("status") != "completed":
            continue
        try:
            session_day = date.fromisoformat(session.get("date", ""))
        except ValueError:
            continue
        week_start = session_day - timedelta(days=session_day.weekday())
        if week_start in minutes_by_week:
            minutes_by_week[week_start] += int(session.get("duration_minutes", 0))
    hours_this_week = minutes_by_week[current_week] / 60
    progress_metrics = st.columns(4)
    progress_metrics[0].metric("Weekly task progress", f"{weekly['completion_rate_percent']}%" if weekly["created_or_completed"] else "—")
    progress_metrics[1].metric("Syllabus coverage", f"{syllabus_coverage_percent}%")
    progress_metrics[2].metric("Quiz average", f"{sum(quiz_scores) / len(quiz_scores):.0f}%" if quiz_scores else "—")
    progress_metrics[3].metric("Study time this week", f"{hours_this_week:.1f}h")

    st.markdown("#### Study time · last four weeks")
    if any(minutes_by_week.values()):
        import pandas as pd
        study_chart = pd.DataFrame({
            "Study hours": [minutes_by_week[week] / 60 for week in week_starts]
        }, index=[week.strftime("%b %d") for week in week_starts])
        st.bar_chart(study_chart)
    else:
        st.caption("Completed study sessions will appear here as you log them.")

    if topics:
        st.markdown("#### Syllabus coverage")
        st.progress(syllabus_coverage_percent / 100, text=f"{sum(topic.get('status') in {'revised', 'mastered'} for topic in topics)} of {len(topics)} topics revised or mastered")
    else:
        st.caption("Add syllabus topics under Exams & Assessments to track preparation progress.")

    risks = assess_deadline_risk(data["tasks"], data["settings"]["daily_focus_minutes"], settings=data["settings"])
    st.markdown("#### Workload and deadlines")
    if risks:
        for risk in risks:
            with st.container(border=True):
                st.markdown(f"**{risk['title']}** · {risk['risk'].upper()} · {risk['hours_left']:.1f} hours remaining")
                st.caption(f"{risk['explanation']} · {risk['remaining_minutes']} minutes remaining / {risk['available_minutes']} available")
                with st.expander("Recovery plan"):
                    for step in risk["recovery_plan"]: st.write(step)
    else:
        st.info("Add deadlines to see workload risk estimates.")
    for collision in deadline_collisions(data["tasks"], daily_minutes=data["settings"]["daily_focus_minutes"], settings=data["settings"]):
        st.warning(f"{collision['start'][:10]}–{collision['end'][:10]}: {', '.join(collision['task_titles'])} · {collision['workload_minutes']} min of work / {collision['available_minutes']} available. {collision['recommendation']}")
    risk_by_id = {row["task_id"]: row for row in risks}
    st.markdown("#### Recommended priority order")
    for rank, task in enumerate(optimize_workload(data["tasks"], data["settings"]["daily_focus_minutes"], data["settings"]), 1):
        risk = next((row for row in risk_by_id.values() if row["task_id"] == task.get("id")), None)
        st.write(f"{rank}. **{task['title']}** · score {priority_score(task, risk_by_id, data['settings'].get('priority_weights'))}/100 · risk {risk['risk'] if risk else 'unrated'}")
    st.markdown("#### This week")
    c1, c2, c3 = st.columns(3)
    c1.metric("Completed", weekly["completed"]); c2.metric("Open", weekly["unfinished"]); c3.metric("Overdue", weekly["overdue_now"])
    st.caption(weekly["basis"])

if current_page == "settings":
    data = agent.load_data()
    st.subheader("Study preferences")
    with st.form("preferences"):
        mode = st.selectbox("Study mode", ["balanced", "focus", "light", "offline"], index=["balanced", "focus", "light", "offline"].index(data["settings"]["study_mode"]))
        budget = st.number_input("Daily study budget (minutes)", min_value=15, max_value=720, value=int(data["settings"]["daily_focus_minutes"]))
        saved = st.form_submit_button("Save preferences", type="primary")
    if saved:
        agent.set_mode(mode)
        latest = agent.load_data(); latest["settings"]["daily_focus_minutes"] = int(budget)
        agent.save_data(latest); agent.log_event(f"Set daily study budget: {int(budget)} minutes")
        st.success("Study preferences saved."); st.rerun()
    with st.form("briefing-preferences"):
        briefing_hour = st.number_input("Daily briefing hour (24-hour clock)", 0, 23,
            int(data["settings"].get("daily_briefing_hour", 7)))
        save_briefing_hour = st.form_submit_button("Save briefing time")
    if save_briefing_hour:
        data["settings"]["daily_briefing_hour"] = int(briefing_hour)
        agent.save_data(data)
        st.success("Briefing time saved. Restart the reminder service for the new time to take effect.")
    st.markdown("#### AI chat setup")
    st.caption("Optional: configure OPENAI_API_KEY in .streamlit/secrets.toml and restart the dashboard. Keep the key private.")
    st.divider()
    st.subheader("Planning weights and exam countdown")
    with st.form("planning-weights"):
        st.caption("Priority uses normalized weights. These are starting defaults; tune them to your study style.")
        old_weights = data["settings"].get("priority_weights", {})
        c1, c2, c3, c4 = st.columns(4)
        weights = {
            "urgency": c1.number_input("Urgency", 0.0, 1.0, float(old_weights.get("urgency", .35)), .05),
            "importance": c2.number_input("Importance", 0.0, 1.0, float(old_weights.get("importance", .25)), .05),
            "risk": c3.number_input("Risk", 0.0, 1.0, float(old_weights.get("risk", .20)), .05),
            "difficulty": c4.number_input("Difficulty", 0.0, 1.0, float(old_weights.get("difficulty", .10)), .05),
        }
        c1, c2, c3 = st.columns(3)
        weights.update({
            "blocking": c1.number_input("Blocking impact", 0.0, 1.0, float(old_weights.get("blocking", .10)), .05),
            "consequence": c2.number_input("Late consequence", 0.0, 1.0, float(old_weights.get("consequence", 0)), .05),
            "completion": c3.number_input("Progress made", 0.0, 1.0, float(old_weights.get("completion", 0)), .05),
        })
        save_weights = st.form_submit_button("Save priority weights")
    if save_weights:
        data["settings"]["priority_weights"] = weights
        agent.save_data(data)
        st.success("Priority weights saved.")
        st.rerun()
    phase_rules = data["settings"].get("exam_phase_rules", {})
    with st.form("exam-countdown-rules"):
        st.caption("Set the preparation phase guidance by countdown day. The phase applies at or below its configured threshold.")
        phase_inputs = {}
        for days, label in ((14, "Coverage phase"), (7, "Practice phase"), (3, "Weak-topic phase"), (1, "Final review phase")):
            phase_inputs[str(days)] = st.text_input(f"{label} · {days} days", value=phase_rules.get(str(days), ""), key=f"exam-phase-{days}")
        save_phases = st.form_submit_button("Save exam countdown guidance")
    if save_phases:
        data["settings"]["exam_phase_rules"] = {key: value.strip() for key, value in phase_inputs.items() if value.strip()}
        agent.save_data(data)
        st.success("Exam countdown guidance saved.")
        st.rerun()
    st.divider()
    st.subheader("Google Calendar and Gmail")
    st.caption("Connect a Google account to add coursework deadlines to your primary Calendar and send approaching-deadline emails through Gmail.")
    uploaded_credentials = st.file_uploader("Google OAuth desktop client JSON", type=["json"], key="google-oauth-file")
    if uploaded_credentials is not None and st.button("Save Google OAuth client"):
        try:
            credential_data = json.loads(uploaded_credentials.getvalue())
            if not isinstance(credential_data, dict) or "installed" not in credential_data:
                raise ValueError("Use an OAuth client JSON for a Desktop app.")
            CREDENTIALS_FILE.write_text(json.dumps(credential_data), encoding="utf-8")
            CREDENTIALS_FILE.chmod(0o600)
            st.success("OAuth client saved locally. It is excluded from Git.")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            st.error(str(exc))
    google_ready = True
    try:
        google_dependencies()
        connected = load_credentials() is not None
    except RuntimeError as exc:
        google_ready = False
        connected = False
        st.warning(str(exc))
    if not connected:
        if st.button("Connect Google account", type="primary", disabled=not google_ready):
            try:
                with st.spinner("Complete Google authorization in the browser window…"):
                    connect_google()
                st.success("Google account connected.")
                st.rerun()
            except Exception as exc:
                st.error(f"Google connection failed: {exc}")
    else:
        st.success("Google account connected.")
        data = agent.load_data()
        if st.button("Sync coursework deadlines to Google Calendar"):
            try:
                calendar, _ = services()
                ids, count = sync_deadlines(calendar, data["tasks"], data.get("google_calendar_event_ids", {}))
                data["google_calendar_event_ids"] = ids
                agent.save_data(data)
                st.success(f"Calendar sync complete. {count} deadline event(s) updated.")
            except Exception as exc:
                st.error(f"Calendar sync failed: {exc}")
        reminder_settings = data["settings"].get("gmail_reminders", {})
        with st.form("gmail-reminders"):
            enabled = st.checkbox("Email me approaching deadlines", value=bool(reminder_settings.get("enabled", False)))
            recipient = st.text_input("Reminder email address", value=reminder_settings.get("recipient", ""), placeholder="you@example.com")
            save_reminders = st.form_submit_button("Save email reminder settings")
        if save_reminders:
            if enabled and (not recipient.strip() or "@" not in recipient):
                st.error("Enter a valid reminder email address.")
            else:
                data["settings"]["gmail_reminders"] = {"enabled": enabled, "recipient": recipient.strip()}
                agent.save_data(data)
                st.success("Email reminder settings saved.")
                st.rerun()
        telegram_settings = data["settings"].get("telegram_reminders", {})
        with st.form("telegram-reminders"):
            telegram_enabled = st.checkbox("Send reminders through Telegram", value=bool(telegram_settings.get("enabled", False)))
            bot_token = st.text_input("Telegram bot token", value=telegram_settings.get("bot_token", ""), type="password")
            chat_id = st.text_input("Telegram chat ID", value=telegram_settings.get("chat_id", ""))
            save_telegram = st.form_submit_button("Save Telegram reminder settings")
        if save_telegram:
            if telegram_enabled and (not bot_token.strip() or not chat_id.strip()):
                st.error("Enter both a bot token and chat ID before enabling Telegram reminders.")
            else:
                data["settings"]["telegram_reminders"] = {"enabled": telegram_enabled,
                    "bot_token": bot_token.strip(), "chat_id": chat_id.strip()}
                agent.save_data(data)
                st.success("Telegram reminder settings saved.")
                st.rerun()
        if st.button("Disconnect Google account"):
            try:
                TOKEN_FILE.unlink(missing_ok=True)
                data["settings"]["gmail_reminders"] = {"enabled": False, "recipient": "", "days_before": 2}
                agent.save_data(data)
                st.rerun()
            except OSError as exc:
                st.error(f"Could not remove the local Google token: {exc}")
    st.caption("A persistent SQLite-backed scheduler checks reminders every 15 minutes while the planner service is running. Each configured task interval is sent once per deadline. In-app and browser desktop alerts work without email or Telegram.")
    st.divider()
    st.subheader("Study data")
    st.download_button("Export planner data", json.dumps(data, indent=2, ensure_ascii=False), "academic-planner.json", "application/json")
    if st.button("Create local backup"):
        agent.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        target = agent.BACKUP_DIR / f"agent_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        import shutil
        shutil.copy2(agent.DATA_FILE, target); agent.log_event(f"Created local backup {target.name}")
        st.success(f"Saved {target.name}")
    if agent.LOG_FILE.exists():
        with st.expander("Recent planner activity"):
            for line in reversed(agent.LOG_FILE.read_text(encoding="utf-8").splitlines()[-30:]): st.caption(line)


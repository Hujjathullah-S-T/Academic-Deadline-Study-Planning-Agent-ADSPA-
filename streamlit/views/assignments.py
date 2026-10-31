"""Assignment lifecycle, checklist dependency, and submission tracking UI."""
from __future__ import annotations

import streamlit as st

from academic.assignment_workflow import (STAGES, add_checklist_item,
    set_checklist_status, set_workflow_stage)
from academic.records import create_assignment_workflow


def render(agent) -> None:
    data = agent.load_data()
    st.subheader("Assignment workflow")
    candidates = [task for task in data["tasks"]
                  if task.get("task_type", task.get("academic_type", "assignment")) in {"assignment", "laboratory", "project"}]
    task_by_id = {int(task["id"]): task for task in candidates}
    workflows = {int(row["task_id"]): row for row in data.get("assignment_workflows", [])}
    available = [task for task in candidates if int(task["id"]) not in workflows]
    if available:
        options = {f"#{task['id']} · {task['title']} · {task.get('category', 'General')}": task["id"] for task in available}
        selected = st.selectbox("Select assignment to track", list(options))
        if st.button("Start assignment workflow", type="primary"):
            try:
                create_assignment_workflow(data, options[selected])
                agent.save_data(data)
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    elif not workflows:
        st.info("Create an assignment, lab record, or project in Coursework or Courses first.")

    for workflow in data.get("assignment_workflows", []):
        task = task_by_id.get(int(workflow["task_id"]))
        if not task:
            continue
        current_index = STAGES.index(workflow.get("stage", "received"))
        with st.expander(f"{task['title']} · {workflow['stage'].replace('_', ' ').title()}", expanded=True):
            st.caption(f"Deadline: {task.get('due') or 'not set'} · {task.get('category', 'General')} · {task.get('percent_complete', 0):g}% complete")
            done = sum(step.get("status") == "completed" for step in workflow.get("checklist", []))
            total = len(workflow.get("checklist", []))
            st.progress(done / total if total else 0, text=f"Checklist {done}/{total} complete")

            material_options = {f"{row['title']} · {row.get('file_name') or 'saved notes/link'}": row
                                for row in data.get("course_materials", [])
                                if row.get("extracted_text") and str(row.get("course_id")) == str(task.get("course_id"))}
            if material_options:
                selected_material = st.selectbox("Analyze attached brief", list(material_options), key=f"brief-{task['id']}")
                if st.button("Extract question checklist", key=f"extract-questions-{task['id']}"):
                    material = material_options[selected_material]
                    questions = material.get("assignment_questions", [])
                    for question in questions:
                        add_checklist_item(workflow, f"Question {question['number']}: {question['text'][:160]}",
                            marks=question.get("marks"))
                    workflow["source_material_id"] = material.get("id")
                    agent.save_data(data)
                    st.info(f"Added {len(questions)} extracted question(s). Verify them against the original brief.")
                    st.rerun()

            for step in workflow.get("checklist", []):
                deps = step.get("depends_on", [])
                dependency_text = f" · requires {', '.join('#' + str(dep) for dep in deps)}" if deps else ""
                c1, c2 = st.columns([5, 1])
                c1.write(f"**#{step['id']} {step['title']}**{dependency_text} · {step.get('estimated_minutes', 30)} min" + (f" · {step['marks']} marks" if step.get("marks") is not None else ""))
                checked = c2.checkbox("Done", value=step.get("status") == "completed", key=f"workflow-step-{task['id']}-{step['id']}")
                if checked != (step.get("status") == "completed"):
                    try:
                        set_checklist_status(workflow, step["id"], "completed" if checked else "pending")
                        agent.save_data(data)
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))

            with st.form(f"new-step-{task['id']}", clear_on_submit=True):
                st.markdown("Add a workflow step")
                c1, c2, c3 = st.columns([4, 1, 1])
                step_title = c1.text_input("Step")
                step_minutes = c2.number_input("Minutes", 1, 1440, 30, key=f"step-minutes-{task['id']}")
                step_marks = c3.number_input("Marks (0 if n/a)", 0.0, 1000.0, 0.0, key=f"step-marks-{task['id']}")
                dependency_options = {f"#{item['id']} {item['title']}": item["id"] for item in workflow["checklist"]}
                dependencies = st.multiselect("Prerequisites", list(dependency_options), key=f"step-deps-{task['id']}")
                if st.form_submit_button("Add workflow step"):
                    try:
                        add_checklist_item(workflow, step_title, int(step_minutes),
                            float(step_marks) if step_marks else None,
                            [dependency_options[label] for label in dependencies])
                        agent.save_data(data)
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))

            next_stage = STAGES[current_index + 1] if current_index + 1 < len(STAGES) else None
            if next_stage:
                with st.form(f"advance-{task['id']}"):
                    st.markdown(f"Next stage: **{next_stage.replace('_', ' ').title()}**")
                    final_file = st.text_input("Final file location", value=workflow.get("final_file", ""))
                    confirmation = st.text_input("Submission confirmation / reference", value=workflow.get("submission_confirmation", ""))
                    if st.form_submit_button("Advance workflow"):
                        try:
                            set_workflow_stage(workflow, next_stage, final_file, confirmation)
                            if next_stage == "submitted":
                                task["status"] = "completed"
                                task["work_status"] = "submitted"
                                task["submission_date"] = workflow["submission_date"]
                                task["submission_confirmation"] = workflow["submission_confirmation"]
                                task["percent_complete"] = 100
                            agent.save_data(data)
                            st.success(f"Assignment moved to {next_stage.replace('_', ' ')}.")
                            st.rerun()
                        except ValueError as exc:
                            st.error(str(exc))

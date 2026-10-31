"""Research, capstone, project milestone, and experiment tracking UI."""
from __future__ import annotations

import json

import streamlit as st

from academic.records import (add_project_experiment, add_project_milestone,
                              add_research_project, update_project_experiment)


def render(agent) -> None:
    data = agent.load_data()
    st.subheader("Research and project tracker")
    st.caption("Track literature, datasets, implementation, experiments, evaluation, meetings, and submissions.")
    with st.form("add-research-project", clear_on_submit=True):
        title = st.text_input("Research / capstone project")
        c1, c2, c3 = st.columns(3)
        project_type = c1.selectbox("Type", ["research", "capstone", "course_project", "paper", "other"])
        course_names = {"Unlinked": None, **{course["title"]: course["id"] for course in data.get("courses", [])}}
        course_name = c2.selectbox("Course", list(course_names))
        due = c3.date_input("Submission deadline (optional)", value=None, key="research-due")
        repository = st.text_input("Git repository / project link")
        description = st.text_area("Abstract, objective, or project scope")
        if st.form_submit_button("Create project", type="primary"):
            try:
                add_research_project(data, title, project_type, course_names[course_name],
                    description, repository, due.isoformat() if due else None)
                if not due:
                    agent.save_data(data)
                st.success("Project added.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    for project in data.get("projects", []):
        project_id = int(project["id"])
        milestones = [task for task in data["tasks"] if int(task.get("project_id", -1)) == project_id]
        experiments = [row for row in data.get("experiments", []) if int(row.get("project_id", -1)) == project_id]
        with st.expander(f"{project['title']} · {project['type'].replace('_', ' ').title()} · {project.get('status', 'active')}", expanded=False):
            st.write(project.get("description", ""))
            if project.get("repository"):
                st.code(project["repository"], language=None)
            if project.get("due"):
                st.caption(f"Submission deadline: {project['due']}")
            if milestones:
                st.markdown("**Milestones**")
                for task in sorted(milestones, key=agent.task_rank):
                    st.write(f"{'✓' if task['status'] == 'completed' else '○'} {task['title']} · {task.get('due') or 'no deadline'} · {task['estimated_minutes']} min")
            with st.form(f"milestone-{project_id}", clear_on_submit=True):
                st.markdown("Add a milestone")
                c1, c2, c3 = st.columns(3)
                milestone_title = c1.text_input("Milestone", key=f"milestone-title-{project_id}")
                milestone_due = c2.date_input("Due (optional)", value=None, key=f"milestone-due-{project_id}")
                milestone_minutes = c3.number_input("Estimated minutes", 1, 1440, 120, key=f"milestone-minutes-{project_id}")
                if st.form_submit_button("Add milestone"):
                    try:
                        add_project_milestone(data, project_id, milestone_title,
                            milestone_due.isoformat() if milestone_due else None,
                            "high", int(milestone_minutes))
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))

            with st.form(f"experiment-{project_id}", clear_on_submit=True):
                st.markdown("Record an experiment")
                experiment_title = st.text_input("Experiment / run name", key=f"experiment-title-{project_id}")
                c1, c2 = st.columns(2)
                dataset_version = c1.text_input("Dataset version", key=f"dataset-{project_id}")
                checkpoint = c2.text_input("Checkpoint location", key=f"checkpoint-{project_id}")
                configuration = st.text_area("Configuration (JSON or text)", key=f"config-{project_id}")
                notes = st.text_area("Research notes", key=f"exp-notes-{project_id}")
                if st.form_submit_button("Add planned experiment"):
                    try:
                        add_project_experiment(data, project_id, experiment_title,
                            dataset_version, configuration, checkpoint, notes)
                        agent.save_data(data)
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
            for experiment in experiments:
                st.markdown(f"**{experiment['title']}** · `{experiment['status']}` · dataset `{experiment.get('dataset_version') or 'unspecified'}`")
                with st.form(f"update-experiment-{experiment['id']}"):
                    c1, c2 = st.columns(2)
                    state = c1.selectbox("Run state", ["planned", "running", "completed", "failed"], index=["planned", "running", "completed", "failed"].index(experiment.get("status", "planned")), key=f"exp-state-{experiment['id']}")
                    metrics_text = c2.text_input("Metrics JSON", value=json.dumps(experiment.get("metrics", {})), key=f"metrics-{experiment['id']}")
                    new_checkpoint = st.text_input("Checkpoint", value=experiment.get("checkpoint", ""), key=f"exp-checkpoint-{experiment['id']}")
                    result = st.text_area("Result / failure reason", value=experiment.get("result", ""), key=f"exp-result-{experiment['id']}")
                    if st.form_submit_button("Save experiment result"):
                        try:
                            metrics = json.loads(metrics_text or "{}")
                            if not isinstance(metrics, dict):
                                raise ValueError("Metrics must be a JSON object.")
                            update_project_experiment(data, experiment["id"], state, metrics, new_checkpoint, result)
                            agent.save_data(data)
                            st.rerun()
                        except (ValueError, json.JSONDecodeError) as exc:
                            st.error(str(exc))

            with st.form(f"project-update-{project_id}", clear_on_submit=True):
                st.markdown("Meeting or supervisor feedback")
                update_kind = st.selectbox("Record type", ["research meeting", "supervisor feedback", "literature note", "dataset note"], key=f"update-kind-{project_id}")
                update_text = st.text_area("Notes / action items", key=f"update-text-{project_id}")
                if st.form_submit_button("Save project note") and update_text.strip():
                    fresh = agent.load_data()
                    fresh["project_updates"].append({"id": max([int(row.get("id", 0)) for row in fresh["project_updates"]] + [0]) + 1,
                        "project_id": project_id, "type": update_kind, "text": update_text.strip(),
                        "created_at": agent.now_iso()})
                    agent.save_data(fresh)
                    st.rerun()
            for update in reversed([row for row in data.get("project_updates", []) if int(row.get("project_id", -1)) == project_id]):
                st.caption(f"{update['created_at']} · {update['type']}")
                st.write(update["text"])

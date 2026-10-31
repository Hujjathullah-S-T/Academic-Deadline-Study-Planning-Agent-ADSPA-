"""Validated create/update helpers for exams, syllabus topics, workflows, and projects."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from academic.assignment_workflow import new_workflow
from academic.research import new_experiment, new_project, update_experiment
from learning.exams import TOPIC_STATES, update_topic_quiz


def _next_id(rows: list[dict[str, Any]]) -> int:
    return max([int(row.get("id", 0)) for row in rows] + [0]) + 1


def add_exam(data: dict[str, Any], title: str, exam_date: str, course_id: int | None = None,
             exam_format: str = "written", study_minutes: int = 120,
             exam_time: str = "09:00") -> dict[str, Any]:
    if not title.strip():
        raise ValueError("Exam title cannot be empty.")
    date.fromisoformat(exam_date)
    from datetime import time
    time.fromisoformat(exam_time)
    exam = {"id": _next_id(data["exams"]), "title": title.strip(), "date": exam_date,
            "time": exam_time, "course_id": course_id, "format": exam_format,
            "study_minutes": max(15, int(study_minutes)), "phase_rules": {},
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds")}
    data["exams"].append(exam)
    from agent import add_task
    task = add_task(exam["title"], exam_date, "high", exam["study_minutes"],
                    next((course["title"] for course in data["courses"]
                          if int(course["id"]) == int(course_id or -1)), "Exams"),
                    task_type="examination", due_time=exam_time)
    fresh = __import__("agent").load_data()
    for task_row in fresh["tasks"]:
        if int(task_row["id"]) == int(task["id"]):
            task_row.update({"task_type": "examination", "exam_id": exam["id"], "course_id": course_id})
    fresh["exams"].append(exam)
    __import__("agent").save_data(fresh)
    return exam


def add_topic(data: dict[str, Any], exam_id: int, unit: str, title: str,
              difficulty: int = 3, study_minutes: int = 30) -> dict[str, Any]:
    if not title.strip():
        raise ValueError("Topic title cannot be empty.")
    exam = next((row for row in data["exams"] if int(row["id"]) == int(exam_id)), None)
    if not exam:
        raise ValueError("Select a valid examination.")
    topic = {"id": _next_id(data["topics"]), "exam_id": int(exam_id),
             "course_id": exam.get("course_id"), "unit": unit.strip(), "title": title.strip(),
             "status": "not_started", "difficulty": min(max(int(difficulty), 1), 5),
             "study_minutes": max(15, int(study_minutes)), "quiz_results": [],
             "review_interval_days": 1, "next_review": date.today().isoformat()}
    data["topics"].append(topic)
    return topic


def update_topic(data: dict[str, Any], topic_id: int, status: str | None = None,
                 quiz_score: float | None = None) -> dict[str, Any]:
    if status is not None and status not in TOPIC_STATES:
        raise ValueError("Unknown syllabus topic status.")
    topic = next((row for row in data["topics"] if int(row["id"]) == int(topic_id)), None)
    if not topic:
        raise ValueError("Syllabus topic not found.")
    if quiz_score is not None:
        topic.update(update_topic_quiz(topic, float(quiz_score)))
    elif status:
        topic["status"] = status
    return topic


def create_assignment_workflow(data: dict[str, Any], task_id: int) -> dict[str, Any]:
    if any(int(row.get("task_id", -1)) == int(task_id) for row in data["assignment_workflows"]):
        raise ValueError("This assignment already has a workflow.")
    if not any(int(task.get("id", -1)) == int(task_id) for task in data["tasks"]):
        raise ValueError("Select a valid assignment.")
    workflow = new_workflow(task_id)
    data["assignment_workflows"].append(workflow)
    return workflow


def add_research_project(data: dict[str, Any], title: str, project_type: str,
                         course_id: int | None, description: str,
                         repository: str, due: str | None = None) -> dict[str, Any]:
    project = new_project(_next_id(data["projects"]), title, project_type,
                          course_id, description, repository, due)
    data["projects"].append(project)
    if due:
        from agent import add_task, load_data, save_data
        save_data(data)
        task = add_task(f"Project deadline: {project['title']}", due, "high", 120,
                        project["title"], task_type="project")
        fresh = load_data()
        for task_row in fresh["tasks"]:
            if int(task_row["id"]) == int(task["id"]):
                task_row.update({"project_id": project["id"], "course_id": course_id})
        for project_row in fresh["projects"]:
            if int(project_row["id"]) == int(project["id"]):
                project_row["deadline_task_id"] = task["id"]
        save_data(fresh)
    return project


def add_project_milestone(data: dict[str, Any], project_id: int, title: str,
                          due: str | None, priority: str, minutes: int) -> dict[str, Any]:
    project = next((row for row in data["projects"] if int(row["id"]) == int(project_id)), None)
    if not project:
        raise ValueError("Select a valid project.")
    from agent import add_task, load_data, save_data
    task = add_task(title, due, priority, minutes, project["title"])
    fresh = load_data()
    for task_row in fresh["tasks"]:
        if int(task_row["id"]) == int(task["id"]):
            task_row.update({"task_type": "project_milestone", "project_id": int(project_id),
                             "course_id": project.get("course_id")})
    save_data(fresh)
    return task


def add_project_experiment(data: dict[str, Any], project_id: int, title: str,
                           dataset_version: str, configuration: str,
                           checkpoint: str, notes: str) -> dict[str, Any]:
    if not any(int(project["id"]) == int(project_id) for project in data["projects"]):
        raise ValueError("Select a valid project.")
    experiment = new_experiment(_next_id(data["experiments"]), project_id, title,
                                dataset_version, configuration, checkpoint, notes)
    data["experiments"].append(experiment)
    return experiment


def update_project_experiment(data: dict[str, Any], experiment_id: int, status: str,
                              metrics: dict[str, Any], checkpoint: str, result: str) -> dict[str, Any]:
    for index, experiment in enumerate(data["experiments"]):
        if int(experiment["id"]) == int(experiment_id):
            data["experiments"][index] = update_experiment(experiment, status, metrics,
                                                             checkpoint, result)
            return data["experiments"][index]
    raise ValueError("Experiment not found.")

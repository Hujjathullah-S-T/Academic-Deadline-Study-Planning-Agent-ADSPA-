"""Research project and experiment record constructors and state transitions."""
from __future__ import annotations

from datetime import datetime
from typing import Any

EXPERIMENT_STATES = {"planned", "running", "completed", "failed"}


def new_project(project_id: int, title: str, project_type: str = "research",
                course_id: int | None = None, description: str = "",
                repository: str = "", due: str | None = None) -> dict[str, Any]:
    if not title.strip():
        raise ValueError("Project title cannot be empty.")
    if project_type not in {"research", "capstone", "course_project", "paper", "other"}:
        raise ValueError("Choose a supported academic project type.")
    return {"id": int(project_id), "title": title.strip(), "type": project_type,
            "course_id": course_id, "description": description.strip(),
            "repository": repository.strip(), "due": due, "status": "active",
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds")}


def new_experiment(experiment_id: int, project_id: int, title: str,
                   dataset_version: str = "", configuration: str = "",
                   checkpoint: str = "", notes: str = "") -> dict[str, Any]:
    if not title.strip():
        raise ValueError("Experiment needs a name.")
    return {"id": int(experiment_id), "project_id": int(project_id), "title": title.strip(),
            "status": "planned", "dataset_version": dataset_version.strip(),
            "configuration": configuration.strip(), "checkpoint": checkpoint.strip(),
            "metrics": {}, "notes": notes.strip(), "result": "",
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds")}


def update_experiment(experiment: dict[str, Any], status: str,
                      metrics: dict[str, Any] | None = None,
                      checkpoint: str | None = None, result: str | None = None) -> dict[str, Any]:
    if status not in EXPERIMENT_STATES:
        raise ValueError("Experiment state must be planned, running, completed, or failed.")
    updated = {**experiment, "status": status}
    if metrics is not None:
        updated["metrics"] = metrics
    if checkpoint is not None:
        updated["checkpoint"] = checkpoint.strip()
    if result is not None:
        updated["result"] = result.strip()
    updated["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    if status in {"completed", "failed"}:
        updated["finished_at"] = updated["updated_at"]
    return updated

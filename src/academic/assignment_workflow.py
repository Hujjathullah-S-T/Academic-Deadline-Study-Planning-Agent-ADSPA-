"""Assignment lifecycle and dependency-aware checklists."""
from __future__ import annotations

from datetime import date
from typing import Any

STAGES = ["received", "analyzed", "planned", "in_progress", "reviewed", "submitted"]
DEFAULT_CHECKLIST = [
    {"title": "Read instructions and identify requirements", "stage": "analyzed", "depends_on": []},
    {"title": "Plan solution and estimate effort", "stage": "planned", "depends_on": [1]},
    {"title": "Implement / complete the required work", "stage": "in_progress", "depends_on": [2]},
    {"title": "Test calculations, code, or answers", "stage": "reviewed", "depends_on": [3]},
    {"title": "Check explanations, formatting, and references", "stage": "reviewed", "depends_on": [3]},
    {"title": "Verify final file and submit", "stage": "submitted", "depends_on": [4, 5]},
]


def new_workflow(task_id: int, checklist: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    steps = []
    for index, source in enumerate(checklist or DEFAULT_CHECKLIST):
        steps.append({"id": index + 1, "title": str(source.get("title", "Step")),
            "status": "pending", "estimated_minutes": int(source.get("estimated_minutes", 30)),
            "marks": source.get("marks"), "depends_on": list(source.get("depends_on", [])),
            "stage": source.get("stage", "in_progress")})
    return {"task_id": int(task_id), "stage": "received", "checklist": steps,
            "final_file": "", "submission_confirmation": "", "submission_date": None}


def add_checklist_item(workflow: dict[str, Any], title: str, estimated_minutes: int = 30,
                       marks: float | None = None, depends_on: list[int] | None = None) -> dict[str, Any]:
    if not title.strip():
        raise ValueError("Checklist item needs a title.")
    ids = {int(item["id"]) for item in workflow.get("checklist", [])}
    dependencies = depends_on or []
    if any(int(item_id) not in ids for item_id in dependencies):
        raise ValueError("Checklist dependencies must reference existing checklist items.")
    item_id = max(ids, default=0) + 1
    item = {"id": item_id, "title": title.strip(), "status": "pending",
            "estimated_minutes": max(1, int(estimated_minutes)), "marks": marks,
            "depends_on": [int(dep) for dep in dependencies], "stage": "in_progress"}
    workflow.setdefault("checklist", []).append(item)
    return item


def set_checklist_status(workflow: dict[str, Any], item_id: int, status: str) -> dict[str, Any]:
    if status not in {"pending", "in_progress", "completed", "blocked"}:
        raise ValueError("Invalid checklist status.")
    items = workflow.get("checklist", [])
    target = next((item for item in items if int(item["id"]) == int(item_id)), None)
    if target is None:
        raise ValueError("Checklist item not found.")
    if status == "completed":
        completed_ids = {int(item["id"]) for item in items if item.get("status") == "completed"}
        missing = [dep for dep in target.get("depends_on", []) if int(dep) not in completed_ids]
        if missing:
            raise ValueError(f"Complete prerequisite checklist item(s) first: {', '.join(map(str, missing))}.")
    target["status"] = status
    return target


def set_workflow_stage(workflow: dict[str, Any], stage: str, final_file: str = "",
                       confirmation: str = "") -> dict[str, Any]:
    if stage not in STAGES:
        raise ValueError("Unknown assignment workflow stage.")
    current = STAGES.index(workflow.get("stage", "received"))
    target = STAGES.index(stage)
    if target > current + 1:
        raise ValueError("Move through assignment stages one step at a time.")
    if target < current:
        raise ValueError("Assignment workflow stages cannot move backward; update checklist status instead.")
    if target == current + 1:
        unfinished_phase = [item for item in workflow.get("checklist", [])
                            if item.get("stage") == workflow.get("stage")
                            and item.get("status") != "completed"]
        if unfinished_phase:
            raise ValueError("Complete the current-stage checklist before advancing the workflow.")
    if stage == "submitted":
        required = [item for item in workflow.get("checklist", []) if item.get("stage") == "submitted"]
        if required and any(item.get("status") != "completed" for item in required):
            raise ValueError("Complete the submission checklist before marking submitted.")
        if not confirmation.strip():
            raise ValueError("Record a submission confirmation or reference before marking submitted.")
        workflow["submission_date"] = date.today().isoformat()
    workflow["stage"] = stage
    if final_file:
        workflow["final_file"] = final_file.strip()
    if confirmation:
        workflow["submission_confirmation"] = confirmation.strip()
    return workflow

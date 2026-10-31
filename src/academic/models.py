"""Pydantic input models for persisted academic records."""
from __future__ import annotations

from datetime import date, time
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class DeadlineInput(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    due: date | None = None
    due_time: time = time(23, 59)
    task_type: Literal["assignment", "quiz", "laboratory", "project", "examination", "study", "other"] = "assignment"
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    estimated_minutes: int = Field(default=30, ge=1, le=1440)
    difficulty: int = Field(default=3, ge=1, le=5)
    importance: int = Field(default=3, ge=1, le=5)
    percent_complete: float = Field(default=0, ge=0, le=100)
    work_status: Literal["not_started", "in_progress", "reviewed", "submitted"] = "not_started"
    reminder_days: list[int] = Field(default_factory=lambda: [7, 3, 1, 0])

    @field_validator("title")
    @classmethod
    def trim_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Task title cannot be empty.")
        return value.strip()

    @field_validator("reminder_days")
    @classmethod
    def valid_reminder_days(cls, value: list[int]) -> list[int]:
        if any(day < 0 or day > 365 for day in value):
            raise ValueError("Reminder intervals must be between 0 and 365 days.")
        return sorted(set(value), reverse=True)


class ExamInput(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    exam_date: date
    exam_time: time = time(9, 0)
    exam_format: Literal["written", "practical", "oral", "online", "mixed"] = "written"
    study_minutes: int = Field(default=120, ge=15, le=1440)

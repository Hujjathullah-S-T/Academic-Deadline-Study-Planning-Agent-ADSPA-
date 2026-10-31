"""
Assignment 1.2: Rule-Based Environmental Reasoner
Agent: Academic Deadline & Study Planning Agent (ADSPA)

Purpose:
    Demonstrate a simple reflex agent that receives mock environmental
    telemetry, parses the incoming data, checks condition-action rules,
    and logs the actions triggered by the current percept.

This is a rule-based demonstration, not a real calendar or notification service.
Run with: python Assignment_1_2_ADSPA.py
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class Telemetry:
    """Structured sensory data received by the agent for one observation."""
    task_name: str
    hours_until_deadline: float
    completed: bool
    available_study_hours: float
    estimated_study_hours: float


def parse_telemetry(raw: dict) -> Telemetry:
    """
    Parse raw mock sensor data into typed fields.
    In a real system, this could parse calendar, task-manager, or user input data.
    """
    return Telemetry(
        task_name=str(raw["task_name"]),
        hours_until_deadline=float(raw["hours_until_deadline"]),
        completed=str(raw["completed"]).strip().lower() in {"true", "yes", "1"},
        available_study_hours=float(raw["available_study_hours"]),
        estimated_study_hours=float(raw["estimated_study_hours"]),
    )


class AcademicDeadlineStudyPlanningAgent:
    """Simple reflex agent using condition-action rules."""

    def __init__(self) -> None:
        self.action_log: List[str] = []

    def log_action(self, timestamp: str, task: str, action: str) -> None:
        """Save and print the action selected by the rule engine."""
        entry = f"[{timestamp}] ACTION for '{task}': {action}"
        self.action_log.append(entry)
        print(entry)

    def perceive_and_act(self, percept: Telemetry) -> None:
        """
        Apply condition-action rules to the current percept.
        Each observation is evaluated independently, like a simple reflex agent.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(
            f"\nPERCEPT: task='{percept.task_name}', "
            f"deadline_in={percept.hours_until_deadline:g}h, "
            f"completed={percept.completed}, "
            f"available_study_hours={percept.available_study_hours:g}h, "
            f"estimated_study_hours={percept.estimated_study_hours:g}h"
        )

        # Rule 1: Completed tasks should be acknowledged first.
        if percept.completed:
            self.log_action(timestamp, percept.task_name,
                            "Mark task as completed; no reminder needed.")
            return

        # Rule 2: An unfinished task whose deadline has passed is overdue.
        if percept.hours_until_deadline < 0:
            self.log_action(timestamp, percept.task_name,
                            "FLAG OVERDUE: notify the student and review the recovery plan.")
            return

        # Rule 3: An unfinished task due within 24 hours is urgent.
        if percept.hours_until_deadline <= 24:
            self.log_action(timestamp, percept.task_name,
                            "URGENT ALERT: prioritize this task because its deadline is within 24 hours.")

        # Rule 4: If the remaining time available is not enough, suggest rescheduling.
        if percept.available_study_hours < percept.estimated_study_hours:
            self.log_action(timestamp, percept.task_name,
                            "RESCHEDULE: available study time is below the estimated time required.")
            return

        # Rule 5: If the task is not urgent, recommend planning it in advance.
        if percept.hours_until_deadline > 24:
            self.log_action(timestamp, percept.task_name,
                            "PLAN AHEAD: add a study block before the deadline.")

        # If an urgent task has sufficient time, record the next useful action.
        elif percept.hours_until_deadline <= 24:
            self.log_action(timestamp, percept.task_name,
                            "NEXT STEP: begin the task now and check progress after the study block.")


def mock_environmental_stream() -> List[dict]:
    """
    Return a sequence of mock incoming telemetry events.
    Each dictionary represents one new sensory observation from the environment.
    """
    return [
        {
            "task_name": "AI Assignment",
            "hours_until_deadline": 18,
            "completed": False,
            "available_study_hours": 3,
            "estimated_study_hours": 5,
        },
        {
            "task_name": "Database Lab Report",
            "hours_until_deadline": 6,
            "completed": False,
            "available_study_hours": 4,
            "estimated_study_hours": 2,
        },
        {
            "task_name": "NLP Quiz Preparation",
            "hours_until_deadline": 48,
            "completed": False,
            "available_study_hours": 5,
            "estimated_study_hours": 3,
        },
        {
            "task_name": "Python Practical",
            "hours_until_deadline": -3,
            "completed": False,
            "available_study_hours": 2,
            "estimated_study_hours": 2,
        },
        {
            "task_name": "Data Mining Notes",
            "hours_until_deadline": 12,
            "completed": True,
            "available_study_hours": 0,
            "estimated_study_hours": 2,
        },
    ]


def main() -> None:
    """Run the perception–rule evaluation–action loop over mock telemetry."""
    print("=" * 72)
    print("ASSIGNMENT 1.2: RULE-BASED ENVIRONMENTAL REASONER")
    print("Agent: Academic Deadline & Study Planning Agent (ADSPA)")
    print("=" * 72)
    agent = AcademicDeadlineStudyPlanningAgent()

    stream = mock_environmental_stream()
    print(f"\nMock telemetry stream started: {len(stream)} observations received.")

    for index, raw_event in enumerate(stream, start=1):
        print(f"\n--- Incoming telemetry {index}/{len(stream)} ---")
        try:
            percept = parse_telemetry(raw_event)
            agent.perceive_and_act(percept)
        except (KeyError, TypeError, ValueError) as error:
            # Defensive handling for malformed or incomplete incoming data.
            print(f"SENSORY PARSING ERROR: event skipped ({error}).")

    print("\n" + "=" * 72)
    print(f"RUN COMPLETE: {len(stream)} observations processed.")
    print(f"Reactive actions logged: {len(agent.action_log)}")
    print("Execution log contains each condition-action response shown above.")
    print("=" * 72)


if __name__ == "__main__":
    main()

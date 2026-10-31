"""
Assignment 4.1 — Belief-Desire-Intention (BDI) Goal-Driven Modeling
Agent: Academic Deadline & Study Planning Agent (ADSPA)

Demonstrates:
- Separate Belief, Desire, and Intention objects
- Goal state transitions
- Belief-update event handling
- Dynamic plan recalculation during execution
- Verification that an unexpected belief update changes the active intention
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import json


class GoalStatus(str, Enum):
    INACTIVE = "INACTIVE"
    ACTIVE = "ACTIVE"
    ACHIEVED = "ACHIEVED"
    BLOCKED = "BLOCKED"
    ABANDONED = "ABANDONED"


@dataclass
class Belief:
    """A fact currently believed by the agent."""
    key: str
    value: Any
    source: str = "environment"
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class Desire:
    """A high-level goal the agent would like to achieve."""
    goal_id: str
    description: str
    priority: int
    success_condition: str
    status: GoalStatus = GoalStatus.INACTIVE


@dataclass
class Intention:
    """An adopted procedural plan for pursuing one desire."""
    intention_id: str
    goal_id: str
    plan_name: str
    steps: List[str]
    current_step: int = 0
    active: bool = True
    rationale: str = ""

    @property
    def next_action(self) -> Optional[str]:
        if not self.active or self.current_step >= len(self.steps):
            return None
        return self.steps[self.current_step]

    def advance(self) -> Optional[str]:
        if self.next_action is None:
            self.active = False
            return None
        completed = self.steps[self.current_step]
        self.current_step += 1
        if self.current_step >= len(self.steps):
            self.active = False
        return completed


class ADSPABDI:
    """A compact BDI controller for academic deadline and study planning."""

    def __init__(self):
        # BDI architecture separation: three independent collections.
        self.beliefs: Dict[str, Belief] = {
            "deadline_hours": Belief("deadline_hours", 8, "initial_state"),
            "estimated_study_hours": Belief("estimated_study_hours", 5, "initial_state"),
            "library_available": Belief("library_available", True, "initial_state"),
            "internet_available": Belief("internet_available", True, "initial_state"),
            "assignment_completed": Belief("assignment_completed", False, "initial_state"),
        }
        self.desires: Dict[str, Desire] = {
            "finish_assignment": Desire(
                "finish_assignment", "Complete the assignment before its deadline",
                priority=10, success_condition="assignment_completed == True"
            ),
            "secure_study_resources": Desire(
                "secure_study_resources", "Secure suitable study resources",
                priority=5, success_condition="library_available or internet_available"
            ),
            "avoid_late_submission": Desire(
                "avoid_late_submission", "Avoid submitting after the deadline",
                priority=9, success_condition="deadline_hours > 0"
            ),
        }
        self.intentions: List[Intention] = []
        self.active_intention: Optional[Intention] = None
        self.event_log: List[Dict[str, Any]] = []
        self._intention_counter = 0
        self.recalculate_plan(reason="initialization")

    def log(self, event: str, **details):
        record = {"event": event, "details": details}
        self.event_log.append(record)
        print(f"[{event}] " + json.dumps(details, sort_keys=True))

    def belief_value(self, key: str):
        return self.beliefs[key].value

    def update_belief(self, key: str, value: Any, source: str = "environment"):
        old_value = self.belief_value(key) if key in self.beliefs else None
        self.beliefs[key] = Belief(key, value, source)
        self.log("BELIEF_UPDATE", key=key, old_value=old_value, new_value=value, source=source)
        # Belief revision is the trigger for reconsidering adopted intentions.
        self.recalculate_plan(reason=f"belief changed: {key}")

    def _feasible_plans(self):
        deadline = self.belief_value("deadline_hours")
        study_hours = self.belief_value("estimated_study_hours")
        library = self.belief_value("library_available")
        internet = self.belief_value("internet_available")
        completed = self.belief_value("assignment_completed")

        if completed:
            return [("finish_assignment", "completion_verified", ["Verify submission receipt"],
                     "The assignment is already marked complete.")]
        if deadline <= 0:
            return [("avoid_late_submission", "deadline_recovery", [
                "Check whether a late-submission exception is available",
                "Notify the student and record the deadline risk"
            ], "Deadline has passed; recovery and transparent notification take priority.")]

        if study_hours > deadline:
            if library or internet:
                resource = "library" if library else "online resources"
                return [("finish_assignment", "deadline_triage", [
                    f"Use available {resource} to identify the highest-value requirements",
                    "Complete the highest-mark sections first",
                    "Submit the best complete work before the deadline"
                ], f"Estimated work ({study_hours}h) exceeds time remaining ({deadline}h); prioritize deliverable completion.")]
            return [("secure_study_resources", "resource_recovery", [
                "Find an offline copy of the assignment instructions",
                "Use locally available notes and materials",
                "Notify the student that external study resources are unavailable"
            ], "Time is short and both library and internet access are unavailable.")]

        if library:
            return [("finish_assignment", "library_study_plan", [
                "Open the assignment brief and rubric",
                "Reserve a focused library study block",
                "Complete the required work",
                "Check the rubric and submit"
            ], "Library access is available and the estimated work fits the deadline.")]
        if internet:
            return [("finish_assignment", "online_study_plan", [
                "Open course materials and the assignment rubric online",
                "Create a focused work session",
                "Complete the required work",
                "Check the rubric and submit"
            ], "Library is unavailable, so the plan uses online materials.")]
        return [("secure_study_resources", "offline_recovery_plan", [
            "Locate downloaded course notes and assignment files",
            "Use offline materials to continue the assignment",
            "Contact the course instructor if required information is missing"
        ], "Neither library nor internet is available; switch to an offline recovery plan.")]

    def recalculate_plan(self, reason: str):
        old = self.active_intention
        plans = self._feasible_plans()
        goal_id, plan_name, steps, rationale = plans[0]

        # Update goal states, keeping achieved goals achieved when supported by beliefs.
        for desire in self.desires.values():
            if desire.goal_id == goal_id:
                desire.status = GoalStatus.ACTIVE
            elif desire.goal_id == "finish_assignment" and self.belief_value("assignment_completed"):
                desire.status = GoalStatus.ACHIEVED
            elif desire.goal_id == "avoid_late_submission" and self.belief_value("deadline_hours") <= 0:
                desire.status = GoalStatus.BLOCKED
            elif desire.status not in (GoalStatus.ACHIEVED, GoalStatus.BLOCKED):
                desire.status = GoalStatus.INACTIVE

        if old and old.active:
            old.active = False
            self.log("INTENTION_SUSPENDED", intention_id=old.intention_id,
                     old_plan=old.plan_name, reason=reason)

        self._intention_counter += 1
        new = Intention(
            intention_id=f"INT-{self._intention_counter:03d}",
            goal_id=goal_id,
            plan_name=plan_name,
            steps=steps,
            current_step=0,
            active=True,
            rationale=rationale,
        )
        self.intentions.append(new)
        self.active_intention = new
        self.log("PLAN_RECALCULATED", reason=reason, selected_goal=goal_id,
                 plan_name=plan_name, rationale=rationale, steps=steps)
        self.log("INTENTION_ADOPTED", intention_id=new.intention_id,
                 goal_id=goal_id, plan_name=plan_name, next_action=new.next_action)

    def execute_next_step(self):
        intention = self.active_intention
        if intention is None or not intention.active:
            self.log("NO_ACTIVE_INTENTION")
            return None
        action = intention.next_action
        completed = intention.advance()
        self.log("STEP_EXECUTED", intention_id=intention.intention_id,
                 action=completed, next_action=intention.next_action,
                 still_active=intention.active)
        return action

    def snapshot(self):
        return {
            "beliefs": {k: {"value": v.value, "source": v.source} for k, v in self.beliefs.items()},
            "desires": {k: {"description": v.description, "priority": v.priority,
                            "status": v.status.value} for k, v in self.desires.items()},
            "active_intention": None if self.active_intention is None else {
                "id": self.active_intention.intention_id,
                "goal_id": self.active_intention.goal_id,
                "plan_name": self.active_intention.plan_name,
                "steps": self.active_intention.steps,
                "current_step": self.active_intention.current_step,
                "active": self.active_intention.active,
            }
        }


def run_verification():
    print("=== ADSPA BDI Verification Run ===")
    agent = ADSPABDI()
    initial_plan = agent.active_intention.plan_name
    print(f"INITIAL_PLAN={initial_plan}")
    agent.execute_next_step()

    print("\n--- Unexpected environmental update: library becomes unavailable ---")
    agent.update_belief("library_available", False, source="unexpected_environment_event")
    shifted_plan = agent.active_intention.plan_name
    print(f"SHIFTED_PLAN={shifted_plan}")
    print(f"INTENTION_SHIFT_VERIFIED={initial_plan != shifted_plan}")
    assert initial_plan != shifted_plan, "Expected the agent to switch plans after belief update."
    assert shifted_plan == "online_study_plan", f"Unexpected shifted plan: {shifted_plan}"

    print("\n--- Second update: internet also becomes unavailable ---")
    agent.update_belief("internet_available", False, source="unexpected_environment_event")
    offline_plan = agent.active_intention.plan_name
    print(f"OFFLINE_PLAN={offline_plan}")
    assert offline_plan == "offline_recovery_plan"

    print("\n--- Deadline becomes shorter than estimated work ---")
    agent.update_belief("deadline_hours", 2, source="deadline_change")
    triage_plan = agent.active_intention.plan_name
    print(f"TRIAGE_PLAN={triage_plan}")
    assert triage_plan == "resource_recovery" or triage_plan == "deadline_triage"

    print("\n--- Assignment is marked completed ---")
    agent.update_belief("assignment_completed", True, source="student_confirmation")
    final_plan = agent.active_intention.plan_name
    print(f"FINAL_PLAN={final_plan}")
    assert final_plan == "completion_verified"

    print("\n=== VERIFICATION SUMMARY ===")
    print(f"Initial plan: {initial_plan}")
    print(f"After library outage: {shifted_plan}")
    print(f"After internet outage: {offline_plan}")
    print(f"After deadline change: {triage_plan}")
    print(f"After completion update: {final_plan}")
    print(f"Belief records: {len(agent.beliefs)}")
    print(f"Desire records: {len(agent.desires)}")
    print(f"Intentions created: {len(agent.intentions)}")
    print("ALL_ASSERTIONS_PASSED=True")
    return agent


if __name__ == "__main__":
    run_verification()

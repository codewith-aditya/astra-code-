"""Planning module — generates step-by-step execution plans."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PlanStep:
    """A single step in an execution plan."""

    action: str          # e.g. "read", "edit", "search", "run"
    target: str          # file path or command
    description: str     # what this step accomplishes
    completed: bool = False


@dataclass
class Plan:
    """An ordered execution plan."""

    goal: str
    steps: list[PlanStep] = field(default_factory=list)

    def add_step(self, action: str, target: str, description: str) -> None:
        self.steps.append(PlanStep(action=action, target=target, description=description))

    def mark_complete(self, index: int) -> None:
        if 0 <= index < len(self.steps):
            self.steps[index].completed = True

    @property
    def progress(self) -> str:
        done = sum(1 for s in self.steps if s.completed)
        return f"{done}/{len(self.steps)} steps completed"

    def summary(self) -> str:
        lines = [f"Plan: {self.goal}", f"Progress: {self.progress}", ""]
        for i, step in enumerate(self.steps, 1):
            check = "x" if step.completed else " "
            lines.append(f"  [{check}] {i}. [{step.action}] {step.description}")
            if step.target:
                lines.append(f"       -> {step.target}")
        return "\n".join(lines)


class Planner:
    """Creates and manages execution plans.

    Plans are informational — the agent controller uses them as guidance,
    but the LLM drives the actual tool calls.
    """

    def __init__(self) -> None:
        self.current_plan: Plan | None = None

    def create_plan(self, goal: str) -> Plan:
        """Start a new plan."""
        self.current_plan = Plan(goal=goal)
        return self.current_plan

    def get_plan(self) -> Plan | None:
        return self.current_plan

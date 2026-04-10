from __future__ import annotations

from dataclasses import dataclass

from openpm_env.models import PMState


from pydantic import BaseModel

class RewardBreakdown(BaseModel):
    progress: float = 0.0
    prioritization: float = 0.0
    blocker_resolution: float = 0.0
    idle_penalty: float = 0.0
    invalid_penalty: float = 0.0
    deadline_penalty: float = 0.0
    completion_bonus: float = 0.0
    blocker_penalty: float = 0.0

    @property
    def total(self) -> float:
        return (
            self.progress
            + self.prioritization
            + self.blocker_resolution
            - self.idle_penalty
            - self.invalid_penalty
            - self.deadline_penalty
            + self.completion_bonus
            - self.blocker_penalty
        )


def compute_reward(
    *,
    state: PMState,
    previous_progress: float,
    invalid_action: bool,
    helped_blocker: bool,
    good_prioritization: bool,
) -> RewardBreakdown:
    breakdown = RewardBreakdown()

    progress_delta = max(0.0, state.sprint_progress - previous_progress)
    breakdown.progress = round(progress_delta * 0.6, 4)

    if good_prioritization:
        breakdown.prioritization = 0.01
    if helped_blocker:
        breakdown.blocker_resolution = 0.02

    active_blockers_count = sum(1 for t in state.tasks if t.blocked and t.status != "completed")
    breakdown.blocker_penalty = min(0.4, active_blockers_count * 0.1)

    if invalid_action:
        breakdown.invalid_penalty = 0.5

    idle_count = sum(
        1
        for developer in state.developers
        if developer.assigned_task_id is None
        and any(task.status != "completed" for task in state.tasks)
    )
    breakdown.idle_penalty = min(0.2, idle_count * 0.1)

    overdue_count = sum(
        1
        for task in state.tasks
        if task.status != "completed" and state.day > task.due_day
    )
    breakdown.deadline_penalty = min(0.4, overdue_count * 0.1)

    if state.project_completed and not state.project_failed:
        breakdown.completion_bonus = 0.4

    return breakdown

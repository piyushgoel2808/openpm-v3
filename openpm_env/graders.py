from __future__ import annotations

from typing import List

from openpm_env.models import PMState, TaskSnapshot
from openpm_env.utils import safe_score


def _count_completed(tasks: List[TaskSnapshot]) -> int:
    return sum(1 for task in tasks if task.status == "completed")


def _deadline_penalty(state: PMState) -> float:
    overdue = sum(1 for task in state.tasks if task.status != "completed" and state.day > task.due_day)
    return min(0.4, overdue * 0.06)


def grade_state(state: PMState) -> float:
    total_tasks = max(1, len(state.tasks))
    completed_ratio = _count_completed(state.tasks) / total_tasks
    progress_signal = state.sprint_progress
    invalid_penalty = min(0.25, state.invalid_action_count * 0.03)
    risk_penalty = min(0.2, state.risk_level * 0.2)
    score = (
        0.6 * completed_ratio
        + 0.4 * progress_signal
        - _deadline_penalty(state)
        - invalid_penalty
        - risk_penalty
    )
    if state.project_completed and not state.project_failed:
        score += 0.2
    return safe_score(score)


def grade_easy(state: PMState) -> float:
    return safe_score(grade_state(state))


def grade_medium(state: PMState) -> float:
    return safe_score(grade_state(state))


def grade_hard(state: PMState) -> float:
    return safe_score(grade_state(state))


def grade_for_task(task_id: str, state: PMState) -> float:
    task_id = task_id.lower()
    if task_id == "easy":
        return safe_score(grade_easy(state))
    if task_id == "medium":
        return safe_score(grade_medium(state))
    if task_id == "hard":
        return safe_score(grade_hard(state))
    raise ValueError(f"Unknown task_id: {task_id}")

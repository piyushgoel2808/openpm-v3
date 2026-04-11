from __future__ import annotations

from typing import List

from openpm_env.models import PMState, TaskSnapshot
from openpm_env.utils import safe_score


def _clamp01(value: float) -> float:
    return safe_score(value)


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
    grade = safe_score(score)
    print(f"DEBUG GRADER - GRADE: {grade}, TYPE: {type(grade)}")
    return grade


def grade_easy(state: PMState) -> float:
    grade = safe_score(grade_state(state))
    print(f"DEBUG GRADER - GRADE: {grade}, TYPE: {type(grade)}")
    return grade


def grade_medium(state: PMState) -> float:
    grade = safe_score(grade_state(state))
    print(f"DEBUG GRADER - GRADE: {grade}, TYPE: {type(grade)}")
    return grade


def grade_hard(state: PMState) -> float:
    grade = safe_score(grade_state(state))
    print(f"DEBUG GRADER - GRADE: {grade}, TYPE: {type(grade)}")
    return grade


def grade_for_task(task_id: str, state: PMState) -> float:
    task_id = task_id.lower()
    if task_id == "easy":
        grade = safe_score(grade_easy(state))
        print(f"DEBUG GRADER - GRADE: {grade}, TYPE: {type(grade)}")
        return grade
    if task_id == "medium":
        grade = safe_score(grade_medium(state))
        print(f"DEBUG GRADER - GRADE: {grade}, TYPE: {type(grade)}")
        return grade
    if task_id == "hard":
        grade = safe_score(grade_hard(state))
        print(f"DEBUG GRADER - GRADE: {grade}, TYPE: {type(grade)}")
        return grade
    raise ValueError(f"Unknown task_id: {task_id}")

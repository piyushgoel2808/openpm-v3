from __future__ import annotations

import random
from collections import defaultdict
from functools import lru_cache
from typing import Dict, Iterable, List, Optional

from openpm_env.models import PMAction, PMObservation, TaskSnapshot


PRIORITY_RANK: Dict[str, int] = {"low": 1, "medium": 2, "high": 3, "critical": 4}


class BaseAgent:
    def step(self, obs: PMObservation) -> PMAction:
        raise NotImplementedError


def _unfinished_tasks(obs: PMObservation) -> List[TaskSnapshot]:
    return [task for task in obs.active_tasks if task.status != "completed"]


def _ready_tasks(obs: PMObservation) -> List[TaskSnapshot]:
    completed = {task.task_id for task in obs.active_tasks if task.status == "completed"}
    return [
        task
        for task in obs.active_tasks
        if task.status != "completed" and not any(dep not in completed for dep in task.dependencies)
    ]


def _available_developers(obs: PMObservation) -> List[str]:
    return sorted(dev_id for dev_id, available in obs.developer_availability.items() if available)


def _best_developer_for_task(obs: PMObservation, task: TaskSnapshot) -> Optional[str]:
    available = _available_developers(obs)
    if not available:
        return None

    return max(
        available,
        key=lambda developer_id: (
            obs.developer_skill_levels.get(developer_id, {}).get(task.domain, 0.0),
            developer_id,
        ),
    )


def _critical_path_scores(tasks: Iterable[TaskSnapshot]) -> Dict[str, float]:
    task_list = list(tasks)
    task_map = {task.task_id: task for task in task_list}
    downstream: Dict[str, List[TaskSnapshot]] = defaultdict(list)

    for task in task_list:
        for dependency in task.dependencies:
            downstream[dependency].append(task)

    @lru_cache(maxsize=None)
    def score(task_id: str) -> float:
        task = task_map[task_id]
        children = downstream.get(task_id, [])
        if not children:
            return float(task.effort_remaining)
        return float(task.effort_remaining) + max(score(child.task_id) for child in children)

    return {task.task_id: score(task.task_id) for task in task_list}


def _sort_key(task: TaskSnapshot, criticality: Dict[str, float]) -> tuple[float, int, int, str]:
    return (
        criticality.get(task.task_id, 0.0),
        PRIORITY_RANK.get(task.priority, 0),
        -task.due_day,
        task.task_id,
    )


class RandomAgent(BaseAgent):
    def __init__(self, seed: Optional[int] = None):
        self._rng = random.Random(42 if seed is None else seed)

    def step(self, obs: PMObservation) -> PMAction:
        tasks = _unfinished_tasks(obs)
        if not tasks:
            return PMAction(action_type="mark_complete", task_id=obs.active_tasks[0].task_id)

        task = self._rng.choice(tasks)
        options: List[PMAction] = [PMAction(action_type="delay_task", task_id=task.task_id)]

        if task.effort_remaining <= 0.2:
            options.append(PMAction(action_type="mark_complete", task_id=task.task_id))

        if task.effort_remaining > 1.2:
            options.append(PMAction(action_type="split_task", task_id=task.task_id))

        if task.assigned_to is None and not task.blocked:
            developer_id = _best_developer_for_task(obs, task)
            if developer_id is not None:
                options.append(PMAction(action_type="assign_task", task_id=task.task_id, developer_id=developer_id))

        if task.blocked and bool(task.metadata.get("dynamic_blocked", False)):
            available = _available_developers(obs)
            if available:
                options.append(
                    PMAction(
                        action_type="request_help",
                        task_id=task.task_id,
                        helper_developer_id=self._rng.choice(available),
                    )
                )

        if task.priority != "critical":
            options.append(
                PMAction(
                    action_type="reprioritize_task",
                    task_id=task.task_id,
                    priority=self._rng.choice(["medium", "high", "critical"]),
                )
            )

        return self._rng.choice(options)


class GreedyAgent(BaseAgent):
    def step(self, obs: PMObservation) -> PMAction:
        tasks = _unfinished_tasks(obs)
        if not tasks:
            return PMAction(action_type="mark_complete", task_id=obs.active_tasks[0].task_id)

        ready_tasks = [task for task in _ready_tasks(obs) if task.assigned_to is None]
        if ready_tasks:
            ready_tasks.sort(key=lambda task: (-PRIORITY_RANK.get(task.priority, 0), task.due_day, task.task_id))
            target = ready_tasks[0]
            developer_id = _best_developer_for_task(obs, target)
            if developer_id is not None:
                return PMAction(action_type="assign_task", task_id=target.task_id, developer_id=developer_id)

        nearly_done = sorted(
            (task for task in tasks if task.effort_remaining <= 0.2),
            key=lambda task: (task.due_day, task.task_id),
        )
        if nearly_done:
            return PMAction(action_type="mark_complete", task_id=nearly_done[0].task_id)

        if tasks:
            target = sorted(tasks, key=lambda task: (task.due_day, task.task_id))[0]
            if target.priority != "critical":
                return PMAction(action_type="reprioritize_task", task_id=target.task_id, priority="critical")

        return PMAction(action_type="delay_task", task_id=tasks[0].task_id)


class AdvancedRuleBasedAgent(BaseAgent):
    def step(self, obs: PMObservation) -> PMAction:
        tasks = _unfinished_tasks(obs)
        if not tasks:
            return PMAction(action_type="mark_complete", task_id=obs.active_tasks[0].task_id)

        criticality = _critical_path_scores(tasks)
        ready_tasks = [task for task in _ready_tasks(obs) if task.assigned_to is None]
        is_hard = obs.scenario_id == "hard"

        if is_hard:
            dynamic_blockers = [
                task
                for task in tasks
                if task.blocked and bool(task.metadata.get("dynamic_blocked", False)) and task.due_day <= obs.day + 1
            ]
            if dynamic_blockers:
                dynamic_blockers.sort(key=lambda task: (task.due_day, -criticality.get(task.task_id, 0.0), task.task_id))
                helper_id = _available_developers(obs)
                if helper_id:
                    target = dynamic_blockers[0]
                    return PMAction(
                        action_type="request_help",
                        task_id=target.task_id,
                        helper_developer_id=helper_id[0],
                    )

            if ready_tasks:
                ready_tasks.sort(key=lambda task: (task.due_day, -criticality.get(task.task_id, 0.0), task.task_id))
                target = ready_tasks[0]
                developer_id = _best_developer_for_task(obs, target)
                if developer_id is not None and target.due_day <= obs.day + 1:
                    return PMAction(action_type="assign_task", task_id=target.task_id, developer_id=developer_id)

            nearly_done = sorted(
                (task for task in tasks if task.effort_remaining <= 0.35),
                key=lambda task: (task.due_day, -criticality.get(task.task_id, 0.0), task.task_id),
            )
            if nearly_done:
                return PMAction(action_type="mark_complete", task_id=nearly_done[0].task_id)

            return PMAction(action_type="delay_task", task_id=min(tasks, key=lambda task: (task.due_day, task.task_id)).task_id)

        dynamic_blockers = [
            task for task in tasks if task.blocked and bool(task.metadata.get("dynamic_blocked", False))
        ]
        if dynamic_blockers:
            dynamic_blockers.sort(key=lambda task: (task.due_day, -criticality.get(task.task_id, 0.0), task.task_id))
            target = dynamic_blockers[0]
            helper_id = _best_developer_for_task(obs, target)
            if helper_id is not None:
                return PMAction(
                    action_type="request_help",
                    task_id=target.task_id,
                    helper_developer_id=helper_id,
                )

        if ready_tasks:
            ready_tasks.sort(key=lambda task: (task.due_day, -criticality.get(task.task_id, 0.0), task.task_id))
            target = ready_tasks[0]
            developer_id = _best_developer_for_task(obs, target)
            if developer_id is not None:
                return PMAction(action_type="assign_task", task_id=target.task_id, developer_id=developer_id)

        support_candidates = sorted(
            (task for task in tasks if task.effort_remaining > 0.8),
            key=lambda task: (task.due_day, -criticality.get(task.task_id, 0.0), task.task_id),
        )
        if support_candidates:
            helper_id = _available_developers(obs)
            if helper_id:
                target = support_candidates[0]
                return PMAction(
                    action_type="request_help",
                    task_id=target.task_id,
                    helper_developer_id=helper_id[0],
                )

        nearly_done = sorted(
            (task for task in tasks if task.effort_remaining <= 0.35),
            key=lambda task: (task.due_day, -criticality.get(task.task_id, 0.0), task.task_id),
        )
        if nearly_done:
            return PMAction(action_type="mark_complete", task_id=nearly_done[0].task_id)

        urgent_reprioritizations = sorted(
            (
                task
                for task in tasks
                if task.priority != "critical" and obs.day + 1 >= task.due_day
            ),
            key=lambda task: (task.due_day, -criticality.get(task.task_id, 0.0), task.task_id),
        )
        if urgent_reprioritizations:
            target = urgent_reprioritizations[0]
            return PMAction(action_type="reprioritize_task", task_id=target.task_id, priority="critical")

        best_task = min(tasks, key=lambda task: (task.due_day, -criticality.get(task.task_id, 0.0), task.task_id))
        return PMAction(action_type="delay_task", task_id=best_task.task_id)

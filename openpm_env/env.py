from __future__ import annotations

import uuid
import random
from typing import Any, Dict, Optional

from openenv.core.env_server.interfaces import Environment
from pydantic import ValidationError

from openpm_env.graders import grade_for_task
from openpm_env.models import (
    PMAction,
    PMObservation,
    PMState,
    TaskSnapshot,
    DeveloperSnapshot,
)
from openpm_env.reward import compute_reward
from openpm_env.tasks.scenarios import SCENARIOS, ScenarioSpec

PRIORITY_WEIGHT: Dict[str, float] = {
    "low": 0.25,
    "medium": 0.5,
    "high": 0.75,
    "critical": 1.0,
}


class OpenPMEnvironment(Environment[PMAction, PMObservation, PMState]):
    """Deterministic software sprint management simulation."""

    def __init__(self):
        self._state = PMState()
        self._event_log: list[str] = []

    def reset(
        self,
        seed: Optional[int] = None,
        episode_id: Optional[str] = None,
        **kwargs: Any,
    ) -> PMObservation:
        self.rng = random.Random(seed if seed is not None else 42)
        scenario_id = str(kwargs.get("task_id", "easy")).lower()
        if scenario_id not in SCENARIOS:
            scenario_id = "easy"

        scenario = SCENARIOS[scenario_id]
        self._state = self._build_initial_state(scenario, episode_id)
        self._state.score = grade_for_task(self._state.scenario_id, self._state)
        self._event_log = [f"reset:{scenario_id}"]

        return self._build_observation(reward=0.0, done=False)

    def step(
        self,
        action: PMAction | Dict[str, Any],
        timeout_s: Optional[float] = None,
        **kwargs: Any,
    ) -> PMObservation:
        if self._state.project_completed or self._state.project_failed:
            self._event_log.append("step_ignored:terminal_state")
            return self._build_observation(reward=0.0, done=True)

        previous_progress = self._state.sprint_progress
        invalid_action = False
        helped_blocker = False
        good_prioritization = False

        parsed_action: PMAction | None = None
        validation_error: Optional[str] = None

        try:
            if isinstance(action, PMAction):
                parsed_action = action
            else:
                parsed_action = PMAction.model_validate(action)
        except ValidationError:
            validation_error = "action_validation_error"

        if validation_error is None and parsed_action is not None:
            validation_error = self._validate_action(parsed_action)

        if validation_error is not None:
            invalid_action = True
            self._state.invalid_action_count += 1
            self._event_log.append(f"invalid:{validation_error}")
        else:
            helped_blocker, good_prioritization = self._apply_action(parsed_action)

        self._state.step_count += 1
        self._state.day += 1
        self._inject_dynamic_blockers()
        self._apply_stochastic_risk()
        self._advance_work()
        self._refresh_task_flags()
        self._update_progress_risk_and_terminal()

        reward_breakdown = compute_reward(
            state=self._state,
            previous_progress=previous_progress,
            invalid_action=invalid_action,
            helped_blocker=helped_blocker,
            good_prioritization=good_prioritization,
        )
        reward = round(reward_breakdown.total, 4)

        self._state.score = grade_for_task(self._state.scenario_id, self._state)

        done = self._state.project_completed or self._state.project_failed
        obs = self._build_observation(reward=reward, done=done)
        obs.metadata["reward_breakdown"] = reward_breakdown.model_dump()
        return obs

    @property
    def state(self) -> PMState:
        return self._state

    def _build_initial_state(self, scenario: ScenarioSpec, episode_id: Optional[str]) -> PMState:
        tasks = [
            TaskSnapshot(
                task_id=seed.task_id,
                title=seed.title,
                priority=seed.priority,
                domain=seed.domain,
                dependencies=list(seed.dependencies),
                blocked=False,
                assigned_to=None,
                effort_total=seed.effort_total,
                effort_remaining=seed.effort_total,
                due_day=seed.due_day,
                status="todo",
            )
            for seed in scenario.tasks
        ]
        developers = [
            DeveloperSnapshot(
                developer_id=seed.developer_id,
                available=True,
                assigned_task_id=None,
                busy_until_day=0,
                skill_profile=dict(seed.skill_profile),
            )
            for seed in scenario.developers
        ]
        state = PMState(
            episode_id=episode_id or str(uuid.uuid4()),
            scenario_id=scenario.scenario_id,
            day=0,
            max_days=scenario.max_days,
            step_count=0,
            sprint_progress=0.0,
            risk_level=0.0,
            time_remaining=scenario.max_days,
            project_completed=False,
            project_failed=False,
            invalid_action_count=0,
            score=0.01,
            developers=developers,
            tasks=tasks,
        )
        self._refresh_task_flags(state)
        return state

    def _refresh_task_flags(self, state: Optional[PMState] = None) -> None:
        working_state = state or self._state
        completed = {task.task_id for task in working_state.tasks if task.status == "completed"}
        for task in working_state.tasks:
            if task.status == "completed":
                task.blocked = False
                continue
            dependency_blocked = any(dep not in completed for dep in task.dependencies)
            dynamic_blocked = "dynamic_blocked" in task.metadata and bool(task.metadata["dynamic_blocked"])
            task.blocked = dependency_blocked or dynamic_blocked
            if task.status == "todo" and task.assigned_to is not None and not task.blocked:
                task.status = "in_progress"

    def _validate_action(self, action: PMAction) -> Optional[str]:
        if action.action_type not in {
            "assign_task",
            "reprioritize_task",
            "split_task",
            "request_help",
            "delay_task",
            "mark_complete",
        }:
            return "unknown_action_type"

        if action.action_type in {"assign_task", "reprioritize_task", "split_task", "request_help", "delay_task", "mark_complete"} and not action.task_id:
            return "task_id_required"

        if action.action_type == "request_help":
            if not action.helper_developer_id:
                return "helper_developer_id_required"
            helper = self._get_developer(action.helper_developer_id)
            if helper is None:
                return "helper_not_found"
            if not helper.available:
                return "helper_busy"

        if action.action_type == "assign_task" and not action.developer_id:
            return "developer_id_required"

        if action.action_type == "reprioritize_task" and not action.priority:
            return "priority_required"

        task = self._get_task(action.task_id) if action.task_id else None
        if action.task_id and task is None:
            return "task_not_found"

        if task and task.status == "completed" and action.action_type != "delay_task":
            return "task_already_completed"

        if action.action_type == "assign_task":
            developer = self._get_developer(action.developer_id)
            if developer is None:
                return "developer_not_found"
            if developer.assigned_task_id is not None:
                return "developer_busy"
            if task is not None and task.blocked:
                return "task_blocked"

        if action.action_type == "mark_complete" and task is not None and task.effort_remaining > 0.2:
            return "task_not_ready_for_completion"

        if action.action_type == "request_help" and task is not None and not task.blocked:
            return "task_not_blocked"

        return None

    def _apply_action(self, action: PMAction) -> tuple[bool, bool]:
        helped_blocker = False
        good_prioritization = False

        task = self._get_task(action.task_id) if action.task_id else None
        if task is None:
            return helped_blocker, good_prioritization

        if action.action_type == "assign_task":
            developer = self._get_developer(action.developer_id)
            if developer is not None:
                developer.assigned_task_id = task.task_id
                developer.available = False
                task.assigned_to = developer.developer_id
                if task.status == "todo" and not task.blocked:
                    task.status = "in_progress"
                self._event_log.append(f"assign:{task.task_id}:{developer.developer_id}")
                if task.priority in {"high", "critical"}:
                    good_prioritization = True

        elif action.action_type == "reprioritize_task" and action.priority is not None:
            previous = task.priority
            task.priority = action.priority
            good_prioritization = self._is_good_reprioritization(task, previous)
            self._event_log.append(f"reprioritize:{task.task_id}:{previous}->{action.priority}")

        elif action.action_type == "split_task":
            self._split_task(task)
            self._event_log.append(f"split:{task.task_id}")

        elif action.action_type == "request_help":
            helper = self._get_developer(action.helper_developer_id)
            if helper is not None:
                helper.available = False
                helper.busy_until_day = self._state.day + 1
            if task.metadata.get("dynamic_blocked"):
                task.metadata["dynamic_blocked"] = False
            task.blocked = False
            helped_blocker = True
            self._event_log.append(f"help:{task.task_id}:{action.helper_developer_id}")

        elif action.action_type == "delay_task":
            task.due_day += 1
            self._event_log.append(f"delay:{task.task_id}")

        elif action.action_type == "mark_complete":
            task.effort_remaining = 0.0
            task.status = "completed"
            self._release_developer(task.assigned_to)
            task.assigned_to = None
            self._event_log.append(f"complete:{task.task_id}")

        return helped_blocker, good_prioritization

    def _split_task(self, task: TaskSnapshot) -> None:
        if task.effort_remaining <= 1.2:
            return
        split_effort = round(task.effort_remaining / 2.0, 2)
        task.effort_remaining = split_effort
        task.effort_total = max(task.effort_total, split_effort)

        child_id = f"{task.task_id}_split"
        if self._get_task(child_id) is not None:
            return

        child_task = TaskSnapshot(
            task_id=child_id,
            title=f"{task.title} (split)",
            priority=task.priority,
            domain=task.domain,
            dependencies=list(task.dependencies),
            blocked=False,
            assigned_to=None,
            effort_total=split_effort,
            effort_remaining=split_effort,
            due_day=task.due_day,
            status="todo",
        )
        self._state.tasks.append(child_task)

    def _inject_dynamic_blockers(self) -> None:
        scenario = SCENARIOS[self._state.scenario_id]
        blocking_tasks = scenario.blocker_schedule.get(self._state.day, [])
        for task_id in blocking_tasks:
            task = self._get_task(task_id)
            if task is not None and task.status != "completed":
                task.metadata["dynamic_blocked"] = True
                task.blocked = True
                self._event_log.append(f"blocked:{task.task_id}")

    def _apply_stochastic_risk(self) -> None:
        if not hasattr(self, "rng"):
            self.rng = random.Random(42)
        for task in self._state.tasks:
            if task.status == "in_progress" and not task.blocked:
                if self.rng.random() < 0.10:
                    if self.rng.choice(["delay", "block"]) == "delay":
                        task.effort_remaining += 1.0
                        task.effort_total += 1.0
                        self._event_log.append(f"risk_delay:{task.task_id}")
                    else:
                        task.metadata["dynamic_blocked"] = True
                        task.blocked = True
                        self._event_log.append(f"risk_blocked:{task.task_id}")

    def _advance_work(self) -> None:
        for developer in self._state.developers:
            if developer.busy_until_day >= self._state.day and developer.assigned_task_id is None:
                developer.available = False
                continue

            if developer.assigned_task_id is None:
                developer.available = True
                continue

            task = self._get_task(developer.assigned_task_id)
            if task is None or task.status == "completed":
                developer.assigned_task_id = None
                developer.available = True
                continue

            if task.blocked:
                developer.available = False
                continue

            skill = developer.skill_profile.get(task.domain, 0.4)
            priority_boost = PRIORITY_WEIGHT.get(task.priority, 0.5) * 0.2
            progress = round(0.5 * skill + priority_boost, 3)
            task.effort_remaining = max(0.0, round(task.effort_remaining - progress, 3))
            if task.effort_remaining <= 0.0:
                task.status = "completed"
                self._release_developer(developer.developer_id)
                task.assigned_to = None
                self._event_log.append(f"auto_complete:{task.task_id}")
            else:
                task.status = "in_progress"
                developer.available = False

    def _update_progress_risk_and_terminal(self) -> None:
        total_effort = sum(task.effort_total for task in self._state.tasks)
        remaining_effort = sum(task.effort_remaining for task in self._state.tasks)
        if total_effort <= 0:
            self._state.sprint_progress = 1.0
        else:
            self._state.sprint_progress = round(1.0 - (remaining_effort / total_effort), 4)

        blocked_count = sum(1 for task in self._state.tasks if task.blocked and task.status != "completed")
        overdue_count = sum(
            1
            for task in self._state.tasks
            if task.status != "completed" and self._state.day > task.due_day
        )
        self._state.risk_level = round(min(1.0, blocked_count * 0.15 + overdue_count * 0.2), 4)
        self._state.time_remaining = max(0, self._state.max_days - self._state.day)

        all_done = all(task.status == "completed" for task in self._state.tasks)
        too_many_invalid = self._state.invalid_action_count >= 8
        deadline_exceeded = self._state.day >= self._state.max_days and not all_done

        self._state.project_completed = all_done
        self._state.project_failed = bool(too_many_invalid or deadline_exceeded)

    def _build_observation(self, *, reward: float, done: bool) -> PMObservation:
        blocked = [task.task_id for task in self._state.tasks if task.blocked and task.status != "completed"]
        developer_availability = {dev.developer_id: dev.available for dev in self._state.developers}
        developer_skill_levels = {
            dev.developer_id: dict(dev.skill_profile)
            for dev in self._state.developers
        }
        obs = PMObservation(
            done=done,
            reward=reward,
            scenario_id=self._state.scenario_id,
            day=self._state.day,
            max_days=self._state.max_days,
            sprint_progress=self._state.sprint_progress,
            risk_level=self._state.risk_level,
            time_remaining=self._state.time_remaining,
            active_tasks=list(self._state.tasks),
            blocked_tasks=blocked,
            developer_availability=developer_availability,
            developer_skill_levels=developer_skill_levels,
            event_log=self._event_log[-6:],
            score=self._state.score,
        )
        obs.metadata = {
            "project_completed": self._state.project_completed,
            "project_failed": self._state.project_failed,
            "invalid_action_count": self._state.invalid_action_count,
            "state": self._state.model_dump(),
        }
        return obs

    def _get_task(self, task_id: Optional[str]) -> Optional[TaskSnapshot]:
        if task_id is None:
            return None
        for task in self._state.tasks:
            if task.task_id == task_id:
                return task
        return None

    def _get_developer(self, developer_id: Optional[str]) -> Optional[DeveloperSnapshot]:
        if developer_id is None:
            return None
        for developer in self._state.developers:
            if developer.developer_id == developer_id:
                return developer
        return None

    def _release_developer(self, developer_id: Optional[str]) -> None:
        developer = self._get_developer(developer_id)
        if developer is not None:
            developer.assigned_task_id = None
            developer.available = True

    def _is_good_reprioritization(self, task: TaskSnapshot, previous: str) -> bool:
        if previous == task.priority:
            return False
        if task.priority == "critical":
            return True
        if self._state.time_remaining <= 2 and task.priority in {"high", "critical"}:
            return True
        return False

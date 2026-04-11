from __future__ import annotations

from typing import Dict, List, Literal, Optional

from openenv.core.env_server.interfaces import Action, Observation, State
from pydantic import Field

Priority = Literal["low", "medium", "high", "critical"]
ActionType = Literal[
    "assign_task",
    "reprioritize_task",
    "split_task",
    "request_help",
    "delay_task",
    "mark_complete",
]


class PMAction(Action):
    """Decision issued by the project manager agent."""

    action_type: ActionType
    task_id: Optional[str] = None
    developer_id: Optional[str] = None
    priority: Optional[Priority] = None
    helper_developer_id: Optional[str] = Field(None, description="The ID of the developer to request help from. Required when action_type is request_help.")


class DeveloperSnapshot(State):
    """Developer availability and load information."""

    developer_id: str = Field(..., description="Unique identifier for the developer.")
    available: bool = Field(True, description="True if the developer is free to take a task, false if currently assigned to a task.")
    assigned_task_id: Optional[str] = Field(None, description="The ID of the task currently assigned to this developer, if any.")
    busy_until_day: int = Field(0, description="Sprint day until which the developer is temporarily unavailable due to support or coordination work.")
    skill_profile: Dict[str, float] = Field(default_factory=dict, description="A mapping of task domains (e.g., 'backend', 'frontend') to a decimal skill multiplier (0.0 to 1.0). Higher skill means tasks complete faster.")


class TaskSnapshot(State):
    """Task-level state used in observations and internal state."""

    task_id: str = Field(..., description="Unique identifier for the task.")
    title: str = Field(..., description="Human-readable title of the task.")
    priority: Priority = Field("medium", description="Priority level of the task affecting effort progress speed.")
    domain: str = Field("backend", description="Domain classification (e.g. backend, frontend) that matches against developer skills.")
    dependencies: List[str] = Field(default_factory=list, description="List of task_ids that must be completed before this task can be worked on.")
    blocked: bool = Field(False, description="True if the task has uncompleted dependencies or a dynamic blocker active.")
    assigned_to: Optional[str] = Field(None, description="The developer_id currently working on this task.")
    effort_total: float = Field(1.0, description="Total effort units required to complete the task.")
    effort_remaining: float = Field(1.0, description="Remaining effort units. Task completes when this hits zero.")
    due_day: int = Field(1, description="Sprint day by which the task should be completed to avoid penalties.")
    status: Literal["todo", "in_progress", "completed"] = Field("todo", description="Current lifecycle status of the task.")
    metadata: Dict[str, str | bool | int | float] = Field(default_factory=dict, description="Dynamic attributes for the task, such as 'dynamic_blocked' flag in hard mode scenarios.")


class PMState(State):
    """Full deterministic sprint state."""

    scenario_id: str = Field("easy", description="The ID of the scenario being simulated.")
    day: int = Field(0, description="Current sprint calendar day.")
    max_days: int = Field(10, description="Maximum days allowed for this sprint.")
    sprint_progress: float = Field(0.0, description="Fraction of total sprint effort completed (0.0 to 1.0).")
    risk_level: float = Field(0.0, description="Calculated risk based on blocked and overdue tasks.")
    time_remaining: int = Field(10, description="Number of days remaining in the sprint.")
    project_completed: bool = Field(False, description="True if all tasks hit completed status.")
    project_failed: bool = Field(False, description="True if the sprint exceeded days or max invalid actions limit.")
    invalid_action_count: int = Field(0, description="Tracker of how many invalid rules were attempted.")
    score: float = Field(0.01, description="Running grader score metric.")
    developers: List[DeveloperSnapshot] = Field(default_factory=list, description="All developers available in the project.")
    tasks: List[TaskSnapshot] = Field(default_factory=list, description="All tasks comprising the sprint.")


class PMObservation(Observation):
    """Structured observation returned after each transition."""

    scenario_id: str = Field("easy", description="The ID of the scenario being simulated.")
    day: int = Field(0, description="Current sprint calendar day.")
    max_days: int = Field(10, description="Maximum days allowed for the sprint limit.")
    sprint_progress: float = Field(0.0, description="Fraction of total sprint effort completed ranging from 0.0 to 1.0.")
    risk_level: float = Field(0.0, description="Calculated risk measure between 0.0 and 1.0 based on blocked and overdue tasks.")
    time_remaining: int = Field(10, description="Number of days remaining in the sprint.")
    active_tasks: List[TaskSnapshot] = Field(default_factory=list, description="Snapshot array of all current tasks and their statuses.")
    blocked_tasks: List[str] = Field(default_factory=list, description="List of task_ids that are currently blocked.")
    developer_availability: Dict[str, bool] = Field(default_factory=dict, description="Dictionary mapping developer ID strings to a boolean true if they are available.")
    developer_skill_levels: Dict[str, Dict[str, float]] = Field(default_factory=dict, description="Nested dictionary mapping developer ID to their domain skill multipliers (0.0 to 1.0).")
    event_log: List[str] = Field(default_factory=list, description="Recent short log of project events.")
    score: float = Field(0.01, description="Current evaluation score from 0.0 to 1.0.")

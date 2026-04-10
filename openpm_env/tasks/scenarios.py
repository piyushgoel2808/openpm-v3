from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from openpm_env.models import Priority


@dataclass(frozen=True)
class TaskSeed:
    task_id: str
    title: str
    priority: Priority
    domain: str
    effort_total: float
    due_day: int
    dependencies: List[str]


@dataclass(frozen=True)
class DeveloperSeed:
    developer_id: str
    skill_profile: Dict[str, float]


@dataclass(frozen=True)
class ScenarioSpec:
    scenario_id: str
    max_days: int
    tasks: List[TaskSeed]
    developers: List[DeveloperSeed]
    blocker_schedule: Dict[int, List[str]]


SCENARIOS: Dict[str, ScenarioSpec] = {
    "easy": ScenarioSpec(
        scenario_id="easy",
        max_days=10,
        tasks=[
            TaskSeed("T1", "Implement login form", "high", "frontend", 1.4, 3, []),
            TaskSeed("T2", "Create auth API", "critical", "backend", 1.4, 4, []),
            TaskSeed("T3", "Add smoke tests", "medium", "qa", 1.0, 6, ["T1", "T2"]),
        ],
        developers=[
            DeveloperSeed("D1", {"frontend": 1.0, "backend": 0.6, "qa": 0.7}),
            DeveloperSeed("D2", {"frontend": 0.5, "backend": 1.0, "qa": 0.8}),
        ],
        blocker_schedule={},
    ),
    "medium": ScenarioSpec(
        scenario_id="medium",
        max_days=13,
        tasks=[
            TaskSeed("M1", "Design DB schema", "high", "backend", 2.3, 3, []),
            TaskSeed("M2", "Build API endpoints", "critical", "backend", 2.6, 6, ["M1"]),
            TaskSeed("M3", "Implement dashboard", "high", "frontend", 2.1, 7, []),
            TaskSeed("M4", "Integration testing", "medium", "qa", 2.0, 10, ["M2"]),
        ],
        developers=[
            DeveloperSeed("D1", {"backend": 1.0, "frontend": 0.5, "qa": 0.6}),
            DeveloperSeed("D2", {"backend": 0.7, "frontend": 1.0, "qa": 0.7}),
            DeveloperSeed("D3", {"backend": 0.6, "frontend": 0.6, "qa": 1.0}),
        ],
        blocker_schedule={},
    ),
    "hard": ScenarioSpec(
        scenario_id="hard",
        max_days=12,
        tasks=[
            TaskSeed("H1", "Plan migration", "high", "backend", 2.2, 3, []),
            TaskSeed("H2", "Migrate auth service", "critical", "backend", 2.6, 6, ["H1"]),
            TaskSeed("H3", "Front-end auth flow", "high", "frontend", 2.4, 7, ["H1"]),
            TaskSeed("H4", "Resilience testing", "high", "qa", 2.5, 10, ["H2", "H3"]),
            TaskSeed("H5", "Production checklist", "medium", "ops", 1.3, 12, ["H4"]),
        ],
        developers=[
            DeveloperSeed("D1", {"backend": 1.0, "frontend": 0.4, "qa": 0.5, "ops": 0.5}),
            DeveloperSeed("D2", {"backend": 0.7, "frontend": 1.0, "qa": 0.7, "ops": 0.6}),
            DeveloperSeed("D3", {"backend": 0.5, "frontend": 0.6, "qa": 1.0, "ops": 0.9}),
        ],
        blocker_schedule={
            3: ["H2"],
            7: ["H4"],
        },
    ),
}

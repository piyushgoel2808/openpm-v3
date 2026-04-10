from __future__ import annotations

from openenv.core.client_types import StepResult
from openenv.core.env_client import EnvClient

from openpm_env.models import PMAction, PMObservation, PMState


class OpenPMEnv(EnvClient[PMAction, PMObservation, PMState]):
    """WebSocket client for the OpenPM environment."""

    def _step_payload(self, action: PMAction) -> dict:
        return action.model_dump(exclude_none=True)

    def _parse_result(self, payload: dict) -> StepResult[PMObservation]:
        obs = PMObservation(**payload["observation"])
        return StepResult(
            observation=obs,
            reward=payload.get("reward"),
            done=bool(payload.get("done", False)),
        )

    def _parse_state(self, payload: dict) -> PMState:
        return PMState(**payload)

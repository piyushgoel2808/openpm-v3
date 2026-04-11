import os
import re
import subprocess
import sys

from openpm_env.env import OpenPMEnvironment
from openpm_env.models import PMAction


def _validate_environment_bounds() -> None:
    env = OpenPMEnvironment()
    env.reset(task_id="hard")
    result = env.step(PMAction(action_type="assign_task", task_id="H1", developer_id="D1"))

    reward = result.reward
    info = result.metadata if isinstance(result.metadata, dict) else {}

    assert type(reward) is float, f"Reward type leak: {type(reward)}"
    assert 0.0 < reward < 1.0, f"Reward out of bounds: {reward}"

    obs_score = getattr(result, "score", None)
    if obs_score is not None:
        assert type(obs_score) is float, f"Observation score type leak: {type(obs_score)}"
        assert 0.0 < obs_score < 1.0, f"Observation score out of bounds: {obs_score}"

    state = info.get("state") if isinstance(info, dict) else None
    if isinstance(state, dict) and "score" in state:
        assert type(state["score"]) is float, f"State score type leak: {type(state['score'])}"
        assert 0.0 < state["score"] < 1.0, f"State score out of bounds: {state['score']}"


def _validate_inference_regex() -> None:
    env = os.environ.copy()
    env["HF_TOKEN"] = env.get("HF_TOKEN", "mock-token")
    env["OPENPM_USE_OPENAI"] = "0"
    env["API_BASE_URL"] = ""
    env["MODEL_NAME"] = ""
    env["OPENPM_TASKS"] = "easy"
    env["OPENPM_DRY_RUN"] = "1"

    pattern = re.compile(r"^\[END\] success=(true|false) steps=\d+ score=0\.\d{2} rewards=.*$", re.MULTILINE)
    try:
        proc = subprocess.run(
            [sys.executable, "inference.py"],
            cwd=os.path.dirname(__file__),
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AssertionError("inference.py did not produce [END] output within 60 seconds") from exc

    output = (proc.stdout or "") + "\n" + (proc.stderr or "")
    match = pattern.search(output)
    assert match is not None, f"END regex mismatch. Output tail:\n{output[-1500:]}"


def main() -> None:
    _validate_environment_bounds()
    _validate_inference_regex()
    with open(os.path.join(os.path.dirname(__file__), ".verify_submission_passed"), "w", encoding="utf-8") as f:
        f.write("PASS\n")
    print("verify_submission.py: PASS")


if __name__ == "__main__":
    main()
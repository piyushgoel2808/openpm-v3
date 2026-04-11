import traceback

import numpy as np

from openpm_env.env import OpenPMEnvironment
from openpm_env.models import PMAction
from openpm_env.utils import safe_score


def run_mock_validation():
    print("🛡️ STARTING META VALIDATOR MOCK TEST...\n")

    print("Testing Zero-Trust Firewall against malicious inputs...")
    malicious_inputs = [
        (0.0, 0.01),
        (1.0, 0.99),
        (np.float32(1.0), 0.99),
        (np.float64(0.0), 0.01),
        (None, 0.01),
        ("0.5", 0.5),
    ]

    for bad_input, expected in malicious_inputs:
        result = safe_score(bad_input)
        assert type(result) is float, f"FAIL: Expected pure float, got {type(result)} for input {bad_input}"
        assert 0.0 < result < 1.0, f"FAIL: Score {result} is out of bounds for input {bad_input}"
        assert result == expected, f"FAIL: Expected {expected}, got {result} for input {bad_input}"
        print(f"✅ Input {str(bad_input).ljust(10)} -> Sanitized to: {result} ({type(result).__name__})")

    print("\n--- TEST 2: ENVIRONMENT NATIVE BYPASS ---")
    print("Testing if environment returns leak raw values...")

    try:
        env = OpenPMEnvironment()
        env.reset(task_id="hard")

        action = PMAction(action_type="assign_task", task_id="H1", developer_id="D1")
        step_result = env.step(action)

        if isinstance(step_result, tuple) and len(step_result) == 4:
            obs, reward, done, info = step_result
        else:
            obs = step_result
            reward = getattr(step_result, "reward", None)
            done = getattr(step_result, "done", None)
            info = getattr(step_result, "metadata", {}) or {}

        assert type(reward) is float, f"FAIL: Reward is type {type(reward)}, must be float."
        assert 0.0 < reward < 1.0, f"FAIL: Reward {reward} out of bounds!"
        print(f"✅ Reward check passed: {reward}")

        obs_score = getattr(obs, "score", None)
        if obs_score is not None:
            assert type(obs_score) is float, f"FAIL: Observation score is type {type(obs_score)}, must be float!"
            assert 0.0 < obs_score < 1.0, f"FAIL: Observation score {obs_score} out of bounds!"
            print(f"✅ Observation score check passed: {obs_score}")

        if isinstance(info, dict):
            info.setdefault("score", getattr(obs, "score", None))
            info.setdefault("task_score", getattr(obs, "score", None))
            info.setdefault("grade", getattr(obs, "score", None))

            for key in ("score", "task_score", "grade"):
                if key in info and info[key] is not None:
                    assert type(info[key]) is float, f"FAIL: Info {key} is type {type(info[key])}, must be float!"
                    assert 0.0 < info[key] < 1.0, f"FAIL: Info {key} {info[key]} out of bounds!"
                    print(f"✅ Info dict {key} check passed: {info[key]}")

            state = info.get("state")
            if isinstance(state, dict) and "score" in state:
                assert type(state["score"]) is float, f"FAIL: State score is type {type(state['score'])}, must be float!"
                assert 0.0 < state["score"] < 1.0, f"FAIL: State score {state['score']} out of bounds!"
                print(f"✅ State score check passed: {state['score']}")

        print("\n🎉 ALL MOCK VALIDATION CHECKS PASSED. YOU ARE SAFE TO SUBMIT.")

    except Exception:
        print("\n❌ VALIDATOR CRASHED! We still have a leak.")
        traceback.print_exc()


if __name__ == "__main__":
    run_mock_validation()
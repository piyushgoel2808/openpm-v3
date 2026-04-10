from __future__ import annotations

import atexit
import os
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path
from urllib.parse import urlparse
from statistics import mean
from typing import Any, Dict, List

import json

from openai import OpenAI

from openpm_env import OpenPMEnv, PMAction
from openpm_env.graders import grade_for_task

TASKS = ["easy", "medium", "hard"]
MAX_STEPS = 25

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4")
HF_TOKEN = os.getenv("HF_TOKEN")
if HF_TOKEN is None:
    raise ValueError("HF_TOKEN is missing")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

USE_OPENAI = bool(API_BASE_URL and MODEL_NAME) or os.getenv("OPENPM_USE_OPENAI", "0") == "1"

_SERVER_PROCESS: subprocess.Popen | None = None


def _is_local_base_url(base_url: str) -> bool:
    parsed = urlparse(base_url)
    host = parsed.hostname or ""
    return host in {"localhost", "127.0.0.1"}


def _try_reset_probe(base_url: str) -> bool:
    try:
        with OpenPMEnv(base_url=base_url).sync() as probe_env:
            probe_env.reset(task_id="easy")
        return True
    except Exception:
        return False


def _stop_local_server() -> None:
    global _SERVER_PROCESS
    if _SERVER_PROCESS is None:
        return

    with suppress(Exception):
        _SERVER_PROCESS.terminate()
        _SERVER_PROCESS.wait(timeout=5)
    with suppress(Exception):
        if _SERVER_PROCESS.poll() is None:
            _SERVER_PROCESS.kill()
    _SERVER_PROCESS = None


def _ensure_server_ready(base_url: str) -> None:
    global _SERVER_PROCESS

    if _try_reset_probe(base_url):
        return

    if not _is_local_base_url(base_url):
        raise RuntimeError(
            f"Unable to connect to running OpenPM server at {base_url}. "
            "Start the server manually or set OPENPM_BASE_URL to a reachable endpoint."
        )

    script_root = Path(__file__).resolve().parent
    parsed = urlparse(base_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8000

    _SERVER_PROCESS = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "server.app:app",
            "--host",
            host,
            "--port",
            str(port),
        ],
        cwd=str(script_root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    atexit.register(_stop_local_server)

    deadline = time.time() + 20
    while time.time() < deadline:
        if _try_reset_probe(base_url):
            return
        time.sleep(0.5)

    _stop_local_server()
    raise RuntimeError(
        f"OpenPM server failed to start at {base_url} within 20 seconds. "
        "Check dependencies and run `uv run server` manually to inspect logs."
    )


def _pick_rule_action(observation) -> PMAction:
    tasks = observation.active_tasks

    # Resolve only dynamic blockers first. Dependency blockers must be solved by completing prerequisites.
    for task in tasks:
        if (
            task.blocked
            and task.status != "completed"
            and bool(task.metadata.get("dynamic_blocked", False))
        ):
            available_devs = [
                dev_id for dev_id, available in observation.developer_availability.items() if available
            ]
            if available_devs:
                return PMAction(action_type="request_help", task_id=task.task_id, helper_developer_id=available_devs[0])
            else:
                return PMAction(action_type="delay_task", task_id=task.task_id)

    # Assign unblocked work by urgency first.
    unassigned = [
        task
        for task in tasks
        if task.status != "completed" and task.assigned_to is None and not task.blocked
    ]
    if unassigned:
        unassigned.sort(
            key=lambda task: (
                -{"low": 1, "medium": 2, "high": 3, "critical": 4}[task.priority],
                task.due_day,
            )
        )
        target = unassigned[0]
        available_devs = [
            dev_id
            for dev_id, available in observation.developer_availability.items()
            if available
        ]
        if available_devs:
            # Match task domain to the highest-skill available developer.
            available_devs.sort(
                key=lambda dev_id: (
                    -observation.developer_skill_levels.get(dev_id, {}).get(target.domain, 0.0),
                    dev_id,
                )
            )
            return PMAction(
                action_type="assign_task",
                task_id=target.task_id,
                developer_id=available_devs[0],
            )

    # Raise urgency for work that is close to due date.
    for task in tasks:
        if (
            task.status != "completed"
            and observation.day + 1 >= task.due_day
            and task.priority != "critical"
        ):
            return PMAction(action_type="reprioritize_task", task_id=task.task_id, priority="critical")

    # Confirm task completion when nearly done.
    for task in tasks:
        if task.status != "completed" and task.effort_remaining <= 0.2:
            return PMAction(action_type="mark_complete", task_id=task.task_id)

    # Final fallback: deterministic reprioritization of the earliest-due unfinished task.
    open_tasks = [task for task in tasks if task.status != "completed"]
    if open_tasks:
        open_tasks.sort(key=lambda task: task.due_day)
        target = open_tasks[0]
        if target.priority != "critical":
            return PMAction(action_type="reprioritize_task", task_id=target.task_id, priority="critical")
        return PMAction(action_type="mark_complete", task_id=target.task_id)

    return PMAction(action_type="mark_complete", task_id=tasks[0].task_id)


def _pick_openai_action(observation, client: OpenAI) -> Dict[str, Any]:
    try:
        prompt = (
            "You are a project manager agent in a deterministic sprint simulation. "
            "Return one JSON object with keys: action_type, task_id, developer_id, priority. "
            "Only use action_type from assign_task, reprioritize_task, split_task, request_help, delay_task, mark_complete. "
            "Current observation: "
            f"day={observation.day}, progress={observation.sprint_progress}, blocked={observation.blocked_tasks}, "
            f"tasks={[(t.task_id, t.priority, t.status, t.assigned_to, t.effort_remaining, t.blocked) for t in observation.active_tasks]}, "
            f"availability={observation.developer_availability}"
        )

        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=120,
        )
        content = completion.choices[0].message.content or "{}"

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            print(f"[WARN] openai_json_error={str(e)}", flush=True)
            return {"action_type": "invalid_fallback"}

        if not isinstance(parsed, dict):
            print("[WARN] openai_payload_error=non_dict_response", flush=True)
            return {"action_type": "invalid_fallback"}

        return parsed
    except Exception as e:
        print(f"[WARN] openai_api_error={str(e)}", flush=True)
        return {"action_type": "invalid_fallback"}


def run_task(task_id: str, base_url: str) -> Dict[str, float]:
    openai_client = None
    if USE_OPENAI:
        if not API_BASE_URL or not MODEL_NAME or not (HF_TOKEN or OPENAI_API_KEY):
            raise RuntimeError(
                "OPENPM_USE_OPENAI=1 requires API_BASE_URL, MODEL_NAME, and HF_TOKEN or OPENAI_API_KEY"
            )
        openai_client = OpenAI(base_url=API_BASE_URL, api_key=HF_TOKEN)

    model_display_name = MODEL_NAME if MODEL_NAME else "rule_based"
    print(f"[START] task={task_id} env=openpm model={model_display_name}", flush=True)

    start = time.time()
    rewards_history = []
    success = False
    steps_taken = 0
    score = 0.0

    try:
        with OpenPMEnv(base_url=base_url).sync() as env:
            result = env.reset(task_id=task_id, seed=42)

            for step_idx in range(MAX_STEPS):
                if result.done:
                    break
                if openai_client is None:
                    action = _pick_rule_action(result.observation)
                else:
                    action_payload = _pick_openai_action(result.observation, openai_client)
                    if action_payload.get("action_type") == "invalid_fallback":
                        action = _pick_rule_action(result.observation)
                    else:
                        try:
                            action = PMAction(**action_payload)
                        except Exception:
                            action = _pick_rule_action(result.observation)

                try:
                    result = env.step(action)
                    step_reward = result.reward
                    rewards_history.append(step_reward)
                    done_str = "true" if result.done else "false"
                    action_str = f"{action.action_type}({action.task_id or ''})"
                    print(f"[STEP] step={step_idx + 1} action={action_str} reward={step_reward:.2f} done={done_str} error=null", flush=True)
                    if result.done:
                        break
                except Exception as e:
                    print(f"[STEP] step={step_idx + 1} action={action.action_type} reward=0.00 done=false error={str(e)}", flush=True)
                    break

            state = env.state()

        duration_s = round(time.time() - start, 3)
        score = float(grade_for_task(task_id, state))
        success = state.project_completed and not state.project_failed
        steps_taken = state.step_count
    except Exception as e:
        duration_s = round(time.time() - start, 3)
        print(f"[WARN] run_task_error={str(e)}", flush=True)

    finally:
        score = float(max(0.01, min(0.99, score)))
        success_str = str(success).lower()
        rewards_str = ",".join(f"{r:.2f}" for r in rewards_history)
        print(f"[END] success={success_str} steps={steps_taken} score={score:.2f} rewards={rewards_str}", flush=True)

    return {
        "score": round(score, 4),
        "duration_s": duration_s,
        "steps": float(steps_taken),
        "progress": round(score, 4),
    }


def main() -> None:
    base_url = os.getenv("OPENPM_BASE_URL", "http://localhost:8000")
    _ensure_server_ready(base_url)
    results: Dict[str, Dict[str, float]] = {}

    for task_id in TASKS:
        metrics = run_task(task_id, base_url)
        results[task_id] = metrics

    avg_score = mean(metric["score"] for metric in results.values())
    total_duration = sum(metric["duration_s"] for metric in results.values())


if __name__ == "__main__":
    main()

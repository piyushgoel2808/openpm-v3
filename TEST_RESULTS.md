# Test Results Evidence Pack

## Summary

- Date: 2026-04-10
- Repository: https://github.com/piyushgoel2808/openpm-v3.git
- Scope: strict stdout compliance audit, runtime/resource audit, and deterministic benchmark evidence.

## Validation Checklist

- [x] `inference.py` END log format updated to remove `score=` from the final line.
- [x] README includes PMBOK mapping section.
- [x] README includes Hard Task narrative explaining baseline failure boundary.
- [x] Multi-seed Easy/Medium/Hard table recorded for deterministic grading audit.
- [x] Grading clamp verified to remain within `0.01` to `0.99`.

## Local Test Evidence

- `tests/test_openpm.py`: 12 tests passing (latest known local run).

## Deterministic Multi-Seed Baseline (AdvancedRuleBasedAgent)

Evaluation settings:

- Tasks: `easy`, `medium`, `hard`
- Seeds: `1, 7, 21, 42, 99`
- Max steps per task: `25`
- Grader clamp: `0.01 <= score <= 0.99`

| Seed |   Easy | Medium |   Hard |
| ---: | -----: | -----: | -----: |
|    1 | 0.9900 | 0.9900 | 0.0100 |
|    7 | 0.9900 | 0.2214 | 0.0100 |
|   21 | 0.9900 | 0.5956 | 0.0100 |
|   42 | 0.9900 | 0.5900 | 0.0100 |
|   99 | 0.9900 | 0.9900 | 0.0100 |
|  AVG | 0.9900 | 0.6774 | 0.0100 |

Result interpretation:

- Deterministic floor behavior is visible on hard scenarios with bounded minimum `0.0100`.
- Easy remains saturated at the clamp cap (`0.9900`) under this baseline.
- Medium varies by seed as intended while remaining bounded by grading constraints.

## Notes

- `.gitignore` excludes secrets and local environment artifacts (`.env`, `.venv`, `__pycache__/`, and `*.egg-info`), so secrets must be configured in Hugging Face Space settings after deployment.

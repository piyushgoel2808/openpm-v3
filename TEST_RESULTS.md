# Test Results Evidence Pack

## Summary

- Date: 2026-04-10
- Repository: https://github.com/piyushgoel2808/openpm-v3.git
- Scope: Waitlist regex fix verification, benchmark evidence, and documentation updates.

## Validation Checklist

- [x] `inference.py` END log format updated to remove `score=` from the final line.
- [x] README includes PMBOK mapping section.
- [x] README includes Hard Task narrative explaining baseline failure boundary.

## Local Test Evidence

- `tests/test_openpm.py`: 12 tests passing (latest known local run).

## Benchmark Evidence (seed=42)

- AdvancedRuleBasedAgent:
  - easy: 0.6385
  - medium: 0.3805
  - hard: 0.0000

## Notes

- `.gitignore` excludes secrets and local environment artifacts (`.env`, `.venv`, and `*.egg-info`), so secrets must be configured in Hugging Face Space settings after deployment.

from __future__ import annotations


def safe_score(val) -> float:
    try:
        if val is None:
            return 0.01
        return max(0.01, min(0.99, float(val)))
    except:
        return 0.01
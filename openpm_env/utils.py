from __future__ import annotations


def safe_score(val) -> float:
    """Zero-Trust Type-Safe Firewall for Meta Validator"""
    try:
        if val is None:
            return 0.01
        val_float = float(val)
        return max(0.01, min(0.99, val_float))
    except (ValueError, TypeError):
        return 0.01
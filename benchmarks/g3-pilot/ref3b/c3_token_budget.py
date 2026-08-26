"""Deterministic largest-remainder token budget allocation."""

from __future__ import annotations

import math
from collections.abc import Mapping


def split_token_budget(total: int, weights: Mapping[str, float]) -> dict[str, int]:
    """Split *total* whole units across *weights* by largest-remainder rounding.

    Remainder units go to the largest fractional parts; ties on the fractional
    part are broken by key in ascending lexicographic order. The allocations
    always sum to *total* and every allocation is non-negative.
    """
    if total < 0:
        raise ValueError("total must be non-negative")
    if not weights:
        raise ValueError("weights must not be empty")
    if any(weight < 0 for weight in weights.values()):
        raise ValueError("weights must be non-negative")
    weight_sum = sum(weights.values())
    if weight_sum <= 0:
        raise ValueError("weight sum must be positive")

    exact = {key: total * weight / weight_sum for key, weight in weights.items()}
    allocations = {key: math.floor(share) for key, share in exact.items()}
    remainder = total - sum(allocations.values())
    by_fraction = sorted(
        exact,
        key=lambda key: (-(exact[key] - allocations[key]), key),
    )
    for key in by_fraction[:remainder]:
        allocations[key] += 1
    return allocations

"""Tests for dspx.g3p3_token_budget: exact splits, ties, errors, and the sum invariant."""

from __future__ import annotations

import random

import pytest

from dspx.g3p3_token_budget import split_token_budget


def test_exact_split_with_no_remainder() -> None:
    assert split_token_budget(100, {"a": 1.0, "b": 3.0}) == {"a": 25, "b": 75}


def test_largest_remainder_with_tie_broken_by_key_order() -> None:
    # exact shares: a=0.4, b=0.4, c=1.2 -> bases 0,0,1; one remainder unit,
    # fractional parts tie at 0.4 between a and b -> 'a' wins by key order.
    assert split_token_budget(2, {"a": 1.0, "b": 1.0, "c": 3.0}) == {"a": 1, "b": 0, "c": 1}


def test_error_cases() -> None:
    with pytest.raises(ValueError):
        split_token_budget(-1, {"a": 1.0})
    with pytest.raises(ValueError):
        split_token_budget(10, {})
    with pytest.raises(ValueError):
        split_token_budget(10, {"a": -0.5, "b": 1.0})
    with pytest.raises(ValueError):
        split_token_budget(10, {"a": 0.0})


@pytest.mark.parametrize(
    ("total", "weights"),
    [
        (0, {"a": 1.0, "b": 2.0}),
        (1, {"a": 1.0, "b": 2.0, "c": 3.0}),
        (7, {"a": 0.1, "b": 0.2, "c": 0.7}),
        (13, {"a": 2.0, "b": 3.0, "c": 5.0, "d": 7.0, "e": 11.0}),
        (50, {"a": 1.0, "b": 1.0}),
        (99, {"a": 1.0, "b": 1.0, "c": 1.0}),
        (1000, {"a": 0.001, "b": 0.999}),
        (37, {"a": 3.0, "b": 3.0, "c": 3.0, "d": 1.0}),
    ],
)
def test_property_sum_invariant_and_key_preservation(total: int, weights: dict[str, float]) -> None:
    result = split_token_budget(total, weights)
    assert sum(result.values()) == total
    assert set(result.keys()) == set(weights.keys())
    assert all(value >= 0 for value in result.values())


def test_property_random_cases_preserve_invariant() -> None:
    rng = random.Random(20260826)
    for _case in range(8):
        total = rng.randrange(0, 500)
        keys = [f"c{index}" for index in range(rng.randrange(2, 6))]
        weights = {key: float(rng.randrange(1, 40)) for key in keys}
        result = split_token_budget(total, weights)
        assert sum(result.values()) == total
        assert set(result.keys()) == set(weights.keys())

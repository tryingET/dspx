# summary: "Tests GEPA metric weighting, normalization hooks, and predictor feedback."
# read_when:
#   - "Changing default GEPA metric composition."

from __future__ import annotations

from types import SimpleNamespace

from dspx.services.optimize_service import _default_gepa_metric


def test_gepa_metric_weighted_average() -> None:
    gold = SimpleNamespace(a="x", b="x")
    pred = SimpleNamespace(a="x", b="nope")

    metric = _default_gepa_metric(
        ["a", "b"],
        metric_name="exact",
        output_weights={"a": 0.2, "b": 0.8},
        normalize_output=None,
    )
    scored = metric(gold, pred, None, None, None)
    assert abs(float(scored.score) - 0.2) < 1e-9


def test_gepa_metric_normalize_hook_and_predictor_feedback() -> None:
    gold = SimpleNamespace(answer="HELLO")
    pred = SimpleNamespace(answer="hello")

    def normalize_output(key, g, p, pred_name, pred_trace):
        return g.strip().lower(), p.strip().lower()

    metric = _default_gepa_metric(
        ["answer"],
        metric_name="exact",
        output_weights={},
        normalize_output=normalize_output,
    )
    scored = metric(gold, pred, None, "Student.predict", object())
    assert float(scored.score) == 1.0
    assert str(scored.feedback).startswith("predictor=Student.predict")

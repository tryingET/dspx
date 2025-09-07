import pytest

from dspx.adapters.eval import (
    accuracy,
    f1_binary,
    roc_auc_binary,
    precision_recall_per_class,
    rouge1_f1_macro,
    bleu1_macro,
    pr_curve_binary,
    expected_calibration_error_binary,
)


def test_accuracy_basic_and_edge_cases() -> None:
    assert accuracy([1, 0, 1], [1, 0, 0]) == pytest.approx(2 / 3)
    assert accuracy([], []) == 0.0
    with pytest.raises(ValueError):
        accuracy([1], [])


def test_f1_binary_with_ints_and_bools() -> None:
    # Perfect match
    assert f1_binary([1, 0, 1, 0], [1, 0, 1, 0]) == 1.0
    # Half true positives, some false positives/negatives
    f1 = f1_binary([1, 0, 1, 0], [1, 1, 0, 0])
    # tp=1, fp=1, fn=1 -> precision=0.5, recall=0.5 => f1=0.5
    assert f1 == pytest.approx(0.5)
    # No positives predicted nor true -> f1=0.0
    assert f1_binary([0, 0], [0, 0]) == 0.0
    # Bool labels inferred as positive=True
    assert f1_binary([True, False, True], [True, True, False]) == pytest.approx(0.5)


def test_f1_binary_requires_label_for_strings() -> None:
    with pytest.raises(ValueError):
        f1_binary(["cat", "dog"], ["cat", "cat"])  # no positive_label
    f1 = f1_binary(["cat", "dog"], ["cat", "cat"], positive_label="cat")
    # true positives=1, fp=1, fn=0 -> precision=0.5, recall=1.0 -> f1=0.666..
    assert f1 == pytest.approx(2 / 3)


def test_roc_auc_binary_basic() -> None:
    # Classic example: AUC = 0.75
    y_true = [0, 0, 1, 1]
    scores = [0.1, 0.4, 0.35, 0.8]
    auc = roc_auc_binary(y_true, scores)
    assert auc == pytest.approx(0.75)


def test_precision_recall_per_class() -> None:
    y_true = ["cat", "dog", "cat", "mouse", "dog", "dog"]
    y_pred = ["cat", "cat", "dog", "mouse", "dog", "mouse"]
    res = precision_recall_per_class(y_true, y_pred)
    assert set(res.keys()) == {"cat", "dog", "mouse"}
    # Sanity checks
    assert 0.0 <= res["cat"]["precision"] <= 1.0
    assert 0.0 <= res["cat"]["recall"] <= 1.0


def test_macro_text_metrics() -> None:
    refs = ["a", "a b"]
    cands = ["a", "b"]
    # Expected macro values approx
    # rouge macro ≈ (1.0 + 2/3)/2 = 0.8333, micro ≈ 0.8
    r_macro = rouge1_f1_macro(refs, cands)
    assert r_macro == pytest.approx(0.83333, rel=1e-3)
    # bleu macro ≈ (1 + exp(-1))/2 ≈ 0.6839
    b_macro = bleu1_macro(refs, cands)
    assert b_macro == pytest.approx(0.6839, rel=1e-3)


def test_pr_curve_and_ece() -> None:
    y_true = [0, 0, 1, 1]
    scores = [0.1, 0.4, 0.35, 0.8]
    curve = pr_curve_binary(y_true, scores)
    assert set(curve.keys()) == {"thresholds", "precision", "recall"}
    assert len(curve["thresholds"]) == len(set(scores))
    # recall should be non-decreasing
    rec = curve["recall"]
    assert all(rec[i] <= rec[i + 1] for i in range(len(rec) - 1))
    # ECE should be finite in [0,1]
    ece = expected_calibration_error_binary(y_true, [0.0, 0.3, 0.7, 1.0])
    assert 0.0 <= ece <= 1.0

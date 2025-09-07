import pytest

from dspx.adapters.eval import accuracy, f1_binary


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

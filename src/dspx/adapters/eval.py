from __future__ import annotations

from typing import List, Sequence


def accuracy(y_true: Sequence[object], y_pred: Sequence[object]) -> float:
    """Compute simple accuracy = correct / total.

    - Returns 0.0 for empty inputs.
    - Raises ValueError on length mismatch.
    - Equality is evaluated via Python's ==.
    """
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have the same length")
    n = len(y_true)
    if n == 0:
        return 0.0
    correct = sum(1 for a, b in zip(y_true, y_pred) if a == b)
    return float(correct) / float(n)


def _to_binary(seq: Sequence[object], positive_label: object) -> List[int]:
    out: List[int] = []
    for v in seq:
        out.append(1 if v == positive_label else 0)
    return out


def f1_binary(
    y_true: Sequence[object],
    y_pred: Sequence[object],
    *,
    positive_label: object | None = None,
) -> float:
    """Compute F1 for binary classification.

    - By default, attempts to infer `positive_label` as follows:
        - If any booleans present in y_true, positive is True.
        - Else if integers 0/1 present in y_true, positive is 1.
        - Else requires explicit `positive_label`.
    - Returns 0.0 when there are no predicted positives and no true positives.
    - Raises ValueError for length mismatch.
    """
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have the same length")
    n = len(y_true)
    if n == 0:
        return 0.0

    if positive_label is None:
        # Infer conventional positive class
        if any(isinstance(v, bool) for v in y_true):
            positive_label = True
        elif any(isinstance(v, int) for v in y_true):
            # Use 1 as positive by convention, even if absent in y_true
            positive_label = 1
        else:
            raise ValueError(
                "positive_label must be provided for non-bool/non-int labels"
            )

    yt = _to_binary(y_true, positive_label)
    yp = _to_binary(y_pred, positive_label)

    tp = sum(1 for t, p in zip(yt, yp) if t == 1 and p == 1)
    fp = sum(1 for t, p in zip(yt, yp) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(yt, yp) if t == 1 and p == 0)

    # Precision and recall with safe 0 denominators
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    if precision + recall == 0.0:
        return 0.0
    return 2.0 * precision * recall / (precision + recall)

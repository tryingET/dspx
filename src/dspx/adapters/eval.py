from __future__ import annotations

from typing import List, Sequence, Dict


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


def confusion_matrix_binary(
    y_true: Sequence[object],
    y_pred: Sequence[object],
    *,
    positive_label: object | None = None,
) -> Dict[str, int]:
    """Compute confusion matrix counts for binary classification.

    Returns a dict with keys: tp, tn, fp, fn.
    """
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have the same length")
    if positive_label is None:
        if any(isinstance(v, bool) for v in y_true):
            positive_label = True
        elif any(isinstance(v, int) for v in y_true):
            positive_label = 1
        else:
            raise ValueError(
                "positive_label must be provided for non-bool/non-int labels"
            )
    tp = tn = fp = fn = 0
    for t, p in zip(y_true, y_pred):
        tb = 1 if t == positive_label else 0
        pb = 1 if p == positive_label else 0
        if tb == 1 and pb == 1:
            tp += 1
        elif tb == 0 and pb == 0:
            tn += 1
        elif tb == 0 and pb == 1:
            fp += 1
        else:
            fn += 1
    return {"tp": tp, "tn": tn, "fp": fp, "fn": fn}


def _tokenize(s: str) -> List[str]:
    return [tok for tok in str(s).lower().split() if tok]


def rouge1_f1(refs: Sequence[str], cands: Sequence[str]) -> float:
    """Corpus-level ROUGE-1 F1 (unigram F1) over pairs of strings.

    Computes global precision/recall by summing overlaps over the corpus.
    Returns 0.0 when there are no tokens.
    """
    if len(refs) != len(cands):
        raise ValueError("refs and cands must have same length")
    total_overlap = 0
    total_ref = 0
    total_cand = 0
    for r, c in zip(refs, cands):
        rtoks = _tokenize(r)
        ctoks = _tokenize(c)
        total_ref += len(rtoks)
        total_cand += len(ctoks)
        # multiset overlap via counts
        from collections import Counter

        rc = Counter(rtoks)
        cc = Counter(ctoks)
        overlap = sum(min(rc[t], cc[t]) for t in set(rc) | set(cc))
        total_overlap += overlap
    if total_ref == 0 or total_cand == 0 or total_overlap == 0:
        return 0.0
    precision = total_overlap / total_cand
    recall = total_overlap / total_ref
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def bleu1(refs: Sequence[str], cands: Sequence[str]) -> float:
    """Corpus BLEU-1 (unigram precision with brevity penalty).

    - BLEU1 = BP * (matches / total_cand_unigrams)
    - BP = min(1, exp(1 - ref_len/cand_len))
    """
    if len(refs) != len(cands):
        raise ValueError("refs and cands must have same length")
    total_match = 0
    total_cand = 0
    total_ref = 0
    from collections import Counter

    for r, c in zip(refs, cands):
        rtoks = _tokenize(r)
        ctoks = _tokenize(c)
        total_ref += len(rtoks)
        total_cand += len(ctoks)
        rc = Counter(rtoks)
        cc = Counter(ctoks)
        total_match += sum(min(cc[t], rc[t]) for t in cc)
    if total_cand == 0:
        return 0.0
    import math

    prec = total_match / total_cand
    if total_ref == 0 or total_cand == 0:
        bp = 0.0
    else:
        bp = 1.0 if total_cand > total_ref else math.exp(1.0 - (total_ref / total_cand))
    return float(bp * prec)

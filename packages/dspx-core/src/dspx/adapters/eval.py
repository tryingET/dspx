# summary: "Implements deterministic classification, ranking, calibration, and text-similarity evaluation metrics."
# read_when:
#   - "You are evaluating DSPx predictions or changing metric definitions and edge-case handling."

from __future__ import annotations

import math
from numbers import Integral
from typing import Any, Dict, List, Sequence, cast


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


def _finite_scores(y_scores: Sequence[object]) -> List[float]:
    try:
        scores: List[float] = [float(cast(Any, s)) for s in y_scores]
    except Exception as e:
        raise ValueError("y_scores must be numeric") from e
    if not all(math.isfinite(score) for score in scores):
        raise ValueError("y_scores must contain only finite numeric values")
    return scores


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


def rouge1_f1_macro(refs: Sequence[str], cands: Sequence[str]) -> float:
    """Macro-averaged ROUGE-1 F1 over pairs.

    Computes per-pair unigram F1 then averages. Returns 0.0 for empty inputs.
    """
    if len(refs) != len(cands):
        raise ValueError("refs and cands must have same length")
    n = len(refs)
    if n == 0:
        return 0.0

    def _pair_f1(r: str, c: str) -> float:
        rt = _tokenize(r)
        ct = _tokenize(c)
        if not rt and not ct:
            return 0.0
        from collections import Counter

        rc = Counter(rt)
        cc = Counter(ct)
        overlap = sum(min(rc[t], cc[t]) for t in set(rc) | set(cc))
        if overlap == 0:
            return 0.0
        precision = overlap / max(len(ct), 1)
        recall = overlap / max(len(rt), 1)
        if precision + recall == 0:
            return 0.0
        return 2 * precision * recall / (precision + recall)

    return sum(_pair_f1(r, c) for r, c in zip(refs, cands)) / float(n)


def bleu1_macro(refs: Sequence[str], cands: Sequence[str]) -> float:
    """Macro-averaged BLEU-1 (unigram precision with brevity penalty).

    Computes per-pair BLEU-1 then averages.
    """
    if len(refs) != len(cands):
        raise ValueError("refs and cands must have same length")
    n = len(refs)
    if n == 0:
        return 0.0
    import math
    from collections import Counter

    def _pair_bleu(r: str, c: str) -> float:
        rt = _tokenize(r)
        ct = _tokenize(c)
        if not ct:
            return 0.0
        rc = Counter(rt)
        cc = Counter(ct)
        matches = sum(min(cc[t], rc[t]) for t in cc)
        prec = matches / len(ct)
        bp = 1.0 if len(ct) > len(rt) else math.exp(1.0 - (len(rt) / max(len(ct), 1)))
        return float(bp * prec)

    return sum(_pair_bleu(r, c) for r, c in zip(refs, cands)) / float(n)


def roc_auc_binary(
    y_true: Sequence[object],
    y_scores: Sequence[object],
    *,
    positive_label: object | None = None,
) -> float:
    """Compute ROC-AUC for binary classification given scores.

    - y_true may contain bools/ints/strings; positive class is inferred similarly to f1_binary:
      True if any booleans present; else 1 if any ints present; else requires positive_label.
    - y_scores are treated as floats.
    - Returns 0.5 for degenerate cases with no pos or no neg examples.
    """
    if len(y_true) != len(y_scores):
        raise ValueError("y_true and y_scores must have the same length")
    n = len(y_true)
    if n == 0:
        return 0.0

    # Determine positive label
    inferred = positive_label
    if inferred is None:
        if any(isinstance(v, bool) for v in y_true):
            inferred = True
        elif any(isinstance(v, int) for v in y_true):
            inferred = 1
        else:
            raise ValueError(
                "positive_label must be provided for non-bool/non-int labels"
            )

    # Convert y_true to 0/1 and scores to float
    yb: List[int] = [1 if v == inferred else 0 for v in y_true]
    scores = _finite_scores(y_scores)

    n_pos = sum(yb)
    n_neg = len(yb) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5

    # Mann–Whitney U: probability a random positive has higher score than a random negative
    # AUC = (sum of ranks for positives - n_pos*(n_pos+1)/2) / (n_pos*n_neg)
    # We compute ranks with average ties.
    order = sorted(range(n), key=lambda i: scores[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        avg_rank = (i + j + 2) / 2.0  # 1-based average rank
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    sum_pos_ranks = sum(r for r, y in zip(ranks, yb) if y == 1)
    auc = (sum_pos_ranks - (n_pos * (n_pos + 1) / 2.0)) / (n_pos * n_neg)
    return float(auc)


def precision_recall_per_class(
    y_true: Sequence[object], y_pred: Sequence[object]
) -> Dict[str, Dict[str, float]]:
    """Compute per-class precision and recall.

    - Returns mapping: {label: {precision, recall, support}} with label stringified.
    - Precision/recall default to 0.0 when denominators are 0.
    """
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have the same length")
    labels = set(y_true) | set(y_pred)
    out: Dict[str, Dict[str, float]] = {}
    for lab in labels:
        tp = fp = fn = 0
        for t, p in zip(y_true, y_pred):
            if p == lab and t == lab:
                tp += 1
            elif p == lab and t != lab:
                fp += 1
            elif p != lab and t == lab:
                fn += 1
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        out[str(lab)] = {
            "precision": float(prec),
            "recall": float(rec),
            "support": float(sum(1 for t in y_true if t == lab)),
        }
    return out


# --- PR Curve and Calibration ---


def pr_curve_binary(
    y_true: Sequence[object],
    y_scores: Sequence[object],
    *,
    positive_label: object | None = None,
) -> Dict[str, List[float]]:
    """Compute precision-recall curve for binary classification.

    Returns a dict with keys: thresholds, precision, recall.
    Uses all unique score thresholds sorted descending.
    """
    if len(y_true) != len(y_scores):
        raise ValueError("y_true and y_scores must have the same length")
    # Determine positive label like in roc_auc
    inferred = positive_label
    if inferred is None:
        if any(isinstance(v, bool) for v in y_true):
            inferred = True
        elif any(isinstance(v, int) for v in y_true):
            inferred = 1
        else:
            raise ValueError(
                "positive_label must be provided for non-bool/non-int labels"
            )
    yb: List[int] = [1 if v == inferred else 0 for v in y_true]
    scores = _finite_scores(y_scores)

    # Sort by score descending
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    sorted_scores = [scores[i] for i in order]
    sorted_true = [yb[i] for i in order]
    # Unique thresholds
    thresholds = sorted(set(sorted_scores), reverse=True)
    precisions: List[float] = []
    recalls: List[float] = []
    # Compute cumulative TP/FP as threshold moves
    tp = 0
    fp = 0
    total_pos = sum(yb)
    i = 0
    for thr in thresholds:
        while i < len(sorted_scores) and sorted_scores[i] >= thr:
            if sorted_true[i] == 1:
                tp += 1
            else:
                fp += 1
            i += 1
        prec = tp / (tp + fp) if (tp + fp) > 0 else 1.0
        rec = tp / total_pos if total_pos > 0 else 0.0
        precisions.append(float(prec))
        recalls.append(float(rec))
    return {"thresholds": thresholds, "precision": precisions, "recall": recalls}


def expected_calibration_error_binary(
    y_true: Sequence[object],
    y_scores: Sequence[object],
    *,
    positive_label: object | None = None,
    n_bins: int = 10,
) -> float:
    """Compute Expected Calibration Error (ECE) with equal-width bins on [0,1].

    Scores are clamped to [0,1]. Returns 0.0 for empty inputs.
    """
    if len(y_true) != len(y_scores):
        raise ValueError("y_true and y_scores must have the same length")
    if isinstance(n_bins, bool) or not isinstance(n_bins, Integral):
        raise ValueError("n_bins must be a positive integer")
    bin_count = int(n_bins)
    if bin_count < 1:
        raise ValueError("n_bins must be a positive integer")
    n = len(y_true)
    if n == 0:
        return 0.0
    inferred = positive_label
    if inferred is None:
        if any(isinstance(v, bool) for v in y_true):
            inferred = True
        elif any(isinstance(v, int) for v in y_true):
            inferred = 1
        else:
            raise ValueError(
                "positive_label must be provided for non-bool/non-int labels"
            )
    yb: List[int] = [1 if v == inferred else 0 for v in y_true]
    scores = _finite_scores(y_scores)
    # Clamp to [0,1]
    scores = [0.0 if s < 0.0 else 1.0 if s > 1.0 else s for s in scores]
    # Bin edges

    ece = 0.0
    for b in range(bin_count):
        lo = b / bin_count
        hi = (b + 1) / bin_count
        idxs = [
            i
            for i, s in enumerate(scores)
            if (s >= lo and (s < hi or (b == bin_count - 1 and s <= hi)))
        ]
        if not idxs:
            continue
        conf = sum(scores[i] for i in idxs) / len(idxs)
        acc = sum(yb[i] for i in idxs) / len(idxs)
        ece += (len(idxs) / n) * abs(acc - conf)
    return float(ece)


# --- Optional: BERTScore (text similarity) ---


def bertscore_f1(
    refs: Sequence[str],
    cands: Sequence[str],
    *,
    model: str | None = None,
    lang: str | None = "en",
    rescale_with_baseline: bool = False,
) -> float:
    """Compute average BERTScore F1 over pairs of strings.

    This is an optional metric that requires the `bert-score` package.

    - Returns 0.0 for empty inputs.
    - Raises ValueError on length mismatch.
    - Lazily imports `bert_score` to avoid hard dependency.
    - `model` corresponds to `model_type` in bert-score; when not provided,
      `lang` (default 'en') guides the default model selection.
    """
    if len(refs) != len(cands):
        raise ValueError("refs and cands must have same length")
    n = len(refs)
    if n == 0:
        return 0.0
    try:
        from bert_score import score as _bs_score  # type: ignore
    except Exception as e:  # pragma: no cover - exercised only when missing
        raise ImportError(
            "bertscore_f1 requires the 'bert-score' package. Install via 'uv add bert-score' or 'pip install bert-score'."
        ) from e

    # bert_score.score expects (cands, refs)
    P, R, F1 = _bs_score(
        list(cands),
        list(refs),
        model_type=model,
        lang=lang,
        rescale_with_baseline=rescale_with_baseline,
        verbose=False,
    )
    try:
        # Torch tensors: take mean over pairs
        return float(F1.mean().item())
    except Exception:
        # Fallback in case different tensor type; convert to python floats first
        vals = [float(x) for x in F1]
        return sum(vals) / float(len(vals))


def bertscore_f1_macro(
    refs: Sequence[str],
    cands: Sequence[str],
    *,
    model: str | None = None,
    lang: str | None = "en",
    rescale_with_baseline: bool = False,
) -> float:
    """Alias of bertscore_f1 for consistency with other text metrics.

    BERTScore is defined per pair; we aggregate by simple mean across pairs.
    """
    return bertscore_f1(
        refs,
        cands,
        model=model,
        lang=lang,
        rescale_with_baseline=rescale_with_baseline,
    )


# --- ROC Curve ---


def roc_curve_binary(
    y_true: Sequence[object],
    y_scores: Sequence[object],
    *,
    positive_label: object | None = None,
) -> Dict[str, List[float]]:
    """Compute ROC curve points (thresholds, tpr, fpr) for binary classification.

    - thresholds sorted descending over unique scores.
    - Returns dict with keys: thresholds, tpr, fpr.
    """
    if len(y_true) != len(y_scores):
        raise ValueError("y_true and y_scores must have the same length")
    n = len(y_true)
    if n == 0:
        return {"thresholds": [], "tpr": [], "fpr": []}
    inferred = positive_label
    if inferred is None:
        if any(isinstance(v, bool) for v in y_true):
            inferred = True
        elif any(isinstance(v, int) for v in y_true):
            inferred = 1
        else:
            raise ValueError(
                "positive_label must be provided for non-bool/non-int labels"
            )
    yb: List[int] = [1 if v == inferred else 0 for v in y_true]
    scores = _finite_scores(y_scores)
    # Sort by score descending
    order = sorted(range(n), key=lambda i: scores[i], reverse=True)
    sorted_scores = [scores[i] for i in order]
    sorted_true = [yb[i] for i in order]
    thresholds = sorted(set(sorted_scores), reverse=True)
    tpr: List[float] = []
    fpr: List[float] = []
    P = sum(yb)
    N = n - P
    tp = 0
    fp = 0
    i = 0
    for thr in thresholds:
        while i < n and sorted_scores[i] >= thr:
            if sorted_true[i] == 1:
                tp += 1
            else:
                fp += 1
            i += 1
        tpr.append(tp / P if P > 0 else 0.0)
        fpr.append(fp / N if N > 0 else 0.0)
    return {"thresholds": thresholds, "tpr": tpr, "fpr": fpr}

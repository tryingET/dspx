"""Reference solution PY-02 (calibration only)."""

from __future__ import annotations

import math

SEMANTIC_DISTANCE_NORMALIZER = 2.0
STABILITY_DISTANCE_MULTIPLIER = 2.0
VARIANCE_PENALTY_WEIGHT = 0.3


def _cosine_similarity(vec_a, vec_b):
    if not vec_a:
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    na = math.sqrt(sum(a * a for a in vec_a))
    nb = math.sqrt(sum(b * b for b in vec_b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _semantic_distance(vec_a, vec_b):
    return 1.0 - _cosine_similarity(vec_a, vec_b)


def _centroid(vecs_with_dim):
    # vecs_with_dim: list of (vector, dimension)
    if not vecs_with_dim:
        return []
    dim = vecs_with_dim[0][1]
    centroid = [0.0] * dim
    for v, _ in vecs_with_dim:
        for i, x in enumerate(v):
            centroid[i] += x
    n = len(vecs_with_dim)
    centroid = [x / n for x in centroid]
    norm = sum(x * x for x in centroid) ** 0.5
    if norm > 0:
        centroid = [x / norm for x in centroid]
    return centroid


def _text_set_variance(texts):
    if len(texts) < 2:
        return 0.0
    lengths = [len(t) for t in texts]
    avg_len = sum(lengths) / len(lengths)
    if avg_len == 0:
        return 0.0
    variance = sum((l - avg_len) ** 2 for l in lengths) / len(lengths)
    return min(1.0, variance / (avg_len ** 2 + 1))


def _stability_score(records):
    if len(records) < 2:
        return -1.0 if len(records) == 1 else 0.0
    centroid = _centroid([(r["vector"], len(r["vector"])) for r in records])
    total = 0.0
    for r in records:
        total += _semantic_distance(r["vector"], centroid) / SEMANTIC_DISTANCE_NORMALIZER
    avg_dist = total / len(records)
    stability = max(0.0, 1.0 - avg_dist * STABILITY_DISTANCE_MULTIPLIER)
    input_texts = [r.get("input_text", "") for r in records if r.get("input_text", "")]
    if len(input_texts) >= 2:
        stability *= max(0.0, 1.0 - _text_set_variance(input_texts) * VARIANCE_PENALTY_WEIGHT)
    output_texts = [r.get("output_text", "") for r in records if r.get("output_text", "")]
    if len(output_texts) >= 2:
        stability *= max(0.0, 1.0 - _text_set_variance(output_texts) * VARIANCE_PENALTY_WEIGHT)
    return max(0.0, min(1.0, stability))


def _convergence_rate(records):
    if len(records) < 2:
        return 0.0
    total = 0.0
    count = 0
    for i, a in enumerate(records):
        for b in records[i + 1:]:
            if len(a["vector"]) != len(b["vector"]):
                continue
            total += _semantic_distance(a["vector"], b["vector"]) / SEMANTIC_DISTANCE_NORMALIZER
            count += 1
    return total / count if count else 0.0


def _internal_variance(records):
    if len(records) < 2:
        return -1.0 if len(records) == 1 else 0.0
    centroid = _centroid([(r["vector"], len(r["vector"])) for r in records])
    total = 0.0
    for r in records:
        total += _semantic_distance(r["vector"], centroid) / SEMANTIC_DISTANCE_NORMALIZER
    return min(1.0, total / len(records))


def stability_summary(records):
    return {
        "stability": round(_stability_score(records), 6),
        "convergence_rate": round(_convergence_rate(records), 6),
        "internal_variance": round(_internal_variance(records), 6),
        "single_stability": _stability_score(records[:1]),
        "empty_variance": _internal_variance([]),
    }

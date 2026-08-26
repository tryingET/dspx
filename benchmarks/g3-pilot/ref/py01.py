"""Reference solution PY-01 (calibration only; not shown to executors)."""

from __future__ import annotations

import math

SEMANTIC_DISTANCE_NORMALIZER = 2.0

DRIFT_THRESHOLDS = {
    "identical": 0.05,
    "minor": 0.15,
    "moderate": 0.30,
    "significant": 0.50,
}


def _cosine_similarity(vec_a, vec_b):
    if len(vec_a) != len(vec_b):
        raise ValueError("dimension mismatch")
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


def _classify_drift(score):
    if score < DRIFT_THRESHOLDS["identical"]:
        return "identical"
    elif score < DRIFT_THRESHOLDS["minor"]:
        return "minor"
    elif score < DRIFT_THRESHOLDS["moderate"]:
        return "moderate"
    elif score < DRIFT_THRESHOLDS["significant"]:
        return "significant"
    return "severe"


def _centroid(vectors):
    if not vectors:
        return []
    dim = len(vectors[0])
    centroid = [0.0] * dim
    for v in vectors:
        for i, x in enumerate(v):
            centroid[i] += x
    n = len(vectors)
    centroid = [x / n for x in centroid]
    norm = sum(x * x for x in centroid) ** 0.5
    if norm > 0:
        centroid = [x / norm for x in centroid]
    return centroid


def drift_triage(records):
    vectors = [r["vector"] for r in records]
    centroid = _centroid(vectors)
    entries = []
    for r in records:
        d = _semantic_distance(r["vector"], centroid) / SEMANTIC_DISTANCE_NORMALIZER
        entries.append({"run_id": r["run_id"], "distance": round(d, 6),
                        "class": _classify_drift(d)})
    return {
        "centroid": centroid,
        "entries": entries,
        "severe": [e["run_id"] for e in entries if e["class"] == "severe"],
    }

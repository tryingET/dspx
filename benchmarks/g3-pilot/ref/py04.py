"""Reference solution PY-04 (calibration only): classify_region reproduction."""

from __future__ import annotations

import math

SEMANTIC_DISTANCE_NORMALIZER = 2.0
MIN_SAMPLES_FOR_CONFIDENCE = 5
STABILITY_THRESHOLD_LOW = 0.15
STABILITY_THRESHOLD_HIGH = 0.35
BASE_CONFIDENCE = 0.7
VARIANCE_MIDPOINT = 0.25
DANGER_ZONE_BASE_CONFIDENCE = 0.9


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


def _internal_variance(vectors):
    if len(vectors) < 2:
        return -1.0 if len(vectors) == 1 else 0.0
    centroid = _centroid(vectors)
    total = 0.0
    for v in vectors:
        total += _semantic_distance(v, centroid) / SEMANTIC_DISTANCE_NORMALIZER
    return min(1.0, total / len(vectors))


def _classify_region(vectors, danger_zones=None):
    n = len(vectors)
    if n == 0:
        return "unknown", 0.0
    if n < MIN_SAMPLES_FOR_CONFIDENCE:
        variance = _internal_variance(vectors)
        if variance < 0:
            return "unknown", 0.1
        elif variance < STABILITY_THRESHOLD_LOW:
            return "unknown", 0.4
        elif variance > STABILITY_THRESHOLD_HIGH:
            return "unknown", 0.4
        else:
            return "unknown", 0.3
    variance = _internal_variance(vectors)
    if danger_zones:
        centroid = _centroid(vectors)
        for zone in danger_zones:
            dist = _semantic_distance(centroid, zone["centroid"]) / SEMANTIC_DISTANCE_NORMALIZER
            if dist < zone["radius"]:
                return "danger", DANGER_ZONE_BASE_CONFIDENCE
    if variance < STABILITY_THRESHOLD_LOW:
        confidence = min(1.0, BASE_CONFIDENCE + (STABILITY_THRESHOLD_LOW - variance) * 2)
        return "stable", confidence
    elif variance > STABILITY_THRESHOLD_HIGH:
        confidence = min(1.0, BASE_CONFIDENCE + (variance - STABILITY_THRESHOLD_HIGH) * 2)
        return "unstable", confidence
    else:
        confidence = 0.5 + abs(variance - VARIANCE_MIDPOINT)
        return "stable", min(confidence, BASE_CONFIDENCE)


def classify_groups(groups, danger_zones=None):
    out = []
    for g in groups:
        vectors = [r["vector"] for r in g]
        t, c = _classify_region(vectors, danger_zones)
        out.append({"type": t, "confidence": round(c, 4)})
    return out

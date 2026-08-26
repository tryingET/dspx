"""Reference solution PY-05 (calibration only): attractor pipeline reproduction."""
from __future__ import annotations

import math
import random

SEMANTIC_DISTANCE_NORMALIZER = 2.0
MIN_SAMPLES_FOR_ATTRACTOR = 5
STABILITY_THRESHOLD_STRONG = 0.9
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
    vectors = [r["vector"] for r in records]
    centroid = _centroid(vectors)
    total = 0.0
    for v in vectors:
        total += _semantic_distance(v, centroid) / SEMANTIC_DISTANCE_NORMALIZER
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


def _average_internal_distance(vectors):
    if len(vectors) < 2:
        return -1.0 if len(vectors) == 1 else 0.0
    total = 0.0
    count = 0
    for i, a in enumerate(vectors):
        for b in vectors[i + 1:]:
            total += _semantic_distance(a, b)
            count += 1
    return (total / count) / SEMANTIC_DISTANCE_NORMALIZER if count > 0 else 0.0


def _simple_kmeans(records, k=10, max_iterations=50, convergence_threshold=0.001, seed=42):
    if not records:
        return []
    n = len(records)
    k = min(k, n)
    vectors = [list(r["vector"]) for r in records]
    rng = random.Random(seed)
    centroids = []
    first_idx = rng.randint(0, n - 1)
    centroids.append(vectors[first_idx].copy())
    for _ in range(1, k):
        distances = []
        for v in vectors:
            min_dist = float("inf")
            for c in centroids:
                d = _semantic_distance(v, c)
                min_dist = min(min_dist, d)
            distances.append(min_dist ** 2)
        total = sum(distances)
        if total == 0:
            remaining = [i for i in range(n) if vectors[i] not in centroids]
            if remaining:
                idx = rng.choice(remaining)
                centroids.append(vectors[idx].copy())
            else:
                break
        else:
            probs = [d / total for d in distances]
            idx = rng.choices(range(n), weights=probs, k=1)[0]
            centroids.append(vectors[idx].copy())
    if not centroids:
        return []
    assignments = [0] * n
    k = len(centroids)
    for _iteration in range(max_iterations):
        for i, v in enumerate(vectors):
            min_dist = float("inf")
            best = 0
            for j, c in enumerate(centroids):
                d = _semantic_distance(v, c)
                if d < min_dist:
                    min_dist = d
                    best = j
            assignments[i] = best
        new_centroids = []
        converged = True
        for j in range(k):
            members = [vectors[i] for i in range(n) if assignments[i] == j]
            if members:
                new_centroid = _compute_centroid_(members)
            else:
                max_min_dist = -1
                new_centroid = centroids[j]
                for v in vectors:
                    min_dist = min(_semantic_distance(v, centroids[c]) for c in range(k) if c != j)
                    if min_dist > max_min_dist:
                        max_min_dist = min_dist
                        new_centroid = v.copy()
            if converged:
                movement = math.sqrt(sum((a - b) ** 2 for a, b in zip(new_centroid, centroids[j])))
                if movement > convergence_threshold:
                    converged = False
            new_centroids.append(new_centroid)
        centroids = new_centroids
        if converged:
            break
    clusters = []
    for j in range(k):
        member_records = [records[i] for i in range(n) if assignments[i] == j]
        if not member_records:
            continue
        member_ids = [r["run_id"] for r in member_records]
        avg_dist = _average_internal_distance([r["vector"] for r in member_records])
        kind_counts = {}
        provider_counts = {}
        for r in member_records:
            kind_counts[r["run_kind"]] = kind_counts.get(r["run_kind"], 0) + 1
            provider_counts[r["provider"]] = provider_counts.get(r["provider"], 0) + 1
        clusters.append({
            "centroid": centroids[j],
            "member_ids": member_ids,
            "member_count": len(member_ids),
            "avg_internal_distance": avg_dist,
            "dominant_run_kind": max(kind_counts.items(), key=lambda x: x[1])[0] if kind_counts else None,
            "dominant_provider": max(provider_counts.items(), key=lambda x: x[1])[0] if provider_counts else None,
        })
    clusters.sort(key=lambda c: c["member_count"], reverse=True)
    return clusters


def _compute_centroid_(vectors):
    return _centroid(vectors)


def attractor_landscape(records, k=3, min_stability=0.5, min_samples=MIN_SAMPLES_FOR_ATTRACTOR):
    if len(records) < min_samples:
        attractors = []
        avg_stability = 0.0
        strong_count = 0
        coverage = 0.0
    else:
        clusters = _simple_kmeans(records, k=k, seed=42)
        attractors = []
        for cluster in clusters:
            if cluster["member_count"] < min_samples:
                continue
            cluster_records = [r for r in records if r["run_id"] in set(cluster["member_ids"])]
            stability = _stability_score(cluster_records)
            convergence = _convergence_rate(cluster_records)
            if stability < 0 or stability < min_stability:
                continue
            max_dist = 0.0
            for r in cluster_records:
                dist = _semantic_distance(r["vector"], cluster["centroid"]) / SEMANTIC_DISTANCE_NORMALIZER
                max_dist = max(max_dist, dist)
            attractors.append({
                "attractor_id": f"A{len(attractors):03d}",
                "centroid": cluster["centroid"],
                "basin_radius": max_dist,
                "member_run_ids": cluster["member_ids"],
                "member_count": cluster["member_count"],
                "stability_score": stability,
                "dominant_run_kind": cluster["dominant_run_kind"],
                "dominant_provider": cluster["dominant_provider"],
            })
        attractors.sort(key=lambda a: a["stability_score"], reverse=True)
        for i, a in enumerate(attractors):
            a["attractor_id"] = f"A{i:03d}"
        if attractors:
            avg_stability = sum(a["stability_score"] for a in attractors) / len(attractors)
            strong_count = len([a for a in attractors if a["stability_score"] >= STABILITY_THRESHOLD_STRONG])
            estimated_unique = min(sum(a["member_count"] for a in attractors), len(records))
            coverage = estimated_unique / len(records) if records else 0.0
        else:
            avg_stability = 0.0
            strong_count = 0
            coverage = 0.0

    if not attractors:
        health = {
            "status": "no_data",
            "message": "No attractors detected - need more execution data",
            "recommendations": ["Run more executions to build attractor map"],
        }
    else:
        strong_ratio = strong_count / len(attractors)
        if avg_stability >= 0.8 and strong_ratio >= 0.5:
            status = "healthy"
            message = "Strong attractor landscape with stable behaviors"
        elif avg_stability >= 0.6:
            status = "moderate"
            message = "Moderate attractor stability - some areas need attention"
        else:
            status = "weak"
            message = "Weak attractors - system behavior is unpredictable"
        recommendations = []
        if avg_stability < 0.7:
            recommendations.append("Investigate high-variance execution clusters")
        if coverage < 0.5:
            recommendations.append("Many executions outside attractor basins - expand coverage")
        if strong_ratio < 0.3:
            recommendations.append("Few strong attractors - increase test coverage for stable regions")
        health = {
            "status": status,
            "message": message,
            "avg_stability": avg_stability,
            "strong_attractor_ratio": strong_ratio,
            "coverage": coverage,
            "recommendations": recommendations,
        }

    def r6(x):
        return round(x, 6) if isinstance(x, float) else x

    return {
        "attractors": [{"attractor_id": a["attractor_id"],
                        "member_run_ids": a["member_run_ids"],
                        "member_count": a["member_count"],
                        "stability_score": round(a["stability_score"], 4),
                        "basin_radius": round(a["basin_radius"], 4),
                        "dominant_run_kind": a["dominant_run_kind"],
                        "dominant_provider": a["dominant_provider"]} for a in attractors],
        "total_embeddings": len(records),
        "avg_stability": round(avg_stability, 4),
        "strong_attractor_count": strong_count,
        "coverage": round(coverage, 4),
        "health": {k2: (r6(v) if not isinstance(v, list) else v) for k2, v in health.items()},
    }

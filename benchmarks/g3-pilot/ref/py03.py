"""Reference solution PY-03 (calibration only): exact simple_kmeans reproduction."""

from __future__ import annotations

import math
import random

SEMANTIC_DISTANCE_NORMALIZER = 2.0


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


def _compute_centroid(vectors):
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


def _simple_kmeans(records, k=5, max_iterations=50, convergence_threshold=0.001, seed=42):
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
                new_centroid = _compute_centroid(members)
            else:
                max_min_dist = -1
                new_centroid = centroids[j]
                for v in vectors:
                    min_dist = min(
                        _semantic_distance(v, centroids[c])
                        for c in range(k) if c != j
                    )
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
        member_vectors = [r["vector"] for r in member_records]
        avg_dist = _average_internal_distance(member_vectors)
        kind_counts = {}
        provider_counts = {}
        for r in member_records:
            kind_counts[r["run_kind"]] = kind_counts.get(r["run_kind"], 0) + 1
            provider_counts[r["provider"]] = provider_counts.get(r["provider"], 0) + 1
        dominant_kind = max(kind_counts.items(), key=lambda x: x[1])[0] if kind_counts else None
        dominant_provider = max(provider_counts.items(), key=lambda x: x[1])[0] if provider_counts else None
        clusters.append({
            "cluster_id": j,
            "member_run_ids": member_ids,
            "member_count": len(member_ids),
            "avg_internal_distance": avg_dist,
            "dominant_run_kind": dominant_kind,
            "dominant_provider": dominant_provider,
        })
    clusters.sort(key=lambda c: c["member_count"], reverse=True)
    for i, c in enumerate(clusters):
        c["cluster_id"] = i
    return clusters


def kmeans_partition(records, k=3):
    return {"clusters": [
        {**c, "avg_internal_distance": round(c["avg_internal_distance"], 6)}
        for c in _simple_kmeans(records, k=k)
    ]}

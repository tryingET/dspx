# summary: "Deterministic k-means clustering utilities for execution embeddings."
# read_when:
#   - "Changing coordinate centroids, cluster assignment, distance aggregation, or embedding classification."

"""Clustering utilities for semantic coordinates.

Groups similar executions together to identify patterns, behaviors,
and behavioral regions in semantic space.
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .metrics import (
    semantic_distance,
    DimensionMismatchError,
    SEMANTIC_DISTANCE_NORMALIZER,
)

if TYPE_CHECKING:
    from .embeddings import ExecutionEmbedding
    from .storage import CoordinateIndex

logger = logging.getLogger(__name__)


@dataclass
class Cluster:
    """A cluster of similar executions."""

    cluster_id: int
    centroid: list[float]
    member_ids: list[str]
    member_count: int
    avg_internal_distance: float
    dominant_run_kind: str | None
    dominant_provider: str | None
    sample_inputs: list[str]
    dimension: int  # NEW: Track dimension

    def to_dict(self) -> dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "member_count": self.member_count,
            "avg_internal_distance": self.avg_internal_distance,
            "dominant_run_kind": self.dominant_run_kind,
            "dominant_provider": self.dominant_provider,
            "sample_inputs": self.sample_inputs[:5],  # Limit samples
            "dimension": self.dimension,
        }


def compute_centroid(embeddings: list["ExecutionEmbedding"]) -> list[float]:
    """Compute centroid of a set of embeddings.

    BUG 22 FIX: Normalize centroid after computing mean.
    """
    if not embeddings:
        return []

    dim = embeddings[0].dimension
    centroid = [0.0] * dim

    for emb in embeddings:
        for i, v in enumerate(emb.vector):
            centroid[i] += v

    n = len(embeddings)
    centroid = [v / n for v in centroid]

    # Normalize to unit length (same as input vectors)
    norm = sum(v * v for v in centroid) ** 0.5
    if norm > 0:
        centroid = [v / norm for v in centroid]

    return centroid


def average_internal_distance(embeddings: list["ExecutionEmbedding"]) -> float:
    """Compute average pairwise distance within a cluster.

    Returns normalized distance in range [0, 1].
    Returns -1.0 for single embedding (distance undefined but distinguishable from 0.0).
    """
    if len(embeddings) < 2:
        return -1.0 if len(embeddings) == 1 else 0.0

    total_dist = 0.0
    count = 0

    for i, emb_a in enumerate(embeddings):
        for emb_b in embeddings[i + 1 :]:
            dist = semantic_distance(emb_a.vector, emb_b.vector)
            total_dist += dist
            count += 1

    # Normalize to [0, 1] range
    return (total_dist / count) / SEMANTIC_DISTANCE_NORMALIZER if count > 0 else 0.0


def simple_kmeans(
    embeddings: list["ExecutionEmbedding"],
    *,
    k: int = 5,
    max_iterations: int = 50,
    convergence_threshold: float = 0.001,
    seed: int | None = 42,  # BUG 20 FIX: Deterministic seeding
) -> list[Cluster]:
    """Simple k-means clustering implementation.

    For production use with large datasets, consider using scikit-learn
    or a dedicated clustering library.

    Args:
        embeddings: List of embeddings to cluster
        k: Number of clusters
        max_iterations: Maximum iterations
        convergence_threshold: Stop when centroid movement below this
        seed: Random seed for reproducibility (default: 42)

    Returns:
        List of Cluster objects
    """
    if not embeddings:
        return []

    n = len(embeddings)
    k = min(k, n)  # Can't have more clusters than items
    dim = embeddings[0].dimension

    # Validate all embeddings have same dimension
    for i, emb in enumerate(embeddings):
        if emb.dimension != dim:
            raise DimensionMismatchError(
                f"Embedding at index {i} has dimension {emb.dimension}, expected {dim}"
            )

    # BUG 20 FIX: Use proper random sampling with seed
    rng = random.Random(seed)

    # Initialize centroids using k-means++ style selection
    centroids: list[list[float]] = []

    # First centroid: random (but seeded)
    first_idx = rng.randint(0, n - 1)
    centroids.append(embeddings[first_idx].vector.copy())

    # Subsequent centroids: weighted random by distance from existing
    for _ in range(1, k):
        distances = []
        for emb in embeddings:
            # Find distance to nearest centroid
            min_dist = float("inf")
            for c in centroids:
                d = semantic_distance(emb.vector, c)
                min_dist = min(min_dist, d)
            distances.append(min_dist**2)  # Square for probability

        # Normalize to probabilities
        total = sum(distances)
        if total == 0:
            # All embeddings identical to existing centroids
            # Pick a random remaining one
            remaining = [i for i in range(n) if embeddings[i].vector not in centroids]
            if remaining:
                idx = rng.choice(remaining)
                centroids.append(embeddings[idx].vector.copy())
            else:
                break
        else:
            # BUG 20 FIX: Use weighted random instead of always picking max
            probs = [d / total for d in distances]
            idx = rng.choices(range(n), weights=probs, k=1)[0]
            centroids.append(embeddings[idx].vector.copy())

    if not centroids:
        return []

    # Iterative assignment and update
    assignments: list[int] = [0] * n
    k = len(centroids)  # May be less than requested

    for iteration in range(max_iterations):
        # Assignment step
        for i, emb in enumerate(embeddings):
            min_dist = float("inf")
            best_cluster = 0
            for j, centroid in enumerate(centroids):
                d = semantic_distance(emb.vector, centroid)
                if d < min_dist:
                    min_dist = d
                    best_cluster = j
            assignments[i] = best_cluster

        # Update step
        new_centroids = []
        converged = True

        for j in range(k):
            cluster_embeddings = [
                embeddings[i] for i in range(n) if assignments[i] == j
            ]

            if cluster_embeddings:
                new_centroid = compute_centroid(cluster_embeddings)
            else:
                # BUG 21 FIX: Reinitialize empty cluster centroid
                # Pick the point furthest from all existing centroids
                logger.debug(f"Cluster {j} became empty, reinitializing")
                max_min_dist = -1
                new_centroid = centroids[j]  # Default to keeping old
                for emb in embeddings:
                    min_dist = min(
                        semantic_distance(emb.vector, centroids[c])
                        for c in range(k)
                        if c != j
                    )
                    if min_dist > max_min_dist:
                        max_min_dist = min_dist
                        new_centroid = emb.vector.copy()

            # Check convergence
            if converged:
                movement = math.sqrt(
                    sum((a - b) ** 2 for a, b in zip(new_centroid, centroids[j]))
                )
                if movement > convergence_threshold:
                    converged = False

            new_centroids.append(new_centroid)

        centroids = new_centroids

        if converged:
            break

    # Build final clusters
    clusters: list[Cluster] = []

    for j in range(k):
        cluster_embeddings = [embeddings[i] for i in range(n) if assignments[i] == j]

        if not cluster_embeddings:
            continue

        member_ids = [emb.run_id for emb in cluster_embeddings]
        avg_dist = average_internal_distance(cluster_embeddings)

        # Find dominant run_kind and provider
        kind_counts: dict[str, int] = {}
        provider_counts: dict[str, int] = {}
        for emb in cluster_embeddings:
            kind_counts[emb.run_kind] = kind_counts.get(emb.run_kind, 0) + 1
            provider_counts[emb.provider] = provider_counts.get(emb.provider, 0) + 1

        dominant_kind = (
            max(kind_counts.items(), key=lambda x: x[1])[0] if kind_counts else None
        )
        dominant_provider = (
            max(provider_counts.items(), key=lambda x: x[1])[0]
            if provider_counts
            else None
        )

        # Sample inputs
        sample_inputs = [
            emb.input_text[:100] for emb in cluster_embeddings[:5] if emb.input_text
        ]

        clusters.append(
            Cluster(
                cluster_id=j,
                centroid=centroids[j],
                member_ids=member_ids,
                member_count=len(member_ids),
                avg_internal_distance=avg_dist,
                dominant_run_kind=dominant_kind,
                dominant_provider=dominant_provider,
                sample_inputs=sample_inputs,
                dimension=dim,
            )
        )

    # Sort by size (largest first)
    clusters.sort(key=lambda c: c.member_count, reverse=True)

    # Re-assign cluster IDs after sorting
    for i, cluster in enumerate(clusters):
        cluster.cluster_id = i

    return clusters


def cluster_from_index(
    index: "CoordinateIndex",
    *,
    k: int = 5,
    run_kind: str | None = None,
    provider: str | None = None,
    embedding_version: int | None = None,
    limit: int = 1000,
    seed: int | None = 42,
) -> list[Cluster]:
    """Cluster all embeddings from an index.

    Args:
        index: CoordinateIndex to cluster
        k: Number of clusters
        run_kind: Filter by run kind
        provider: Filter by provider
        embedding_version: Filter by embedding version
        limit: Maximum embeddings to cluster
        seed: Random seed for reproducibility

    Returns:
        List of Cluster objects
    """
    embeddings = index.list_all(
        run_kind=run_kind,
        provider=provider,
        embedding_version=embedding_version,
        limit=limit,
    )

    return simple_kmeans(embeddings, k=k, seed=seed)


def find_cluster_for_embedding(
    embedding: "ExecutionEmbedding",
    clusters: list[Cluster],
) -> tuple[int, float]:
    """Find which cluster an embedding belongs to.

    BUG 23 FIX: Validate dimension before computing.

    Args:
        embedding: Embedding to classify
        clusters: List of clusters

    Returns:
        Tuple of (cluster_id, distance_to_centroid) or (-1, inf) if no valid cluster

    Raises:
        DimensionMismatchError: If embedding dimension doesn't match cluster dimensions
    """
    if not clusters:
        return (-1, float("inf"))

    # Validate dimensions match
    cluster_dim = clusters[0].dimension
    if embedding.dimension != cluster_dim:
        raise DimensionMismatchError(
            f"Embedding dimension {embedding.dimension} doesn't match "
            f"cluster dimension {cluster_dim}"
        )

    best_cluster = -1
    best_distance = float("inf")

    for cluster in clusters:
        # Additional safety check
        if cluster.dimension != embedding.dimension:
            logger.warning(
                f"Cluster {cluster.cluster_id} has dimension {cluster.dimension}, "
                f"expected {embedding.dimension}. Skipping."
            )
            continue

        dist = (
            semantic_distance(embedding.vector, cluster.centroid)
            / SEMANTIC_DISTANCE_NORMALIZER
        )
        if dist < best_distance:
            best_distance = dist
            best_cluster = cluster.cluster_id

    return (best_cluster, best_distance)

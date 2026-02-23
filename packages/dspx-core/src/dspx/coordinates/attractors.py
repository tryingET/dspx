"""Attractor detection for behavioral topology.

Attractors are regions of behavioral space where executions
naturally converge - indicating stable, repeatable behaviors.
Understanding attractors helps identify reliable system behaviors
and potential optimization targets.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .clustering import compute_centroid, simple_kmeans
from .metrics import semantic_distance, SEMANTIC_DISTANCE_NORMALIZER

if TYPE_CHECKING:
    from .embeddings import ExecutionEmbedding
    from .storage import CoordinateIndex

logger = logging.getLogger(__name__)


@dataclass
class Attractor:
    """An attractor basin in behavioral space.

    Attractors represent stable equilibria where similar inputs
    converge to similar outputs. Strong attractors indicate
    reliable, repeatable behavior.
    """

    attractor_id: str
    centroid: list[float]
    basin_radius: float  # Normalized radius of attraction basin
    member_count: int
    stability_score: float  # 0-1, higher = more stable
    convergence_rate: float  # How tightly outputs cluster
    dominant_run_kind: str | None
    dominant_provider: str | None
    sample_inputs: list[str]
    sample_outputs: list[str]
    dimension: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "attractor_id": self.attractor_id,
            "centroid": self.centroid[:10]
            if len(self.centroid) > 10
            else self.centroid,  # Truncate for readability
            "basin_radius": round(self.basin_radius, 4),
            "member_count": self.member_count,
            "stability_score": round(self.stability_score, 4),
            "convergence_rate": round(self.convergence_rate, 4),
            "dominant_run_kind": self.dominant_run_kind,
            "dominant_provider": self.dominant_provider,
            "sample_inputs": self.sample_inputs[:3],
            "sample_outputs": self.sample_outputs[:3],
            "dimension": self.dimension,
        }


@dataclass
class AttractorReport:
    """Report of detected attractors."""

    attractors: list[Attractor]
    total_embeddings: int
    avg_stability: float
    strong_attractor_count: int  # Stability > 0.9
    coverage: float  # Fraction of embeddings in attractor basins
    dimension: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_attractors": len(self.attractors),
            "total_embeddings": self.total_embeddings,
            "avg_stability": round(self.avg_stability, 4),
            "strong_attractor_count": self.strong_attractor_count,
            "coverage": round(self.coverage, 4),
            "dimension": self.dimension,
            "attractors": [a.to_dict() for a in self.attractors],
        }


# Thresholds for attractor classification
MIN_SAMPLES_FOR_ATTRACTOR = 5
STABILITY_THRESHOLD_STRONG = 0.9
STABILITY_THRESHOLD_MODERATE = 0.7
CONVERGENCE_THRESHOLD = 0.3  # Lower = tighter convergence

# Scoring weights
VARIANCE_PENALTY_WEIGHT = 0.3  # How much input/output variance reduces stability
STABILITY_DISTANCE_MULTIPLIER = 2.0  # Convert distance to stability (inverse)


def compute_stability_score(
    embeddings: list["ExecutionEmbedding"],
    *,
    check_input_variance: bool = True,
    check_output_variance: bool = True,
) -> float:
    """Compute stability score for a set of embeddings.

    Stability measures how consistently the system behaves
    within this region. High stability = predictable behavior.

    Args:
        embeddings: Embeddings in the region
        check_input_variance: Consider input variance in score
        check_output_variance: Consider output variance in score

    Returns:
        Stability score in [0, 1], higher = more stable.
        Returns 1.0 for single embedding (trivially stable by definition).
    """
    if len(embeddings) < 2:
        return 1.0 if len(embeddings) == 1 else 0.0

    # Compute internal variance
    centroid = compute_centroid(embeddings)
    total_dist = 0.0

    for emb in embeddings:
        dist = semantic_distance(emb.vector, centroid) / SEMANTIC_DISTANCE_NORMALIZER
        total_dist += dist

    avg_dist = total_dist / len(embeddings)

    # Convert to stability (inverse of variance)
    # Lower distance = higher stability
    stability = max(0.0, 1.0 - avg_dist * STABILITY_DISTANCE_MULTIPLIER)

    # Optionally check input/output variance separately
    if check_input_variance:
        input_texts = [emb.input_text for emb in embeddings if emb.input_text]
        if len(input_texts) >= 2:
            input_variance = _compute_text_set_variance(input_texts)
            stability *= max(
                0.0, 1.0 - input_variance * VARIANCE_PENALTY_WEIGHT
            )  # Clamp to prevent negative

    if check_output_variance:
        output_texts = [emb.output_text for emb in embeddings if emb.output_text]
        if len(output_texts) >= 2:
            output_variance = _compute_text_set_variance(output_texts)
            stability *= max(
                0.0, 1.0 - output_variance * VARIANCE_PENALTY_WEIGHT
            )  # Clamp to prevent negative

    return max(0.0, min(1.0, stability))


def _compute_text_set_variance(texts: list[str]) -> float:
    """Compute variance in a set of texts.

    Higher variance = more diverse texts = lower stability.
    """
    if len(texts) < 2:
        return 0.0

    # Use length variance as a simple proxy
    lengths = [len(t) for t in texts]
    avg_len = sum(lengths) / len(lengths)

    if avg_len == 0:
        return 0.0

    variance = sum((length - avg_len) ** 2 for length in lengths) / len(lengths)
    # Normalize to [0, 1] range
    normalized = min(1.0, variance / (avg_len**2 + 1))
    return normalized


def compute_convergence_rate(
    embeddings: list["ExecutionEmbedding"],
) -> float:
    """Compute how tightly outputs converge.

    Low convergence rate = outputs are very similar (good)
    High convergence rate = outputs diverge (bad)

    Returns:
        Convergence rate in [0, 1], lower = better convergence.
        Returns 0.0 for single embedding or no valid pairs.
    """
    if len(embeddings) < 2:
        return 0.0

    # Get all pairwise output distances
    total_dist = 0.0
    count = 0
    skipped = 0

    for i, emb_a in enumerate(embeddings):
        for emb_b in embeddings[i + 1 :]:
            if emb_a.dimension != emb_b.dimension:
                skipped += 1
                continue
            dist = (
                semantic_distance(emb_a.vector, emb_b.vector)
                / SEMANTIC_DISTANCE_NORMALIZER
            )
            total_dist += dist
            count += 1

    if count == 0:
        if skipped > 0:
            logger.warning(
                f"compute_convergence_rate: skipped {skipped} pairs due to dimension mismatch"
            )
        return 0.0

    return total_dist / count


def find_attractors(
    index: "CoordinateIndex",
    *,
    k: int = 10,
    min_stability: float = 0.5,
    min_samples: int = MIN_SAMPLES_FOR_ATTRACTOR,
    seed: int | None = 42,
) -> AttractorReport:
    """Find attractor basins in behavioral space.

    Args:
        index: CoordinateIndex to analyze
        k: Number of clusters to analyze
        min_stability: Minimum stability threshold
        min_samples: Minimum samples for attractor
        seed: Random seed

    Returns:
        AttractorReport with all detected attractors
    """
    embeddings = index.list_all(limit=10000)

    if len(embeddings) < min_samples:
        return AttractorReport(
            attractors=[],
            total_embeddings=len(embeddings),
            avg_stability=0.0,
            strong_attractor_count=0,
            coverage=0.0,
            dimension=0,
        )

    dim = embeddings[0].dimension

    # Cluster embeddings
    clusters = simple_kmeans(embeddings, k=k, seed=seed)

    # Build attractors from clusters
    attractors: list[Attractor] = []
    emb_by_id = {emb.run_id: emb for emb in embeddings}

    for cluster in clusters:
        if cluster.member_count < min_samples:
            continue

        # Get embeddings for this cluster
        cluster_embeddings = [
            emb_by_id[rid] for rid in cluster.member_ids if rid in emb_by_id
        ]

        # Compute stability and convergence
        stability = compute_stability_score(cluster_embeddings)
        convergence = compute_convergence_rate(cluster_embeddings)

        # Skip low-stability clusters
        if stability < min_stability:
            continue

        # Compute basin radius (max distance from centroid)
        max_dist = 0.0
        for emb in cluster_embeddings:
            dist = (
                semantic_distance(emb.vector, cluster.centroid)
                / SEMANTIC_DISTANCE_NORMALIZER
            )
            max_dist = max(max_dist, dist)

        # Build attractor
        # Use same embeddings for both sample lists (consistency)
        sample_embeddings = [
            emb for emb in cluster_embeddings[:5] if emb.input_text and emb.output_text
        ]
        if len(sample_embeddings) < 3:
            # Fall back to separate extraction if not enough complete samples
            sample_embeddings = cluster_embeddings[:5]

        attractor = Attractor(
            attractor_id=f"A{len(attractors):03d}",
            centroid=cluster.centroid,
            basin_radius=max_dist,
            member_count=cluster.member_count,
            stability_score=stability,
            convergence_rate=convergence,
            dominant_run_kind=cluster.dominant_run_kind,
            dominant_provider=cluster.dominant_provider,
            sample_inputs=[
                emb.input_text[:100] for emb in sample_embeddings if emb.input_text
            ],
            sample_outputs=[
                emb.output_text[:100] for emb in sample_embeddings if emb.output_text
            ],
            dimension=cluster.dimension,
        )
        attractors.append(attractor)

    # Sort by stability (descending)
    attractors.sort(key=lambda a: a.stability_score, reverse=True)

    # Reassign IDs after sorting
    for i, attractor in enumerate(attractors):
        attractor.attractor_id = f"A{i:03d}"

    # Compute statistics
    if attractors:
        avg_stability = sum(a.stability_score for a in attractors) / len(attractors)
        strong_count = len(
            [a for a in attractors if a.stability_score >= STABILITY_THRESHOLD_STRONG]
        )
        # Coverage: unique embeddings in attractors / total (avoid double-counting)
        # Use member_count as approximation (may slightly overestimate if basins overlap)
        estimated_unique = min(sum(a.member_count for a in attractors), len(embeddings))
        coverage = estimated_unique / len(embeddings) if embeddings else 0.0
    else:
        avg_stability = 0.0
        strong_count = 0
        coverage = 0.0

    return AttractorReport(
        attractors=attractors,
        total_embeddings=len(embeddings),
        avg_stability=avg_stability,
        strong_attractor_count=strong_count,
        coverage=coverage,
        dimension=dim,
    )


def find_nearest_attractor(
    embedding: "ExecutionEmbedding",
    attractors: list[Attractor],
) -> tuple[Attractor | None, float]:
    """Find the nearest attractor for an embedding.

    Args:
        embedding: Embedding to locate
        attractors: List of attractors to search

    Returns:
        Tuple of (attractor, distance) or (None, inf) if none found
    """
    if not attractors:
        return None, float("inf")

    best_attractor = None
    best_distance = float("inf")

    for attractor in attractors:
        if attractor.dimension != embedding.dimension:
            continue

        dist = (
            semantic_distance(embedding.vector, attractor.centroid)
            / SEMANTIC_DISTANCE_NORMALIZER
        )
        if dist < best_distance:
            best_distance = dist
            best_attractor = attractor

    return best_attractor, best_distance


def is_in_attractor_basin(
    embedding: "ExecutionEmbedding",
    attractor: Attractor,
) -> bool:
    """Check if an embedding is within an attractor's basin.

    Args:
        embedding: Embedding to check
        attractor: Attractor to check against

    Returns:
        True if embedding is within the attractor basin (strictly inside, not on boundary)
    """
    if attractor.dimension != embedding.dimension:
        return False

    dist = (
        semantic_distance(embedding.vector, attractor.centroid)
        / SEMANTIC_DISTANCE_NORMALIZER
    )
    # Use < for consistency with find_attractors which uses max_dist (exclusive boundary)
    return dist < attractor.basin_radius


def compute_attractor_health(report: AttractorReport) -> dict[str, Any]:
    """Compute health metrics for the attractor landscape.

    Args:
        report: AttractorReport to analyze

    Returns:
        Dict with health metrics
    """
    if not report.attractors:
        return {
            "status": "no_data",
            "message": "No attractors detected - need more execution data",
            "recommendations": ["Run more executions to build attractor map"],
        }

    strong_ratio = report.strong_attractor_count / len(report.attractors)

    # Determine overall status
    if report.avg_stability >= 0.8 and strong_ratio >= 0.5:
        status = "healthy"
        message = "Strong attractor landscape with stable behaviors"
    elif report.avg_stability >= 0.6:
        status = "moderate"
        message = "Moderate attractor stability - some areas need attention"
    else:
        status = "weak"
        message = "Weak attractors - system behavior is unpredictable"

    recommendations = []

    if report.avg_stability < 0.7:
        recommendations.append("Investigate high-variance execution clusters")

    if report.coverage < 0.5:
        recommendations.append(
            "Many executions outside attractor basins - expand coverage"
        )

    if strong_ratio < 0.3:
        recommendations.append(
            "Few strong attractors - increase test coverage for stable regions"
        )

    return {
        "status": status,
        "message": message,
        "avg_stability": report.avg_stability,
        "strong_attractor_ratio": strong_ratio,
        "coverage": report.coverage,
        "recommendations": recommendations,
    }


def predict_convergence(
    embedding: "ExecutionEmbedding",
    attractors: list[Attractor],
    *,
    confidence_thresholds: tuple[float, float, float] = (0.7, 0.5, 0.3),
) -> dict[str, Any]:
    """Predict which attractor an execution will converge to.

    Useful for predicting behavior before execution completes.

    Args:
        embedding: Embedding to predict
        attractors: Known attractors
        confidence_thresholds: (high, medium, low) thresholds for confidence interpretation

    Returns:
        Dict with prediction results including confidence level and uncertainty
    """
    high_thresh, medium_thresh, low_thresh = confidence_thresholds

    nearest, distance = find_nearest_attractor(embedding, attractors)

    if nearest is None:
        return {
            "predicted_attractor": None,
            "confidence": 0.0,
            "confidence_level": "none",
            "uncertainty": 1.0,
            "message": "No attractors available for prediction",
        }

    # Confidence based on distance and attractor stability
    # Closer to centroid + higher stability = higher confidence
    if distance < nearest.basin_radius:
        in_basin = True
        # Avoid division by near-zero when distance ≈ 0
        distance_ratio = distance / (nearest.basin_radius + 0.01)
        confidence = nearest.stability_score * (1.0 - distance_ratio)
    else:
        in_basin = False
        # Outside basin - lower confidence, with graceful decay
        excess_distance = distance - nearest.basin_radius + 0.01  # Add small epsilon
        confidence = nearest.stability_score * 0.5 / (1.0 + excess_distance)

    confidence = max(0.0, min(1.0, confidence))
    uncertainty = 1.0 - confidence

    # Interpret confidence level
    if confidence >= high_thresh:
        confidence_level = "high"
    elif confidence >= medium_thresh:
        confidence_level = "medium"
    elif confidence >= low_thresh:
        confidence_level = "low"
    else:
        confidence_level = "very_low"

    return {
        "predicted_attractor": nearest.attractor_id,
        "attractor_stability": nearest.stability_score,
        "distance": round(distance, 4),
        "in_basin": in_basin,
        "confidence": round(confidence, 4),
        "confidence_level": confidence_level,
        "uncertainty": round(uncertainty, 4),
        "expected_behavior": {
            "run_kind": nearest.dominant_run_kind,
            "provider": nearest.dominant_provider,
        },
    }

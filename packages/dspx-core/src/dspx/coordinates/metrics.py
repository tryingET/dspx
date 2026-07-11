# summary: "Computes vector similarity, semantic distance, behavioral drift, and embedding outliers."
# read_when:
#   - "Changing coordinate distance math, drift scoring or thresholds, or outlier detection."

"""Distance and similarity metrics for semantic coordinates.

Provides functions for measuring semantic distance between executions,
detecting behavioral drift, and scoring similarity.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .embeddings import ExecutionEmbedding


class DimensionMismatchError(ValueError):
    """Raised when vector dimensions don't match."""

    pass


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two vectors.

    Returns:
        Similarity score in range [-1, 1], where 1 means identical direction.
    """
    if len(vec_a) != len(vec_b):
        raise DimensionMismatchError(
            f"Vector dimension mismatch: {len(vec_a)} vs {len(vec_b)}"
        )

    if not vec_a:
        return 0.0

    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


def euclidean_distance(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute Euclidean distance between two vectors.

    Returns:
        Distance >= 0, where 0 means identical vectors.
    """
    if len(vec_a) != len(vec_b):
        raise DimensionMismatchError(
            f"Vector dimension mismatch: {len(vec_a)} vs {len(vec_b)}"
        )

    return math.sqrt(sum((a - b) ** 2 for a, b in zip(vec_a, vec_b)))


def semantic_distance(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute semantic distance from cosine similarity.

    Converts similarity to a distance metric where:
    - 0 = identical semantic meaning
    - 1 = orthogonal (unrelated)
    - 2 = opposite semantic meaning

    Returns:
        Distance in range [0, 2].
    """
    sim = cosine_similarity(vec_a, vec_b)
    return 1.0 - sim


# Normalization constant: semantic_distance ranges [0, 2], so divide by 2 for [0, 1]
SEMANTIC_DISTANCE_NORMALIZER = 2.0


def drift_score(
    baseline: "ExecutionEmbedding",
    comparison: "ExecutionEmbedding",
    *,
    weight_input: float = 0.5,
    weight_output: float = 0.4,
    weight_config: float = 0.1,
) -> dict[str, float]:
    """Compute behavioral drift score between two executions.

    Analyzes semantic drift across input, output, and config dimensions
    to provide a comprehensive drift assessment.

    IMPORTANT (BUG 8 DOCS): Component drift scores are computed by embedding
    individual fields separately, which creates vectors in a different semantic
    space than the combined embedding. These scores are approximate indicators
    of where drift is occurring, not precise measurements. The overall score
    based on the combined embedding is the authoritative drift metric.

    Args:
        baseline: The baseline execution to compare against
        comparison: The execution being evaluated for drift
        weight_input: Weight for input similarity in overall score
        weight_output: Weight for output similarity in overall score
        weight_config: Weight for config similarity in overall score

    Returns:
        Dict with drift metrics:
        - overall: Weighted drift score (0 = identical, 1 = completely different)
        - input_drift: Approximate drift in input semantics
        - output_drift: Approximate drift in output semantics
        - config_drift: Approximate drift in configuration
        - vector_distance: Raw vector distance normalized to [0, 1]
    """
    # Validate dimension match
    if baseline.dimension != comparison.dimension:
        raise DimensionMismatchError(
            f"Embedding dimension mismatch: baseline has {baseline.dimension}, "
            f"comparison has {comparison.dimension}"
        )

    # Normalize weights
    total_weight = weight_input + weight_output + weight_config
    if total_weight <= 0:
        raise ValueError("Weights must sum to a positive value")
    weight_input /= total_weight
    weight_output /= total_weight
    weight_config /= total_weight

    # Overall vector distance (authoritative metric)
    vector_distance = semantic_distance(baseline.vector, comparison.vector)

    # Compute per-component drift using partial embeddings
    # NOTE: These are in a different semantic space than the combined embedding
    engine = _get_engine()

    input_drift = 0.0
    if baseline.input_text and comparison.input_text:
        vec_a = engine.embed_text(baseline.input_text)
        vec_b = engine.embed_text(comparison.input_text)
        # BUG 9 FIX: Consistent normalization
        input_drift = semantic_distance(vec_a, vec_b) / SEMANTIC_DISTANCE_NORMALIZER

    output_drift = 0.0
    if baseline.output_text and comparison.output_text:
        vec_a = engine.embed_text(baseline.output_text)
        vec_b = engine.embed_text(comparison.output_text)
        output_drift = semantic_distance(vec_a, vec_b) / SEMANTIC_DISTANCE_NORMALIZER

    config_drift = 0.0
    if baseline.config_text and comparison.config_text:
        vec_a = engine.embed_text(baseline.config_text)
        vec_b = engine.embed_text(comparison.config_text)
        config_drift = semantic_distance(vec_a, vec_b) / SEMANTIC_DISTANCE_NORMALIZER
    elif baseline.config_text != comparison.config_text:
        # Config changed but one is empty - use moderate drift
        config_drift = 0.5

    # Weighted overall drift based on component scores
    # (This is separate from vector_distance which is the authoritative metric)
    component_weighted_drift = (
        weight_input * input_drift
        + weight_output * output_drift
        + weight_config * config_drift
    )

    # Use the combined embedding distance as the overall score
    # (more reliable than component-weighted)
    overall = vector_distance / SEMANTIC_DISTANCE_NORMALIZER

    return {
        "overall": overall,
        "component_weighted": component_weighted_drift,
        "input_drift": input_drift,
        "output_drift": output_drift,
        "config_drift": config_drift,
        "vector_distance": vector_distance / SEMANTIC_DISTANCE_NORMALIZER,
    }


def _get_engine():
    """Lazy import to avoid circular dependency."""
    from .embeddings import get_embedding_engine

    return get_embedding_engine()


# BUG 11 FIX: Documented drift classification thresholds
# Thresholds are based on empirical observation of semantic distance distributions
DRIFT_THRESHOLDS = {
    "identical": 0.05,  # < 5% drift - essentially the same
    "minor": 0.15,  # 5-15% drift - small variations
    "moderate": 0.30,  # 15-30% drift - noticeable change
    "significant": 0.50,  # 30-50% drift - substantial change
    # >= 50% drift is "severe"
}


def classify_drift(drift_score: float) -> str:
    """Classify drift score into a human-readable category.

    Thresholds are chosen based on semantic distance distributions:
    - identical: < 5% - within noise tolerance for most embeddings
    - minor: 5-15% - small variations, likely acceptable
    - moderate: 15-30% - noticeable change, may need review
    - significant: 30-50% - substantial change, likely needs attention
    - severe: > 50% - major behavioral change

    Args:
        drift_score: Drift score in range [0, 1]

    Returns:
        Classification: "identical", "minor", "moderate", "significant", "severe"
    """
    if drift_score < DRIFT_THRESHOLDS["identical"]:
        return "identical"
    elif drift_score < DRIFT_THRESHOLDS["minor"]:
        return "minor"
    elif drift_score < DRIFT_THRESHOLDS["moderate"]:
        return "moderate"
    elif drift_score < DRIFT_THRESHOLDS["significant"]:
        return "significant"
    else:
        return "severe"


def find_outliers(
    embeddings: list["ExecutionEmbedding"],
    *,
    threshold: float = 0.5,
    reference: "ExecutionEmbedding | None" = None,
) -> list[tuple[int, float]]:
    """Find embeddings that are outliers relative to a reference.

    Args:
        embeddings: List of embeddings to check
        threshold: Distance threshold for outlier detection (normalized [0,1])
        reference: Reference embedding (uses centroid if None)

    Returns:
        List of (index, distance) tuples for outliers, sorted by distance descending

    Raises:
        DimensionMismatchError: If embeddings have inconsistent dimensions
    """
    if not embeddings:
        return []

    # Validate all embeddings have same dimension
    dim = embeddings[0].dimension
    for i, emb in enumerate(embeddings):
        if emb.dimension != dim:
            raise DimensionMismatchError(
                f"Embedding at index {i} has dimension {emb.dimension}, expected {dim}"
            )

    # Calculate centroid if no reference provided
    if reference is None:
        centroid = [0.0] * dim
        for emb in embeddings:
            for i, v in enumerate(emb.vector):
                centroid[i] += v
        n = len(embeddings)
        centroid = [v / n for v in centroid]

        # BUG 10 FIX: Use valid timestamp for centroid pseudo-embedding
        from .embeddings import ExecutionEmbedding

        reference = ExecutionEmbedding(
            run_id="__centroid__",
            vector=centroid,
            input_text="",
            output_text="",
            config_text="",
            run_kind="centroid",
            provider="computed",
            template_version=None,
            created_at=datetime.now(timezone.utc).isoformat(),
            dimension=dim,
        )

    # Validate reference dimension matches
    if reference.dimension != dim:
        raise DimensionMismatchError(
            f"Reference embedding has dimension {reference.dimension}, expected {dim}"
        )

    outliers = []
    for i, emb in enumerate(embeddings):
        dist = (
            semantic_distance(reference.vector, emb.vector)
            / SEMANTIC_DISTANCE_NORMALIZER
        )
        if dist > threshold:
            outliers.append((i, dist))

    return sorted(outliers, key=lambda x: x[1], reverse=True)

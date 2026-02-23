"""Distance and similarity metrics for semantic coordinates.

Provides functions for measuring semantic distance between executions,
detecting behavioral drift, and scoring similarity.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .embeddings import ExecutionEmbedding


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two vectors.

    Returns:
        Similarity score in range [-1, 1], where 1 means identical direction.
    """
    if len(vec_a) != len(vec_b):
        raise ValueError(f"Vector dimension mismatch: {len(vec_a)} vs {len(vec_b)}")

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
        raise ValueError(f"Vector dimension mismatch: {len(vec_a)} vs {len(vec_b)}")

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

    Args:
        baseline: The baseline execution to compare against
        comparison: The execution being evaluated for drift
        weight_input: Weight for input similarity in overall score
        weight_output: Weight for output similarity in overall score
        weight_config: Weight for config similarity in overall score

    Returns:
        Dict with drift metrics:
        - overall: Weighted drift score (0 = identical, 1 = completely different)
        - input_drift: Drift in input semantics
        - output_drift: Drift in output semantics
        - config_drift: Drift in configuration
        - vector_distance: Raw vector distance
    """
    # Normalize weights
    total_weight = weight_input + weight_output + weight_config
    weight_input /= total_weight
    weight_output /= total_weight
    weight_config /= total_weight

    # Overall vector distance
    vector_distance = semantic_distance(baseline.vector, comparison.vector)

    # Compute per-component drift using partial embeddings
    engine = _get_engine()

    input_drift = 0.0
    if baseline.input_text and comparison.input_text:
        vec_a = engine.embed_text(baseline.input_text)
        vec_b = engine.embed_text(comparison.input_text)
        input_drift = semantic_distance(vec_a, vec_b) / 2.0  # Normalize to [0, 1]

    output_drift = 0.0
    if baseline.output_text and comparison.output_text:
        vec_a = engine.embed_text(baseline.output_text)
        vec_b = engine.embed_text(comparison.output_text)
        output_drift = semantic_distance(vec_a, vec_b) / 2.0  # Normalize to [0, 1]

    config_drift = 0.0
    if baseline.config_text and comparison.config_text:
        vec_a = engine.embed_text(baseline.config_text)
        vec_b = engine.embed_text(comparison.config_text)
        config_drift = semantic_distance(vec_a, vec_b) / 2.0  # Normalize to [0, 1]
    elif baseline.config_text != comparison.config_text:
        # Config changed but one is empty
        config_drift = 0.5

    # Weighted overall drift
    overall = (
        weight_input * input_drift
        + weight_output * output_drift
        + weight_config * config_drift
    )

    return {
        "overall": overall,
        "input_drift": input_drift,
        "output_drift": output_drift,
        "config_drift": config_drift,
        "vector_distance": vector_distance / 2.0,  # Normalize to [0, 1]
    }


def _get_engine():
    """Lazy import to avoid circular dependency."""
    from .embeddings import get_embedding_engine

    return get_embedding_engine()


def classify_drift(drift_score: float) -> str:
    """Classify drift score into a human-readable category.

    Args:
        drift_score: Drift score in range [0, 1]

    Returns:
        Classification: "identical", "minor", "moderate", "significant", "severe"
    """
    if drift_score < 0.05:
        return "identical"
    elif drift_score < 0.15:
        return "minor"
    elif drift_score < 0.30:
        return "moderate"
    elif drift_score < 0.50:
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
        threshold: Distance threshold for outlier detection
        reference: Reference embedding (uses centroid if None)

    Returns:
        List of (index, distance) tuples for outliers
    """
    if not embeddings:
        return []

    # Calculate centroid if no reference provided
    if reference is None:
        dim = embeddings[0].dimension
        centroid = [0.0] * dim
        for emb in embeddings:
            for i, v in enumerate(emb.vector):
                centroid[i] += v
        n = len(embeddings)
        centroid = [v / n for v in centroid]

        # Create pseudo-embedding for centroid
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
            created_at="",
            dimension=dim,
        )

    outliers = []
    for i, emb in enumerate(embeddings):
        dist = semantic_distance(reference.vector, emb.vector) / 2.0
        if dist > threshold:
            outliers.append((i, dist))

    return sorted(outliers, key=lambda x: x[1], reverse=True)

"""Semantic coordinates for DSPx behavioral oracle.

This module provides the foundation layer for transforming execution receipts
into navigable semantic space. Every execution becomes a point that can be
searched, compared, and analyzed.

Key components:
- embeddings: Convert (input, output, config) → vector
- metrics: Semantic distance, drift scoring
- clustering: Group similar executions
- storage: Persist and query coordinate index
"""

from __future__ import annotations

from .embeddings import (
    EmbeddingEngine,
    ExecutionEmbedding,
    get_embedding_engine,
)
from .metrics import (
    cosine_similarity,
    euclidean_distance,
    semantic_distance,
    drift_score,
    classify_drift,
    find_outliers,
)
from .storage import (
    CoordinateIndex,
    CoordinateRecord,
    SearchResult,
    get_default_index_path,
    parse_since,
)
from .clustering import (
    Cluster,
    compute_centroid,
    simple_kmeans,
    cluster_from_index,
    find_cluster_for_embedding,
)

__all__ = [
    # Embeddings
    "EmbeddingEngine",
    "ExecutionEmbedding",
    "get_embedding_engine",
    # Metrics
    "cosine_similarity",
    "euclidean_distance",
    "semantic_distance",
    "drift_score",
    "classify_drift",
    "find_outliers",
    # Storage
    "CoordinateIndex",
    "CoordinateRecord",
    "SearchResult",
    "get_default_index_path",
    "parse_since",
    # Clustering
    "Cluster",
    "compute_centroid",
    "simple_kmeans",
    "cluster_from_index",
    "find_cluster_for_embedding",
]

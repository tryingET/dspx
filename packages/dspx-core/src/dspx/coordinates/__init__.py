"""Semantic coordinates for DSPx behavioral oracle.

This module provides the foundation layer for transforming execution receipts
into navigable semantic space. Every execution becomes a point that can be
searched, compared, and analyzed.

Key components:
- embeddings: Convert (input, output, config) → vector
- metrics: Semantic distance, drift scoring
- clustering: Group similar executions
- storage: Persist and query coordinate index

Phase B additions:
- territory: Map behavioral space into regions (stable/unstable/unknown)
- contracts: Define and verify behavioral invariants
- frontiers: Detect unexplored input space
- attractors: Find naturally stable behaviors
"""

from __future__ import annotations

from .embeddings import (
    EmbeddingEngine,
    ExecutionEmbedding,
    EmbeddingValidationError,
    EmbeddingResult,
    get_embedding_engine,
    reset_embedding_engine,
    EMBEDDING_VERSION,
)
from .metrics import (
    cosine_similarity,
    euclidean_distance,
    semantic_distance,
    drift_score,
    classify_drift,
    find_outliers,
    DimensionMismatchError,
    DRIFT_THRESHOLDS,
    SEMANTIC_DISTANCE_NORMALIZER,
)
from .storage import (
    CoordinateIndex,
    CoordinateRecord,
    CoordinateStore,
    SearchResult,
    StoreHealth,
    StoreStats,
    SchemaVersionError,
    ParseSinceError,
    get_default_index_path,
    open_coordinate_store,
    parse_since,
    SCHEMA_VERSION,
)
from .postgres_store import (
    PostgresPgvectorCoordinateStore,
    StoreConfigurationError,
    StoreUnavailableError,
    configured_postgres_env_keys,
    redact_database_url,
)
from .clustering import (
    Cluster,
    compute_centroid,
    simple_kmeans,
    cluster_from_index,
    find_cluster_for_embedding,
)

# Phase B: Behavioral Topology
from .territory import (
    RegionType,
    Region,
    TerritoryMap,
    DangerZone,
    build_territory_map,
    find_region_for_embedding,
    detect_danger_zones,
    compute_internal_variance,
    classify_region,
    STABILITY_THRESHOLD_LOW,
    STABILITY_THRESHOLD_HIGH,
    MIN_SAMPLES_FOR_CONFIDENCE,
    NEIGHBOR_DISTANCE_THRESHOLD,
    BASE_CONFIDENCE,
    VARIANCE_MIDPOINT,
    DANGER_ZONE_BASE_CONFIDENCE,
)
from .contracts import (
    ContractSeverity,
    ContractStatus,
    ContractViolation,
    ContractResult,
    Contract,
    ContractRegistry,
    evaluate_contract,
    validate_no_pii,
    validate_output_format,
    validate_response_quality,
    create_default_contracts,
    save_contracts,
    load_contracts,
    VALIDATORS,
)
from .frontiers import (
    Frontier,
    FrontierReport,
    find_frontiers,
    find_sparse_regions,
    suggest_exploration,
)
from .attractors import (
    Attractor,
    AttractorReport,
    find_attractors,
    find_nearest_attractor,
    is_in_attractor_basin,
    compute_attractor_health,
    predict_convergence,
    compute_stability_score,
    compute_convergence_rate,
    MIN_SAMPLES_FOR_ATTRACTOR,
    STABILITY_THRESHOLD_STRONG,
    STABILITY_THRESHOLD_MODERATE,
    VARIANCE_PENALTY_WEIGHT,
    STABILITY_DISTANCE_MULTIPLIER,
)

__all__ = [
    # Embeddings
    "EmbeddingEngine",
    "ExecutionEmbedding",
    "EmbeddingValidationError",
    "EmbeddingResult",
    "get_embedding_engine",
    "reset_embedding_engine",
    "EMBEDDING_VERSION",
    # Metrics
    "cosine_similarity",
    "euclidean_distance",
    "semantic_distance",
    "drift_score",
    "classify_drift",
    "find_outliers",
    "DimensionMismatchError",
    "DRIFT_THRESHOLDS",
    "SEMANTIC_DISTANCE_NORMALIZER",
    # Storage
    "CoordinateIndex",
    "CoordinateRecord",
    "CoordinateStore",
    "SearchResult",
    "StoreHealth",
    "StoreStats",
    "PostgresPgvectorCoordinateStore",
    "StoreConfigurationError",
    "StoreUnavailableError",
    "configured_postgres_env_keys",
    "redact_database_url",
    "SchemaVersionError",
    "ParseSinceError",
    "get_default_index_path",
    "open_coordinate_store",
    "parse_since",
    "SCHEMA_VERSION",
    # Clustering
    "Cluster",
    "compute_centroid",
    "simple_kmeans",
    "cluster_from_index",
    "find_cluster_for_embedding",
    # Phase B: Territory
    "RegionType",
    "Region",
    "TerritoryMap",
    "DangerZone",
    "build_territory_map",
    "find_region_for_embedding",
    "detect_danger_zones",
    "compute_internal_variance",
    "classify_region",
    "STABILITY_THRESHOLD_LOW",
    "STABILITY_THRESHOLD_HIGH",
    "MIN_SAMPLES_FOR_CONFIDENCE",
    "NEIGHBOR_DISTANCE_THRESHOLD",
    "BASE_CONFIDENCE",
    "VARIANCE_MIDPOINT",
    "DANGER_ZONE_BASE_CONFIDENCE",
    # Phase B: Contracts
    "ContractSeverity",
    "ContractStatus",
    "ContractViolation",
    "ContractResult",
    "Contract",
    "ContractRegistry",
    "evaluate_contract",
    "validate_no_pii",
    "validate_output_format",
    "validate_response_quality",
    "create_default_contracts",
    "save_contracts",
    "load_contracts",
    "VALIDATORS",
    # Phase B: Frontiers
    "Frontier",
    "FrontierReport",
    "find_frontiers",
    "find_sparse_regions",
    "suggest_exploration",
    # Phase B: Attractors
    "Attractor",
    "AttractorReport",
    "find_attractors",
    "find_nearest_attractor",
    "is_in_attractor_basin",
    "compute_attractor_health",
    "predict_convergence",
    "compute_stability_score",
    "compute_convergence_rate",
    "MIN_SAMPLES_FOR_ATTRACTOR",
    "STABILITY_THRESHOLD_STRONG",
    "STABILITY_THRESHOLD_MODERATE",
    "VARIANCE_PENALTY_WEIGHT",
    "STABILITY_DISTANCE_MULTIPLIER",
]

"""Territory mapping for behavioral topology.

Maps semantic space into regions: stable, unstable, and unknown.
Territory analysis helps understand where the system is reliable vs.
where it needs more testing or investigation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from .clustering import simple_kmeans, compute_centroid
from .metrics import (
    semantic_distance,
    SEMANTIC_DISTANCE_NORMALIZER,
)

if TYPE_CHECKING:
    from .embeddings import ExecutionEmbedding
    from .storage import CoordinateIndex

logger = logging.getLogger(__name__)


class RegionType(Enum):
    """Types of behavioral regions."""

    STABLE = "stable"  # Low internal variance, well-tested
    UNSTABLE = "unstable"  # High variance, needs investigation
    UNKNOWN = "unknown"  # Insufficient data
    DANGER = "danger"  # Known problematic area
    FRONTIER = "frontier"  # Edge of explored space


@dataclass
class Region:
    """A region in behavioral space."""

    region_id: str
    region_type: RegionType
    centroid: list[float]
    member_count: int
    internal_variance: float  # 0-1, lower is more stable
    confidence: float  # 0-1, how confident in classification
    dominant_run_kind: str | None
    dominant_provider: str | None
    sample_run_ids: list[str]  # First N for display
    all_member_ids: list[str] = field(
        default_factory=list
    )  # Full membership for lookup
    neighbors: list[str] = field(default_factory=list)  # Adjacent region IDs
    dimension: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "region_id": self.region_id,
            "region_type": self.region_type.value,
            "centroid": self.centroid[:10]
            if len(self.centroid) > 10
            else self.centroid,  # Truncate for readability
            "member_count": self.member_count,
            "internal_variance": round(self.internal_variance, 4),
            "confidence": round(self.confidence, 4),
            "dominant_run_kind": self.dominant_run_kind,
            "dominant_provider": self.dominant_provider,
            "sample_run_ids": self.sample_run_ids[:5],
            "all_member_ids": self.all_member_ids,  # Persist full membership for accurate lookup
            "neighbors": self.neighbors,
            "dimension": self.dimension,
            "metadata": self.metadata,
        }


@dataclass
class TerritoryMap:
    """Complete map of behavioral territory.

    Note: The 'coverage' field is a heuristic estimate based on cluster distribution
    and embedding density. It is NOT a mathematically rigorous coverage measure.
    In high-dimensional spaces, true coverage estimation requires more sophisticated
    techniques (e.g., hyperloglog-style cardinality estimation or density-based methods).
    Treat 'coverage' as a relative indicator for comparing states, not an absolute measure.
    """

    regions: list[Region]
    total_embeddings: int
    coverage: float  # Heuristic estimate of fraction of space mapped (see note above)
    dimension: int
    stable_ratio: float  # Fraction of regions that are stable
    unstable_ratio: float
    unknown_ratio: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_regions": len(self.regions),
            "total_embeddings": self.total_embeddings,
            "coverage": round(self.coverage, 4),
            "coverage_note": "heuristic estimate based on cluster distribution",
            "dimension": self.dimension,
            "stable_ratio": round(self.stable_ratio, 4),
            "unstable_ratio": round(self.unstable_ratio, 4),
            "unknown_ratio": round(self.unknown_ratio, 4),
            "regions": [r.to_dict() for r in self.regions],
        }

    def get_stable_regions(self) -> list[Region]:
        return [r for r in self.regions if r.region_type == RegionType.STABLE]

    def get_unstable_regions(self) -> list[Region]:
        return [r for r in self.regions if r.region_type == RegionType.UNSTABLE]

    def get_unknown_regions(self) -> list[Region]:
        return [r for r in self.regions if r.region_type == RegionType.UNKNOWN]

    def get_danger_regions(self) -> list[Region]:
        return [r for r in self.regions if r.region_type == RegionType.DANGER]

    def find_region_for_run_id(self, run_id: str) -> Region | None:
        """Find which region contains a given run_id.

        Args:
            run_id: The run ID to search for

        Returns:
            The Region containing this run_id, or None if not found
        """
        for region in self.regions:
            # Prefer full membership list for accurate lookup.
            pool = (
                region.all_member_ids
                if region.all_member_ids
                else region.sample_run_ids
            )
            if run_id in pool:
                return region
        return None

    def get_region_neighbors(self, region_id: str, max_depth: int = 1) -> list[Region]:
        """Get neighboring regions within max_depth hops.

        Args:
            region_id: Starting region ID
            max_depth: Maximum number of hops (1 = direct neighbors only)

        Returns:
            List of neighboring Region objects
        """
        visited: set[str] = {region_id}
        result: list[Region] = []
        current_frontier = {region_id}

        region_by_id = {r.region_id: r for r in self.regions}

        for _ in range(max_depth):
            next_frontier: set[str] = set()
            for rid in current_frontier:
                region = region_by_id.get(rid)
                if region:
                    for neighbor_id in region.neighbors:
                        if neighbor_id not in visited:
                            visited.add(neighbor_id)
                            neighbor = region_by_id.get(neighbor_id)
                            if neighbor:
                                result.append(neighbor)
                            next_frontier.add(neighbor_id)
            current_frontier = next_frontier

        return result


# Thresholds for region classification
STABILITY_THRESHOLD_LOW = 0.15  # Below this = stable
STABILITY_THRESHOLD_HIGH = 0.35  # Above this = unstable
MIN_SAMPLES_FOR_CONFIDENCE = 5  # Need this many for confident classification
HIGH_CONFIDENCE_THRESHOLD = 0.8

# Confidence scoring constants
BASE_CONFIDENCE = 0.7  # Base confidence for classification
VARIANCE_MIDPOINT = 0.25  # Midpoint variance for moderate stability
NEIGHBOR_DISTANCE_THRESHOLD = 0.5  # Distance threshold for region neighbors
DANGER_ZONE_BASE_CONFIDENCE = 0.9  # Confidence when in known danger zone


def compute_internal_variance(embeddings: list["ExecutionEmbedding"]) -> float:
    """Compute normalized internal variance of a set of embeddings.

    Returns value in [0, 1] where lower = more stable/consistent.
    Returns -1.0 for single embedding (variance undefined but distinguishable from 0.0).
    """
    if len(embeddings) < 2:
        return -1.0 if len(embeddings) == 1 else 0.0

    # Compute centroid
    centroid = compute_centroid(embeddings)

    # Compute average distance from centroid
    total_dist = 0.0
    for emb in embeddings:
        dist = semantic_distance(emb.vector, centroid) / SEMANTIC_DISTANCE_NORMALIZER
        total_dist += dist

    avg_dist = total_dist / len(embeddings)
    return min(1.0, avg_dist)  # Clamp to [0, 1]


def classify_region(
    embeddings: list["ExecutionEmbedding"],
    *,
    known_danger_zones: list["DangerZone"] | None = None,
) -> tuple[RegionType, float]:
    """Classify a region based on its embeddings.

    Args:
        embeddings: Embeddings in this region
        known_danger_zones: Known dangerous areas to check

    Returns:
        Tuple of (region_type, confidence)
    """
    n = len(embeddings)

    if n == 0:
        return RegionType.UNKNOWN, 0.0

    if n < MIN_SAMPLES_FOR_CONFIDENCE:
        # Not enough data for confident classification
        variance = compute_internal_variance(embeddings)

        # Distinguish based on variance even with low sample count
        if variance < 0:  # Single embedding
            return RegionType.UNKNOWN, 0.1  # Very low confidence - need more data
        elif variance < STABILITY_THRESHOLD_LOW:
            return RegionType.UNKNOWN, 0.4  # Probably stable but unsure
        elif variance > STABILITY_THRESHOLD_HIGH:
            return RegionType.UNKNOWN, 0.4  # Probably unstable but unsure
        else:
            return RegionType.UNKNOWN, 0.3  # Truly unknown behavior

    variance = compute_internal_variance(embeddings)

    # Check if in known danger zone
    if known_danger_zones:
        centroid = compute_centroid(embeddings)
        for zone in known_danger_zones:
            dist = (
                semantic_distance(centroid, zone.centroid)
                / SEMANTIC_DISTANCE_NORMALIZER
            )
            if dist < zone.radius:
                return RegionType.DANGER, DANGER_ZONE_BASE_CONFIDENCE

    # Classify based on variance
    if variance < STABILITY_THRESHOLD_LOW:
        confidence = min(
            1.0, BASE_CONFIDENCE + (STABILITY_THRESHOLD_LOW - variance) * 2
        )
        return RegionType.STABLE, confidence
    elif variance > STABILITY_THRESHOLD_HIGH:
        confidence = min(
            1.0, BASE_CONFIDENCE + (variance - STABILITY_THRESHOLD_HIGH) * 2
        )
        return RegionType.UNSTABLE, confidence
    else:
        # In between - moderate stability
        confidence = 0.5 + abs(
            variance - VARIANCE_MIDPOINT
        )  # Higher confidence at extremes
        return RegionType.STABLE, min(confidence, BASE_CONFIDENCE)


@dataclass
class DangerZone:
    """A known dangerous region in behavioral space."""

    zone_id: str
    centroid: list[float]
    radius: float  # Normalized distance
    reason: str
    severity: str  # "low", "medium", "high", "critical"
    dimension: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "zone_id": self.zone_id,
            "centroid": self.centroid,  # Required for reconstruction
            "radius": round(self.radius, 4),
            "reason": self.reason,
            "severity": self.severity,
            "dimension": self.dimension,
        }


def build_territory_map(
    index: "CoordinateIndex",
    *,
    k: int = 10,
    min_region_size: int = 3,
    known_danger_zones: list[DangerZone] | None = None,
    seed: int | None = 42,
) -> TerritoryMap:
    """Build a territory map from the coordinate index.

    Args:
        index: CoordinateIndex to analyze
        k: Number of regions to create
        min_region_size: Minimum embeddings per region
        known_danger_zones: Pre-defined danger zones
        seed: Random seed for reproducibility

    Returns:
        TerritoryMap with all regions classified
    """
    # Get all embeddings
    embeddings = index.list_all(limit=10000)

    if not embeddings:
        return TerritoryMap(
            regions=[],
            total_embeddings=0,
            coverage=0.0,
            dimension=0,
            stable_ratio=0.0,
            unstable_ratio=0.0,
            unknown_ratio=1.0,
        )

    dim = embeddings[0].dimension

    # Cluster embeddings
    clusters = simple_kmeans(embeddings, k=k, seed=seed)

    # Build regions from clusters
    regions: list[Region] = []
    unassigned_count = 0  # Track embeddings in skipped clusters
    region_id = 0

    # Create embedding lookup
    emb_by_id = {emb.run_id: emb for emb in embeddings}

    for cluster in clusters:
        if cluster.member_count < min_region_size:
            # Track embeddings from tiny clusters as unassigned
            unassigned_count += cluster.member_count
            continue

        # Get embeddings for this cluster
        cluster_embeddings = [
            emb_by_id[rid] for rid in cluster.member_ids if rid in emb_by_id
        ]

        # Classify the region
        region_type, confidence = classify_region(
            cluster_embeddings, known_danger_zones=known_danger_zones
        )

        # Build region
        region = Region(
            region_id=f"R{region_id:03d}",
            region_type=region_type,
            centroid=cluster.centroid,
            member_count=cluster.member_count,
            internal_variance=cluster.avg_internal_distance,
            confidence=confidence,
            dominant_run_kind=cluster.dominant_run_kind,
            dominant_provider=cluster.dominant_provider,
            sample_run_ids=cluster.member_ids[:10],
            all_member_ids=list(
                cluster.member_ids
            ),  # Full membership for accurate lookup
            dimension=cluster.dimension,
        )
        regions.append(region)
        region_id += 1

    # Compute neighbor relationships based on centroid distances
    for i, region_a in enumerate(regions):
        neighbors = []
        for j, region_b in enumerate(regions):
            if i == j:
                continue
            dist = (
                semantic_distance(region_a.centroid, region_b.centroid)
                / SEMANTIC_DISTANCE_NORMALIZER
            )
            # Consider neighbors if within threshold normalized distance
            if dist < NEIGHBOR_DISTANCE_THRESHOLD:
                neighbors.append(region_b.region_id)
        region_a.neighbors = neighbors

    # Compute statistics
    total = len(regions)
    if total == 0:
        stable_ratio = unstable_ratio = unknown_ratio = 0.0
    else:
        stable_count = len([r for r in regions if r.region_type == RegionType.STABLE])
        unstable_count = len(
            [r for r in regions if r.region_type == RegionType.UNSTABLE]
        )
        unknown_count = len([r for r in regions if r.region_type == RegionType.UNKNOWN])

        stable_ratio = stable_count / total
        unstable_ratio = unstable_count / total
        unknown_ratio = unknown_count / total

    # Estimate coverage based on cluster distribution and embedding density
    # Coverage is higher when more embeddings are in well-defined regions
    assigned_count = sum(r.member_count for r in regions)
    region_coverage = assigned_count / len(embeddings) if embeddings else 0.0
    # Combine region coverage with a density factor
    coverage = (
        region_coverage * (1.0 - (unassigned_count / len(embeddings)))
        if embeddings
        else 0.0
    )
    coverage = min(1.0, max(0.0, coverage))

    return TerritoryMap(
        regions=regions,
        total_embeddings=len(embeddings),
        coverage=coverage,
        dimension=dim,
        stable_ratio=stable_ratio,
        unstable_ratio=unstable_ratio,
        unknown_ratio=unknown_ratio,
    )


def find_region_for_embedding(
    embedding: "ExecutionEmbedding",
    territory: TerritoryMap,
) -> tuple[Region | None, float]:
    """Find which region an embedding belongs to.

    Args:
        embedding: Embedding to locate
        territory: Territory map to search

    Returns:
        Tuple of (region, distance) or (None, inf) if no match
    """
    if not territory.regions:
        return None, float("inf")

    best_region = None
    best_distance = float("inf")

    for region in territory.regions:
        if region.dimension != embedding.dimension:
            continue

        dist = (
            semantic_distance(embedding.vector, region.centroid)
            / SEMANTIC_DISTANCE_NORMALIZER
        )
        if dist < best_distance:
            best_distance = dist
            best_region = region

    return best_region, best_distance


def detect_danger_zones(
    index: "CoordinateIndex",
    *,
    failure_run_ids: list[str] | None = None,
    high_variance_threshold: float = 0.5,
) -> list[DangerZone]:
    """Detect potential danger zones from execution history.

    Danger zones are regions with:
    - High internal variance (unpredictable behavior)
    - Known failure points
    - Edge cases

    Args:
        index: CoordinateIndex to analyze
        failure_run_ids: Known failed run IDs
        high_variance_threshold: Threshold for high variance detection

    Returns:
        List of detected DangerZones
    """
    embeddings = index.list_all(limit=10000)

    if not embeddings:
        return []

    dim = embeddings[0].dimension
    emb_by_id = {emb.run_id: emb for emb in embeddings}

    danger_zones: list[DangerZone] = []

    # Detect high-variance regions
    clusters = simple_kmeans(embeddings, k=10, seed=42)

    for cluster in clusters:
        if cluster.avg_internal_distance > high_variance_threshold:
            zone = DangerZone(
                zone_id=f"high-variance-{cluster.cluster_id}",
                centroid=cluster.centroid,
                radius=cluster.avg_internal_distance,
                reason="High behavioral variance detected",
                severity="medium",
                dimension=cluster.dimension,
            )
            danger_zones.append(zone)

    # Detect failure clusters
    if failure_run_ids:
        # Validate run_ids exist before lookup
        failure_embeddings = [
            emb_by_id[rid] for rid in failure_run_ids if rid in emb_by_id
        ]
        missing_count = len(failure_run_ids) - len(failure_embeddings)
        if missing_count > 0:
            logger.warning(
                f"detect_danger_zones: {missing_count} failure_run_ids not found in index"
            )
        if len(failure_embeddings) >= 2:
            centroid = compute_centroid(failure_embeddings)
            # Compute radius to include all failures
            max_dist = 0.0
            for emb in failure_embeddings:
                dist = (
                    semantic_distance(emb.vector, centroid)
                    / SEMANTIC_DISTANCE_NORMALIZER
                )
                max_dist = max(max_dist, dist)

            zone = DangerZone(
                zone_id="failure-cluster",
                centroid=centroid,
                radius=max_dist * 1.2,  # Add 20% margin
                reason=f"Contains {len(failure_embeddings)} known failures",
                severity="high",
                dimension=dim,
            )
            danger_zones.append(zone)

    return danger_zones

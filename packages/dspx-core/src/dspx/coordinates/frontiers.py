# summary: "Finds sparse behavioral frontiers and ranks suggested semantic-space exploration targets."
# read_when:
#   - "Changing frontier detection, coverage heuristics, sparse-region analysis, or exploration suggestions."

"""Frontier detection for behavioral topology.

Frontiers represent the edges of explored behavioral space.
Identifying frontiers helps discover unexplored inputs and
potential gaps in test coverage.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .metrics import semantic_distance, SEMANTIC_DISTANCE_NORMALIZER

if TYPE_CHECKING:
    from .embeddings import ExecutionEmbedding
    from .storage import CoordinateIndex

logger = logging.getLogger(__name__)

# Frontier detection thresholds
ISOLATION_NORMALIZER = 0.5  # Distance threshold for isolation scoring
HIGH_ISOLATION_THRESHOLD = 0.6  # Above this = highly isolated
MODERATE_ISOLATION_THRESHOLD = 0.4  # Above this = moderately isolated
COVERAGE_DISTANCE_MULTIPLIER = 2.0  # Convert avg distance to coverage estimate

# Priority scoring weights
ISOLATION_WEIGHT = 0.7  # Weight for isolation score in priority calculation
RANK_WEIGHT = 0.3  # Weight for rank position in priority calculation


@dataclass
class Frontier:
    """A frontier point in behavioral space.

    Frontiers are points at the edge of explored space,
    indicating potential areas for exploration.
    """

    frontier_id: str
    point: list[float]  # Coordinates of frontier
    nearest_run_id: str  # Closest known execution
    distance_to_known: float  # How far from nearest known point
    suggested_input: str | None  # Suggested input to explore
    exploration_priority: float  # 0-1, higher = more important
    reason: str  # Why this frontier is interesting
    dimension: int
    explored: bool = False  # Whether this frontier has been investigated
    explored_by: str | None = None  # Who/what explored it
    explored_at: str | None = None  # When it was explored

    def mark_explored(self, by: str | None = None) -> None:
        """Mark this frontier as explored."""
        from datetime import datetime, timezone

        self.explored = True
        self.explored_by = by
        self.explored_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "frontier_id": self.frontier_id,
            "point": self.point[:10]
            if len(self.point) > 10
            else self.point,  # Truncate for readability
            "nearest_run_id": self.nearest_run_id,
            "distance_to_known": round(self.distance_to_known, 4),
            "suggested_input": self.suggested_input,
            "exploration_priority": round(self.exploration_priority, 4),
            "reason": self.reason,
            "dimension": self.dimension,
            "explored": self.explored,
            "explored_by": self.explored_by,
            "explored_at": self.explored_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Frontier":
        """Reconstruct a Frontier from its dictionary representation."""
        return cls(
            frontier_id=data["frontier_id"],
            point=data.get("point", []),
            nearest_run_id=data["nearest_run_id"],
            distance_to_known=data.get("distance_to_known", 0.0),
            suggested_input=data.get("suggested_input"),
            exploration_priority=data.get("exploration_priority", 0.0),
            reason=data.get("reason", ""),
            dimension=data.get("dimension", 0),
            explored=data.get("explored", False),
            explored_by=data.get("explored_by"),
            explored_at=data.get("explored_at"),
        )


@dataclass
class FrontierReport:
    """Report of all detected frontiers.

    Note: The 'coverage_estimate' field is a heuristic based on average distance
    between embeddings. In high-dimensional spaces, this is NOT a reliable measure
    of actual coverage. Treat as a relative indicator for comparing states.
    """

    frontiers: list[Frontier]
    total_embeddings: int
    coverage_estimate: float  # Heuristic estimate (0-1), see note above
    avg_distance_to_frontier: float
    high_priority_count: int
    _original_frontier_count: int = 0  # Track original count for serialization fidelity

    def to_dict(self) -> dict[str, Any]:
        # Serialize top 50 frontiers (increased from 20 for better fidelity)
        # but always include original count for reconstruction awareness
        max_serialize = 50
        serialized_frontiers = self.frontiers[:max_serialize]
        truncated = len(self.frontiers) > max_serialize

        return {
            "total_frontiers": len(self.frontiers),  # Actual count
            "total_embeddings": self.total_embeddings,
            "coverage_estimate": round(self.coverage_estimate, 4),
            "avg_distance_to_frontier": round(self.avg_distance_to_frontier, 4),
            "high_priority_count": self.high_priority_count,
            "unexplored_count": len(self.get_unexplored()),
            "truncated": truncated,
            "frontiers": [f.to_dict() for f in serialized_frontiers],
        }

    def get_unexplored(self) -> list[Frontier]:
        """Get all unexplored frontiers, sorted by priority."""
        return sorted(
            [f for f in self.frontiers if not f.explored],
            key=lambda f: f.exploration_priority,
            reverse=True,
        )

    def mark_explored(self, frontier_id: str, by: str | None = None) -> bool:
        """Mark a frontier as explored by ID.

        Returns True if frontier was found and marked, False otherwise.
        """
        for frontier in self.frontiers:
            if frontier.frontier_id == frontier_id:
                frontier.mark_explored(by)
                return True
        return False

    def get_exploration_progress(self) -> dict[str, Any]:
        """Get exploration progress summary."""
        total = len(self.frontiers)
        explored = sum(1 for f in self.frontiers if f.explored)
        unexplored = total - explored

        return {
            "total_frontiers": total,
            "explored": explored,
            "unexplored": unexplored,
            "progress_pct": round(explored / total * 100, 1) if total > 0 else 0.0,
            "remaining_high_priority": sum(
                1
                for f in self.frontiers
                if not f.explored and f.exploration_priority >= 0.5
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FrontierReport":
        """Reconstruct a FrontierReport from its dictionary representation.

        Note: If the original report was truncated, only the serialized frontiers
        are restored. Check the 'truncated' field in the source data to detect this.
        Statistics are preserved from the original serialization.
        """
        frontiers = [Frontier.from_dict(f) for f in data.get("frontiers", [])]

        # Warn if data was truncated during serialization
        original_count = data.get("total_frontiers", len(frontiers))
        if data.get("truncated", False) or original_count > len(frontiers):
            logger.warning(
                f"FrontierReport.from_dict: Restoring {len(frontiers)} of "
                f"{original_count} original frontiers. Statistics may be approximate."
            )

        return cls(
            frontiers=frontiers,
            total_embeddings=data.get("total_embeddings", 0),
            coverage_estimate=data.get("coverage_estimate", 0.0),
            avg_distance_to_frontier=data.get("avg_distance_to_frontier", 0.0),
            high_priority_count=data.get("high_priority_count", 0),
            _original_frontier_count=original_count,
        )


def find_frontiers(
    index: "CoordinateIndex",
    *,
    max_frontiers: int = 50,
    min_distance: float = 0.3,
    priority_threshold: float = 0.5,
    seed: int | None = 42,
) -> FrontierReport:
    """Find frontier points in behavioral space.

    Frontiers are identified by:
    1. Points with large distances to nearest neighbors
    2. Sparse regions in embedding space
    3. Edges of cluster boundaries

    Args:
        index: CoordinateIndex to analyze
        max_frontiers: Maximum frontiers to return
        min_distance: Minimum distance to consider a frontier
        priority_threshold: Threshold for high-priority classification
        seed: Random seed

    Returns:
        FrontierReport with all detected frontiers
    """
    embeddings = index.list_all(limit=10000)

    if len(embeddings) < 2:
        return FrontierReport(
            frontiers=[],
            total_embeddings=len(embeddings),
            coverage_estimate=0.0,  # No coverage with < 2 embeddings
            avg_distance_to_frontier=0.0,
            high_priority_count=0,
        )

    dim = embeddings[0].dimension
    frontiers: list[Frontier] = []

    # Compute all pairwise distances to find outliers
    # Use a sample for large datasets, but compute distances against ALL embeddings
    sample_size = min(len(embeddings), 500)

    import random

    rng = random.Random(seed)
    if len(embeddings) > sample_size:
        sample = rng.sample(embeddings, sample_size)
    else:
        sample = embeddings

    # For each embedding in sample, find distance to nearest neighbor in ALL embeddings
    neighbor_distances: list[tuple[int, float, str | None]] = []

    for i, emb in enumerate(sample):
        min_dist = float("inf")
        nearest_other_id: str | None = None
        for j, other in enumerate(
            embeddings
        ):  # Check against ALL embeddings, not just sample
            if (
                emb.run_id == other.run_id
            ):  # Compare by ID, not index (sample != embeddings)
                continue
            dist = (
                semantic_distance(emb.vector, other.vector)
                / SEMANTIC_DISTANCE_NORMALIZER
            )
            if dist < min_dist:
                min_dist = dist
                nearest_other_id = other.run_id
        neighbor_distances.append((i, min_dist, nearest_other_id))

    # Sort by distance (descending) - highest distances are frontiers
    neighbor_distances.sort(key=lambda x: x[1], reverse=True)

    # Take top frontiers
    for rank, (idx, dist, nearest_other_id) in enumerate(
        neighbor_distances[:max_frontiers]
    ):
        if dist < min_distance:
            break

        emb = sample[idx]

        # Compute exploration priority based on:
        # - Distance from neighbors (more isolated = higher priority)
        # - Position in ranking (higher rank = higher priority)
        isolation_score = min(1.0, dist / ISOLATION_NORMALIZER)  # Normalize to [0, 1]
        rank_score = 1.0 - (rank / max_frontiers)  # Higher for top ranks
        priority = isolation_score * ISOLATION_WEIGHT + rank_score * RANK_WEIGHT

        # Determine reason
        if dist > HIGH_ISOLATION_THRESHOLD:
            reason = "Highly isolated execution - potentially unexplored input space"
        elif dist > MODERATE_ISOLATION_THRESHOLD:
            reason = "Moderately isolated - edge of explored space"
        else:
            reason = "Near frontier - boundary of known behavior"

        frontier = Frontier(
            frontier_id=f"F{rank:03d}",
            point=emb.vector,
            nearest_run_id=nearest_other_id
            or emb.run_id,  # Actual nearest neighbor, not self
            distance_to_known=dist,
            suggested_input=_suggest_exploration_input(emb),
            exploration_priority=priority,
            reason=reason,
            dimension=dim,
        )
        frontiers.append(frontier)

    # Compute statistics
    if neighbor_distances:
        avg_dist = sum(d for _, d, _ in neighbor_distances) / len(neighbor_distances)
        coverage = max(0.0, 1.0 - avg_dist * COVERAGE_DISTANCE_MULTIPLIER)  # Heuristic
    else:
        avg_dist = 0.0
        coverage = 1.0

    high_priority = len(
        [f for f in frontiers if f.exploration_priority >= priority_threshold]
    )

    return FrontierReport(
        frontiers=frontiers,
        total_embeddings=len(embeddings),
        coverage_estimate=coverage,
        avg_distance_to_frontier=avg_dist,
        high_priority_count=high_priority,
    )


def _suggest_exploration_input(embedding: "ExecutionEmbedding") -> str | None:
    """Generate suggested inputs for exploring a frontier.

    Creates variations of the existing input that might reveal
    new behaviors. Returns the most relevant suggestion, with
    alternatives noted.
    """
    input_text = embedding.input_text
    if not input_text:
        return None

    # Generate suggestions based on input characteristics
    suggestions = []

    # Length-based variations
    if len(input_text) < 50:
        suggestions.append("Try a more detailed version of this input")
    elif len(input_text) > 500:
        suggestions.append("Try a more concise version of this input")

    # Content-based suggestions
    if "class" in input_text.lower():
        suggestions.append("Try different class structures or interfaces")
    if "error" in input_text.lower() or "exception" in input_text.lower():
        suggestions.append("Explore error handling variations")
    if "{" in input_text and "}" in input_text:
        suggestions.append("Try different JSON/data structures")

    # Default suggestion
    if not suggestions:
        suggestions.append("Explore similar inputs with different parameters")

    # Return primary suggestion with count of alternatives
    if len(suggestions) == 1:
        return suggestions[0]
    else:
        return f"{suggestions[0]} (+{len(suggestions) - 1} more options)"


def find_sparse_regions(
    index: "CoordinateIndex",
    *,
    grid_resolution: int = 10,
    sparsity_threshold: float = 0.1,
) -> list[dict[str, Any]]:
    """Find sparse regions in behavioral space using grid-based analysis.

    Divides embedding space into grid cells and identifies cells
    with few or no points.

    Args:
        index: CoordinateIndex to analyze
        grid_resolution: Number of divisions per dimension (capped at 5 for performance)
        sparsity_threshold: Threshold for considering a region sparse

    Returns:
        List of sparse region descriptors
    """
    # Cap resolution for performance (10^dim is too many cells)
    grid_resolution = min(grid_resolution, 5)

    embeddings = index.list_all(limit=5000)

    if len(embeddings) < 10:
        return []

    dim = embeddings[0].dimension

    # For high dimensions, only analyze first few dimensions
    # (curse of dimensionality makes full grid impractical)
    analysis_dims = min(dim, 3)

    # Project to lower dimensions if needed
    if dim > analysis_dims:
        # Use first N dimensions as proxy
        projections = [
            [emb.vector[i] for i in range(analysis_dims)] for emb in embeddings
        ]
    else:
        projections = [emb.vector[:analysis_dims] for emb in embeddings]

    # Find bounds
    mins = [float("inf")] * analysis_dims
    maxs = [float("-inf")] * analysis_dims

    for proj in projections:
        for i, val in enumerate(proj):
            mins[i] = min(mins[i], val)
            maxs[i] = max(maxs[i], val)

    # Add margins
    margins = [(maxs[i] - mins[i]) * 0.1 for i in range(analysis_dims)]
    mins = [mins[i] - margins[i] for i in range(analysis_dims)]
    maxs = [maxs[i] + margins[i] for i in range(analysis_dims)]

    # Count points in each cell
    cell_counts: dict[tuple[int, ...], int] = {}

    for proj in projections:
        cell = tuple(
            min(
                grid_resolution - 1,
                int(
                    (proj[i] - mins[i]) / (maxs[i] - mins[i] + 1e-10) * grid_resolution
                ),
            )
            for i in range(analysis_dims)
        )
        cell_counts[cell] = cell_counts.get(cell, 0) + 1

    # Find sparse cells (cells with few points)
    total_cells = grid_resolution**analysis_dims
    expected_per_cell = len(embeddings) / total_cells
    sparse_threshold = expected_per_cell * sparsity_threshold

    sparse_regions = []
    for cell, count in sorted(cell_counts.items()):
        if count < sparse_threshold:
            # Compute center of this cell
            center = [
                mins[i] + (cell[i] + 0.5) * (maxs[i] - mins[i]) / grid_resolution
                for i in range(analysis_dims)
            ]

            sparse_regions.append(
                {
                    "cell": cell,
                    "count": count,
                    "expected": expected_per_cell,
                    "sparsity": 1.0 - (count / expected_per_cell)
                    if expected_per_cell > 0
                    else 1.0,
                    "center": center,
                }
            )

    return sparse_regions[:20]  # Top 20 sparse regions


def suggest_exploration(
    index: "CoordinateIndex",
    *,
    top_k: int = 10,
    include_explored: bool = False,
    value_weights: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Suggest exploration targets based on frontier analysis.

    Combines frontier detection with input analysis to provide
    concrete exploration suggestions ranked by potential value.

    Args:
        index: CoordinateIndex to analyze
        top_k: Number of suggestions to return
        include_explored: Whether to include already-explored frontiers
        value_weights: Weights for value factors (isolation, novelty, coverage_gap)
                      Default: {"isolation": 0.4, "novelty": 0.3, "coverage_gap": 0.3}

    Returns:
        List of exploration suggestions sorted by potential value
    """
    weights = value_weights or {"isolation": 0.4, "novelty": 0.3, "coverage_gap": 0.3}

    report = find_frontiers(index, max_frontiers=top_k * 3)

    # Filter out explored frontiers if requested
    frontiers = (
        report.frontiers
        if include_explored
        else [f for f in report.frontiers if not f.explored]
    )

    suggestions = []
    for frontier in frontiers:
        # Compute value score from multiple factors
        isolation_score = min(
            1.0, frontier.distance_to_known / 0.5
        )  # Higher = more isolated

        # Novelty: inversely related to exploration_priority (already-prioritized = less novel)
        novelty_score = 1.0 - frontier.exploration_priority * 0.5

        # Coverage gap: higher distance = bigger gap to fill
        coverage_gap_score = min(1.0, frontier.distance_to_known)

        value_score = (
            isolation_score * weights.get("isolation", 0.4)
            + novelty_score * weights.get("novelty", 0.3)
            + coverage_gap_score * weights.get("coverage_gap", 0.3)
        )

        suggestion = {
            "frontier_id": frontier.frontier_id,
            "priority": frontier.exploration_priority,
            "value_score": round(value_score, 4),
            "target": frontier.suggested_input or "Explore near this execution",
            "reference_run": frontier.nearest_run_id,
            "distance_from_known": frontier.distance_to_known,
            "reason": frontier.reason,
            "explored": frontier.explored,
        }
        suggestions.append(suggestion)

    # Sort by value score (descending)
    suggestions.sort(key=lambda s: s["value_score"], reverse=True)

    return suggestions[:top_k]

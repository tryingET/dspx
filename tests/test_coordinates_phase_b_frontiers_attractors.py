# summary: "Tests Phase B frontier discovery, attractor detection, exploration suggestions, and health reporting."
# read_when:
#   - "You are changing Oracle frontier or attractor models, topology analysis, or exploration guidance."

"""Phase B behavioral topology frontier and attractor tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from dspx.coordinates import (
    Attractor,
    CoordinateIndex,
    EmbeddingEngine,
    Frontier,
    compute_attractor_health,
    compute_stability_score,
    find_attractors,
    find_frontiers,
    find_nearest_attractor,
    suggest_exploration,
)


class TestFrontiers:
    """Tests for frontier detection."""

    @pytest.fixture
    def engine(self) -> EmbeddingEngine:
        return EmbeddingEngine(backend="mock", mock_dimension=32)

    @pytest.fixture
    def temp_db(self, tmp_path: Path) -> Path:
        return tmp_path / "test_frontiers.db"

    @pytest.fixture
    def populated_index(
        self, temp_db: Path, engine: EmbeddingEngine
    ) -> CoordinateIndex:
        index = CoordinateIndex(db_path=temp_db)

        # Create clustered embeddings with some outliers
        for i in range(15):
            emb = engine.embed_execution(
                run_id=f"cluster-{i}",
                input_text="classify ticket",
                output_text="result",
                run_kind="test",
                provider="test",
            )
            index.upsert(emb)

        # Add an outlier
        emb = engine.embed_execution(
            run_id="outlier-1",
            input_text="completely different unique task that is very special",
            output_text="special result",
            run_kind="test",
            provider="test",
        )
        index.upsert(emb)

        return index

    def test_find_frontiers(self, populated_index: CoordinateIndex) -> None:
        """Can find frontiers in the index."""
        report = find_frontiers(populated_index, max_frontiers=10)

        assert report.total_embeddings == 16
        assert isinstance(report.frontiers, list)
        assert isinstance(report.coverage_estimate, float)

    def test_frontier_report_serialization(
        self, populated_index: CoordinateIndex
    ) -> None:
        """Frontier report can be serialized."""
        report = find_frontiers(populated_index, max_frontiers=5)

        data = report.to_dict()
        assert "total_frontiers" in data
        assert "frontiers" in data

    def test_frontier_serialization(self, engine: EmbeddingEngine) -> None:
        """Frontier can be serialized."""
        emb = engine.embed_execution(
            run_id="test",
            input_text="test",
            output_text="out",
            run_kind="test",
            provider="test",
        )

        frontier = Frontier(
            frontier_id="F001",
            point=emb.vector,
            nearest_run_id="test",
            distance_to_known=0.5,
            suggested_input="Try different inputs",
            exploration_priority=0.8,
            reason="Isolated execution",
            dimension=emb.dimension,
        )

        data = frontier.to_dict()
        assert data["frontier_id"] == "F001"
        assert data["exploration_priority"] == 0.8

    def test_suggest_exploration(self, populated_index: CoordinateIndex) -> None:
        """Can generate exploration suggestions."""
        suggestions = suggest_exploration(populated_index, top_k=5)

        assert isinstance(suggestions, list)
        if suggestions:
            assert "priority" in suggestions[0]
            assert "target" in suggestions[0]


class TestAttractors:
    """Tests for attractor detection."""

    @pytest.fixture
    def engine(self) -> EmbeddingEngine:
        return EmbeddingEngine(backend="mock", mock_dimension=32)

    @pytest.fixture
    def temp_db(self, tmp_path: Path) -> Path:
        return tmp_path / "test_attractors.db"

    @pytest.fixture
    def populated_index(
        self, temp_db: Path, engine: EmbeddingEngine
    ) -> CoordinateIndex:
        index = CoordinateIndex(db_path=temp_db)

        # Create tight cluster (strong attractor)
        for i in range(15):
            emb = engine.embed_execution(
                run_id=f"attractor-{i}",
                input_text="same task repeated",
                output_text="consistent result",
                run_kind="sig-gen",
                provider="claude",
            )
            index.upsert(emb)

        return index

    def test_compute_stability_score(self, engine: EmbeddingEngine) -> None:
        """Can compute stability score."""
        embeddings = []
        for i in range(5):
            emb = engine.embed_execution(
                run_id=f"stable-{i}",
                input_text="same input",
                output_text="same output",
                run_kind="test",
                provider="test",
            )
            embeddings.append(emb)

        stability = compute_stability_score(embeddings)
        assert 0.0 <= stability <= 1.0

    def test_find_attractors(self, populated_index: CoordinateIndex) -> None:
        """Can find attractors in the index."""
        report = find_attractors(populated_index, k=3, min_stability=0.3)

        assert report.total_embeddings == 15
        assert isinstance(report.attractors, list)

    def test_attractor_report_serialization(
        self, populated_index: CoordinateIndex
    ) -> None:
        """Attractor report can be serialized."""
        report = find_attractors(populated_index, k=3)

        data = report.to_dict()
        assert "total_attractors" in data
        assert "avg_stability" in data

    def test_attractor_serialization(self, engine: EmbeddingEngine) -> None:
        """Attractor can be serialized."""
        emb = engine.embed_execution(
            run_id="test",
            input_text="test",
            output_text="out",
            run_kind="test",
            provider="test",
        )

        attractor = Attractor(
            attractor_id="A001",
            centroid=emb.vector,
            basin_radius=0.3,
            member_count=10,
            stability_score=0.9,
            convergence_rate=0.1,
            dominant_run_kind="sig-gen",
            dominant_provider="claude",
            sample_inputs=["input1"],
            sample_outputs=["output1"],
            dimension=emb.dimension,
        )

        data = attractor.to_dict()
        assert data["attractor_id"] == "A001"
        assert data["stability_score"] == 0.9

    def test_find_nearest_attractor(
        self, populated_index: CoordinateIndex, engine: EmbeddingEngine
    ) -> None:
        """Can find nearest attractor for an embedding."""
        report = find_attractors(populated_index, k=3)

        if report.attractors:
            emb = engine.embed_execution(
                run_id="new",
                input_text="same task repeated",
                output_text="consistent result",
                run_kind="sig-gen",
                provider="claude",
            )

            nearest, distance = find_nearest_attractor(emb, report.attractors)
            assert nearest is not None or distance == float("inf")

    def test_compute_attractor_health(self, populated_index: CoordinateIndex) -> None:
        """Can compute attractor health."""
        report = find_attractors(populated_index, k=3)
        health = compute_attractor_health(report)

        assert "status" in health
        assert "message" in health
        assert health["status"] in ["healthy", "moderate", "weak", "no_data"]

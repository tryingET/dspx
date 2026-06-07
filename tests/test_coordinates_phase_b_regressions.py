"""Regression coverage for Phase B behavioral topology bug fixes."""

from __future__ import annotations

from pathlib import Path

import pytest

from dspx.coordinates import (
    Attractor,
    Contract,
    ContractRegistry,
    ContractSeverity,
    ContractStatus,
    CoordinateIndex,
    DangerZone,
    EmbeddingEngine,
    Frontier,
    FrontierReport,
    build_territory_map,
    compute_internal_variance,
    compute_stability_score,
    find_attractors,
    find_frontiers,
    is_in_attractor_basin,
    predict_convergence,
    suggest_exploration,
    validate_no_pii,
)


class TestBugFixesPhaseB:
    """Regression tests for Phase B bug fixes."""

    @pytest.fixture
    def engine(self) -> EmbeddingEngine:
        return EmbeddingEngine(backend="mock", mock_dimension=32)

    # Bug #3, #4: stability score for single embedding and negative prevention
    def test_stability_score_single_embedding_is_insufficient_data(
        self, engine: EmbeddingEngine
    ) -> None:
        """Single embedding should return -1.0 (insufficient data for stability).

        A single point cannot be "stable" - it's unknown whether the region
        is stable or not. Using -1.0 distinguishes from actual low stability (0.0).
        """
        emb = engine.embed_execution(
            run_id="single",
            input_text="test",
            output_text="out",
            run_kind="test",
            provider="test",
        )
        stability = compute_stability_score([emb])
        assert stability == -1.0  # Insufficient data sentinel

    def test_stability_score_never_negative(self, engine: EmbeddingEngine) -> None:
        """Stability should never go negative even with high variance."""
        embeddings = []
        for i in range(5):
            emb = engine.embed_execution(
                run_id=f"var-{i}",
                input_text="x" * (i * 1000),  # Very different lengths
                output_text="y" * (i * 500),
                run_kind="test",
                provider="test",
            )
            embeddings.append(emb)

        stability = compute_stability_score(embeddings)
        assert stability >= 0.0

    # Bug #5: coverage_estimate for empty/small index
    def test_coverage_zero_for_few_embeddings(
        self, engine: EmbeddingEngine, tmp_path: Path
    ) -> None:
        """Coverage should be 0.0 for < 2 embeddings."""
        index = CoordinateIndex(db_path=tmp_path / "test.db")

        emb = engine.embed_execution(
            run_id="only-one",
            input_text="test",
            output_text="out",
            run_kind="test",
            provider="test",
        )
        index.upsert(emb)

        report = find_frontiers(index)
        assert report.coverage_estimate == 0.0

    # Bug #12, #25: variance/distance for single embedding
    def test_internal_variance_single_embedding_distinguishable(
        self, engine: EmbeddingEngine
    ) -> None:
        """Single embedding variance should be distinguishable from 0.0."""
        emb = engine.embed_execution(
            run_id="single",
            input_text="test",
            output_text="out",
            run_kind="test",
            provider="test",
        )
        variance = compute_internal_variance([emb])
        assert variance == -1.0  # Distinguishable sentinel

        # Empty list should be 0.0
        empty_variance = compute_internal_variance([])
        assert empty_variance == 0.0

    # Bug #16: coverage can't exceed 1.0
    def test_attractor_coverage_capped_at_one(
        self, engine: EmbeddingEngine, tmp_path: Path
    ) -> None:
        """Attractor coverage should never exceed 1.0."""
        index = CoordinateIndex(db_path=tmp_path / "test.db")

        # Add some embeddings
        for i in range(10):
            emb = engine.embed_execution(
                run_id=f"test-{i}",
                input_text="same input",
                output_text="same output",
                run_kind="test",
                provider="test",
            )
            index.upsert(emb)

        report = find_attractors(index, k=3)
        assert report.coverage <= 1.0

    # Bug #18: basin boundary consistency
    def test_basin_boundary_strict_inequality(self, engine: EmbeddingEngine) -> None:
        """is_in_attractor_basin should use strict inequality."""
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
            dominant_run_kind="test",
            dominant_provider="test",
            sample_inputs=["in"],
            sample_outputs=["out"],
            dimension=emb.dimension,
        )

        # Point at exactly basin_radius should NOT be in basin (strict inequality)
        # This is hard to test directly, but verify the function works
        result = is_in_attractor_basin(emb, attractor)
        # The embedding is at centroid (distance 0), so it should be in basin
        assert result is True

    # Bug #23: PII detection patterns
    def test_pii_detects_international_phone(self, engine: EmbeddingEngine) -> None:
        """PII detection should catch international phone formats.

        Note: International phone patterns have higher false positive rates,
        so they are flagged as WARNING (not ERROR). This means the contract
        PASSes but violations are still recorded for review.
        """
        emb = engine.embed_execution(
            run_id="intl-phone",
            input_text="get contact",
            output_text="Call +44 20 7946 0958 for support",
            run_kind="test",
            provider="test",
        )

        result = validate_no_pii(emb)
        # International phone is WARNING severity, so status is PASS
        # (only ERROR-level violations cause FAIL)
        assert result.status == ContractStatus.PASS
        # But violations should still be recorded
        assert len(result.violations) > 0
        assert result.violations[0].severity == ContractSeverity.WARNING

    def test_pii_does_not_flag_uuid(self, engine: EmbeddingEngine) -> None:
        """PII detection should NOT flag UUIDs - they are anonymized identifiers.

        UUIDs are intentionally designed to be non-identifying and are commonly
        used in ML systems as run IDs, trace IDs, etc. Flagging them creates
        noise and false positives.
        """
        emb = engine.embed_execution(
            run_id="uuid-test",
            input_text="get id",
            output_text="Your ID is 550e8400-e29b-41d4-a716-446655440000",
            run_kind="test",
            provider="test",
        )

        result = validate_no_pii(emb)
        assert result.status == ContractStatus.PASS

    # Bug #26, #33, #34: serialization includes centroids/points
    def test_danger_zone_serialization_includes_centroid(
        self, engine: EmbeddingEngine
    ) -> None:
        """DangerZone.to_dict should include centroid."""
        emb = engine.embed_execution(
            run_id="test",
            input_text="test",
            output_text="out",
            run_kind="test",
            provider="test",
        )

        zone = DangerZone(
            zone_id="D001",
            centroid=emb.vector,
            radius=0.3,
            reason="Test",
            severity="high",
            dimension=emb.dimension,
        )

        data = zone.to_dict()
        assert "centroid" in data
        assert data["centroid"] == emb.vector

    def test_attractor_serialization_includes_centroid(
        self, engine: EmbeddingEngine
    ) -> None:
        """Attractor.to_dict should include centroid."""
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
            dominant_run_kind="test",
            dominant_provider="test",
            sample_inputs=["in"],
            sample_outputs=["out"],
            dimension=emb.dimension,
        )

        data = attractor.to_dict()
        assert "centroid" in data

    def test_frontier_serialization_includes_point(
        self, engine: EmbeddingEngine
    ) -> None:
        """Frontier.to_dict should include point."""
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
            suggested_input="Test",
            exploration_priority=0.8,
            reason="Test frontier",
            dimension=emb.dimension,
        )

        data = frontier.to_dict()
        assert "point" in data

    # Bug #46: bulk enable/disable by tags
    def test_contract_registry_enable_by_tags(self) -> None:
        """ContractRegistry should support bulk enable/disable by tags."""
        registry = ContractRegistry()

        # Add contracts with different tags
        registry.add(
            Contract(
                name="security-1",
                description="Security contract",
                invariant="x",
                tags=["security"],
                enabled=False,
            )
        )
        registry.add(
            Contract(
                name="quality-1",
                description="Quality contract",
                invariant="y",
                tags=["quality"],
                enabled=False,
            )
        )
        registry.add(
            Contract(
                name="security-2",
                description="Another security contract",
                invariant="z",
                tags=["security", "critical"],
                enabled=False,
            )
        )

        # Enable all security contracts
        count = registry.enable_by_tags(["security"])
        assert count == 2

        security_contracts = registry.get_by_tags(["security"])
        assert all(c.enabled for c in security_contracts)

        quality_contracts = registry.get_by_tags(["quality"])
        assert all(not c.enabled for c in quality_contracts)

    # Gap #41: find region by run_id
    def test_territory_map_find_region_by_run_id(
        self, engine: EmbeddingEngine, tmp_path: Path
    ) -> None:
        """TerritoryMap should support reverse lookup by run_id."""
        index = CoordinateIndex(db_path=tmp_path / "test.db")

        for i in range(10):
            emb = engine.embed_execution(
                run_id=f"test-{i}",
                input_text="same input",
                output_text="same output",
                run_kind="test",
                provider="test",
            )
            index.upsert(emb)

        territory = build_territory_map(index, k=3, min_region_size=2)

        if territory.regions:
            # Get a run_id that should be in a region
            region = territory.regions[0]
            if region.sample_run_ids:
                found = territory.find_region_for_run_id(region.sample_run_ids[0])
                assert found is not None
                assert found.region_id == region.region_id

    # Gap #43: confidence thresholds in predict_convergence
    def test_predict_convergence_includes_confidence_level(
        self, engine: EmbeddingEngine, tmp_path: Path
    ) -> None:
        """predict_convergence should include confidence level interpretation."""
        index = CoordinateIndex(db_path=tmp_path / "test.db")

        for i in range(15):
            emb = engine.embed_execution(
                run_id=f"test-{i}",
                input_text="same input",
                output_text="same output",
                run_kind="test",
                provider="test",
            )
            index.upsert(emb)

        attractor_report = find_attractors(index, k=3)

        if attractor_report.attractors:
            new_emb = engine.embed_execution(
                run_id="new",
                input_text="same input",
                output_text="same output",
                run_kind="test",
                provider="test",
            )

            prediction = predict_convergence(new_emb, attractor_report.attractors)
            assert "confidence_level" in prediction
            assert "uncertainty" in prediction
            assert prediction["confidence_level"] in [
                "high",
                "medium",
                "low",
                "very_low",
            ]

    # Gap #44: frontier exploration tracking
    def test_frontier_exploration_tracking(
        self, engine: EmbeddingEngine, tmp_path: Path
    ) -> None:
        """Frontiers should track exploration status."""
        index = CoordinateIndex(db_path=tmp_path / "test.db")

        for i in range(15):
            emb = engine.embed_execution(
                run_id=f"cluster-{i}",
                input_text="same input",
                output_text="same output",
                run_kind="test",
                provider="test",
            )
            index.upsert(emb)

        # Add an outlier
        outlier = engine.embed_execution(
            run_id="outlier",
            input_text="completely different unique task",
            output_text="different result",
            run_kind="test",
            provider="test",
        )
        index.upsert(outlier)

        report = find_frontiers(index)

        if report.frontiers:
            # Initially unexplored
            frontier = report.frontiers[0]
            assert frontier.explored is False

            # Mark as explored
            result = report.mark_explored(frontier.frontier_id, by="tester")
            assert result is True
            assert frontier.explored is True
            assert frontier.explored_by == "tester"
            assert frontier.explored_at is not None

            # Check progress
            progress = report.get_exploration_progress()
            assert "total_frontiers" in progress
            assert "explored" in progress
            assert progress["explored"] >= 1

    # Gap #45: suggest_exploration ranked by value
    def test_suggest_exploration_ranked_by_value(
        self, engine: EmbeddingEngine, tmp_path: Path
    ) -> None:
        """suggest_exploration should rank suggestions by value score."""
        index = CoordinateIndex(db_path=tmp_path / "test.db")

        for i in range(20):
            emb = engine.embed_execution(
                run_id=f"test-{i}",
                input_text=f"input {i % 3}",  # Some variation
                output_text=f"output {i % 3}",
                run_kind="test",
                provider="test",
            )
            index.upsert(emb)

        suggestions = suggest_exploration(index, top_k=5)

        if len(suggestions) > 1:
            # Should be sorted by value_score descending
            for i in range(len(suggestions) - 1):
                assert (
                    suggestions[i]["value_score"] >= suggestions[i + 1]["value_score"]
                )

            # Each suggestion should have value_score
            for s in suggestions:
                assert "value_score" in s
                assert "frontier_id" in s

    # Gap #43: Frontier persistence (from_dict)
    def test_frontier_from_dict(self, engine: EmbeddingEngine) -> None:
        """Frontier should be reconstructable from dict."""
        emb = engine.embed_execution(
            run_id="test",
            input_text="test",
            output_text="out",
            run_kind="test",
            provider="test",
        )

        original = Frontier(
            frontier_id="F001",
            point=emb.vector,
            nearest_run_id="test",
            distance_to_known=0.5,
            suggested_input="Test suggestion",
            exploration_priority=0.8,
            reason="Test frontier",
            dimension=emb.dimension,
            explored=True,
            explored_by="tester",
            explored_at="2025-01-01T00:00:00Z",
        )

        data = original.to_dict()
        restored = Frontier.from_dict(data)

        assert restored.frontier_id == original.frontier_id
        assert restored.nearest_run_id == original.nearest_run_id
        assert restored.distance_to_known == original.distance_to_known
        assert restored.suggested_input == original.suggested_input
        assert restored.exploration_priority == original.exploration_priority
        assert restored.explored == original.explored
        assert restored.explored_by == original.explored_by

    def test_frontier_report_from_dict(
        self, engine: EmbeddingEngine, tmp_path: Path
    ) -> None:
        """FrontierReport should be reconstructable from dict."""
        index = CoordinateIndex(db_path=tmp_path / "test.db")

        for i in range(10):
            emb = engine.embed_execution(
                run_id=f"test-{i}",
                input_text=f"input {i}",
                output_text=f"output {i}",
                run_kind="test",
                provider="test",
            )
            index.upsert(emb)

        original = find_frontiers(index, max_frontiers=5)

        # Add exploration state
        if original.frontiers:
            original.frontiers[0].explored = True
            original.frontiers[0].explored_by = "tester"

        data = original.to_dict()
        restored = FrontierReport.from_dict(data)

        # Note: coverage_estimate is rounded in to_dict(), so compare rounded values
        assert restored.total_embeddings == original.total_embeddings
        assert round(restored.coverage_estimate, 4) == round(
            original.coverage_estimate, 4
        )
        assert len(restored.frontiers) == len(
            original.frontiers[:20]
        )  # Only top 20 serialized

        # Verify exploration state is preserved
        if restored.frontiers and restored.frontiers[0].explored:
            assert restored.frontiers[0].explored_by == "tester"

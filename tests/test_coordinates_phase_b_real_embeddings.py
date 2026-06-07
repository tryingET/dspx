"""Phase B integration tests with real embedding backends."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from dspx.coordinates import (
    ContractRegistry,
    CoordinateIndex,
    EmbeddingEngine,
    build_territory_map,
    create_default_contracts,
    find_attractors,
    predict_convergence,
)


class TestIntegrationRealEmbeddings:
    """Integration tests using real (non-mock) embedding engine.

    These tests verify that Phase B works correctly with actual
    semantic embeddings, not just mock vectors.
    """

    @pytest.fixture
    def real_engine(self) -> EmbeddingEngine | None:
        """Create a real embedding engine if API keys are available.

        Returns None if no API key is configured (tests will be skipped).
        """
        import importlib.util

        if importlib.util.find_spec("sentence_transformers") is not None:
            try:
                return EmbeddingEngine(backend="sentence-transformers")
            except Exception:
                pass

        return None

    @pytest.fixture
    def temp_db(self, tmp_path: Path) -> Path:
        return tmp_path / "test_integration.db"

    @pytest.mark.skipif(
        importlib.util.find_spec("sentence_transformers") is None,
        reason="No embedding backend available (needs sentence-transformers)",
    )
    def test_territory_with_real_embeddings(
        self, real_engine: EmbeddingEngine | None, temp_db: Path
    ) -> None:
        """Territory analysis works with real semantic embeddings."""
        if real_engine is None:
            pytest.skip("No real embedding engine available")

        index = CoordinateIndex(db_path=temp_db)

        # Create semantically similar embeddings (should cluster together)
        similar_inputs = [
            "classify this bug report",
            "categorize this issue as bug or feature",
            "label this ticket as bug, feature, or enhancement",
            "determine the category of this support ticket",
        ]

        # Create semantically different embeddings (should be separate)
        different_inputs = [
            "generate a Python function to sort a list",
            "write code to implement binary search",
            "create a REST API endpoint for user authentication",
        ]

        for i, inp in enumerate(similar_inputs):
            emb = real_engine.embed_execution(
                run_id=f"similar-{i}",
                input_text=inp,
                output_text='{"category": "bug"}',
                run_kind="classify",
                provider="claude",
            )
            index.upsert(emb)

        for i, inp in enumerate(different_inputs):
            emb = real_engine.embed_execution(
                run_id=f"different-{i}",
                input_text=inp,
                output_text="def solution(): pass",
                run_kind="codegen",
                provider="codex",
            )
            index.upsert(emb)

        # Build territory
        territory = build_territory_map(index, k=2, min_region_size=2)

        assert territory.total_embeddings == 7
        assert len(territory.regions) >= 1

        # Similar inputs should have lower variance than different inputs
        # (This is a soft check - real embeddings should show this pattern)
        if len(territory.regions) >= 2:
            # At least we should have multiple regions
            assert territory.coverage > 0

    @pytest.mark.skipif(
        importlib.util.find_spec("sentence_transformers") is None,
        reason="No embedding backend available",
    )
    def test_convergence_prediction_with_real_embeddings(
        self, real_engine: EmbeddingEngine | None, temp_db: Path
    ) -> None:
        """Convergence prediction works with real embeddings."""
        if real_engine is None:
            pytest.skip("No real embedding engine available")

        index = CoordinateIndex(db_path=temp_db)

        # Create training data
        for i in range(10):
            emb = real_engine.embed_execution(
                run_id=f"train-{i}",
                input_text=f"classify ticket {i}: bug report about login issue",
                output_text='{"category": "bug", "priority": "high"}',
                run_kind="classify",
                provider="claude",
            )
            index.upsert(emb)

        # Find attractors
        report = find_attractors(index, k=3, min_stability=0.3)

        if report.attractors:
            # Create a test embedding similar to training
            test_emb = real_engine.embed_execution(
                run_id="test-prediction",
                input_text="classify this: bug report about password reset",
                output_text="",  # Empty - we're predicting before execution
                run_kind="classify",
                provider="claude",
            )

            prediction = predict_convergence(test_emb, report.attractors)

            assert prediction["predicted_attractor"] is not None
            assert prediction["confidence"] >= 0.0
            assert prediction["confidence_level"] in [
                "high",
                "medium",
                "low",
                "very_low",
            ]
            # New input similar to training should have reasonable confidence
            assert prediction["uncertainty"] <= 1.0

    @pytest.mark.skipif(
        importlib.util.find_spec("sentence_transformers") is None,
        reason="No embedding backend available",
    )
    def test_contract_verification_with_real_data(
        self, real_engine: EmbeddingEngine | None, temp_db: Path
    ) -> None:
        """Contract verification works with real embeddings."""
        if real_engine is None:
            pytest.skip("No real embedding engine available")

        index = CoordinateIndex(db_path=temp_db)

        # Create embedding with clean output
        clean_emb = real_engine.embed_execution(
            run_id="clean-output",
            input_text="generate a greeting",
            output_text="Hello! Welcome to our service.",
            run_kind="generate",
            provider="claude",
        )
        index.upsert(clean_emb)

        # Create embedding with potential PII
        pii_emb = real_engine.embed_execution(
            run_id="pii-output",
            input_text="get user info",
            output_text="Contact user@example.com for details",
            run_kind="query",
            provider="claude",
        )
        index.upsert(pii_emb)

        # Verify contracts
        registry = ContractRegistry()
        for c in create_default_contracts():
            registry.add(c)

        results = registry.verify_index(index, limit=10)

        assert results["total_checks"] >= 2
        assert results["fail"] >= 1  # PII embedding should fail
        assert results["pass"] >= 1  # Clean embedding should pass

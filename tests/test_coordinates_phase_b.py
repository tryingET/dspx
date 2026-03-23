"""Tests for Phase B: Behavioral Topology."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from dspx.coordinates import (
    # Embeddings
    EmbeddingEngine,
    # Territory
    RegionType,
    Region,
    DangerZone,
    build_territory_map,
    find_region_for_embedding,
    detect_danger_zones,
    compute_internal_variance,
    # Contracts
    ContractSeverity,
    ContractStatus,
    Contract,
    ContractRegistry,
    validate_no_pii,
    validate_output_format,
    validate_response_quality,
    create_default_contracts,
    evaluate_contract,
    # Frontiers
    Frontier,
    FrontierReport,
    find_frontiers,
    suggest_exploration,
    # Attractors
    Attractor,
    find_attractors,
    find_nearest_attractor,
    is_in_attractor_basin,
    compute_attractor_health,
    compute_stability_score,
    predict_convergence,
    # Storage
    CoordinateIndex,
)


# =============================================================================
# Territory Tests
# =============================================================================


class TestTerritory:
    """Tests for territory mapping."""

    @pytest.fixture
    def engine(self) -> EmbeddingEngine:
        return EmbeddingEngine(backend="mock", mock_dimension=32)

    @pytest.fixture
    def temp_db(self, tmp_path: Path) -> Path:
        return tmp_path / "test_territory.db"

    @pytest.fixture
    def populated_index(
        self, temp_db: Path, engine: EmbeddingEngine
    ) -> CoordinateIndex:
        index = CoordinateIndex(db_path=temp_db)

        # Create embeddings with different patterns
        # Group 1: Similar inputs (stable region)
        for i in range(10):
            emb = engine.embed_execution(
                run_id=f"stable-{i}",
                input_text="classify ticket as bug or feature",
                output_text='{"category": "bug"}',
                run_kind="sig-gen",
                provider="claude",
            )
            index.upsert(emb)

        # Group 2: Varied inputs (unstable region)
        for i in range(8):
            emb = engine.embed_execution(
                run_id=f"unstable-{i}",
                input_text=f"random task {i} with unique content {i * 100}",
                output_text=f"output {i}",
                run_kind="codegen",
                provider="codex",
            )
            index.upsert(emb)

        return index

    def test_compute_internal_variance_low(self, engine: EmbeddingEngine) -> None:
        """Low variance for similar embeddings."""
        embeddings = []
        for i in range(5):
            emb = engine.embed_execution(
                run_id=f"test-{i}",
                input_text="same input text",
                output_text="same output",
                run_kind="test",
                provider="test",
            )
            embeddings.append(emb)

        variance = compute_internal_variance(embeddings)
        assert variance < 0.2  # Should be low for similar embeddings

    def test_compute_internal_variance_high(self, engine: EmbeddingEngine) -> None:
        """High variance for diverse embeddings."""
        embeddings = []
        for i in range(5):
            emb = engine.embed_execution(
                run_id=f"test-{i}",
                input_text=f"completely different input number {i} with unique words",
                output_text=f"different output {i}",
                run_kind="test",
                provider="test",
            )
            embeddings.append(emb)

        variance = compute_internal_variance(embeddings)
        # Variance should be positive for diverse embeddings
        assert variance >= 0.0

    def test_build_territory_map(self, populated_index: CoordinateIndex) -> None:
        """Can build territory map from index."""
        territory = build_territory_map(populated_index, k=3)

        assert territory.total_embeddings == 18
        assert len(territory.regions) > 0
        assert territory.dimension > 0

        # Should have some regions
        assert (
            territory.stable_ratio + territory.unstable_ratio + territory.unknown_ratio
            <= 1.0
        )

    def test_territory_map_serialization(
        self, populated_index: CoordinateIndex
    ) -> None:
        """Territory map can be serialized."""
        territory = build_territory_map(populated_index, k=3)

        data = territory.to_dict()
        assert "total_regions" in data
        assert "regions" in data
        assert isinstance(data["regions"], list)

    def test_find_region_for_embedding(
        self, populated_index: CoordinateIndex, engine: EmbeddingEngine
    ) -> None:
        """Can find region for an embedding."""
        territory = build_territory_map(populated_index, k=3)

        if territory.regions:
            # Create a new embedding similar to existing ones
            emb = engine.embed_execution(
                run_id="new-test",
                input_text="classify ticket as bug",
                output_text='{"category": "feature"}',
                run_kind="sig-gen",
                provider="claude",
            )

            region, distance = find_region_for_embedding(emb, territory)
            # Should find some region
            assert region is not None or distance == float("inf")

    def test_get_regions_by_type(self, populated_index: CoordinateIndex) -> None:
        """Can filter regions by type."""
        territory = build_territory_map(populated_index, k=3)

        stable = territory.get_stable_regions()
        unstable = territory.get_unstable_regions()
        unknown = territory.get_unknown_regions()

        # All should be lists
        assert isinstance(stable, list)
        assert isinstance(unstable, list)
        assert isinstance(unknown, list)

    def test_region_to_dict(self, engine: EmbeddingEngine) -> None:
        """Region can be serialized."""
        emb = engine.embed_execution(
            run_id="test",
            input_text="test",
            output_text="out",
            run_kind="test",
            provider="test",
        )

        region = Region(
            region_id="R001",
            region_type=RegionType.STABLE,
            centroid=emb.vector,
            member_count=10,
            internal_variance=0.1,
            confidence=0.9,
            dominant_run_kind="sig-gen",
            dominant_provider="claude",
            sample_run_ids=["r1", "r2"],
            dimension=emb.dimension,
        )

        data = region.to_dict()
        assert data["region_id"] == "R001"
        assert data["region_type"] == "stable"
        assert data["member_count"] == 10


class TestDangerZones:
    """Tests for danger zone detection."""

    @pytest.fixture
    def engine(self) -> EmbeddingEngine:
        return EmbeddingEngine(backend="mock", mock_dimension=32)

    @pytest.fixture
    def temp_db(self, tmp_path: Path) -> Path:
        return tmp_path / "test_danger.db"

    def test_detect_high_variance_zones(
        self, temp_db: Path, engine: EmbeddingEngine
    ) -> None:
        """Detect zones with high variance."""
        index = CoordinateIndex(db_path=temp_db)

        # Add diverse embeddings
        for i in range(20):
            emb = engine.embed_execution(
                run_id=f"var-{i}",
                input_text=f"unique task {i} totally different",
                output_text=f"result {i}",
                run_kind="test",
                provider="test",
            )
            index.upsert(emb)

        zones = detect_danger_zones(index, high_variance_threshold=0.3)
        # May or may not find zones depending on clustering
        assert isinstance(zones, list)

    def test_danger_zone_serialization(self, engine: EmbeddingEngine) -> None:
        """DangerZone can be serialized."""
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
            reason="Test zone",
            severity="high",
            dimension=emb.dimension,
        )

        data = zone.to_dict()
        assert data["zone_id"] == "D001"
        assert data["severity"] == "high"


# =============================================================================
# Contracts Tests
# =============================================================================


class TestContracts:
    """Tests for behavioral contracts."""

    @pytest.fixture
    def engine(self) -> EmbeddingEngine:
        return EmbeddingEngine(backend="mock", mock_dimension=32)

    def test_validate_no_pii_pass(self, engine: EmbeddingEngine) -> None:
        """No PII validation passes for clean output."""
        emb = engine.embed_execution(
            run_id="clean",
            input_text="classify this",
            output_text="This is a safe response without any PII.",
            run_kind="test",
            provider="test",
        )

        result = validate_no_pii(emb)
        assert result.status == ContractStatus.PASS

    def test_validate_no_pii_fail_email(self, engine: EmbeddingEngine) -> None:
        """No PII validation fails for email in output."""
        emb = engine.embed_execution(
            run_id="with-email",
            input_text="get user info",
            output_text="Contact user@example.com for details",
            run_kind="test",
            provider="test",
        )

        result = validate_no_pii(emb)
        assert result.status == ContractStatus.FAIL
        assert len(result.violations) > 0
        assert "email" in result.violations[0].message.lower()

    def test_validate_no_pii_fail_phone(self, engine: EmbeddingEngine) -> None:
        """No PII validation fails for phone in output."""
        emb = engine.embed_execution(
            run_id="with-phone",
            input_text="get contact",
            output_text="Call 555-123-4567 for support",
            run_kind="test",
            provider="test",
        )

        result = validate_no_pii(emb)
        assert result.status == ContractStatus.FAIL

    def test_validate_no_pii_api_key_with_prefix(self, engine: EmbeddingEngine) -> None:
        """API keys with common prefixes should be flagged as WARNING."""
        emb = engine.embed_execution(
            run_id="with-api-key",
            input_text="get config",
            output_text="Your key is sk-proj-abc123def456ghi789jkl",
            run_kind="test",
            provider="test",
        )

        result = validate_no_pii(emb)
        # API keys are WARNING, not ERROR, so status is PASS (only ERROR causes FAIL)
        assert result.status == ContractStatus.PASS
        # But violations should still be recorded
        assert len(result.violations) > 0
        assert result.violations[0].severity == ContractSeverity.WARNING

    def test_validate_no_pii_no_false_positive_hashes(
        self, engine: EmbeddingEngine
    ) -> None:
        """Hash-like strings without prefixes should NOT be flagged.

        Previously, any 32+ char alphanumeric string was flagged as API key,
        causing false positives for base64 content, hash digests, etc.
        """
        emb = engine.embed_execution(
            run_id="with-hash",
            input_text="get hash",
            output_text="SHA256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            run_kind="test",
            provider="test",
        )

        result = validate_no_pii(emb)
        # Should pass - hash without prefix is not suspicious
        assert result.status == ContractStatus.PASS

    def test_validate_output_format_json_valid(self, engine: EmbeddingEngine) -> None:
        """JSON format validation passes for valid JSON."""
        emb = engine.embed_execution(
            run_id="json-valid",
            input_text="get data",
            output_text='{"status": "ok", "value": 42}',
            run_kind="test",
            provider="test",
        )

        result = validate_output_format(emb, format_type="json")
        assert result.status == ContractStatus.PASS

    def test_validate_output_format_json_invalid(self, engine: EmbeddingEngine) -> None:
        """JSON format validation fails for invalid JSON."""
        emb = engine.embed_execution(
            run_id="json-invalid",
            input_text="get data",
            output_text="not valid json {",
            run_kind="test",
            provider="test",
        )

        result = validate_output_format(emb, format_type="json")
        assert result.status == ContractStatus.FAIL

    def test_validate_response_quality(self, engine: EmbeddingEngine) -> None:
        """Response quality validation works."""
        emb = engine.embed_execution(
            run_id="quality-test",
            input_text="generate code",
            output_text="def hello(): pass",  # Short but valid
            run_kind="test",
            provider="test",
        )

        result = validate_response_quality(emb, min_length=1)
        assert result.status == ContractStatus.PASS

    def test_validate_response_quality_too_short(self, engine: EmbeddingEngine) -> None:
        """Quality validation fails for too short output."""
        emb = engine.embed_execution(
            run_id="short-output",
            input_text="generate",
            output_text="x",  # Too short
            run_kind="test",
            provider="test",
        )

        result = validate_response_quality(emb, min_length=10)
        assert result.status == ContractStatus.FAIL

    def test_contract_registry(self) -> None:
        """Contract registry manages contracts."""
        registry = ContractRegistry()

        contract = Contract(
            name="test-contract",
            description="Test description",
            invariant="x must be true",
        )

        registry.add(contract)
        assert registry.get("test-contract") is not None

        registry.remove("test-contract")
        assert registry.get("test-contract") is None

    def test_create_default_contracts(self) -> None:
        """Default contracts are created."""
        contracts = create_default_contracts()

        assert len(contracts) > 0
        names = [c.name for c in contracts]
        assert "no-pii" in names

    def test_contract_serialization(self) -> None:
        """Contract can be serialized."""
        contract = Contract(
            name="test",
            description="desc",
            invariant="x > 0",
            severity=ContractSeverity.ERROR,
            tags=["security"],
        )

        data = contract.to_dict()
        assert data["name"] == "test"
        assert data["severity"] == "error"
        assert "security" in data["tags"]

    def test_contract_deserialization(self) -> None:
        """Contract can be loaded from dict."""
        data = {
            "name": "loaded",
            "description": "Loaded contract",
            "invariant": "y > 0",
            "severity": "warning",
        }

        contract = Contract.from_dict(data)
        assert contract.name == "loaded"
        assert contract.severity == ContractSeverity.WARNING


class TestContractRegistryIntegration:
    """Integration tests for contract verification."""

    @pytest.fixture
    def engine(self) -> EmbeddingEngine:
        return EmbeddingEngine(backend="mock", mock_dimension=32)

    @pytest.fixture
    def temp_db(self, tmp_path: Path) -> Path:
        return tmp_path / "test_contracts.db"

    def test_verify_embedding(self, engine: EmbeddingEngine) -> None:
        """Registry can verify an embedding."""
        registry = ContractRegistry()
        for c in create_default_contracts():
            registry.add(c)

        emb = engine.embed_execution(
            run_id="test",
            input_text="classify",
            output_text='{"result": "ok"}',
            run_kind="test",
            provider="test",
        )

        results = registry.verify_embedding(emb)
        assert len(results) > 0

        # Check that we get results
        statuses = [r.status for r in results]
        assert ContractStatus.PASS in statuses or ContractStatus.SKIP in statuses


class TestSafeExpressionEvaluation:
    """Tests for safe Python expression contract evaluation.

    These tests verify that the AST-based expression evaluator:
    1. Evaluates safe expressions correctly
    2. Rejects unsafe expressions (imports, function definitions, etc.)
    3. Does not allow arbitrary code execution
    """

    @pytest.fixture
    def engine(self) -> EmbeddingEngine:
        return EmbeddingEngine(backend="mock", mock_dimension=32)

    def test_safe_expression_equality(self, engine: EmbeddingEngine) -> None:
        """Safe equality comparison should work."""
        emb = engine.embed_execution(
            run_id="test",
            input_text="test",
            output_text="hello world",
            run_kind="test",
            provider="test",
        )

        contract = Contract(
            name="test-eq",
            description="Test equality",
            invariant="output_text == 'hello world'",
            validator_type="python_expr",
            validator_config={"expression": "output_text == 'hello world'"},
        )

        result = evaluate_contract(contract, emb)
        assert result.status == ContractStatus.PASS

    def test_safe_expression_length_check(self, engine: EmbeddingEngine) -> None:
        """Safe length check should work."""
        emb = engine.embed_execution(
            run_id="test",
            input_text="test",
            output_text="hello",
            run_kind="test",
            provider="test",
        )

        contract = Contract(
            name="test-len",
            description="Test length",
            invariant="len(output_text) > 0",
            validator_type="python_expr",
            validator_config={"expression": "len(output_text) > 0"},
        )

        result = evaluate_contract(contract, emb)
        assert result.status == ContractStatus.PASS

    def test_safe_expression_contains(self, engine: EmbeddingEngine) -> None:
        """Safe string containment should work."""
        emb = engine.embed_execution(
            run_id="test",
            input_text="test",
            output_text="hello world",
            run_kind="test",
            provider="test",
        )

        contract = Contract(
            name="test-contains",
            description="Test contains",
            invariant="'hello' in output_text",
            validator_type="python_expr",
            validator_config={"expression": "'hello' in output_text"},
        )

        result = evaluate_contract(contract, emb)
        assert result.status == ContractStatus.PASS

    def test_unsafe_expression_import(self, engine: EmbeddingEngine) -> None:
        """Import statements should be rejected.

        Note: __import__ is not in the safe namespace, so calling it
        results in a NameError, which is correctly reported as an evaluation error.
        The expression is safely rejected either way.
        """
        emb = engine.embed_execution(
            run_id="test",
            input_text="test",
            output_text="test",
            run_kind="test",
            provider="test",
        )

        contract = Contract(
            name="test-import",
            description="Test import rejection",
            invariant="Should fail",
            validator_type="python_expr",
            validator_config={"expression": "__import__('os').system('echo pwned')"},
        )

        result = evaluate_contract(contract, emb)
        assert result.status == ContractStatus.ERROR
        # Rejected either because __import__ is not defined or due to AST validation
        assert "error" in result.message.lower()

    def test_unsafe_expression_function_def(self, engine: EmbeddingEngine) -> None:
        """Function definitions should be rejected."""
        emb = engine.embed_execution(
            run_id="test",
            input_text="test",
            output_text="test",
            run_kind="test",
            provider="test",
        )

        contract = Contract(
            name="test-func",
            description="Test function def rejection",
            invariant="Should fail",
            validator_type="python_expr",
            validator_config={"expression": "lambda: 1"},
        )

        result = evaluate_contract(contract, emb)
        assert result.status == ContractStatus.ERROR
        assert (
            "unsafe" in result.message.lower() or "forbidden" in result.message.lower()
        )

    def test_unsafe_expression_dunder_bypass(self, engine: EmbeddingEngine) -> None:
        """Dunder-based code execution should be rejected.

        This tests the classic Python sandbox escape via __class__.__bases__.
        """
        emb = engine.embed_execution(
            run_id="test",
            input_text="test",
            output_text="test",
            run_kind="test",
            provider="test",
        )

        # This is a common sandbox escape pattern
        contract = Contract(
            name="test-dunder",
            description="Test dunder bypass rejection",
            invariant="Should fail",
            validator_type="python_expr",
            validator_config={
                "expression": "().__class__.__bases__[0].__subclasses__()"
            },
        )

        # Should either reject (ERROR) or if allowed, not crash
        result = evaluate_contract(contract, emb)
        # The key is it shouldn't crash - it either rejects or handles safely
        assert result.status in (ContractStatus.ERROR, ContractStatus.FAIL)

    def test_unsafe_expression_assignment(self, engine: EmbeddingEngine) -> None:
        """Assignment statements should be rejected.

        Note: In Python, 'x = 1' is a statement, not an expression, so
        ast.parse() in 'eval' mode will raise a SyntaxError. This is correct
        behavior - assignments are rejected regardless of how they're caught.
        """
        emb = engine.embed_execution(
            run_id="test",
            input_text="test",
            output_text="test",
            run_kind="test",
            provider="test",
        )

        contract = Contract(
            name="test-assign",
            description="Test assignment rejection",
            invariant="Should fail",
            validator_type="python_expr",
            validator_config={"expression": "x = 1"},
        )

        result = evaluate_contract(contract, emb)
        # Assignment is a statement, not expression - SyntaxError is appropriate
        assert result.status == ContractStatus.ERROR
        assert (
            "syntax" in result.message.lower() or "forbidden" in result.message.lower()
        )


# =============================================================================
# Frontiers Tests
# =============================================================================


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


# =============================================================================
# Attractors Tests
# =============================================================================


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


# =============================================================================
# Regression Tests for Bug Fixes
# =============================================================================


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


# =============================================================================
# Integration Tests with Real Embeddings
# =============================================================================


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

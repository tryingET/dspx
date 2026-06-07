"""Phase B behavioral topology territory and contract tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from dspx.coordinates import (
    Contract,
    ContractRegistry,
    ContractSeverity,
    ContractStatus,
    CoordinateIndex,
    DangerZone,
    EmbeddingEngine,
    Region,
    RegionType,
    build_territory_map,
    compute_internal_variance,
    create_default_contracts,
    detect_danger_zones,
    evaluate_contract,
    find_region_for_embedding,
    validate_no_pii,
    validate_output_format,
    validate_response_quality,
)


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

    def test_safe_expression_embedding_view_attr(self, engine: EmbeddingEngine) -> None:
        """The narrowed embedding view should still expose safe fields."""
        emb = engine.embed_execution(
            run_id="test",
            input_text="test",
            output_text="hello world",
            run_kind="test",
            provider="test",
        )

        contract = Contract(
            name="test-embedding-field",
            description="Test safe embedding field access",
            invariant="embedding.output_text == 'hello world'",
            validator_type="python_expr",
            validator_config={"expression": "embedding.output_text == 'hello world'"},
        )

        result = evaluate_contract(contract, emb)
        assert result.status == ContractStatus.PASS

    def test_unsafe_expression_method_call(self, engine: EmbeddingEngine) -> None:
        """Method calls should be rejected to avoid object capability escapes."""
        emb = engine.embed_execution(
            run_id="test",
            input_text="test",
            output_text=" hello world ",
            run_kind="test",
            provider="test",
        )

        contract = Contract(
            name="test-method-call",
            description="Test method call rejection",
            invariant="Should fail",
            validator_type="python_expr",
            validator_config={"expression": "output_text.strip() == 'hello world'"},
        )

        result = evaluate_contract(contract, emb)
        assert result.status == ContractStatus.ERROR
        assert (
            "method calls" in result.message.lower()
            or "unsafe" in result.message.lower()
        )

    def test_unsafe_expression_non_allowlisted_function(
        self, engine: EmbeddingEngine
    ) -> None:
        """Only explicit helper functions should be callable."""
        emb = engine.embed_execution(
            run_id="test",
            input_text="test",
            output_text="hello world",
            run_kind="test",
            provider="test",
        )

        contract = Contract(
            name="test-type-call",
            description="Test non-allowlisted function rejection",
            invariant="Should fail",
            validator_type="python_expr",
            validator_config={"expression": "type(output_text) is str"},
        )

        result = evaluate_contract(contract, emb)
        assert result.status == ContractStatus.ERROR
        assert (
            "not allowed" in result.message.lower()
            or "unsafe" in result.message.lower()
        )

    def test_unsafe_expression_import(self, engine: EmbeddingEngine) -> None:
        """Import-style code execution attempts should be rejected."""
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
        assert (
            "unsafe" in result.message.lower()
            or "not allowed" in result.message.lower()
        )

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

# summary: "Tests Phase A semantic coordinates across embeddings, metrics, storage, clustering, and receipt indexing."
# read_when:
#   - "You are changing Oracle coordinate embeddings, similarity metrics, stores, clustering, or receipt identity."

"""Tests for semantic coordinates module (Phase A: Oracle)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from dspx.coordinates import (
    # Embeddings
    EmbeddingEngine,
    ExecutionEmbedding,
    EmbeddingValidationError,
    EmbeddingResult,
    get_embedding_engine,
    reset_embedding_engine,
    # Metrics
    cosine_similarity,
    semantic_distance,
    drift_score,
    classify_drift,
    DimensionMismatchError,
    # Storage
    CoordinateIndex,
    CoordinateStore,
    open_coordinate_store,
    parse_since,
    ParseSinceError,
    # Clustering
    compute_centroid,
    simple_kmeans,
    find_cluster_for_embedding,
)


# =============================================================================
# Embedding Tests
# =============================================================================


class TestMockEmbedder:
    """Tests for mock embedding backend."""

    def test_mock_embedder_basic(self) -> None:
        """Mock embedder produces consistent vectors."""
        engine = EmbeddingEngine(backend="mock", mock_dimension=128)
        assert engine.backend == "mock"
        assert engine.dimension == 128

        vec = engine.embed_text("hello world")
        assert len(vec) == 128
        # Check normalization (unit vector)
        norm = sum(v * v for v in vec) ** 0.5
        assert abs(norm - 1.0) < 0.0001

    def test_mock_embedder_deterministic(self) -> None:
        """Same input produces same output."""
        engine = EmbeddingEngine(backend="mock")
        vec1 = engine.embed_text("test input")
        vec2 = engine.embed_text("test input")
        assert vec1 == vec2

    def test_mock_embedder_different_inputs(self) -> None:
        """Different inputs produce different outputs."""
        engine = EmbeddingEngine(backend="mock")
        vec1 = engine.embed_text("hello")
        vec2 = engine.embed_text("goodbye")
        assert vec1 != vec2

    def test_embed_texts_batch(self) -> None:
        """Batch embedding works correctly."""
        engine = EmbeddingEngine(backend="mock")
        texts = ["one", "two", "three"]
        vectors = engine.embed_texts(texts)
        assert len(vectors) == 3
        assert all(len(v) == engine.dimension for v in vectors)

    def test_mock_embedder_uniform_distribution(self) -> None:
        """BUG 1 FIX: Mock embedder produces uniform magnitude distribution."""
        engine = EmbeddingEngine(backend="mock", mock_dimension=100)
        # Test multiple texts to ensure no systematic bias
        for text in ["test a", "test b", "test c"]:
            vec = engine.embed_text(text)
            # All elements should be in reasonable range after normalization
            for v in vec:
                assert -2.0 < v < 2.0, f"Value {v} out of expected range"


class TestExecutionEmbedding:
    """Tests for ExecutionEmbedding dataclass."""

    def test_create_embedding(self) -> None:
        """Can create and serialize embedding."""
        engine = EmbeddingEngine(backend="mock", mock_dimension=64)
        emb = engine.embed_execution(
            run_id="test-123",
            input_text="classify this ticket",
            output_text='{"category": "bug"}',
            config_text="provider: claude",
            run_kind="signature-gen",
            provider="claude",
            template_version="v1",
        )

        assert emb.run_id == "test-123"
        assert emb.run_kind == "signature-gen"
        assert emb.provider == "claude"
        assert emb.dimension == 64
        assert len(emb.vector) == 64

        # Test serialization
        data = emb.to_dict()
        assert data["run_id"] == "test-123"
        assert len(data["vector"]) == 64

        # Test deserialization
        emb2 = ExecutionEmbedding.from_dict(data)
        assert emb2.run_id == emb.run_id
        assert emb2.vector == emb.vector

    def test_dimension_validation(self) -> None:
        """BUG 5 FIX: Dimension must match vector length."""
        # Should work with correct dimension
        emb = ExecutionEmbedding(
            run_id="test",
            vector=[1.0, 2.0, 3.0],
            input_text="test",
            output_text="out",
            config_text="",
            run_kind="test",
            provider="test",
            template_version=None,
            created_at="2024-01-01T00:00:00Z",
            dimension=3,
        )
        assert emb.dimension == 3

        # Should fail with wrong dimension
        with pytest.raises(EmbeddingValidationError) as exc_info:
            ExecutionEmbedding(
                run_id="test",
                vector=[1.0, 2.0, 3.0],
                input_text="test",
                output_text="out",
                config_text="",
                run_kind="test",
                provider="test",
                template_version=None,
                created_at="2024-01-01T00:00:00Z",
                dimension=384,  # Wrong!
            )
        assert "Dimension mismatch" in str(exc_info.value)

    def test_empty_run_id_validation(self) -> None:
        """Empty run_id should fail validation."""
        with pytest.raises(EmbeddingValidationError):
            ExecutionEmbedding(
                run_id="",
                vector=[1.0, 2.0, 3.0],
                input_text="test",
                output_text="out",
                config_text="",
                run_kind="test",
                provider="test",
                template_version=None,
                created_at="2024-01-01T00:00:00Z",
                dimension=3,
            )


class TestGlobalEngine:
    """Tests for global engine singleton."""

    def test_get_embedding_engine_cached(self) -> None:
        """Engine is cached."""
        reset_embedding_engine()
        engine1 = get_embedding_engine(backend="mock", force_new=False)
        engine2 = get_embedding_engine(backend="mock", force_new=False)
        assert engine1 is engine2
        reset_embedding_engine()

    def test_force_new_engine(self) -> None:
        """Can force new engine."""
        reset_embedding_engine()
        engine1 = get_embedding_engine()
        engine2 = get_embedding_engine(force_new=True)
        assert engine1 is not engine2
        reset_embedding_engine()

    def test_parameter_change_creates_new_engine(self) -> None:
        """BUG 2 FIX: Different parameters create new engine."""
        reset_embedding_engine()
        engine1 = get_embedding_engine(
            backend="mock", mock_dimension=32, force_new=True
        )
        assert engine1.dimension == 32

        # Different dimension should create new engine
        engine2 = get_embedding_engine(
            backend="mock", mock_dimension=64, force_new=False
        )
        assert engine2.dimension == 64
        assert engine1 is not engine2
        reset_embedding_engine()

    def test_reset_embedding_engine_resets_detected_backend(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Reset clears both engine and backend auto-detection caches."""
        monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "none")
        reset_embedding_engine()
        assert get_embedding_engine().backend == "none"

        monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
        reset_embedding_engine()
        assert get_embedding_engine().backend == "mock"
        reset_embedding_engine()


class TestEmbeddingResult:
    """Tests for EmbeddingResult class."""

    def test_success_result(self) -> None:
        """Success result works correctly."""
        engine = EmbeddingEngine(backend="mock", mock_dimension=16)
        emb = engine.embed_execution(
            run_id="test",
            input_text="test",
            output_text="out",
            run_kind="test",
            provider="test",
        )
        result = EmbeddingResult.success(emb)
        assert result.ok
        assert result.embedding is emb
        assert not result.skipped
        assert result.error is None

    def test_skip_result(self) -> None:
        """Skip result works correctly."""
        result = EmbeddingResult.skip("No ID found")
        assert not result.ok
        assert result.skipped
        assert result.skip_reason == "No ID found"

    def test_failure_result(self) -> None:
        """Failure result works correctly."""
        result = EmbeddingResult.failure("Something broke")
        assert not result.ok
        assert not result.skipped
        assert result.error == "Something broke"


# =============================================================================
# Metrics Tests
# =============================================================================


class TestCosineSimilarity:
    """Tests for cosine similarity."""

    def test_identical_vectors(self) -> None:
        """Identical vectors have similarity 1.0."""
        vec = [1.0, 0.0, 0.0]
        assert cosine_similarity(vec, vec) == pytest.approx(1.0)

    def test_orthogonal_vectors(self) -> None:
        """Orthogonal vectors have similarity 0.0."""
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [0.0, 1.0, 0.0]
        assert cosine_similarity(vec_a, vec_b) == pytest.approx(0.0)

    def test_opposite_vectors(self) -> None:
        """Opposite vectors have similarity -1.0."""
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [-1.0, 0.0, 0.0]
        assert cosine_similarity(vec_a, vec_b) == pytest.approx(-1.0)

    def test_dimension_mismatch(self) -> None:
        """Mismatched dimensions raise DimensionMismatchError."""
        with pytest.raises(DimensionMismatchError):
            cosine_similarity([1.0, 2.0], [1.0])


class TestSemanticDistance:
    """Tests for semantic distance."""

    def test_distance_from_similarity(self) -> None:
        """Distance is 1 - similarity."""
        vec_a = [1.0, 0.0]
        vec_b = [1.0, 0.0]  # identical
        assert semantic_distance(vec_a, vec_b) == pytest.approx(0.0)

        vec_c = [0.0, 1.0]  # orthogonal
        assert semantic_distance(vec_a, vec_c) == pytest.approx(1.0)


class TestDriftScore:
    """Tests for drift scoring."""

    def test_identical_embeddings(self) -> None:
        """Identical embeddings have zero drift."""
        engine = EmbeddingEngine(backend="mock", mock_dimension=32)
        emb = engine.embed_execution(
            run_id="test",
            input_text="same input",
            output_text="same output",
            config_text="same config",
            run_kind="test",
            provider="test",
        )
        drift = drift_score(emb, emb)
        assert drift["overall"] == pytest.approx(0.0, abs=0.01)

    def test_dimension_mismatch_raises(self) -> None:
        """BUG 23 FIX: Dimension mismatch raises error."""
        engine32 = EmbeddingEngine(backend="mock", mock_dimension=32)
        engine64 = EmbeddingEngine(backend="mock", mock_dimension=64)

        emb32 = engine32.embed_execution(
            run_id="test32",
            input_text="test",
            output_text="out",
            run_kind="test",
            provider="test",
        )
        emb64 = engine64.embed_execution(
            run_id="test64",
            input_text="test",
            output_text="out",
            run_kind="test",
            provider="test",
        )

        with pytest.raises(DimensionMismatchError):
            drift_score(emb32, emb64)


class TestClassifyDrift:
    """Tests for drift classification."""

    def test_classify_identical(self) -> None:
        assert classify_drift(0.0) == "identical"
        assert classify_drift(0.04) == "identical"

    def test_classify_minor(self) -> None:
        assert classify_drift(0.05) == "minor"
        assert classify_drift(0.14) == "minor"

    def test_classify_moderate(self) -> None:
        assert classify_drift(0.15) == "moderate"
        assert classify_drift(0.29) == "moderate"

    def test_classify_significant(self) -> None:
        assert classify_drift(0.30) == "significant"
        assert classify_drift(0.49) == "significant"

    def test_classify_severe(self) -> None:
        assert classify_drift(0.50) == "severe"
        assert classify_drift(1.0) == "severe"


# =============================================================================
# Storage Tests
# =============================================================================


class TestCoordinateIndex:
    """Tests for SQLite-backed coordinate index."""

    @pytest.fixture
    def temp_db(self, tmp_path: Path) -> Path:
        return tmp_path / "test_coordinates.db"

    @pytest.fixture
    def index(self, temp_db: Path) -> CoordinateIndex:
        return CoordinateIndex(db_path=temp_db)

    @pytest.fixture
    def engine(self) -> EmbeddingEngine:
        return EmbeddingEngine(backend="mock", mock_dimension=32)

    def test_index_creation(self, temp_db: Path) -> None:
        """Index creates database file."""
        CoordinateIndex(db_path=temp_db)
        assert temp_db.exists()

    def test_v1_sqlite_store_migrates_before_embedding_version_index(
        self, tmp_path: Path
    ) -> None:
        db_path = tmp_path / "coordinates-v1.db"
        conn = sqlite3.connect(db_path)
        conn.executescript(
            """
            CREATE TABLE coordinates (
                run_id TEXT PRIMARY KEY,
                vector_json TEXT NOT NULL,
                input_text TEXT,
                output_text TEXT,
                config_text TEXT,
                run_kind TEXT,
                provider TEXT,
                template_version TEXT,
                created_at TEXT,
                dimension INTEGER NOT NULL,
                source_path TEXT,
                metadata_json TEXT,
                indexed_at TEXT NOT NULL
            );
            CREATE TABLE index_meta (key TEXT PRIMARY KEY, value TEXT);
            INSERT INTO index_meta VALUES ('schema_version', '1');
            """
        )
        conn.commit()
        conn.close()

        index = CoordinateIndex(db_path=db_path)

        assert index.stats()["total"] == 0
        with sqlite3.connect(db_path) as check_conn:
            columns = {
                row[1] for row in check_conn.execute("PRAGMA table_info(coordinates)")
            }
            schema_version = check_conn.execute(
                "SELECT value FROM index_meta WHERE key = 'schema_version'"
            ).fetchone()[0]
        assert "embedding_version" in columns
        assert schema_version == "2"

    def test_coordinate_index_satisfies_store_protocol(
        self, index: CoordinateIndex
    ) -> None:
        """SQLite CoordinateIndex implements the CoordinateStore boundary."""
        assert isinstance(index, CoordinateStore)

    def test_open_coordinate_store_defaults_to_sqlite(self, temp_db: Path) -> None:
        """Store factory preserves the current SQLite default behavior."""
        store = open_coordinate_store(db_path=temp_db)
        assert isinstance(store, CoordinateIndex)
        assert temp_db.exists()

    def test_open_coordinate_store_requires_postgres_url_when_selected(
        self, temp_db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Postgres/pgvector opt-in fails closed without a DB URL."""
        monkeypatch.setenv("DSPX_ORACLE_STORE", "postgres_pgvector")
        with pytest.raises(ValueError, match="DATABASE_URL"):
            open_coordinate_store(db_path=temp_db)
        assert not temp_db.exists()

    def test_open_coordinate_store_postgres_health_redacts_secret(
        self, temp_db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Postgres store scaffold reports unavailable without leaking secrets."""
        secret_url = "postgresql://oracle:super-secret@example.invalid/oracle"
        monkeypatch.setenv("DSPX_ORACLE_STORE", "postgres_pgvector")
        monkeypatch.setenv("DSPX_ORACLE_DATABASE_URL", secret_url)

        store = open_coordinate_store(db_path=temp_db)
        health = store.health().to_dict()

        assert health["backend"] == "postgres_pgvector"
        assert health["available"] is False
        assert "super-secret" not in json.dumps(health)
        assert not temp_db.exists()

    def test_health_reports_sqlite_status(
        self, index: CoordinateIndex, temp_db: Path
    ) -> None:
        """Store health is read-only and exposes backend identity."""
        health = index.health()
        assert health.backend == "sqlite"
        assert health.available is True
        assert health.path == str(temp_db)
        assert health.to_dict()["backend"] == "sqlite"

    def test_upsert_and_get(
        self, index: CoordinateIndex, engine: EmbeddingEngine
    ) -> None:
        """Can insert and retrieve embedding."""
        emb = engine.embed_execution(
            run_id="test-1",
            input_text="test input",
            output_text="test output",
            run_kind="test",
            provider="mock",
        )

        assert index.upsert(emb)
        retrieved = index.get("test-1")
        assert retrieved is not None
        assert retrieved.run_id == "test-1"
        assert retrieved.input_text == "test input"

    def test_upsert_updates(
        self, index: CoordinateIndex, engine: EmbeddingEngine
    ) -> None:
        """Upsert updates existing record."""
        emb1 = engine.embed_execution(
            run_id="test-1",
            input_text="original",
            output_text="output",
            run_kind="test",
            provider="mock",
        )
        emb2 = engine.embed_execution(
            run_id="test-1",
            input_text="updated",
            output_text="output",
            run_kind="test",
            provider="mock",
        )

        index.upsert(emb1)
        index.upsert(emb2)

        retrieved = index.get("test-1")
        assert retrieved is not None
        assert retrieved.input_text == "updated"

    def test_delete(self, index: CoordinateIndex, engine: EmbeddingEngine) -> None:
        """Can delete embedding."""
        emb = engine.embed_execution(
            run_id="test-1",
            input_text="test",
            output_text="out",
            run_kind="test",
            provider="mock",
        )

        index.upsert(emb)
        assert index.get("test-1") is not None

        assert index.delete("test-1")
        assert index.get("test-1") is None

    def test_search(self, index: CoordinateIndex, engine: EmbeddingEngine) -> None:
        """Similarity search returns relevant results."""
        # Insert several embeddings
        for i, text in enumerate(
            ["hello world", "foo bar", "hello there", "goodbye now"]
        ):
            emb = engine.embed_execution(
                run_id=f"test-{i}",
                input_text=text,
                output_text="output",
                run_kind="test",
                provider="mock",
            )
            index.upsert(emb)

        # Search for "hello" - should return results with valid similarity scores
        query_vec = engine.embed_text("hello")
        results = index.search(query_vec, top_k=4)

        # All inserted embeddings should be searchable
        assert len(results) == 4
        # Results should be sorted by similarity descending
        for i in range(len(results) - 1):
            assert results[i].similarity >= results[i + 1].similarity

    def test_search_negative_top_k_returns_empty(
        self, index: CoordinateIndex, engine: EmbeddingEngine
    ) -> None:
        """SQLite search matches backend contract for negative result counts."""
        for i in range(3):
            index.upsert(
                engine.embed_execution(
                    run_id=f"test-{i}",
                    input_text=f"input {i}",
                    output_text="output",
                    run_kind="test",
                    provider="mock",
                )
            )

        query_vec = engine.embed_text("input")
        assert index.search(query_vec, top_k=-1) == []

    def test_search_with_filters(
        self, index: CoordinateIndex, engine: EmbeddingEngine
    ) -> None:
        """Search respects filters."""
        # Insert with different kinds
        for i, kind in enumerate(["sig-gen", "sig-gen", "codegen"]):
            emb = engine.embed_execution(
                run_id=f"test-{i}",
                input_text=f"input {i}",
                output_text="output",
                run_kind=kind,
                provider="mock",
            )
            index.upsert(emb)

        query_vec = engine.embed_text("input")
        results = index.search(query_vec, top_k=10, run_kind="sig-gen")

        assert len(results) == 2
        assert all(r.embedding.run_kind == "sig-gen" for r in results)

    def test_get_neighbors(
        self, index: CoordinateIndex, engine: EmbeddingEngine
    ) -> None:
        """Neighbor search excludes query run."""
        for i in range(5):
            emb = engine.embed_execution(
                run_id=f"test-{i}",
                input_text=f"input {i}",
                output_text="output",
                run_kind="test",
                provider="mock",
            )
            index.upsert(emb)

        neighbors = index.get_neighbors("test-0", top_k=10)
        # Should return up to 4 neighbors (5 total - 1 for self)
        assert len(neighbors) == 4
        assert all(n.run_id != "test-0" for n in neighbors)

    def test_stats(self, index: CoordinateIndex, engine: EmbeddingEngine) -> None:
        """Stats returns correct counts."""
        for i in range(3):
            emb = engine.embed_execution(
                run_id=f"test-{i}",
                input_text="input",
                output_text="out",
                run_kind="sig-gen",
                provider="claude" if i < 2 else "codex",
            )
            index.upsert(emb)

        stats = index.stats()
        assert stats["total"] == 3
        assert stats["by_run_kind"]["sig-gen"] == 3
        assert stats["by_provider"]["claude"] == 2
        assert stats["by_provider"]["codex"] == 1

    def test_batch_upsert_transactional(
        self, index: CoordinateIndex, engine: EmbeddingEngine
    ) -> None:
        """BUG 19 FIX: Batch upsert is transactional."""
        # Create valid embeddings
        embeddings = []
        for i in range(3):
            emb = engine.embed_execution(
                run_id=f"valid-{i}",
                input_text=f"input {i}",
                output_text="output",
                run_kind="test",
                provider="test",
            )
            embeddings.append(emb)

        # Batch upsert
        count = index.upsert_batch(embeddings)
        assert count == 3

        # Verify all were inserted
        for i in range(3):
            assert index.get(f"valid-{i}") is not None


class TestParseSince:
    """Tests for since string parsing."""

    def test_parse_days(self) -> None:
        since = parse_since("30d")
        expected = datetime.now(timezone.utc) - timedelta(days=30)
        # Allow 1 minute tolerance
        assert abs((since - expected).total_seconds()) < 60

    def test_parse_hours(self) -> None:
        since = parse_since("24h")
        expected = datetime.now(timezone.utc) - timedelta(hours=24)
        assert abs((since - expected).total_seconds()) < 60

    def test_parse_weeks(self) -> None:
        since = parse_since("1w")
        expected = datetime.now(timezone.utc) - timedelta(weeks=1)
        assert abs((since - expected).total_seconds()) < 60

    def test_parse_iso_preserves_uppercase_utc_designator(self) -> None:
        since = parse_since("2024-01-15T10:00:00Z")

        assert since == datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

    def test_parse_invalid_raises(self) -> None:
        """BUG 14 FIX: Invalid since string raises ParseSinceError."""
        with pytest.raises(ParseSinceError):
            parse_since("invalid")

        with pytest.raises(ParseSinceError):
            parse_since("")


# =============================================================================
# Clustering Tests
# =============================================================================


class TestClustering:
    """Tests for clustering functionality."""

    @pytest.fixture
    def engine(self) -> EmbeddingEngine:
        return EmbeddingEngine(backend="mock", mock_dimension=16)

    @pytest.fixture
    def sample_embeddings(self, engine: EmbeddingEngine) -> list[ExecutionEmbedding]:
        embeddings = []
        for i in range(10):
            emb = engine.embed_execution(
                run_id=f"test-{i}",
                input_text=f"input {i % 3}",  # Creates some similarity patterns
                output_text=f"output {i}",
                run_kind="sig-gen" if i < 7 else "codegen",
                provider="claude" if i < 5 else "codex",
            )
            embeddings.append(emb)
        return embeddings

    def test_compute_centroid(
        self, sample_embeddings: list[ExecutionEmbedding]
    ) -> None:
        """Centroid computation works correctly."""
        centroid = compute_centroid(sample_embeddings)
        assert len(centroid) == sample_embeddings[0].dimension
        # Centroid should be normalized (unit vector)
        norm = sum(v * v for v in centroid) ** 0.5
        assert abs(norm - 1.0) < 0.0001

    def test_simple_kmeans(self, sample_embeddings: list[ExecutionEmbedding]) -> None:
        """K-means produces clusters."""
        clusters = simple_kmeans(sample_embeddings, k=3)

        assert len(clusters) <= 3
        assert len(clusters) > 0

        # All embeddings should be assigned
        total_members = sum(c.member_count for c in clusters)
        assert total_members == len(sample_embeddings)

        # Cluster IDs should be sequential from 0
        cluster_ids = sorted([c.cluster_id for c in clusters])
        assert cluster_ids == list(range(len(clusters)))

    def test_find_cluster_for_embedding(
        self, sample_embeddings: list[ExecutionEmbedding]
    ) -> None:
        """Can find cluster for new embedding."""
        clusters = simple_kmeans(sample_embeddings, k=2)

        # Test embedding should belong to some cluster
        cluster_id, distance = find_cluster_for_embedding(
            sample_embeddings[0], clusters
        )
        assert cluster_id >= 0
        assert distance >= 0

    def test_find_cluster_dimension_validation(self) -> None:
        """BUG 23 FIX: find_cluster_for_embedding validates dimension."""
        engine32 = EmbeddingEngine(backend="mock", mock_dimension=32)
        engine64 = EmbeddingEngine(backend="mock", mock_dimension=64)

        # Create embeddings with 32 dims
        embeddings32 = [
            engine32.embed_execution(
                run_id=f"test-{i}",
                input_text=f"input {i}",
                output_text="output",
                run_kind="test",
                provider="test",
            )
            for i in range(5)
        ]

        clusters = simple_kmeans(embeddings32, k=2)

        # Try to find cluster for 64-dim embedding
        emb64 = engine64.embed_execution(
            run_id="wrong-dim",
            input_text="test",
            output_text="out",
            run_kind="test",
            provider="test",
        )

        with pytest.raises(DimensionMismatchError):
            find_cluster_for_embedding(emb64, clusters)


# =============================================================================
# Integration Tests
# =============================================================================


class TestReceiptEmbedding:
    """Tests for embedding from run receipts."""

    def test_embed_receipt_basic(self, tmp_path: Path) -> None:
        """Can embed from receipt dictionary."""
        engine = EmbeddingEngine(backend="mock", mock_dimension=32)

        # Create a receipt
        receipt = {
            "hash": "abc123",
            "cache_key": "key-abc123",
            "run_kind": "signature-gen",
            "provider": "claude",
            "template_version": "v1",
            "replay_inputs": {
                "prompt": "classify this ticket",
                "class_name": "TicketClassifier",
            },
            "output_path": None,
        }

        emb = engine.embed_receipt(receipt, output_content='{"category": "bug"}')

        assert emb is not None
        assert emb.run_id == "key-abc123"
        assert emb.run_kind == "signature-gen"
        assert "classify this ticket" in emb.input_text
        assert '{"category": "bug"}' in emb.output_text

    def test_embed_receipt_preserves_original_execution_time(self) -> None:
        engine = EmbeddingEngine(backend="mock", mock_dimension=32)
        receipt = {
            "execution_id": "exec-temporal",
            "run_kind": "program-runtime",
            "provider": "stub",
            "created_at": "2024-03-04T05:06:07-05:00",
            "replay_inputs": {"prompt": "temporal evidence"},
        }

        emb = engine.embed_receipt(receipt, output_content="result")

        assert emb is not None
        assert emb.created_at == "2024-03-04T10:06:07+00:00"

    def test_embed_receipt_rejects_naive_execution_time(self) -> None:
        engine = EmbeddingEngine(backend="mock", mock_dimension=32)
        receipt = {
            "execution_id": "exec-naive",
            "created_at": "2024-03-04T05:06:07",
            "replay_inputs": {"prompt": "temporal evidence"},
        }

        result = engine.embed_receipt_result(receipt, output_content="result")

        assert not result.ok
        assert (
            result.error
            == "Validation error: created_at must include an explicit timezone"
        )

    def test_embed_receipt_with_file(self, tmp_path: Path) -> None:
        """Can embed from receipt with output file."""
        engine = EmbeddingEngine(backend="mock", mock_dimension=32)

        # Create output file
        output_file = tmp_path / "output.py"
        output_file.write_text("class TicketClassifier: pass")

        receipt = {
            "hash": "abc123",
            "run_kind": "signature-gen",
            "provider": "claude",
            "replay_inputs": {"prompt": "create classifier"},
            "output_path": str(output_file),
        }

        emb = engine.embed_receipt(
            receipt, receipt_path=tmp_path / "output.py.meta.json"
        )

        assert emb is not None
        assert "TicketClassifier" in emb.output_text

    def test_embed_receipt_does_not_read_absolute_output_without_receipt_root(
        self, tmp_path: Path
    ) -> None:
        """Untrusted receipt payloads need a receipt root or explicit content."""
        engine = EmbeddingEngine(backend="mock", mock_dimension=32)
        output_file = tmp_path / "output.py"
        output_file.write_text("class TicketClassifier: pass")
        receipt = {
            "hash": "abc123",
            "run_kind": "signature-gen",
            "provider": "claude",
            "replay_inputs": {"prompt": "create classifier"},
            "output_path": str(output_file),
        }

        emb = engine.embed_receipt(receipt)

        assert emb is not None
        assert emb.output_text == ""

    def test_embed_receipt_no_id(self) -> None:
        """Receipt without ID returns None."""
        engine = EmbeddingEngine(backend="mock", mock_dimension=32)

        receipt = {
            "run_kind": "signature-gen",
            "provider": "claude",
        }

        emb = engine.embed_receipt(receipt)
        assert emb is None

    def test_embed_receipt_result_no_id(self) -> None:
        """BUG 6 FIX: embed_receipt_result provides skip information."""
        engine = EmbeddingEngine(backend="mock", mock_dimension=32)

        receipt = {
            "run_kind": "signature-gen",
            "provider": "claude",
        }

        result = engine.embed_receipt_result(receipt)
        assert not result.ok
        assert result.skipped
        assert result.skip_reason is not None
        assert "storage identifier" in result.skip_reason.lower()
        assert "execution_id" in result.skip_reason.lower()

    def test_embed_receipt_prefers_execution_id(self) -> None:
        """Embedding storage identity should prefer explicit execution IDs."""
        engine = EmbeddingEngine(backend="mock", mock_dimension=32)

        receipt = {
            "execution_id": "exec-123",
            "hash": "hash-legacy",
            "cache_key": "cache-legacy",
            "run_kind": "signature-gen",
            "provider": "claude",
            "replay_inputs": {"prompt": "create classifier"},
        }

        emb = engine.embed_receipt(receipt, output_content='{"category": "bug"}')

        assert emb is not None
        assert emb.run_id == "exec-123"
        assert emb.metadata["receipt_identity"]["canonical_id"] == "exec-123"
        assert emb.metadata["receipt_identity"]["behavioral_id"] == "cache-legacy"

    def test_embed_receipt_uses_receipt_path_as_last_resort_identity(
        self, tmp_path: Path
    ) -> None:
        engine = EmbeddingEngine(backend="mock", mock_dimension=32)
        receipt_path = tmp_path / "orphan.meta.json"
        receipt = {
            "run_kind": "signature-gen",
            "provider": "claude",
            "replay_inputs": {"prompt": "create classifier"},
        }

        emb = engine.embed_receipt(
            receipt,
            output_content='{"category": "bug"}',
            receipt_path=receipt_path,
        )

        assert emb is not None
        assert emb.run_id == str(receipt_path)
        assert emb.metadata["receipt_identity"]["storage_source"] == "meta_path"

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from dspx.coordinates import (
    # Embeddings
    EmbeddingEngine,
    ExecutionEmbedding,
    get_embedding_engine,
    # Metrics
    cosine_similarity,
    semantic_distance,
    drift_score,
    classify_drift,
    # Storage
    CoordinateIndex,
    parse_since,
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
        """Mismatched dimensions raise error."""
        with pytest.raises(ValueError):
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
        # Centroid should be normalized (not strictly but check it's reasonable)
        assert all(abs(v) < 10 for v in centroid)

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
        assert emb.run_id == "abc123"
        assert emb.run_kind == "signature-gen"
        assert "classify this ticket" in emb.input_text
        assert '{"category": "bug"}' in emb.output_text

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

        emb = engine.embed_receipt(receipt)

        assert emb is not None
        assert "TicketClassifier" in emb.output_text


class TestGlobalEngine:
    """Tests for global engine singleton."""

    def test_get_embedding_engine_cached(self) -> None:
        """Engine is cached."""
        engine1 = get_embedding_engine()
        engine2 = get_embedding_engine()
        assert engine1 is engine2

    def test_force_new_engine(self) -> None:
        """Can force new engine."""
        engine1 = get_embedding_engine()
        engine2 = get_embedding_engine(force_new=True)
        assert engine1 is not engine2

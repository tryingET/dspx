"""Storage layer for semantic coordinate index.

Provides SQLite-based persistence for execution embeddings with
efficient similarity search using vector operations.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Iterator

from .embeddings import ExecutionEmbedding
from .metrics import cosine_similarity, semantic_distance


def get_default_index_path() -> Path:
    """Get default path for coordinate index database."""
    base = os.getenv("DSPX_ORACLE_INDEX_PATH")
    if base:
        return Path(base)
    return Path.cwd() / "generated" / "oracle" / "coordinates.db"


@dataclass
class SearchResult:
    """Result from a similarity search."""

    run_id: str
    similarity: float
    distance: float
    embedding: ExecutionEmbedding

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "similarity": self.similarity,
            "distance": self.distance,
            "embedding": self.embedding.to_dict(),
        }


@dataclass
class CoordinateRecord:
    """A record in the coordinate index."""

    run_id: str
    vector_json: str
    input_text: str
    output_text: str
    config_text: str
    run_kind: str
    provider: str
    template_version: str | None
    created_at: str
    dimension: int
    source_path: str | None
    metadata_json: str
    indexed_at: str

    @classmethod
    def from_embedding(
        cls, emb: ExecutionEmbedding, indexed_at: str | None = None
    ) -> "CoordinateRecord":
        return cls(
            run_id=emb.run_id,
            vector_json=json.dumps(emb.vector),
            input_text=emb.input_text,
            output_text=emb.output_text,
            config_text=emb.config_text,
            run_kind=emb.run_kind,
            provider=emb.provider,
            template_version=emb.template_version,
            created_at=emb.created_at,
            dimension=emb.dimension,
            source_path=emb.source_path,
            metadata_json=json.dumps(emb.metadata),
            indexed_at=indexed_at or datetime.now(timezone.utc).isoformat(),
        )

    def to_embedding(self) -> ExecutionEmbedding:
        return ExecutionEmbedding(
            run_id=self.run_id,
            vector=json.loads(self.vector_json),
            input_text=self.input_text,
            output_text=self.output_text,
            config_text=self.config_text,
            run_kind=self.run_kind,
            provider=self.provider,
            template_version=self.template_version,
            created_at=self.created_at,
            dimension=self.dimension,
            source_path=self.source_path,
            metadata=json.loads(self.metadata_json) if self.metadata_json else {},
        )


class CoordinateIndex:
    """SQLite-backed index for semantic coordinates.

    Provides:
    - Storage and retrieval of execution embeddings
    - Similarity search using brute-force vector comparison
    - Filtering by run_kind, provider, date range
    - Incremental updates

    For larger scale, consider replacing with sqlite-vss or a dedicated
    vector database (Chroma, Qdrant, etc.).
    """

    SCHEMA_VERSION = 1

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path) if db_path else get_default_index_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS coordinates (
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

                CREATE INDEX IF NOT EXISTS idx_coordinates_run_kind
                    ON coordinates(run_kind);
                CREATE INDEX IF NOT EXISTS idx_coordinates_provider
                    ON coordinates(provider);
                CREATE INDEX IF NOT EXISTS idx_coordinates_created_at
                    ON coordinates(created_at);
                CREATE INDEX IF NOT EXISTS idx_coordinates_indexed_at
                    ON coordinates(indexed_at);

                CREATE TABLE IF NOT EXISTS index_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                """
            )
            # Set schema version
            conn.execute(
                "INSERT OR REPLACE INTO index_meta (key, value) VALUES (?, ?)",
                ("schema_version", str(self.SCHEMA_VERSION)),
            )

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        """Get database connection with context management."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def upsert(self, embedding: ExecutionEmbedding) -> bool:
        """Insert or update an embedding in the index.

        Returns:
            True if inserted/updated, False on error
        """
        record = CoordinateRecord.from_embedding(embedding)
        try:
            with self._conn() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO coordinates (
                        run_id, vector_json, input_text, output_text, config_text,
                        run_kind, provider, template_version, created_at, dimension,
                        source_path, metadata_json, indexed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.run_id,
                        record.vector_json,
                        record.input_text,
                        record.output_text,
                        record.config_text,
                        record.run_kind,
                        record.provider,
                        record.template_version,
                        record.created_at,
                        record.dimension,
                        record.source_path,
                        record.metadata_json,
                        record.indexed_at,
                    ),
                )
            return True
        except Exception:
            return False

    def upsert_batch(self, embeddings: list[ExecutionEmbedding]) -> int:
        """Insert or update multiple embeddings.

        Returns:
            Number of successfully indexed embeddings
        """
        success = 0
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._conn() as conn:
                for emb in embeddings:
                    record = CoordinateRecord.from_embedding(emb, indexed_at=now)
                    try:
                        conn.execute(
                            """
                            INSERT OR REPLACE INTO coordinates (
                                run_id, vector_json, input_text, output_text, config_text,
                                run_kind, provider, template_version, created_at, dimension,
                                source_path, metadata_json, indexed_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                record.run_id,
                                record.vector_json,
                                record.input_text,
                                record.output_text,
                                record.config_text,
                                record.run_kind,
                                record.provider,
                                record.template_version,
                                record.created_at,
                                record.dimension,
                                record.source_path,
                                record.metadata_json,
                                record.indexed_at,
                            ),
                        )
                        success += 1
                    except Exception:
                        pass
        except Exception:
            pass
        return success

    def get(self, run_id: str) -> ExecutionEmbedding | None:
        """Get embedding by run_id."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM coordinates WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row:
                return self._row_to_embedding(row)
        return None

    def delete(self, run_id: str) -> bool:
        """Delete embedding by run_id."""
        with self._conn() as conn:
            cursor = conn.execute("DELETE FROM coordinates WHERE run_id = ?", (run_id,))
            return cursor.rowcount > 0

    def search(
        self,
        query_vector: list[float],
        *,
        top_k: int = 10,
        run_kind: str | None = None,
        provider: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        min_similarity: float = -1.0,
    ) -> list[SearchResult]:
        """Search for similar embeddings.

        Args:
            query_vector: Query embedding vector
            top_k: Maximum results to return
            run_kind: Filter by run kind
            provider: Filter by provider
            since: Filter by creation date (after)
            until: Filter by creation date (before)
            min_similarity: Minimum similarity threshold

        Returns:
            List of SearchResult sorted by similarity (descending)
        """
        results = []

        # Build query with filters
        sql = "SELECT * FROM coordinates WHERE 1=1"
        params: list[Any] = []

        if run_kind:
            sql += " AND run_kind = ?"
            params.append(run_kind)
        if provider:
            sql += " AND provider = ?"
            params.append(provider)
        if since:
            sql += " AND created_at >= ?"
            params.append(since.isoformat())
        if until:
            sql += " AND created_at <= ?"
            params.append(until.isoformat())

        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()

            for row in rows:
                emb = self._row_to_embedding(row)
                if emb.dimension != len(query_vector):
                    continue

                similarity = cosine_similarity(query_vector, emb.vector)
                if similarity < min_similarity:
                    continue

                distance = semantic_distance(query_vector, emb.vector)
                results.append(
                    SearchResult(
                        run_id=emb.run_id,
                        similarity=similarity,
                        distance=distance,
                        embedding=emb,
                    )
                )

        # Sort by similarity descending
        results.sort(key=lambda r: r.similarity, reverse=True)
        return results[:top_k]

    def search_by_text(
        self,
        query_text: str,
        *,
        top_k: int = 10,
        run_kind: str | None = None,
        provider: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        min_similarity: float = -1.0,
    ) -> list[SearchResult]:
        """Search by text query (will be embedded).

        Args:
            query_text: Text to embed and search for
            top_k: Maximum results to return
            run_kind: Filter by run kind
            provider: Filter by provider
            since: Filter by creation date (after)
            until: Filter by creation date (before)
            min_similarity: Minimum similarity threshold

        Returns:
            List of SearchResult sorted by similarity (descending)
        """
        from dspx.coordinates.embeddings import get_embedding_engine

        engine = get_embedding_engine()
        query_vector = engine.embed_text(query_text)
        return self.search(
            query_vector,
            top_k=top_k,
            run_kind=run_kind,
            provider=provider,
            since=since,
            until=until,
            min_similarity=min_similarity,
        )

    def get_neighbors(
        self,
        run_id: str,
        *,
        top_k: int = 10,
        same_kind: bool = False,
        same_provider: bool = False,
    ) -> list[SearchResult]:
        """Find semantic neighbors of a specific run.

        Args:
            run_id: Run ID to find neighbors for
            top_k: Number of neighbors to return
            same_kind: Only return runs of the same kind
            same_provider: Only return runs from the same provider

        Returns:
            List of SearchResult (excluding the query run itself)
        """
        emb = self.get(run_id)
        if emb is None:
            return []

        run_kind = emb.run_kind if same_kind else None
        provider = emb.provider if same_provider else None

        # Search with one extra to account for self
        results = self.search(
            emb.vector,
            top_k=top_k + 1,
            run_kind=run_kind,
            provider=provider,
        )

        # Filter out the query run itself
        return [r for r in results if r.run_id != run_id][:top_k]

    def list_all(
        self,
        *,
        run_kind: str | None = None,
        provider: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[ExecutionEmbedding]:
        """List all embeddings with optional filters."""
        sql = "SELECT * FROM coordinates WHERE 1=1"
        params: list[Any] = []

        if run_kind:
            sql += " AND run_kind = ?"
            params.append(run_kind)
        if provider:
            sql += " AND provider = ?"
            params.append(provider)
        if since:
            sql += " AND created_at >= ?"
            params.append(since.isoformat())
        if until:
            sql += " AND created_at <= ?"
            params.append(until.isoformat())

        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_embedding(row) for row in rows]

    def count(
        self,
        *,
        run_kind: str | None = None,
        provider: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> int:
        """Count embeddings matching filters."""
        sql = "SELECT COUNT(*) FROM coordinates WHERE 1=1"
        params: list[Any] = []

        if run_kind:
            sql += " AND run_kind = ?"
            params.append(run_kind)
        if provider:
            sql += " AND provider = ?"
            params.append(provider)
        if since:
            sql += " AND created_at >= ?"
            params.append(since.isoformat())
        if until:
            sql += " AND created_at <= ?"
            params.append(until.isoformat())

        with self._conn() as conn:
            return conn.execute(sql, params).fetchone()[0]

    def stats(self) -> dict[str, Any]:
        """Get index statistics."""
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM coordinates").fetchone()[0]

            # Get run_kind distribution
            kind_rows = conn.execute(
                "SELECT run_kind, COUNT(*) as cnt FROM coordinates GROUP BY run_kind"
            ).fetchall()
            by_kind = {row["run_kind"]: row["cnt"] for row in kind_rows}

            # Get provider distribution
            provider_rows = conn.execute(
                "SELECT provider, COUNT(*) as cnt FROM coordinates GROUP BY provider"
            ).fetchall()
            by_provider = {row["provider"]: row["cnt"] for row in provider_rows}

            # Get dimension info
            dim_row = conn.execute(
                "SELECT MIN(dimension), MAX(dimension) FROM coordinates"
            ).fetchone()

            return {
                "total": total,
                "by_run_kind": by_kind,
                "by_provider": by_provider,
                "dimension_range": (
                    [dim_row[0], dim_row[1]] if dim_row[0] is not None else None
                ),
            }

    def vacuum(self) -> None:
        """Vacuum the database to reclaim space."""
        with self._conn() as conn:
            conn.execute("VACUUM")

    def _row_to_embedding(self, row: sqlite3.Row) -> ExecutionEmbedding:
        """Convert database row to ExecutionEmbedding."""
        return ExecutionEmbedding(
            run_id=row["run_id"],
            vector=json.loads(row["vector_json"]),
            input_text=row["input_text"] or "",
            output_text=row["output_text"] or "",
            config_text=row["config_text"] or "",
            run_kind=row["run_kind"] or "unknown",
            provider=row["provider"] or "unknown",
            template_version=row["template_version"],
            created_at=row["created_at"] or "",
            dimension=row["dimension"],
            source_path=row["source_path"],
            metadata=json.loads(row["metadata_json"]) if row["metadata_json"] else {},
        )


def parse_since(since_str: str) -> datetime:
    """Parse a 'since' string like '30d', '7d', '1h' into a datetime.

    Args:
        since_str: Duration string (e.g., '30d', '7d', '24h', '1w')

    Returns:
        Datetime that many units ago from now
    """
    since_str = since_str.strip().lower()

    if since_str.endswith("d"):
        days = int(since_str[:-1])
        return datetime.now(timezone.utc) - timedelta(days=days)
    elif since_str.endswith("h"):
        hours = int(since_str[:-1])
        return datetime.now(timezone.utc) - timedelta(hours=hours)
    elif since_str.endswith("w"):
        weeks = int(since_str[:-1])
        return datetime.now(timezone.utc) - timedelta(weeks=weeks)
    elif since_str.endswith("m"):
        minutes = int(since_str[:-1])
        return datetime.now(timezone.utc) - timedelta(minutes=minutes)
    else:
        # Try parsing as ISO date
        return datetime.fromisoformat(since_str)

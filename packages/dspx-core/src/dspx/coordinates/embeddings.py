"""Embedding engine for semantic coordinates.

Converts execution data (inputs, outputs, config) into dense vector representations
that capture semantic meaning for similarity search and behavioral analysis.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

# Optional embedding backends
_EMBEDDING_BACKEND: Literal["none", "mock", "sentence-transformers"] | None = None


def _detect_embedding_backend() -> Literal["none", "mock", "sentence-transformers"]:
    """Detect available embedding backend.

    Precedence:
    1. DSPX_ORACLE_EMBEDDING_BACKEND env var (none, mock, sentence-transformers)
    2. sentence-transformers if installed
    3. mock (deterministic hash-based vectors for testing)
    """
    global _EMBEDDING_BACKEND
    if _EMBEDDING_BACKEND is not None:
        return _EMBEDDING_BACKEND

    env_backend = os.getenv("DSPX_ORACLE_EMBEDDING_BACKEND", "").lower().strip()
    if env_backend == "none":
        _EMBEDDING_BACKEND = "none"
    elif env_backend == "mock":
        _EMBEDDING_BACKEND = "mock"
    elif env_backend == "sentence-transformers":
        _EMBEDDING_BACKEND = "sentence-transformers"
    else:
        try:
            import sentence_transformers  # type: ignore[import-untyped]  # noqa: F401

            _EMBEDDING_BACKEND = "sentence-transformers"
        except ImportError:
            _EMBEDDING_BACKEND = "mock"

    return _EMBEDDING_BACKEND


@runtime_checkable
class EmbedderProtocol(Protocol):
    """Protocol for embedding backends."""

    def encode(self, texts: list[str]) -> list[list[float]]:
        """Encode texts into vectors."""
        ...

    def get_dimension(self) -> int:
        """Return embedding dimension."""
        ...


@dataclass(frozen=True)
class ExecutionEmbedding:
    """Embedded representation of a DSPx execution.

    Captures the semantic content of inputs, outputs, and configuration
    as a unified vector for similarity search and behavioral analysis.
    """

    run_id: str
    vector: list[float]
    input_text: str
    output_text: str
    config_text: str
    run_kind: str
    provider: str
    template_version: str | None
    created_at: str
    dimension: int
    source_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for storage."""
        return {
            "run_id": self.run_id,
            "vector": self.vector,
            "input_text": self.input_text,
            "output_text": self.output_text,
            "config_text": self.config_text,
            "run_kind": self.run_kind,
            "provider": self.provider,
            "template_version": self.template_version,
            "created_at": self.created_at,
            "dimension": self.dimension,
            "source_path": self.source_path,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutionEmbedding":
        """Deserialize from dictionary."""
        return cls(
            run_id=data["run_id"],
            vector=data["vector"],
            input_text=data["input_text"],
            output_text=data["output_text"],
            config_text=data["config_text"],
            run_kind=data["run_kind"],
            provider=data["provider"],
            template_version=data.get("template_version"),
            created_at=data["created_at"],
            dimension=data["dimension"],
            source_path=data.get("source_path"),
            metadata=data.get("metadata", {}),
        )


class MockEmbedder:
    """Deterministic mock embedder for testing.

    Uses SHA256 hashing to generate reproducible vectors without ML models.
    Useful for CI, testing, and environments without sentence-transformers.
    """

    def __init__(self, dimension: int = 384):
        self._dimension = dimension

    def encode(self, texts: list[str]) -> list[list[float]]:
        """Encode texts using deterministic hash-based vectors."""
        vectors = []
        for text in texts:
            # Create deterministic vector from hash
            h = hashlib.sha256(text.encode("utf-8")).digest()
            # Expand to dimension using repeated hash
            seed = h
            vector = []
            for i in range(self._dimension):
                byte_idx = i % 32
                val = float(seed[byte_idx]) / 255.0
                # Add variation based on position
                val = val * 2.0 - 1.0  # Range [-1, 1]
                if i >= 32:
                    # Mix in position-dependent variation
                    val = val * (1.0 + 0.1 * (i / self._dimension))
                vector.append(val)
            # Normalize to unit length
            norm = sum(v * v for v in vector) ** 0.5
            if norm > 0:
                vector = [v / norm for v in vector]
            vectors.append(vector)
        return vectors

    def get_dimension(self) -> int:
        return self._dimension


class SentenceTransformerEmbedder:
    """Real embedder using sentence-transformers."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]

        self._model = SentenceTransformer(model_name)
        self._dimension = self._model.get_sentence_embedding_dimension()

    def encode(self, texts: list[str]) -> list[list[float]]:
        """Encode texts using sentence-transformers."""
        embeddings = self._model.encode(texts, convert_to_numpy=True)
        return [emb.tolist() for emb in embeddings]

    def get_dimension(self) -> int:
        return self._dimension


class EmbeddingEngine:
    """Main embedding engine for DSPx executions.

    Provides a unified interface for embedding execution data regardless
    of the underlying model. Supports multiple backends and graceful fallback.
    """

    def __init__(
        self,
        backend: Literal["auto", "none", "mock", "sentence-transformers"] = "auto",
        model_name: str = "all-MiniLM-L6-v2",
        mock_dimension: int = 384,
    ):
        if backend == "auto":
            backend = _detect_embedding_backend()

        self._backend_name = backend

        if backend == "sentence-transformers":
            self._embedder: EmbedderProtocol = SentenceTransformerEmbedder(model_name)
        elif backend == "mock":
            self._embedder = MockEmbedder(dimension=mock_dimension)
        else:
            self._embedder = MockEmbedder(dimension=mock_dimension)

        self._dimension = self._embedder.get_dimension()

    @property
    def backend(self) -> str:
        """Return the active backend name."""
        return self._backend_name

    @property
    def dimension(self) -> int:
        """Return embedding dimension."""
        return self._dimension

    def embed_text(self, text: str) -> list[float]:
        """Embed a single text string."""
        return self._embedder.encode([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple text strings."""
        return self._embedder.encode(texts)

    def embed_execution(
        self,
        run_id: str,
        input_text: str,
        output_text: str,
        config_text: str = "",
        *,
        run_kind: str = "unknown",
        provider: str = "unknown",
        template_version: str | None = None,
        source_path: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExecutionEmbedding:
        """Embed a complete execution record.

        Combines input, output, and config into a unified semantic representation.
        """
        # Create combined text for embedding
        # Weight: input (most important), output, config
        combined = f"[INPUT]\n{input_text}\n\n[OUTPUT]\n{output_text}"
        if config_text:
            combined += f"\n\n[CONFIG]\n{config_text}"

        vector = self.embed_text(combined)

        return ExecutionEmbedding(
            run_id=run_id,
            vector=vector,
            input_text=input_text,
            output_text=output_text,
            config_text=config_text,
            run_kind=run_kind,
            provider=provider,
            template_version=template_version,
            created_at=datetime.now(timezone.utc).isoformat(),
            dimension=self._dimension,
            source_path=source_path,
            metadata=metadata or {},
        )

    def embed_receipt(
        self, receipt: dict[str, Any], output_content: str | None = None
    ) -> ExecutionEmbedding | None:
        """Embed from a run receipt dictionary.

        Args:
            receipt: Run receipt dict from .meta.json file
            output_content: Optional output file content (read from receipt path if not provided)

        Returns:
            ExecutionEmbedding or None if receipt lacks required fields
        """
        run_id = receipt.get("hash") or receipt.get("cache_key")
        if not run_id:
            return None

        # Extract replay inputs
        replay_inputs = receipt.get("replay_inputs", {})
        input_text = self._extract_input_text(replay_inputs)

        # Get output text
        if output_content is None:
            output_content = self._read_output_from_receipt(receipt)
        output_text = output_content or ""

        # Build config text
        config_parts = []
        if receipt.get("template_version"):
            config_parts.append(f"template_version: {receipt['template_version']}")
        if receipt.get("provider"):
            config_parts.append(f"provider: {receipt['provider']}")
        if receipt.get("run_kind"):
            config_parts.append(f"run_kind: {receipt['run_kind']}")
        config_text = "\n".join(config_parts)

        source_path = receipt.get("output_path")

        return self.embed_execution(
            run_id=run_id,
            input_text=input_text,
            output_text=output_text,
            config_text=config_text,
            run_kind=receipt.get("run_kind", "unknown"),
            provider=receipt.get("provider", "unknown"),
            template_version=receipt.get("template_version"),
            source_path=source_path,
            metadata={
                "cache_key": receipt.get("cache_key"),
                "cache_enabled": receipt.get("cache_enabled"),
            },
        )

    def _extract_input_text(self, replay_inputs: dict[str, Any]) -> str:
        """Extract meaningful input text from replay inputs."""
        parts = []

        # Common fields
        if "prompt" in replay_inputs:
            parts.append(str(replay_inputs["prompt"]))
        if "spec" in replay_inputs:
            parts.append(str(replay_inputs["spec"]))
        if "name" in replay_inputs:
            parts.append(f"name: {replay_inputs['name']}")
        if "description" in replay_inputs:
            parts.append(f"description: {replay_inputs['description']}")
        if "inputs" in replay_inputs:
            parts.append(f"inputs: {replay_inputs['inputs']}")
        if "outputs" in replay_inputs:
            parts.append(f"outputs: {replay_inputs['outputs']}")

        return "\n".join(parts) if parts else json.dumps(replay_inputs, sort_keys=True)

    def _read_output_from_receipt(self, receipt: dict[str, Any]) -> str | None:
        """Try to read output content from receipt path."""
        output_path = receipt.get("output_path")
        if not output_path:
            return None

        try:
            path = Path(output_path)
            if path.exists() and path.is_file():
                # Limit read size
                content = path.read_text(encoding="utf-8", errors="replace")
                return content[:10000]  # Truncate for embedding
        except Exception:
            pass
        return None


# Global engine instance
_ENGINE: EmbeddingEngine | None = None


def get_embedding_engine(
    backend: Literal["auto", "none", "mock", "sentence-transformers"] = "auto",
    model_name: str = "all-MiniLM-L6-v2",
    force_new: bool = False,
) -> EmbeddingEngine:
    """Get or create the global embedding engine.

    Args:
        backend: Embedding backend to use
        model_name: Model name for sentence-transformers
        force_new: Force creation of new engine (ignore cached)

    Returns:
        EmbeddingEngine instance
    """
    global _ENGINE
    if _ENGINE is None or force_new:
        _ENGINE = EmbeddingEngine(backend=backend, model_name=model_name)
    return _ENGINE

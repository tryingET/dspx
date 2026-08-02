# summary: "Builds validated semantic embeddings from text, executions, and replay receipts."
# read_when:
#   - "Changing embedding backends, execution vectors, receipt extraction, validation, or engine caching."

"""Embedding engine for semantic coordinates.

Converts execution data (inputs, outputs, config) into dense vector representations
that capture semantic meaning for similarity search and behavioral analysis.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib import import_module
from importlib.util import find_spec
from pathlib import Path
from typing import Any, cast, Literal, Mapping, Protocol, runtime_checkable

from dspx.run_receipts import resolve_run_identity

from .embedding_identity import (
    SentenceTransformerIdentitySpec,
    build_sentence_transformer_identity,
    validate_unit_vector,
)
from .mdenseon import (
    MDENSEON_ADAPTER,
    MDENSEON_DIMENSION,
    MDENSEON_DOCUMENT_PROMPT,
    MDENSEON_MAX_TOKENS,
    MDENSEON_QUERY_PROMPT,
    MDENSEON_REPOSITORY_ID,
    MDENSEON_REVISION,
    MDenseOnEmbedder,
)

logger = logging.getLogger(__name__)

# Embedding schema version - bump when changing embedding behavior
EMBEDDING_VERSION = 2

EmbeddingBackendName = Literal[
    "none", "mock", "sentence-transformers", "transformers-dense"
]
EmbeddingBackendRequest = Literal[
    "auto", "none", "mock", "sentence-transformers", "transformers-dense"
]
EMBEDDING_BACKEND_IDENTITY_SCHEMA = "dspx-embedding-backend-identity-v2"
_EMBEDDING_BACKEND_ENV = "DSPX_ORACLE_EMBEDDING_BACKEND"
_VALID_EMBEDDING_BACKENDS = {
    "none",
    "mock",
    "sentence-transformers",
    "transformers-dense",
}

_LEGACY_SENTENCE_TRANSFORMER_MODEL = "all-MiniLM-L6-v2"
_LEGACY_SENTENCE_TRANSFORMER_DIMENSION = 384


class EmbeddingBackendConfigurationError(RuntimeError):
    """Raised when no truthful embedding backend can be selected."""


@dataclass(frozen=True)
class EmbeddingBackendSelection:
    """Read-only resolution of the requested and effective embedding backend."""

    requested_backend: str
    effective_backend: EmbeddingBackendName
    selection_source: str
    explicitly_selected: bool
    available: bool
    reason: str

    @property
    def semantic_class(self) -> str:
        if self.effective_backend == "mock":
            return "deterministic_test_double"
        if self.effective_backend in {
            "sentence-transformers",
            "transformers-dense",
        }:
            return "model_backed_semantic_embedding"
        return "disabled"

    @property
    def semantic_claim(self) -> str:
        if self.effective_backend == "mock":
            return "plumbing_only_not_production_semantics"
        if self.effective_backend == "transformers-dense":
            return (
                "oracle_selected_model_backed_semantics_requires_exact_runtime_identity"
            )
        if self.effective_backend == "sentence-transformers":
            return "legacy_model_backed_semantics_not_current_default"
        return "no_embedding_backend_available"

    def to_dict(
        self,
        *,
        model_name: str | None = None,
        dimension: int | None = None,
    ) -> dict[str, Any]:
        adapter: dict[str, Any] | None = None
        if self.effective_backend == "mock":
            resolved_model = "sha256-deterministic-test-double-v1"
        elif self.effective_backend == "transformers-dense":
            resolved_model = model_name or MDENSEON_REPOSITORY_ID
            dimension = dimension or MDENSEON_DIMENSION
            adapter = {
                "name": MDENSEON_ADAPTER,
                "revision": MDENSEON_REVISION,
                "document_prompt": MDENSEON_DOCUMENT_PROMPT,
                "query_prompt": MDENSEON_QUERY_PROMPT,
                "pooling": "last_hidden_state_cls_token",
                "normalization": "l2",
                "similarity": "cosine",
                "maximum_tokens": MDENSEON_MAX_TOKENS,
            }
        elif self.effective_backend == "sentence-transformers":
            resolved_model = model_name or _LEGACY_SENTENCE_TRANSFORMER_MODEL
            dimension = dimension or _LEGACY_SENTENCE_TRANSFORMER_DIMENSION
        else:
            resolved_model = None
        return {
            "schema_version": EMBEDDING_BACKEND_IDENTITY_SCHEMA,
            "requested_backend": self.requested_backend,
            "effective_backend": self.effective_backend,
            "selection_source": self.selection_source,
            "explicitly_selected": self.explicitly_selected,
            "available": self.available,
            "reason": self.reason,
            "model": resolved_model,
            "dimension": dimension,
            "adapter": adapter,
            "semantic_class": self.semantic_class,
            "semantic_claim": self.semantic_claim,
            "production_semantic_claim_allowed": False,
        }


_ENGINE_LOCK = threading.Lock()


def resolve_embedding_backend(
    backend: EmbeddingBackendRequest = "auto",
    *,
    environ: Mapping[str, str] | None = None,
) -> EmbeddingBackendSelection:
    """Resolve backend identity without importing a model or creating state.

    Mock vectors are never an implicit fallback. They remain available for tests and
    plumbing proofs only when selected explicitly. ``none`` truthfully disables
    embedding rather than executing a mock backend under a false identity.
    """

    env = os.environ if environ is None else environ
    if backend != "auto":
        if backend not in _VALID_EMBEDDING_BACKENDS:
            raise EmbeddingBackendConfigurationError(
                f"Unsupported Oracle embedding backend {backend!r}; expected "
                "none, mock, sentence-transformers, or transformers-dense"
            )
        selected = backend
        source = "explicit_argument"
        explicitly_selected = True
    else:
        configured = str(env.get(_EMBEDDING_BACKEND_ENV, "")).strip().lower()
        if configured and configured not in _VALID_EMBEDDING_BACKENDS:
            raise EmbeddingBackendConfigurationError(
                f"Invalid {_EMBEDDING_BACKEND_ENV}={configured!r}; expected "
                "none, mock, sentence-transformers, or transformers-dense"
            )
        if configured:
            selected = configured
            source = _EMBEDDING_BACKEND_ENV
            explicitly_selected = True
        elif all(
            find_spec(module) is not None
            for module in ("transformers", "torch", "huggingface_hub")
        ):
            selected = "transformers-dense"
            source = "automatic_dependency_detection"
            explicitly_selected = False
        elif find_spec("sentence_transformers") is not None:
            selected = "sentence-transformers"
            source = "legacy_dependency_detection"
            explicitly_selected = False
        else:
            selected = "none"
            source = "automatic_no_model_backend"
            explicitly_selected = False

    effective_backend = cast(EmbeddingBackendName, selected)
    if effective_backend == "none":
        reason = (
            "embedding backend explicitly disabled"
            if explicitly_selected
            else "no model-backed embedding dependency detected; mock requires explicit selection"
        )
        available = False
    elif effective_backend == "mock":
        reason = "explicit deterministic test-double selection"
        available = True
    elif effective_backend == "transformers-dense":
        available = all(
            find_spec(module) is not None
            for module in ("transformers", "torch", "huggingface_hub")
        )
        reason = (
            "selected mDenseOn runtime dependencies detected"
            if available
            else "transformers-dense selected but a required dependency is unavailable"
        )
    else:
        available = find_spec("sentence_transformers") is not None
        reason = (
            "legacy sentence-transformers dependency detected"
            if available
            else "sentence-transformers selected but dependency is unavailable"
        )

    selection = EmbeddingBackendSelection(
        requested_backend=(
            str(env.get(_EMBEDDING_BACKEND_ENV, "")).strip().lower() or "auto"
            if backend == "auto"
            else backend
        ),
        effective_backend=effective_backend,
        selection_source=source,
        explicitly_selected=explicitly_selected,
        available=available,
        reason=reason,
    )
    return selection


@runtime_checkable
class EmbedderProtocol(Protocol):
    """Protocol for embedding backends."""

    def encode(self, texts: list[str]) -> list[list[float]]:
        """Encode texts into vectors."""
        ...

    def get_dimension(self) -> int:
        """Return embedding dimension."""
        ...


class EmbeddingValidationError(ValueError):
    """Raised when embedding validation fails."""

    pass


def _canonical_execution_time(value: object | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat()
    if not isinstance(value, str) or not value.strip():
        raise EmbeddingValidationError("created_at must be a non-empty ISO-8601 string")
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EmbeddingValidationError("created_at must be valid ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EmbeddingValidationError("created_at must include an explicit timezone")
    return parsed.astimezone(timezone.utc).isoformat()


class EmbeddingResult:
    """Result type for embedding operations that may fail.

    Provides more information than None on failure.
    """

    def __init__(
        self,
        embedding: "ExecutionEmbedding | None" = None,
        error: str | None = None,
        skipped: bool = False,
        skip_reason: str | None = None,
    ):
        self._embedding = embedding
        self._error = error
        self._skipped = skipped
        self._skip_reason = skip_reason

    @property
    def ok(self) -> bool:
        """True if embedding was created successfully."""
        return self._embedding is not None

    @property
    def embedding(self) -> "ExecutionEmbedding | None":
        """The embedding, or None if failed/skipped."""
        return self._embedding

    @property
    def error(self) -> str | None:
        """Error message if failed."""
        return self._error

    @property
    def skipped(self) -> bool:
        """True if item was skipped (not an error)."""
        return self._skipped

    @property
    def skip_reason(self) -> str | None:
        """Reason for skipping."""
        return self._skip_reason

    @classmethod
    def success(cls, embedding: "ExecutionEmbedding") -> "EmbeddingResult":
        return cls(embedding=embedding)

    @classmethod
    def failure(cls, error: str) -> "EmbeddingResult":
        return cls(error=error)

    @classmethod
    def skip(cls, reason: str) -> "EmbeddingResult":
        return cls(skipped=True, skip_reason=reason)


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
    embedding_version: int = EMBEDDING_VERSION

    def __post_init__(self) -> None:
        """Validate invariants after initialization."""
        # BUG 5 FIX: Validate dimension matches vector length
        if len(self.vector) != self.dimension:
            raise EmbeddingValidationError(
                f"Dimension mismatch: vector has {len(self.vector)} elements "
                f"but dimension field is {self.dimension}"
            )

        # Validate vector is not empty
        if not self.vector:
            raise EmbeddingValidationError("Vector cannot be empty")

        # Validate run_id is not empty
        if not self.run_id:
            raise EmbeddingValidationError("run_id cannot be empty")

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
            "embedding_version": self.embedding_version,
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
            embedding_version=data.get("embedding_version", 1),
        )


def _expand_hash_seed(seed: bytes, length: int) -> list[int]:
    """Expand a 32-byte hash seed into arbitrary length using SHAKE-like expansion.

    BUG 1 FIX: Use proper hash expansion instead of byte recycling.
    """
    result = []
    counter = 0
    while len(result) < length:
        # Hash the seed with counter to generate more bytes
        h = hashlib.sha256(seed + counter.to_bytes(4, "big"))
        result.extend(h.digest())
        counter += 1
    return result[:length]


class MockEmbedder:
    """Deterministic mock embedder for testing.

    Uses SHA256 hashing to generate reproducible vectors without ML models.
    Useful for CI, testing, and environments without sentence-transformers.
    """

    def __init__(self, dimension: int = 384):
        if (
            isinstance(dimension, bool)
            or not isinstance(dimension, int)
            or dimension <= 0
        ):
            raise EmbeddingValidationError(
                "mock embedding dimension must be a positive integer"
            )
        self._dimension = dimension

    def encode(self, texts: list[str]) -> list[list[float]]:
        """Encode texts using deterministic hash-based vectors.

        BUG 1 FIX: Use proper hash expansion for consistent magnitude distribution.
        """
        vectors = []
        for text in texts:
            # Create deterministic vector from hash
            seed = hashlib.sha256(text.encode("utf-8")).digest()
            # Expand seed to full dimension using proper expansion
            expanded = _expand_hash_seed(seed, self._dimension)

            # Convert bytes to floats in [-1, 1] range uniformly
            vector = []
            for byte_val in expanded:
                val = (byte_val / 255.0) * 2.0 - 1.0  # Map [0,255] to [-1,1]
                vector.append(val)

            # Normalize to unit length
            norm = sum(v * v for v in vector) ** 0.5
            if norm > 0:
                vector = [v / norm for v in vector]
            else:
                # Edge case: all zeros (shouldn't happen with proper hash)
                vector = [1.0 / (self._dimension**0.5)] * self._dimension

            vectors.append(vector)
        return vectors

    def get_dimension(self) -> int:
        return self._dimension


class SentenceTransformerEmbedder:
    """Real embedder with optional retained-artifact and normalization controls."""

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        *,
        model_root: Path | None = None,
        normalize_embeddings: bool = False,
        device: str | None = None,
    ):
        sentence_transformers = import_module("sentence_transformers")
        sentence_transformer_cls = getattr(sentence_transformers, "SentenceTransformer")

        self._model_name = model_name
        self._model_root = model_root
        self._normalize_embeddings = normalize_embeddings
        self._device = device
        self._observed_vector_dtype: str | None = None
        source = str(model_root) if model_root is not None else model_name
        kwargs: dict[str, Any] = {"trust_remote_code": False}
        if device is not None:
            kwargs["device"] = device
        if model_root is not None:
            kwargs["local_files_only"] = True
        self._model = sentence_transformer_cls(source, **kwargs)
        self._observed_device = str(getattr(self._model, "device", ""))
        self._dimension = self._model.get_sentence_embedding_dimension()
        if isinstance(self._dimension, bool) or not isinstance(self._dimension, int):
            raise EmbeddingValidationError(
                "sentence-transformer dimension must be an integer"
            )

    def encode(self, texts: list[str]) -> list[list[float]]:
        """Encode text under the configured normalization contract."""
        embeddings = self._model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=self._normalize_embeddings,
        )
        observed_dtype = str(getattr(embeddings, "dtype", ""))
        observed_shape = getattr(embeddings, "shape", None)
        if observed_dtype != "float32" or observed_shape != (
            len(texts),
            self._dimension,
        ):
            raise EmbeddingValidationError(
                "sentence-transformer output must be a float32 matrix with exact batch shape"
            )
        self._observed_vector_dtype = observed_dtype
        vectors = [emb.tolist() for emb in embeddings]
        if self._normalize_embeddings:
            for vector in vectors:
                validate_unit_vector(vector)
        return vectors

    def get_dimension(self) -> int:
        return self._dimension

    def build_identity(
        self,
        spec: SentenceTransformerIdentitySpec,
        *,
        runtime_versions: Mapping[str, str] | None = None,
        frozen_runtime_lock_sha256: str,
    ) -> dict[str, Any]:
        """Build complete identity only for a retained local model snapshot."""

        if self._model_root is None:
            raise EmbeddingValidationError(
                "complete sentence-transformer identity requires a retained model root"
            )
        if self._normalize_embeddings is not spec.normalize_embeddings:
            raise EmbeddingValidationError(
                "embedding normalization configuration drift"
            )
        if self._device != spec.device:
            raise EmbeddingValidationError("embedding device configuration drift")
        if self._observed_device != spec.device:
            raise EmbeddingValidationError("observed model device drift")
        if self._observed_vector_dtype is None:
            raise EmbeddingValidationError(
                "complete identity requires one observed full-batch encoding"
            )
        tokenizer = getattr(self._model, "tokenizer", None)
        if tokenizer is None:
            raise EmbeddingValidationError(
                "sentence-transformer tokenizer is unavailable"
            )
        torch = import_module("torch")
        runtime_observations = {
            "model_device": self._observed_device,
            "torch_cuda_available": bool(torch.cuda.is_available()),
            "torch_default_dtype": str(torch.get_default_dtype()),
            "numpy_output_dtype": self._observed_vector_dtype,
        }
        return build_sentence_transformer_identity(
            spec=spec,
            model_root=self._model_root,
            tokenizer=tokenizer,
            dimension=self._dimension,
            observed_vector_dtype=self._observed_vector_dtype,
            frozen_runtime_lock_sha256=frozen_runtime_lock_sha256,
            runtime_observations=runtime_observations,
            runtime_versions=runtime_versions,
        )


class EmbeddingEngine:
    """Main embedding engine for DSPx executions.

    Provides a unified interface for embedding execution data regardless
    of the underlying model. Supports multiple backends and graceful fallback.
    """

    def __init__(
        self,
        backend: EmbeddingBackendRequest = "auto",
        model_name: str | None = None,
        mock_dimension: int = 384,
        *,
        _selection: EmbeddingBackendSelection | None = None,
    ):
        selection = _selection or resolve_embedding_backend(backend)
        if not selection.available:
            raise EmbeddingBackendConfigurationError(
                f"Oracle embedding backend unavailable: {selection.reason}. "
                f"Set {_EMBEDDING_BACKEND_ENV}=mock only for explicit test/plumbing use, "
                "or install the oracle-embeddings dependencies and select a model backend."
            )

        self._selection = selection
        self._backend_name = selection.effective_backend
        self._mock_dimension = mock_dimension

        if self._backend_name == "transformers-dense":
            resolved_model = model_name or MDENSEON_REPOSITORY_ID
            if resolved_model != MDENSEON_REPOSITORY_ID:
                raise EmbeddingBackendConfigurationError(
                    "transformers-dense currently supports only the frozen lightonai/mDenseOn adapter"
                )
            self._embedder: EmbedderProtocol | MDenseOnEmbedder = MDenseOnEmbedder(
                resolved_model
            )
        elif self._backend_name == "sentence-transformers":
            resolved_model = model_name or _LEGACY_SENTENCE_TRANSFORMER_MODEL
            self._embedder = SentenceTransformerEmbedder(resolved_model)
        elif self._backend_name == "mock":
            resolved_model = "sha256-deterministic-test-double-v1"
            self._embedder = MockEmbedder(dimension=mock_dimension)
        else:  # guarded by selection.available; retained as a fail-closed invariant
            raise EmbeddingBackendConfigurationError(
                f"Oracle embedding backend {self._backend_name!r} cannot encode vectors"
            )

        self._model_name = resolved_model
        self._dimension = self._embedder.get_dimension()

    @property
    def backend(self) -> str:
        """Return the active backend name."""
        return self._backend_name

    @property
    def dimension(self) -> int:
        """Return embedding dimension."""
        return self._dimension

    @property
    def model_name(self) -> str:
        """Return the selected model or deterministic test-double identity."""
        return self._model_name

    @property
    def backend_identity(self) -> dict[str, Any]:
        """Return the persisted claim boundary for vectors created by this engine."""

        return self._selection.to_dict(
            model_name=self._model_name,
            dimension=self._dimension,
        )

    def embed_document(self, text: str) -> list[float]:
        """Embed one stored document under the backend's document role."""
        return self.embed_documents([text])[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed stored documents under the backend's document role."""
        if self._backend_name == "transformers-dense":
            return cast(MDenseOnEmbedder, self._embedder).encode_documents(texts)
        return cast(EmbedderProtocol, self._embedder).encode(texts)

    def embed_query(self, text: str) -> list[float]:
        """Embed one retrieval request under the backend's query role."""
        if self._backend_name == "transformers-dense":
            return cast(MDenseOnEmbedder, self._embedder).encode_queries([text])[0]
        return cast(EmbedderProtocol, self._embedder).encode([text])[0]

    def embed_text(self, text: str) -> list[float]:
        """Backward-compatible alias for document-role encoding."""
        return self.embed_document(text)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Backward-compatible alias for document-role batch encoding."""
        return self.embed_documents(texts)

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
        created_at: str | None = None,
    ) -> ExecutionEmbedding:
        """Embed a complete execution record.

        Combines input, output, and config into a unified semantic representation.
        """
        # Create combined text for embedding
        # Weight: input (most important), output, config
        combined = f"[INPUT]\n{input_text}\n\n[OUTPUT]\n{output_text}"
        if config_text:
            combined += f"\n\n[CONFIG]\n{config_text}"

        vector = self.embed_document(combined)

        return ExecutionEmbedding(
            run_id=run_id,
            vector=vector,
            input_text=input_text,
            output_text=output_text,
            config_text=config_text,
            run_kind=run_kind,
            provider=provider,
            template_version=template_version,
            created_at=_canonical_execution_time(created_at),
            dimension=self._dimension,
            source_path=source_path,
            metadata={
                **(metadata or {}),
                # Reserved producer identity wins over caller-supplied metadata.
                "embedding_backend": self.backend_identity,
            },
            embedding_version=EMBEDDING_VERSION,
        )

    def embed_receipt(
        self,
        receipt: dict[str, Any],
        output_content: str | None = None,
        *,
        receipt_path: Path | None = None,
        allow_unconfined_output_path: bool = False,
    ) -> ExecutionEmbedding | None:
        """Embed from a run receipt dictionary.

        Args:
            receipt: Run receipt dict from .meta.json file
            output_content: Optional output file content (read from receipt path if not provided)

        Returns:
            ExecutionEmbedding or None if receipt lacks required fields

        Note:
            For more detailed error information, use embed_receipt_result().
        """
        result = self.embed_receipt_result(
            receipt,
            output_content,
            receipt_path=receipt_path,
            allow_unconfined_output_path=allow_unconfined_output_path,
        )
        return result.embedding

    def embed_receipt_result(
        self,
        receipt: dict[str, Any],
        output_content: str | None = None,
        *,
        receipt_path: Path | None = None,
        allow_unconfined_output_path: bool = False,
    ) -> EmbeddingResult:
        """Embed from a run receipt dictionary with detailed result.

        BUG 6 FIX: Return result type with error/skip information.

        Args:
            receipt: Run receipt dict from .meta.json file
            output_content: Optional output file content

        Returns:
            EmbeddingResult with success/failure/skip information
        """
        identity = resolve_run_identity(receipt, meta_path=receipt_path)
        run_id = identity.storage_id
        if not run_id:
            return EmbeddingResult.skip(
                "Receipt has no storage identifier (execution_id, run_id, cache_key, hash, output_path, or receipt path)"
            )

        # Extract replay inputs
        replay_inputs = receipt.get("replay_inputs", {})
        input_text = self._extract_input_text(replay_inputs)

        # Get output text
        if output_content is None:
            output_content = self._read_output_from_receipt(
                receipt,
                receipt_path=receipt_path,
                allow_unconfined_output_path=allow_unconfined_output_path,
            )
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

        try:
            embedding = self.embed_execution(
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
                    "receipt_identity": identity.to_dict(),
                },
                created_at=receipt.get("created_at"),
            )
            return EmbeddingResult.success(embedding)
        except EmbeddingValidationError as e:
            return EmbeddingResult.failure(f"Validation error: {e}")
        except Exception as e:
            return EmbeddingResult.failure(f"Unexpected error: {e}")

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

    def _read_output_from_receipt(
        self,
        receipt: dict[str, Any],
        *,
        receipt_path: Path | None = None,
        allow_unconfined_output_path: bool = False,
    ) -> str | None:
        """Try to read output content from a receipt-confined path."""
        output_path = receipt.get("output_path")
        if not output_path:
            return None

        try:
            raw_path = Path(str(output_path)).expanduser()
            if receipt_path is not None:
                from dspx.security import confine_path

                root = receipt_path.expanduser().resolve().parent
                path = confine_path(root, raw_path)
            elif raw_path.is_absolute():
                if not allow_unconfined_output_path:
                    logger.debug(
                        "Skipping unconfined receipt output read without receipt root: %s",
                        output_path,
                    )
                    return None
                path = raw_path
            else:
                path = raw_path
            if path.exists() and path.is_file():
                # Limit read size
                content = path.read_text(encoding="utf-8", errors="replace")
                return content[:10000]  # Truncate for embedding
        except PermissionError as e:
            logger.debug(f"Permission denied reading {output_path}: {e}")
        except OSError as e:
            logger.debug(f"OS error reading {output_path}: {e}")
        except Exception as e:
            logger.debug(f"Unexpected error reading {output_path}: {e}")
        return None


# Global engine instance and its configuration
_ENGINE: EmbeddingEngine | None = None
_ENGINE_CONFIG: tuple[str, str, str, bool, str | None, int] | None = None


def get_embedding_engine(
    backend: EmbeddingBackendRequest = "auto",
    model_name: str | None = None,
    mock_dimension: int = 384,
    force_new: bool = False,
) -> EmbeddingEngine:
    """Get or create the global embedding engine.

    BUG 2 FIX: Respect parameter changes.
    BUG 4 FIX: Thread-safe singleton.

    Args:
        backend: Embedding backend to use
        model_name: Explicit backend model name; defaults by selected backend
        mock_dimension: Dimension for mock embedder
        force_new: Force creation of new engine (ignore cached)

    Returns:
        EmbeddingEngine instance
    """
    global _ENGINE, _ENGINE_CONFIG

    with _ENGINE_LOCK:
        selection = resolve_embedding_backend(backend)

        # Check if we need to create a new engine
        config = (
            selection.requested_backend,
            selection.effective_backend,
            selection.selection_source,
            selection.explicitly_selected,
            model_name,
            mock_dimension,
        )
        needs_new = (
            force_new
            or _ENGINE is None
            or _ENGINE_CONFIG != config
            or _ENGINE.backend != selection.effective_backend
        )

        if needs_new:
            _ENGINE = EmbeddingEngine(
                backend=backend,
                model_name=model_name,
                mock_dimension=mock_dimension,
                _selection=selection,
            )
            _ENGINE_CONFIG = config

        # Type assertion: _ENGINE is guaranteed to be non-None here
        assert _ENGINE is not None
        return _ENGINE


def reset_embedding_engine() -> None:
    """Reset the global embedding engine (mainly for testing)."""
    global _ENGINE, _ENGINE_CONFIG
    with _ENGINE_LOCK:
        _ENGINE = None
        _ENGINE_CONFIG = None

# summary: "Implements the prompt-aware, single-vector mDenseOn adapter and identity boundary."
# read_when:
#   - "Changing the selected Oracle dense model, query/document prompts, CLS pooling, or mDenseOn identity."

"""Local mDenseOn adapter with explicit asymmetric retrieval semantics."""

from __future__ import annotations

import json
import stat
from importlib import import_module
from pathlib import Path
from typing import Any, Literal, Mapping, cast

from .embedding_identity import (
    SentenceTransformerIdentitySpec,
    build_sentence_transformer_identity,
    validate_unit_vector,
)

MDENSEON_REPOSITORY_ID = "lightonai/mDenseOn"
MDENSEON_REVISION = "a5fdb000f7a21da96c3bddde3a782ef777316df3"
MDENSEON_DIMENSION = 768
MDENSEON_MAX_TOKENS = 8192
MDENSEON_DOCUMENT_PROMPT = "document: "
MDENSEON_QUERY_PROMPT = "query: "
MDENSEON_ADAPTER = "dspx-mdenseon-cls-v1"
MDENSEON_IDENTITY_SCHEMA = "dspx-mdenseon-identity-v1"
MDENSEON_ARTIFACT_PATHS = (
    "1_Pooling/config.json",
    "config.json",
    "config_sentence_transformers.json",
    "model.safetensors",
    "modules.json",
    "sentence_bert_config.json",
    "tokenizer.json",
    "tokenizer_config.json",
)

EmbeddingRole = Literal["document", "query"]


class MDenseOnError(ValueError):
    """Raised when mDenseOn cannot preserve its frozen encoding contract."""


def modernbert_model_inputs(encoded: Mapping[str, Any]) -> dict[str, Any]:
    """Remove only the segment IDs unsupported by ModernBERT's forward API."""

    resolved = dict(encoded)
    resolved.pop("token_type_ids", None)
    if set(resolved) != set(encoded) - {"token_type_ids"}:
        raise MDenseOnError("mDenseOn model-input filtering changed an unexpected key")
    return resolved


def _read_model_json(root: Path, relative: str) -> object:
    path = root / relative
    try:
        before = path.lstat()
    except OSError as exc:
        raise MDenseOnError(f"mDenseOn metadata is unavailable: {relative}") from exc
    if (
        path.is_symlink()
        or not stat.S_ISREG(before.st_mode)
        or root.resolve() not in path.resolve().parents
        or before.st_size > 16_384
    ):
        raise MDenseOnError(f"mDenseOn metadata path is invalid: {relative}")
    try:
        return json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise MDenseOnError(f"mDenseOn metadata is invalid: {relative}") from exc


def validate_serialized_mdenseon_semantics(model_root: Path) -> None:
    """Prove the retained serialization declares the adapter's exact semantics."""

    root = model_root.resolve()
    if not root.is_dir() or model_root.is_symlink():
        raise MDenseOnError("mDenseOn model root must be a retained directory")
    if _read_model_json(root, "modules.json") != [
        {
            "idx": 0,
            "name": "0",
            "path": "",
            "type": "sentence_transformers.base.modules.transformer.Transformer",
        },
        {
            "idx": 1,
            "name": "1",
            "path": "1_Pooling",
            "type": "sentence_transformers.sentence_transformer.modules.pooling.Pooling",
        },
    ]:
        raise MDenseOnError("mDenseOn serialized module topology drift")
    if _read_model_json(root, "1_Pooling/config.json") != {
        "embedding_dimension": MDENSEON_DIMENSION,
        "pooling_mode": "cls",
        "include_prompt": True,
    }:
        raise MDenseOnError("mDenseOn serialized CLS pooling drift")
    sentence_transformer = _read_model_json(root, "config_sentence_transformers.json")
    if not isinstance(sentence_transformer, dict):
        raise MDenseOnError("mDenseOn serialized prompt or similarity drift")
    sentence_transformer = cast(dict[str, object], sentence_transformer)
    if {
        "default_prompt_name": sentence_transformer.get("default_prompt_name"),
        "model_type": sentence_transformer.get("model_type"),
        "prompts": sentence_transformer.get("prompts"),
        "similarity_fn_name": sentence_transformer.get("similarity_fn_name"),
    } != {
        "default_prompt_name": None,
        "model_type": "SentenceTransformer",
        "prompts": {
            "document": MDENSEON_DOCUMENT_PROMPT,
            "query": MDENSEON_QUERY_PROMPT,
        },
        "similarity_fn_name": "cosine",
    }:
        raise MDenseOnError("mDenseOn serialized prompt or similarity drift")
    if _read_model_json(root, "sentence_bert_config.json") != {
        "transformer_task": "feature-extraction",
        "modality_config": {
            "text": {
                "method": "forward",
                "method_output_name": "last_hidden_state",
            }
        },
        "module_output_name": "token_embeddings",
    }:
        raise MDenseOnError("mDenseOn serialized transformer output drift")


class MDenseOnEmbedder:
    """Encode mDenseOn with explicit role prompts, CLS pooling, and L2 normalization.

    The retained Hugging Face serialization currently references Sentence Transformers
    module paths newer than DSPx's frozen v1 runtime. The model architecture itself is
    one Transformers encoder followed by CLS pooling, so this adapter executes that
    declared architecture directly without remote code or a dependency upgrade that
    would invalidate the retained MiniLM v1 runtime.
    """

    def __init__(
        self,
        model_name: str = MDENSEON_REPOSITORY_ID,
        *,
        model_root: Path | None = None,
        device: str = "cpu",
        max_tokens: int = MDENSEON_MAX_TOKENS,
    ) -> None:
        if model_name != MDENSEON_REPOSITORY_ID:
            raise MDenseOnError("mDenseOn adapter requires the frozen repository id")
        if device != "cpu":
            raise MDenseOnError("mDenseOn evaluation and default are CPU-only")
        if type(max_tokens) is not int or max_tokens != MDENSEON_MAX_TOKENS:
            raise MDenseOnError("mDenseOn maximum-token contract drift")
        explicit_model_root = model_root
        if model_root is None:
            huggingface_hub = import_module("huggingface_hub")
            snapshot_download = getattr(huggingface_hub, "snapshot_download")
            model_root = Path(
                snapshot_download(
                    repo_id=MDENSEON_REPOSITORY_ID,
                    revision=MDENSEON_REVISION,
                    allow_patterns=list(MDENSEON_ARTIFACT_PATHS),
                )
            )
        else:
            validate_serialized_mdenseon_semantics(model_root)

        transformers = import_module("transformers")
        torch = import_module("torch")
        tokenizer_cls = getattr(transformers, "PreTrainedTokenizerFast")
        model_cls = getattr(transformers, "AutoModel")
        self._tokenizer = tokenizer_cls(
            tokenizer_file=str(model_root / "tokenizer.json"),
            model_max_length=MDENSEON_MAX_TOKENS,
            padding_side="right",
            truncation_side="right",
            bos_token="<bos>",
            cls_token="<bos>",
            eos_token="<eos>",
            sep_token="<eos>",
            mask_token="<mask>",
            pad_token="<pad>",
            unk_token="<unk>",
            clean_up_tokenization_spaces=False,
        )
        tokenizer_identity = {
            "implementation": (
                f"{type(self._tokenizer).__module__}."
                f"{type(self._tokenizer).__qualname__}"
            ),
            "model_max_length": self._tokenizer.model_max_length,
            "padding_side": self._tokenizer.padding_side,
            "truncation_side": self._tokenizer.truncation_side,
            "vocabulary_size": len(self._tokenizer),
        }
        if tokenizer_identity != {
            "implementation": "transformers.tokenization_utils_fast.PreTrainedTokenizerFast",
            "model_max_length": MDENSEON_MAX_TOKENS,
            "padding_side": "right",
            "truncation_side": "right",
            "vocabulary_size": 256000,
        }:
            raise MDenseOnError(
                f"mDenseOn tokenizer identity drift: {tokenizer_identity!r}"
            )
        self._model = model_cls.from_pretrained(
            str(model_root),
            local_files_only=True,
            trust_remote_code=False,
            use_safetensors=True,
            torch_dtype=torch.float32,
        )
        self._model.to(device)
        self._model.eval()
        self._model_name = model_name
        self._model_root = explicit_model_root
        self._device = device
        self._max_tokens = max_tokens
        self._observed_vector_dtype: str | None = None
        self._observed_roles: set[str] = set()

        config = self._model.config
        observed = {
            "model_type": getattr(config, "model_type", None),
            "hidden_size": getattr(config, "hidden_size", None),
            "max_position_embeddings": getattr(config, "max_position_embeddings", None),
        }
        if observed != {
            "model_type": "modernbert",
            "hidden_size": MDENSEON_DIMENSION,
            "max_position_embeddings": MDENSEON_MAX_TOKENS,
        }:
            raise MDenseOnError(f"mDenseOn architecture drift: {observed!r}")
        first_parameter = next(self._model.parameters())
        self._observed_device = str(first_parameter.device)
        self._observed_parameter_dtype = str(first_parameter.dtype)
        if (
            self._observed_device != device
            or self._observed_parameter_dtype != "torch.float32"
        ):
            raise MDenseOnError("mDenseOn CPU float32 parameter identity drift")

    @property
    def tokenizer(self) -> Any:
        return self._tokenizer

    def get_dimension(self) -> int:
        return MDENSEON_DIMENSION

    def encode(self, texts: list[str], *, role: EmbeddingRole) -> list[list[float]]:
        """Encode one complete ordered batch under the required retrieval role."""

        if role not in {"document", "query"}:
            raise MDenseOnError("mDenseOn role must be document or query")
        if not texts or any(not isinstance(text, str) or not text for text in texts):
            raise MDenseOnError("mDenseOn texts must be a non-empty string batch")
        prompt = (
            MDENSEON_DOCUMENT_PROMPT if role == "document" else MDENSEON_QUERY_PROMPT
        )
        prompted = [f"{prompt}{text}" for text in texts]
        torch = import_module("torch")
        encoded = modernbert_model_inputs(
            self._tokenizer(
                prompted,
                padding=True,
                truncation=True,
                max_length=self._max_tokens,
                return_tensors="pt",
            )
        )
        encoded = {name: value.to(self._device) for name, value in encoded.items()}
        with torch.inference_mode():
            output = self._model(**encoded)
            vectors = output.last_hidden_state[:, 0, :].to(dtype=torch.float32)
            vectors = torch.nn.functional.normalize(vectors, p=2, dim=1)
            vectors = vectors.cpu()
        if tuple(vectors.shape) != (len(texts), MDENSEON_DIMENSION):
            raise MDenseOnError("mDenseOn output batch shape drift")
        if str(vectors.dtype) != "torch.float32":
            raise MDenseOnError("mDenseOn output dtype drift")
        resolved = vectors.tolist()
        for vector in resolved:
            validate_unit_vector(vector)
        self._observed_vector_dtype = "float32"
        self._observed_roles.add(role)
        return resolved

    def encode_documents(self, texts: list[str]) -> list[list[float]]:
        return self.encode(texts, role="document")

    def encode_queries(self, texts: list[str]) -> list[list[float]]:
        return self.encode(texts, role="query")

    def build_identity(
        self,
        spec: SentenceTransformerIdentitySpec,
        *,
        frozen_runtime_lock_sha256: str,
        runtime_versions: Mapping[str, str] | None = None,
        runtime_distribution_content_sha256: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """Bind retained artifacts, runtime, prompts, and the direct CLS adapter."""

        if self._model_root is None:
            raise MDenseOnError(
                "complete mDenseOn identity requires a retained model root"
            )
        if self._observed_vector_dtype is None or self._observed_roles != {
            "document",
            "query",
        }:
            raise MDenseOnError(
                "complete mDenseOn identity requires document and query batch observations"
            )
        torch = import_module("torch")
        base = build_sentence_transformer_identity(
            spec=spec,
            model_root=self._model_root,
            tokenizer=self._tokenizer,
            dimension=MDENSEON_DIMENSION,
            observed_vector_dtype=self._observed_vector_dtype,
            frozen_runtime_lock_sha256=frozen_runtime_lock_sha256,
            runtime_observations={
                "model_device": self._observed_device,
                "torch_cuda_available": bool(torch.cuda.is_available()),
                "torch_default_dtype": str(torch.get_default_dtype()),
                "numpy_output_dtype": self._observed_vector_dtype,
            },
            runtime_versions=runtime_versions,
            runtime_distribution_content_sha256=runtime_distribution_content_sha256,
        )
        base.update(
            {
                "schema_version": MDENSEON_IDENTITY_SCHEMA,
                "backend": "transformers-dense",
                "adapter": {
                    "name": MDENSEON_ADAPTER,
                    "trust_remote_code": False,
                    "pooling": "last_hidden_state_cls_token",
                    "document_prompt": MDENSEON_DOCUMENT_PROMPT,
                    "query_prompt": MDENSEON_QUERY_PROMPT,
                    "maximum_tokens": MDENSEON_MAX_TOKENS,
                    "serialized_semantics_verified": True,
                    "removed_model_input_keys": ["token_type_ids"],
                },
                "architecture": {
                    "model_type": "modernbert",
                    "hidden_size": MDENSEON_DIMENSION,
                    "parameter_dtype": self._observed_parameter_dtype,
                    "maximum_position_embeddings": MDENSEON_MAX_TOKENS,
                },
            }
        )
        return base

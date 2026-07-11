from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping
from uuid import uuid4

from dspx.redaction import redact_url

RUN_RECEIPT_VERSION = "v2"
RUN_IDENTITY_VERSION = "v1"
EXECUTION_REPLAY_POLICY_VERSION = "local-execution-replay-v2"
PROGRAM_RUNTIME_REPLAY_CONTRACT_MODES = frozenset({"none", "pdf_transition_review"})

_EXECUTION_REPLAY_EFFECTS = {
    "network_access_requested": False,
    "network_isolation_enforced": False,
    "provider_call": False,
    "mlflow": False,
    "subprocess": True,
    "temporary_filesystem": True,
    "external_filesystem_access_requested": False,
    "external_filesystem_isolation_enforced": False,
    "source_artifact_write": False,
    "shared_oracle": False,
    "external_authority_mutation_requested": False,
    "explicit_replay_output_write": True,
}
_EXECUTION_REPLAY_PROGRAM_RUNTIME_KEYS = {
    "candidate_manifest_path",
    "candidate_manifest_sha256",
    "candidate_receipt_path",
    "candidate_receipt_sha256",
    "runtime_inputs_sha256",
    "replay_fixture_path",
    "replay_fixture_sha256",
    "contract_mode",
    "skip_oracle_index",
    "publication_preflight_requested",
    "expected_episode",
}
_PROGRAM_RUNTIME_EXPECTED_EPISODE_KEYS = {
    "runtime_episode_id",
    "contract_mode",
    "execution_status",
    "status",
    "quality_status",
    "quality_evaluation_sha256",
    "observed_outputs_sha256",
    "behavior_results_sha256",
    "oracle_evidence_sha256",
    "program_runtime_traces_sha256",
    "runtime_episode_sha256",
}
_PROGRAM_RUNTIME_EXPECTED_EPISODE_HASH_KEYS = {
    "quality_evaluation_sha256",
    "observed_outputs_sha256",
    "behavior_results_sha256",
    "oracle_evidence_sha256",
    "program_runtime_traces_sha256",
    "runtime_episode_sha256",
}
_EXECUTION_REPLAY_SIGNATURE_OPTION_KEYS = {
    "class_name",
    "constraints",
    "feedback",
    "inputs",
    "max_attempts",
    "outputs",
}


# Outcome types for Oracle Dreaming/Consciousness
OutcomeType = Literal["success", "failure", "partial", "cached", "unknown"]


# Cached execution context (static portion computed once per process)
_CACHED_STATIC_EXECUTION_CONTEXT: dict[str, Any] | None = None
_SENSITIVE_ENV_FIELD_NAMES = {
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "token",
}
_SENSITIVE_ENV_FIELD_SUFFIXES = (
    "_access_token",
    "_api_key",
    "_password",
    "_secret",
    "_token",
)


@dataclass(frozen=True)
class RunIdentity:
    """Explicit contract for receipt identity across schema versions."""

    execution_id: str | None = None
    legacy_run_id: str | None = None
    cache_key: str | None = None
    output_hash: str | None = None
    output_path: str | None = None
    meta_path: str | None = None
    warnings: tuple[str, ...] = ()
    version: str = RUN_IDENTITY_VERSION

    @staticmethod
    def _pick(*candidates: tuple[str | None, str]) -> tuple[str | None, str | None]:
        for value, source in candidates:
            if value:
                return value, source
        return None, None

    @property
    def canonical_id(self) -> str | None:
        value, _ = self._pick(
            (self.execution_id, "execution_id"),
            (self.legacy_run_id, "run_id"),
            (self.cache_key, "cache_key"),
            (self.output_hash, "hash"),
            (self.output_path, "output_path"),
            (self.meta_path, "meta_path"),
        )
        return value

    @property
    def canonical_source(self) -> str | None:
        _, source = self._pick(
            (self.execution_id, "execution_id"),
            (self.legacy_run_id, "run_id"),
            (self.cache_key, "cache_key"),
            (self.output_hash, "hash"),
            (self.output_path, "output_path"),
            (self.meta_path, "meta_path"),
        )
        return source

    @property
    def behavioral_id(self) -> str | None:
        value, _ = self._pick(
            (self.legacy_run_id, "run_id"),
            (self.cache_key, "cache_key"),
            (self.output_hash, "hash"),
        )
        return value

    @property
    def behavioral_source(self) -> str | None:
        _, source = self._pick(
            (self.legacy_run_id, "run_id"),
            (self.cache_key, "cache_key"),
            (self.output_hash, "hash"),
        )
        return source

    @property
    def storage_id(self) -> str | None:
        value, _ = self._pick(
            (self.execution_id, "execution_id"),
            (self.legacy_run_id, "run_id"),
            (self.cache_key, "cache_key"),
            (self.output_hash, "hash"),
            (self.output_path, "output_path"),
            (self.meta_path, "meta_path"),
        )
        return value

    @property
    def storage_source(self) -> str | None:
        _, source = self._pick(
            (self.execution_id, "execution_id"),
            (self.legacy_run_id, "run_id"),
            (self.cache_key, "cache_key"),
            (self.output_hash, "hash"),
            (self.output_path, "output_path"),
            (self.meta_path, "meta_path"),
        )
        return source

    @property
    def alias_ids(self) -> tuple[str, ...]:
        seen: set[str] = set()
        aliases: list[str] = []
        for value in (
            self.execution_id,
            self.legacy_run_id,
            self.cache_key,
            self.output_hash,
            self.output_path,
            self.meta_path,
        ):
            if not value or value in seen:
                continue
            seen.add(value)
            aliases.append(value)
        return tuple(aliases)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "execution_id": self.execution_id,
            "legacy_run_id": self.legacy_run_id,
            "cache_key": self.cache_key,
            "output_hash": self.output_hash,
            "output_path": self.output_path,
            "meta_path": self.meta_path,
            "canonical_id": self.canonical_id,
            "canonical_source": self.canonical_source,
            "behavioral_id": self.behavioral_id,
            "behavioral_source": self.behavioral_source,
            "storage_id": self.storage_id,
            "storage_source": self.storage_source,
            "alias_ids": list(self.alias_ids),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class ReceiptProvenance:
    """Normalized receipt provenance with typed identity and lineage."""

    identity: RunIdentity
    branch: str
    parent_run_id: str | None = None
    causal_chain: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def run_id(self) -> str | None:
        return self.identity.canonical_id

    @property
    def lineage_ids(self) -> tuple[str, ...]:
        ids = list(self.causal_chain)
        if self.parent_run_id and self.parent_run_id not in ids:
            ids.append(self.parent_run_id)
        return tuple(ids)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "branch": self.branch,
            "parent_run_id": self.parent_run_id,
            "causal_chain": list(self.causal_chain),
            "lineage_ids": list(self.lineage_ids),
            "identity": self.identity.to_dict(),
            "warnings": list(self.warnings),
        }


def _capture_git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if result.returncode == 0:
        return result.stdout.strip()[:12] or None
    return None


def _capture_git_dirty() -> bool:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False
    return bool(result.returncode == 0 and result.stdout.strip())


def _env_key_is_sensitive(key: str) -> bool:
    lowered = str(key or "").strip().lower()
    return lowered in _SENSITIVE_ENV_FIELD_NAMES or lowered.endswith(
        _SENSITIVE_ENV_FIELD_SUFFIXES
    )


def _environment_context_hash() -> str | None:
    entries = []
    for key in sorted(
        k for k in os.environ if k.startswith(("DSPX_", "DSPY_", "MLFLOW_"))
    ):
        value = "[REDACTED]" if _env_key_is_sensitive(key) else os.environ.get(key, "")
        entries.append(f"{key}={value}")
    if not entries:
        return None
    return hashlib.sha256("\0".join(entries).encode("utf-8")).hexdigest()[:16]


def _get_static_execution_context() -> dict[str, Any]:
    global _CACHED_STATIC_EXECUTION_CONTEXT
    if _CACHED_STATIC_EXECUTION_CONTEXT is not None:
        return dict(_CACHED_STATIC_EXECUTION_CONTEXT)

    ctx: dict[str, Any] = {
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "platform": sys.platform,
    }
    git_commit = _capture_git_commit()
    if git_commit:
        ctx["git_commit"] = git_commit

    _CACHED_STATIC_EXECUTION_CONTEXT = dict(ctx)
    return dict(ctx)


def _get_execution_context() -> dict[str, Any]:
    """Capture system state for behavioral analysis.

    Static fields are cached per-process; dynamic drift-sensitive fields are
    recomputed for each receipt.
    """
    ctx = _get_static_execution_context()
    if _capture_git_dirty():
        ctx["git_dirty"] = True
    env_hash = _environment_context_hash()
    if env_hash:
        ctx["env_hash"] = env_hash
    return ctx


def receipt_path_for_output(output_path: Path) -> Path:
    return output_path.parent / f"{output_path.name}.meta.json"


def _service_from_run_kind(run_kind: str) -> str | None:
    return {
        "signature-gen": "signature",
        "signature-refine": "signature",
        "module-gen": "module",
        "codegen": "codegen",
        "mermaid": "mermaid",
        "program-gen": "program",
    }.get((run_kind or "").strip().lower())


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    return str(value)


def canonical_replay_identity_hash(value: Any) -> str:
    encoded = json.dumps(
        _json_safe(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def current_execution_replay_runtime_identity() -> dict[str, Any]:
    """Stable compatibility identity for the versioned local replay executor."""
    return {
        "executor_version": EXECUTION_REPLAY_POLICY_VERSION,
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
        "platform": sys.platform,
    }


def valid_program_runtime_expected_episode(
    value: object, *, contract_mode: object
) -> bool:
    if not isinstance(value, Mapping):
        return False
    payload: dict[str, Any] = {str(key): item for key, item in value.items()}
    if set(payload) != _PROGRAM_RUNTIME_EXPECTED_EPISODE_KEYS:
        return False
    if payload.get("contract_mode") != contract_mode:
        return False
    if any(
        not isinstance(payload.get(key), str) or not str(payload.get(key)).strip()
        for key in {
            "runtime_episode_id",
            "execution_status",
            "status",
            "quality_status",
        }
    ):
        return False
    return all(
        isinstance(payload.get(key), str)
        and len(str(payload.get(key))) == 64
        and all(character in "0123456789abcdef" for character in str(payload.get(key)))
        for key in _PROGRAM_RUNTIME_EXPECTED_EPISODE_HASH_KEYS
    )


def build_execution_replay_policy(
    *,
    run_kind: str,
    provider: str,
    provider_details: Mapping[str, Any],
    replay_inputs: Mapping[str, Any],
    output_hash: str,
) -> dict[str, Any]:
    """Bind the narrow local executor to input/provider/runtime/output identities."""
    run_kind_norm = str(run_kind or "").strip().lower()
    provider_norm = str(provider or "").strip()
    inputs = _json_safe(dict(replay_inputs))
    provider_identity = {
        "provider": provider_norm,
        "provider_details": _json_safe(dict(provider_details)),
    }
    runtime_identity = current_execution_replay_runtime_identity()
    options = inputs.get("options") if isinstance(inputs, Mapping) else None
    template_version = str(inputs.get("template_version") or "")

    unsupported_reasons: list[str] = []
    strategy: str | None = None
    if provider_norm != "stub":
        unsupported_reasons.append("unsupported_provider")
    if run_kind_norm == "signature-gen":
        strategy = "signature-gen-local-reexecution"
        if not template_version.startswith("simple-"):
            unsupported_reasons.append("unsupported_template")
        if (
            not isinstance(options, Mapping)
            or set(options) - _EXECUTION_REPLAY_SIGNATURE_OPTION_KEYS
        ):
            unsupported_reasons.append("unsupported_options")
    elif run_kind_norm == "program-runtime":
        strategy = "program-runtime-local-reexecution"
        if set(inputs) != _EXECUTION_REPLAY_PROGRAM_RUNTIME_KEYS:
            unsupported_reasons.append("unsupported_inputs")
        if inputs.get("contract_mode") not in PROGRAM_RUNTIME_REPLAY_CONTRACT_MODES:
            unsupported_reasons.append("unsupported_contract_mode")
        if inputs.get("skip_oracle_index") is not True:
            unsupported_reasons.append("oracle_index_not_skipped")
        if inputs.get("publication_preflight_requested") is not False:
            unsupported_reasons.append("publication_preflight_requested")
        fixture_path = inputs.get("replay_fixture_path")
        fixture_hash = inputs.get("replay_fixture_sha256")
        if not isinstance(fixture_path, str) or not fixture_path:
            unsupported_reasons.append("missing_replay_fixture")
        if not isinstance(fixture_hash, str) or len(fixture_hash) != 64:
            unsupported_reasons.append("missing_replay_fixture_hash")
        if not valid_program_runtime_expected_episode(
            inputs.get("expected_episode"), contract_mode=inputs.get("contract_mode")
        ):
            unsupported_reasons.append("invalid_expected_episode")
    else:
        unsupported_reasons.append("unsupported_run_kind")
    if os.name != "posix" or not all(
        hasattr(os, name) for name in ("O_DIRECTORY", "O_NOFOLLOW")
    ):
        unsupported_reasons.append("secure_output_creation_unavailable")

    supported = not unsupported_reasons
    return {
        "schema_version": EXECUTION_REPLAY_POLICY_VERSION,
        "supported": supported,
        "strategy": strategy if supported else None,
        "unsupported_reasons": unsupported_reasons,
        "local_only": True,
        "input_hash": canonical_replay_identity_hash(inputs),
        "provider_identity": {
            **provider_identity,
            "hash": canonical_replay_identity_hash(provider_identity),
        },
        "runtime_identity": {
            **runtime_identity,
            "hash": canonical_replay_identity_hash(runtime_identity),
        },
        "output_identity": {"algorithm": "sha256", "hash": str(output_hash)},
        "effects": dict(_EXECUTION_REPLAY_EFFECTS),
    }


def _hash_prefix(value: str | None, *, width: int = 12) -> str:
    raw = (value or "").strip().lower()
    if not raw:
        return ""
    filtered = "".join(ch for ch in raw if ch in "0123456789abcdef")
    if len(filtered) < width:
        return ""
    return filtered[:width]


def _bool_env(name: str) -> bool | None:
    raw = os.getenv(name)
    if raw is None:
        return None
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _normalized_optional_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _normalized_path_str(value: Path | str) -> str:
    return str(Path(value).expanduser().resolve())


def _normalized_optional_path_str(value: Any) -> str | None:
    if value in {None, ""}:
        return None
    try:
        return _normalized_path_str(str(value))
    except Exception:
        return _normalized_optional_str(value)


def _normalize_run_id_list(
    values: Iterable[Any], *, field_name: str
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    normalized: list[str] = []
    warnings: list[str] = []
    non_string_items = 0
    blank_items = 0
    overlength_items = 0

    for item in values:
        if not isinstance(item, str):
            non_string_items += 1
            continue
        text = item.strip()
        if not text:
            blank_items += 1
            continue
        if len(text) > 128:
            overlength_items += 1
            continue
        normalized.append(text)

    deduped = tuple(build_causal_chain(*normalized))
    duplicate_items = len(normalized) - len(deduped)

    if non_string_items:
        warnings.append(f"{field_name}:ignored_non_string_items={non_string_items}")
    if blank_items:
        warnings.append(f"{field_name}:ignored_blank_items={blank_items}")
    if overlength_items:
        warnings.append(f"{field_name}:ignored_overlength_items={overlength_items}")
    if duplicate_items:
        warnings.append(f"{field_name}:deduplicated_items={duplicate_items}")

    return deduped, tuple(warnings)


def _parse_env_causal_chain(raw: str | None) -> list[str] | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list):
        values, _warnings = _normalize_run_id_list(parsed, field_name="causal_chain")
        return list(values) or None
    return build_causal_chain(*(part.strip() for part in text.split(","))) or None


def current_receipt_lineage(
    *,
    branch: str | None = None,
    parent_run_id: str | None = None,
    causal_chain: list[str] | None = None,
) -> dict[str, Any]:
    resolved_parent = (
        str(parent_run_id or os.getenv("DSPX_PARENT_RUN_ID") or "").strip() or None
    )
    if causal_chain is not None:
        resolved_chain, _warnings = _normalize_run_id_list(
            causal_chain, field_name="causal_chain"
        )
        resolved_chain_list = list(resolved_chain)
    else:
        resolved_chain_list = (
            _parse_env_causal_chain(os.getenv("DSPX_CAUSAL_CHAIN")) or []
        )
    if resolved_parent:
        resolved_chain_list = build_causal_chain(*resolved_chain_list, resolved_parent)
    resolved_branch = get_branch_name(
        explicit_branch=(
            branch or os.getenv("DSPX_RECEIPT_BRANCH") or os.getenv("DSPX_BRANCH")
        )
    )
    payload: dict[str, Any] = {"branch": resolved_branch}
    if resolved_parent:
        payload["parent_run_id"] = resolved_parent
    if resolved_chain_list:
        payload["causal_chain"] = resolved_chain_list
    return payload


def resolve_run_identity(
    receipt: Mapping[str, Any],
    *,
    meta_path: Path | None = None,
) -> RunIdentity:
    """Resolve explicit receipt identity facets across schema versions."""
    identity = RunIdentity(
        execution_id=_normalized_optional_str(receipt.get("execution_id")),
        legacy_run_id=_normalized_optional_str(receipt.get("run_id")),
        cache_key=_normalized_optional_str(receipt.get("cache_key")),
        output_hash=_normalized_optional_str(receipt.get("hash")),
        output_path=_normalized_optional_str(receipt.get("output_path")),
        meta_path=str(meta_path) if meta_path is not None else None,
    )
    warnings = list(identity.warnings)
    if identity.canonical_source in {"output_path", "meta_path"}:
        warnings.append(f"identity:using_path_fallback={identity.canonical_source}")
    if not identity.canonical_id:
        warnings.append("identity:missing")
    return RunIdentity(
        execution_id=identity.execution_id,
        legacy_run_id=identity.legacy_run_id,
        cache_key=identity.cache_key,
        output_hash=identity.output_hash,
        output_path=identity.output_path,
        meta_path=identity.meta_path,
        warnings=tuple(warnings),
    )


def resolve_receipt_run_id(
    receipt: Mapping[str, Any],
    *,
    meta_path: Path | None = None,
) -> str | None:
    """Resolve the canonical run identity for a receipt."""
    return resolve_run_identity(receipt, meta_path=meta_path).canonical_id


def resolve_receipt_provenance(
    receipt: Mapping[str, Any],
    *,
    meta_path: Path | None = None,
    default_branch: str = "main",
) -> ReceiptProvenance:
    """Normalize receipt identity and lineage across schema versions."""
    identity = resolve_run_identity(receipt, meta_path=meta_path)
    warnings = list(identity.warnings)

    raw_parent_run_id = receipt.get("parent_run_id")
    parent_run_id = _normalized_optional_str(raw_parent_run_id)
    if raw_parent_run_id is not None and parent_run_id is None:
        warnings.append("parent_run_id:ignored_invalid_value")

    raw_causal_chain = receipt.get("causal_chain")
    if isinstance(raw_causal_chain, list):
        causal_chain, chain_warnings = _normalize_run_id_list(
            raw_causal_chain, field_name="causal_chain"
        )
        warnings.extend(chain_warnings)
    elif raw_causal_chain is None:
        causal_chain = ()
    else:
        causal_chain = ()
        warnings.append("causal_chain:ignored_invalid_value")

    branch = _normalized_optional_str(receipt.get("branch")) or default_branch
    return ReceiptProvenance(
        identity=identity,
        branch=branch,
        parent_run_id=parent_run_id,
        causal_chain=causal_chain,
        warnings=tuple(warnings),
    )


def normalize_receipt_provenance(
    receipt: Mapping[str, Any],
    *,
    meta_path: Path | None = None,
    default_branch: str = "main",
) -> dict[str, Any]:
    """Backward-compatible dict view of normalized receipt provenance."""
    return resolve_receipt_provenance(
        receipt,
        meta_path=meta_path,
        default_branch=default_branch,
    ).to_dict()


def _current_provider_details() -> dict[str, Any]:
    provider = str(os.getenv("DSPX_PROVIDER") or "pi-rpc")
    details: dict[str, Any] = {
        "provider": provider,
        "provider_family": provider,
    }

    if provider == "dspy-lm-auth":
        details.update(
            {
                "requested_model": os.getenv("DSPX_LM_AUTH_MODEL") or "codex/gpt-5.5",
                "auth_provider": os.getenv("DSPX_LM_AUTH_PROVIDER") or None,
                "auth_storage": "[REDACTED]",
                "auth_storage_exists": "[REDACTED]",
                "timeout": os.getenv("DSPX_LM_AUTH_TIMEOUT") or None,
            }
        )
        return details

    if provider in {"openai-compatible", "vllm-local"}:
        prefix = "DSPX_VLLM" if provider == "vllm-local" else "DSPX_OPENAI_COMPAT"
        details.update(
            {
                "base_url": redact_url(
                    str(os.getenv(f"{prefix}_API_BASE") or "http://127.0.0.1:8000/v1")
                ),
                "model": os.getenv(f"{prefix}_MODEL") or "local-model",
                "timeout": os.getenv(f"{prefix}_TIMEOUT") or None,
                "json_mode": _bool_env(f"{prefix}_JSON_MODE"),
            }
        )
        return details

    if provider == "openrouter":
        details.update(
            {
                "base_url": redact_url(
                    str(
                        os.getenv("OPENROUTER_BASE_URL")
                        or "https://openrouter.ai/api/v1"
                    )
                ),
                "model": os.getenv("OPENROUTER_MODEL") or None,
                "timeout": os.getenv("OPENROUTER_TIMEOUT") or None,
            }
        )
        return details

    if provider == "pi-rpc":
        details.update(
            {
                "pi_provider": os.getenv("DSPX_PI_PROVIDER") or None,
                "model": os.getenv("DSPX_PI_MODEL") or None,
                "thinking": os.getenv("DSPX_PI_THINKING") or None,
                "timeout": os.getenv("DSPX_PI_TIMEOUT") or None,
                "no_tools": _bool_env("DSPX_PI_NO_TOOLS"),
                "no_session": _bool_env("DSPX_PI_NO_SESSION"),
            }
        )
        return details

    if provider == "codex-exec":
        details.update(
            {
                "model": os.getenv("CODEX_MODEL") or None,
                "reasoning": os.getenv("CODEX_REASONING") or None,
                "timeout": os.getenv("CODEX_TIMEOUT") or None,
                "search": _bool_env("CODEX_SEARCH"),
                "bypass": _bool_env("CODEX_BYPASS"),
            }
        )
        return details

    return details


def build_mlflow_hints(
    *,
    run_kind: str,
    template_version: str | None,
    output_path: Path,
    output_hash: str,
    cache_key: str | None = None,
    tracking_uri: str | None = None,
    extra_expected_tags: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build additive receipt hints for MLflow explain correlation.

    Hints are advisory only; replay correctness never depends on them.
    """
    run_kind_norm = str(run_kind or "other").strip().lower() or "other"
    output_basename = output_path.name
    output_hash_prefix = _hash_prefix(output_hash, width=12)

    expected_tags: dict[str, Any] = {
        "dspx.run_kind": run_kind_norm,
        "dspx.output_basename": output_basename,
    }
    if template_version:
        expected_tags["dspx.template_version"] = str(template_version)
    if cache_key:
        expected_tags["dspx.cache_key"] = str(cache_key)
    if output_hash_prefix:
        expected_tags["dspx.output_hash_prefix"] = output_hash_prefix

    service = _service_from_run_kind(run_kind_norm)
    if service:
        expected_tags["service"] = service
    if template_version:
        expected_tags["template_version"] = str(template_version)

    for key, val in (extra_expected_tags or {}).items():
        expected_tags[str(key)] = _json_safe(val)

    observed_uri_raw = (
        str(tracking_uri)
        if tracking_uri is not None
        else str(os.getenv("MLFLOW_TRACKING_URI") or "")
    )
    observed_uri = redact_url(observed_uri_raw)

    return {
        "tracking_uri_observed": observed_uri,
        "output_hash_prefix": output_hash_prefix,
        "expected_tags": _json_safe(expected_tags),
    }


def build_run_receipt(
    *,
    run_kind: str,
    output_path: Path,
    output_hash: str,
    template_version: str | None,
    cache_key: str | None,
    cache_file: str | None,
    cache_enabled: bool,
    replay_inputs: Mapping[str, Any] | None = None,
    run_summary: Mapping[str, Any] | None = None,
    extra: Mapping[str, Any] | None = None,
    execution_id: str | None = None,
    # === Phase C+ (Time Travel / Dreaming / Consciousness) ===
    causal_chain: list[str] | None = None,
    parent_run_id: str | None = None,
    branch: str | None = None,
    outcome: OutcomeType = "unknown",
    latency_ms: float | None = None,
    tokens_used: int | None = None,
    tokens_prompt: int | None = None,
    tokens_completion: int | None = None,
    capture_context: bool = True,
) -> dict[str, Any]:
    """Build a versioned run receipt for replay/explain.

    Backwards-compat fields (`hash`, `cache_key`, `cache_file`, `cache_enabled`)
    stay top-level so existing tooling keeps working.

    Phase C+ fields (optional, for Oracle behavioral analysis):

        causal_chain: List of run_ids that led to this execution.
            Enables Time Travel (bisect, branch diff).
            Example: ["abc123", "def456"] means this run was triggered
            after those runs completed.

        parent_run_id: Immediate parent run that triggered this one.
            Single-hop causal relationship for simpler queries.

        branch: Named behavioral branch (like git branches).
            Groups related runs for Time Travel operations.
            Default: "main" if not specified.

        outcome: Execution result for Dreaming/Consciousness.
            One of: success, failure, partial, cached, unknown.
            Used to learn which inputs produce good outputs.

        latency_ms: Execution duration in milliseconds.
            Used for behavioral simulation and cost modeling.

        tokens_used: Total tokens consumed (if available).
        tokens_prompt: Tokens in prompt (if available).
        tokens_completion: Tokens in completion (if available).

        capture_context: If True, capture git commit, Python version, env hash.
            Used by Consciousness for environment correlation.
    """
    provider_name = os.getenv("DSPX_PROVIDER") or "pi-rpc"
    provider_details = _json_safe(_current_provider_details())
    replay_inputs_payload = _json_safe(dict(replay_inputs or {}))
    receipt: dict[str, Any] = {
        "receipt_version": RUN_RECEIPT_VERSION,
        "execution_id": str(execution_id or uuid4().hex),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_kind": str(run_kind),
        "provider": provider_name,
        "provider_details": provider_details,
        "output_path": _normalized_path_str(output_path),
        "hash": str(output_hash),
        "template_version": template_version,
        "cache_key": cache_key,
        "cache_file": _normalized_optional_path_str(cache_file),
        "cache_enabled": bool(cache_enabled),
        "replay_inputs": replay_inputs_payload,
        "run_summary": _json_safe(dict(run_summary or {})),
        "execution_replay": build_execution_replay_policy(
            run_kind=run_kind,
            provider=provider_name,
            provider_details=provider_details,
            replay_inputs=replay_inputs_payload,
            output_hash=output_hash,
        ),
    }

    # Phase C+ fields (only add if non-default)
    if causal_chain:
        receipt["causal_chain"] = list(causal_chain)
    if parent_run_id:
        receipt["parent_run_id"] = str(parent_run_id)
    if branch:
        receipt["branch"] = str(branch)
    if outcome != "unknown":
        receipt["outcome"] = outcome
    if latency_ms is not None:
        receipt["latency_ms"] = float(latency_ms)
    if tokens_used is not None:
        receipt["tokens_used"] = int(tokens_used)
    if tokens_prompt is not None:
        receipt["tokens_prompt"] = int(tokens_prompt)
    if tokens_completion is not None:
        receipt["tokens_completion"] = int(tokens_completion)

    # Execution context (for Consciousness phase)
    if capture_context:
        receipt["execution_context"] = _get_execution_context()

    # Extra fields (don't overwrite core fields)
    for k, v in (extra or {}).items():
        if k in receipt:
            continue
        receipt[str(k)] = _json_safe(v)
    return receipt


def write_run_receipt(output_path: Path, receipt: Mapping[str, Any]) -> Path:
    meta_path = receipt_path_for_output(output_path)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps(
            _json_safe(dict(receipt)), ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )
    return meta_path


def load_run_receipt(meta_path: Path) -> dict[str, Any] | None:
    if not meta_path.exists() or not meta_path.is_file():
        return None
    try:
        loaded = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return loaded if isinstance(loaded, dict) else None


# =============================================================================
# Oracle Phase C+ Helpers (Time Travel / Dreaming / Consciousness)
# =============================================================================


def build_causal_chain(
    *parent_run_ids: str,
    include_context: bool = False,
) -> list[str]:
    """Build a causal chain from parent run IDs.

    Validates run IDs and deduplicates. Used by Time Travel to track
    behavioral lineage.

    Args:
        parent_run_ids: One or more parent run IDs to include
        include_context: If True, include execution context in chain

    Returns:
        List of validated, deduplicated run IDs
    """
    seen = set()
    chain = []
    for run_id in parent_run_ids:
        if not run_id:
            continue
        # Validate: non-empty string, reasonable length
        run_id = str(run_id).strip()
        if not run_id or len(run_id) > 128:
            continue
        if run_id not in seen:
            seen.add(run_id)
            chain.append(run_id)
    return chain


def extend_causal_chain(
    existing_chain: list[str] | None,
    new_run_id: str,
    max_depth: int = 50,
) -> list[str]:
    """Extend a causal chain with a new run ID.

    Maintains bounded depth to prevent unbounded growth.
    Used when chaining executions (e.g., signature-gen → module-gen).

    Args:
        existing_chain: Previous causal chain (may be None)
        new_run_id: Run ID to append
        max_depth: Maximum chain length (default 50)

    Returns:
        New causal chain with new_run_id appended
    """
    chain = list(existing_chain or [])
    if new_run_id and new_run_id not in chain:
        chain.append(new_run_id)
    # Trim from front if exceeds max depth
    if len(chain) > max_depth:
        chain = chain[-max_depth:]
    return chain


def get_branch_name(
    explicit_branch: str | None = None,
    git_branch_fallback: bool = True,
    default: str = "main",
) -> str:
    """Determine behavioral branch name.

    Precedence:
    1. Explicit branch name if provided
    2. Current git branch (if git_branch_fallback=True)
    3. Default branch name

    Args:
        explicit_branch: Explicitly specified branch name
        git_branch_fallback: If True, fall back to git branch
        default: Default branch name if no other source

    Returns:
        Branch name for behavioral grouping
    """
    if explicit_branch:
        return str(explicit_branch).strip() or default

    if git_branch_fallback:
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                branch = result.stdout.strip()
                if branch:
                    return branch
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

    return default


def compute_latency_ms(start_time: datetime) -> float:
    """Compute latency in milliseconds from start time to now.

    Args:
        start_time: When execution started (UTC)

    Returns:
        Latency in milliseconds
    """
    delta = datetime.now(timezone.utc) - start_time
    return delta.total_seconds() * 1000

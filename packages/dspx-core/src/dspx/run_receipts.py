from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Mapping
from uuid import uuid4

from dspx.redaction import redact_url

RUN_RECEIPT_VERSION = "v2"

# Outcome types for Oracle Dreaming/Consciousness
OutcomeType = Literal["success", "failure", "partial", "cached", "unknown"]


# Cached execution context (static portion computed once per process)
_CACHED_STATIC_EXECUTION_CONTEXT: dict[str, Any] | None = None


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
            ["git", "diff", "--stat", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False
    return bool(result.returncode == 0 and result.stdout.strip())


def _environment_context_hash() -> str | None:
    entries = []
    for key in sorted(
        k for k in os.environ if k.startswith(("DSPX_", "DSPY_", "MLFLOW_"))
    ):
        entries.append(f"{key}={os.environ.get(key, '')}")
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
    }.get((run_kind or "").strip().lower())


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    return str(value)


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


def _parse_env_causal_chain(raw: str | None) -> list[str] | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list):
        return build_causal_chain(*(str(item) for item in parsed)) or None
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
    resolved_chain = (
        build_causal_chain(*causal_chain)
        if causal_chain
        else _parse_env_causal_chain(os.getenv("DSPX_CAUSAL_CHAIN"))
    )
    if resolved_chain is None and resolved_parent:
        resolved_chain = build_causal_chain(resolved_parent)
    resolved_branch = get_branch_name(
        explicit_branch=(
            branch or os.getenv("DSPX_RECEIPT_BRANCH") or os.getenv("DSPX_BRANCH")
        )
    )
    payload: dict[str, Any] = {"branch": resolved_branch}
    if resolved_parent:
        payload["parent_run_id"] = resolved_parent
    if resolved_chain:
        payload["causal_chain"] = resolved_chain
    return payload


def _current_provider_details() -> dict[str, Any]:
    provider = str(os.getenv("DSPX_PROVIDER") or "pi-rpc")
    details: dict[str, Any] = {
        "provider": provider,
        "provider_family": provider,
    }

    if provider == "dspy-lm-auth":
        storage = str(
            Path(
                os.getenv("DSPX_LM_AUTH_STORAGE") or "~/.pi/agent/auth.json"
            ).expanduser()
        )
        details.update(
            {
                "requested_model": os.getenv("DSPX_LM_AUTH_MODEL") or "codex/gpt-5.4",
                "auth_provider": os.getenv("DSPX_LM_AUTH_PROVIDER") or None,
                "auth_storage": storage,
                "auth_storage_exists": Path(storage).exists(),
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

    observed_uri = (
        str(tracking_uri)
        if tracking_uri is not None
        else str(os.getenv("MLFLOW_TRACKING_URI") or "")
    )

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
    receipt: dict[str, Any] = {
        "receipt_version": RUN_RECEIPT_VERSION,
        "execution_id": str(execution_id or uuid4().hex),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_kind": str(run_kind),
        "provider": provider_name,
        "provider_details": _json_safe(_current_provider_details()),
        "output_path": str(output_path),
        "hash": str(output_hash),
        "template_version": template_version,
        "cache_key": cache_key,
        "cache_file": cache_file,
        "cache_enabled": bool(cache_enabled),
        "replay_inputs": _json_safe(dict(replay_inputs or {})),
        "run_summary": _json_safe(dict(run_summary or {})),
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

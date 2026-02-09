from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

RUN_RECEIPT_VERSION = "v1"


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
) -> dict[str, Any]:
    """Build a versioned run receipt for replay/explain.

    Backwards-compat fields (`hash`, `cache_key`, `cache_file`, `cache_enabled`)
    stay top-level so existing tooling keeps working.
    """

    receipt: dict[str, Any] = {
        "receipt_version": RUN_RECEIPT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_kind": str(run_kind),
        "provider": os.getenv("DSPX_PROVIDER") or "pi-rpc",
        "output_path": str(output_path),
        "hash": str(output_hash),
        "template_version": template_version,
        "cache_key": cache_key,
        "cache_file": cache_file,
        "cache_enabled": bool(cache_enabled),
        "replay_inputs": _json_safe(dict(replay_inputs or {})),
        "run_summary": _json_safe(dict(run_summary or {})),
    }
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

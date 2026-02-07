from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

RUN_RECEIPT_VERSION = "v1"


def receipt_path_for_output(output_path: Path) -> Path:
    return output_path.parent / f"{output_path.name}.meta.json"


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    return str(value)


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

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from dspx.cache import make_key
from dspx.run_receipts import RUN_RECEIPT_VERSION, load_run_receipt


_REQUIRED_FIELDS: tuple[str, ...] = (
    "receipt_version",
    "created_at",
    "run_kind",
    "provider",
    "output_path",
    "hash",
    "template_version",
    "cache_key",
    "cache_file",
    "cache_enabled",
    "replay_inputs",
)

_RUN_KIND_TO_CACHE_KIND: dict[str, str] = {
    "signature-gen": "signature",
    "signature-refine": "signature",
    "module-gen": "module",
    "codegen": "codegen",
}

_REQUIRED_REPLAY_INPUTS: dict[str, tuple[str, ...]] = {
    "signature-gen": ("prompt", "template_version", "options"),
    "signature-refine": (
        "prompt",
        "template_version",
        "attempts",
        "non_interactive",
        "wrap_script",
        "feedback",
        "constraints",
    ),
    "module-gen": (
        "name",
        "description",
        "inputs",
        "outputs",
        "use_signature",
        "template_version",
    ),
    "codegen": ("spec", "language", "template_version", "options"),
}


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _infer_output_path_from_meta(meta_path: Path) -> Path | None:
    suffix = ".meta.json"
    name = meta_path.name
    if name.endswith(suffix):
        return meta_path.parent / name[: -len(suffix)]
    return None


def _resolve_path(raw_path: str, *, meta_path: Path, output_hint: bool = False) -> Path:
    p = Path(raw_path).expanduser()
    if p.is_absolute():
        return p

    candidates: list[Path] = [p, meta_path.parent / p]
    if output_hint:
        inferred = _infer_output_path_from_meta(meta_path)
        if inferred is not None:
            candidates.append(inferred)

    for cand in candidates:
        if cand.exists():
            return cand

    # Stable fallback for diagnostics.
    return candidates[1] if len(candidates) > 1 else p


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(64 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _validate_receipt(receipt: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []

    for key in _REQUIRED_FIELDS:
        if key not in receipt:
            errors.append(f"missing required field: {key}")

    if errors:
        return errors

    if str(receipt.get("receipt_version") or "") != RUN_RECEIPT_VERSION:
        errors.append(
            f"unsupported receipt_version: {receipt.get('receipt_version')!r}"
        )

    run_kind = str(receipt.get("run_kind") or "")
    if run_kind not in _RUN_KIND_TO_CACHE_KIND:
        errors.append(f"unsupported run_kind: {run_kind!r}")

    if (
        not isinstance(receipt.get("output_path"), str)
        or not str(receipt.get("output_path")).strip()
    ):
        errors.append("field output_path must be a non-empty string")

    if not isinstance(receipt.get("hash"), str) or not str(receipt.get("hash")).strip():
        errors.append("field hash must be a non-empty string")

    if (
        not isinstance(receipt.get("cache_key"), str)
        or not str(receipt.get("cache_key")).strip()
    ):
        errors.append("field cache_key must be a non-empty string")

    if (
        not isinstance(receipt.get("cache_file"), str)
        or not str(receipt.get("cache_file")).strip()
    ):
        errors.append("field cache_file must be a non-empty string")

    if not isinstance(receipt.get("cache_enabled"), bool):
        errors.append("field cache_enabled must be bool")

    replay_inputs = receipt.get("replay_inputs")
    if not isinstance(replay_inputs, Mapping):
        errors.append("field replay_inputs must be an object")
    else:
        required_inputs = _REQUIRED_REPLAY_INPUTS.get(run_kind, ())
        missing_inputs = [k for k in required_inputs if k not in replay_inputs]
        if missing_inputs:
            errors.append(
                "replay_inputs missing required keys: "
                + ", ".join(sorted(missing_inputs))
            )

    return errors


def _expected_cache_payload(receipt: Mapping[str, Any]) -> dict[str, Any] | None:
    run_kind = str(receipt.get("run_kind") or "")
    replay_inputs = _as_dict(receipt.get("replay_inputs"))

    if run_kind == "signature-gen":
        class_name = replay_inputs.get("class_name")
        options = replay_inputs.get("options")
        opts = _as_dict(options)
        cls = str(class_name or "GeneratedSignature")
        return {
            "kind": "signature",
            "prompt": replay_inputs.get("prompt"),
            "template_version": replay_inputs.get("template_version"),
            "class_name": cls,
            "options": opts,
        }

    if run_kind == "signature-refine":
        return {
            "kind": "signature",
            "prompt": replay_inputs.get("prompt"),
            "template_version": replay_inputs.get("template_version"),
            "class_name": str(receipt.get("class_name") or ""),
            "mode": str(receipt.get("mode") or "refine"),
            "backend": str(receipt.get("backend") or "native"),
            "attempts": int(replay_inputs.get("attempts") or 1),
            "non_interactive": bool(replay_inputs.get("non_interactive")),
            "feedback": _as_list(replay_inputs.get("feedback")),
            "constraints": _as_list(replay_inputs.get("constraints")),
        }

    if run_kind == "module-gen":
        return {
            "kind": "module",
            "name": replay_inputs.get("name"),
            "description": replay_inputs.get("description"),
            "inputs": _as_list(replay_inputs.get("inputs")),
            "outputs": _as_list(replay_inputs.get("outputs")),
            "use_signature": bool(replay_inputs.get("use_signature")),
            "template_version": replay_inputs.get("template_version"),
        }

    if run_kind == "codegen":
        return {
            "kind": "codegen",
            "spec": replay_inputs.get("spec"),
            "language": replay_inputs.get("language"),
            "template_version": replay_inputs.get("template_version"),
            "options": _as_dict(replay_inputs.get("options")),
        }

    return None


def check_run_receipt(meta_path: Path) -> dict[str, Any]:
    report: dict[str, Any] = {
        "status": "ok",
        "receipt_path": str(meta_path),
        "checks": {},
        "errors": [],
        "warnings": [],
    }

    if not meta_path.exists() or not meta_path.is_file():
        report["status"] = "invalid"
        report["errors"].append(f"receipt not found: {meta_path}")
        return report

    receipt = load_run_receipt(meta_path)
    if receipt is None:
        report["status"] = "invalid"
        report["errors"].append("receipt is not valid JSON object")
        return report

    report["receipt_version"] = receipt.get("receipt_version")
    report["run_kind"] = receipt.get("run_kind")

    validation_errors = _validate_receipt(receipt)
    if validation_errors:
        report["status"] = "invalid"
        report["errors"].extend(validation_errors)
        return report

    receipt_hash = str(receipt.get("hash") or "")
    output_path = _resolve_path(
        str(receipt.get("output_path") or ""), meta_path=meta_path, output_hint=True
    )
    report["output_path"] = str(output_path)
    report["receipt_hash"] = receipt_hash

    checks: dict[str, bool] = report["checks"]

    output_exists = output_path.exists() and output_path.is_file()
    checks["output_exists"] = bool(output_exists)
    if not output_exists:
        report["errors"].append(f"output artifact missing: {output_path}")
    else:
        actual_hash = _sha256_file(output_path)
        report["actual_output_hash"] = actual_hash
        checks["output_hash_match"] = actual_hash == receipt_hash
        if actual_hash != receipt_hash:
            report["errors"].append(
                f"output hash mismatch: expected={receipt_hash} actual={actual_hash}"
            )

    cache_key = str(receipt.get("cache_key") or "")
    cache_file = _resolve_path(
        str(receipt.get("cache_file") or ""), meta_path=meta_path
    )
    cache_enabled = bool(receipt.get("cache_enabled"))
    run_kind = str(receipt.get("run_kind") or "")
    cache_kind = _RUN_KIND_TO_CACHE_KIND.get(run_kind) or ""

    report["cache_key"] = cache_key
    report["cache_file"] = str(cache_file)
    report["cache_enabled"] = cache_enabled

    checks["cache_file_matches_key"] = cache_file.name == f"{cache_key}.json"
    if not checks["cache_file_matches_key"]:
        report["errors"].append(
            "cache linkage mismatch: cache_file basename does not match cache_key"
        )

    checks["cache_kind_matches_run_kind"] = cache_file.parent.name == cache_kind
    if not checks["cache_kind_matches_run_kind"]:
        report["errors"].append(
            "cache linkage mismatch: cache_file parent kind does not match run_kind"
        )

    expected_payload = _expected_cache_payload(receipt)
    if expected_payload is None:
        checks["cache_key_recomputes"] = False
        report["errors"].append(
            f"cannot recompute cache key for run_kind={run_kind!r}; unsupported"
        )
    else:
        expected_key = make_key(expected_payload)
        report["expected_cache_key"] = expected_key
        checks["cache_key_recomputes"] = expected_key == cache_key
        if expected_key != cache_key:
            report["errors"].append(
                f"cache key mismatch: expected={expected_key} receipt={cache_key}"
            )

    if cache_enabled:
        cache_exists = cache_file.exists() and cache_file.is_file()
        checks["cache_file_exists"] = bool(cache_exists)
        if not cache_exists:
            report["errors"].append(f"cache file missing: {cache_file}")
        else:
            try:
                cache_payload = json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                cache_payload = None
            checks["cache_file_json_object"] = isinstance(cache_payload, dict)
            if not isinstance(cache_payload, dict):
                report["errors"].append(
                    f"cache file is not valid JSON object: {cache_file}"
                )
            else:
                code = cache_payload.get("code")
                checks["cache_has_code"] = isinstance(code, str)
                if not isinstance(code, str):
                    report["errors"].append(
                        "cache provenance missing: cache payload has no string 'code'"
                    )
                else:
                    cache_code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
                    report["cache_code_hash"] = cache_code_hash
                    checks["cache_code_hash_matches_receipt"] = (
                        cache_code_hash == receipt_hash
                    )
                    if cache_code_hash != receipt_hash:
                        report["errors"].append(
                            "cache provenance mismatch: cache code hash does not match receipt hash"
                        )
    else:
        checks["cache_file_exists"] = cache_file.exists() and cache_file.is_file()
        report["warnings"].append(
            "cache disabled in receipt; cache existence/provenance checks are informational"
        )

    if report["errors"]:
        report["status"] = "failed"
    return report

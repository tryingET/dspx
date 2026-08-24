"""Immutable protected candidate snapshot capture for Soomfon custody."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

from dspx.services.soomfon_evaluation_filesystem import (
    SoomfonCustodyError,
    stable_source_bytes,
)


def _json_object(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SoomfonCustodyError(f"protected {label} JSON is invalid") from exc
    if not isinstance(payload, dict):
        raise SoomfonCustodyError(f"protected {label} is not an object")
    return payload


def _capture_runtime_snapshot(
    *, manifest_path: Path, inputs_path: Path, custody: Any
) -> object:
    from dspx.services.soomfon_evaluation_runtime import (
        SoomfonRuntimeSnapshot,
        verified_surface_declarations,
    )

    manifest_raw = stable_source_bytes(
        manifest_path, expected_sha256=custody.expected_manifest_sha256
    )
    manifest = _json_object(manifest_raw, label="manifest")
    inputs_raw = stable_source_bytes(
        inputs_path, expected_sha256=custody.expected_inputs_sha256
    )
    inputs_payload = _json_object(inputs_raw, label="inputs")
    nested_inputs = inputs_payload.get("inputs")
    if not isinstance(nested_inputs, dict) or not nested_inputs:
        raise SoomfonCustodyError("protected candidate inputs are invalid")
    receipt_raw = stable_source_bytes(
        manifest_path.with_name("manifest.json.meta.json"),
        expected_sha256=custody.expected_receipt_sha256,
    )
    receipt_sha256 = hashlib.sha256(receipt_raw).hexdigest()
    sources: dict[str, str] = {}
    module_surfaces: dict[str, Any] = {"module_surfaces": []}
    seen: set[PurePosixPath] = set()
    for declaration in verified_surface_declarations(manifest):
        relative = PurePosixPath(declaration["path"])
        if (
            relative.is_absolute()
            or not relative.parts
            or any(part in {"", ".", ".."} for part in relative.parts)
            or relative in seen
        ):
            raise SoomfonCustodyError("protected candidate surface path is invalid")
        seen.add(relative)
        if relative.name == manifest_path.name:
            continue
        raw = stable_source_bytes(
            manifest_path.parent.joinpath(*relative.parts),
            expected_sha256=declaration["content_hash"],
        )
        if relative.as_posix() in {"program.py", "module.py", "signature.py"}:
            try:
                sources[relative.stem] = raw.decode("utf-8")
            except UnicodeError as exc:
                raise SoomfonCustodyError(
                    "protected candidate source is not UTF-8"
                ) from exc
        elif relative.as_posix() == "module_surfaces.json":
            module_surfaces = _json_object(raw, label="module surfaces")
    if "program" not in sources:
        raise SoomfonCustodyError("protected candidate program source is missing")
    return SoomfonRuntimeSnapshot(
        manifest_path=manifest_path,
        manifest_sha256=custody.expected_manifest_sha256,
        manifest_payload=manifest,
        receipt_sha256=receipt_sha256,
        runtime_inputs={str(key): value for key, value in nested_inputs.items()},
        surface_sources=sources,
        module_surfaces=module_surfaces,
    )

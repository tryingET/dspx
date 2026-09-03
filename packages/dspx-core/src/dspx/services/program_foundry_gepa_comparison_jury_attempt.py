# summary: "Attempt-marker, sidecar path, and exclusive JSON write helpers for the foundry comparison jury."
# read_when:
#   - "Changing comparison-jury sidecar names, attempt payloads, or how jury inputs are hashed."

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any, Mapping

from dspx.services.program_foundry_gepa_comparison_jury_runtime import (
    PROGRAM_FOUNDRY_GEPA_COMPARISON_JURY_ATTEMPT_SCHEMA,
    PROGRAM_FOUNDRY_GEPA_COMPARISON_JURY_SCHEMA,
    ProgramFoundryGepaComparisonJuryError,
)
from dspx.services.program_foundry_gepa_proposal_io import (
    ProgramFoundryGepaProposalError,
    assert_path_descriptor_identity,
    read_regular_bytes,
)

_NON_AUTHORITY = {
    "winner_selection": False,
    "promotion_authority": False,
    "activation_authority": False,
    "governance_authority": False,
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ProgramFoundryGepaComparisonJuryError(
            f"comparison jury value must be canonical JSON: {exc}"
        ) from exc


def _decode_json_object(raw: bytes, *, label: str) -> tuple[dict[str, Any], str]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProgramFoundryGepaComparisonJuryError(
            f"{label} must be valid JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise ProgramFoundryGepaComparisonJuryError(
            f"{label} must contain one JSON object"
        )
    return ({str(key): item for key, item in payload.items()}, sha256_bytes(raw))


def load_json_snapshot(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    return _decode_json_object(read_regular_bytes(path, label=label), label=label)


def load_json_snapshot_at(
    directory_descriptor: int,
    name: str,
    *,
    label: str,
) -> tuple[dict[str, Any], str]:
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=directory_descriptor,
        )
    except OSError as exc:
        raise ProgramFoundryGepaComparisonJuryError(
            f"{label} cannot be opened safely"
        ) from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ProgramFoundryGepaComparisonJuryError(
                f"{label} must be a regular file"
            )
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            raw = stream.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return _decode_json_object(raw, label=label)


def write_json_exclusive(
    path: Path,
    payload: Mapping[str, Any],
    *,
    root_descriptor: int,
) -> str:
    target = path.expanduser().absolute()
    encoded = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if target.parent.name != "gepa-experiment":
        raise ProgramFoundryGepaComparisonJuryError(
            "comparison jury sidecars must stay in the canonical experiment directory"
        )
    experiment_descriptor = os.open(
        "gepa-experiment",
        os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=root_descriptor,
    )
    try:
        assert_path_descriptor_identity(
            target.parent,
            experiment_descriptor,
            label="foundry GEPA experiment directory",
        )
        descriptor = os.open(
            target.name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=experiment_descriptor,
        )
        try:
            with os.fdopen(descriptor, "wb") as stream:
                descriptor = -1
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        os.fsync(experiment_descriptor)
        os.fsync(root_descriptor)
    finally:
        os.close(experiment_descriptor)
    return sha256_bytes(encoded)


def jury_paths(experiment_root: Path) -> dict[str, Path]:
    return {
        "attempt": experiment_root / "comparison-jury-attempt.json",
        "result": experiment_root / "comparison-jury-results.json",
        "receipt": experiment_root / "comparison-jury-receipt.json",
    }


def jury_input_sha256(validated: Mapping[str, Any]) -> dict[Path, str]:
    candidate_manifest = Path(str(validated["candidate_manifest_path"]))
    comparison = Path(str(validated["comparison_path"]))
    paths = (
        candidate_manifest,
        candidate_manifest.parent / "jury.json",
        candidate_manifest.parent / "jury_selection.json",
        candidate_manifest.parent / "jury_rubric.json",
        comparison,
    )
    try:
        snapshots = {
            path: sha256_bytes(read_regular_bytes(path, label=path.name))
            for path in paths
        }
    except ProgramFoundryGepaProposalError as exc:
        # A partial evidence bundle is a closed pre-marker rejection (exit 2),
        # not an indeterminate provider effect.
        raise ProgramFoundryGepaComparisonJuryError(
            f"comparison jury input is missing or unsafe: {exc}"
        ) from exc
    if snapshots[candidate_manifest] != validated["candidate_manifest_sha256"]:
        raise ProgramFoundryGepaComparisonJuryError(
            "candidate manifest changed before comparison jury execution"
        )
    if snapshots[comparison] != validated["comparison_sha256"]:
        raise ProgramFoundryGepaComparisonJuryError(
            "candidate comparison changed before comparison jury execution"
        )
    return snapshots


def _input_bindings(input_sha256: Mapping[Path, str]) -> list[dict[str, str]]:
    return [
        {"path": str(path), "sha256": digest}
        for path, digest in sorted(input_sha256.items(), key=lambda item: str(item[0]))
    ]


def attempt_payload(
    *,
    validated: Mapping[str, Any],
    request: Mapping[str, Any],
    input_sha256: Mapping[Path, str],
) -> dict[str, Any]:
    body = {
        "schema_version": PROGRAM_FOUNDRY_GEPA_COMPARISON_JURY_ATTEMPT_SCHEMA,
        "status": "provider_effect_possible",
        "proposal_id": validated["proposal_id"],
        "consumption_receipt_path": str(validated["receipt_path"]),
        "consumption_receipt_sha256": validated["receipt_sha256"],
        "execution_request": dict(request),
        "jury_input_snapshots": _input_bindings(input_sha256),
        "no_replay_after_marker": True,
        "effect_disposition": "indeterminate_until_comparison_jury_receipt",
        "non_authority": dict(_NON_AUTHORITY),
    }
    return {
        **body,
        "attempt_id": sha256_bytes(canonical_json(body).encode("utf-8")),
    }


def validate_attempt(
    *,
    path: Path,
    validated: Mapping[str, Any],
    request: Mapping[str, Any],
    input_sha256: Mapping[Path, str],
) -> tuple[dict[str, Any], str]:
    attempt, digest = load_json_snapshot(path, label="comparison jury attempt")
    expected = attempt_payload(
        validated=validated,
        request=request,
        input_sha256=input_sha256,
    )
    if attempt != expected:
        raise ProgramFoundryGepaComparisonJuryError(
            "comparison jury attempt or execution request drifted"
        )
    return attempt, digest


def blocked_indeterminate_payload(proposal_id: object) -> dict[str, Any]:
    """Closed no-replay answer once an attempt marker exists without a receipt."""

    return {
        "schema_version": PROGRAM_FOUNDRY_GEPA_COMPARISON_JURY_SCHEMA,
        "status": "blocked_indeterminate",
        "proposal_id": proposal_id,
        "effect_disposition": "one_or_more_provider_juror_calls_may_have_occurred",
        "reused": True,
        "non_authority": dict(_NON_AUTHORITY),
    }


__all__ = [
    "attempt_payload",
    "blocked_indeterminate_payload",
    "canonical_json",
    "jury_input_sha256",
    "jury_paths",
    "load_json_snapshot",
    "load_json_snapshot_at",
    "sha256_bytes",
    "validate_attempt",
    "write_json_exclusive",
]

# summary: "Runs one receipt-bound program-specific jury over a foundry GEPA comparison without transition authority."
# read_when:
#   - "Changing foundry comparison-jury execution, no-replay behavior, or jury receipts."

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from dspx.services.program_foundry_gepa_consumption import (
    ProgramFoundryGepaConsumptionError,
    validate_successful_program_foundry_gepa_consumption_receipt,
)
from dspx.services.program_foundry_gepa_proposal_io import (
    assert_path_descriptor_identity,
    read_regular_bytes,
)
from dspx.services.program_foundry_io import foundry_lock
from dspx.services.program_model_jury_execution import (
    ProgramModelJuryExecutionError,
    build_program_model_jury_execution_result,
)
from dspx.services.program_model_jury_validation import (
    validate_program_model_jury_results_contract,
)

PROGRAM_FOUNDRY_GEPA_COMPARISON_JURY_ATTEMPT_SCHEMA = (
    "dspx-program-foundry-gepa-comparison-jury-attempt-v1"
)
PROGRAM_FOUNDRY_GEPA_COMPARISON_JURY_SCHEMA = (
    "dspx-program-foundry-gepa-comparison-jury-v1"
)


class ProgramFoundryGepaComparisonJuryError(ValueError):
    """Raised when a receipt-bound comparison jury cannot execute safely."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_json(value: object) -> str:
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


def _load_json_snapshot(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    raw = read_regular_bytes(path, label=label)
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
    return ({str(key): item for key, item in payload.items()}, _sha256_bytes(raw))


def _write_json_exclusive(
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
    return _sha256_bytes(encoded)


def _paths(experiment_root: Path) -> dict[str, Path]:
    return {
        "attempt": experiment_root / "comparison-jury-attempt.json",
        "result": experiment_root / "comparison-jury-results.json",
        "receipt": experiment_root / "comparison-jury-receipt.json",
    }


def _execution_request(
    *,
    provider: str,
    adjudicator_id: str,
    adjudicator_kind: str,
    adjudicator_repo: str | None,
    max_jurors: int | None,
) -> dict[str, Any]:
    if not provider.strip():
        raise ProgramFoundryGepaComparisonJuryError(
            "comparison jury requires an explicit provider"
        )
    if not adjudicator_id.strip() or not adjudicator_kind.strip():
        raise ProgramFoundryGepaComparisonJuryError(
            "comparison jury adjudicator id and kind must be non-empty"
        )
    if max_jurors is not None and (isinstance(max_jurors, bool) or max_jurors < 1):
        raise ProgramFoundryGepaComparisonJuryError(
            "comparison jury max_jurors must be at least one"
        )
    return {
        "provider": provider.strip(),
        "adjudicator_id": adjudicator_id.strip(),
        "adjudicator_kind": adjudicator_kind.strip(),
        "adjudicator_repo": (
            adjudicator_repo.strip()
            if adjudicator_repo and adjudicator_repo.strip()
            else None
        ),
        "max_jurors": max_jurors,
    }


def _jury_input_sha256(validated: Mapping[str, Any]) -> dict[Path, str]:
    candidate_manifest = Path(str(validated["candidate_manifest_path"]))
    comparison = Path(str(validated["comparison_path"]))
    paths = (
        candidate_manifest,
        candidate_manifest.parent / "jury.json",
        candidate_manifest.parent / "jury_selection.json",
        candidate_manifest.parent / "jury_rubric.json",
        comparison,
    )
    snapshots = {
        path: _sha256_bytes(read_regular_bytes(path, label=path.name)) for path in paths
    }
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


def _attempt_payload(
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
        "non_authority": {
            "winner_selection": False,
            "promotion_authority": False,
            "activation_authority": False,
            "governance_authority": False,
        },
    }
    return {
        **body,
        "attempt_id": _sha256_bytes(_canonical_json(body).encode("utf-8")),
    }


def _validate_attempt(
    *,
    path: Path,
    validated: Mapping[str, Any],
    request: Mapping[str, Any],
    input_sha256: Mapping[Path, str],
) -> tuple[dict[str, Any], str]:
    attempt, digest = _load_json_snapshot(path, label="comparison jury attempt")
    expected = _attempt_payload(
        validated=validated,
        request=request,
        input_sha256=input_sha256,
    )
    if attempt != expected:
        raise ProgramFoundryGepaComparisonJuryError(
            "comparison jury attempt or execution request drifted"
        )
    return attempt, digest


def _validate_jury_result(
    *,
    result_path: Path,
    validated: Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    result, digest = _load_json_snapshot(
        result_path,
        label="comparison jury results",
    )
    validate_program_model_jury_results_contract(
        result,
        label="foundry GEPA comparison jury results",
        error_type=ProgramFoundryGepaComparisonJuryError,
        valid_manifest_refs={
            Path(str(validated["candidate_manifest_path"])): str(
                validated["candidate_manifest_sha256"]
            )
        },
    )
    evidence = result.get("evidence")
    entries = evidence.get("entries") if isinstance(evidence, Mapping) else None
    comparison_path = str(validated["comparison_path"])
    comparison_hash = str(validated["comparison_sha256"])
    comparison_entries = [
        entry
        for entry in entries or []
        if isinstance(entry, Mapping) and entry.get("path") == comparison_path
    ]
    if (
        len(comparison_entries) != 1
        or comparison_entries[0].get("sha256") != comparison_hash
    ):
        raise ProgramFoundryGepaComparisonJuryError(
            "comparison jury results do not bind the receipt comparison exactly once"
        )
    return result, digest


def _receipt_payload(
    *,
    validated: Mapping[str, Any],
    request: Mapping[str, Any],
    attempt_sha256: str,
    result: Mapping[str, Any],
    result_sha256: str,
    paths: Mapping[str, Path],
) -> dict[str, Any]:
    return {
        "schema_version": PROGRAM_FOUNDRY_GEPA_COMPARISON_JURY_SCHEMA,
        "status": "ok",
        "jury_status": result["status"],
        "proposal_id": validated["proposal_id"],
        "execution_request": dict(request),
        "bindings": {
            "consumption_receipt_path": str(validated["receipt_path"]),
            "consumption_receipt_sha256": validated["receipt_sha256"],
            "execution_receipt_path": str(validated["execution_receipt_path"]),
            "execution_receipt_sha256": validated["execution_receipt_sha256"],
            "source_manifest_path": str(validated["source_manifest_path"]),
            "source_manifest_sha256": validated["source_manifest_sha256"],
            "candidate_manifest_path": str(validated["candidate_manifest_path"]),
            "candidate_manifest_sha256": validated["candidate_manifest_sha256"],
            "comparison_path": str(validated["comparison_path"]),
            "comparison_sha256": validated["comparison_sha256"],
            "attempt_path": str(paths["attempt"]),
            "attempt_sha256": attempt_sha256,
            "jury_results_path": str(paths["result"]),
            "jury_results_sha256": result_sha256,
        },
        "aggregate": result["aggregate"],
        "effect": {
            "program_specific_jury_executed": True,
            "provider_calls_may_have_occurred": True,
            "comparison_mutated": False,
            "candidate_mutated": False,
            "winner_selected": False,
            "promotion_applied": False,
            "activation_applied": False,
            "external_authority_mutated": False,
            "ak_called": False,
        },
        "non_authority": {
            "local_jury_evidence_only": True,
            "winner_selection": False,
            "promotion_authority": False,
            "activation_authority": False,
            "governance_authority": False,
        },
    }


def _validate_existing_receipt(
    *,
    validated: Mapping[str, Any],
    request: Mapping[str, Any],
    input_sha256: Mapping[Path, str],
    paths: Mapping[str, Path],
) -> dict[str, Any]:
    _, attempt_sha256 = _validate_attempt(
        path=paths["attempt"],
        validated=validated,
        request=request,
        input_sha256=input_sha256,
    )
    result, result_sha256 = _validate_jury_result(
        result_path=paths["result"],
        validated=validated,
    )
    expected = _receipt_payload(
        validated=validated,
        request=request,
        attempt_sha256=attempt_sha256,
        result=result,
        result_sha256=result_sha256,
        paths=paths,
    )
    receipt, _ = _load_json_snapshot(paths["receipt"], label="comparison jury receipt")
    if receipt != expected:
        raise ProgramFoundryGepaComparisonJuryError(
            "comparison jury receipt or bound artifacts drifted"
        )
    return {**receipt, "reused": True}


def execute_program_foundry_gepa_comparison_jury(
    *,
    consumption_receipt_path: Path,
    provider: str,
    adjudicator_id: str = "local_foundry_adjudicator",
    adjudicator_kind: str = "local_foundry_adjudicator",
    adjudicator_repo: str | None = None,
    max_jurors: int | None = None,
) -> dict[str, Any]:
    """Execute one program-specific jury against one receipt-bound comparison."""

    receipt_path = consumption_receipt_path.expanduser().absolute()
    root = receipt_path.parent.parent
    request = _execution_request(
        provider=provider,
        adjudicator_id=adjudicator_id,
        adjudicator_kind=adjudicator_kind,
        adjudicator_repo=adjudicator_repo,
        max_jurors=max_jurors,
    )
    with foundry_lock(root) as root_descriptor:
        assert_path_descriptor_identity(root, root_descriptor, label="foundry root")
        try:
            validated = validate_successful_program_foundry_gepa_consumption_receipt(
                receipt_path,
                root_descriptor=root_descriptor,
            )
        except ProgramFoundryGepaConsumptionError as exc:
            raise ProgramFoundryGepaComparisonJuryError(str(exc)) from exc
        experiment_root = Path(str(validated["experiment_root"]))
        input_sha256 = _jury_input_sha256(validated)
        paths = _paths(experiment_root)
        if paths["receipt"].exists():
            return _validate_existing_receipt(
                validated=validated,
                request=request,
                input_sha256=input_sha256,
                paths=paths,
            )
        if paths["receipt"].is_symlink():
            raise ProgramFoundryGepaComparisonJuryError(
                "comparison jury receipt must not be a symlink"
            )
        if paths["attempt"].exists():
            _validate_attempt(
                path=paths["attempt"],
                validated=validated,
                request=request,
                input_sha256=input_sha256,
            )
            return {
                "schema_version": PROGRAM_FOUNDRY_GEPA_COMPARISON_JURY_SCHEMA,
                "status": "blocked_indeterminate",
                "proposal_id": validated["proposal_id"],
                "effect_disposition": "one_or_more_provider_juror_calls_may_have_occurred",
                "reused": True,
                "non_authority": {
                    "winner_selection": False,
                    "promotion_authority": False,
                    "activation_authority": False,
                    "governance_authority": False,
                },
            }
        if paths["attempt"].is_symlink():
            raise ProgramFoundryGepaComparisonJuryError(
                "comparison jury attempt must not be a symlink"
            )
        if paths["result"].exists() or paths["result"].is_symlink():
            raise ProgramFoundryGepaComparisonJuryError(
                "comparison jury results exist without an attempt marker"
            )
        attempt = _attempt_payload(
            validated=validated,
            request=request,
            input_sha256=input_sha256,
        )
        attempt_sha256 = _write_json_exclusive(
            paths["attempt"],
            attempt,
            root_descriptor=root_descriptor,
        )
        try:
            result = build_program_model_jury_execution_result(
                manifest_path=Path(str(validated["candidate_manifest_path"])),
                evidence_paths=[Path(str(validated["comparison_path"]))],
                provider=request["provider"],
                adjudicator_id=str(request["adjudicator_id"]),
                adjudicator_kind=str(request["adjudicator_kind"]),
                adjudicator_repo=request["adjudicator_repo"],
                max_jurors=request["max_jurors"],
                expected_input_sha256=input_sha256,
                include_default_behavior=False,
            )
        except ProgramModelJuryExecutionError as exc:
            raise ProgramFoundryGepaComparisonJuryError(str(exc)) from exc
        _write_json_exclusive(
            paths["result"],
            result,
            root_descriptor=root_descriptor,
        )
        try:
            validated_after = (
                validate_successful_program_foundry_gepa_consumption_receipt(
                    receipt_path,
                    root_descriptor=root_descriptor,
                )
            )
        except ProgramFoundryGepaConsumptionError as exc:
            raise ProgramFoundryGepaComparisonJuryError(str(exc)) from exc
        if validated_after != validated:
            raise ProgramFoundryGepaComparisonJuryError(
                "foundry GEPA comparison lineage changed during jury execution"
            )
        validated_result, result_sha256 = _validate_jury_result(
            result_path=paths["result"],
            validated=validated,
        )
        receipt = _receipt_payload(
            validated=validated,
            request=request,
            attempt_sha256=attempt_sha256,
            result=validated_result,
            result_sha256=result_sha256,
            paths=paths,
        )
        _write_json_exclusive(
            paths["receipt"],
            receipt,
            root_descriptor=root_descriptor,
        )
        return {**receipt, "reused": False}

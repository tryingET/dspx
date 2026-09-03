# summary: "Runs one receipt-bound program-specific jury over a foundry GEPA comparison without transition authority."
# read_when:
#   - "Changing foundry comparison-jury execution, no-replay behavior, or jury receipts."

from __future__ import annotations

import hashlib
import json
import os
import stat
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Mapping

from dspx.services.program_foundry_gepa_consumption import (
    ProgramFoundryGepaConsumptionError,
    validate_successful_program_foundry_gepa_consumption_receipt,
)
from dspx.services.program_foundry_gepa_proposal_io import (
    ProgramFoundryGepaProposalError,
    assert_path_descriptor_identity,
    read_regular_bytes,
)
from dspx.services.program_foundry_io import foundry_lock
from dspx.services.program_foundry_gepa_comparison_model_jury import (
    build_comparison_model_jury_result,
)
from dspx.services.program_foundry_gepa_comparison_jury_preflight import (
    run_task_local_preflight,
    selected_juror_count,
)
from dspx.services.program_foundry_gepa_comparison_jury_result import (
    validate_task_local_jury_result,
)
from dspx.services.program_foundry_gepa_comparison_jury_runtime import (
    COMMON_EXECUTION_REQUEST_KEYS,
    PROGRAM_FOUNDRY_GEPA_COMPARISON_JURY_ATTEMPT_SCHEMA,
    PROGRAM_FOUNDRY_GEPA_COMPARISON_JURY_SCHEMA,
    TASK_LOCAL_EXECUTION_REQUEST_KEYS,
    TASK_LOCAL_PROVIDER_NAME,
    TASK_LOCAL_PROVIDER_NAMES,
    _DSPX_REPO_ROOT,
    ProgramFoundryGepaComparisonJuryError,
    execution_request as _execution_request,
    family_for_provider,
    make_task_local_runtime_binding,
    receipt_payload as _receipt_payload,
    revalidate_execution_request,
    task_local_process_slot,
)
from dspx.services.program_model_jury_provider_runtime import (
    ProgramModelJuryExecutionError,
    _model_jury_process_slot,
)
from dspx.services.program_model_jury_validation import (
    validate_program_model_jury_results_contract,
)


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


def _load_json_snapshot_at(
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
    try:
        snapshots = {
            path: _sha256_bytes(read_regular_bytes(path, label=path.name))
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
    request: Mapping[str, Any],
    attempt_sha256: str,
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
    validate_task_local_jury_result(
        result=result,
        result_path=result_path,
        validated=validated,
        request=request,
        attempt_sha256=attempt_sha256,
    )
    return result, digest


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
        request=request,
        attempt_sha256=attempt_sha256,
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


def validate_successful_program_foundry_gepa_comparison_jury_receipt(
    comparison_jury_receipt_path: Path,
    *,
    root_descriptor: int,
) -> dict[str, Any]:
    """Revalidate a terminal comparison-jury receipt and its complete lineage."""

    receipt_path = comparison_jury_receipt_path.expanduser().absolute()
    if (
        receipt_path.name != "comparison-jury-receipt.json"
        or receipt_path.parent.name != "gepa-experiment"
    ):
        raise ProgramFoundryGepaComparisonJuryError(
            "comparison jury receipt must be canonical gepa-experiment/comparison-jury-receipt.json"
        )
    experiment_root = receipt_path.parent
    root = experiment_root.parent
    assert_path_descriptor_identity(root, root_descriptor, label="foundry root")
    experiment_descriptor = os.open(
        "gepa-experiment",
        os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=root_descriptor,
    )
    try:
        assert_path_descriptor_identity(
            experiment_root,
            experiment_descriptor,
            label="foundry GEPA experiment directory",
        )
        try:
            validated = validate_successful_program_foundry_gepa_consumption_receipt(
                experiment_root / "consumption-receipt.json",
                root_descriptor=root_descriptor,
            )
        except ProgramFoundryGepaConsumptionError as exc:
            raise ProgramFoundryGepaComparisonJuryError(str(exc)) from exc
        input_sha256 = _jury_input_sha256(validated)
        receipt, receipt_sha256 = _load_json_snapshot_at(
            experiment_descriptor,
            "comparison-jury-receipt.json",
            label="comparison jury receipt",
        )
        raw_request = receipt.get("execution_request")
        if not isinstance(raw_request, Mapping):
            raise ProgramFoundryGepaComparisonJuryError(
                "comparison jury receipt execution_request is invalid"
            )
        request = revalidate_execution_request(raw_request)
        paths = _paths(experiment_root)
        validated_receipt = _validate_existing_receipt(
            validated=validated,
            request=request,
            input_sha256=input_sha256,
            paths=paths,
        )
        expected_receipt = {
            key: value for key, value in validated_receipt.items() if key != "reused"
        }
        if receipt != expected_receipt or receipt.get("status") != "ok":
            raise ProgramFoundryGepaComparisonJuryError(
                "comparison jury receipt changed during validation"
            )
        path_jury_result, path_jury_result_sha256 = _validate_jury_result(
            result_path=paths["result"],
            validated=validated,
            request=request,
            attempt_sha256=_sha256_bytes(
                read_regular_bytes(paths["attempt"], label="comparison jury attempt")
            ),
        )
        jury_result, jury_result_sha256 = _load_json_snapshot_at(
            experiment_descriptor,
            "comparison-jury-results.json",
            label="comparison jury results",
        )
        bindings = receipt.get("bindings")
        if not isinstance(bindings, Mapping):
            raise ProgramFoundryGepaComparisonJuryError(
                "comparison jury receipt bindings are required"
            )
        if (
            jury_result != path_jury_result
            or jury_result_sha256 != path_jury_result_sha256
            or jury_result_sha256 != bindings.get("jury_results_sha256")
            or receipt.get("aggregate") != jury_result.get("aggregate")
            or receipt.get("jury_status") != jury_result.get("status")
        ):
            raise ProgramFoundryGepaComparisonJuryError(
                "comparison jury result changed during receipt validation"
            )
        assert_path_descriptor_identity(
            experiment_root,
            experiment_descriptor,
            label="foundry GEPA experiment directory",
        )
        return {
            **validated,
            "jury_receipt": receipt,
            "jury_receipt_path": receipt_path,
            "jury_receipt_sha256": receipt_sha256,
            "jury_result": jury_result,
            "jury_result_path": paths["result"],
            "jury_result_sha256": jury_result_sha256,
            "jury_status": receipt["jury_status"],
            "aggregate": receipt["aggregate"],
        }
    finally:
        os.close(experiment_descriptor)


def execute_program_foundry_gepa_comparison_jury(
    *,
    consumption_receipt_path: Path,
    provider: str,
    adjudicator_id: str = "local_foundry_adjudicator",
    adjudicator_kind: str = "local_foundry_adjudicator",
    adjudicator_repo: str | None = None,
    max_jurors: int | None = None,
    owner_source_root: Path | None = None,
    execution_task_id: int | None = None,
    execution_claimant: str | None = None,
    codex_model: str | None = None,
    reasoning_effort: str | None = None,
    model: str | None = None,
    preflight_only: bool = False,
) -> dict[str, Any]:
    """Execute one program-specific jury against one receipt-bound comparison.

    ``preflight_only`` runs every write-free gate for a task-local provider and
    returns the closed preflight facts without writing an attempt marker.
    """

    receipt_path = consumption_receipt_path.expanduser().absolute()
    root = receipt_path.parent.parent
    request = _execution_request(
        provider=provider,
        adjudicator_id=adjudicator_id,
        adjudicator_kind=adjudicator_kind,
        adjudicator_repo=adjudicator_repo,
        max_jurors=max_jurors,
        owner_source_root=owner_source_root,
        execution_task_id=execution_task_id,
        execution_claimant=execution_claimant,
        codex_model=codex_model,
        reasoning_effort=reasoning_effort,
        model=model,
    )
    with (
        task_local_process_slot(request["provider"]),
        foundry_lock(root) as root_descriptor,
        ExitStack() as exit_stack,
    ):
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
        preflight: dict[str, Any] | None = None
        if family_for_provider(request["provider"]) is not None:
            preflight = run_task_local_preflight(
                request,
                experiment_root=experiment_root,
                expected_juror_count=selected_juror_count(
                    Path(str(validated["candidate_manifest_path"])),
                    max_jurors=request["max_jurors"],
                ),
                repo_root=_DSPX_REPO_ROOT,
            )
        elif preflight_only:
            raise ProgramFoundryGepaComparisonJuryError(
                "preflight-only runs are defined for task-local providers"
            )
        if preflight_only:
            return {"status": "preflight_ok", "preflight": preflight}
        try:
            model_jury_slot = exit_stack.enter_context(_model_jury_process_slot())
        except ProgramModelJuryExecutionError as exc:
            raise ProgramFoundryGepaComparisonJuryError(
                "model jury process slot is unavailable before provider effect"
            ) from exc
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
        provider_runtime_binding = make_task_local_runtime_binding(
            request=request,
            experiment_root=experiment_root,
            attempt_sha256=attempt_sha256,
        )
        try:
            result = build_comparison_model_jury_result(
                model_jury_slot,
                manifest_path=Path(str(validated["candidate_manifest_path"])),
                evidence_paths=[Path(str(validated["comparison_path"]))],
                provider=str(request["provider"]),
                adjudicator_id=str(request["adjudicator_id"]),
                adjudicator_kind=str(request["adjudicator_kind"]),
                adjudicator_repo=request["adjudicator_repo"],
                max_jurors=request["max_jurors"],
                expected_input_sha256=input_sha256,
                provider_runtime_binding=provider_runtime_binding,
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
            request=request,
            attempt_sha256=attempt_sha256,
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
        payload = {**receipt, "reused": False}
        if preflight is not None:
            payload["preflight"] = preflight
        return payload


__all__ = [
    "COMMON_EXECUTION_REQUEST_KEYS",
    "TASK_LOCAL_EXECUTION_REQUEST_KEYS",
    "TASK_LOCAL_PROVIDER_NAME",
    "TASK_LOCAL_PROVIDER_NAMES",
    "ProgramFoundryGepaComparisonJuryError",
    "execute_program_foundry_gepa_comparison_jury",
    "validate_successful_program_foundry_gepa_comparison_jury_receipt",
]

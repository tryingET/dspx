# summary: "Runs one receipt-bound program-specific jury over a foundry GEPA comparison without transition authority."
# read_when:
#   - "Changing foundry comparison-jury execution, no-replay behavior, or jury receipts."

from __future__ import annotations

import os
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Mapping

from dspx.services import (
    program_foundry_gepa_comparison_jury_receipt_validation as receipt_validation,
)
from dspx.services.program_foundry_gepa_comparison_jury_attempt import (
    attempt_payload,
    blocked_indeterminate_payload,
    jury_input_sha256,
    jury_paths,
    load_json_snapshot_at,
    sha256_bytes,
    validate_attempt,
    write_json_exclusive,
)
from dspx.services.program_foundry_gepa_comparison_jury_child import (
    ProgramFoundryGepaComparisonJuryChildError,
    child_environment,
    child_request_payload,
    child_timeout_seconds,
    default_child_argv,
    run_task_local_jury_child,
)
from dspx.services.program_foundry_gepa_comparison_jury_preflight import (
    run_task_local_preflight,
    selected_juror_count,
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
from dspx.services.program_foundry_gepa_comparison_model_jury import (
    build_comparison_model_jury_result,
)
from dspx.services.program_foundry_gepa_consumption import (
    ProgramFoundryGepaConsumptionError,
    validate_successful_program_foundry_gepa_consumption_receipt,
)
from dspx.services.program_foundry_gepa_proposal_io import (
    assert_path_descriptor_identity,
    read_regular_bytes,
)
from dspx.services.program_foundry_io import foundry_lock
from dspx.services.program_model_jury_provider_runtime import (
    ProgramModelJuryExecutionError,
    _model_jury_process_slot,
)

# Argv of the fresh ``-I -B`` child that runs every task-local jury. ``None``
# runs the jury in this process instead; that is a test seam for fixtures that
# patch ``build_comparison_model_jury_result`` here, never a production setting.
_CHILD_ARGV: tuple[str, ...] | None = default_child_argv()


def _run_jury(
    *,
    model_jury_slot: Any,
    request: dict[str, Any],
    validated: dict[str, Any],
    experiment_root: Path,
    attempt_sha256: str,
    input_sha256: dict[Path, str],
    expected_juror_count: int | None,
) -> tuple[dict[str, Any], str | None]:
    """Task-local providers run in a fresh child; generic providers in-process.

    Returns the jury results object and, when the child already classified it
    as rejected by the results contract (``jury_failed``), the rejection text.
    The caller retains the results either way and raises the rejection after
    the write, which is exactly what the in-process path does implicitly by
    writing first and validating second.
    """

    family = family_for_provider(request["provider"])
    if family is not None and _CHILD_ARGV is not None:
        envelope = run_task_local_jury_child(
            _CHILD_ARGV,
            payload=child_request_payload(
                request=request,
                validated=validated,
                experiment_root=experiment_root,
                attempt_sha256=attempt_sha256,
                input_sha256=input_sha256,
            ),
            env=child_environment(family),
            timeout=child_timeout_seconds(expected_juror_count or 0, family),
        )
        if envelope["kind"] == "jury_error":
            error = envelope["error"]
            raise ProgramFoundryGepaComparisonJuryChildError(
                f"failed: {error['type']}: {error['message']}"
            )
        if envelope["kind"] == "jury_failed":
            return envelope["results"], str(envelope["error"]["message"])
        return envelope["results"], None
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
    return result, None


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
        input_sha256 = jury_input_sha256(validated)
        receipt, receipt_sha256 = load_json_snapshot_at(
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
        paths = jury_paths(experiment_root)
        validated_receipt = receipt_validation._validate_existing_receipt(
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
        path_jury_result, path_jury_result_sha256 = (
            receipt_validation._validate_jury_result(
                result_path=paths["result"],
                validated=validated,
                request=request,
                attempt_sha256=sha256_bytes(
                    read_regular_bytes(
                        paths["attempt"], label="comparison jury attempt"
                    )
                ),
            )
        )
        jury_result, jury_result_sha256 = load_json_snapshot_at(
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
        input_sha256 = jury_input_sha256(validated)
        paths = jury_paths(experiment_root)
        if paths["receipt"].exists():
            return receipt_validation._validate_existing_receipt(
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
            validate_attempt(
                path=paths["attempt"],
                validated=validated,
                request=request,
                input_sha256=input_sha256,
            )
            return blocked_indeterminate_payload(validated["proposal_id"])
        if paths["attempt"].is_symlink():
            raise ProgramFoundryGepaComparisonJuryError(
                "comparison jury attempt must not be a symlink"
            )
        if paths["result"].exists() or paths["result"].is_symlink():
            raise ProgramFoundryGepaComparisonJuryError(
                "comparison jury results exist without an attempt marker"
            )
        preflight: dict[str, Any] | None = None
        expected_juror_count: int | None = None
        if family_for_provider(request["provider"]) is not None:
            expected_juror_count = selected_juror_count(
                Path(str(validated["candidate_manifest_path"])),
                max_jurors=request["max_jurors"],
            )
            preflight = run_task_local_preflight(
                request,
                experiment_root=experiment_root,
                expected_juror_count=expected_juror_count,
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
        attempt = attempt_payload(
            validated=validated,
            request=request,
            input_sha256=input_sha256,
        )
        attempt_sha256 = write_json_exclusive(
            paths["attempt"],
            attempt,
            root_descriptor=root_descriptor,
        )
        result, rejection = _run_jury(
            model_jury_slot=model_jury_slot,
            request=request,
            validated=validated,
            experiment_root=experiment_root,
            attempt_sha256=attempt_sha256,
            input_sha256=input_sha256,
            expected_juror_count=expected_juror_count,
        )
        write_json_exclusive(
            paths["result"],
            result,
            root_descriptor=root_descriptor,
        )
        if rejection is not None:
            # Same class and text the in-process validation raises below once
            # the results are on disk; the marker and results stay as evidence.
            raise ProgramFoundryGepaComparisonJuryError(rejection)
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
        validated_result, result_sha256 = receipt_validation._validate_jury_result(
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
        write_json_exclusive(
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
    "PROGRAM_FOUNDRY_GEPA_COMPARISON_JURY_ATTEMPT_SCHEMA",
    "PROGRAM_FOUNDRY_GEPA_COMPARISON_JURY_SCHEMA",
    "TASK_LOCAL_EXECUTION_REQUEST_KEYS",
    "TASK_LOCAL_PROVIDER_NAME",
    "TASK_LOCAL_PROVIDER_NAMES",
    "ProgramFoundryGepaComparisonJuryError",
    "execute_program_foundry_gepa_comparison_jury",
    "validate_successful_program_foundry_gepa_comparison_jury_receipt",
]

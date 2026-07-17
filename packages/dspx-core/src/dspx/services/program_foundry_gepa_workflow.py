# summary: "Composes receipt-owned GEPA continuation stages into one resumable foundry workflow."
# read_when:
#   - "Changing the integrated foundry GEPA, jury, adjudicator, or completion continuation path."

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from dspx.services.artifact_boundary import read_stable_json_artifact
from dspx.services.program_foundry_gepa_adjudicator_completion import (
    ProgramFoundryGepaAdjudicatorCompletionIndeterminateError,
    import_program_foundry_gepa_adjudicator_completion,
)
from dspx.services.program_foundry_gepa_adjudicator_dispatch import (
    ProgramFoundryGepaAdjudicatorDispatchIndeterminateError,
    dispatch_program_foundry_gepa_comparison_adjudicator,
)
from dspx.services.program_foundry_gepa_comparison_jury import (
    execute_program_foundry_gepa_comparison_jury,
)
from dspx.services.program_foundry_gepa_consumption import (
    consume_successful_program_foundry_gepa_receipt,
)
from dspx.services.program_foundry_gepa_execution import (
    execute_reviewed_program_foundry_gepa,
)
from dspx.services.program_foundry_gepa_workflow_contract import (
    ProgramFoundryGepaWorkflowError,
    blocked_result as _blocked_result,
    stage_projection as _stage_projection,
    workflow_result as _workflow_result,
)
from dspx.redaction import sanitize_diagnostic_text


def _present(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _call_effect_stage(
    *,
    name: str,
    call: Callable[[], dict[str, Any]],
    attempt_path: Path,
    receipt_path: Path,
) -> dict[str, Any]:
    """Call a stage once and recover only a newly committed terminal receipt.

    Any attempt without a receipt is returned as blocked. A new receipt after an
    exception is re-entered exactly once so the stage owner can validate and reuse
    it without repeating the protected effect. Other failures are normalized into
    this coordinator's ordinary error boundary.
    """

    receipt_before = _present(receipt_path)
    try:
        return call()
    except Exception as exc:
        attempt_after = _present(attempt_path)
        receipt_after = _present(receipt_path)
        if not receipt_before and receipt_after:
            try:
                return call()
            except Exception as validation_exc:
                return {
                    "status": "blocked_indeterminate",
                    "effect_disposition": "committed_receipt_cannot_be_revalidated",
                    "detail": sanitize_diagnostic_text(
                        str(validation_exc), limit=1_000
                    ),
                    "reused": True,
                }
        if attempt_after and not receipt_after:
            return {
                "status": "blocked_indeterminate",
                "effect_disposition": "indeterminate_no_replay",
                "detail": sanitize_diagnostic_text(str(exc), limit=1_000),
                "reused": True,
            }
        raise ProgramFoundryGepaWorkflowError(f"{name} failed: {exc}") from exc


def _validate_inputs(
    *,
    declared_reviewed: str | None,
    operator_label: str | None,
    jury_provider: str | None,
    registration_paths: Sequence[Path],
    owner_completion_path: Path | None,
    verifier_policy_path: Path | None,
    trusted_policy_sha256: str | None,
    declared_request_id: str | None,
    expected_owner_receipt_id: str | None,
) -> bool:
    review_values = (declared_reviewed, operator_label)
    review_supplied = all(
        value is not None and value.strip() for value in review_values
    )
    if any(value is not None for value in review_values) and not review_supplied:
        raise ProgramFoundryGepaWorkflowError(
            "--declare-gepa-reviewed and --operator-label must be supplied together"
        )
    completion_values = (
        owner_completion_path,
        verifier_policy_path,
        trusted_policy_sha256,
        declared_request_id,
        expected_owner_receipt_id,
    )
    completion_supplied = all(
        value is not None and (not isinstance(value, str) or bool(value.strip()))
        for value in completion_values
    )
    if (
        any(value is not None for value in completion_values)
        and not completion_supplied
    ):
        raise ProgramFoundryGepaWorkflowError(
            "completion import requires completion, verifier policy, trusted policy digest, "
            "declared request ID, and declared owner receipt ID"
        )
    continuation_inputs = bool(
        jury_provider or registration_paths or completion_supplied
    )
    if continuation_inputs and not review_supplied:
        raise ProgramFoundryGepaWorkflowError(
            "an explicit GEPA review declaration is required for continuation options"
        )
    if registration_paths and not jury_provider:
        raise ProgramFoundryGepaWorkflowError(
            "adjudicator registrations require an explicit jury provider"
        )
    if completion_supplied and not jury_provider:
        raise ProgramFoundryGepaWorkflowError(
            "completion import requires an explicit jury provider"
        )
    if completion_supplied and not registration_paths:
        raise ProgramFoundryGepaWorkflowError(
            "completion import requires the exact external adjudicator registration sources"
        )
    return bool(review_supplied)


def run_program_foundry_gepa_workflow(
    *,
    proposal_path: Path,
    expected_proposal_id: str,
    declared_reviewed: str | None = None,
    operator_label: str | None = None,
    jury_provider: str | None = None,
    jury_adjudicator_id: str = "local_foundry_adjudicator",
    jury_adjudicator_kind: str = "local_foundry_adjudicator",
    jury_adjudicator_repo: str | None = None,
    jury_max_jurors: int | None = None,
    registration_paths: Sequence[Path] = (),
    include_builtin_fallback: bool = True,
    owner_completion_path: Path | None = None,
    verifier_policy_path: Path | None = None,
    trusted_policy_sha256: str | None = None,
    declared_request_id: str | None = None,
    expected_owner_receipt_id: str | None = None,
) -> dict[str, Any]:
    """Safely continue one foundry proposal through its receipt-owned local stages."""

    proposal_path = proposal_path.expanduser().absolute()
    if proposal_path.name != "gepa_experiment_proposal.json":
        raise ProgramFoundryGepaWorkflowError(
            "foundry continuation requires canonical gepa_experiment_proposal.json"
        )
    artifact = read_stable_json_artifact(
        proposal_path,
        label="foundry GEPA proposal",
        error_type=ProgramFoundryGepaWorkflowError,
    )
    proposal_id = artifact.payload.get("proposal_id")
    if (
        not isinstance(proposal_id, str)
        or not expected_proposal_id
        or proposal_id != expected_proposal_id
    ):
        raise ProgramFoundryGepaWorkflowError(
            "foundry GEPA proposal_id does not match the current foundry invocation"
        )
    review_supplied = _validate_inputs(
        declared_reviewed=declared_reviewed,
        operator_label=operator_label,
        jury_provider=jury_provider,
        registration_paths=registration_paths,
        owner_completion_path=owner_completion_path,
        verifier_policy_path=verifier_policy_path,
        trusted_policy_sha256=trusted_policy_sha256,
        declared_request_id=declared_request_id,
        expected_owner_receipt_id=expected_owner_receipt_id,
    )
    root = proposal_path.parent
    experiment = root / "gepa-experiment"
    stages: dict[str, Any] = {}
    if not review_supplied:
        return _workflow_result(
            root=root,
            proposal_path=proposal_path,
            proposal_id=proposal_id,
            status="waiting_gepa_review",
            disposition="explicit_review_declaration_required",
            stages=stages,
        )

    execution_receipt = experiment / "execution-receipt.json"
    execution = _call_effect_stage(
        name="GEPA execution",
        call=lambda: execute_reviewed_program_foundry_gepa(
            proposal_path=proposal_path,
            declared_reviewed=str(declared_reviewed),
            operator_label=str(operator_label),
        ),
        attempt_path=experiment / "attempt.json",
        receipt_path=execution_receipt,
    )
    stages["gepa_execution"] = _stage_projection(
        execution, artifact_path=execution_receipt
    )
    if execution.get("status") == "blocked_indeterminate":
        return _blocked_result(
            root=root,
            proposal_path=proposal_path,
            proposal_id=proposal_id,
            stages=stages,
            blocked_stage="gepa_execution",
            detail=str(execution.get("detail") or execution.get("effect_disposition")),
        )
    if execution.get("status") == "degraded":
        return _workflow_result(
            root=root,
            proposal_path=proposal_path,
            proposal_id=proposal_id,
            status="require_review",
            disposition="gepa_execution_degraded",
            stages=stages,
        )
    if execution.get("status") != "ok":
        raise ProgramFoundryGepaWorkflowError(
            f"unsupported GEPA execution status: {execution.get('status')}"
        )

    consumption_receipt = experiment / "consumption-receipt.json"
    consumption = _call_effect_stage(
        name="GEPA candidate consumption",
        call=lambda: consume_successful_program_foundry_gepa_receipt(
            execution_receipt_path=execution_receipt
        ),
        attempt_path=experiment / "consumption-attempt.json",
        receipt_path=consumption_receipt,
    )
    stages["candidate_consumption"] = _stage_projection(
        consumption, artifact_path=consumption_receipt
    )
    if consumption.get("status") == "blocked_indeterminate":
        return _blocked_result(
            root=root,
            proposal_path=proposal_path,
            proposal_id=proposal_id,
            stages=stages,
            blocked_stage="candidate_consumption",
            detail=str(
                consumption.get("detail") or consumption.get("effect_disposition")
            ),
        )
    if consumption.get("status") == "degraded":
        return _workflow_result(
            root=root,
            proposal_path=proposal_path,
            proposal_id=proposal_id,
            status="require_review",
            disposition="candidate_comparison_degraded",
            stages=stages,
        )
    if consumption.get("status") != "ok":
        raise ProgramFoundryGepaWorkflowError(
            f"unsupported GEPA consumption status: {consumption.get('status')}"
        )
    if jury_provider is None:
        return _workflow_result(
            root=root,
            proposal_path=proposal_path,
            proposal_id=proposal_id,
            status="waiting_jury_provider",
            disposition="explicit_jury_provider_required",
            stages=stages,
        )

    jury_receipt = experiment / "comparison-jury-receipt.json"
    jury = _call_effect_stage(
        name="comparison jury",
        call=lambda: execute_program_foundry_gepa_comparison_jury(
            consumption_receipt_path=consumption_receipt,
            provider=jury_provider,
            adjudicator_id=jury_adjudicator_id,
            adjudicator_kind=jury_adjudicator_kind,
            adjudicator_repo=jury_adjudicator_repo,
            max_jurors=jury_max_jurors,
        ),
        attempt_path=experiment / "comparison-jury-attempt.json",
        receipt_path=jury_receipt,
    )
    stages["comparison_jury"] = _stage_projection(jury, artifact_path=jury_receipt)
    if jury.get("status") == "blocked_indeterminate":
        return _blocked_result(
            root=root,
            proposal_path=proposal_path,
            proposal_id=proposal_id,
            stages=stages,
            blocked_stage="comparison_jury",
            detail=str(jury.get("detail") or jury.get("effect_disposition")),
        )

    try:
        dispatch = dispatch_program_foundry_gepa_comparison_adjudicator(
            comparison_jury_receipt_path=jury_receipt,
            registration_paths=registration_paths,
            include_builtin_fallback=include_builtin_fallback,
        )
    except ProgramFoundryGepaAdjudicatorDispatchIndeterminateError as exc:
        stages["adjudicator_dispatch"] = {
            "status": "blocked_indeterminate",
            "effect_disposition": "request_or_deterministic_result_may_have_committed",
        }
        return _blocked_result(
            root=root,
            proposal_path=proposal_path,
            proposal_id=proposal_id,
            stages=stages,
            blocked_stage="adjudicator_dispatch",
            detail=str(exc),
        )
    except Exception as exc:
        raise ProgramFoundryGepaWorkflowError(
            f"adjudicator dispatch failed: {exc}"
        ) from exc
    request_path = experiment / "comparison-adjudicator-request.json"
    stages["adjudicator_dispatch"] = _stage_projection(
        dispatch, artifact_path=request_path
    )
    dispatch_status = str(dispatch.get("status"))
    if dispatch_status == "require_review":
        return _workflow_result(
            root=root,
            proposal_path=proposal_path,
            proposal_id=proposal_id,
            status="require_review",
            disposition=str(dispatch.get("disposition") or "require_review"),
            stages=stages,
        )

    completion_supplied = owner_completion_path is not None
    if dispatch_status == "pending" and not completion_supplied:
        return _workflow_result(
            root=root,
            proposal_path=proposal_path,
            proposal_id=proposal_id,
            status="waiting_external_adjudicator",
            disposition="pending",
            stages=stages,
        )
    if dispatch_status == "completed":
        if completion_supplied:
            raise ProgramFoundryGepaWorkflowError(
                "owner completion cannot replace a completed deterministic adjudication"
            )
        return _workflow_result(
            root=root,
            proposal_path=proposal_path,
            proposal_id=proposal_id,
            status="completed_local_disposition",
            disposition=str(dispatch.get("disposition")),
            stages=stages,
        )
    if dispatch_status != "pending":
        raise ProgramFoundryGepaWorkflowError(
            f"unsupported adjudicator dispatch status: {dispatch_status}"
        )

    assert owner_completion_path is not None
    assert verifier_policy_path is not None
    assert trusted_policy_sha256 is not None
    assert declared_request_id is not None
    assert expected_owner_receipt_id is not None
    try:
        completion = import_program_foundry_gepa_adjudicator_completion(
            request_path=request_path,
            registration_paths=registration_paths,
            owner_completion_path=owner_completion_path,
            verifier_policy_path=verifier_policy_path,
            trusted_policy_sha256=trusted_policy_sha256,
            declared_request_id=declared_request_id,
            expected_owner_receipt_id=expected_owner_receipt_id,
        )
    except ProgramFoundryGepaAdjudicatorCompletionIndeterminateError as exc:
        stages["adjudicator_completion"] = {
            "status": "blocked_indeterminate",
            "effect_disposition": "terminal_completion_may_have_committed",
        }
        return _blocked_result(
            root=root,
            proposal_path=proposal_path,
            proposal_id=proposal_id,
            stages=stages,
            blocked_stage="adjudicator_completion",
            detail=str(exc),
        )
    except Exception as exc:
        raise ProgramFoundryGepaWorkflowError(
            f"adjudicator completion import failed: {exc}"
        ) from exc
    stages["adjudicator_completion"] = _stage_projection(
        completion,
        artifact_path=experiment / "comparison-adjudicator-completion.json",
    )
    return _workflow_result(
        root=root,
        proposal_path=proposal_path,
        proposal_id=proposal_id,
        status="completed_local_disposition",
        disposition=str(completion.get("disposition")),
        stages=stages,
    )

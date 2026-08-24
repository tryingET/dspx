# summary: "Independent Gate-5 retained result and operation-count rederivation."
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal, cast

from dspx.services.program_oracle_semantic_artifacts_v11 import (
    ConsumedAttempt,
    load_case_terminal_markers,
    load_result_fragments,
    require_consumed_attempt,
)
from dspx.services.program_oracle_semantic_gate4_contract_v11 import SemanticV11Error
from dspx.services.program_oracle_semantic_gate5_journal_v11 import (
    expected_reservation,
    inspect_journal,
)
from dspx.services.program_oracle_semantic_gate5_semantics_v11 import (
    load_verifier_cases,
    semantic_request_sha256,
    validate_retained_semantic_result,
)
from dspx.services.provider_outcome_receipt_contract import (
    ReceiptProjection,
    SemanticOutcome,
)
from dspx.services.provider_outcome_receipt_identity import VerifiedOwnerArtifact

_RESULT_SCHEMA = "dspx-oracle-semantic-v11-result-v1"
_SETUP_STAGES = {
    "runtime_import",
    "runtime_origin",
    "owner_api",
    "owner_verification",
    "case_load",
    "request_normalization",
    "reservation",
    "endpoint",
    "adapter_construction",
    "case_custody",
    "mark_generate_entered",
    "adapter_call",
    "post_return_projection",
    "result_fragment",
}
CorpusDisposition = Literal["effect_indeterminate", "error", "failed", "passed"]


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise SemanticV11Error("Gate-5 value is not canonical JSON") from exc


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _aggregate(cases: list[dict[str, Any]]) -> CorpusDisposition:
    values = [case["provider_outcome"]["empirical_disposition"] for case in cases]
    if not values or "effect_indeterminate" in values:
        return "effect_indeterminate"
    if any(value in {"error", "not_evaluated"} for value in values):
        return "error"
    if "failed" in values:
        return "failed"
    if (
        tuple(case["case_id"] for case in cases)
        != (
            "authority-boundary",
            "causal-calibration",
            "review-only-transition",
            "provenance-drift",
        )
        or len({case["observed_model"] for case in cases}) != 1
    ):
        return "error"
    return "passed"


def _semantic_error(case_id: str) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "outcome": "semantic_error",
        "analysis": None,
        "score": None,
        "analysis_sha256": None,
    }


def _pre_generate_fragment(
    attempt: ConsumedAttempt, case: Any, reservation: Any, stage: str
) -> dict[str, Any]:
    semantic = _semantic_error(case.case_id)
    provider = ReceiptProjection(
        provider_outcome_receipt="rejected",
        request_acknowledged=None,
        external_effect_possible=False,
        producer_terminal=None,
        empirical_disposition="error",
        reason=f"post_entry_{stage}_failed_before_provider_effect",
    ).payload()
    return {
        "schema_version": _RESULT_SCHEMA,
        "artifact_kind": "case_result_fragment",
        "case_phase": "pre_generate_terminal",
        "live_task_id": attempt.binding.live_task_id,
        "case_id": case.case_id,
        "case_ordinal": case.case_ordinal,
        "semantic_request_sha256": reservation.semantic_request_sha256,
        "reservation_id": reservation.reservation_id,
        "reservation_sha256": _sha(_canonical(reservation.payload())),
        "journal_present": False,
        "dspx_generate_entered": False,
        "invocation_admitted": False,
        "effect_capable_delegations": 0,
        "clean_terminal_order_proven": False,
        "terminal_event_sha256": None,
        "semantic_result": semantic,
        "semantic_result_sha256": _sha(_canonical(semantic)),
        "observed_model": None,
        "provider_outcome": provider,
        "fixture_only": False,
        "v11_authorized": True,
        "live_execution_authorized": True,
    }


def _case_terminal_marker(
    attempt: ConsumedAttempt, case: Any, fragment: dict[str, Any], stage: str
) -> dict[str, Any]:
    if stage not in {"post_return_projection", "result_fragment"}:
        raise SemanticV11Error("Gate-5 case terminal stage drift")
    return {
        "schema_version": _RESULT_SCHEMA,
        "artifact_kind": "case_terminal_marker",
        "live_task_id": attempt.binding.live_task_id,
        "case_id": case.case_id,
        "case_ordinal": case.case_ordinal,
        "stage": stage,
        "case_result_fragment_sha256": _sha(_canonical(fragment)),
        "external_effect_possible": True,
        "empirical_disposition": "error",
        "reason": f"post_entry_{stage}_failed_after_case_terminal",
        "fixture_only": False,
        "v11_authorized": True,
        "live_execution_authorized": True,
    }


def independently_rederive_result(
    *, repo_root: Path, attempt: ConsumedAttempt, artifact: VerifiedOwnerArtifact
) -> dict[str, Any]:
    """Local request, semantic, marker, count, and result rederivation."""

    attempt = require_consumed_attempt(attempt)
    cases = load_verifier_cases(repo_root)
    fragments = load_result_fragments(attempt)
    markers = load_case_terminal_markers(attempt)
    derived_cases: list[dict[str, Any]] = []
    if 0 in fragments:
        fragment = fragments[0]
        stage = fragment.get("setup_stage")
        expected_setup = {
            "schema_version": _RESULT_SCHEMA,
            "artifact_kind": "setup_result_fragment",
            "live_task_id": attempt.binding.live_task_id,
            "setup_stage": stage,
            "external_effect_possible": False,
            "empirical_disposition": "error",
            "reason": f"post_entry_{stage}_failed_before_provider_effect",
            "dspx_generate_entered": False,
            "invocation_admitted": False,
            "effect_capable_delegations": 0,
            "fixture_only": False,
            "v11_authorized": True,
            "live_execution_authorized": True,
        }
        if (
            set(fragments) != {0}
            or stage not in _SETUP_STAGES
            or fragment != expected_setup
        ):
            raise SemanticV11Error("Gate-5 setup fragment drift")
        disposition: CorpusDisposition = "error"
        owner_for_result: VerifiedOwnerArtifact | None = None
    else:
        owner_for_result = artifact
        expected_ordinals: set[int] = set()
        for case in cases:
            fragment = fragments.get(case.case_ordinal)
            if fragment is None:
                break
            expected_ordinals.add(case.case_ordinal)
            semantic = validate_retained_semantic_result(
                case, fragment.get("semantic_result")
            )
            request_sha = semantic_request_sha256(case)
            reservation = expected_reservation(attempt, case, request_sha, artifact)
            if fragment.get("case_phase") == "pre_generate_terminal":
                provider = fragment.get("provider_outcome")
                reason = provider.get("reason") if isinstance(provider, dict) else None
                prefix, suffix = "post_entry_", "_failed_before_provider_effect"
                if (
                    not isinstance(reason, str)
                    or not reason.startswith(prefix)
                    or not reason.endswith(suffix)
                ):
                    raise SemanticV11Error("Gate-5 pre-generate reason drift")
                stage = reason[len(prefix) : -len(suffix)]
                if stage not in _SETUP_STAGES or fragment != _pre_generate_fragment(
                    attempt, case, reservation, stage
                ):
                    raise SemanticV11Error(
                        "Gate-5 pre-generate case reconstruction drift"
                    )
                derived_cases.append(
                    {
                        "case_id": case.case_id,
                        "case_ordinal": case.case_ordinal,
                        "semantic_request_sha256": request_sha,
                        "reservation_sha256": fragment["reservation_sha256"],
                        "terminal_event_sha256": None,
                        "semantic_result_sha256": fragment["semantic_result_sha256"],
                        "semantic_outcome": "semantic_error",
                        "provider_outcome": fragment["provider_outcome"],
                        "observed_model": None,
                        "dspx_generate_entered": False,
                        "invocation_admitted": False,
                        "effect_capable_delegations": 0,
                        "receipt_journal": False,
                        "clean_terminal_order_proven": False,
                    }
                )
                break
            journal_root = (
                attempt.attempt_root
                / "provider-outcomes"
                / f"{case.case_ordinal:02d}-{case.case_id}"
            )
            inspection = inspect_journal(
                journal_root,
                expected=reservation,
                artifact=artifact,
                semantic_outcome=cast(SemanticOutcome, semantic["outcome"]),
            )
            retained_model = fragment.get("observed_model")
            provider = inspection["provider_outcome"]
            if (
                provider["producer_terminal"] != "provider_response_completed"
                or inspection["observed_model"] is None
            ):
                semantic = _semantic_error(case.case_id)
                retained_model = None
            elif retained_model != inspection["observed_model"]:
                semantic = _semantic_error(case.case_id)
                retained_model = inspection["observed_model"]
                provider = ReceiptProjection(
                    "accepted",
                    True,
                    True,
                    "provider_response_completed",
                    "error",
                    "attributable_completion_semantic_error",
                ).payload()
            expected_fragment = {
                "schema_version": _RESULT_SCHEMA,
                "artifact_kind": "case_result_fragment",
                "case_phase": "generate_call_terminal",
                "live_task_id": attempt.binding.live_task_id,
                "case_id": case.case_id,
                "case_ordinal": case.case_ordinal,
                "semantic_request_sha256": request_sha,
                "reservation_id": reservation.reservation_id,
                "reservation_sha256": inspection["reservation_sha256"],
                "journal_present": inspection["journal_present"],
                "dspx_generate_entered": True,
                "invocation_admitted": inspection["invocation_admitted"],
                "effect_capable_delegations": inspection["effect_capable_delegations"],
                "clean_terminal_order_proven": inspection[
                    "clean_terminal_order_proven"
                ],
                "terminal_event_sha256": inspection["terminal_event_sha256"],
                "semantic_result": semantic,
                "semantic_result_sha256": _sha(_canonical(semantic)),
                "observed_model": retained_model,
                "provider_outcome": provider,
                "fixture_only": False,
                "v11_authorized": True,
                "live_execution_authorized": True,
            }
            if fragment != expected_fragment:
                raise SemanticV11Error("Gate-5 case/result reconstruction drift")
            marker = markers.get(case.case_ordinal)
            if marker is not None:
                stage = marker.get("stage")
                if not isinstance(stage, str) or marker != _case_terminal_marker(
                    attempt, case, fragment, stage
                ):
                    raise SemanticV11Error("Gate-5 case terminal marker drift")
                if provider["empirical_disposition"] != "effect_indeterminate":
                    provider = ReceiptProjection(
                        "accepted",
                        True,
                        True,
                        provider["producer_terminal"],
                        "error",
                        f"post_entry_{stage}_failed_after_case_terminal",
                    ).payload()
            derived_cases.append(
                {
                    "case_id": case.case_id,
                    "case_ordinal": case.case_ordinal,
                    "semantic_request_sha256": request_sha,
                    "reservation_sha256": inspection["reservation_sha256"],
                    "terminal_event_sha256": inspection["terminal_event_sha256"],
                    "semantic_result_sha256": expected_fragment[
                        "semantic_result_sha256"
                    ],
                    "semantic_outcome": semantic["outcome"],
                    "provider_outcome": provider,
                    "observed_model": retained_model,
                    "dspx_generate_entered": True,
                    "invocation_admitted": inspection["invocation_admitted"],
                    "effect_capable_delegations": inspection[
                        "effect_capable_delegations"
                    ],
                    "receipt_journal": inspection["journal_present"],
                    "clean_terminal_order_proven": inspection[
                        "clean_terminal_order_proven"
                    ],
                }
            )
            if provider["empirical_disposition"] != "passed":
                break
        if set(markers) - expected_ordinals:
            raise SemanticV11Error("Gate-5 terminal-marker ordinal drift")
        if set(fragments) != expected_ordinals:
            raise SemanticV11Error("Gate-5 stop-policy reconstruction drift")
        disposition = _aggregate(derived_cases)
    ledger = attempt.ledger
    admitted = sum(bool(item["invocation_admitted"]) for item in derived_cases)
    delegations = sum(item["effect_capable_delegations"] for item in derived_cases)
    journals = sum(bool(item["receipt_journal"]) for item in derived_cases)
    models = {
        item["observed_model"] for item in derived_cases if item["observed_model"]
    }
    return {
        "schema_version": _RESULT_SCHEMA,
        "artifact_kind": "evaluation_result",
        "live_task_id": attempt.binding.live_task_id,
        "task_binding": attempt.binding.payload(),
        "ledger_sha256": attempt.ledger_sha256,
        "root_binding_sha256": ledger["root_binding_sha256"],
        "candidate_commit": ledger["candidate_commit"],
        "candidate_tree": ledger["candidate_tree"],
        "candidate_source_manifest_sha256": ledger["candidate_source_manifest_sha256"],
        "contract_sha256": ledger["contract_sha256"],
        "candidate_review_sha256": ledger["candidate_review_sha256"],
        "live_gate_sha256": ledger["live_gate_sha256"],
        "authority_snapshot_sha256": ledger["authority_snapshot_sha256"],
        "provider_owner_source_identity_sha256": _sha(
            _canonical(owner_for_result.source_identity)
        )
        if owner_for_result
        else None,
        "dependency_identity_sha256": _sha(
            _canonical(owner_for_result.dependency_identity)
        )
        if owner_for_result
        else None,
        "artifact_integrity_review": "not_evaluated",
        "empirical_gate": disposition,
        "cases": derived_cases,
        "operation_counts": {
            "corpus_processes": 1,
            "reached_requests": len(derived_cases),
            "admitted_invocations": admitted,
            "dspx_generate_calls": sum(
                bool(item["dspx_generate_entered"]) for item in derived_cases
            ),
            "effect_capable_delegations": delegations,
            "receipt_journals": journals,
            "separate_health_probes": 0,
            "dspx_managed_retries": 0,
            "fallback_routes": 0,
            "provider_transport_calls": "not_proven",
        },
        "observed_model": next(iter(models)) if len(models) == 1 else None,
        "fixture_only": False,
        "v11_authorized": True,
        "live_execution_authorized": True,
    }

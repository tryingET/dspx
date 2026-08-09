# summary: "Disk-rederived no-replace evaluation-result custody for semantic v11."
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from dspx.services.program_oracle_semantic_artifacts_v11 import (
    CASE_CUSTODY_SCHEMA,
    RESULT_NAME,
    RESULT_SCHEMA,
    ConsumedAttempt,
    _load_terminal_preserving_journal,
    _read_private_json,
    load_case_custody,
    load_pre_effect_setup_terminal,
    validate_retained_semantic_result,
    write_exclusive,
)
from dspx.services.program_oracle_semantic_contract_v11 import (
    CASE_ORDER,
    BoundContractCase,
    SemanticV11Error,
    canonical,
    semantic_request_sha256,
    sha256,
)
from dspx.services.program_oracle_semantic_evaluation_v11 import (
    CorpusDisposition,
    normalized_semantic_request,
)
from dspx.services.program_oracle_semantic_gate4_contract_v11 import (
    EXPECTED_ENDPOINT_ORIGIN_SHA256,
)
from dspx.services.program_oracle_semantic_identity_v11 import (
    REQUESTED_ROUTE,
    RESOLVED_ROUTE,
    logical_request_id,
    process_id,
    transport_gate_id,
)
from dspx.services.provider_outcome_receipt_contract import (
    ProviderOutcomeConsumerError,
    ReceiptProjection,
    ReceiptReservation,
    SemanticOutcome,
)
from dspx.services.provider_outcome_receipt_identity import VerifiedOwnerArtifact
from dspx.services.provider_outcome_receipt_journal import ReceiptJournal
from dspx.services.provider_outcome_receipt_reducer import (
    reduce_verified_chain,
    verify_receipt_chain,
)

_TERMINAL_KEYS = {
    "schema_version",
    "kind",
    "live_task_id",
    "case_id",
    "case_ordinal",
    "semantic_outcome",
    "semantic_result",
    "semantic_result_sha256",
    "observed_model",
    "provider_outcome_receipt",
    "request_acknowledged",
    "external_effect_possible",
    "producer_terminal",
    "empirical_disposition",
    "reason",
}


def _reservation_from_root(
    root: Path, artifact: VerifiedOwnerArtifact
) -> ReceiptReservation:
    wrapper, _ = _read_private_json(root / "reservation.json", "reservation")
    payload = wrapper.get("reservation")
    if not isinstance(payload, Mapping):
        raise SemanticV11Error("retained reservation missing")
    reservation = dict(payload)
    if (
        reservation.pop("schema_version", None)
        != "dspx-provider-outcome-reservation-v1"
    ):
        raise SemanticV11Error("retained reservation schema drift")
    try:
        value = ReceiptReservation(**reservation)
        if value.payload() != payload:
            raise ProviderOutcomeConsumerError("reservation_payload_drift")
    except (TypeError, ProviderOutcomeConsumerError) as exc:
        raise SemanticV11Error("retained reservation invalid") from exc
    if (
        value.source_identity != artifact.source_identity
        or value.dependency_identity != artifact.dependency_identity
    ):
        raise SemanticV11Error("retained reservation owner identity drift")
    return value


def _reduced_projection(
    journal: ReceiptJournal, semantic_outcome: SemanticOutcome
) -> tuple[ReceiptProjection, str | None]:
    try:
        retained = _load_terminal_preserving_journal(journal)
        chain = verify_receipt_chain(retained)
        terminal_model = retained.events[-1].event.observed_model
        if chain.terminal == "provider_response_completed" and (
            not isinstance(terminal_model, str)
            or not terminal_model
            or len(terminal_model.encode("utf-8")) > 128
            or any(ord(char) < 32 or ord(char) == 127 for char in terminal_model)
        ):
            semantic_outcome = "semantic_error"
        elif chain.terminal != "provider_response_completed":
            terminal_model = None
        reduced = reduce_verified_chain(chain, semantic_outcome=semantic_outcome)
        projection = ReceiptProjection(
            provider_outcome_receipt="accepted",
            request_acknowledged=reduced.request_acknowledged,
            external_effect_possible=reduced.external_effect_possible,
            producer_terminal=reduced.terminal,
            empirical_disposition=reduced.empirical_disposition,
            reason=reduced.reason,
        )
    except ProviderOutcomeConsumerError as exc:
        terminal_model = None
        projection = ReceiptProjection(
            provider_outcome_receipt="rejected",
            request_acknowledged=None,
            external_effect_possible=exc.effect_possible,
            producer_terminal=None,
            empirical_disposition=(
                "effect_indeterminate" if exc.effect_possible else "error"
            ),
            reason=exc.reason,
        )
    return projection, terminal_model


def _expected_reservation(
    attempt: ConsumedAttempt,
    case: BoundContractCase,
    request_digest: str,
    artifact: VerifiedOwnerArtifact,
) -> ReceiptReservation:
    logical = logical_request_id(
        attempt.binding,
        contract_sha256=case.contract_sha256,
        ledger_sha256=attempt.ledger_sha256,
        case_id=case.case_id,
        case_ordinal=case.case_ordinal,
    )
    return ReceiptReservation(
        consumer_task_id=attempt.binding.live_task_id,
        ledger_sha256=attempt.ledger_sha256,
        process_id=process_id(attempt),
        case_id=case.case_id,
        logical_request_id=logical,
        transport_gate_id=transport_gate_id(logical),
        semantic_request_sha256=request_digest,
        contract_sha256=case.contract_sha256,
        mode="sync",
        requested_route=REQUESTED_ROUTE,
        resolved_route=RESOLVED_ROUTE,
        endpoint_origin_sha256=EXPECTED_ENDPOINT_ORIGIN_SHA256,
        source_identity=artifact.source_identity,
        dependency_identity=artifact.dependency_identity,
    )


def _derive_pre_effect_case(
    attempt: ConsumedAttempt,
    case: BoundContractCase,
    reserved: Mapping[str, Any],
    terminal: Mapping[str, Any],
    artifact: VerifiedOwnerArtifact,
) -> dict[str, Any]:
    semantic = validate_retained_semantic_result(case, terminal.get("semantic_result"))
    expected_request = normalized_semantic_request(case.materialized_request())
    request_digest = semantic_request_sha256(expected_request)
    expected_reservation = _expected_reservation(
        attempt, case, request_digest, artifact
    )
    expected_reserved = {
        "schema_version": CASE_CUSTODY_SCHEMA,
        "kind": "reserved",
        "live_task_id": attempt.binding.live_task_id,
        "case_id": case.case_id,
        "case_ordinal": case.case_ordinal,
        "logical_request_id": expected_reservation.logical_request_id,
        "semantic_request_sha256": request_digest,
        "reservation_sha256": sha256(canonical(expected_reservation.payload())),
    }
    expected_facts = {
        "provider_outcome_receipt": "rejected",
        "request_acknowledged": None,
        "external_effect_possible": False,
        "producer_terminal": None,
        "empirical_disposition": "error",
        "reason": "receipt_preparation_failed_before_effect",
    }
    if (
        semantic.get("outcome") != "semantic_error"
        or dict(reserved) != expected_reserved
        or terminal.get("semantic_outcome") != "semantic_error"
        or terminal.get("observed_model") is not None
        or any(terminal.get(key) != item for key, item in expected_facts.items())
        or reserved.get("semantic_request_sha256") != request_digest
    ):
        raise SemanticV11Error("retained pre-effect case derivation drift")
    root = (
        attempt.attempt_root
        / "provider-outcomes"
        / f"{case.case_ordinal:02d}-{case.case_id}"
    )
    journal_count = 0
    if root.exists() or root.is_symlink():
        journal_count = 1
        try:
            members = {path.name: path for path in root.iterdir()}
            event_names = list((root / "events").iterdir())
        except OSError as exc:
            raise SemanticV11Error("pre-effect journal state invalid") from exc
        allowed = {"events", "reservation.json", "poisoned.json"}
        if (
            "events" not in members
            or set(members) - allowed
            or event_names
            or "poisoned.json" in members
            and _read_private_json(
                members["poisoned.json"], "pre-effect poison marker"
            )[0]
            != {
                "schema_version": "dspx-provider-outcome-poison-v1",
                "effect_possible": False,
            }
        ):
            raise SemanticV11Error("pre-effect journal state drift")
        if "reservation.json" in members:
            reservation = _reservation_from_root(root, artifact)
            if reservation.payload() != expected_reservation.payload():
                raise SemanticV11Error("pre-effect reservation binding drift")
    projection = ReceiptProjection(
        provider_outcome_receipt="rejected",
        request_acknowledged=None,
        external_effect_possible=False,
        producer_terminal=None,
        empirical_disposition="error",
        reason="receipt_preparation_failed_before_effect",
    )
    return {
        "case_id": case.case_id,
        "case_ordinal": case.case_ordinal,
        "semantic_result_sha256": terminal["semantic_result_sha256"],
        "semantic_outcome": "semantic_error",
        "provider_outcome": projection.payload(),
        "observed_model": None,
        "terminal_sha256": sha256(canonical(terminal)),
        "reservation_sha256": reserved["reservation_sha256"],
        "semantic_request_sha256": request_digest,
        "dspx_generate_calls": 0,
        "receipt_journals": journal_count,
    }


def _derive_case(
    attempt: ConsumedAttempt,
    case: BoundContractCase,
    reserved: Mapping[str, Any],
    terminal: Mapping[str, Any],
    artifact: VerifiedOwnerArtifact,
) -> dict[str, Any]:
    case.require_canonical()
    value = dict(terminal)
    reserved_value = dict(reserved)
    semantic = validate_retained_semantic_result(case, value.get("semantic_result"))
    semantic_outcome = cast(SemanticOutcome, semantic["outcome"])
    if (
        set(value) != _TERMINAL_KEYS
        or value.get("schema_version") != CASE_CUSTODY_SCHEMA
        or value.get("kind") != "terminal"
        or value.get("live_task_id") != attempt.binding.live_task_id
        or value.get("case_id") != case.case_id
        or value.get("case_ordinal") != case.case_ordinal
        or value.get("semantic_outcome") != semantic_outcome
        or value.get("semantic_result_sha256") != sha256(canonical(semantic))
    ):
        raise SemanticV11Error("retained case terminal schema drift")
    if (
        reserved_value.get("case_id") != case.case_id
        or reserved_value.get("case_ordinal") != case.case_ordinal
    ):
        raise SemanticV11Error("retained case reservation record drift")
    if value.get("reason") == "receipt_preparation_failed_before_effect":
        return _derive_pre_effect_case(attempt, case, reserved_value, value, artifact)
    root = (
        attempt.attempt_root
        / "provider-outcomes"
        / f"{case.case_ordinal:02d}-{case.case_id}"
    )
    reservation = _reservation_from_root(root, artifact)
    expected_request = normalized_semantic_request(case.materialized_request())
    if (
        reservation.consumer_task_id != attempt.binding.live_task_id
        or reservation.ledger_sha256 != attempt.ledger_sha256
        or reservation.case_id != case.case_id
        or reservation.contract_sha256 != case.contract_sha256
        or sha256(canonical(reservation.payload()))
        != reserved_value.get("reservation_sha256")
        or reservation.semantic_request_sha256
        != reserved_value.get("semantic_request_sha256")
        or reservation.semantic_request_sha256
        != semantic_request_sha256(expected_request)
    ):
        raise SemanticV11Error("retained case reservation binding drift")
    journal = ReceiptJournal(root, reservation, artifact)
    projection, observed_model = _reduced_projection(journal, semantic_outcome)
    expected_facts = {
        "provider_outcome_receipt": projection.provider_outcome_receipt,
        "request_acknowledged": projection.request_acknowledged,
        "external_effect_possible": projection.external_effect_possible,
        "producer_terminal": projection.producer_terminal,
        "empirical_disposition": projection.empirical_disposition,
        "reason": projection.reason,
    }
    if (
        any(value.get(key) != item for key, item in expected_facts.items())
        or value.get("observed_model") != observed_model
    ):
        raise SemanticV11Error("retained case terminal derivation drift")
    return {
        "case_id": case.case_id,
        "case_ordinal": case.case_ordinal,
        "semantic_result_sha256": value["semantic_result_sha256"],
        "semantic_outcome": semantic_outcome,
        "provider_outcome": projection.payload(),
        "observed_model": observed_model,
        "terminal_sha256": sha256(canonical(value)),
        "reservation_sha256": sha256(canonical(reservation.payload())),
        "semantic_request_sha256": reservation.semantic_request_sha256,
        "dspx_generate_calls": 1,
        "receipt_journals": 1,
    }


def _aggregate_disposition(cases: list[dict[str, Any]]) -> CorpusDisposition:
    dispositions = [case["provider_outcome"]["empirical_disposition"] for case in cases]
    if not dispositions or any(
        value == "effect_indeterminate" for value in dispositions
    ):
        return "effect_indeterminate"
    if any(value in {"error", "not_evaluated"} for value in dispositions):
        return "error"
    if any(value == "failed" for value in dispositions):
        return "failed"
    if (
        tuple(case["case_id"] for case in cases) != CASE_ORDER
        or len(cases) != len(CASE_ORDER)
        or any(value != "passed" for value in dispositions)
        or len({case["observed_model"] for case in cases}) != 1
    ):
        return "error"
    return "passed"


def derive_evaluation_result(
    attempt: ConsumedAttempt,
    cases: tuple[BoundContractCase, ...],
    artifact: VerifiedOwnerArtifact,
) -> dict[str, Any]:
    """Re-derive every retained result fact from disk without provider activity."""

    if (
        type(attempt) is not ConsumedAttempt
        or tuple(case.case_id for case in cases) != CASE_ORDER
        or type(artifact) is not VerifiedOwnerArtifact
        or artifact.accepted is not True
    ):
        raise SemanticV11Error("evaluation-result derivation capability drift")
    artifact.revalidate()
    records = load_case_custody(attempt)
    setup_terminal = load_pre_effect_setup_terminal(attempt)
    derived: list[dict[str, Any]] = []
    expected_names: set[str] = set()
    for case in cases:
        reserved_name = f"{case.case_ordinal:02d}-reserved.json"
        terminal_name = f"{case.case_ordinal:02d}-terminal.json"
        if reserved_name not in records and terminal_name not in records:
            break
        if reserved_name not in records or terminal_name not in records:
            raise SemanticV11Error("incomplete reached-case custody")
        expected_names.update({reserved_name, terminal_name})
        case_result = _derive_case(
            attempt,
            case,
            records[reserved_name],
            records[terminal_name],
            artifact,
        )
        derived.append(case_result)
        if case_result["provider_outcome"]["empirical_disposition"] != "passed":
            break
    if set(records) != expected_names:
        raise SemanticV11Error("case custody stop-policy drift")
    disposition = _aggregate_disposition(derived)
    if setup_terminal is not None:
        expected_ordinal = len(derived) + 1
        if expected_ordinal > len(CASE_ORDER):
            raise SemanticV11Error("setup terminal after complete corpus")
        if (
            setup_terminal.get("next_case_ordinal") != expected_ordinal
            or setup_terminal.get("next_case_id") != CASE_ORDER[expected_ordinal - 1]
        ):
            raise SemanticV11Error("setup terminal/case sequence drift")
        disposition = "error"
    observed = {case["observed_model"] for case in derived if case["observed_model"]}
    return {
        "schema_version": RESULT_SCHEMA,
        "live_task_id": attempt.binding.live_task_id,
        "task_binding": attempt.binding.payload(),
        "ledger_sha256": attempt.ledger_sha256,
        "candidate_commit": attempt.ledger["candidate_commit"],
        "candidate_tree": attempt.ledger["candidate_tree"],
        "candidate_source_manifest_sha256": attempt.ledger[
            "candidate_source_manifest_sha256"
        ],
        "contract_sha256": attempt.ledger["contract_sha256"],
        "candidate_review_sha256": attempt.ledger["candidate_review_sha256"],
        "live_gate_sha256": attempt.ledger["live_gate_sha256"],
        "authority_snapshot_sha256": attempt.ledger["authority_snapshot_sha256"],
        "provider_owner_source_identity_sha256": sha256(
            canonical(artifact.source_identity)
        ),
        "dependency_identity_sha256": sha256(canonical(artifact.dependency_identity)),
        "artifact_integrity_review": "not_evaluated",
        "empirical_gate": disposition,
        "cases": derived,
        "operation_counts": {
            "corpus_processes": 1,
            "reached_requests": len(derived),
            "dspx_generate_calls": sum(case["dspx_generate_calls"] for case in derived),
            "receipt_journals": sum(case["receipt_journals"] for case in derived),
            "separate_health_probes": 0,
            "dspx_managed_retries": 0,
            "fallback_routes": 0,
            "provider_transport_calls": "not_proven",
        },
        "observed_model": next(iter(observed)) if len(observed) == 1 else None,
        "pre_effect_setup_terminal_sha256": (
            sha256(canonical(setup_terminal)) if setup_terminal is not None else None
        ),
        "fixture_only": False,
        "v11_authorized": True,
        "live_execution_authorized": True,
    }


def derive_pre_effect_setup_result(attempt: ConsumedAttempt) -> dict[str, Any]:
    """Derive a bounded error result for a proven pre-provider setup failure."""

    if type(attempt) is not ConsumedAttempt or load_case_custody(attempt):
        raise SemanticV11Error("pre-effect setup result custody drift")
    terminal = load_pre_effect_setup_terminal(attempt)
    if terminal is None:
        raise SemanticV11Error("pre-effect setup terminal missing")
    ledger = attempt.ledger
    return {
        "schema_version": RESULT_SCHEMA,
        "live_task_id": attempt.binding.live_task_id,
        "task_binding": attempt.binding.payload(),
        "ledger_sha256": attempt.ledger_sha256,
        "candidate_commit": ledger["candidate_commit"],
        "candidate_tree": ledger["candidate_tree"],
        "candidate_source_manifest_sha256": ledger["candidate_source_manifest_sha256"],
        "contract_sha256": ledger["contract_sha256"],
        "candidate_review_sha256": ledger["candidate_review_sha256"],
        "live_gate_sha256": ledger["live_gate_sha256"],
        "authority_snapshot_sha256": ledger["authority_snapshot_sha256"],
        "provider_owner_source_identity_sha256": None,
        "dependency_identity_sha256": None,
        "artifact_integrity_review": "not_evaluated",
        "empirical_gate": "error",
        "cases": [],
        "operation_counts": {
            "corpus_processes": 1,
            "reached_requests": 0,
            "dspx_generate_calls": 0,
            "receipt_journals": 0,
            "separate_health_probes": 0,
            "dspx_managed_retries": 0,
            "fallback_routes": 0,
            "provider_transport_calls": "not_proven",
        },
        "observed_model": None,
        "pre_effect_setup_terminal_sha256": sha256(canonical(terminal)),
        "fixture_only": False,
        "v11_authorized": True,
        "live_execution_authorized": True,
    }


def write_pre_effect_setup_result(attempt: ConsumedAttempt) -> dict[str, Any]:
    attempt.require_live()
    payload = derive_pre_effect_setup_result(attempt)
    write_exclusive(attempt.attempt_root / RESULT_NAME, payload)
    return payload


def write_evaluation_result(
    attempt: ConsumedAttempt,
    cases: tuple[BoundContractCase, ...],
    artifact: VerifiedOwnerArtifact,
) -> dict[str, Any]:
    """Write the current-process result no-replace after disk re-derivation."""

    attempt.require_live()
    payload = derive_evaluation_result(attempt, cases, artifact)
    write_exclusive(attempt.attempt_root / RESULT_NAME, payload)
    return payload


def load_evaluation_result(attempt: ConsumedAttempt) -> tuple[dict[str, Any], bytes]:
    return _read_private_json(
        attempt.attempt_root / RESULT_NAME, "semantic v11 evaluation result"
    )

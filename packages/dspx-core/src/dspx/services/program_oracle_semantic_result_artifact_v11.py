# summary: "Pure snapshot-based Gate-4 fragment and aggregate derivation."
from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal, cast, final

from dspx.services.program_oracle_semantic_artifacts_v11 import (
    ConsumedAttempt,
    load_case_terminal_markers,
    load_result_fragments,
    require_consumed_attempt,
)
from dspx.services.program_oracle_semantic_contract_v11 import (
    CASE_ORDER,
    BoundContractCase,
    SemanticV11Error,
    canonical,
    sha256,
)
from dspx.services.program_oracle_semantic_gate4_contract_v11 import RESULT_SCHEMA
from dspx.services.program_oracle_semantic_identity_v11 import (
    assert_exact_reservation,
    expected_reservation,
)
from dspx.services.program_oracle_semantic_journal_v11 import (
    JournalInspection,
    _rejected,
    inspect_fixture_journal,
    inspect_journal,
)
from dspx.services.program_oracle_semantic_result_v11 import (
    semantic_error_report,
    validate_retained_semantic_result,
)
from dspx.services.provider_outcome_receipt_contract import (
    ReceiptProjection,
    ReceiptReservation,
    SemanticOutcome,
)
from dspx.services.provider_outcome_receipt_identity import VerifiedOwnerArtifact

__all__ = ["inspect_fixture_journal", "inspect_journal"]

CorpusDisposition = Literal["effect_indeterminate", "error", "failed", "passed"]
SETUP_FAILURE_STAGES = frozenset(
    {
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
)
_CASE_STAGE_FAILURES = frozenset(
    {
        "case_custody",
        "mark_generate_entered",
        "adapter_call",
        "post_return_projection",
        "result_fragment",
    }
)


def _closed(value: Mapping[str, Any]) -> dict[str, Any]:
    result = json.loads(canonical(value))
    if not isinstance(result, dict):  # pragma: no cover
        raise SemanticV11Error("captured case mapping drift")
    return result


@final
class CaseSnapshot:
    """Immutable case/owner/reservation facts captured before the corpus loop."""

    attempt: ConsumedAttempt
    case: BoundContractCase
    reservation: ReceiptReservation
    artifact: VerifiedOwnerArtifact
    _semantic_raw: bytes
    _source_raw: bytes
    _dependency_raw: bytes
    _case_sha256: str
    _sealed: bool

    __slots__ = (
        "attempt",
        "case",
        "reservation",
        "artifact",
        "_semantic_raw",
        "_source_raw",
        "_dependency_raw",
        "_case_sha256",
        "_sealed",
    )

    def __init__(
        self,
        *,
        attempt: ConsumedAttempt,
        case: BoundContractCase,
        semantic_request: Mapping[str, Any],
        reservation: ReceiptReservation,
        artifact: VerifiedOwnerArtifact,
    ) -> None:
        attempt = require_consumed_attempt(attempt)
        case.require_canonical()
        if type(artifact) is not VerifiedOwnerArtifact or artifact.accepted is not True:
            raise SemanticV11Error("accepted owner artifact required for snapshot")
        artifact.revalidate()
        expected = expected_reservation(
            attempt,
            case=case,
            semantic_request=semantic_request,
            artifact=artifact,
        )
        assert_exact_reservation(reservation, expected)
        object.__setattr__(self, "attempt", attempt)
        object.__setattr__(self, "case", case)
        object.__setattr__(self, "reservation", reservation)
        object.__setattr__(self, "artifact", artifact)
        object.__setattr__(self, "_semantic_raw", canonical(dict(semantic_request)))
        object.__setattr__(self, "_source_raw", canonical(artifact.source_identity))
        object.__setattr__(
            self, "_dependency_raw", canonical(artifact.dependency_identity)
        )
        object.__setattr__(
            self,
            "_case_sha256",
            sha256(
                canonical(
                    {
                        "case_id": case.case_id,
                        "case_ordinal": case.case_ordinal,
                        "contract_sha256": case.contract_sha256,
                        "materialized_request_sha256": case.materialized_request().request_sha256,
                        "case": case.case,
                    }
                )
            ),
        )
        object.__setattr__(self, "_sealed", True)

    def __init_subclass__(cls, **_kwargs: object) -> None:
        raise TypeError("CaseSnapshot is sealed")

    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "_sealed", False):
            raise TypeError("CaseSnapshot is immutable")
        object.__setattr__(self, name, value)

    @property
    def semantic_request(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(self._semantic_raw))

    @property
    def source_identity(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(self._source_raw))

    @property
    def dependency_identity(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(self._dependency_raw))

    def require_captured(self, attempt: ConsumedAttempt) -> None:
        if (
            type(self) is not CaseSnapshot
            or self.attempt is not attempt
            or sha256(
                canonical(
                    {
                        "case_id": self.case.case_id,
                        "case_ordinal": self.case.case_ordinal,
                        "contract_sha256": self.case.contract_sha256,
                        "materialized_request_sha256": self.case.materialized_request().request_sha256,
                        "case": self.case.case,
                    }
                )
            )
            != self._case_sha256
        ):
            raise SemanticV11Error("captured case snapshot drift")


def validate_generate_entry(
    snapshot: CaseSnapshot, entered_ordinals: frozenset[int]
) -> None:
    """Pure ordering check immediately before local generate-entry capture."""

    snapshot.require_captured(snapshot.attempt)
    ordinal = snapshot.case.case_ordinal
    if ordinal in entered_ordinals or entered_ordinals != frozenset(range(1, ordinal)):
        raise SemanticV11Error("DSPx generate-entry ordering drift")


def build_setup_failure_fragment(
    attempt: ConsumedAttempt, stage: str
) -> dict[str, Any]:
    if stage not in SETUP_FAILURE_STAGES:
        raise SemanticV11Error("post-ledger setup failure stage drift")
    attempt = require_consumed_attempt(attempt)
    return {
        "schema_version": RESULT_SCHEMA,
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


def _base_result(
    attempt: ConsumedAttempt,
    *,
    owner_source_sha256: str | None,
    dependency_sha256: str | None,
    cases: list[dict[str, Any]],
    disposition: CorpusDisposition,
) -> dict[str, Any]:
    ledger = attempt.ledger
    admitted = sum(bool(case["invocation_admitted"]) for case in cases)
    delegations = sum(case["effect_capable_delegations"] for case in cases)
    journals = sum(bool(case["receipt_journal"]) for case in cases)
    observed = {case["observed_model"] for case in cases if case["observed_model"]}
    return {
        "schema_version": RESULT_SCHEMA,
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
        "provider_owner_source_identity_sha256": owner_source_sha256,
        "dependency_identity_sha256": dependency_sha256,
        "artifact_integrity_review": "not_evaluated",
        "empirical_gate": disposition,
        "cases": cases,
        "operation_counts": {
            "corpus_processes": 1,
            "reached_requests": len(cases),
            "admitted_invocations": admitted,
            "dspx_generate_calls": sum(
                bool(case["dspx_generate_entered"]) for case in cases
            ),
            "effect_capable_delegations": delegations,
            "receipt_journals": journals,
            "separate_health_probes": 0,
            "dspx_managed_retries": 0,
            "fallback_routes": 0,
            "provider_transport_calls": "not_proven",
        },
        "observed_model": next(iter(observed)) if len(observed) == 1 else None,
        "fixture_only": False,
        "v11_authorized": True,
        "live_execution_authorized": True,
    }


def build_setup_failure_result(attempt: ConsumedAttempt) -> dict[str, Any]:
    return _base_result(
        require_consumed_attempt(attempt),
        owner_source_sha256=None,
        dependency_sha256=None,
        cases=[],
        disposition="error",
    )


def _case_fragment_payload(
    attempt: ConsumedAttempt,
    *,
    snapshot: CaseSnapshot,
    inspection: JournalInspection,
    semantic: Mapping[str, Any],
    observed_model: str | None,
) -> dict[str, Any]:
    case = snapshot.case
    expected = snapshot.reservation
    if (
        inspection.projection.producer_terminal != "provider_response_completed"
        or inspection.observed_model is None
    ):
        semantic = semantic_error_report(case).semantic_payload()
        observed_model = None
    elif observed_model != inspection.observed_model:
        semantic = semantic_error_report(case).semantic_payload()
        observed_model = inspection.observed_model
        inspection = JournalInspection(
            ReceiptProjection(
                "accepted",
                True,
                True,
                "provider_response_completed",
                "error",
                "attributable_completion_semantic_error",
            ),
            inspection.observed_model,
            inspection.reservation_sha256,
            inspection.terminal_event_sha256,
            inspection.journal_present,
            inspection.invocation_admitted,
            inspection.effect_capable_delegations,
            inspection.clean_terminal_order_proven,
        )
    return {
        "schema_version": RESULT_SCHEMA,
        "artifact_kind": "case_result_fragment",
        "case_phase": "generate_call_terminal",
        "live_task_id": attempt.binding.live_task_id,
        "case_id": case.case_id,
        "case_ordinal": case.case_ordinal,
        "semantic_request_sha256": expected.semantic_request_sha256,
        "reservation_id": expected.reservation_id,
        "reservation_sha256": inspection.reservation_sha256,
        "journal_present": inspection.journal_present,
        "dspx_generate_entered": True,
        "invocation_admitted": inspection.invocation_admitted,
        "effect_capable_delegations": inspection.effect_capable_delegations,
        "clean_terminal_order_proven": inspection.clean_terminal_order_proven,
        "terminal_event_sha256": inspection.terminal_event_sha256,
        "semantic_result": dict(semantic),
        "semantic_result_sha256": sha256(canonical(semantic)),
        "observed_model": observed_model,
        "provider_outcome": inspection.projection.payload(),
        "fixture_only": False,
        "v11_authorized": True,
        "live_execution_authorized": True,
    }


def _journal_root(snapshot: CaseSnapshot) -> Path:
    case = snapshot.case
    return (
        snapshot.attempt.attempt_root
        / "provider-outcomes"
        / f"{case.case_ordinal:02d}-{case.case_id}"
    )


def build_case_result_fragment(
    snapshot: CaseSnapshot,
    *,
    semantic: Mapping[str, Any],
    observed_model: str | None,
) -> dict[str, Any]:
    """Pure normal fragment derivation from already-captured facts."""

    attempt = require_consumed_attempt(snapshot.attempt)
    snapshot.require_captured(attempt)
    validated = validate_retained_semantic_result(snapshot.case, semantic)
    inspection = inspect_journal(
        _journal_root(snapshot),
        expected=snapshot.reservation,
        artifact=snapshot.artifact,
        semantic_outcome=cast(SemanticOutcome, validated["outcome"]),
    )
    return _case_fragment_payload(
        attempt,
        snapshot=snapshot,
        inspection=inspection,
        semantic=validated,
        observed_model=observed_model,
    )


def build_case_call_failure(snapshot: CaseSnapshot) -> dict[str, Any]:
    """Fallback derivation that never revalidates owner source state."""

    attempt = require_consumed_attempt(snapshot.attempt)
    snapshot.require_captured(attempt)
    semantic = semantic_error_report(snapshot.case).semantic_payload()
    inspection = inspect_journal(
        _journal_root(snapshot),
        expected=snapshot.reservation,
        artifact=snapshot.artifact,
        semantic_outcome="semantic_error",
    )
    return _case_fragment_payload(
        attempt,
        snapshot=snapshot,
        inspection=inspection,
        semantic=semantic,
        observed_model=None,
    )


def build_pre_generate_failure(snapshot: CaseSnapshot, stage: str) -> dict[str, Any]:
    if stage not in _CASE_STAGE_FAILURES:
        raise SemanticV11Error("case terminal stage drift")
    attempt = require_consumed_attempt(snapshot.attempt)
    snapshot.require_captured(attempt)
    case, expected = snapshot.case, snapshot.reservation
    semantic = semantic_error_report(case).semantic_payload()
    return {
        "schema_version": RESULT_SCHEMA,
        "artifact_kind": "case_result_fragment",
        "case_phase": "pre_generate_terminal",
        "live_task_id": attempt.binding.live_task_id,
        "case_id": case.case_id,
        "case_ordinal": case.case_ordinal,
        "semantic_request_sha256": expected.semantic_request_sha256,
        "reservation_id": expected.reservation_id,
        "reservation_sha256": sha256(canonical(expected.payload())),
        "journal_present": False,
        "dspx_generate_entered": False,
        "invocation_admitted": False,
        "effect_capable_delegations": 0,
        "clean_terminal_order_proven": False,
        "terminal_event_sha256": None,
        "semantic_result": semantic,
        "semantic_result_sha256": sha256(canonical(semantic)),
        "observed_model": None,
        "provider_outcome": _rejected(
            f"post_entry_{stage}_failed_before_provider_effect", False
        ).payload(),
        "fixture_only": False,
        "v11_authorized": True,
        "live_execution_authorized": True,
    }


def build_case_terminal_marker(
    snapshot: CaseSnapshot, fragment: Mapping[str, Any], stage: str
) -> dict[str, Any]:
    if stage not in {"post_return_projection", "result_fragment"}:
        raise SemanticV11Error("case terminal marker stage drift")
    snapshot.require_captured(snapshot.attempt)
    return {
        "schema_version": RESULT_SCHEMA,
        "artifact_kind": "case_terminal_marker",
        "live_task_id": snapshot.attempt.binding.live_task_id,
        "case_id": snapshot.case.case_id,
        "case_ordinal": snapshot.case.case_ordinal,
        "stage": stage,
        "case_result_fragment_sha256": sha256(canonical(fragment)),
        "external_effect_possible": True,
        "empirical_disposition": "error",
        "reason": f"post_entry_{stage}_failed_after_case_terminal",
        "fixture_only": False,
        "v11_authorized": True,
        "live_execution_authorized": True,
    }


def _validate_case_fragment_shape(
    snapshot: CaseSnapshot, fragment: Mapping[str, Any]
) -> None:
    snapshot.require_captured(snapshot.attempt)
    if (
        fragment.get("schema_version") != RESULT_SCHEMA
        or fragment.get("artifact_kind") != "case_result_fragment"
        or fragment.get("case_id") != snapshot.case.case_id
        or fragment.get("case_ordinal") != snapshot.case.case_ordinal
        or fragment.get("semantic_request_sha256")
        != snapshot.reservation.semantic_request_sha256
        or canonical(fragment) != canonical(dict(fragment))
    ):
        raise SemanticV11Error("case result-fragment shape drift")


def validate_case_fragment_write(
    snapshot: CaseSnapshot, fragment: Mapping[str, Any]
) -> None:
    """Application check immediately before the one-shot persistence primitive."""

    _validate_case_fragment_shape(snapshot, fragment)


def validate_case_fragment_seal(
    snapshot: CaseSnapshot, fragment: Mapping[str, Any]
) -> None:
    """Application seal check immediately after durable fragment persistence."""

    _validate_case_fragment_shape(snapshot, fragment)


def _derive_case(
    snapshot: CaseSnapshot,
    fragment: Mapping[str, Any],
    marker: Mapping[str, Any] | None,
) -> dict[str, Any]:
    attempt, case, expected = snapshot.attempt, snapshot.case, snapshot.reservation
    phase = fragment.get("case_phase")
    if phase == "pre_generate_terminal":
        provider = fragment.get("provider_outcome")
        reason = provider.get("reason") if isinstance(provider, Mapping) else None
        prefix, suffix = "post_entry_", "_failed_before_provider_effect"
        if (
            not isinstance(reason, str)
            or not reason.startswith(prefix)
            or not reason.endswith(suffix)
            or dict(fragment)
            != build_pre_generate_failure(snapshot, reason[len(prefix) : -len(suffix)])
        ):
            raise SemanticV11Error("pre-generate case result derivation drift")
        semantic = validate_retained_semantic_result(
            case, fragment.get("semantic_result")
        )
        return {
            "case_id": case.case_id,
            "case_ordinal": case.case_ordinal,
            "semantic_request_sha256": expected.semantic_request_sha256,
            "reservation_sha256": fragment["reservation_sha256"],
            "terminal_event_sha256": None,
            "semantic_result_sha256": fragment["semantic_result_sha256"],
            "semantic_outcome": semantic["outcome"],
            "provider_outcome": fragment["provider_outcome"],
            "observed_model": None,
            "dspx_generate_entered": False,
            "invocation_admitted": False,
            "effect_capable_delegations": 0,
            "receipt_journal": False,
            "clean_terminal_order_proven": False,
        }
    semantic = validate_retained_semantic_result(case, fragment.get("semantic_result"))
    inspection = inspect_journal(
        _journal_root(snapshot),
        expected=expected,
        artifact=snapshot.artifact,
        semantic_outcome=cast(SemanticOutcome, semantic["outcome"]),
    )
    expected_fragment = _case_fragment_payload(
        attempt,
        snapshot=snapshot,
        inspection=inspection,
        semantic=semantic,
        observed_model=cast(str | None, fragment.get("observed_model")),
    )
    if dict(fragment) != expected_fragment:
        raise SemanticV11Error("retained case result derivation drift")
    provider = inspection.projection.payload()
    if marker is not None:
        stage = marker.get("stage")
        if not isinstance(stage, str) or dict(marker) != build_case_terminal_marker(
            snapshot, fragment, stage
        ):
            raise SemanticV11Error("case terminal marker drift")
        if provider["empirical_disposition"] != "effect_indeterminate":
            provider = ReceiptProjection(
                "accepted",
                True,
                True,
                inspection.projection.producer_terminal,
                "error",
                f"post_entry_{stage}_failed_after_case_terminal",
            ).payload()
    return {
        "case_id": case.case_id,
        "case_ordinal": case.case_ordinal,
        "semantic_request_sha256": expected.semantic_request_sha256,
        "reservation_sha256": inspection.reservation_sha256,
        "terminal_event_sha256": inspection.terminal_event_sha256,
        "semantic_result_sha256": fragment["semantic_result_sha256"],
        "semantic_outcome": semantic["outcome"],
        "provider_outcome": provider,
        "observed_model": fragment.get("observed_model"),
        "dspx_generate_entered": True,
        "invocation_admitted": inspection.invocation_admitted,
        "effect_capable_delegations": inspection.effect_capable_delegations,
        "receipt_journal": inspection.journal_present,
        "clean_terminal_order_proven": inspection.clean_terminal_order_proven,
    }


def _aggregate(cases: list[dict[str, Any]]) -> CorpusDisposition:
    dispositions = [case["provider_outcome"]["empirical_disposition"] for case in cases]
    if not dispositions or "effect_indeterminate" in dispositions:
        return "effect_indeterminate"
    if any(value in {"error", "not_evaluated"} for value in dispositions):
        return "error"
    if "failed" in dispositions:
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
    attempt: ConsumedAttempt, snapshots: tuple[CaseSnapshot, ...]
) -> dict[str, Any]:
    """Derive only from retained bytes and immutable pre-loop snapshots."""

    attempt = require_consumed_attempt(attempt)
    fragments = load_result_fragments(attempt)
    markers = load_case_terminal_markers(attempt)
    if 0 in fragments:
        stage = fragments[0].get("setup_stage")
        if (
            set(fragments) != {0}
            or markers
            or not isinstance(stage, str)
            or fragments[0] != build_setup_failure_fragment(attempt, stage)
        ):
            raise SemanticV11Error("setup result fragment drift")
        return build_setup_failure_result(attempt)
    if (
        len(snapshots) != len(CASE_ORDER)
        or tuple(snapshot.case.case_id for snapshot in snapshots) != CASE_ORDER
        or any(snapshot.attempt is not attempt for snapshot in snapshots)
    ):
        raise SemanticV11Error("complete captured case snapshots required")
    derived: list[dict[str, Any]] = []
    expected_ordinals: set[int] = set()
    for snapshot in snapshots:
        fragment = fragments.get(snapshot.case.case_ordinal)
        if fragment is None:
            break
        expected_ordinals.add(snapshot.case.case_ordinal)
        item = _derive_case(snapshot, fragment, markers.get(snapshot.case.case_ordinal))
        derived.append(item)
        if item["provider_outcome"]["empirical_disposition"] != "passed":
            break
    if set(fragments) != expected_ordinals or set(markers) - expected_ordinals:
        raise SemanticV11Error("result fragment stop-policy drift")
    first = snapshots[0]
    return _base_result(
        attempt,
        owner_source_sha256=sha256(canonical(first.source_identity)),
        dependency_sha256=sha256(canonical(first.dependency_identity)),
        cases=derived,
        disposition=_aggregate(derived),
    )

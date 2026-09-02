"""Retained evidence validation for foundry-only dspy-lm-auth jury calls."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from dspx.services.program_foundry_gepa_comparison_jury_owner import (
    expected_foundry_jury_dependency_identity,
    verify_foundry_jury_owner_source,
)
from dspx.services.program_foundry_gepa_comparison_jury_provider_custody import (
    ENDPOINT_ORIGIN_SHA256,
    FoundryJuryProviderConfigurationError,
    _journal_projection_sha256,
    _LOCAL_CLOSED_STOP_REASONS,
    _private_directory,
    _request_identity,
)
from dspx.services.soomfon_provider_outcome_receipt_journal import (
    load_verified_journal,
)
from dspx.services.soomfon_provider_outcome_receipt_reducer import (
    reduce_verified_chain,
    verify_receipt_chain,
)


def validate_foundry_jury_provider_evidence(
    value: Mapping[str, Any],
    *,
    journal_parent: Path,
    owner_source_root: Path,
    execution_task_id: int,
    contract_sha256: str,
    expected_juror_ids: Sequence[str],
    expected_model: str,
) -> dict[str, Any]:
    """Revalidate retained closed journals against one outer jury attempt."""

    records = value.get("call_records")
    total = value.get("logical_call_total")
    maximum = len(tuple(expected_juror_ids))
    disposition = value.get("session_disposition")
    stopped_after_call = value.get("stopped_after_call")
    stop_reason = value.get("stop_reason")
    if (
        value.get("schema_version") != "dspx-foundry-jury-provider-outcome-evidence-v1"
        or value.get("artifact_verification") != "accepted_exact"
        or isinstance(total, bool)
        or not isinstance(total, int)
        or not isinstance(records, list)
        or total != len(records)
        or not 1 <= total <= maximum
        or value.get("maximum_logical_calls") != maximum
        or value.get("maximum_provider_transports") != maximum
        or value.get("sync_only") is not True
        or value.get("fallback_allowed") is not False
        or value.get("health_probe_allowed") is not False
        or value.get("retry_count") != 0
        or disposition not in {"complete", "closed_terminal"}
        or (
            disposition == "complete"
            and (
                total != maximum
                or stopped_after_call is not None
                or stop_reason is not None
            )
        )
        or (
            disposition == "closed_terminal"
            and (
                stopped_after_call != total
                or not isinstance(stop_reason, str)
                or not stop_reason
            )
        )
    ):
        raise FoundryJuryProviderConfigurationError(
            "provider outcome evidence shape is invalid"
        )
    parent = _private_directory(journal_parent)
    members = sorted(parent.iterdir(), key=lambda item: item.name)
    source_identity = verify_foundry_jury_owner_source(owner_source_root)
    dependency_identity = expected_foundry_jury_dependency_identity()
    requested_route = f"dspy-lm-auth:codex:{expected_model}"
    resolved_route = f"openai:{expected_model}:responses"
    if len(members) != total:
        raise FoundryJuryProviderConfigurationError(
            "provider outcome journal count drifted"
        )
    for ordinal, (path, raw_record) in enumerate(
        zip(members, records, strict=True), start=1
    ):
        if not isinstance(raw_record, Mapping):
            raise FoundryJuryProviderConfigurationError(
                "provider call record shape is invalid"
            )
        journal = load_verified_journal(path)
        reduced = reduce_verified_chain(verify_receipt_chain(journal))
        reservation = journal.reservation
        logical, process, gate = _request_identity(
            contract_sha256=contract_sha256,
            execution_task_id=execution_task_id,
            ordinal=ordinal,
            juror_id=expected_juror_ids[ordinal - 1],
        )
        expected_record = {
            "call_ordinal": ordinal,
            "juror_id": expected_juror_ids[ordinal - 1],
            "reservation_id": reservation.reservation_id,
            "journal_sha256": _journal_projection_sha256(journal),
            "semantic_request_sha256": reservation.semantic_request_sha256,
            "provider_outcome_receipt": "accepted",
            "request_acknowledged": reduced.request_acknowledged,
            "external_effect_possible": reduced.external_effect_possible,
            "producer_terminal": reduced.terminal,
            "status_class": reduced.status_class,
            "status_code": reduced.status_code,
            "empirical_disposition": reduced.empirical_disposition,
            "reason": reduced.reason,
        }
        if (
            path.name != f"{ordinal:02d}-{reservation.logical_request_id}"
            or journal.artifact_verification != "accepted_exact"
            or reservation.consumer_task_id != execution_task_id
            or reservation.contract_sha256 != contract_sha256
            or reservation.ledger_sha256 != contract_sha256
            or reservation.case_id != f"jury-{ordinal}"
            or reservation.process_id != process
            or reservation.logical_request_id != logical
            or reservation.transport_gate_id != gate
            or reservation.mode != "sync"
            or reservation.requested_route != requested_route
            or reservation.resolved_route != resolved_route
            or reservation.endpoint_origin_sha256 != ENDPOINT_ORIGIN_SHA256
            or reservation.source_identity != source_identity
            or reservation.dependency_identity != dependency_identity
            or (
                reduced.terminal == "provider_response_completed"
                and journal.events[-1].event.observed_model != expected_model
            )
            or dict(raw_record) != expected_record
            or reduced.empirical_disposition == "effect_indeterminate"
        ):
            raise FoundryJuryProviderConfigurationError(
                "provider outcome journal binding drifted"
            )
    if disposition == "closed_terminal":
        last_reason = records[-1]["reason"]
        if stop_reason != last_reason and stop_reason not in _LOCAL_CLOSED_STOP_REASONS:
            raise FoundryJuryProviderConfigurationError(
                "provider closed-session disposition drifted"
            )
    return dict(value)

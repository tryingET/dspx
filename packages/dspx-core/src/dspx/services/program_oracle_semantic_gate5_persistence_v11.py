# summary: "Durable Gate-5 one-shot marker and bounded rejected-artifact sink."
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import dspx.services.program_oracle_semantic_state_v11 as _state_io
from dspx.services.program_oracle_semantic_artifacts_v11 import (
    ConsumedAttempt,
    TaskBinding,
    current_process_identity_sha256,
)
from dspx.services.program_oracle_semantic_gate4_contract_v11 import (
    GATE2_TASK_ID,
    GATE5_REJECTION_REASON_CODES,
    GATE5_STARTED_SCHEMA,
    REMEDIATION_TASK_ID,
    RESULT_NAME,
    RESULT_SCHEMA,
    VERIFICATION_NAME,
    VERIFICATION_SCHEMA,
    SemanticV11Error,
)


class Gate5PersistenceError(SemanticV11Error):
    """Truthful Gate-5 disposition at or around durable one-shot entry."""

    retry_allowed: bool
    started_marker_consumed: bool
    verification_retained: bool
    artifact_integrity_review: str
    provider_invoked: bool
    v11_authorized: bool
    live_execution_authorized: bool
    authority_granted: bool
    reason_code: str

    def __init__(
        self,
        reason_code: str,
        *,
        started_marker_consumed: bool,
        verification_retained: bool = False,
    ) -> None:
        retry_allowed = not started_marker_consumed
        message = (
            "Gate-5 entry did not begin; retry is mechanically allowed"
            if retry_allowed
            else "Gate-5 persistence/integrity failed; retry authority is false"
        )
        super().__init__(message)
        self.retry_allowed = retry_allowed
        self.started_marker_consumed = started_marker_consumed
        self.verification_retained = verification_retained
        self.artifact_integrity_review = (
            "rejected" if started_marker_consumed else "not_evaluated"
        )
        self.provider_invoked = False
        self.v11_authorized = False
        self.live_execution_authorized = False
        self.authority_granted = False
        self.reason_code = reason_code


class Gate5PreflightError(Gate5PersistenceError):
    """Root-bound canonical evidence preflight failed before one-shot entry."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code, started_marker_consumed=False)


class Gate5OneShotError(Gate5PersistenceError):
    """A durable Gate-5 started marker already consumed this root."""

    def __init__(self) -> None:
        super().__init__(
            "gate5_already_started",
            started_marker_consumed=True,
        )


_EMPIRICAL_DISPOSITIONS = {"effect_indeterminate", "error", "failed", "passed"}
_OPERATION_COUNT_KEYS = {
    "corpus_processes",
    "reached_requests",
    "admitted_invocations",
    "dspx_generate_calls",
    "effect_capable_delegations",
    "receipt_journals",
    "separate_health_probes",
    "dspx_managed_retries",
    "fallback_routes",
    "provider_transport_calls",
}
_NUMERIC_OPERATION_KEYS = _OPERATION_COUNT_KEYS - {"provider_transport_calls"}
_GATE5_STARTED_KEYS = {
    "schema_version",
    "artifact_kind",
    "gate5_task_id",
    "gate5_evidence_id",
    "live_task_id",
    "state_root_identity_sha256",
    "root_binding_id",
    "process_identity_sha256",
    "status",
    "maximum_verification_processes",
    "retry_allowed",
    "provider_invoked",
    "fixture_only",
    "v11_authorized",
    "live_execution_authorized",
    "authority_granted",
}


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
        raise SemanticV11Error(
            "Gate-5 persistence value is not canonical JSON"
        ) from exc


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _valid_positive_int(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value > 0


def _gate5_started_path(state_root: Path, root_binding_id: str) -> Path:
    return state_root / (
        f".dspx-oracle-semantic-v11-gate5-{root_binding_id}.started.json"
    )


def _consume_gate5_started(
    *,
    state_root: Path,
    live_task_id: int,
    gate5_task_id: int,
    gate5_evidence_id: int,
    expected_state_root_identity_sha256: str,
) -> tuple[TaskBinding, Path, dict[str, Any]]:
    """Persist one marker only after canonical root/evidence preflight passed."""

    if not all(
        _valid_positive_int(value)
        for value in (live_task_id, gate5_task_id, gate5_evidence_id)
    ) or gate5_task_id in {GATE2_TASK_ID, REMEDIATION_TASK_ID, live_task_id}:
        raise SemanticV11Error("Gate-5 start identity rejected")
    try:
        root = state_root.expanduser()
        root_identity = _state_io.state_root_identity_sha256(root)
        if root_identity != expected_state_root_identity_sha256:
            raise Gate5PreflightError("state_root_changed_before_start")
        binding = TaskBinding(live_task_id, root_identity)
        process_identity = current_process_identity_sha256()
    except Gate5PreflightError:
        raise
    except (OSError, RuntimeError, SemanticV11Error) as exc:
        raise Gate5PersistenceError(
            "unsafe_state_root",
            started_marker_consumed=False,
        ) from exc
    payload = {
        "schema_version": GATE5_STARTED_SCHEMA,
        "artifact_kind": "gate5_verification_started",
        "gate5_task_id": gate5_task_id,
        "gate5_evidence_id": gate5_evidence_id,
        "live_task_id": live_task_id,
        "state_root_identity_sha256": root_identity,
        "root_binding_id": binding.root_binding_id,
        "process_identity_sha256": process_identity,
        "status": "started",
        "maximum_verification_processes": 1,
        "retry_allowed": False,
        "provider_invoked": False,
        "fixture_only": False,
        "v11_authorized": False,
        "live_execution_authorized": False,
        "authority_granted": False,
    }
    if set(payload) != _GATE5_STARTED_KEYS:
        raise SemanticV11Error("Gate-5 started marker shape drift")
    marker_path = _gate5_started_path(root, binding.root_binding_id)
    try:
        _state_io._persist_no_replace(marker_path, payload)
    except (OSError, SemanticV11Error) as exc:
        if marker_path.exists() or marker_path.is_symlink():
            raise Gate5OneShotError() from exc
        raise Gate5PersistenceError(
            "gate5_started_persistence_failed",
            started_marker_consumed=False,
        ) from exc
    _, _, _, attempt_root = _state_io._paths(root, binding)
    return binding, attempt_root, payload


def _empty_rejection_facts() -> dict[str, Any]:
    return {
        "gate5_task_contract_sha256": None,
        "gate5_guardrails_sha256": None,
        "gate5_evidence_sha256": None,
        "empirical_gate": None,
        "result_sha256": None,
        "ledger_sha256": None,
        "candidate_review_sha256": None,
        "live_gate_sha256": None,
        "candidate_commit": None,
        "candidate_tree": None,
        "candidate_source_manifest_sha256": None,
        "contract_sha256": None,
        "provider_owner_source_identity_sha256": None,
        "dependency_identity_sha256": None,
        "operation_counts": None,
    }


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _is_git_identity(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(char in "0123456789abcdef" for char in value)
    )


def _bounded_operation_counts(value: object) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    items: dict[str, Any] = {str(key): item for key, item in value.items()}
    if set(items) != _OPERATION_COUNT_KEYS:
        return None
    for key in _NUMERIC_OPERATION_KEYS:
        item = items.get(key)
        if isinstance(item, bool) or not isinstance(item, int) or not 0 <= item <= 4:
            return None
    if (
        items.get("corpus_processes") != 1
        or items.get("provider_transport_calls") != "not_proven"
    ):
        return None
    closed = json.loads(_canonical(items))
    return closed if isinstance(closed, dict) else None


def _capture_attempt_facts(facts: dict[str, Any], attempt: ConsumedAttempt) -> None:
    ledger = attempt.ledger
    facts["ledger_sha256"] = attempt.ledger_sha256
    for key in ("candidate_source_manifest_sha256", "contract_sha256"):
        value = ledger.get(key)
        if _is_sha256(value):
            facts[key] = value
    for key in ("candidate_commit", "candidate_tree"):
        value = ledger.get(key)
        if _is_git_identity(value):
            facts[key] = value


def _capture_result_facts(
    facts: dict[str, Any], payload: Mapping[str, Any], raw: bytes
) -> None:
    if (
        payload.get("schema_version") != RESULT_SCHEMA
        or payload.get("artifact_kind") != "evaluation_result"
    ):
        return
    facts["result_sha256"] = _sha(raw)
    empirical = payload.get("empirical_gate")
    if empirical in _EMPIRICAL_DISPOSITIONS:
        facts["empirical_gate"] = empirical
    counts = _bounded_operation_counts(payload.get("operation_counts"))
    if counts is not None:
        facts["operation_counts"] = counts
    for key in (
        "candidate_source_manifest_sha256",
        "contract_sha256",
        "provider_owner_source_identity_sha256",
        "dependency_identity_sha256",
    ):
        value = payload.get(key)
        if value is None or _is_sha256(value):
            facts[key] = value
    for key in ("candidate_commit", "candidate_tree"):
        value = payload.get(key)
        if _is_git_identity(value):
            facts[key] = value


def _try_capture_result_facts(attempt_root: Path, facts: dict[str, Any]) -> None:
    try:
        payload, raw = _state_io.read_private_json(
            attempt_root / RESULT_NAME, "evaluation result"
        )
    except (OSError, SemanticV11Error):
        return
    _capture_result_facts(facts, payload, raw)


def _rejected_payload(
    *,
    live_task_id: int,
    gate5_task_id: int,
    gate5_evidence_id: int,
    reason_code: str,
    facts: Mapping[str, Any],
) -> dict[str, Any]:
    if reason_code not in GATE5_REJECTION_REASON_CODES:
        raise SemanticV11Error("Gate-5 rejection reason-code drift")
    return {
        "schema_version": VERIFICATION_SCHEMA,
        "artifact_kind": "independent_verification",
        "gate5_task_id": gate5_task_id,
        "gate5_evidence_id": gate5_evidence_id,
        "gate5_task_contract_sha256": facts["gate5_task_contract_sha256"],
        "gate5_guardrails_sha256": facts["gate5_guardrails_sha256"],
        "gate5_evidence_sha256": facts["gate5_evidence_sha256"],
        "live_task_id": live_task_id,
        "artifact_integrity_review": "rejected",
        "empirical_gate": facts["empirical_gate"],
        "rejection_reason_code": reason_code,
        "result_sha256": facts["result_sha256"],
        "ledger_sha256": facts["ledger_sha256"],
        "candidate_review_sha256": facts["candidate_review_sha256"],
        "live_gate_sha256": facts["live_gate_sha256"],
        "candidate_commit": facts["candidate_commit"],
        "candidate_tree": facts["candidate_tree"],
        "candidate_source_manifest_sha256": facts["candidate_source_manifest_sha256"],
        "contract_sha256": facts["contract_sha256"],
        "provider_owner_source_identity_sha256": facts[
            "provider_owner_source_identity_sha256"
        ],
        "dependency_identity_sha256": facts["dependency_identity_sha256"],
        "operation_counts": facts["operation_counts"],
        "privacy": None,
        "provider_invoked": False,
        "terminal_evidence_modified": False,
        "fixture_only": False,
        "v11_authorized": False,
        "live_execution_authorized": False,
        "authority_granted": False,
    }


def _persist_rejected_once(
    *,
    attempt_root: Path,
    live_task_id: int,
    gate5_task_id: int,
    gate5_evidence_id: int,
    reason_code: str,
    facts: dict[str, Any],
) -> dict[str, Any]:
    _try_capture_result_facts(attempt_root, facts)
    payload = _rejected_payload(
        live_task_id=live_task_id,
        gate5_task_id=gate5_task_id,
        gate5_evidence_id=gate5_evidence_id,
        reason_code=reason_code,
        facts=facts,
    )
    path = attempt_root / VERIFICATION_NAME
    try:
        _state_io._persist_no_replace(path, payload)
    except (OSError, SemanticV11Error) as exc:
        raise Gate5PersistenceError(
            "rejection_persistence_failed",
            started_marker_consumed=True,
        ) from exc
    try:
        written, written_raw = _state_io.read_private_json(
            path, "independent verification"
        )
    except (OSError, SemanticV11Error) as exc:
        raise Gate5PersistenceError(
            "rejection_readback_failed",
            started_marker_consumed=True,
            verification_retained=path.exists(),
        ) from exc
    if written != payload or written_raw != _canonical(payload):
        raise Gate5PersistenceError(
            "rejection_readback_failed",
            started_marker_consumed=True,
            verification_retained=path.exists(),
        )
    return payload

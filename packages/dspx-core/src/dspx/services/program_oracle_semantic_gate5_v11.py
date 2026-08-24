# summary: "Monolithic distinct-process Gate-5 read, rederive, write, and readback."
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import dspx.services.program_oracle_semantic_state_v11 as _state_io
from dspx.services.program_oracle_semantic_artifacts_v11 import (
    ConsumedAttempt,
    current_process_identity_sha256,
    load_authority_artifacts,
    load_consumed_attempt,
    load_evaluation_result,
    load_independent_verification,
    require_consumed_attempt,
)
from dspx.services.program_oracle_semantic_evidence_v11 import (
    canonical_evidence_record,
)
from dspx.services.program_oracle_semantic_gate4_contract_v11 import (
    CONTRACT_SHA256,
    GATE2_TASK_ID,
    GATE5_DONE_CONTRACT,
    GATE5_GUARDRAILS,
    REMEDIATION_TASK_ID,
    VERIFICATION_NAME,
    VERIFICATION_SCHEMA,
    SemanticV11Error,
)
from dspx.services.program_oracle_semantic_gate5_authority_v11 import (
    reconstruct_authority_payloads,
)
from dspx.services.program_oracle_semantic_gate5_result_v11 import (
    independently_rederive_result,
)
from dspx.services.program_oracle_semantic_gate5_persistence_v11 import (
    Gate5PersistenceError,
    Gate5PreflightError,
    _capture_attempt_facts,
    _capture_result_facts,
    _consume_gate5_started,
    _empty_rejection_facts,
    _persist_rejected_once,
)
from dspx.services.program_oracle_semantic_gate5_runtime_v11 import (
    git_identity as _git_identity,
    _run_ak,
    source_manifest as _source_manifest,
    verify_loaded_origins as _verify_loaded_origins,
    verify_owner as _verify_owner,
)

__all__ = ["validate_gate5_authority_documents", "verify_retained_once"]


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


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SemanticV11Error(f"Gate-5 {label} must be an object")
    return {str(key): item for key, item in value.items()}


_GATE5_PREFLIGHT_DETAIL_KEYS = {
    "schema_version",
    "artifact_kind",
    "gate5_task_id",
    "gate5_task_entity_version",
    "gate5_task_contract_sha256",
    "gate5_guardrails_sha256",
    "live_task_id",
    "gate_3_task_id",
    "state_root_identity_sha256",
    "ledger_sha256",
    "result_sha256",
    "candidate_review_sha256",
    "live_gate_sha256",
    "decision",
    "different_process_required",
    "provider_operations",
    "terminal_modification_allowed",
}
_GATE5_PREFLIGHT_HASH_KEYS = {
    "gate5_task_contract_sha256",
    "gate5_guardrails_sha256",
    "state_root_identity_sha256",
    "ledger_sha256",
    "result_sha256",
    "candidate_review_sha256",
    "live_gate_sha256",
}


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_positive_int(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value > 0


def _machine(value: object, surface: str) -> dict[str, Any]:
    envelope = _mapping(value, f"{surface} envelope")
    if (
        envelope.get("surface") != surface
        or envelope.get("ok") is not True
        or envelope.get("error") is not None
    ):
        raise SemanticV11Error("Gate-5 canonical AK envelope rejected")
    return _mapping(envelope.get("payload"), f"{surface} payload")


@dataclass(frozen=True, slots=True)
class _Gate5Record:
    gate5_task_id: int
    gate5_evidence_id: int
    task_contract_sha256: str
    guardrails_sha256: str
    evidence_sha256: str


def _resolved_repo(value: object, expected: Path) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return Path(value).expanduser().resolve(strict=True) == expected
    except OSError:
        return False


def _validate_gate5_documents(
    *,
    repo_root: Path,
    attempt: ConsumedAttempt,
    result_sha256: str,
    gate5_task_id: int,
    gate5_evidence_id: int,
    task_document: Mapping[str, Any],
    contract_document: Mapping[str, Any],
    evidence_document: Mapping[str, Any],
    evidence_set_document: Mapping[str, Any],
) -> _Gate5Record:
    attempt = require_consumed_attempt(attempt)
    ledger = attempt.ledger
    distinct_tasks = {
        GATE2_TASK_ID,
        REMEDIATION_TASK_ID,
        ledger["gate_3_task_id"],
        attempt.binding.live_task_id,
        gate5_task_id,
    }
    gate2_evidence_ids = ledger.get("gate_2_evidence_ids")
    if gate2_evidence_ids != [6729, 6730]:
        raise SemanticV11Error("Gate-5 Gate-2 evidence identity drift")
    gate2_evidence_ids = cast(list[int], gate2_evidence_ids)
    prior_evidence = {
        *gate2_evidence_ids,
        ledger["remediation_validation_evidence_id"],
        ledger["candidate_review_evidence_id"],
        ledger["operator_evidence_id"],
        ledger["live_gate_evidence_id"],
        gate5_evidence_id,
    }
    if (
        ledger.get("live_authorized") is not True
        or ledger.get("process_admitted") is not True
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in (gate5_task_id, gate5_evidence_id)
        )
        or len(distinct_tasks) != 5
        or len(prior_evidence) != 7
        or not distinct_tasks.isdisjoint(prior_evidence)
        or ledger["process_identity_sha256"] == current_process_identity_sha256()
    ):
        raise SemanticV11Error("Gate-5 task/evidence/process separation rejected")
    root = repo_root.expanduser().resolve(strict=True)
    task = _mapping(_machine(task_document, "task.show").get("task"), "task")
    version = task.get("entity_version")
    if (
        task.get("id") != gate5_task_id
        or task.get("status") not in {"claimed", "running"}
        or not _resolved_repo(task.get("repo"), root)
        or isinstance(version, bool)
        or not isinstance(version, int)
        or version <= 0
    ):
        raise SemanticV11Error("canonical Gate-5 task rejected")
    contract = dict(contract_document)
    done = _mapping(contract.get("done_contract"), "done contract")
    guard = _mapping(contract.get("guardrails"), "guardrails")
    if (
        set(contract) != {"task_id", "repo", "status", "done_contract", "guardrails"}
        or set(done) != {"task_id", "contract", "entity_version"}
        or set(guard) != {"task_id", "guardrails", "entity_version"}
        or contract.get("task_id") != gate5_task_id
        or contract.get("status") != task["status"]
        or not _resolved_repo(contract.get("repo"), root)
        or done.get("task_id") != gate5_task_id
        or guard.get("task_id") != gate5_task_id
        or done.get("contract") != GATE5_DONE_CONTRACT
        or guard.get("guardrails") != GATE5_GUARDRAILS
        or any(
            isinstance(item, bool) or not isinstance(item, int) or item <= 0
            for item in (done.get("entity_version"), guard.get("entity_version"))
        )
    ):
        raise SemanticV11Error("canonical Gate-5 full task contract rejected")
    contract_sha = _sha(_canonical(done))
    guard_sha = _sha(_canonical(guard))
    evidence = canonical_evidence_record(
        _machine(evidence_document, "evidence.show").get("evidence"),
        evidence_id=gate5_evidence_id,
        task_id=gate5_task_id,
        check_type="oracle_semantic_v11_gate5_authorization",
    )
    expected = {
        "schema_version": VERIFICATION_SCHEMA,
        "artifact_kind": "gate5_authorization",
        "gate5_task_id": gate5_task_id,
        "gate5_task_entity_version": version,
        "gate5_task_contract_sha256": contract_sha,
        "gate5_guardrails_sha256": guard_sha,
        "live_task_id": attempt.binding.live_task_id,
        "gate_3_task_id": ledger["gate_3_task_id"],
        "state_root_identity_sha256": attempt.binding.state_root_identity_sha256,
        "ledger_sha256": attempt.ledger_sha256,
        "result_sha256": result_sha256,
        "candidate_review_sha256": ledger["candidate_review_sha256"],
        "live_gate_sha256": ledger["live_gate_sha256"],
        "decision": "AUTHORIZE_ONE_PROVIDER_FREE_INDEPENDENT_VERIFICATION",
        "different_process_required": True,
        "provider_operations": 0,
        "terminal_modification_allowed": False,
    }
    if (
        evidence.get("id") != gate5_evidence_id
        or evidence.get("task_ref") != gate5_task_id
        or evidence.get("check_type") != "oracle_semantic_v11_gate5_authorization"
        or evidence.get("result") != "pass"
        or evidence.get("details") != expected
    ):
        raise SemanticV11Error("canonical Gate-5 evidence rejected")
    evidence_set = _machine(evidence_set_document, "evidence.task")
    rows = evidence_set.get("evidence")
    selected = (
        [
            row
            for row in rows
            if row.get("check_type") == "oracle_semantic_v11_gate5_authorization"
        ]
        if isinstance(rows, list) and all(isinstance(row, Mapping) for row in rows)
        else []
    )
    if (
        evidence_set.get("task_id") != gate5_task_id
        or evidence_set.get("count") != len(rows or [])
        or len(selected) != 1
        or dict(selected[0]) != evidence
    ):
        raise SemanticV11Error("Gate-5 evidence cardinality rejected")
    return _Gate5Record(
        gate5_task_id,
        gate5_evidence_id,
        contract_sha,
        guard_sha,
        _sha(_canonical(evidence)),
    )


def validate_gate5_authority_documents(**kwargs: Any) -> dict[str, Any]:
    """Pure Gate-5 document validator; its output grants no write authority."""

    record = _validate_gate5_documents(**kwargs)
    return {
        "gate5_task_id": record.gate5_task_id,
        "gate5_evidence_id": record.gate5_evidence_id,
        "task_contract_sha256": record.task_contract_sha256,
        "guardrails_sha256": record.guardrails_sha256,
        "evidence_sha256": record.evidence_sha256,
        "fixture_only": True,
        "v11_authorized": False,
        "live_execution_authorized": False,
        "authority_granted": False,
    }


def _with_final_privacy(
    payload: dict[str, Any], before: Mapping[str, int]
) -> dict[str, Any]:
    payload["privacy"] = {
        "files": before["files"] + 1,
        "directories": before["directories"],
        "bytes": 0,
    }
    for _ in range(20):
        total = before["bytes"] + len(_canonical(payload))
        if payload["privacy"]["bytes"] == total:
            return payload
        payload["privacy"]["bytes"] = total
    raise SemanticV11Error("Gate-5 final privacy fixed point unavailable")


def _validate_written_verification(
    attempt: ConsumedAttempt, payload: Mapping[str, Any]
) -> dict[str, int]:
    """Read back exact bytes and rerun the complete tree including verification."""

    written, written_raw = load_independent_verification(attempt)
    if written != dict(payload) or written_raw != _canonical(payload):
        raise SemanticV11Error("Gate-5 written verification payload drift")
    from dspx.services.program_oracle_semantic_verification_v11 import (
        verify_private_tree,
    )

    final_privacy = verify_private_tree(attempt, include_verification=True)
    if final_privacy != payload.get("privacy"):
        raise SemanticV11Error("Gate-5 written verification privacy drift")
    return final_privacy


def _gate5_root_preflight(
    *,
    state_root: Path,
    live_task_id: int,
    gate5_task_id: int,
    gate5_evidence_id: int,
) -> str:
    """Read and minimally bind canonical Gate-5 evidence before consumption."""

    if any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
        for value in (live_task_id, gate5_task_id, gate5_evidence_id)
    ) or gate5_task_id in {GATE2_TASK_ID, REMEDIATION_TASK_ID, live_task_id}:
        raise Gate5PreflightError("gate5_selector_preflight_rejected")
    try:
        root_identity = _state_io.state_root_identity_sha256(state_root.expanduser())
    except (OSError, RuntimeError, SemanticV11Error) as exc:
        raise Gate5PreflightError("unsafe_state_root_preflight") from exc
    try:
        document = _run_ak("evidence", "show", str(gate5_evidence_id), "--machine")
        evidence = canonical_evidence_record(
            _machine(document, "evidence.show").get("evidence"),
            evidence_id=gate5_evidence_id,
            task_id=gate5_task_id,
            check_type="oracle_semantic_v11_gate5_authorization",
        )
        details = _mapping(evidence.get("details"), "authorization details")
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        raise Gate5PreflightError("gate5_evidence_preflight_malformed") from exc
    gate3_task_id = details.get("gate_3_task_id")
    if (
        set(details) != _GATE5_PREFLIGHT_DETAIL_KEYS
        or details.get("schema_version") != VERIFICATION_SCHEMA
        or details.get("artifact_kind") != "gate5_authorization"
        or details.get("gate5_task_id") != gate5_task_id
        or not _is_positive_int(details.get("gate5_task_entity_version"))
        or details.get("live_task_id") != live_task_id
        or not _is_positive_int(gate3_task_id)
        or gate3_task_id
        in {GATE2_TASK_ID, REMEDIATION_TASK_ID, live_task_id, gate5_task_id}
        or any(not _is_sha256(details.get(key)) for key in _GATE5_PREFLIGHT_HASH_KEYS)
        or details.get("state_root_identity_sha256") != root_identity
        or details.get("decision")
        != "AUTHORIZE_ONE_PROVIDER_FREE_INDEPENDENT_VERIFICATION"
        or details.get("different_process_required") is not True
        or details.get("provider_operations") != 0
        or details.get("terminal_modification_allowed") is not False
    ):
        raise Gate5PreflightError("gate5_evidence_preflight_unbound")
    return root_identity


def verify_retained_once(
    *,
    repo_root: Path,
    state_root: Path,
    live_task_id: int,
    gate5_task_id: int,
    gate5_evidence_id: int,
    owner_source_root: Path,
) -> dict[str, Any]:
    """Trusted Gate 5: root preflight, durable consume, derive, and retain.

    Arbitrary code execution, monkeypatching, tracing, or reflection inside this
    interpreter is outside the capability boundary, consistent with the accepted
    same-UID sink boundary. Supported public and caller-data paths fail closed.
    """

    root_identity = _gate5_root_preflight(
        state_root=state_root,
        live_task_id=live_task_id,
        gate5_task_id=gate5_task_id,
        gate5_evidence_id=gate5_evidence_id,
    )
    binding, attempt_root, started = _consume_gate5_started(
        state_root=state_root,
        live_task_id=live_task_id,
        gate5_task_id=gate5_task_id,
        gate5_evidence_id=gate5_evidence_id,
        expected_state_root_identity_sha256=root_identity,
    )
    try:
        _state_io._private_info(attempt_root, directory=True)
    except (OSError, SemanticV11Error) as exc:
        raise Gate5PersistenceError(
            "unsafe_attempt_root",
            started_marker_consumed=True,
        ) from exc

    facts = _empty_rejection_facts()
    reason_code = "consumed_attempt_rejected"
    try:
        attempt = load_consumed_attempt(state_root, live_task_id)
        _capture_attempt_facts(facts, attempt)
        if (
            attempt.binding.payload() != binding.payload()
            or started["state_root_identity_sha256"]
            != attempt.binding.state_root_identity_sha256
            or started["root_binding_id"] != attempt.binding.root_binding_id
            or started["process_identity_sha256"] != current_process_identity_sha256()
            or attempt.ledger["process_identity_sha256"]
            == started["process_identity_sha256"]
        ):
            raise SemanticV11Error("Gate-5 started/attempt binding rejected")

        reason_code = "retained_result_rejected"
        retained, retained_raw = load_evaluation_result(attempt)
        _capture_result_facts(facts, retained, retained_raw)

        reason_code = "retained_authority_rejected"
        review, review_raw, gate, gate_raw = load_authority_artifacts(attempt)
        facts["candidate_review_sha256"] = _sha(review_raw)
        facts["live_gate_sha256"] = _sha(gate_raw)

        reason_code = "candidate_source_rejected"
        manifest = _source_manifest(repo_root)
        reason_code = "candidate_git_identity_rejected"
        commit, tree = _git_identity(repo_root)
        ledger = attempt.ledger

        reason_code = "canonical_authority_read_rejected"
        documents = {
            "gate_2_task_document": _run_ak(
                "task", "show", str(GATE2_TASK_ID), "--machine"
            ),
            "gate_2_contract_document": _run_ak(
                "task", "contract", "show", str(GATE2_TASK_ID), "-F", "json"
            ),
            "gate_2_evidence_6729_document": _run_ak(
                "evidence", "show", "6729", "--machine"
            ),
            "gate_2_evidence_6730_document": _run_ak(
                "evidence", "show", "6730", "--machine"
            ),
            "remediation_task_document": _run_ak(
                "task", "show", str(REMEDIATION_TASK_ID), "--machine"
            ),
            "remediation_contract_document": _run_ak(
                "task",
                "contract",
                "show",
                str(REMEDIATION_TASK_ID),
                "-F",
                "json",
            ),
            "review_task_document": _run_ak(
                "task", "show", str(ledger["gate_3_task_id"]), "--machine"
            ),
            "review_contract_document": _run_ak(
                "task",
                "contract",
                "show",
                str(ledger["gate_3_task_id"]),
                "-F",
                "json",
            ),
            "live_task_document": _run_ak(
                "task", "show", str(live_task_id), "--machine"
            ),
            "live_contract_document": _run_ak(
                "task", "contract", "show", str(live_task_id), "-F", "json"
            ),
            "remediation_validation_evidence_document": _run_ak(
                "evidence",
                "show",
                str(ledger["remediation_validation_evidence_id"]),
                "--machine",
            ),
            "review_evidence_document": _run_ak(
                "evidence",
                "show",
                str(ledger["candidate_review_evidence_id"]),
                "--machine",
            ),
            "operator_evidence_document": _run_ak(
                "evidence",
                "show",
                str(ledger["operator_evidence_id"]),
                "--machine",
            ),
            "live_gate_evidence_document": _run_ak(
                "evidence",
                "show",
                str(ledger["live_gate_evidence_id"]),
                "--machine",
            ),
            "live_task_evidence_set_document": _run_ak(
                "evidence", "task", str(live_task_id), "--machine"
            ),
            "gate5_task_document": _run_ak(
                "task", "show", str(gate5_task_id), "--machine"
            ),
            "gate5_contract_document": _run_ak(
                "task", "contract", "show", str(gate5_task_id), "-F", "json"
            ),
            "gate5_evidence_document": _run_ak(
                "evidence", "show", str(gate5_evidence_id), "--machine"
            ),
            "gate5_evidence_set_document": _run_ak(
                "evidence", "task", str(gate5_task_id), "--machine"
            ),
        }

        reason_code = "authority_reconstruction_rejected"
        reconstructed_review, reconstructed_gate, snapshot_sha = (
            reconstruct_authority_payloads(
                repo_root=repo_root,
                state_root_identity_sha256=(attempt.binding.state_root_identity_sha256),
                ledger=attempt.ledger,
                commit=commit,
                tree=tree,
                source_manifest=manifest,
                documents=documents,
            )
        )
        if (
            review != reconstructed_review
            or gate != reconstructed_gate
            or review_raw != _canonical(reconstructed_review)
            or gate_raw != _canonical(reconstructed_gate)
            or snapshot_sha != attempt.ledger["authority_snapshot_sha256"]
            or manifest != reconstructed_review["candidate_source_manifest"]
        ):
            raise SemanticV11Error(
                "Gate-5 retained authority payload reconstruction drift"
            )

        reason_code = "gate5_authorization_rejected"
        authority = _validate_gate5_documents(
            repo_root=repo_root,
            attempt=attempt,
            result_sha256=_sha(retained_raw),
            gate5_task_id=gate5_task_id,
            gate5_evidence_id=gate5_evidence_id,
            task_document=documents["gate5_task_document"],
            contract_document=documents["gate5_contract_document"],
            evidence_document=documents["gate5_evidence_document"],
            evidence_set_document=documents["gate5_evidence_set_document"],
        )
        facts["gate5_task_contract_sha256"] = authority.task_contract_sha256
        facts["gate5_guardrails_sha256"] = authority.guardrails_sha256
        facts["gate5_evidence_sha256"] = authority.evidence_sha256

        reason_code = "runtime_origin_rejected"
        _verify_loaded_origins(repo_root, manifest)
        reason_code = "owner_identity_rejected"
        artifact = _verify_owner(owner_source_root)
        reason_code = "result_reconstruction_rejected"
        derived = independently_rederive_result(
            repo_root=repo_root, attempt=attempt, artifact=artifact
        )
        if retained != derived or retained_raw != _canonical(derived):
            reason_code = "result_comparison_rejected"
            raise SemanticV11Error("Gate-5 retained result comparison drift")

        from dspx.services.program_oracle_semantic_verification_v11 import (
            verify_private_tree,
        )

        reason_code = "retained_tree_rejected"
        before_privacy = verify_private_tree(attempt, include_verification=False)
        reason_code = "accepted_payload_derivation_rejected"
        payload = {
            "schema_version": VERIFICATION_SCHEMA,
            "artifact_kind": "independent_verification",
            "gate5_task_id": gate5_task_id,
            "gate5_evidence_id": gate5_evidence_id,
            "gate5_task_contract_sha256": authority.task_contract_sha256,
            "gate5_guardrails_sha256": authority.guardrails_sha256,
            "gate5_evidence_sha256": authority.evidence_sha256,
            "live_task_id": live_task_id,
            "artifact_integrity_review": "accepted",
            "empirical_gate": derived["empirical_gate"],
            "result_sha256": _sha(retained_raw),
            "ledger_sha256": attempt.ledger_sha256,
            "candidate_review_sha256": _sha(review_raw),
            "live_gate_sha256": _sha(gate_raw),
            "candidate_commit": derived["candidate_commit"],
            "candidate_tree": derived["candidate_tree"],
            "candidate_source_manifest_sha256": derived[
                "candidate_source_manifest_sha256"
            ],
            "contract_sha256": CONTRACT_SHA256,
            "provider_owner_source_identity_sha256": derived[
                "provider_owner_source_identity_sha256"
            ],
            "dependency_identity_sha256": derived["dependency_identity_sha256"],
            "operation_counts": derived["operation_counts"],
            "privacy": {},
            "provider_invoked": False,
            "terminal_evidence_modified": False,
            "fixture_only": False,
            "v11_authorized": False,
            "live_execution_authorized": False,
            "authority_granted": False,
        }
        payload = _with_final_privacy(payload, before_privacy)
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, IndexError):
        return _persist_rejected_once(
            attempt_root=attempt_root,
            live_task_id=live_task_id,
            gate5_task_id=gate5_task_id,
            gate5_evidence_id=gate5_evidence_id,
            reason_code=reason_code,
            facts=facts,
        )

    terminal_before = (
        attempt.ledger_sha256,
        _sha(review_raw),
        _sha(gate_raw),
        _sha(retained_raw),
    )
    verification_path = attempt.attempt_root / VERIFICATION_NAME
    try:
        _state_io._persist_no_replace(verification_path, payload)
    except (OSError, SemanticV11Error) as exc:
        raise Gate5PersistenceError(
            "acceptance_persistence_failed",
            started_marker_consumed=True,
        ) from exc
    try:
        final_privacy = _validate_written_verification(attempt, payload)
        after_attempt = load_consumed_attempt(state_root, live_task_id)
        after_result, after_result_raw = load_evaluation_result(after_attempt)
        _, after_review_raw, _, after_gate_raw = load_authority_artifacts(after_attempt)
        terminal_after = (
            after_attempt.ledger_sha256,
            _sha(after_review_raw),
            _sha(after_gate_raw),
            _sha(after_result_raw),
        )
        if (
            terminal_before != terminal_after
            or after_result != retained
            or final_privacy != payload["privacy"]
        ):
            raise SemanticV11Error("Gate-5 post-write verification drift")
    except (OSError, SemanticV11Error) as exc:
        raise Gate5PersistenceError(
            "acceptance_readback_failed",
            started_marker_consumed=True,
            verification_retained=verification_path.exists(),
        ) from exc
    return payload

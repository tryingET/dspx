# summary: "Independent Gate-5 reconstruction from canonical AK execution evidence."
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from dspx.services.program_oracle_semantic_evidence_v11 import (
    GATE2_EVIDENCE_IDS,
    canonical_evidence_record,
    evidence_binding,
    execution_evidence_binding,
    gate2_evidence_bindings,
)
from dspx.services.program_oracle_semantic_gate4_contract_v11 import (
    CANDIDATE_REVIEW_SCHEMA,
    CONSUMER_MODULE_HASHES,
    CONTRACT_SHA256,
    EXACT_ROUTE,
    GATE2_BASE_COMMIT,
    GATE2_BASE_TREE,
    GATE2_DONE_CONTRACT,
    GATE2_GUARDRAILS,
    GATE2_SCOPE_SHA256,
    GATE2_TASK_ID,
    GATE3_DONE_CONTRACT,
    GATE3_GUARDRAILS,
    GATE4_DONE_CONTRACT,
    GATE4_GUARDRAILS,
    LIVE_GATE_SCHEMA,
    PROPOSAL_SHA256,
    REMEDIATION_DONE_CONTRACT,
    REMEDIATION_GUARDRAILS,
    REMEDIATION_SCOPE_SHA256,
    REMEDIATION_TASK_ID,
    SemanticV11Error,
    canonical,
    sha256,
)

_REVIEW_EVIDENCE_SCHEMA = "dspx-oracle-semantic-v11-candidate-review-evidence-v2"


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SemanticV11Error(f"Gate-5 {label} must be an object")
    return {str(key): item for key, item in value.items()}


def _machine(value: object, surface: str) -> dict[str, Any]:
    envelope = _mapping(value, f"{surface} envelope")
    if (
        envelope.get("surface") != surface
        or envelope.get("ok") is not True
        or envelope.get("error") is not None
    ):
        raise SemanticV11Error("Gate-5 canonical AK envelope rejected")
    return _mapping(envelope.get("payload"), f"{surface} payload")


def _repo(value: object, expected: Path) -> bool:
    try:
        return (
            isinstance(value, str)
            and Path(value).expanduser().resolve(strict=True) == expected
        )
    except OSError:
        return False


def _task(
    document: Mapping[str, Any], task_id: int, repo: Path, statuses: set[str]
) -> dict[str, Any]:
    task = _mapping(_machine(document, "task.show").get("task"), "task")
    version = task.get("entity_version")
    if (
        task.get("id") != task_id
        or task.get("status") not in statuses
        or not _repo(task.get("repo"), repo)
        or isinstance(version, bool)
        or not isinstance(version, int)
        or version <= 0
    ):
        raise SemanticV11Error("Gate-5 canonical prior task rejected")
    return task


def _contract(
    document: Mapping[str, Any],
    task_id: int,
    repo: Path,
    status: str,
    expected_done: Mapping[str, Any],
    expected_guard: Mapping[str, Any],
) -> tuple[str, str]:
    value = dict(document)
    done = _mapping(value.get("done_contract"), "done-contract version")
    guard = _mapping(value.get("guardrails"), "guardrail version")
    versions = (done.get("entity_version"), guard.get("entity_version"))
    if (
        set(value) != {"task_id", "repo", "status", "done_contract", "guardrails"}
        or set(done) != {"task_id", "contract", "entity_version"}
        or set(guard) != {"task_id", "guardrails", "entity_version"}
        or value.get("task_id") != task_id
        or value.get("status") != status
        or not _repo(value.get("repo"), repo)
        or done.get("task_id") != task_id
        or guard.get("task_id") != task_id
        or done.get("contract") != dict(expected_done)
        or guard.get("guardrails") != dict(expected_guard)
        or any(
            isinstance(item, bool) or not isinstance(item, int) or item <= 0
            for item in versions
        )
    ):
        raise SemanticV11Error("Gate-5 exact prior task contract rejected")
    return sha256(canonical(done)), sha256(canonical(guard))


def _evidence(
    document: Mapping[str, Any], evidence_id: int, task_id: int, check_type: str
) -> dict[str, Any]:
    evidence = _mapping(_machine(document, "evidence.show").get("evidence"), "evidence")
    if (
        evidence.get("id") != evidence_id
        or evidence.get("task_ref") != task_id
        or evidence.get("check_type") != check_type
        or evidence.get("result") != "pass"
        or not isinstance(evidence.get("details"), Mapping)
    ):
        raise SemanticV11Error("Gate-5 canonical prior evidence rejected")
    return evidence


def _canonical_record(
    document: Mapping[str, Any],
    evidence_id: int,
    task_id: int,
    check_type: str | None = None,
) -> dict[str, Any]:
    return canonical_evidence_record(
        _machine(document, "evidence.show").get("evidence"),
        evidence_id=evidence_id,
        task_id=task_id,
        check_type=check_type,
    )


def reconstruct_authority_payloads(
    *,
    repo_root: Path,
    state_root_identity_sha256: str,
    ledger: Mapping[str, Any],
    commit: str,
    tree: str,
    source_manifest: Mapping[str, str],
    documents: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Reconstruct from canonical records; ledger bytes are comparison-only."""

    repo = repo_root.expanduser().resolve(strict=True)
    source_sha = sha256(canonical(source_manifest))
    live_task_id = ledger.get("live_task_id")
    if isinstance(live_task_id, bool) or not isinstance(live_task_id, int):
        raise SemanticV11Error("Gate-5 live task selector rejected")
    gate2_task = _task(documents["gate_2_task_document"], GATE2_TASK_ID, repo, {"done"})
    remediation_task = _task(
        documents["remediation_task_document"], REMEDIATION_TASK_ID, repo, {"done"}
    )
    review_raw = _mapping(
        _machine(documents["review_evidence_document"], "evidence.show").get(
            "evidence"
        ),
        "review evidence",
    )
    review_task_id = review_raw.get("task_ref")
    if isinstance(review_task_id, bool) or not isinstance(review_task_id, int):
        raise SemanticV11Error("Gate-5 Gate-3 selector rejected")
    review_task = _task(
        documents["review_task_document"], review_task_id, repo, {"done"}
    )
    live_task = _task(
        documents["live_task_document"], live_task_id, repo, {"claimed", "running"}
    )
    if len({GATE2_TASK_ID, REMEDIATION_TASK_ID, review_task_id, live_task_id}) != 4:
        raise SemanticV11Error("Gate-5 prior task separation drift")
    gate2_contract, gate2_guard = _contract(
        documents["gate_2_contract_document"],
        GATE2_TASK_ID,
        repo,
        "done",
        GATE2_DONE_CONTRACT,
        GATE2_GUARDRAILS,
    )
    remediation_contract, remediation_guard = _contract(
        documents["remediation_contract_document"],
        REMEDIATION_TASK_ID,
        repo,
        "done",
        REMEDIATION_DONE_CONTRACT,
        REMEDIATION_GUARDRAILS,
    )
    review_contract, review_guard = _contract(
        documents["review_contract_document"],
        review_task_id,
        repo,
        "done",
        GATE3_DONE_CONTRACT,
        GATE3_GUARDRAILS,
    )
    live_contract, live_guard = _contract(
        documents["live_contract_document"],
        live_task_id,
        repo,
        str(live_task["status"]),
        GATE4_DONE_CONTRACT,
        GATE4_GUARDRAILS,
    )

    gate2_records = (
        _canonical_record(
            documents["gate_2_evidence_6729_document"],
            GATE2_EVIDENCE_IDS[0],
            GATE2_TASK_ID,
        ),
        _canonical_record(
            documents["gate_2_evidence_6730_document"],
            GATE2_EVIDENCE_IDS[1],
            GATE2_TASK_ID,
        ),
    )
    gate2_bindings = gate2_evidence_bindings(gate2_records)
    gate2_set_sha = sha256(canonical(list(gate2_records)))
    remediation_raw = _mapping(
        _machine(
            documents["remediation_validation_evidence_document"], "evidence.show"
        ).get("evidence"),
        "remediation evidence",
    )
    remediation_id = remediation_raw.get("id")
    if isinstance(remediation_id, bool) or not isinstance(remediation_id, int):
        raise SemanticV11Error("Gate-5 remediation selector rejected")
    remediation = _canonical_record(
        documents["remediation_validation_evidence_document"],
        remediation_id,
        REMEDIATION_TASK_ID,
        "oracle_semantic_v11_remediation_validation",
    )
    execution_evidence_binding(
        remediation,
        artifact_kind="remediation_validation",
        task_id=REMEDIATION_TASK_ID,
        commit=commit,
        tree=tree,
        source_manifest_sha256=source_sha,
    )
    review_id = review_raw.get("id")
    if isinstance(review_id, bool) or not isinstance(review_id, int):
        raise SemanticV11Error("Gate-5 review selector rejected")
    review_evidence = _canonical_record(
        documents["review_evidence_document"],
        review_id,
        review_task_id,
        "oracle_semantic_v11_candidate_review",
    )
    details = _mapping(review_evidence.get("details"), "review details")
    if (
        set(details)
        != {
            "schema_version",
            "artifact_kind",
            "candidate_review",
            "validation_evidence",
        }
        or details.get("schema_version") != _REVIEW_EVIDENCE_SCHEMA
        or details.get("artifact_kind") != "candidate_review_evidence"
    ):
        raise SemanticV11Error("Gate-5 Gate-3 evidence schema drift")
    gate3_validation = execution_evidence_binding(
        {"details": _mapping(details.get("validation_evidence"), "Gate-3 validation")},
        artifact_kind="gate_3_validation",
        task_id=review_task_id,
        commit=commit,
        tree=tree,
        source_manifest_sha256=source_sha,
    )
    review = {
        "schema_version": CANDIDATE_REVIEW_SCHEMA,
        "artifact_kind": "candidate_review",
        "gate_2_task_id": GATE2_TASK_ID,
        "remediation_task_id": REMEDIATION_TASK_ID,
        "gate_3_task_id": review_task_id,
        "gate_2_candidate_commit": GATE2_BASE_COMMIT,
        "gate_2_candidate_tree": GATE2_BASE_TREE,
        "gate_2_scope_sha256": GATE2_SCOPE_SHA256,
        "remediation_scope_sha256": REMEDIATION_SCOPE_SHA256,
        "gate_2_task_contract_sha256": gate2_contract,
        "gate_2_guardrails_sha256": gate2_guard,
        "remediation_task_contract_sha256": remediation_contract,
        "remediation_guardrails_sha256": remediation_guard,
        "gate_3_task_contract_sha256": review_contract,
        "gate_3_guardrails_sha256": review_guard,
        "gate_2_evidence_bindings": list(gate2_bindings),
        "gate_2_evidence_set_sha256": gate2_set_sha,
        "remediation_validation_evidence_binding": evidence_binding(remediation),
        "gate_3_validation_evidence": gate3_validation,
        "decision": "ACCEPT_V11_CANDIDATE_FOR_SEPARATE_LIVE_GATE",
        "contract_sha256": CONTRACT_SHA256,
        "proposal_sha256": PROPOSAL_SHA256,
        "candidate_commit": commit,
        "candidate_tree": tree,
        "candidate_source_manifest": dict(source_manifest),
        "candidate_source_manifest_sha256": source_sha,
        "accepted_consumer_module_sha256": CONSUMER_MODULE_HASHES,
        "provider_operations": 0,
    }
    if details.get("candidate_review") != review:
        raise SemanticV11Error("Gate-5 complete candidate-review reconstruction drift")
    review_sha = sha256(canonical(review))
    operator_id = ledger.get("operator_evidence_id")
    gate_id = ledger.get("live_gate_evidence_id")
    if any(
        isinstance(item, bool) or not isinstance(item, int)
        for item in (operator_id, gate_id)
    ):
        raise SemanticV11Error("Gate-5 live evidence selectors rejected")
    operator_id = cast(int, operator_id)
    gate_id = cast(int, gate_id)
    operator = _evidence(
        documents["operator_evidence_document"],
        operator_id,
        live_task_id,
        "oracle_semantic_v11_operator_authorization",
    )
    expected_operator = {
        "schema_version": LIVE_GATE_SCHEMA,
        "artifact_kind": "operator_authorization",
        "live_task_id": live_task_id,
        "state_root_identity_sha256": state_root_identity_sha256,
        "candidate_review_evidence_id": review_id,
        "candidate_review_sha256": review_sha,
        "decision": "AUTHORIZE_EXACTLY_ONE_V11_CORPUS_PROCESS",
        "route": EXACT_ROUTE,
        "maximum_corpus_processes": 1,
        "maximum_effect_capable_delegations_per_request": 1,
        "maximum_health_probes": 0,
        "maximum_dspx_managed_retries": 0,
        "fallback_allowed": False,
    }
    if operator.get("details") != expected_operator:
        raise SemanticV11Error("Gate-5 operator reconstruction drift")
    gate_evidence = _evidence(
        documents["live_gate_evidence_document"],
        gate_id,
        live_task_id,
        "oracle_semantic_v11_live_gate",
    )
    gate = {
        "schema_version": LIVE_GATE_SCHEMA,
        "artifact_kind": "live_gate",
        "live_task_id": live_task_id,
        "gate_3_task_id": review_task_id,
        "state_root_identity_sha256": state_root_identity_sha256,
        "task_entity_version": live_task["entity_version"],
        "gate_4_task_contract_sha256": live_contract,
        "gate_4_guardrails_sha256": live_guard,
        "candidate_review_evidence_id": review_id,
        "candidate_review_sha256": review_sha,
        "operator_evidence_id": operator_id,
        "operator_evidence_sha256": sha256(canonical(operator)),
        "candidate_commit": commit,
        "candidate_tree": tree,
        "candidate_source_manifest_sha256": source_sha,
        "contract_sha256": CONTRACT_SHA256,
        "route": EXACT_ROUTE,
        "maximum_corpus_processes": 1,
        "maximum_effect_capable_delegations_per_request": 1,
        "maximum_health_probes": 0,
        "maximum_dspx_managed_retries": 0,
        "fallback_allowed": False,
    }
    if gate_evidence.get("details") != gate:
        raise SemanticV11Error("Gate-5 complete live-gate reconstruction drift")
    evidence_set = _machine(
        documents["live_task_evidence_set_document"], "evidence.task"
    )
    rows = evidence_set.get("evidence")
    if not isinstance(rows, list):
        raise SemanticV11Error("Gate-5 Gate-4 evidence-set drift")
    operators = [
        row
        for row in rows
        if isinstance(row, Mapping)
        and row.get("check_type") == "oracle_semantic_v11_operator_authorization"
    ]
    gates = [
        row
        for row in rows
        if isinstance(row, Mapping)
        and row.get("check_type") == "oracle_semantic_v11_live_gate"
    ]
    if (
        evidence_set.get("task_id") != live_task_id
        or evidence_set.get("count") != len(rows)
        or len(operators) != 1
        or len(gates) != 1
        or dict(operators[0]) != operator
        or dict(gates[0]) != gate_evidence
    ):
        raise SemanticV11Error("Gate-5 Gate-4 evidence-pair cardinality drift")
    evidence_set_sha = sha256(canonical(evidence_set))
    snapshot = {
        "gate_2_task_sha256": sha256(canonical(gate2_task)),
        "remediation_task_sha256": sha256(canonical(remediation_task)),
        "gate_3_task_sha256": sha256(canonical(review_task)),
        "gate_4_task_sha256": sha256(canonical(live_task)),
        "gate_2_evidence_digests": [item["evidence_sha256"] for item in gate2_bindings],
        "gate_2_evidence_set_sha256": gate2_set_sha,
        "remediation_validation_evidence_sha256": sha256(canonical(remediation)),
        "candidate_review_evidence_sha256": sha256(canonical(review_evidence)),
        "operator_evidence_sha256": sha256(canonical(operator)),
        "live_gate_evidence_sha256": sha256(canonical(gate_evidence)),
        "gate_4_evidence_set_sha256": evidence_set_sha,
    }
    expected_ledger = {
        "candidate_commit": commit,
        "candidate_tree": tree,
        "candidate_source_manifest_sha256": source_sha,
        "contract_sha256": CONTRACT_SHA256,
        "candidate_review_sha256": review_sha,
        "live_gate_sha256": sha256(canonical(gate)),
        "authority_snapshot_sha256": sha256(canonical(snapshot)),
        "gate_4_evidence_set_sha256": evidence_set_sha,
        "gate_2_task_contract_sha256": gate2_contract,
        "gate_2_guardrails_sha256": gate2_guard,
        "remediation_task_contract_sha256": remediation_contract,
        "remediation_guardrails_sha256": remediation_guard,
        "gate_3_task_id": review_task_id,
        "gate_3_task_contract_sha256": review_contract,
        "gate_3_guardrails_sha256": review_guard,
        "gate_4_task_contract_sha256": live_contract,
        "gate_4_guardrails_sha256": live_guard,
        "gate_2_evidence_ids": list(GATE2_EVIDENCE_IDS),
        "gate_2_evidence_digests": [item["evidence_sha256"] for item in gate2_bindings],
        "gate_2_evidence_set_sha256": gate2_set_sha,
        "remediation_validation_evidence_id": remediation_id,
        "candidate_review_evidence_id": review_id,
        "operator_evidence_id": operator_id,
        "live_gate_evidence_id": gate_id,
    }
    if any(ledger.get(key) != value for key, value in expected_ledger.items()):
        raise SemanticV11Error("Gate-5 canonical authority/ledger reconstruction drift")
    return review, gate, sha256(canonical(snapshot))

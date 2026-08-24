# summary: "Pure authority-false Gate-4 mapping validation and source identity checks."
from __future__ import annotations

import stat
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dspx.services.program_oracle_semantic_authority_v11 import (
    evidence_document,
    evidence_set_document,
    full_task_contract,
    machine_payload,
    task_document,
)
from dspx.services.program_oracle_semantic_evidence_v11 import (
    GATE2_EVIDENCE_IDS,
    canonical_evidence_record,
    evidence_binding,
    execution_evidence_binding,
    gate2_evidence_bindings,
)
from dspx.services.program_oracle_semantic_gate4_contract_v11 import (
    CANDIDATE_REVIEW_SCHEMA,
    CANDIDATE_SOURCE_PATHS,
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
    RUNTIME_SUPPORT_SOURCE_PATHS,
    SemanticV11Error,
    canonical,
    sha256,
)
from dspx.services.program_oracle_semantic_state_v11 import state_root_identity_sha256

_REVIEW_EVIDENCE_SCHEMA = "dspx-oracle-semantic-v11-candidate-review-evidence-v2"
_GIT_ID_LENGTH = 40


def candidate_source_manifest(repo_root: Path) -> dict[str, str]:
    root = repo_root.expanduser().resolve(strict=True)
    paths = tuple(
        dict.fromkeys((*CANDIDATE_SOURCE_PATHS, *RUNTIME_SUPPORT_SOURCE_PATHS))
    )
    manifest: dict[str, str] = {}
    for relative in paths:
        path = root / relative
        try:
            info, raw = path.lstat(), path.read_bytes()
        except OSError as exc:
            raise SemanticV11Error("candidate source member unavailable") from exc
        if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise SemanticV11Error("candidate source member posture drift")
        manifest[relative] = sha256(raw)
    return manifest


def candidate_source_manifest_sha256(repo_root: Path) -> str:
    return sha256(canonical(candidate_source_manifest(repo_root)))


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=False,
        capture_output=True,
        timeout=30,
        env={"HOME": str(Path.home()), "PATH": "/usr/bin:/bin"},
    )


def _git_identity(repo_root: Path) -> tuple[str, str]:
    root = repo_root.expanduser().resolve(strict=True)
    commit_result = _git(root, "rev-parse", "HEAD")
    tree_result = _git(root, "rev-parse", "HEAD^{tree}")
    paths = tuple(
        dict.fromkeys((*CANDIDATE_SOURCE_PATHS, *RUNTIME_SUPPORT_SOURCE_PATHS))
    )
    checks = (
        _git(root, "diff", "--quiet", "HEAD", "--", *paths),
        _git(root, "diff", "--cached", "--quiet", "--", *paths),
        _git(root, "ls-files", "--others", "--exclude-standard", "--", *paths),
    )
    if any(item.returncode for item in (*checks[:2], commit_result, tree_result)) or (
        checks[2].returncode or checks[2].stdout.strip()
    ):
        raise SemanticV11Error("reviewed candidate source is not commit-clean")
    try:
        commit = commit_result.stdout.decode("ascii").strip()
        tree = tree_result.stdout.decode("ascii").strip()
    except UnicodeError as exc:
        raise SemanticV11Error("candidate Git identity unavailable") from exc
    if (
        len(commit) != _GIT_ID_LENGTH
        or len(tree) != _GIT_ID_LENGTH
        or any(char not in "0123456789abcdef" for char in commit + tree)
    ):
        raise SemanticV11Error("candidate Git identity drift")
    return commit, tree


def _details(evidence: Mapping[str, Any]) -> dict[str, Any]:
    value = evidence.get("details")
    if not isinstance(value, Mapping):
        raise SemanticV11Error("AK evidence details rejected")
    return dict(value)


def _status(value: object) -> str:
    if value not in {"claimed", "running"}:
        raise SemanticV11Error("Gate-4 task status drift")
    return str(value)


def _canonical_record(
    document: Mapping[str, Any],
    evidence_id: int,
    task_id: int,
    check_type: str | None = None,
) -> dict[str, Any]:
    payload = machine_payload(document, "evidence.show")
    return canonical_evidence_record(
        payload.get("evidence"),
        evidence_id=evidence_id,
        task_id=task_id,
        check_type=check_type,
    )


def _derive_gate4_documents(
    *,
    repo_root: Path,
    state_root: Path,
    live_task_id: int,
    remediation_validation_evidence_id: int,
    review_evidence_id: int,
    operator_evidence_id: int,
    live_gate_evidence_id: int,
    gate_2_task_document: Mapping[str, Any],
    gate_2_contract_document: Mapping[str, Any],
    gate_2_evidence_6729_document: Mapping[str, Any],
    gate_2_evidence_6730_document: Mapping[str, Any],
    remediation_task_document: Mapping[str, Any],
    remediation_contract_document: Mapping[str, Any],
    review_task_document: Mapping[str, Any],
    review_contract_document: Mapping[str, Any],
    live_task_document: Mapping[str, Any],
    live_contract_document: Mapping[str, Any],
    remediation_validation_evidence_document: Mapping[str, Any],
    review_evidence_document: Mapping[str, Any],
    operator_evidence_document: Mapping[str, Any],
    live_gate_evidence_document: Mapping[str, Any],
    live_task_evidence_set_document: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Derive exact facts from mappings; this function grants no authority."""
    selectors = (
        remediation_validation_evidence_id,
        review_evidence_id,
        operator_evidence_id,
        live_gate_evidence_id,
    )
    if (
        isinstance(live_task_id, bool)
        or not isinstance(live_task_id, int)
        or live_task_id <= 0
        or any(
            isinstance(item, bool) or not isinstance(item, int) or item <= 0
            for item in selectors
        )
        or len({*selectors, *GATE2_EVIDENCE_IDS})
        != len(selectors) + len(GATE2_EVIDENCE_IDS)
    ):
        raise SemanticV11Error("Gate-4 AK selectors rejected")
    root = repo_root.expanduser().resolve(strict=True)
    state_identity = state_root_identity_sha256(state_root)
    commit, tree = _git_identity(root)
    source_manifest = candidate_source_manifest(root)
    source_sha = sha256(canonical(source_manifest))
    if (
        source_manifest.get("governance/task-scopes/AK-4691.snapshot.json")
        != GATE2_SCOPE_SHA256
        or source_manifest.get("governance/task-scopes/AK-4713.snapshot.json")
        != REMEDIATION_SCOPE_SHA256
    ):
        raise SemanticV11Error("exact task-scope snapshot drift")

    gate2_task = task_document(
        gate_2_task_document, task_id=GATE2_TASK_ID, repo_root=root, statuses={"done"}
    )
    remediation_task = task_document(
        remediation_task_document,
        task_id=REMEDIATION_TASK_ID,
        repo_root=root,
        statuses={"done"},
    )
    unchecked_review = machine_payload(review_evidence_document, "evidence.show").get(
        "evidence"
    )
    if not isinstance(unchecked_review, Mapping):
        raise SemanticV11Error("Gate-3 task selector rejected")
    review_task_id = unchecked_review.get("task_ref")
    if isinstance(review_task_id, bool) or not isinstance(review_task_id, int):
        raise SemanticV11Error("Gate-3 task selector rejected")
    task_selectors = {GATE2_TASK_ID, REMEDIATION_TASK_ID, review_task_id, live_task_id}
    evidence_selectors = {*GATE2_EVIDENCE_IDS, *selectors}
    if len(task_selectors) != 4:
        raise SemanticV11Error("Gate tasks must be distinct")
    if not task_selectors.isdisjoint(evidence_selectors):
        raise SemanticV11Error("Gate task/evidence selectors must be distinct")
    review_task = task_document(
        review_task_document, task_id=review_task_id, repo_root=root, statuses={"done"}
    )
    live_task = task_document(
        live_task_document,
        task_id=live_task_id,
        repo_root=root,
        statuses={"claimed", "running"},
    )
    _, gate2_contract, gate2_guard = full_task_contract(
        gate_2_contract_document,
        task_id=GATE2_TASK_ID,
        repo_root=root,
        status="done",
        done_contract=GATE2_DONE_CONTRACT,
        guardrails=GATE2_GUARDRAILS,
    )
    _, remediation_contract, remediation_guard = full_task_contract(
        remediation_contract_document,
        task_id=REMEDIATION_TASK_ID,
        repo_root=root,
        status="done",
        done_contract=REMEDIATION_DONE_CONTRACT,
        guardrails=REMEDIATION_GUARDRAILS,
    )
    _, review_contract, review_guard = full_task_contract(
        review_contract_document,
        task_id=review_task_id,
        repo_root=root,
        status="done",
        done_contract=GATE3_DONE_CONTRACT,
        guardrails=GATE3_GUARDRAILS,
    )
    _, live_contract, live_guard = full_task_contract(
        live_contract_document,
        task_id=live_task_id,
        repo_root=root,
        status=_status(live_task["status"]),
        done_contract=GATE4_DONE_CONTRACT,
        guardrails=GATE4_GUARDRAILS,
    )

    gate2_records = (
        _canonical_record(
            gate_2_evidence_6729_document, GATE2_EVIDENCE_IDS[0], GATE2_TASK_ID
        ),
        _canonical_record(
            gate_2_evidence_6730_document, GATE2_EVIDENCE_IDS[1], GATE2_TASK_ID
        ),
    )
    gate2_bindings = gate2_evidence_bindings(gate2_records)
    gate2_set_sha = sha256(canonical(list(gate2_records)))
    remediation = _canonical_record(
        remediation_validation_evidence_document,
        remediation_validation_evidence_id,
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
    review_evidence = _canonical_record(
        review_evidence_document,
        review_evidence_id,
        review_task_id,
        "oracle_semantic_v11_candidate_review",
    )
    review_details = _details(review_evidence)
    if (
        set(review_details)
        != {
            "schema_version",
            "artifact_kind",
            "candidate_review",
            "validation_evidence",
        }
        or review_details.get("schema_version") != _REVIEW_EVIDENCE_SCHEMA
        or review_details.get("artifact_kind") != "candidate_review_evidence"
        or not isinstance(review_details.get("candidate_review"), Mapping)
        or not isinstance(review_details.get("validation_evidence"), Mapping)
    ):
        raise SemanticV11Error("canonical Gate-3 evidence schema rejected")
    gate3_validation = execution_evidence_binding(
        {"details": review_details["validation_evidence"]},
        artifact_kind="gate_3_validation",
        task_id=review_task_id,
        commit=commit,
        tree=tree,
        source_manifest_sha256=source_sha,
    )
    expected_review = {
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
        "candidate_source_manifest": source_manifest,
        "candidate_source_manifest_sha256": source_sha,
        "accepted_consumer_module_sha256": CONSUMER_MODULE_HASHES,
        "provider_operations": 0,
    }
    if dict(review_details["candidate_review"]) != expected_review:
        raise SemanticV11Error("canonical Gate-3 acceptance evidence rejected")
    review_sha = sha256(canonical(expected_review))
    operator = evidence_document(
        operator_evidence_document,
        expected_id=operator_evidence_id,
        expected_task=live_task_id,
        check_type="oracle_semantic_v11_operator_authorization",
    )
    expected_operator = {
        "schema_version": LIVE_GATE_SCHEMA,
        "artifact_kind": "operator_authorization",
        "live_task_id": live_task_id,
        "state_root_identity_sha256": state_identity,
        "candidate_review_evidence_id": review_evidence_id,
        "candidate_review_sha256": review_sha,
        "decision": "AUTHORIZE_EXACTLY_ONE_V11_CORPUS_PROCESS",
        "route": EXACT_ROUTE,
        "maximum_corpus_processes": 1,
        "maximum_effect_capable_delegations_per_request": 1,
        "maximum_health_probes": 0,
        "maximum_dspx_managed_retries": 0,
        "fallback_allowed": False,
    }
    if _details(operator) != expected_operator:
        raise SemanticV11Error("canonical operator authorization rejected")
    gate_evidence = evidence_document(
        live_gate_evidence_document,
        expected_id=live_gate_evidence_id,
        expected_task=live_task_id,
        check_type="oracle_semantic_v11_live_gate",
    )
    expected_gate = {
        "schema_version": LIVE_GATE_SCHEMA,
        "artifact_kind": "live_gate",
        "live_task_id": live_task_id,
        "gate_3_task_id": review_task_id,
        "state_root_identity_sha256": state_identity,
        "task_entity_version": live_task["entity_version"],
        "gate_4_task_contract_sha256": live_contract,
        "gate_4_guardrails_sha256": live_guard,
        "candidate_review_evidence_id": review_evidence_id,
        "candidate_review_sha256": review_sha,
        "operator_evidence_id": operator_evidence_id,
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
    if _details(gate_evidence) != expected_gate:
        raise SemanticV11Error("canonical Gate-4 live-gate evidence rejected")
    _, evidence_set_sha = evidence_set_document(
        live_task_evidence_set_document,
        live_task_id=live_task_id,
        operator_evidence=operator,
        live_gate_evidence=gate_evidence,
    )
    gate_sha = sha256(canonical(expected_gate))
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
    facts = {
        "live_task_id": live_task_id,
        "state_root_identity_sha256": state_identity,
        "candidate_commit": commit,
        "candidate_tree": tree,
        "candidate_source_manifest_sha256": source_sha,
        "contract_sha256": CONTRACT_SHA256,
        "candidate_review_sha256": review_sha,
        "live_gate_sha256": gate_sha,
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
        "remediation_validation_evidence_id": remediation_validation_evidence_id,
        "candidate_review_evidence_id": review_evidence_id,
        "operator_evidence_id": operator_evidence_id,
        "live_gate_evidence_id": live_gate_evidence_id,
    }
    return facts, expected_review, expected_gate


def validate_gate4_authority_documents(**kwargs: Any) -> dict[str, Any]:
    """Pure mapping validator; its returned projection is authority-false."""

    facts, review, gate = _derive_gate4_documents(**kwargs)
    return {
        "facts": dict(facts),
        "candidate_review": dict(review),
        "live_gate": dict(gate),
        "facts_sha256": sha256(canonical(facts)),
        "candidate_review_sha256": sha256(canonical(review)),
        "live_gate_sha256": sha256(canonical(gate)),
        "fixture_only": True,
        "v11_authorized": False,
        "live_execution_authorized": False,
        "authority_granted": False,
    }

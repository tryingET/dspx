# summary: "Exact privacy-safe candidate-review retained grammar."
from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any

from dspx.services.program_oracle_semantic_evidence_v11 import (
    EVIDENCE_BINDING_KEYS,
    EXECUTION_BINDING_KEYS,
    GATE2_EVIDENCE_IDS,
)
from dspx.services.program_oracle_semantic_gate4_contract_v11 import (
    CANDIDATE_REVIEW_SCHEMA,
    CANDIDATE_SOURCE_PATHS,
    CONSUMER_MODULE_HASHES,
    CONTRACT_SHA256,
    GATE2_BASE_COMMIT,
    GATE2_BASE_TREE,
    GATE2_SCOPE_SHA256,
    GATE2_TASK_ID,
    PROPOSAL_SHA256,
    REMEDIATION_SCOPE_SHA256,
    REMEDIATION_TASK_ID,
    RUNTIME_SUPPORT_SOURCE_PATHS,
    canonical,
    sha256,
)

_REVIEW_KEYS = {
    "schema_version",
    "artifact_kind",
    "gate_2_task_id",
    "remediation_task_id",
    "gate_3_task_id",
    "gate_2_candidate_commit",
    "gate_2_candidate_tree",
    "gate_2_scope_sha256",
    "remediation_scope_sha256",
    "gate_2_task_contract_sha256",
    "gate_2_guardrails_sha256",
    "remediation_task_contract_sha256",
    "remediation_guardrails_sha256",
    "gate_3_task_contract_sha256",
    "gate_3_guardrails_sha256",
    "gate_2_evidence_bindings",
    "gate_2_evidence_set_sha256",
    "remediation_validation_evidence_binding",
    "gate_3_validation_evidence",
    "decision",
    "contract_sha256",
    "proposal_sha256",
    "candidate_commit",
    "candidate_tree",
    "candidate_source_manifest",
    "candidate_source_manifest_sha256",
    "accepted_consumer_module_sha256",
    "provider_operations",
}
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_RE = re.compile(r"^[0-9a-f]{40}$")


def _positive(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value > 0


def _hash(value: object) -> bool:
    return isinstance(value, str) and bool(_HASH_RE.fullmatch(value))


def _git(value: object) -> bool:
    return isinstance(value, str) and bool(_GIT_RE.fullmatch(value))


def _evidence_binding(
    value: object, *, evidence_id: int | None, task_id: int, check_type: str | None
) -> bool:
    if not isinstance(value, Mapping):
        return False
    item = dict(value)
    return (
        set(item) == EVIDENCE_BINDING_KEYS
        and _positive(item.get("id"))
        and (evidence_id is None or item.get("id") == evidence_id)
        and item.get("task_ref") == task_id
        and isinstance(item.get("check_type"), str)
        and bool(item["check_type"])
        and (check_type is None or item.get("check_type") == check_type)
        and item.get("result") == "pass"
        and _hash(item.get("evidence_sha256"))
    )


def _execution_binding(
    value: object, *, task_id: object, commit: object, tree: object, source_sha: object
) -> bool:
    if not isinstance(value, Mapping):
        return False
    item = dict(value)
    return (
        set(item) == EXECUTION_BINDING_KEYS
        and item.get("artifact_kind") == "gate_3_validation"
        and item.get("task_id") == task_id
        and item.get("candidate_commit") == commit
        and item.get("candidate_tree") == tree
        and item.get("candidate_source_manifest_sha256") == source_sha
        and item.get("contract_sha256") == CONTRACT_SHA256
        and all(
            _hash(item.get(key))
            for key in (
                "commands_sha256",
                "validation_result_sha256",
                "validation_receipt_sha256",
            )
        )
    )


def _source_manifest(value: object, expected_sha: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    manifest = dict(value)
    expected_paths = tuple(
        dict.fromkeys((*CANDIDATE_SOURCE_PATHS, *RUNTIME_SUPPORT_SOURCE_PATHS))
    )
    if (
        len(manifest) != len(expected_paths)
        or set(manifest) != set(expected_paths)
        or any(
            not isinstance(path, str)
            or not path
            or PurePosixPath(path).is_absolute()
            or ".." in PurePosixPath(path).parts
            or not _hash(digest)
            for path, digest in manifest.items()
        )
    ):
        return False
    return _hash(expected_sha) and sha256(canonical(manifest)) == expected_sha


def valid_candidate_review(value: object) -> bool:
    """Validate exact nested retained grammar without accepting raw AK fields."""

    if not isinstance(value, Mapping):
        return False
    review: dict[str, Any] = {str(key): item for key, item in value.items()}
    gate3_task_id = review.get("gate_3_task_id")
    commit = review.get("candidate_commit")
    tree = review.get("candidate_tree")
    source_sha = review.get("candidate_source_manifest_sha256")
    gate2 = review.get("gate_2_evidence_bindings")
    if (
        set(review) != _REVIEW_KEYS
        or review.get("schema_version") != CANDIDATE_REVIEW_SCHEMA
        or review.get("artifact_kind") != "candidate_review"
        or review.get("gate_2_task_id") != GATE2_TASK_ID
        or review.get("remediation_task_id") != REMEDIATION_TASK_ID
        or not _positive(gate3_task_id)
        or len({GATE2_TASK_ID, REMEDIATION_TASK_ID, gate3_task_id}) != 3
        or review.get("gate_2_candidate_commit") != GATE2_BASE_COMMIT
        or review.get("gate_2_candidate_tree") != GATE2_BASE_TREE
        or review.get("gate_2_scope_sha256") != GATE2_SCOPE_SHA256
        or review.get("remediation_scope_sha256") != REMEDIATION_SCOPE_SHA256
        or not _git(commit)
        or not _git(tree)
        or review.get("contract_sha256") != CONTRACT_SHA256
        or review.get("proposal_sha256") != PROPOSAL_SHA256
        or review.get("decision") != "ACCEPT_V11_CANDIDATE_FOR_SEPARATE_LIVE_GATE"
        or review.get("provider_operations") != 0
        or not isinstance(gate2, list)
        or len(gate2) != 2
    ):
        return False
    hash_fields = (
        "gate_2_task_contract_sha256",
        "gate_2_guardrails_sha256",
        "remediation_task_contract_sha256",
        "remediation_guardrails_sha256",
        "gate_3_task_contract_sha256",
        "gate_3_guardrails_sha256",
        "gate_2_evidence_set_sha256",
        "candidate_source_manifest_sha256",
    )
    if not all(_hash(review.get(key)) for key in hash_fields):
        return False
    if (
        not all(
            _evidence_binding(
                item,
                evidence_id=evidence_id,
                task_id=GATE2_TASK_ID,
                check_type=None,
            )
            for item, evidence_id in zip(gate2, GATE2_EVIDENCE_IDS, strict=True)
        )
        or len({item["check_type"] for item in gate2}) != 2
    ):
        return False
    return (
        _evidence_binding(
            review.get("remediation_validation_evidence_binding"),
            evidence_id=None,
            task_id=REMEDIATION_TASK_ID,
            check_type="oracle_semantic_v11_remediation_validation",
        )
        and _execution_binding(
            review.get("gate_3_validation_evidence"),
            task_id=gate3_task_id,
            commit=commit,
            tree=tree,
            source_sha=source_sha,
        )
        and _source_manifest(review.get("candidate_source_manifest"), source_sha)
        and review.get("accepted_consumer_module_sha256") == CONSUMER_MODULE_HASHES
    )

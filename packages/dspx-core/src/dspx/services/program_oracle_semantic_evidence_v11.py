# summary: "Canonical AK execution-evidence schemas; never command-execution synthesis."
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from dspx.services.program_oracle_semantic_gate4_contract_v11 import (
    CONTRACT_SHA256,
    GATE2_TASK_ID,
    SemanticV11Error,
    canonical,
    sha256,
)

# AK evidence identities are immutable execution-record selectors. Their full
# canonical objects—not a locally manufactured successful receipt—are the lawful
# boundary for what commands/results were recorded. This code does not prove that
# a command ran; it validates and hashes the exact evidence object returned by AK.
GATE2_EVIDENCE_IDS = (6729, 6730)
EXECUTION_EVIDENCE_SCHEMA = "dspx-oracle-semantic-v11-ak-execution-evidence-v1"
_COMMAND_REQUIRED_KEYS = {
    "check_type",
    "command",
    "result",
    "result_sha256",
    "receipt_sha256",
}
_COMMAND_OPTIONAL_KEYS = {"diagnostics"}
EVIDENCE_BINDING_KEYS = frozenset(
    {"id", "task_ref", "check_type", "result", "evidence_sha256"}
)
EXECUTION_BINDING_KEYS = frozenset(
    {
        "artifact_kind",
        "task_id",
        "candidate_commit",
        "candidate_tree",
        "candidate_source_manifest_sha256",
        "contract_sha256",
        "commands_sha256",
        "validation_result_sha256",
        "validation_receipt_sha256",
    }
)
_EXECUTION_KEYS = {
    "schema_version",
    "artifact_kind",
    "task_id",
    "candidate_commit",
    "candidate_tree",
    "candidate_source_manifest_sha256",
    "contract_sha256",
    "commands",
    "validation_result_sha256",
    "validation_receipt_sha256",
    "provider_operations",
}
_EVIDENCE_FIELDS = {
    "id",
    "task_ref",
    "check_type",
    "result",
    "details",
    "checked_at",
    "checked_by",
}


def _digest(value: object) -> str:
    return sha256(canonical(value))


def _hash(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise SemanticV11Error(f"{label} immutable hash rejected")
    return value


def canonical_evidence_record(
    value: object,
    *,
    evidence_id: int,
    task_id: int,
    check_type: str | None = None,
) -> dict[str, Any]:
    """Validate every canonical AK evidence byte without retaining raw fields."""

    if not isinstance(value, Mapping):
        raise SemanticV11Error("canonical AK evidence object rejected")
    evidence = dict(value)
    checked_at = evidence.get("checked_at")
    checked_by = evidence.get("checked_by")
    if (
        not _EVIDENCE_FIELDS.issubset(evidence)
        or evidence.get("id") != evidence_id
        or evidence.get("task_ref") != task_id
        or (check_type is not None and evidence.get("check_type") != check_type)
        or not isinstance(evidence.get("check_type"), str)
        or not evidence["check_type"]
        or evidence.get("result") != "pass"
        or not isinstance(evidence.get("details"), Mapping)
        or not isinstance(checked_at, str)
        or not checked_at
        or not isinstance(checked_by, str)
        or not checked_by
    ):
        raise SemanticV11Error("canonical AK evidence object rejected")
    # Canonicalization also rejects non-JSON values and includes every unknown AK
    # field in the immutable digest rather than silently dropping it.
    _digest(evidence)
    return evidence


def evidence_binding(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Return only the closed digest binding; raw AK fields stay in memory."""

    binding = {
        "id": evidence["id"],
        "task_ref": evidence["task_ref"],
        "check_type": evidence["check_type"],
        "result": evidence["result"],
        "evidence_sha256": _digest(evidence),
    }
    if set(binding) != EVIDENCE_BINDING_KEYS:  # pragma: no cover - fixed literal
        raise SemanticV11Error("minimal evidence binding shape drift")
    return binding


def gate2_evidence_bindings(
    records: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if len(records) != len(GATE2_EVIDENCE_IDS):
        raise SemanticV11Error("canonical Gate-2 evidence cardinality rejected")
    validated = tuple(
        canonical_evidence_record(
            record, evidence_id=evidence_id, task_id=GATE2_TASK_ID
        )
        for evidence_id, record in zip(GATE2_EVIDENCE_IDS, records, strict=True)
    )
    if len({record["check_type"] for record in validated}) != len(validated):
        raise SemanticV11Error("canonical Gate-2 check-type cardinality rejected")
    return evidence_binding(validated[0]), evidence_binding(validated[1])


def _command_facts(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise SemanticV11Error("canonical validation command facts rejected")
    commands: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise SemanticV11Error("canonical validation command facts rejected")
        command = dict(item)
        argv = command.get("command")
        if (
            not _COMMAND_REQUIRED_KEYS.issubset(command)
            or set(command) - _COMMAND_REQUIRED_KEYS - _COMMAND_OPTIONAL_KEYS
            or not isinstance(command.get("check_type"), str)
            or not command["check_type"]
            or not isinstance(argv, list)
            or not argv
            or any(not isinstance(part, str) or not part for part in argv)
            or command.get("result") != "pass"
            or (
                "diagnostics" in command
                and (
                    not isinstance(command["diagnostics"], str)
                    or not command["diagnostics"]
                )
            )
        ):
            raise SemanticV11Error("canonical validation command facts rejected")
        _hash(command.get("result_sha256"), "validation result")
        _hash(command.get("receipt_sha256"), "validation receipt")
        commands.append(command)
    if len({item["check_type"] for item in commands}) != len(commands):
        raise SemanticV11Error("canonical validation check-type duplication")
    return commands


def execution_evidence_binding(
    evidence: Mapping[str, Any],
    *,
    artifact_kind: str,
    task_id: int,
    commit: str,
    tree: str,
    source_manifest_sha256: str,
) -> dict[str, Any]:
    """Validate raw command/details bytes, then return only closed hashes."""

    details_raw = evidence.get("details")
    if not isinstance(details_raw, Mapping):
        raise SemanticV11Error("canonical validation evidence details rejected")
    details = dict(details_raw)
    if (
        set(details) != _EXECUTION_KEYS
        or details.get("schema_version") != EXECUTION_EVIDENCE_SCHEMA
        or details.get("artifact_kind") != artifact_kind
        or details.get("task_id") != task_id
        or details.get("candidate_commit") != commit
        or details.get("candidate_tree") != tree
        or details.get("candidate_source_manifest_sha256") != source_manifest_sha256
        or details.get("contract_sha256") != CONTRACT_SHA256
        or details.get("provider_operations") != 0
    ):
        raise SemanticV11Error("canonical validation evidence identity rejected")
    commands = _command_facts(details.get("commands"))
    result_sha = _hash(details.get("validation_result_sha256"), "validation result")
    receipt_sha = _hash(details.get("validation_receipt_sha256"), "validation receipt")
    binding = {
        "artifact_kind": artifact_kind,
        "task_id": task_id,
        "candidate_commit": commit,
        "candidate_tree": tree,
        "candidate_source_manifest_sha256": source_manifest_sha256,
        "contract_sha256": CONTRACT_SHA256,
        "commands_sha256": _digest(commands),
        "validation_result_sha256": result_sha,
        "validation_receipt_sha256": receipt_sha,
    }
    if set(binding) != EXECUTION_BINDING_KEYS:  # pragma: no cover - fixed literal
        raise SemanticV11Error("minimal execution binding shape drift")
    return binding

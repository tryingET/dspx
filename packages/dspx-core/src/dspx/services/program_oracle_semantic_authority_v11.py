# summary: "Canonical AK task, evidence-set, and validation-receipt checks for Gate 4."
from __future__ import annotations

import json
import os
import stat
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dspx.services.program_oracle_semantic_gate4_contract_v11 import (
    SemanticV11Error,
    canonical,
    mapping,
    sha256,
)

AK_EXECUTABLE = Path.home() / ".local/bin/ak"


def machine_payload(value: object, surface: str) -> dict[str, Any]:
    envelope = mapping(value, f"{surface} machine envelope")
    if (
        envelope.get("surface") != surface
        or envelope.get("ok") is not True
        or envelope.get("error") is not None
    ):
        raise SemanticV11Error("canonical AK machine envelope rejected")
    return mapping(envelope.get("payload"), f"{surface} payload")


def resolved_repo(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise SemanticV11Error(f"{label} repo binding rejected")
    try:
        return Path(value).expanduser().resolve(strict=True)
    except OSError as exc:
        raise SemanticV11Error(f"{label} repo binding rejected") from exc


def task_document(
    document: Mapping[str, Any],
    *,
    task_id: int,
    repo_root: Path,
    statuses: set[str],
) -> dict[str, Any]:
    payload = machine_payload(document, "task.show")
    task = mapping(payload.get("task"), "AK task")
    version = task.get("entity_version")
    if (
        task.get("id") != task_id
        or task.get("status") not in statuses
        or resolved_repo(task.get("repo"), "AK task") != repo_root
        or isinstance(version, bool)
        or not isinstance(version, int)
        or version <= 0
    ):
        raise SemanticV11Error("canonical AK task rejected")
    return task


def full_task_contract(
    document: Mapping[str, Any],
    *,
    task_id: int,
    repo_root: Path,
    status: str,
    done_contract: Mapping[str, Any],
    guardrails: Mapping[str, Any],
) -> tuple[dict[str, Any], str, str]:
    value = dict(document)
    done_version = mapping(value.get("done_contract"), "done contract version")
    guard_version = mapping(value.get("guardrails"), "guardrail version")
    done = mapping(done_version.get("contract"), "done contract")
    guard = mapping(guard_version.get("guardrails"), "guardrails")
    done_entity_version = done_version.get("entity_version")
    guard_entity_version = guard_version.get("entity_version")
    if (
        set(value) != {"task_id", "repo", "status", "done_contract", "guardrails"}
        or set(done_version) != {"task_id", "contract", "entity_version"}
        or set(guard_version) != {"task_id", "guardrails", "entity_version"}
        or value.get("task_id") != task_id
        or value.get("status") != status
        or resolved_repo(value.get("repo"), "task contract") != repo_root
        or done_version.get("task_id") != task_id
        or guard_version.get("task_id") != task_id
        or isinstance(done_entity_version, bool)
        or not isinstance(done_entity_version, int)
        or done_entity_version <= 0
        or isinstance(guard_entity_version, bool)
        or not isinstance(guard_entity_version, int)
        or guard_entity_version <= 0
        or done != dict(done_contract)
        or guard != dict(guardrails)
    ):
        raise SemanticV11Error("canonical exact full task contract rejected")
    return value, sha256(canonical(done_version)), sha256(canonical(guard_version))


def evidence_document(
    value: object,
    *,
    expected_id: int,
    expected_task: int,
    check_type: str,
) -> dict[str, Any]:
    payload = machine_payload(value, "evidence.show")
    evidence = mapping(payload.get("evidence"), "AK evidence")
    if (
        evidence.get("id") != expected_id
        or evidence.get("task_ref") != expected_task
        or evidence.get("check_type") != check_type
        or evidence.get("result") != "pass"
        or not isinstance(evidence.get("details"), Mapping)
    ):
        raise SemanticV11Error("canonical AK evidence rejected")
    return evidence


def evidence_set_document(
    value: object,
    *,
    live_task_id: int,
    operator_evidence: Mapping[str, Any],
    live_gate_evidence: Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    payload = machine_payload(value, "evidence.task")
    rows = payload.get("evidence")
    if not isinstance(rows, list) or any(not isinstance(row, Mapping) for row in rows):
        raise SemanticV11Error("canonical Gate-4 evidence set rejected")
    canonical_rows = [dict(row) for row in rows]
    count = payload.get("count")
    if (
        payload.get("task_id") != live_task_id
        or isinstance(count, bool)
        or not isinstance(count, int)
        or count != len(canonical_rows)
        or any(row.get("task_ref") != live_task_id for row in canonical_rows)
    ):
        raise SemanticV11Error("canonical Gate-4 evidence set rejected")
    operators = [
        row
        for row in canonical_rows
        if row.get("check_type") == "oracle_semantic_v11_operator_authorization"
    ]
    gates = [
        row
        for row in canonical_rows
        if row.get("check_type") == "oracle_semantic_v11_live_gate"
    ]
    if (
        len(operators) != 1
        or len(gates) != 1
        or operators[0] != dict(operator_evidence)
        or gates[0] != dict(live_gate_evidence)
    ):
        raise SemanticV11Error("Gate-4 evidence pair cardinality rejected")
    return payload, sha256(canonical(payload))


def run_ak(*args: str) -> dict[str, Any]:
    try:
        info = AK_EXECUTABLE.resolve(strict=True).stat()
    except OSError as exc:
        raise SemanticV11Error("canonical AK executable unavailable") from exc
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or not info.st_mode & stat.S_IXUSR
    ):
        raise SemanticV11Error("canonical AK executable posture drift")
    completed = subprocess.run(
        [str(AK_EXECUTABLE), *args],
        check=False,
        capture_output=True,
        timeout=30,
        env={
            "HOME": str(Path.home()),
            "PATH": "/usr/bin:/bin",
            "XDG_CONFIG_HOME": str(Path.home() / ".config"),
            "XDG_DATA_HOME": str(Path.home() / ".local/share"),
            "XDG_STATE_HOME": str(Path.home() / ".local/state"),
        },
    )
    if completed.returncode != 0 or completed.stderr:
        raise SemanticV11Error("canonical AK authority read failed")
    try:
        value = json.loads(completed.stdout)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SemanticV11Error("canonical AK authority output invalid") from exc
    return mapping(value, "canonical AK authority output")

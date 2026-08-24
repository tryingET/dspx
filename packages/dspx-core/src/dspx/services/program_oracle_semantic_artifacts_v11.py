# summary: "Closed retained artifact names and exact authority-false JSON loaders."
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from dspx.services.program_oracle_semantic_gate4_contract_v11 import (
    CANDIDATE_REVIEW_NAME,
    CANDIDATE_REVIEW_SCHEMA,
    LIVE_GATE_NAME,
    LIVE_GATE_SCHEMA,
    RESULT_FRAGMENTS_NAME,
    RESULT_NAME,
    RESULT_SCHEMA,
    VERIFICATION_NAME,
    VERIFICATION_SCHEMA,
    SemanticV11Error,
    sha256,
)
from dspx.services.program_oracle_semantic_state_v11 import (
    LEDGER_KEYS,
    MAX_RETAINED_BYTES,
    ConsumedAttempt,
    TaskBinding,
    _private_info,
    _validate_artifact,
    assert_attempt_absent,
    current_process_identity_sha256,
    load_consumed_attempt,
    read_private_json,
    require_consumed_attempt,
    state_root_identity_sha256,
)

__all__ = [
    "LEDGER_KEYS",
    "MAX_RETAINED_BYTES",
    "ConsumedAttempt",
    "TaskBinding",
    "assert_attempt_absent",
    "current_process_identity_sha256",
    "load_consumed_attempt",
    "read_private_json",
    "require_consumed_attempt",
    "state_root_identity_sha256",
]


def result_fragment_path(attempt: ConsumedAttempt, ordinal: int) -> Path:
    exact = require_consumed_attempt(attempt)
    if ordinal == 0:
        name = "00-setup.json"
    elif 1 <= ordinal <= 4:
        name = f"{ordinal:02d}-case.json"
    else:
        raise SemanticV11Error("result fragment ordinal drift")
    return exact.attempt_root / RESULT_FRAGMENTS_NAME / name


def load_result_fragments(attempt: ConsumedAttempt) -> dict[int, dict[str, Any]]:
    exact = require_consumed_attempt(attempt)
    root = exact.attempt_root / RESULT_FRAGMENTS_NAME
    _private_info(root, directory=True)
    try:
        members = sorted(root.iterdir())
    except OSError as exc:
        raise SemanticV11Error("result fragment listing failed") from exc
    values: dict[int, dict[str, Any]] = {}
    for member in members:
        if re.fullmatch(r"0[1-4]-terminal\.json", member.name):
            continue
        match = re.fullmatch(r"(00)-setup\.json|(0[1-4])-case\.json", member.name)
        if match is None:
            raise SemanticV11Error("unexpected result fragment")
        ordinal = int(match.group(1) or match.group(2))
        payload, _ = read_private_json(member, "result fragment")
        if payload.get("schema_version") != RESULT_SCHEMA:
            raise SemanticV11Error("result fragment schema drift")
        values[ordinal] = payload
    return values


def load_case_terminal_markers(
    attempt: ConsumedAttempt,
) -> dict[int, dict[str, Any]]:
    exact = require_consumed_attempt(attempt)
    root = exact.attempt_root / RESULT_FRAGMENTS_NAME
    values: dict[int, dict[str, Any]] = {}
    for member in sorted(root.iterdir()):
        match = re.fullmatch(r"(0[1-4])-terminal\.json", member.name)
        if match is None:
            continue
        payload, _ = read_private_json(member, "case terminal marker")
        if payload.get("schema_version") != RESULT_SCHEMA:
            raise SemanticV11Error("case terminal marker schema drift")
        values[int(match.group(1))] = payload
    return values


def load_authority_artifacts(
    attempt: ConsumedAttempt,
) -> tuple[dict[str, Any], bytes, dict[str, Any], bytes]:
    attempt = require_consumed_attempt(attempt)
    review, review_raw = read_private_json(
        attempt.attempt_root / CANDIDATE_REVIEW_NAME, "candidate review"
    )
    gate, gate_raw = read_private_json(
        attempt.attempt_root / LIVE_GATE_NAME, "live gate"
    )
    _validate_artifact(review, CANDIDATE_REVIEW_SCHEMA, "candidate_review")
    _validate_artifact(gate, LIVE_GATE_SCHEMA, "live_gate")
    if (
        sha256(review_raw) != attempt.ledger["candidate_review_sha256"]
        or sha256(gate_raw) != attempt.ledger["live_gate_sha256"]
    ):
        raise SemanticV11Error("retained authority artifact digest drift")
    return review, review_raw, gate, gate_raw


def load_evaluation_result(attempt: ConsumedAttempt) -> tuple[dict[str, Any], bytes]:
    attempt = require_consumed_attempt(attempt)
    payload, raw = read_private_json(
        attempt.attempt_root / RESULT_NAME, "evaluation result"
    )
    if (
        payload.get("schema_version") != RESULT_SCHEMA
        or payload.get("artifact_kind") != "evaluation_result"
    ):
        raise SemanticV11Error("evaluation result schema drift")
    return payload, raw


def load_independent_verification(
    attempt: ConsumedAttempt,
) -> tuple[dict[str, Any], bytes]:
    attempt = require_consumed_attempt(attempt)
    payload, raw = read_private_json(
        attempt.attempt_root / VERIFICATION_NAME, "independent verification"
    )
    if (
        payload.get("schema_version") != VERIFICATION_SCHEMA
        or payload.get("artifact_kind") != "independent_verification"
        or payload.get("artifact_integrity_review") not in {"accepted", "rejected"}
    ):
        raise SemanticV11Error("independent verification schema drift")
    return payload, raw

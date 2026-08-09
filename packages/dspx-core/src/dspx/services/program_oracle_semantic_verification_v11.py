# summary: "Provider-free candidate and independent retained-result verification for v11."
from __future__ import annotations

import os
import re
import stat
from pathlib import Path
from typing import Any

from dspx.services.program_oracle_semantic_artifacts_v11 import (
    ATTEMPT_TERMINAL_NAME,
    MAX_RETAINED_BYTES,
    RESULT_NAME,
    VERIFICATION_NAME,
    VERIFICATION_SCHEMA,
    ConsumedAttempt,
    TaskBinding,
    _read_private_json,
    load_case_custody,
    load_consumed_attempt,
    load_pre_effect_setup_terminal,
    write_exclusive,
)
from dspx.services.program_oracle_semantic_contract_v11 import (
    CASE_ORDER,
    SemanticV11Error,
    canonical,
    load_bound_cases,
    load_candidate,
    semantic_request_sha256,
    sha256,
)
from dspx.services.program_oracle_semantic_evaluation_v11 import (
    normalized_semantic_request,
)
from dspx.services.program_oracle_semantic_gate4_v11 import (
    _git_identity,
    candidate_source_manifest_sha256,
)
from dspx.services.program_oracle_semantic_result_artifact_v11 import (
    derive_evaluation_result,
    derive_pre_effect_setup_result,
    load_evaluation_result,
)
from dspx.services.provider_outcome_receipt_identity import VerifiedOwnerArtifact

_FORBIDDEN_RETAINED_KEYS = (
    b'"access_token"',
    b'"refresh_token"',
    b'"api_key"',
    b'"headers"',
    b'"url"',
    b'"path"',
    b'"exception"',
    b'"traceback"',
    b'"diagnostic"',
)


def candidate_manifest(repo_root: Path) -> dict[str, Any]:
    """Re-derive the provider-free contract/request manifest without state creation."""

    _, _, contract_hash = load_candidate(repo_root)
    cases = load_bound_cases(repo_root)
    requests: dict[str, dict[str, str]] = {}
    for case in cases:
        request = case.materialized_request()
        projection = normalized_semantic_request(request)
        requests[case.case_id] = {
            "case_ordinal": str(case.case_ordinal),
            "oracle_request_sha256": request.request_sha256,
            "semantic_request_sha256": semantic_request_sha256(projection),
        }
    if tuple(requests) != CASE_ORDER:
        raise SemanticV11Error("candidate request order drift")
    return {
        "schema_version": VERIFICATION_SCHEMA,
        "artifact_integrity_review": "not_evaluated",
        "empirical_gate": "not_evaluated",
        "provider_invoked": False,
        "terminal_evidence_modified": False,
        "contract_sha256": contract_hash,
        "requests": requests,
        "fixture_only": True,
        "v11_authorized": False,
        "live_execution_authorized": False,
    }


def verify_task_binding_fixture(
    state_root: Path, live_task_id: int, completion_kind: str
) -> dict[str, Any]:
    binding = TaskBinding.create(live_task_id, completion_kind)
    attempt = load_consumed_attempt(state_root, binding)
    return {
        "binding": binding.payload(),
        "ledger_sha256": attempt.ledger_sha256,
        "retry_allowed": False,
        "maximum_evaluation_processes": 1,
        "provider_invoked": False,
        "fixture_only": True,
        "v11_authorized": False,
        "live_execution_authorized": False,
    }


def _expected_tree(attempt: ConsumedAttempt) -> tuple[set[str], set[str]]:
    directories = {".", "case-custody", "provider-outcomes"}
    files = {"ledger.json", RESULT_NAME}
    records = load_case_custody(attempt)
    files.update(f"case-custody/{name}" for name in records)
    if load_pre_effect_setup_terminal(attempt) is not None:
        files.add(ATTEMPT_TERMINAL_NAME)
    if (attempt.attempt_root / VERIFICATION_NAME).exists():
        verification, _ = _read_private_json(
            attempt.attempt_root / VERIFICATION_NAME,
            "semantic v11 independent verification",
        )
        if (
            verification.get("schema_version") != VERIFICATION_SCHEMA
            or verification.get("live_task_id") != attempt.binding.live_task_id
        ):
            raise SemanticV11Error("retained verification schema drift")
        files.add(VERIFICATION_NAME)
    reached = sorted(
        int(name[:2])
        for name in records
        if re.fullmatch(r"0[1-4]-reserved\.json", name)
    )
    provider_root = attempt.attempt_root / "provider-outcomes"
    for ordinal in reached:
        case_id = CASE_ORDER[ordinal - 1]
        relative_root = f"provider-outcomes/{ordinal:02d}-{case_id}"
        journal_root = provider_root / f"{ordinal:02d}-{case_id}"
        terminal = records.get(f"{ordinal:02d}-terminal.json", {})
        pre_effect = (
            terminal.get("reason") == "receipt_preparation_failed_before_effect"
        )
        if not journal_root.exists() and not journal_root.is_symlink():
            if not pre_effect:
                raise SemanticV11Error("retained provider journal missing")
            continue
        directories.update({relative_root, f"{relative_root}/events"})
        try:
            members = {path.name: path for path in journal_root.iterdir()}
            event_names = sorted(
                path.name for path in (journal_root / "events").iterdir()
            )
        except OSError as exc:
            raise SemanticV11Error("retained journal listing failed") from exc
        member_names = set(members)
        if pre_effect:
            if (
                "events" not in member_names
                or member_names - {"events", "reservation.json", "poisoned.json"}
                or event_names
            ):
                raise SemanticV11Error("unexpected pre-effect journal member")
        elif member_names not in (
            {"reservation.json", "events"},
            {"reservation.json", "events", "poisoned.json"},
        ):
            raise SemanticV11Error("unexpected retained journal member")
        if "reservation.json" in members:
            files.add(f"{relative_root}/reservation.json")
        if "poisoned.json" in members:
            files.add(f"{relative_root}/poisoned.json")
        if event_names != [f"{index:06d}.json" for index in range(len(event_names))]:
            raise SemanticV11Error("retained journal event sequence drift")
        files.update(f"{relative_root}/events/{name}" for name in event_names)
    return directories, files


def _verify_private_tree(attempt: ConsumedAttempt) -> dict[str, int]:
    expected_directories, expected_files = _expected_tree(attempt)
    total = 0
    files = 0
    directories = 0
    observed_directories: set[str] = set()
    observed_files: set[str] = set()
    try:
        paths = [attempt.attempt_root, *attempt.attempt_root.rglob("*")]
    except OSError as exc:
        raise SemanticV11Error("retained tree listing failed") from exc
    for path in paths:
        relative = (
            "."
            if path == attempt.attempt_root
            else str(path.relative_to(attempt.attempt_root))
        )
        try:
            info = path.lstat()
        except OSError as exc:
            raise SemanticV11Error("retained tree member unavailable") from exc
        if stat.S_ISLNK(info.st_mode) or info.st_uid != os.getuid():
            raise SemanticV11Error("retained tree ownership drift")
        if stat.S_ISDIR(info.st_mode):
            directories += 1
            observed_directories.add(relative)
            if stat.S_IMODE(info.st_mode) != 0o700:
                raise SemanticV11Error("retained directory mode drift")
            continue
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
        ):
            raise SemanticV11Error("retained file posture drift")
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise SemanticV11Error("retained file read failed") from exc
        files += 1
        observed_files.add(relative)
        total += len(raw)
        if total > MAX_RETAINED_BYTES:
            raise SemanticV11Error("retained tree byte budget exceeded")
        if (
            b"/home/" in raw
            or b"Traceback (most recent call last)" in raw
            or any(key in raw for key in _FORBIDDEN_RETAINED_KEYS)
        ):
            raise SemanticV11Error("retained private data marker detected")
    if observed_directories != expected_directories or observed_files != expected_files:
        raise SemanticV11Error("retained tree grammar drift")
    return {"files": files, "directories": directories, "bytes": total}


def _verify_candidate_source(repo_root: Path, ledger: Any) -> None:
    if not isinstance(ledger, dict):
        ledger = dict(ledger)
    commit, tree = _git_identity(repo_root)
    manifest_digest = candidate_source_manifest_sha256(repo_root)
    if (
        ledger.get("candidate_commit") != commit
        or ledger.get("candidate_tree") != tree
        or ledger.get("candidate_source_manifest_sha256") != manifest_digest
    ):
        raise SemanticV11Error("retained candidate source binding drift")


def verify_retained_evaluation(
    *,
    repo_root: Path,
    state_root: Path,
    live_task_id: int,
    artifact: VerifiedOwnerArtifact,
) -> tuple[ConsumedAttempt, dict[str, Any]]:
    """Re-derive result, source, receipts, scores, counts, and privacy from disk."""

    binding = TaskBinding.create(live_task_id, "oracle_semantic_v11_live_execution")
    attempt = load_consumed_attempt(state_root, binding, require_current_process=False)
    _verify_candidate_source(repo_root, attempt.ledger)
    cases = load_bound_cases(repo_root)
    retained, retained_raw = load_evaluation_result(attempt)
    setup_terminal = load_pre_effect_setup_terminal(attempt)
    if setup_terminal is not None and not load_case_custody(attempt):
        derived = derive_pre_effect_setup_result(attempt)
    else:
        derived = derive_evaluation_result(attempt, cases, artifact)
    if retained != derived or retained_raw != canonical(derived):
        raise SemanticV11Error("retained evaluation result derivation drift")
    privacy = _verify_private_tree(attempt)
    verification = {
        "schema_version": VERIFICATION_SCHEMA,
        "live_task_id": live_task_id,
        "artifact_integrity_review": "accepted",
        "empirical_gate": derived["empirical_gate"],
        "result_sha256": sha256(retained_raw),
        "ledger_sha256": attempt.ledger_sha256,
        "candidate_commit": derived["candidate_commit"],
        "candidate_tree": derived["candidate_tree"],
        "candidate_source_manifest_sha256": derived["candidate_source_manifest_sha256"],
        "contract_sha256": derived["contract_sha256"],
        "provider_owner_source_identity_sha256": derived[
            "provider_owner_source_identity_sha256"
        ],
        "dependency_identity_sha256": derived["dependency_identity_sha256"],
        "operation_counts": derived["operation_counts"],
        "privacy": privacy,
        "provider_invoked": False,
        "terminal_evidence_modified": False,
        "fixture_only": False,
        "v11_authorized": False,
        "live_execution_authorized": False,
    }
    return attempt, verification


def write_independent_verification(
    *,
    repo_root: Path,
    state_root: Path,
    live_task_id: int,
    artifact: VerifiedOwnerArtifact,
) -> dict[str, Any]:
    """Write Gate-5 verification no-replace without changing terminal bytes."""

    attempt, payload = verify_retained_evaluation(
        repo_root=repo_root,
        state_root=state_root,
        live_task_id=live_task_id,
        artifact=artifact,
    )
    write_exclusive(attempt.attempt_root / VERIFICATION_NAME, payload)
    return payload


def load_independent_verification(
    attempt: ConsumedAttempt,
) -> tuple[dict[str, Any], bytes]:
    return _read_private_json(
        attempt.attempt_root / VERIFICATION_NAME,
        "semantic v11 independent verification",
    )

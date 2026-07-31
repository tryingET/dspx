#!/usr/bin/env python3
# ---
# summary: "Freshly resolves accepted Core policy selectors from live AK with anti-rollback."
# read_when:
#   - "Changing current signer-policy resolution or highest-observed checkpoints."
# ---

from __future__ import annotations

from collections.abc import Mapping
import fcntl
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess
from typing import Any, cast

from core_release_evidence_io import CoreReleaseEvidenceError, stable_regular_bytes
from core_release_policy import (
    REPO_SCOPE,
    SELECTOR_REF_PATTERN,
    load_json,
    loads_json,
    mapping,
    sha256,
    validate_selector,
)


def _run_machine(command: list[str], surface: str) -> Mapping[str, Any]:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise CoreReleaseEvidenceError(f"live AK {surface} failed")
    try:
        envelope = mapping(json.loads(result.stdout), f"AK {surface} envelope")
    except json.JSONDecodeError as exc:
        raise CoreReleaseEvidenceError(
            f"live AK {surface} returned invalid JSON"
        ) from exc
    if (
        envelope.get("surface") != surface
        or envelope.get("schema_version") != 1
        or envelope.get("ok") is not True
        or envelope.get("error") is not None
    ):
        raise CoreReleaseEvidenceError(f"live AK {surface} schema drift")
    return mapping(envelope.get("payload"), f"AK {surface} payload")


def _selector_from_ref(
    *, repo_root: Path, evidence_ref: str, decision_id: int
) -> dict[str, Any]:
    match = SELECTOR_REF_PATTERN.fullmatch(evidence_ref)
    if match is None:
        raise CoreReleaseEvidenceError("accepted selector evidence_ref is malformed")
    commit = match.group("commit")
    path = match.group("path")
    observed_blob = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", f"{commit}:{path}"],
        capture_output=True,
        text=True,
        check=False,
    )
    raw = subprocess.run(
        ["git", "-C", str(repo_root), "show", f"{commit}:{path}"],
        capture_output=True,
        check=False,
    )
    if (
        observed_blob.returncode != 0
        or observed_blob.stdout.strip() != match.group("blob")
        or raw.returncode != 0
        or sha256(raw.stdout) != match.group("sha256")
    ):
        raise CoreReleaseEvidenceError("accepted selector Git binding drift")
    selector = validate_selector(
        loads_json(raw.stdout, "accepted selector"), repo_root=repo_root
    )
    if selector["accepting_decision_id"] != decision_id:
        raise CoreReleaseEvidenceError("accepted selector decision identity drift")
    return selector


def resolve_selector_chain(
    candidates: list[tuple[int, dict[str, Any], str]],
) -> tuple[int, dict[str, Any], str]:
    if not candidates:
        raise CoreReleaseEvidenceError("no accepted Core policy selector exists")
    by_version: dict[int, tuple[int, dict[str, Any], str]] = {}
    for candidate in candidates:
        version = candidate[1]["policy"]["version"]
        if version in by_version:
            raise CoreReleaseEvidenceError("Core policy selector version fork")
        by_version[version] = candidate
    versions = sorted(by_version)
    if versions != list(range(1, versions[-1] + 1)):
        raise CoreReleaseEvidenceError("Core policy selector chain has a gap")
    previous_decision: int | None = None
    for version in versions:
        decision_id, selector, _reference = by_version[version]
        supersession = mapping(selector["supersession"], "selector supersession")
        expected = {
            "supersedes_decision_id": previous_decision,
            "supersedes_policy_version": None if version == 1 else version - 1,
        }
        if dict(supersession) != expected:
            raise CoreReleaseEvidenceError("Core policy selector chain is inconsistent")
        previous_decision = decision_id
    return by_version[versions[-1]]


def _checkpoint_payload(version: int, reference: str) -> dict[str, Any]:
    identity = {
        "schema_version": "dspx-core-policy-checkpoint-v1",
        "highest_policy_version": version,
        "selector_ref": reference,
    }
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    return {**identity, "integrity_sha256": sha256(canonical)}


def _validate_checkpoint(value: object) -> dict[str, Any]:
    checkpoint = mapping(value, "policy checkpoint")
    if set(checkpoint) != {
        "schema_version",
        "highest_policy_version",
        "selector_ref",
        "integrity_sha256",
    }:
        raise CoreReleaseEvidenceError("policy checkpoint fields drift")
    version = checkpoint.get("highest_policy_version")
    reference = checkpoint.get("selector_ref")
    if (
        checkpoint.get("schema_version") != "dspx-core-policy-checkpoint-v1"
        or not isinstance(version, int)
        or isinstance(version, bool)
        or version <= 0
        or not isinstance(reference, str)
    ):
        raise CoreReleaseEvidenceError("policy checkpoint identity drift")
    if _checkpoint_payload(version, reference) != dict(checkpoint):
        raise CoreReleaseEvidenceError("policy checkpoint integrity drift")
    return dict(checkpoint)


def advance_checkpoint(path: Path, *, version: int, reference: str) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = path.parent / f".{path.name}.lock"
    lock_descriptor = os.open(
        lock_path,
        os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        os.fchmod(lock_descriptor, 0o600)
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
        return _advance_checkpoint_unlocked(path, version=version, reference=reference)
    finally:
        fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
        os.close(lock_descriptor)


def _advance_checkpoint_unlocked(
    path: Path, *, version: int, reference: str
) -> dict[str, Any]:
    if path.is_symlink():
        raise CoreReleaseEvidenceError("policy checkpoint must not be a symlink")
    if path.exists():
        current = _validate_checkpoint(load_json(path, "policy checkpoint"))
        if current["highest_policy_version"] > version:
            raise CoreReleaseEvidenceError(
                "current policy is below the highest observed version"
            )
        if current["highest_policy_version"] == version:
            if current["selector_ref"] != reference:
                raise CoreReleaseEvidenceError("policy checkpoint selector fork")
            return current
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = _checkpoint_payload(version, reference)
    raw = (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode()
    temporary = path.parent / f".{path.name}.{secrets.token_hex(12)}.tmp"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            if written <= 0:
                raise CoreReleaseEvidenceError(
                    "policy checkpoint write made no progress"
                )
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)
    os.chmod(path, 0o600, follow_symlinks=False)
    parent_descriptor = os.open(
        path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    )
    try:
        os.fsync(parent_descriptor)
    finally:
        os.close(parent_descriptor)
    if not stat.S_ISREG(path.stat(follow_symlinks=False).st_mode):
        raise CoreReleaseEvidenceError("policy checkpoint is not regular")
    observed = stable_regular_bytes(path, label="policy checkpoint", limit=64 * 1024)
    if observed != raw:
        raise CoreReleaseEvidenceError("policy checkpoint publication drift")
    return payload


def resolve_live_current_policy(
    *,
    repo_root: Path,
    checkpoint_path: Path,
    ak_command: str = "ak",
    limit: int = 100_000,
) -> dict[str, Any]:
    collection = _run_machine(
        [ak_command, "decision", "list", "--limit", str(limit), "--machine"],
        "decision.list",
    )
    count = collection.get("count")
    decisions = collection.get("decisions")
    if (
        not isinstance(count, int)
        or count >= limit
        or not isinstance(decisions, list)
        or count != len(decisions)
    ):
        raise CoreReleaseEvidenceError("live AK decision list completeness is unproven")
    candidates: list[tuple[int, dict[str, Any], str]] = []
    for raw_decision in decisions:
        decision = mapping(raw_decision, "AK decision")
        reference = decision.get("evidence_ref")
        if not isinstance(reference, str) or not reference.startswith(
            "dspx-core-policy-selector-v1:git:"
        ):
            continue
        decision_id = decision.get("id")
        if (
            not isinstance(decision_id, int)
            or decision.get("scope") != "repo"
            or decision.get("repo_scope") != REPO_SCOPE
            or decision.get("outcome") != "accepted"
            or decision.get("state") != "unblocked"
        ):
            raise CoreReleaseEvidenceError("accepted selector decision state drift")
        detail = _run_machine(
            [ak_command, "decision", "get", str(decision_id), "--machine"],
            "decision.get",
        )
        detailed = mapping(detail.get("decision"), "AK decision detail")
        if (
            detailed.get("id") != decision_id
            or detailed.get("evidence_ref") != reference
        ):
            raise CoreReleaseEvidenceError("live AK selector detail drift")
        selector = _selector_from_ref(
            repo_root=repo_root, evidence_ref=reference, decision_id=decision_id
        )
        candidates.append((decision_id, selector, reference))
    decision_id, selector, reference = resolve_selector_chain(candidates)
    version = cast(int, mapping(selector["policy"], "selected policy")["version"])
    checkpoint = advance_checkpoint(
        checkpoint_path, version=version, reference=reference
    )
    return {
        "schema_version": "dspx-core-current-policy-resolution-v1",
        "status": "current",
        "decision_id": decision_id,
        "policy_version": version,
        "selector_ref": reference,
        "checkpoint": checkpoint,
    }

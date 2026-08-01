#!/usr/bin/env python3
# ---
# summary: "Resolves immutable accepted Core owner policies from live AK with anti-rollback."
# ---

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess
from typing import Any, cast

from core_release_evidence_io import (
    CoreReleaseEvidenceError,
    sha256,
    stable_regular_bytes,
)
from core_release_owner_authorization import (
    OWNER_SELECTOR_REF_PATTERN,
    load_json,
    loads_json,
    validate_policy,
)

SELECTOR_SCHEMA = "dspx-core-release-owner-policy-selector-v1"
REPO_SCOPE = "/home/tryinget/ai-society/softwareco/owned/dspx"
REPOSITORY = {"name": "tryingET/dspx", "id": 1_318_473_695, "repo_scope": REPO_SCOPE}
POLICY_PATH_TEMPLATE = (
    "governance/release-signing/release-owner-policy-v{version:03d}.json"
)


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CoreReleaseEvidenceError(f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise CoreReleaseEvidenceError(f"{label} fields drift")


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise CoreReleaseEvidenceError("owner policy Git lookup failed")
    return result.stdout.strip()


def validate_selector(
    value: object, *, repo_root: Path, now: datetime
) -> dict[str, Any]:
    selector = _mapping(value, "owner policy selector")
    _exact(
        selector,
        {
            "schema_version",
            "repository",
            "policy",
            "accepting_decision_id",
            "supersession",
        },
        "owner policy selector",
    )
    if (
        selector.get("schema_version") != SELECTOR_SCHEMA
        or selector.get("repository") != REPOSITORY
    ):
        raise CoreReleaseEvidenceError("owner policy selector repository drift")
    decision_id = selector.get("accepting_decision_id")
    if (
        not isinstance(decision_id, int)
        or isinstance(decision_id, bool)
        or decision_id <= 0
    ):
        raise CoreReleaseEvidenceError("owner policy selector decision drift")
    policy = _mapping(selector.get("policy"), "selected owner policy")
    _exact(
        policy,
        {"version", "path", "commit", "blob_oid", "file_sha256"},
        "selected owner policy",
    )
    version = policy.get("version")
    path = policy.get("path")
    if (
        not isinstance(version, int)
        or isinstance(version, bool)
        or version < 2
        or path != POLICY_PATH_TEMPLATE.format(version=version)
    ):
        raise CoreReleaseEvidenceError("selected owner policy locator drift")
    commit = policy.get("commit")
    blob = policy.get("blob_oid")
    digest = policy.get("file_sha256")
    if (
        not isinstance(commit, str)
        or len(commit) != 40
        or not isinstance(blob, str)
        or len(blob) != 40
        or not isinstance(digest, str)
        or len(digest) != 64
    ):
        raise CoreReleaseEvidenceError("selected owner policy Git identity drift")
    if _git(repo_root, "rev-parse", f"{commit}:{path}") != blob:
        raise CoreReleaseEvidenceError("selected owner policy blob drift")
    raw = subprocess.run(
        ["git", "-C", str(repo_root), "show", f"{commit}:{path}"],
        capture_output=True,
        check=False,
    )
    if raw.returncode != 0 or sha256(raw.stdout) != digest:
        raise CoreReleaseEvidenceError("selected owner policy digest drift")
    selected_policy = validate_policy(
        loads_json(raw.stdout, "selected owner policy"), now=now
    )
    if selected_policy["owner_policy_version"] != version:
        raise CoreReleaseEvidenceError("selected owner policy version binding drift")
    supersession = _mapping(selector.get("supersession"), "owner selector supersession")
    _exact(
        supersession,
        {"supersedes_decision_id", "supersedes_owner_policy_version"},
        "owner selector supersession",
    )
    if version == 2:
        if dict(supersession) != {
            "supersedes_decision_id": None,
            "supersedes_owner_policy_version": None,
        }:
            raise CoreReleaseEvidenceError("owner policy selector supersession drift")
    elif (
        not isinstance(supersession.get("supersedes_decision_id"), int)
        or supersession.get("supersedes_owner_policy_version") != version - 1
    ):
        raise CoreReleaseEvidenceError("owner policy selector supersession drift")
    return dict(selector)


def selector_ref(*, repo_root: Path, selector_path: Path) -> str:
    relative = selector_path.resolve().relative_to(repo_root.resolve()).as_posix()
    commit = _git(repo_root, "rev-parse", "HEAD")
    blob = _git(repo_root, "rev-parse", f"{commit}:{relative}")
    raw = subprocess.run(
        ["git", "-C", str(repo_root), "show", f"{commit}:{relative}"],
        capture_output=True,
        check=True,
    ).stdout
    return f"dspx-core-owner-policy-selector-v1:git:{commit}:{relative}:{blob}:{sha256(raw)}"


def selector_from_ref(
    *, repo_root: Path, reference: str, decision_id: int, now: datetime
) -> dict[str, Any]:
    match = OWNER_SELECTOR_REF_PATTERN.fullmatch(reference)
    if match is None:
        raise CoreReleaseEvidenceError("accepted owner selector reference is malformed")
    raw = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "show",
            f"{match.group('commit')}:{match.group('path')}",
        ],
        capture_output=True,
        check=False,
    )
    observed_blob = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "rev-parse",
            f"{match.group('commit')}:{match.group('path')}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if (
        raw.returncode != 0
        or observed_blob.returncode != 0
        or observed_blob.stdout.strip() != match.group("blob")
        or sha256(raw.stdout) != match.group("sha256")
    ):
        raise CoreReleaseEvidenceError("accepted owner selector Git binding drift")
    selector = validate_selector(
        loads_json(raw.stdout, "accepted owner selector"), repo_root=repo_root, now=now
    )
    if selector["accepting_decision_id"] != decision_id:
        raise CoreReleaseEvidenceError("accepted owner selector decision drift")
    return selector


def resolve_selector_chain(
    candidates: list[tuple[int, dict[str, Any], str]],
) -> tuple[int, dict[str, Any], str]:
    if not candidates:
        raise CoreReleaseEvidenceError("no accepted owner policy selector exists")
    by_version: dict[int, tuple[int, dict[str, Any], str]] = {}
    for candidate in candidates:
        version = cast(
            int, _mapping(candidate[1]["policy"], "selected owner policy")["version"]
        )
        if version in by_version:
            raise CoreReleaseEvidenceError("owner policy selector version fork")
        by_version[version] = candidate
    versions = sorted(by_version)
    if versions != list(range(2, versions[-1] + 1)):
        raise CoreReleaseEvidenceError("owner policy selector chain has a gap")
    previous_decision: int | None = None
    for version in versions:
        decision_id, selector, _reference = by_version[version]
        supersession = _mapping(selector["supersession"], "owner selector supersession")
        expected = {
            "supersedes_decision_id": previous_decision,
            "supersedes_owner_policy_version": None if version == 2 else version - 1,
        }
        if dict(supersession) != expected:
            raise CoreReleaseEvidenceError(
                "owner policy selector chain is inconsistent"
            )
        previous_decision = decision_id
    return by_version[versions[-1]]


def _checkpoint_payload(version: int, reference: str) -> dict[str, Any]:
    identity = {
        "schema_version": "dspx-core-owner-policy-checkpoint-v1",
        "highest_owner_policy_version": version,
        "selector_ref": reference,
    }
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    return {**identity, "integrity_sha256": sha256(canonical)}


def _validate_checkpoint(value: object) -> dict[str, Any]:
    checkpoint = _mapping(value, "owner policy checkpoint")
    _exact(
        checkpoint,
        {
            "schema_version",
            "highest_owner_policy_version",
            "selector_ref",
            "integrity_sha256",
        },
        "owner policy checkpoint",
    )
    version = checkpoint.get("highest_owner_policy_version")
    reference = checkpoint.get("selector_ref")
    if (
        checkpoint.get("schema_version") != "dspx-core-owner-policy-checkpoint-v1"
        or not isinstance(version, int)
        or isinstance(version, bool)
        or version <= 0
        or not isinstance(reference, str)
    ):
        raise CoreReleaseEvidenceError("owner policy checkpoint identity drift")
    if _checkpoint_payload(version, reference) != dict(checkpoint):
        raise CoreReleaseEvidenceError("owner policy checkpoint integrity drift")
    return dict(checkpoint)


def advance_checkpoint(path: Path, *, version: int, reference: str) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = os.open(
        path.parent / f".{path.name}.lock",
        os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        os.fchmod(lock, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        if path.is_symlink():
            raise CoreReleaseEvidenceError(
                "owner policy checkpoint must not be a symlink"
            )
        if path.exists():
            current = _validate_checkpoint(load_json(path, "owner policy checkpoint"))
            current_version = cast(int, current["highest_owner_policy_version"])
            if current_version > version:
                raise CoreReleaseEvidenceError(
                    "owner policy is below highest observed version"
                )
            if current_version == version:
                if current["selector_ref"] != reference:
                    raise CoreReleaseEvidenceError(
                        "owner policy checkpoint selector fork"
                    )
                return current
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
                        "owner policy checkpoint write made no progress"
                    )
                offset += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, path)
        parent_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
        if (
            not stat.S_ISREG(path.stat(follow_symlinks=False).st_mode)
            or stable_regular_bytes(
                path, label="owner policy checkpoint", limit=64 * 1024
            )
            != raw
        ):
            raise CoreReleaseEvidenceError("owner policy checkpoint publication drift")
        return payload
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        os.close(lock)


def _run_machine(command: list[str], surface: str) -> Mapping[str, Any]:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise CoreReleaseEvidenceError(f"live AK {surface} failed")
    try:
        envelope = _mapping(json.loads(result.stdout), f"AK {surface} envelope")
    except json.JSONDecodeError as exc:
        raise CoreReleaseEvidenceError(f"live AK {surface} invalid JSON") from exc
    if (
        envelope.get("surface") != surface
        or envelope.get("schema_version") != 1
        or envelope.get("ok") is not True
        or envelope.get("error") is not None
    ):
        raise CoreReleaseEvidenceError(f"live AK {surface} schema drift")
    return _mapping(envelope.get("payload"), f"AK {surface} payload")


def resolve_live_current_owner_policy(
    *,
    repo_root: Path,
    checkpoint_path: Path,
    ak_command: str = "ak",
    limit: int = 100_000,
    now: datetime | None = None,
) -> dict[str, Any]:
    observed_now = now or datetime.now(timezone.utc)
    collection = _run_machine(
        [ak_command, "decision", "list", "--limit", str(limit), "--machine"],
        "decision.list",
    )
    decisions = collection.get("decisions")
    count = collection.get("count")
    if (
        not isinstance(decisions, list)
        or not isinstance(count, int)
        or count != len(decisions)
        or count >= limit
    ):
        raise CoreReleaseEvidenceError(
            "live AK owner decision completeness is unproven"
        )
    matches: list[tuple[int, dict[str, Any], str]] = []
    for raw in decisions:
        decision = _mapping(raw, "AK owner decision")
        reference = decision.get("evidence_ref")
        if not isinstance(reference, str) or not reference.startswith(
            "dspx-core-owner-policy-selector-v1:git:"
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
            raise CoreReleaseEvidenceError(
                "accepted owner selector decision state drift"
            )
        selector = selector_from_ref(
            repo_root=repo_root,
            reference=reference,
            decision_id=decision_id,
            now=observed_now,
        )
        matches.append((decision_id, selector, reference))
    decision_id, selector, reference = resolve_selector_chain(matches)
    version = cast(
        int, _mapping(selector["policy"], "selected owner policy")["version"]
    )
    checkpoint = advance_checkpoint(
        checkpoint_path, version=version, reference=reference
    )
    return {
        "schema_version": "dspx-core-current-owner-policy-resolution-v1",
        "status": "current",
        "decision_id": decision_id,
        "owner_policy_version": version,
        "selector_ref": reference,
        "selector": selector,
        "checkpoint": checkpoint,
    }

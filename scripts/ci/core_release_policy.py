#!/usr/bin/env python3
# ---
# summary: "Validates immutable Core trust policy, selector, roster, and owner approvals."
# read_when:
#   - "Changing Core signer policy selection, release-owner bindings, or approvals."
# ---

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any, cast

from core_release_evidence_io import (
    MAX_JSON_BYTES,
    CoreReleaseEvidenceError,
    stable_regular_bytes,
)

POLICY_SCHEMA = "dspx-core-trust-policy-v1"
SELECTOR_SCHEMA = "dspx-core-policy-selector-v1"
ROSTER_SCHEMA = "dspx-core-release-owner-roster-v1"
APPROVAL_SCHEMA = "dspx-core-release-owner-approval-v1"
REPOSITORY = "tryingET/dspx"
REPOSITORY_ID = 1_318_473_695
REPO_SCOPE = "/home/tryinget/ai-society/softwareco/owned/dspx"
POLICY_PATH = "governance/release-signing/trust-policy-v001.json"
SELECTOR_PATH = "governance/release-signing/policy-selector-v001.json"
ROSTER_VERSION = "dspx-core-release-owners-v1"
ROLES = (
    "role:dspx-release-governance-owner",
    "role:softwareco-security-owner",
    "role:softwareco-delivery-owner",
)
AUXILIARY_ROLES = (
    "installed_wheel_proof",
    "release_evidence_v3",
    "exact_wheel_sbom",
    "resolved_environment_sbom",
    "source_state",
    "bundle_manifest",
    "unsigned_unsupported_distribution_evidence",
)
SELECTOR_REF_PATTERN = re.compile(
    r"^dspx-core-policy-selector-v1:git:"
    r"(?P<commit>[0-9a-f]{40}):"
    r"(?P<path>governance/release-signing/policy-selector-v[0-9]{3}\.json):"
    r"(?P<blob>[0-9a-f]{40}):(?P<sha256>[0-9a-f]{64})$"
)
_POLICY_FIELDS = {
    "schema_version",
    "policy_version",
    "effective_at",
    "repository",
    "workload",
    "sigstore",
    "statement",
    "roster_version",
    "selector_path",
    "deny",
    "claims",
}


def mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CoreReleaseEvidenceError(f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise CoreReleaseEvidenceError(f"{label} fields drift")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def is_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise CoreReleaseEvidenceError(f"{label} must be UTC RFC3339")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise CoreReleaseEvidenceError(f"{label} is invalid") from exc
    if parsed.tzinfo != timezone.utc:
        raise CoreReleaseEvidenceError(f"{label} must be UTC")
    return parsed


def loads_json(raw: bytes, label: str) -> Mapping[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise CoreReleaseEvidenceError(f"{label} has duplicate key {key!r}")
            result[key] = value
        return result

    try:
        return mapping(json.loads(raw, object_pairs_hook=reject_duplicates), label)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoreReleaseEvidenceError(f"{label} is not valid JSON") from exc


def load_json(path: Path, label: str) -> Mapping[str, Any]:
    raw = stable_regular_bytes(path, label=label, limit=MAX_JSON_BYTES)
    return loads_json(raw, label)


def validate_policy(value: object) -> dict[str, Any]:
    policy = mapping(value, "trust policy")
    exact(policy, _POLICY_FIELDS, "trust policy")
    if (
        policy.get("schema_version") != POLICY_SCHEMA
        or policy.get("policy_version") != 1
    ):
        raise CoreReleaseEvidenceError("trust policy version drift")
    timestamp(policy.get("effective_at"), "policy effective_at")
    if policy.get("repository") != {
        "name": REPOSITORY,
        "id": REPOSITORY_ID,
        "owner": "tryingET",
        "owner_id": 260_287_438,
        "visibility": "public",
    }:
        raise CoreReleaseEvidenceError("trust policy repository drift")
    workload = mapping(policy.get("workload"), "policy workload")
    expected_workload = {
        "issuer": "https://token.actions.githubusercontent.com",
        "workflow_path": ".github/workflows/core-release-evidence.yml",
        "workflow_ref": "refs/heads/main",
        "environment": "core-release-evidence",
        "event": "workflow_dispatch",
        "runner_environment": "github-hosted",
        "token_subject": "repo:tryingET/dspx:environment:core-release-evidence",
    }
    for key, expected in expected_workload.items():
        if workload.get(key) != expected:
            raise CoreReleaseEvidenceError(f"trust policy workload {key} drift")
    extensions = mapping(
        workload.get("certificate_extensions"), "certificate extensions"
    )
    expected_oids = {"2.5.29.17"} | {
        f"1.3.6.1.4.1.57264.1.{index}" for index in range(8, 25)
    }
    if set(extensions) != expected_oids:
        raise CoreReleaseEvidenceError("trust policy certificate OID coverage drift")
    if (
        extensions["1.3.6.1.4.1.57264.1.10"] != "$workflow_commit_sha"
        or extensions["1.3.6.1.4.1.57264.1.13"] != "$source_commit_sha"
        or extensions["1.3.6.1.4.1.57264.1.21"] != "$run_invocation_uri"
    ):
        raise CoreReleaseEvidenceError("trust policy dynamic certificate matcher drift")
    sigstore = mapping(policy.get("sigstore"), "policy sigstore")
    if sigstore != {
        "cosign_version": "v2.6.4",
        "bundle_media_type": "application/vnd.dev.sigstore.bundle.v0.3+json",
        "trusted_root_source": "https://raw.githubusercontent.com/sigstore/root-signing/5a1d1a50849a7805f290c90c3bf5ee3ada8da3af/targets/trusted_root.json",
        "trusted_root_sha256": "6494e21ea73fa7ee769f85f57d5a3e6a08725eae1e38c755fc3517c9e6bc0b66",
        "require_certificate_transparency": True,
        "require_rekor_inclusion": True,
        "offline_verification": True,
    }:
        raise CoreReleaseEvidenceError("trust policy Sigstore contract drift")
    statement = mapping(policy.get("statement"), "policy statement")
    if statement != {
        "type": "https://in-toto.io/Statement/v1",
        "predicate_type": "https://dspx.ai/attestations/core-release-evidence/v1",
        "subject_count": 1,
        "subject_role": "core-wheel",
        "auxiliary_roles": list(AUXILIARY_ROLES),
    }:
        raise CoreReleaseEvidenceError("trust policy statement contract drift")
    if (
        policy.get("roster_version") != ROSTER_VERSION
        or policy.get("selector_path") != SELECTOR_PATH
    ):
        raise CoreReleaseEvidenceError("trust policy authority locator drift")
    deny = mapping(policy.get("deny"), "policy denylist")
    if set(deny) != {
        "workflow_run_ids",
        "source_commit_shas",
        "signed_statement_sha256",
        "bundle_manifest_sha256",
    }:
        raise CoreReleaseEvidenceError("trust policy denylist fields drift")
    for key, entries in deny.items():
        if not isinstance(entries, list) or len(entries) != len(set(entries)):
            raise CoreReleaseEvidenceError(f"trust policy denylist {key} is invalid")
    if any(
        not isinstance(value, int) or isinstance(value, bool) or value <= 0
        for value in deny["workflow_run_ids"]
    ):
        raise CoreReleaseEvidenceError("trust policy workflow run denylist is invalid")
    for key in (
        "source_commit_shas",
        "signed_statement_sha256",
        "bundle_manifest_sha256",
    ):
        width = 40 if key == "source_commit_shas" else 64
        if any(
            not isinstance(value, str)
            or re.fullmatch(rf"[0-9a-f]{{{width}}}", value) is None
            for value in deny[key]
        ):
            raise CoreReleaseEvidenceError(
                f"trust policy denylist {key} identity drift"
            )
    if policy.get("claims") != {
        "evidence_authenticity_possible": True,
        "release_authority": False,
        "package_publication": False,
        "sdist_supported": False,
    }:
        raise CoreReleaseEvidenceError("trust policy claims drift")
    return dict(policy)


def validate_roster(value: object, *, require_bindings: bool = False) -> dict[str, Any]:
    roster = mapping(value, "release-owner roster")
    exact(
        roster,
        {
            "schema_version",
            "roster_version",
            "roles",
            "bindings",
            "threshold",
            "authorization_enabled",
            "disabled_reason",
        },
        "release-owner roster",
    )
    if (
        roster.get("schema_version") != ROSTER_SCHEMA
        or roster.get("roster_version") != ROSTER_VERSION
    ):
        raise CoreReleaseEvidenceError("release-owner roster version drift")
    if roster.get("roles") != list(ROLES):
        raise CoreReleaseEvidenceError("release-owner roster role drift")
    threshold = roster.get("threshold")
    if threshold != {
        "required": 2,
        "total": 3,
        "distinct_roles": True,
        "distinct_principals": True,
        "approval_max_age_hours": 72,
    }:
        raise CoreReleaseEvidenceError("release-owner threshold drift")
    bindings = roster.get("bindings")
    if not isinstance(bindings, list):
        raise CoreReleaseEvidenceError("release-owner bindings must be a list")
    roles: set[str] = set()
    principals: set[str] = set()
    for index, raw_binding in enumerate(bindings):
        binding = mapping(raw_binding, f"roster binding {index}")
        exact(
            binding,
            {
                "role",
                "principal",
                "authentication",
                "authority_ref",
                "valid_from",
                "expires_at",
                "withdrawn",
            },
            f"roster binding {index}",
        )
        role = binding.get("role")
        principal = binding.get("principal")
        if (
            role not in ROLES
            or role in roles
            or not isinstance(principal, str)
            or not principal
            or principal in principals
        ):
            raise CoreReleaseEvidenceError(
                "release-owner binding identity is ambiguous"
            )
        if binding.get("withdrawn") is not False:
            raise CoreReleaseEvidenceError("release-owner binding is withdrawn")
        valid_from = timestamp(binding.get("valid_from"), "binding valid_from")
        expires_at = timestamp(binding.get("expires_at"), "binding expires_at")
        now = datetime.now(timezone.utc)
        if valid_from >= expires_at or (
            require_bindings and not (valid_from <= now < expires_at)
        ):
            raise CoreReleaseEvidenceError(
                "release-owner binding time window is invalid"
            )
        roles.add(cast(str, role))
        principals.add(principal)
    fully_bound = roles == set(ROLES)
    if roster.get("authorization_enabled") is not fully_bound:
        raise CoreReleaseEvidenceError("release-owner authorization flag drift")
    disabled_reason = roster.get("disabled_reason")
    if (fully_bound and disabled_reason is not None) or (
        not fully_bound
        and (not isinstance(disabled_reason, str) or not disabled_reason)
    ):
        raise CoreReleaseEvidenceError("release-owner disabled reason drift")
    if require_bindings and not fully_bound:
        raise CoreReleaseEvidenceError("three distinct owner bindings are required")
    return dict(roster)


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise CoreReleaseEvidenceError(f"Git lookup failed: {result.stderr.strip()}")
    return result.stdout.strip()


def validate_selector(value: object, *, repo_root: Path) -> dict[str, Any]:
    selector = mapping(value, "policy selector")
    exact(
        selector,
        {
            "schema_version",
            "repository",
            "policy",
            "accepting_decision_id",
            "supersession",
        },
        "policy selector",
    )
    if selector.get("schema_version") != SELECTOR_SCHEMA or selector.get(
        "repository"
    ) != {
        "name": REPOSITORY,
        "id": REPOSITORY_ID,
        "repo_scope": REPO_SCOPE,
    }:
        raise CoreReleaseEvidenceError("policy selector repository drift")
    accepting_decision_id = selector.get("accepting_decision_id")
    if (
        not isinstance(accepting_decision_id, int)
        or isinstance(accepting_decision_id, bool)
        or accepting_decision_id <= 0
    ):
        raise CoreReleaseEvidenceError("policy selector decision drift")
    policy = mapping(selector.get("policy"), "selected policy")
    exact(
        policy,
        {"version", "path", "commit", "blob_oid", "file_sha256"},
        "selected policy",
    )
    if policy.get("version") != 1 or policy.get("path") != POLICY_PATH:
        raise CoreReleaseEvidenceError("selected policy locator drift")
    commit = policy.get("commit")
    blob_oid = policy.get("blob_oid")
    file_sha = policy.get("file_sha256")
    if (
        not isinstance(commit, str)
        or re.fullmatch(r"[0-9a-f]{40}", commit) is None
        or not isinstance(blob_oid, str)
        or re.fullmatch(r"[0-9a-f]{40}", blob_oid) is None
        or not is_sha256(file_sha)
    ):
        raise CoreReleaseEvidenceError("selected policy Git identity is invalid")
    if git(repo_root, "rev-parse", f"{commit}:{POLICY_PATH}") != blob_oid:
        raise CoreReleaseEvidenceError("selected policy blob OID drift")
    raw = subprocess.run(
        ["git", "-C", str(repo_root), "show", f"{commit}:{POLICY_PATH}"],
        capture_output=True,
        check=False,
    )
    if raw.returncode != 0 or sha256(raw.stdout) != file_sha:
        raise CoreReleaseEvidenceError("selected policy file digest drift")
    validate_policy(loads_json(raw.stdout, "selected trust policy"))
    if selector.get("supersession") != {
        "supersedes_decision_id": None,
        "supersedes_policy_version": None,
    }:
        raise CoreReleaseEvidenceError("policy selector v1 supersession drift")
    return dict(selector)


def selector_ref(*, repo_root: Path, selector_path: Path) -> str:
    relative = selector_path.resolve().relative_to(repo_root.resolve()).as_posix()
    commit = git(repo_root, "rev-parse", "HEAD")
    blob = git(repo_root, "rev-parse", f"{commit}:{relative}")
    raw = subprocess.run(
        ["git", "-C", str(repo_root), "show", f"{commit}:{relative}"],
        capture_output=True,
        check=True,
    ).stdout
    return f"{SELECTOR_SCHEMA}:git:{commit}:{relative}:{blob}:{sha256(raw)}"


def validate_approvals(
    approvals: Sequence[object],
    *,
    roster: object,
    expected: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    valid_roster = validate_roster(roster, require_bindings=True)
    bindings = {entry["role"]: entry["principal"] for entry in valid_roster["bindings"]}
    accepted_roles: set[str] = set()
    accepted_principals: set[str] = set()
    for index, raw in enumerate(approvals):
        approval = mapping(raw, f"owner approval {index}")
        exact(
            approval,
            {
                "schema_version",
                "roster_version",
                "policy_version",
                "role",
                "principal",
                "payload",
                "created_at",
                "expires_at",
                "authority_ref",
                "withdrawn",
            },
            f"owner approval {index}",
        )
        role = approval.get("role")
        principal = approval.get("principal")
        created = timestamp(approval.get("created_at"), "approval created_at")
        expires = timestamp(approval.get("expires_at"), "approval expires_at")
        if (
            approval.get("schema_version") != APPROVAL_SCHEMA
            or approval.get("roster_version") != ROSTER_VERSION
            or approval.get("policy_version") != expected.get("policy_version")
        ):
            raise CoreReleaseEvidenceError("owner approval policy drift")
        if (
            role not in bindings
            or bindings[role] != principal
            or role in accepted_roles
            or principal in accepted_principals
        ):
            raise CoreReleaseEvidenceError("owner approval identity is ambiguous")
        if (
            approval.get("payload") != dict(expected)
            or approval.get("authority_ref") != expected.get("authority_ref")
            or approval.get("withdrawn") is not False
        ):
            raise CoreReleaseEvidenceError("owner approval payload or withdrawal drift")
        if created > now or expires <= now or expires > created + timedelta(hours=72):
            raise CoreReleaseEvidenceError("owner approval time window is invalid")
        accepted_roles.add(cast(str, role))
        accepted_principals.add(cast(str, principal))
    return {
        "schema_version": "dspx-core-release-authorization-evaluation-v1",
        "valid_approval_count": len(accepted_roles),
        "release_authority": len(accepted_roles) >= 2,
        "package_publication": False,
    }

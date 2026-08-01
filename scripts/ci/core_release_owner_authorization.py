#!/usr/bin/env python3
# ---
# summary: "Authenticates exact Core single-owner approvals with a hardware-backed OpenSSH SSHSIG key."
# read_when:
#   - "Changing the explicit single-owner Core release-authorization boundary."
# ---

from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, cast

from core_release_evidence_io import CoreReleaseEvidenceError, stable_regular_bytes

POLICY_SCHEMA = "dspx-core-release-owner-policy-v2"
PAYLOAD_SCHEMA = "dspx-core-single-owner-approval-payload-v1"
RESULT_SCHEMA = "dspx-core-single-owner-authorization-v1"
NAMESPACE = "dspx-core-release-authorization-v1"
REPOSITORY = {"name": "tryingET/dspx", "id": 1_318_473_695}
PAYLOAD_FIELDS = {
    "schema_version",
    "repository",
    "policy_version",
    "policy_selector_ref",
    "owner_policy_version",
    "owner_key_fingerprint",
    "wheel_sha256",
    "bundle_manifest_sha256",
    "signed_statement_sha256",
    "source_commit_sha",
    "package_version",
    "workflow_run_id",
    "workflow_run_attempt",
    "purpose",
    "nonce",
    "issued_at",
    "expires_at",
    "authority_ref",
}


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CoreReleaseEvidenceError(f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise CoreReleaseEvidenceError(f"{label} fields drift")


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise CoreReleaseEvidenceError(f"{label} must be UTC RFC3339")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise CoreReleaseEvidenceError(f"{label} is invalid") from exc
    if parsed.tzinfo != timezone.utc:
        raise CoreReleaseEvidenceError(f"{label} must be UTC")
    return parsed


def _sha(value: object, width: int = 64) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(rf"[0-9a-f]{{{width}}}", value) is not None
    )


def load_json(path: Path, label: str) -> Mapping[str, Any]:
    raw = stable_regular_bytes(path, label=label, limit=16 * 1024 * 1024)
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoreReleaseEvidenceError(f"{label} is not valid JSON") from exc
    return _mapping(value, label)


def validate_policy(value: object, *, now: datetime) -> dict[str, Any]:
    policy = _mapping(value, "owner policy")
    _exact(
        policy,
        {
            "schema_version",
            "owner_policy_version",
            "effective_at",
            "repository",
            "principal",
            "authentication",
            "approval",
            "revocation",
            "claims",
        },
        "owner policy",
    )
    if (
        policy.get("schema_version") != POLICY_SCHEMA
        or policy.get("owner_policy_version") != 2
    ):
        raise CoreReleaseEvidenceError("owner policy version drift")
    if _timestamp(policy.get("effective_at"), "effective_at") > now:
        raise CoreReleaseEvidenceError("owner policy is not effective")
    if policy.get("repository") != REPOSITORY:
        raise CoreReleaseEvidenceError("owner policy repository drift")
    principal = _mapping(policy.get("principal"), "owner principal")
    if principal != {
        "kind": "github-user",
        "login": "tryingET",
        "id": 260_287_438,
        "authority_model": "explicit_single_owner_concentrated_risk",
    }:
        raise CoreReleaseEvidenceError("owner principal drift")
    auth = _mapping(policy.get("authentication"), "owner authentication")
    _exact(
        auth,
        {
            "kind",
            "namespace",
            "key_type",
            "public_key",
            "fingerprint_sha256",
            "user_presence_required",
            "user_verification_required",
        },
        "owner authentication",
    )
    public_key = auth.get("public_key")
    if (
        auth.get("kind") != "openssh-sshsig-fido2"
        or auth.get("namespace") != NAMESPACE
        or auth.get("key_type")
        not in {"sk-ssh-ed25519@openssh.com", "sk-ecdsa-sha2-nistp256@openssh.com"}
        or not isinstance(public_key, str)
        or not public_key.startswith(cast(str, auth.get("key_type")) + " ")
        or auth.get("user_presence_required") is not True
        or auth.get("user_verification_required") is not True
    ):
        raise CoreReleaseEvidenceError("hardware-backed owner authentication drift")
    with tempfile.TemporaryDirectory() as directory:
        key = Path(directory) / "owner.pub"
        key.write_text(public_key + "\n", encoding="utf-8")
        result = subprocess.run(
            ["ssh-keygen", "-lf", str(key), "-E", "sha256"],
            capture_output=True,
            text=True,
            check=False,
        )
    if result.returncode != 0 or auth.get("fingerprint_sha256") not in result.stdout:
        raise CoreReleaseEvidenceError("owner key fingerprint drift")
    if policy.get("approval") != {
        "purpose": "authorize-dspx-core-wheel-release",
        "max_age_seconds": 900,
        "single_use_nonce": True,
    }:
        raise CoreReleaseEvidenceError("owner approval policy drift")
    revocation = _mapping(policy.get("revocation"), "owner revocation")
    _exact(
        revocation,
        {"authorization_enabled", "disabled_reason", "revoked_fingerprints"},
        "owner revocation",
    )
    if (
        not isinstance(revocation.get("authorization_enabled"), bool)
        or not isinstance(revocation.get("disabled_reason"), str)
        or revocation.get("revoked_fingerprints") != []
    ):
        raise CoreReleaseEvidenceError("owner revocation policy drift")
    if policy.get("claims") != {
        "human_principal_count": 1,
        "independent_quorum": False,
        "concentrated_risk_accepted": True,
        "technical_controls_are_conjunction_not_principals": True,
        "package_publication": False,
        "sdist_supported": False,
    }:
        raise CoreReleaseEvidenceError("owner authority claims drift")
    return dict(policy)


def canonical_payload(
    value: object, *, policy: Mapping[str, Any], now: datetime
) -> bytes:
    payload = _mapping(value, "approval payload")
    _exact(payload, PAYLOAD_FIELDS, "approval payload")
    auth = _mapping(policy["authentication"], "owner authentication")
    if (
        payload.get("schema_version") != PAYLOAD_SCHEMA
        or payload.get("repository") != REPOSITORY
    ):
        raise CoreReleaseEvidenceError("approval payload identity drift")
    if (
        payload.get("owner_policy_version") != policy["owner_policy_version"]
        or payload.get("owner_key_fingerprint") != auth["fingerprint_sha256"]
    ):
        raise CoreReleaseEvidenceError("approval owner binding drift")
    if (
        not isinstance(payload.get("policy_version"), int)
        or cast(int, payload["policy_version"]) <= 0
    ):
        raise CoreReleaseEvidenceError("approval policy version drift")
    if not isinstance(payload.get("policy_selector_ref"), str) or not cast(
        str, payload["policy_selector_ref"]
    ).startswith("dspx-core-policy-selector-v1:git:"):
        raise CoreReleaseEvidenceError("approval selector binding drift")
    for field in ("wheel_sha256", "bundle_manifest_sha256", "signed_statement_sha256"):
        if not _sha(payload.get(field)):
            raise CoreReleaseEvidenceError(f"approval {field} drift")
    if not _sha(payload.get("source_commit_sha"), 40) or not _sha(payload.get("nonce")):
        raise CoreReleaseEvidenceError("approval source or nonce drift")
    for field in ("workflow_run_id", "workflow_run_attempt"):
        if (
            not isinstance(payload.get(field), int)
            or isinstance(payload.get(field), bool)
            or cast(int, payload[field]) <= 0
        ):
            raise CoreReleaseEvidenceError(f"approval {field} drift")
    if (
        payload.get("purpose") != "authorize-dspx-core-wheel-release"
        or not isinstance(payload.get("package_version"), str)
        or not payload.get("package_version")
        or not isinstance(payload.get("authority_ref"), str)
        or not payload.get("authority_ref")
    ):
        raise CoreReleaseEvidenceError("approval purpose or authority ref drift")
    issued = _timestamp(payload.get("issued_at"), "issued_at")
    expires = _timestamp(payload.get("expires_at"), "expires_at")
    if issued > now or expires <= now or expires > issued + timedelta(seconds=900):
        raise CoreReleaseEvidenceError("approval time window drift")
    return (
        json.dumps(dict(payload), sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()


def verify_owner_signature(
    *, policy: Mapping[str, Any], payload_raw: bytes, signature_path: Path
) -> None:
    signature = stable_regular_bytes(
        signature_path, label="owner SSHSIG", limit=64 * 1024
    )
    auth = _mapping(policy["authentication"], "owner authentication")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        allowed = root / "allowed_signers"
        sig = root / "approval.sig"
        allowed.write_text(
            f'tryingET@260287438 namespaces="{NAMESPACE}" {auth["public_key"]}\n',
            encoding="utf-8",
        )
        sig.write_bytes(signature)
        result = subprocess.run(
            [
                "ssh-keygen",
                "-Y",
                "verify",
                "-f",
                str(allowed),
                "-I",
                "tryingET@260287438",
                "-n",
                NAMESPACE,
                "-s",
                str(sig),
            ],
            input=payload_raw,
            capture_output=True,
            check=False,
        )
    if result.returncode != 0:
        raise CoreReleaseEvidenceError(
            "hardware-backed owner approval signature failed"
        )


def authenticate_owner_approval(
    *,
    policy: object,
    payload: object,
    signature_path: Path,
    consumed_nonces: set[str],
    now: datetime,
) -> dict[str, Any]:
    """Authenticate owner intent without granting release authority.

    The later release consumer must independently verify evidence, current policy,
    denylist, current paired custody, and atomically consume the nonce. Keeping
    this adapter non-authoritative prevents caller-asserted booleans from
    becoming a release bypass.
    """
    valid_policy = validate_policy(policy, now=now)
    revocation = _mapping(valid_policy["revocation"], "owner revocation")
    if revocation["authorization_enabled"] is not True:
        raise CoreReleaseEvidenceError("owner authorization is disabled")
    raw = canonical_payload(payload, policy=valid_policy, now=now)
    verify_owner_signature(
        policy=valid_policy, payload_raw=raw, signature_path=signature_path
    )
    approved = _mapping(payload, "approval payload")
    nonce = cast(str, approved["nonce"])
    if nonce in consumed_nonces:
        raise CoreReleaseEvidenceError("approval nonce was already consumed")
    return {
        "schema_version": RESULT_SCHEMA,
        "status": "owner_authenticated_technical_consumer_required",
        "principal": "tryingET@260287438",
        "owner_authentication": "hardware-backed-sshsig-fido2",
        "independent_quorum": False,
        "concentrated_risk": True,
        "approval_payload_sha256": hashlib.sha256(raw).hexdigest(),
        "nonce_pending_atomic_consumption": nonce,
        "release_authority": False,
        "package_publication": False,
        "sdist_supported": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--signature", type=Path, required=True)
    parser.add_argument("--now", required=True)
    args = parser.parse_args()
    now = _timestamp(args.now, "now")
    result = authenticate_owner_approval(
        policy=load_json(args.policy, "owner policy"),
        payload=load_json(args.payload, "approval payload"),
        signature_path=args.signature,
        consumed_nonces=set(),
        now=now,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CoreReleaseEvidenceError as exc:
        raise SystemExit(f"Core release owner authorization failed: {exc}") from exc

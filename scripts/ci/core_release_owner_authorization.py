#!/usr/bin/env python3
# ---
# summary: "Authenticates exact Core single-owner approvals with a hardware-backed OpenSSH SSHSIG key."
# read_when:
#   - "Changing the explicit single-owner Core release-authorization boundary."
# ---

from __future__ import annotations

import argparse
import base64
import binascii
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import tempfile
from typing import Any, cast

from core_release_evidence_io import CoreReleaseEvidenceError, stable_regular_bytes
from core_release_policy import SELECTOR_REF_PATTERN

POLICY_SCHEMA = "dspx-core-release-owner-policy-v2"
PAYLOAD_SCHEMA = "dspx-core-single-owner-approval-payload-v2"
RESULT_SCHEMA = "dspx-core-single-owner-authorization-v2"
NAMESPACE = "dspx-core-release-authorization-v1"
SK_ALGORITHM = "sk-ssh-ed25519@openssh.com"
REPOSITORY = {"name": "tryingET/dspx", "id": 1_318_473_695}
OWNER_SELECTOR_REF_PATTERN = re.compile(
    r"^dspx-core-owner-policy-selector-v1:git:"
    r"(?P<commit>[0-9a-f]{40}):"
    r"(?P<path>governance/release-signing/release-owner-policy-selector-v[0-9]{3}\.json):"
    r"(?P<blob>[0-9a-f]{40}):(?P<sha256>[0-9a-f]{64})$"
)
AUTHORITY_REF_PATTERN = re.compile(r"^ak-decision:(?P<id>[1-9][0-9]*)$")
FINGERPRINT_PATTERN = re.compile(r"^SHA256:[A-Za-z0-9+/]{43}$")
PAYLOAD_FIELDS = {
    "schema_version",
    "repository",
    "policy_version",
    "policy_selector_ref",
    "owner_policy_version",
    "owner_policy_selector_ref",
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


def loads_json(raw: bytes, label: str) -> Mapping[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise CoreReleaseEvidenceError(f"{label} has duplicate key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(raw, object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoreReleaseEvidenceError(f"{label} is not valid JSON") from exc
    return _mapping(value, label)


def load_json(path: Path, label: str) -> Mapping[str, Any]:
    raw = stable_regular_bytes(path, label=label, limit=16 * 1024 * 1024)
    return loads_json(raw, label)


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
    version = policy.get("owner_policy_version")
    if (
        policy.get("schema_version") != POLICY_SCHEMA
        or not isinstance(version, int)
        or isinstance(version, bool)
        or version < 2
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
        or auth.get("key_type") != SK_ALGORITHM
        or not isinstance(public_key, str)
        or not public_key.startswith(SK_ALGORITHM + " ")
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
    output_fields = result.stdout.split()
    observed_fingerprint = output_fields[1] if len(output_fields) >= 2 else None
    configured_fingerprint = auth.get("fingerprint_sha256")
    if (
        result.returncode != 0
        or not isinstance(configured_fingerprint, str)
        or FINGERPRINT_PATTERN.fullmatch(configured_fingerprint) is None
        or observed_fingerprint != configured_fingerprint
    ):
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
    enabled = revocation.get("authorization_enabled")
    reason = revocation.get("disabled_reason")
    revoked = revocation.get("revoked_fingerprints")
    if (
        not isinstance(enabled, bool)
        or not isinstance(revoked, list)
        or len(revoked) != len(set(cast(list[object], revoked)))
        or any(
            not isinstance(item, str) or FINGERPRINT_PATTERN.fullmatch(item) is None
            for item in revoked
        )
        or (enabled and reason is not None)
        or (not enabled and (not isinstance(reason, str) or not reason))
    ):
        raise CoreReleaseEvidenceError("owner revocation policy drift")
    if auth["fingerprint_sha256"] in revoked:
        raise CoreReleaseEvidenceError("current owner key is revoked")
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
        or isinstance(payload.get("policy_version"), bool)
        or cast(int, payload["policy_version"]) <= 0
    ):
        raise CoreReleaseEvidenceError("approval policy version drift")
    trust_ref = payload.get("policy_selector_ref")
    owner_ref = payload.get("owner_policy_selector_ref")
    if (
        not isinstance(trust_ref, str)
        or SELECTOR_REF_PATTERN.fullmatch(trust_ref) is None
    ):
        raise CoreReleaseEvidenceError("approval trust selector binding drift")
    if (
        not isinstance(owner_ref, str)
        or OWNER_SELECTOR_REF_PATTERN.fullmatch(owner_ref) is None
    ):
        raise CoreReleaseEvidenceError("approval owner selector binding drift")
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
    authority_ref = payload.get("authority_ref")
    if (
        payload.get("purpose") != "authorize-dspx-core-wheel-release"
        or not isinstance(payload.get("package_version"), str)
        or not payload.get("package_version")
        or not isinstance(authority_ref, str)
        or AUTHORITY_REF_PATTERN.fullmatch(authority_ref) is None
    ):
        raise CoreReleaseEvidenceError("approval purpose or authority ref drift")
    issued = _timestamp(payload.get("issued_at"), "issued_at")
    expires = _timestamp(payload.get("expires_at"), "expires_at")
    if issued > now or expires <= now or expires > issued + timedelta(seconds=900):
        raise CoreReleaseEvidenceError("approval time window drift")
    return (
        json.dumps(dict(payload), sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()


def _read_u32(raw: bytes, offset: int, label: str) -> tuple[int, int]:
    if offset + 4 > len(raw):
        raise CoreReleaseEvidenceError(f"{label} is truncated")
    return struct.unpack(">I", raw[offset : offset + 4])[0], offset + 4


def _read_string(
    raw: bytes, offset: int, label: str, *, limit: int = 128 * 1024
) -> tuple[bytes, int]:
    size, offset = _read_u32(raw, offset, label)
    if size > limit or offset + size > len(raw):
        raise CoreReleaseEvidenceError(f"{label} string is invalid")
    return raw[offset : offset + size], offset + size


def _decode_sshsig_pem(raw: bytes) -> bytes:
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise CoreReleaseEvidenceError("owner SSHSIG is not ASCII PEM") from exc
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if (
        len(lines) < 3
        or lines[0] != "-----BEGIN SSH SIGNATURE-----"
        or lines[-1] != "-----END SSH SIGNATURE-----"
    ):
        raise CoreReleaseEvidenceError("owner SSHSIG PEM framing drift")
    try:
        return base64.b64decode("".join(lines[1:-1]), validate=True)
    except (ValueError, binascii.Error) as exc:
        raise CoreReleaseEvidenceError("owner SSHSIG base64 drift") from exc


def parse_sk_signature_details(
    signature_pem: bytes, *, policy: Mapping[str, Any]
) -> dict[str, Any]:
    raw = _decode_sshsig_pem(signature_pem)
    if not raw.startswith(b"SSHSIG"):
        raise CoreReleaseEvidenceError("owner SSHSIG magic drift")
    offset = 6
    version, offset = _read_u32(raw, offset, "owner SSHSIG")
    public_blob, offset = _read_string(raw, offset, "owner SSHSIG public key")
    namespace, offset = _read_string(raw, offset, "owner SSHSIG namespace", limit=256)
    reserved, offset = _read_string(raw, offset, "owner SSHSIG reserved", limit=1024)
    hash_algorithm, offset = _read_string(raw, offset, "owner SSHSIG hash", limit=64)
    signature_blob, offset = _read_string(raw, offset, "owner SSHSIG signature")
    if (
        version != 1
        or offset != len(raw)
        or namespace != NAMESPACE.encode("ascii")
        or reserved != b""
        or hash_algorithm not in {b"sha256", b"sha512"}
    ):
        raise CoreReleaseEvidenceError("owner SSHSIG envelope drift")
    auth = _mapping(policy["authentication"], "owner authentication")
    try:
        configured_blob = base64.b64decode(
            cast(str, auth["public_key"]).split()[1], validate=True
        )
    except (IndexError, ValueError, binascii.Error) as exc:
        raise CoreReleaseEvidenceError("owner public key encoding drift") from exc
    if public_blob != configured_blob:
        raise CoreReleaseEvidenceError("owner SSHSIG public key drift")
    algorithm, inner_offset = _read_string(
        signature_blob, 0, "owner SK algorithm", limit=128
    )
    if algorithm != SK_ALGORITHM.encode("ascii"):
        raise CoreReleaseEvidenceError("owner SK signature algorithm drift")
    raw_signature, inner_offset = _read_string(
        signature_blob, inner_offset, "owner SK raw signature", limit=256
    )
    if len(raw_signature) != 64 or inner_offset + 5 != len(signature_blob):
        raise CoreReleaseEvidenceError("owner SK signature detail drift")
    flags = signature_blob[inner_offset]
    counter = struct.unpack(">I", signature_blob[inner_offset + 1 : inner_offset + 5])[
        0
    ]
    if flags & 0x01 == 0:
        raise CoreReleaseEvidenceError("owner SK user presence is absent")
    if flags & 0x04 == 0:
        raise CoreReleaseEvidenceError("owner SK user verification is absent")
    if flags & ~0x05:
        raise CoreReleaseEvidenceError("owner SK flags drift")
    return {
        "user_presence": True,
        "user_verification": True,
        "counter": counter,
        "flags": flags,
    }


def verify_owner_signature(
    *, policy: Mapping[str, Any], payload_raw: bytes, signature_path: Path
) -> dict[str, Any]:
    signature = stable_regular_bytes(
        signature_path, label="owner SSHSIG", limit=64 * 1024
    )
    details = parse_sk_signature_details(signature, policy=policy)
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
    return details


def authenticate_owner_approval(
    *,
    policy: object,
    payload: object,
    signature_path: Path,
    consumed_nonces: set[str],
    now: datetime,
) -> dict[str, Any]:
    """Authenticate owner intent; technical consumer and nonce commit remain required."""
    valid_policy = validate_policy(policy, now=now)
    revocation = _mapping(valid_policy["revocation"], "owner revocation")
    if revocation["authorization_enabled"] is not True:
        raise CoreReleaseEvidenceError("owner authorization is disabled")
    raw = canonical_payload(payload, policy=valid_policy, now=now)
    details = verify_owner_signature(
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
        "owner_authentication": "hardware-backed-sshsig-fido2-up-uv",
        "security_key_counter": details["counter"],
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
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
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

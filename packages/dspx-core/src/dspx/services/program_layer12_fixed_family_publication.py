# summary: "Verifies the closed DSPx owner-local publication for one Layer-12 transition family."
# read_when:
#   - "Changing the fixed continue-current-execution-task family, signed publication fixture, or external trust pins."

"""Pure verification for the DSPx-owned Layer-12 fixed-family publication.

The verifier has no AK integration and performs no publication. AK wire identity and
Ed25519 trust are caller-supplied pins; declarations inside the artifact are evidence
only and can never bootstrap trust.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, cast

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SPEC_SCHEMA = "layer12-fixed-family-spec-v1"
PUBLICATION_SCHEMA = "layer12-fixed-family-publication-v1"
PROTOCOL_VERSION = "layer12-v1"
ONLY_TOKEN = "continue_current_execution_task"
OWNER_LOCAL_SCOPE = "owner_local_artifact_only"


class Layer12FixedFamilyPublicationError(ValueError):
    """A fixed-family spec or publication is malformed, drifted, or untrusted."""


def canonical_json(value: object) -> str:
    """Return the byte-stable JSON representation used for digests/signatures."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def sha256_digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _object(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise Layer12FixedFamilyPublicationError(f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def _closed(item: Mapping[str, Any], required: set[str], label: str) -> None:
    missing = required - set(item)
    extra = set(item) - required
    if missing or extra:
        raise Layer12FixedFamilyPublicationError(
            f"{label} fields mismatch; missing={sorted(missing)} extra={sorted(extra)}"
        )


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise Layer12FixedFamilyPublicationError(f"{label} must be non-empty text")
    return value


def _digest(value: object, label: str) -> str:
    text = _text(value, label)
    if re.fullmatch(r"sha256:[0-9a-f]{64}", text) is None:
        raise Layer12FixedFamilyPublicationError(f"{label} must be a sha256 digest")
    return text


def _time(value: object, label: str) -> datetime:
    text = _text(value, label)
    if (
        re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})",
            text,
        )
        is None
    ):
        raise Layer12FixedFamilyPublicationError(f"{label} must be RFC3339")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Layer12FixedFamilyPublicationError(f"{label} must be RFC3339") from exc
    if parsed.tzinfo is None:
        raise Layer12FixedFamilyPublicationError(f"{label} must include timezone")
    return parsed.astimezone(timezone.utc)


def _exact(item: Mapping[str, Any], expected: Mapping[str, object], label: str) -> None:
    _closed(item, set(expected), label)
    for field, value in expected.items():
        if item[field] != value:
            raise Layer12FixedFamilyPublicationError(f"{label}.{field} drift")


def check_fixed_family_spec(
    spec: object,
    *,
    expected_owner: str,
    expected_family_id: str,
    expected_scope_digest: str,
    expected_ak_wire_identity: str,
    expected_ak_wire_digest: str,
) -> dict[str, str]:
    """Validate the one-token spec against independently supplied AK/scope pins."""

    item = _object(spec, "spec")
    _closed(
        item,
        {
            "schema_version",
            "owner",
            "family_id",
            "protocol_version",
            "transition_tokens",
            "scope_digest",
            "ak_wire_evidence",
            "publication_contract",
            "authority_boundary",
        },
        "spec",
    )
    if item["schema_version"] != SPEC_SCHEMA:
        raise Layer12FixedFamilyPublicationError("unsupported spec schema")
    if item["owner"] != _text(expected_owner, "expected_owner"):
        raise Layer12FixedFamilyPublicationError("spec owner identity drift")
    if item["family_id"] != _text(expected_family_id, "expected_family_id"):
        raise Layer12FixedFamilyPublicationError("spec family identity drift")
    if item["protocol_version"] != PROTOCOL_VERSION:
        raise Layer12FixedFamilyPublicationError("spec protocol identity drift")
    if item["transition_tokens"] != [ONLY_TOKEN]:
        raise Layer12FixedFamilyPublicationError(
            "spec must contain exactly the one allowed token"
        )
    if _digest(item["scope_digest"], "scope_digest") != _digest(
        expected_scope_digest, "expected_scope_digest"
    ):
        raise Layer12FixedFamilyPublicationError("spec scope digest drift")

    wire = _object(item["ak_wire_evidence"], "spec.ak_wire_evidence")
    _exact(
        wire,
        {
            "source_owner": "softwareco/owned/agent-kernel",
            "wire_identity": _text(
                expected_ak_wire_identity, "expected_ak_wire_identity"
            ),
            "wire_digest": _digest(expected_ak_wire_digest, "expected_ak_wire_digest"),
            "declaration_is_trust_root": False,
        },
        "spec.ak_wire_evidence",
    )
    publication = _object(item["publication_contract"], "spec.publication_contract")
    _exact(
        publication,
        {
            "publication_scope": OWNER_LOCAL_SCOPE,
            "signed_payload": "publication_object_without_signature",
            "signature_algorithm": "Ed25519",
            "external_trust_required": True,
        },
        "spec.publication_contract",
    )
    authority = _object(item["authority_boundary"], "spec.authority_boundary")
    _exact(
        authority,
        {
            "owner_local_artifact_publication": True,
            "affected_use_publication": False,
            "ak_legality": False,
            "policy_selection": False,
            "apply": False,
            "promotion": False,
            "activation": False,
            "dogfood": False,
            "rollout": False,
        },
        "spec.authority_boundary",
    )
    return {
        "owner": expected_owner,
        "family_id": expected_family_id,
        "transition_token": ONLY_TOKEN,
        "spec_digest": sha256_digest(item),
    }


def check_fixed_family_publication(
    publication: object,
    *,
    spec: object,
    expected_owner: str,
    expected_family_id: str,
    expected_spec_digest: str,
    expected_scope_digest: str,
    expected_ak_wire_identity: str,
    expected_ak_wire_digest: str,
    expected_key_id: str,
    trusted_public_key_b64: str,
    expected_key_status: str,
    expected_key_valid_from: str,
    expected_key_valid_until: str,
    verification_time: str,
) -> dict[str, object]:
    """Verify a publication using only caller-pinned trust and identity inputs."""

    spec_result = check_fixed_family_spec(
        spec,
        expected_owner=expected_owner,
        expected_family_id=expected_family_id,
        expected_scope_digest=expected_scope_digest,
        expected_ak_wire_identity=expected_ak_wire_identity,
        expected_ak_wire_digest=expected_ak_wire_digest,
    )
    pinned_spec_digest = _digest(expected_spec_digest, "expected_spec_digest")
    if spec_result["spec_digest"] != pinned_spec_digest:
        raise Layer12FixedFamilyPublicationError(
            "spec digest does not match external pin"
        )

    item = _object(publication, "publication")
    _closed(
        item,
        {
            "schema_version",
            "publication_id",
            "published_at",
            "publication_scope",
            "identity",
            "ak_wire_evidence",
            "signer_evidence",
            "authority_boundary",
            "signature",
        },
        "publication",
    )
    if item["schema_version"] != PUBLICATION_SCHEMA:
        raise Layer12FixedFamilyPublicationError("unsupported publication schema")
    _text(item["publication_id"], "publication_id")
    published_at = _time(item["published_at"], "published_at")
    if item["publication_scope"] != OWNER_LOCAL_SCOPE:
        raise Layer12FixedFamilyPublicationError(
            "affected-use publication is forbidden"
        )

    identity = _object(item["identity"], "publication.identity")
    _exact(
        identity,
        {
            "owner": expected_owner,
            "family_id": expected_family_id,
            "protocol_version": PROTOCOL_VERSION,
            "transition_token": ONLY_TOKEN,
            "spec_schema_version": SPEC_SCHEMA,
            "spec_digest": pinned_spec_digest,
            "scope_digest": _digest(expected_scope_digest, "expected_scope_digest"),
        },
        "publication.identity",
    )
    wire = _object(item["ak_wire_evidence"], "publication.ak_wire_evidence")
    _exact(
        wire,
        {
            "source_owner": "softwareco/owned/agent-kernel",
            "wire_identity": expected_ak_wire_identity,
            "wire_digest": _digest(expected_ak_wire_digest, "expected_ak_wire_digest"),
            "declaration_is_trust_root": False,
        },
        "publication.ak_wire_evidence",
    )

    signer = _object(item["signer_evidence"], "publication.signer_evidence")
    _exact(
        signer,
        {
            "algorithm": "Ed25519",
            "key_id": _text(expected_key_id, "expected_key_id"),
            "public_key_b64": _text(trusted_public_key_b64, "trusted_public_key_b64"),
            "key_status": _text(expected_key_status, "expected_key_status"),
            "valid_from": _text(expected_key_valid_from, "expected_key_valid_from"),
            "valid_until": _text(expected_key_valid_until, "expected_key_valid_until"),
            "declaration_is_trust_root": False,
        },
        "publication.signer_evidence",
    )
    if expected_key_status != "active":
        raise Layer12FixedFamilyPublicationError("external key lifecycle is not active")
    valid_from = _time(expected_key_valid_from, "expected_key_valid_from")
    valid_until = _time(expected_key_valid_until, "expected_key_valid_until")
    current = _time(verification_time, "verification_time")
    if valid_until <= valid_from or not (
        valid_from <= published_at <= current < valid_until
    ):
        raise Layer12FixedFamilyPublicationError(
            "key lifecycle or publication time is invalid"
        )

    authority = _object(item["authority_boundary"], "publication.authority_boundary")
    _exact(
        authority,
        {
            "owner_local_artifact_publication": True,
            "affected_use_publication": False,
            "ak_legality": False,
            "policy_selection": False,
            "apply": False,
            "promotion": False,
            "activation": False,
            "dogfood": False,
            "rollout": False,
        },
        "publication.authority_boundary",
    )

    signature = _object(item["signature"], "publication.signature")
    _closed(
        signature,
        {"algorithm", "key_id", "signed_payload_digest", "signature_b64"},
        "publication.signature",
    )
    if signature["algorithm"] != "Ed25519" or signature["key_id"] != expected_key_id:
        raise Layer12FixedFamilyPublicationError("signature identity drift")
    signed_payload = {key: value for key, value in item.items() if key != "signature"}
    computed_digest = sha256_digest(signed_payload)
    if signature["signed_payload_digest"] != computed_digest:
        raise Layer12FixedFamilyPublicationError("signed payload digest drift")
    try:
        public_key_bytes = base64.b64decode(trusted_public_key_b64, validate=True)
        signature_bytes = base64.b64decode(
            _text(signature["signature_b64"], "signature_b64"), validate=True
        )
    except (binascii.Error, ValueError) as exc:
        raise Layer12FixedFamilyPublicationError(
            "invalid base64 signature material"
        ) from exc
    if len(public_key_bytes) != 32 or len(signature_bytes) != 64:
        raise Layer12FixedFamilyPublicationError("invalid Ed25519 material length")
    try:
        Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(
            signature_bytes, canonical_json(signed_payload).encode()
        )
    except (InvalidSignature, ValueError) as exc:
        raise Layer12FixedFamilyPublicationError(
            "invalid publication signature"
        ) from exc

    return {
        "verified": True,
        "publication_id": item["publication_id"],
        "owner": expected_owner,
        "family_id": expected_family_id,
        "transition_token": ONLY_TOKEN,
        "publication_scope": OWNER_LOCAL_SCOPE,
        "spec_digest": pinned_spec_digest,
        "ak_wire_trust_source": "external_pin",
        "signature_trust_source": "external_pin",
        "authority_granted": False,
    }

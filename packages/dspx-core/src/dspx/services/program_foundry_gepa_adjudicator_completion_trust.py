# summary: "Validates digest-pinned, request-scoped verifier trust policies for external adjudicator completions."
# read_when:
#   - "Changing adjudicator verifier trust anchors, key lifecycle, policy scope, or canonical completion JSON."

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Any, Mapping

ADJUDICATOR_VERIFIER_TRUST_POLICY_SCHEMA = "dspx-adjudicator-verifier-trust-policy-v1"
_OWNER_COMPLETION_SCOPE = "dspx_foundry_gepa_adjudicator_completion"


class ProgramFoundryGepaAdjudicatorCompletionError(ValueError):
    """Raised when an externally verified completion cannot be imported safely."""


def canonical_completion_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            f"adjudicator completion must be canonical JSON: {exc}"
        ) from exc


def completion_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProgramFoundryGepaAdjudicatorCompletionError(f"{label} is required")
    return value.strip()


def completion_timestamp(value: object, label: str) -> datetime:
    text = completion_text(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            f"{label} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            f"{label} must include a timezone"
        )
    return parsed


def completion_exact_keys(
    value: object, expected: set[str], label: str
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ProgramFoundryGepaAdjudicatorCompletionError(f"{label} must be an object")
    item = {str(key): member for key, member in value.items()}
    if set(item) != expected:
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            f"{label} has unexpected or missing fields"
        )
    return item


def validate_adjudicator_verifier_trust_policy(
    payload: Mapping[str, Any],
    *,
    policy_sha256: str,
    trusted_policy_sha256: str,
    request: Mapping[str, Any],
    request_sha256: str,
    verification_time: datetime,
) -> dict[str, Any]:
    """Validate a scoped policy whose exact raw bytes are trusted out of band."""

    policy = completion_exact_keys(
        payload,
        {
            "schema_version",
            "policy_id",
            "observed_at",
            "expires_at",
            "verification_scope",
            "request_binding",
            "verifier_evidence",
            "authority_boundary",
        },
        "verifier trust policy",
    )
    if policy["schema_version"] != ADJUDICATOR_VERIFIER_TRUST_POLICY_SCHEMA:
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "unsupported verifier trust policy schema"
        )
    pinned_digest = completion_text(trusted_policy_sha256, "trusted_policy_sha256")
    if len(pinned_digest) != 64 or any(
        character not in "0123456789abcdef" for character in pinned_digest
    ):
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "trusted verifier policy sha256 must be a lowercase digest"
        )
    if policy_sha256 != pinned_digest:
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "verifier trust policy canonical payload does not match the external digest pin"
        )
    selected = request.get("selected_adjudicator")
    if not isinstance(selected, Mapping):
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "verifier trust policy requires a selected adjudicator"
        )
    bindings = request.get("bindings")
    if not isinstance(bindings, Mapping):
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "verifier trust policy requires request lineage bindings"
        )
    expected_request_binding = {
        "request_id": request.get("request_id"),
        "request_sha256": request_sha256,
        "request_canonical_sha256": hashlib.sha256(
            canonical_completion_json(request)
        ).hexdigest(),
        "task_kind": request.get("task_kind"),
        "registration_id": selected.get("registration_id"),
        "registration_snapshot_sha256": bindings.get("registration_snapshot_sha256"),
        "selection_sha256": bindings.get("selection_sha256"),
    }
    policy_request_binding = completion_exact_keys(
        policy["request_binding"],
        set(expected_request_binding),
        "verifier trust policy request_binding",
    )
    if (
        policy["verification_scope"] != _OWNER_COMPLETION_SCOPE
        or policy_request_binding != expected_request_binding
    ):
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "verifier trust policy does not match the exact request scope"
        )
    verifier = completion_exact_keys(
        policy["verifier_evidence"],
        {
            "owner",
            "implementation_id",
            "protocol_version",
            "algorithm",
            "key_id",
            "public_key_b64",
            "key_status",
            "valid_from",
            "valid_until",
            "declaration_is_trust_root",
        },
        "verifier trust policy verifier_evidence",
    )
    for key in ("owner", "implementation_id", "protocol_version", "key_id"):
        completion_text(verifier[key], f"verifier trust policy {key}")
    if (
        verifier["algorithm"] != "Ed25519"
        or verifier["key_status"] != "active"
        or verifier["declaration_is_trust_root"] is not False
    ):
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "verifier trust policy key contract is invalid"
        )
    authority = completion_exact_keys(
        policy["authority_boundary"],
        {
            "local_completion_trust_anchor",
            "social_identity_authority",
            "production_promotion",
            "activation",
            "governance",
            "external_apply",
        },
        "verifier trust policy authority_boundary",
    )
    if authority != {
        "local_completion_trust_anchor": True,
        "social_identity_authority": False,
        "production_promotion": False,
        "activation": False,
        "governance": False,
        "external_apply": False,
    }:
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "verifier trust policy widens local trust authority"
        )
    observed_at = completion_timestamp(
        policy["observed_at"], "verifier policy observed_at"
    )
    expires_at = completion_timestamp(
        policy["expires_at"], "verifier policy expires_at"
    )
    valid_from = completion_timestamp(verifier["valid_from"], "verifier key valid_from")
    valid_until = completion_timestamp(
        verifier["valid_until"], "verifier key valid_until"
    )
    if not (valid_from <= observed_at <= verification_time < expires_at <= valid_until):
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "verifier trust policy is stale or outside the active key lifecycle"
        )
    return {
        "policy_id": completion_text(policy["policy_id"], "verifier policy policy_id"),
        "sha256": policy_sha256,
        "observed_at": policy["observed_at"],
        "expires_at": policy["expires_at"],
        "verifier": verifier,
    }

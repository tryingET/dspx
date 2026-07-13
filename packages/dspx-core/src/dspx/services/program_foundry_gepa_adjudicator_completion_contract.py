# summary: "Verifies signed owner adjudicator completions against external trust pins and computes panel quorum."
# read_when:
#   - "Changing signed owner completion schemas, external trust pins, subject claims, or panel quorum semantics."

from __future__ import annotations

import base64
import binascii
from collections import Counter
from datetime import datetime
import hashlib
from typing import Any, Mapping, Sequence

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from dspx.services.program_adjudicator_protocol import SHARED_ADJUDICATOR_DISPOSITIONS
from dspx.services.program_foundry_gepa_adjudicator_completion_trust import (
    ProgramFoundryGepaAdjudicatorCompletionError,
    canonical_completion_json,
    completion_exact_keys as _exact_keys,
    completion_text as _text,
    completion_timestamp as _timestamp,
    validate_adjudicator_verifier_trust_policy,
)

OWNER_VERIFIED_ADJUDICATOR_COMPLETION_SCHEMA = (
    "dspx-owner-verified-adjudicator-completion-v1"
)
PROGRAM_FOUNDRY_GEPA_ADJUDICATOR_COMPLETION_SCHEMA = (
    "dspx-program-foundry-gepa-adjudicator-completion-v1"
)
_OWNER_COMPLETION_SCOPE = "dspx_foundry_gepa_adjudicator_completion"
_EXTERNAL_COMPLETION_BACKENDS = frozenset(
    {"human", "human_panel", "multi_agent_panel", "hybrid"}
)
_ALLOWED_CLAIM_DISPOSITIONS = frozenset(SHARED_ADJUDICATOR_DISPOSITIONS) - {"pending"}


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def expected_adjudicator_request_binding(
    request: Mapping[str, Any], request_sha256: str
) -> dict[str, Any]:
    selected = request.get("selected_adjudicator")
    bindings = request.get("bindings")
    if not isinstance(selected, Mapping) or not isinstance(bindings, Mapping):
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "pending adjudicator request is missing selected lineage"
        )
    required_bindings = (
        "comparison_jury_receipt_sha256",
        "jury_results_sha256",
        "candidate_manifest_sha256",
        "comparison_sha256",
        "registration_snapshot_sha256",
        "selection_sha256",
    )
    if any(not isinstance(bindings.get(key), str) for key in required_bindings):
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "pending adjudicator request has incomplete hash lineage"
        )
    return {
        "request_id": request["request_id"],
        "request_sha256": request_sha256,
        "request_canonical_sha256": _sha256(canonical_completion_json(request)),
        "proposal_id": request["proposal_id"],
        "task_kind": request["task_kind"],
        "registration_id": selected["registration_id"],
        **{key: bindings[key] for key in required_bindings},
    }


def _registered_subjects(selected: Mapping[str, Any]) -> list[tuple[str, str]]:
    identity = selected.get("identity_claims")
    if not isinstance(identity, Mapping):
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "selected adjudicator identity claims are missing"
        )
    subjects = identity.get("subjects")
    kinds = identity.get("subject_kinds")
    if (
        not isinstance(subjects, list)
        or not isinstance(kinds, list)
        or len(subjects) != len(kinds)
        or not all(isinstance(item, str) and item for item in subjects)
        or not all(item in {"human", "agent"} for item in kinds)
    ):
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "selected adjudicator subject declarations are invalid"
        )
    return list(zip(subjects, kinds, strict=True))


def _validated_claims(
    raw_claims: object,
    *,
    selected: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if not isinstance(raw_claims, list):
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "owner completion claims must be a list"
        )
    registered = _registered_subjects(selected)
    claims_by_subject: dict[str, dict[str, Any]] = {}
    expected_keys = {
        "subject",
        "subject_kind",
        "disposition",
        "owner_verifier_assertions",
    }
    assertion_keys = {
        "identity_verified",
        "roster_membership_verified",
        "participation_verified",
        "disposition_attested",
        "subject_signature_verified",
    }
    for index, raw_claim in enumerate(raw_claims):
        claim = _exact_keys(raw_claim, expected_keys, f"claims[{index}]")
        subject = _text(claim["subject"], f"claims[{index}].subject")
        kind = _text(claim["subject_kind"], f"claims[{index}].subject_kind")
        disposition = _text(claim["disposition"], f"claims[{index}].disposition")
        assertions = _exact_keys(
            claim["owner_verifier_assertions"],
            assertion_keys,
            f"claims[{index}].owner_verifier_assertions",
        )
        if subject in claims_by_subject:
            raise ProgramFoundryGepaAdjudicatorCompletionError(
                "owner completion contains duplicate subject claims"
            )
        if disposition not in _ALLOWED_CLAIM_DISPOSITIONS:
            raise ProgramFoundryGepaAdjudicatorCompletionError(
                "owner completion disposition must be promote_locally, reject_locally, require_review, or abstain"
            )
        if (
            assertions["identity_verified"] is not True
            or assertions["participation_verified"] is not True
            or assertions["disposition_attested"] is not True
            or assertions["roster_membership_verified"] is not True
            or not isinstance(assertions["subject_signature_verified"], bool)
        ):
            raise ProgramFoundryGepaAdjudicatorCompletionError(
                "owner completion must verify registered-roster membership, identity, participation, and disposition while declaring the subject-signature outcome"
            )
        claims_by_subject[subject] = {
            "subject": subject,
            "subject_kind": kind,
            "disposition": disposition,
            "owner_verifier_assertions": {
                "identity_verified": True,
                "roster_membership_verified": True,
                "participation_verified": True,
                "disposition_attested": True,
                "subject_signature_verified": assertions["subject_signature_verified"],
            },
        }
    expected_by_subject = dict(registered)
    if set(claims_by_subject) != set(expected_by_subject):
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "owner completion must contain exactly one claim for every registered subject"
        )
    if any(
        claims_by_subject[subject]["subject_kind"] != expected_kind
        for subject, expected_kind in expected_by_subject.items()
    ):
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "owner completion subject kinds do not match the selected registration"
        )
    return [claims_by_subject[subject] for subject, _kind in registered]


def _quorum_result(
    *, selected: Mapping[str, Any], claims: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    quorum = selected.get("quorum")
    if not isinstance(quorum, Mapping):
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "selected adjudicator quorum is missing"
        )
    mode = quorum.get("mode")
    required = quorum.get("required")
    eligible = quorum.get("eligible")
    if (
        mode not in {"single", "threshold", "unanimous"}
        or isinstance(required, bool)
        or not isinstance(required, int)
        or isinstance(eligible, bool)
        or not isinstance(eligible, int)
        or required < 1
        or eligible != len(claims)
    ):
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "selected adjudicator quorum contract is invalid"
        )
    decision_claims = [claim for claim in claims if claim["disposition"] != "abstain"]
    counts = Counter(str(claim["disposition"]) for claim in decision_claims)
    winners = sorted(
        disposition for disposition, count in counts.items() if count >= required
    )
    constituency_satisfied = False
    reason = "unique_quorum_disposition"
    disposition = "require_review"
    quorum_satisfied = False
    if len(winners) == 1:
        winner = winners[0]
        if mode == "unanimous" and counts[winner] != eligible:
            winners = []
        else:
            backend = selected.get("backend")
            backend_kind = backend.get("kind") if isinstance(backend, Mapping) else None
            constituency_satisfied = backend_kind != "hybrid"
            if backend_kind == "hybrid":
                winning_kinds = {
                    str(claim["subject_kind"])
                    for claim in decision_claims
                    if claim["disposition"] == winner
                }
                constituency_satisfied = winning_kinds == {"human", "agent"}
            if constituency_satisfied:
                disposition = winner
                quorum_satisfied = True
            else:
                reason = "hybrid_cross_constituency_quorum_not_satisfied"
    if len(winners) > 1:
        reason = "ambiguous_quorum_dispositions"
    elif not winners:
        reason = "no_quorum_disposition"
    return {
        "mode": mode,
        "required": required,
        "eligible": eligible,
        "participation_count": len(claims),
        "decision_count": len(decision_claims),
        "abstention_count": len(claims) - len(decision_claims),
        "disposition_counts": {key: counts[key] for key in sorted(counts)},
        "winning_dispositions": winners,
        "constituency_rule": quorum.get("constituency_rule"),
        "constituency_satisfied": constituency_satisfied,
        "quorum_satisfied": quorum_satisfied,
        "adjudication_completed": True,
        "reason": reason,
        "disposition": disposition,
    }


def validate_owner_verified_adjudicator_completion(
    payload: Mapping[str, Any],
    *,
    request: Mapping[str, Any],
    request_sha256: str,
    expected_owner_receipt_id: str,
    trust_policy: Mapping[str, Any],
    trust_policy_sha256: str,
    trusted_policy_sha256: str,
    verification_time: datetime,
) -> dict[str, Any]:
    """Verify a completion under a digest-pinned scoped policy without social-auth claims."""

    if verification_time.tzinfo is None or verification_time.utcoffset() is None:
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "verification system time must be timezone-aware"
        )
    policy = validate_adjudicator_verifier_trust_policy(
        trust_policy,
        policy_sha256=trust_policy_sha256,
        trusted_policy_sha256=trusted_policy_sha256,
        request=request,
        request_sha256=request_sha256,
        verification_time=verification_time,
    )
    item = _exact_keys(
        payload,
        {
            "schema_version",
            "owner_receipt_id",
            "issued_at",
            "verification_scope",
            "request_binding",
            "verifier_evidence",
            "claims",
            "authority_boundary",
            "signature",
        },
        "owner completion",
    )
    if item["schema_version"] != OWNER_VERIFIED_ADJUDICATOR_COMPLETION_SCHEMA:
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "unsupported owner completion schema"
        )
    if request.get("status") != "pending":
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "owner completion requires a pending selected adjudicator request"
        )
    selected = request.get("selected_adjudicator")
    if not isinstance(selected, Mapping):
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "owner completion requires a selected adjudicator"
        )
    backend = selected.get("backend")
    backend_kind = backend.get("kind") if isinstance(backend, Mapping) else None
    if backend_kind not in _EXTERNAL_COMPLETION_BACKENDS:
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "selected adjudicator does not accept owner-verified asynchronous completion"
        )
    owner_receipt_id = _text(
        item["owner_receipt_id"], "owner completion owner_receipt_id"
    )
    if owner_receipt_id != _text(
        expected_owner_receipt_id, "expected_owner_receipt_id"
    ):
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "owner completion receipt id does not match the external pin"
        )
    if item["verification_scope"] != _OWNER_COMPLETION_SCOPE:
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "owner completion verification scope is invalid"
        )
    expected_binding = expected_adjudicator_request_binding(request, request_sha256)
    binding = _exact_keys(
        item["request_binding"],
        set(expected_binding),
        "owner completion request_binding",
    )
    if binding != expected_binding:
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "owner completion does not match the current request lineage"
        )
    verifier = _exact_keys(
        item["verifier_evidence"],
        set(policy["verifier"]),
        "owner completion verifier_evidence",
    )
    if verifier != policy["verifier"]:
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "owner completion verifier declaration does not match the digest-pinned trust policy"
        )
    issued_at = _timestamp(item["issued_at"], "owner completion issued_at")
    valid_from = _timestamp(verifier["valid_from"], "verifier key valid_from")
    valid_until = _timestamp(verifier["valid_until"], "verifier key valid_until")
    if not (valid_from <= issued_at <= verification_time < valid_until):
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "owner completion or verifier key lifecycle is invalid"
        )
    authority = _exact_keys(
        item["authority_boundary"],
        {
            "identity_verification_assertion",
            "participation_verification_assertion",
            "bounded_local_disposition_authority",
            "production_promotion",
            "activation",
            "governance",
            "external_apply",
        },
        "owner completion authority_boundary",
    )
    if authority != {
        "identity_verification_assertion": True,
        "participation_verification_assertion": True,
        "bounded_local_disposition_authority": False,
        "production_promotion": False,
        "activation": False,
        "governance": False,
        "external_apply": False,
    }:
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "owner completion widens its verification authority"
        )
    claims = _validated_claims(item["claims"], selected=selected)
    signature = _exact_keys(
        item["signature"],
        {"algorithm", "key_id", "signed_payload_digest", "signature_b64"},
        "owner completion signature",
    )
    signed_payload = {key: value for key, value in item.items() if key != "signature"}
    signed_payload_bytes = canonical_completion_json(signed_payload)
    signed_payload_digest = _sha256(signed_payload_bytes)
    if (
        signature["algorithm"] != "Ed25519"
        or signature["key_id"] != verifier["key_id"]
        or signature["signed_payload_digest"] != signed_payload_digest
    ):
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "owner completion signature identity or payload digest drifted"
        )
    try:
        public_key_bytes = base64.b64decode(verifier["public_key_b64"], validate=True)
        signature_bytes = base64.b64decode(
            _text(signature["signature_b64"], "signature_b64"), validate=True
        )
    except (binascii.Error, ValueError) as exc:
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "owner completion contains invalid base64 signature material"
        ) from exc
    if len(public_key_bytes) != 32 or len(signature_bytes) != 64:
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "owner completion contains invalid Ed25519 material length"
        )
    try:
        Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(
            signature_bytes, signed_payload_bytes
        )
    except (InvalidSignature, ValueError) as exc:
        raise ProgramFoundryGepaAdjudicatorCompletionError(
            "owner completion signature is invalid"
        ) from exc
    return {
        "owner_receipt_id": owner_receipt_id,
        "issued_at": item["issued_at"],
        "signed_payload_digest": signed_payload_digest,
        "claims": claims,
        "quorum": _quorum_result(selected=selected, claims=claims),
        "verifier": verifier,
        "trust_policy": policy,
    }

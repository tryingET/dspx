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
from collections.abc import Mapping, Sequence
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


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise Layer12FixedFamilyPublicationError(f"{label} must be a positive integer")
    return value


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


def _canonical_import(value: object, label: str) -> dict[str, object]:
    item = _object(value, label)
    fields = {
        "schema_version",
        "owner",
        "family_id",
        "publication_id",
        "epoch",
        "spec_digest",
        "transition_token",
        "publication_scope",
        "authority_granted",
    }
    _closed(item, fields, label)
    result: dict[str, object] = {
        "schema_version": _text(item["schema_version"], f"{label}.schema_version"),
        "owner": _text(item["owner"], f"{label}.owner"),
        "family_id": _text(item["family_id"], f"{label}.family_id"),
        "publication_id": _text(item["publication_id"], f"{label}.publication_id"),
        "epoch": _positive_integer(item["epoch"], f"{label}.epoch"),
        "spec_digest": _digest(item["spec_digest"], f"{label}.spec_digest"),
        "transition_token": _text(
            item["transition_token"], f"{label}.transition_token"
        ),
        "publication_scope": item["publication_scope"],
        "authority_granted": item["authority_granted"],
    }
    if result["schema_version"] != "layer12-fixed-family-import-v1":
        raise Layer12FixedFamilyPublicationError(f"{label} schema drift")
    if result["publication_scope"] != OWNER_LOCAL_SCOPE:
        raise Layer12FixedFamilyPublicationError(f"{label} publication scope drift")
    if result["authority_granted"] is not False:
        raise Layer12FixedFamilyPublicationError(f"{label} authority widening")
    return result


def reconstruct_fixed_family_imports(
    *,
    prior_imports: Sequence[object],
    prior_epoch_high_watermarks: Sequence[object],
    current_import: object | None,
    current_withdrawal: object | None,
) -> dict[str, object]:
    """Reconstruct cumulative imports while retaining withdrawn epoch tombstones."""

    imports: list[dict[str, object]] = []
    coordinates: set[tuple[str, str, int]] = set()
    publication_ids: set[str] = set()
    last_epochs: dict[tuple[str, str], int] = {}
    family_contracts: dict[tuple[str, str], tuple[str, str]] = {}
    family_order: list[tuple[str, str]] = []
    family_used_publication_ids: dict[tuple[str, str], list[str]] = {}
    durable_publication_ids: set[str] = set()

    def remember_family(key: tuple[str, str]) -> None:
        if key not in family_order:
            family_order.append(key)

    def append_import(value: object, label: str, *, is_current: bool) -> None:
        item = _canonical_import(value, label)
        owner = cast(str, item["owner"])
        family_id = cast(str, item["family_id"])
        epoch = cast(int, item["epoch"])
        publication_id = cast(str, item["publication_id"])
        family_key = (owner, family_id)
        coordinate = (owner, family_id, epoch)
        family_contract = (
            cast(str, item["transition_token"]),
            cast(str, item["spec_digest"]),
        )
        previous_contract = family_contracts.get(family_key)
        if previous_contract is not None and family_contract != previous_contract:
            raise Layer12FixedFamilyPublicationError(
                f"{label} conflicts with the existing owner/family contract"
            )
        if coordinate in coordinates:
            raise Layer12FixedFamilyPublicationError(
                f"{label} duplicates or conflicts with an existing family epoch"
            )
        if publication_id in publication_ids:
            raise Layer12FixedFamilyPublicationError(
                f"{label} duplicates or conflicts with an existing publication_id"
            )
        if is_current and publication_id in durable_publication_ids:
            raise Layer12FixedFamilyPublicationError(
                f"{label} reuses a durable used or withdrawn publication_id"
            )
        previous_epoch = last_epochs.get(family_key)
        if previous_epoch is not None and epoch <= previous_epoch:
            raise Layer12FixedFamilyPublicationError(
                f"{label} is not strictly monotonic for owner/family"
            )
        if is_current:
            high_water = epoch_high_watermarks.get(family_key)
            if high_water is not None and epoch <= high_water:
                raise Layer12FixedFamilyPublicationError(
                    f"{label} reuses or regresses the owner/family epoch high-water mark"
                )
        remember_family(family_key)
        coordinates.add(coordinate)
        publication_ids.add(publication_id)
        last_epochs[family_key] = epoch
        family_contracts[family_key] = family_contract
        imports.append(item)

    for index, value in enumerate(prior_imports):
        append_import(value, f"prior_imports[{index}]", is_current=False)

    epoch_high_watermarks: dict[tuple[str, str], int] = {}
    for index, value in enumerate(prior_epoch_high_watermarks):
        label = f"prior_epoch_high_watermarks[{index}]"
        watermark = _object(value, label)
        _closed(
            watermark,
            {
                "schema_version",
                "owner",
                "family_id",
                "epoch",
                "spec_digest",
                "transition_token",
                "used_publication_ids",
            },
            label,
        )
        if (
            watermark["schema_version"]
            != "layer12-fixed-family-epoch-high-watermark-v1"
        ):
            raise Layer12FixedFamilyPublicationError(f"{label} schema drift")
        owner = _text(watermark["owner"], f"{label}.owner")
        family_id = _text(watermark["family_id"], f"{label}.family_id")
        epoch = _positive_integer(watermark["epoch"], f"{label}.epoch")
        watermark_contract = (
            _text(watermark["transition_token"], f"{label}.transition_token"),
            _digest(watermark["spec_digest"], f"{label}.spec_digest"),
        )
        raw_used_ids = watermark["used_publication_ids"]
        if not isinstance(raw_used_ids, list) or not raw_used_ids:
            raise Layer12FixedFamilyPublicationError(
                f"{label}.used_publication_ids must be a non-empty list"
            )
        used_ids = [
            _text(value, f"{label}.used_publication_ids") for value in raw_used_ids
        ]
        if len(set(used_ids)) != len(used_ids):
            raise Layer12FixedFamilyPublicationError(
                f"{label}.used_publication_ids contains duplicates"
            )
        family_key = (owner, family_id)
        if family_key in epoch_high_watermarks:
            raise Layer12FixedFamilyPublicationError(
                f"{label} duplicates or conflicts with an existing family watermark"
            )
        imported_epoch = last_epochs.get(family_key)
        imported_contract = family_contracts.get(family_key)
        if imported_contract is not None and imported_contract != watermark_contract:
            raise Layer12FixedFamilyPublicationError(
                f"{label} conflicts with imported owner/family contract"
            )
        if imported_epoch is not None and epoch < imported_epoch:
            raise Layer12FixedFamilyPublicationError(
                f"{label} regresses below imported family history"
            )
        imported_ids = {
            cast(str, item["publication_id"])
            for item in imports
            if item["owner"] == owner and item["family_id"] == family_id
        }
        if not imported_ids.issubset(set(used_ids)):
            raise Layer12FixedFamilyPublicationError(
                f"{label} omits publication ids from imported family history"
            )
        reused_ids = durable_publication_ids.intersection(used_ids)
        if reused_ids:
            raise Layer12FixedFamilyPublicationError(
                f"{label} conflicts with durable publication ids from another family"
            )
        remember_family(family_key)
        epoch_high_watermarks[family_key] = epoch
        family_contracts[family_key] = watermark_contract
        family_used_publication_ids[family_key] = used_ids
        durable_publication_ids.update(used_ids)

    missing_watermarks = set(last_epochs) - set(epoch_high_watermarks)
    if missing_watermarks:
        raise Layer12FixedFamilyPublicationError(
            "prior imports require an epoch high-water mark for every owner/family"
        )

    if current_import is not None:
        append_import(current_import, "current_import", is_current=True)
        current_item = imports[-1]
        current_key = (
            cast(str, current_item["owner"]),
            cast(str, current_item["family_id"]),
        )
        epoch_high_watermarks[current_key] = cast(int, current_item["epoch"])
        current_publication_id = cast(str, current_item["publication_id"])
        family_used_publication_ids.setdefault(current_key, []).append(
            current_publication_id
        )
        durable_publication_ids.add(current_publication_id)

    withdrawal_applied = False
    withdrawn_identity: dict[str, object] | None = None
    if current_withdrawal is not None:
        withdrawal = _object(current_withdrawal, "current_withdrawal")
        _closed(
            withdrawal,
            {
                "schema_version",
                "owner",
                "family_id",
                "publication_id",
                "epoch",
                "withdrawal_ref",
                "owner_local_only",
                "authority_granted",
            },
            "current_withdrawal",
        )
        if withdrawal["schema_version"] != "layer12-fixed-family-withdrawal-v1":
            raise Layer12FixedFamilyPublicationError("withdrawal schema drift")
        owner = _text(withdrawal["owner"], "current_withdrawal.owner")
        family_id = _text(withdrawal["family_id"], "current_withdrawal.family_id")
        publication_id = _text(
            withdrawal["publication_id"], "current_withdrawal.publication_id"
        )
        epoch = _positive_integer(withdrawal["epoch"], "current_withdrawal.epoch")
        withdrawal_ref = _text(
            withdrawal["withdrawal_ref"], "current_withdrawal.withdrawal_ref"
        )
        if withdrawal["owner_local_only"] is not True:
            raise Layer12FixedFamilyPublicationError("withdrawal scope widening")
        if withdrawal["authority_granted"] is not False:
            raise Layer12FixedFamilyPublicationError("withdrawal authority widening")
        matches = [
            (index, item)
            for index, item in enumerate(imports)
            if item["owner"] == owner
            and item["family_id"] == family_id
            and item["epoch"] == epoch
        ]
        if len(matches) != 1:
            raise Layer12FixedFamilyPublicationError(
                "withdrawal does not match exactly one imported owner/family/epoch"
            )
        index, matched = matches[0]
        if matched["publication_id"] != publication_id:
            raise Layer12FixedFamilyPublicationError(
                "withdrawal publication_id conflicts with matching family epoch"
            )
        imports.pop(index)
        withdrawal_applied = True
        withdrawn_identity = {
            "owner": owner,
            "family_id": family_id,
            "epoch": epoch,
            "publication_id": publication_id,
            "withdrawal_ref": withdrawal_ref,
        }

    watermark_output = [
        {
            "schema_version": "layer12-fixed-family-epoch-high-watermark-v1",
            "owner": owner,
            "family_id": family_id,
            "epoch": epoch_high_watermarks[(owner, family_id)],
            "transition_token": family_contracts[(owner, family_id)][0],
            "spec_digest": family_contracts[(owner, family_id)][1],
            "used_publication_ids": family_used_publication_ids[(owner, family_id)],
        }
        for owner, family_id in family_order
    ]
    return {
        "schema_version": "layer12-fixed-family-reconstruction-v1",
        "mode": "cumulative_owner_local_family_epochs",
        "imports": imports,
        "family_epoch_high_watermarks": watermark_output,
        "withdrawal_applied": withdrawal_applied,
        "withdrawn_identity": withdrawn_identity,
        "preserve_unrelated_imports": True,
        "authority_granted": False,
    }


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
            "reconstruction_contract",
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
    reconstruction = _object(
        item["reconstruction_contract"], "spec.reconstruction_contract"
    )
    _exact(
        reconstruction,
        {
            "mode": "cumulative_owner_local_family_epochs",
            "identity_key": ["owner", "family_id"],
            "epoch_order": "strictly_monotonic_per_family",
            "withdrawal_scope": "matching_owner_family_epoch_only",
            "preserve_unrelated_imports": True,
        },
        "spec.reconstruction_contract",
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
    expected_publication_id: str,
    expected_publication_epoch: int,
    expected_publication_state: str,
    expected_withdrawal_ref: str | None,
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
            "publication_lifecycle",
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
    pinned_publication_id = _text(expected_publication_id, "expected_publication_id")
    if item["publication_id"] != pinned_publication_id:
        raise Layer12FixedFamilyPublicationError(
            "publication_id does not match external pin"
        )
    published_at = _time(item["published_at"], "published_at")
    if item["publication_scope"] != OWNER_LOCAL_SCOPE:
        raise Layer12FixedFamilyPublicationError(
            "affected-use publication is forbidden"
        )

    pinned_epoch = _positive_integer(
        expected_publication_epoch, "expected_publication_epoch"
    )
    lifecycle = _object(
        item["publication_lifecycle"], "publication.publication_lifecycle"
    )
    _exact(
        lifecycle,
        {
            "epoch": pinned_epoch,
            "state_at_signing": "published",
            "withdrawal_ref_at_signing": None,
        },
        "publication.publication_lifecycle",
    )
    pinned_state = _text(expected_publication_state, "expected_publication_state")
    if pinned_state not in {"published", "withdrawn"}:
        raise Layer12FixedFamilyPublicationError(
            "unsupported external publication state"
        )
    if pinned_state == "withdrawn":
        _text(expected_withdrawal_ref, "expected_withdrawal_ref")
        raise Layer12FixedFamilyPublicationError(
            "publication is withdrawn by external lifecycle pin"
        )
    if expected_withdrawal_ref is not None:
        raise Layer12FixedFamilyPublicationError(
            "published external state cannot carry a withdrawal ref"
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
        "publication_id": pinned_publication_id,
        "publication_epoch": pinned_epoch,
        "publication_state": pinned_state,
        "owner": expected_owner,
        "family_id": expected_family_id,
        "transition_token": ONLY_TOKEN,
        "publication_scope": OWNER_LOCAL_SCOPE,
        "spec_digest": pinned_spec_digest,
        "ak_wire_trust_source": "external_pin",
        "signature_trust_source": "external_pin",
        "publication_lifecycle_source": "external_pin",
        "canonical_import": {
            "schema_version": "layer12-fixed-family-import-v1",
            "owner": expected_owner,
            "family_id": expected_family_id,
            "publication_id": pinned_publication_id,
            "epoch": pinned_epoch,
            "spec_digest": pinned_spec_digest,
            "transition_token": ONLY_TOKEN,
            "publication_scope": OWNER_LOCAL_SCOPE,
            "authority_granted": False,
        },
        "canonical_reconstruction": {
            "mode": "cumulative_owner_local_family_epochs",
            "family_identity": {
                "owner": expected_owner,
                "family_id": expected_family_id,
            },
            "epoch": pinned_epoch,
            "action": "retain_published_epoch",
            "preserve_unrelated_imports": True,
        },
        "authority_granted": False,
    }

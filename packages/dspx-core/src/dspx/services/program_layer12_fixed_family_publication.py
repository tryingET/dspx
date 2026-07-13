# summary: "Verifies the closed DSPx owner-local publication for one Layer-12 transition family."
# read_when:
#   - "Changing a fixed Layer-12 family, signed publication fixture, or external trust pin."

"""Pure verification for the DSPx-owned Layer-12 fixed-family publication.

The verifier has no AK integration and performs no publication. Caller pins are
required, while closed TEST fixtures also have DSPx-owner-fixed identity and
signer-lifecycle anchors. Those local anchors and declarations inside the artifact
never bootstrap AK trust; AK must independently pin its own trust later.
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
B0_TOKEN = "continue_current_execution_task"
B1_TOKEN = "request_owner_route"
B3_TOKEN = "inspect_status_before_proceeding"
B4_TOKEN = "open_decision"
B2_TOKENS = (
    "close_implementation_wave",
    "activate_guidance",
    "default_residual_adoption_hardening",
)
SUPPORTED_TOKENS = {B0_TOKEN, B1_TOKEN, B3_TOKEN, B4_TOKEN, *B2_TOKENS}
DSPX_OWNER = "softwareco/owned/dspx"
AK_OWNER = "softwareco/owned/agent-kernel"
B0_FAMILY_ID = "dspx.layer12.continue-current-execution-task.v1"
B1_FAMILY_ID = "dspx.layer12.request-owner-route.v1"
B3_FAMILY_ID = "dspx.layer12.inspect-status-before-proceeding.v1"
B4_FAMILY_ID = "dspx.layer12.open-decision.v1"
B2_FAMILY_IDS = {
    "close_implementation_wave": "dspx.layer12.close-implementation-wave.v1",
    "activate_guidance": "dspx.layer12.activate-guidance.v1",
    "default_residual_adoption_hardening": "dspx.layer12.default-residual-adoption-hardening.v1",
}
TOKEN_FAMILY_IDS = {
    B0_TOKEN: B0_FAMILY_ID,
    B1_TOKEN: B1_FAMILY_ID,
    B3_TOKEN: B3_FAMILY_ID,
    B4_TOKEN: B4_FAMILY_ID,
    **B2_FAMILY_IDS,
}
# Immutable DSPx-owner facts for the only imports this closed reconstruction
# contract admits. Reconstruction never accepts caller-defined families, spec
# digests, publication identities, or epochs as trust roots.
FIXED_IMPORT_FACTS: dict[str, tuple[str, str, int]] = {
    B0_TOKEN: (
        "sha256:7c4686dcdf26b085a595d1b381660a3191d650c8d26be1bb22a8adaa533142cc",
        "dspx-iw14b-continue-current-execution-task-owner-local-v1",
        1,
    ),
    B1_TOKEN: (
        "sha256:9c7fdfa7b13d13b803fecef1b57ed080a2b8462658f82b7f169521b84a4a893f",
        "dspx-iw14b-request-owner-route-owner-local-test-v1",
        1,
    ),
    "close_implementation_wave": (
        "sha256:ebd3b5f19be87179911029e552aa5bc00c4de774bd9264efd5fac397435ac06f",
        "dspx-iw14b-close-implementation-wave-owner-local-test-v1",
        1,
    ),
    "activate_guidance": (
        "sha256:e58fb94f75ccd9cbf3a63216d779e0bf45791b37f128dc0a43e741858e9fb374",
        "dspx-iw14b-activate-guidance-owner-local-test-v1",
        1,
    ),
    "default_residual_adoption_hardening": (
        "sha256:eb4f1d7634fbade45cc80fcf2c753611ea41672603dcf04d42e595fa7258f86d",
        "dspx-iw14b-default-residual-adoption-hardening-owner-local-test-v1",
        1,
    ),
    B3_TOKEN: (
        "sha256:cf7c6722cb780d7c1f8bb2c4242e77f5e2c77950d379cfb453b62fbc8c48dd30",
        "dspx-iw14b-inspect-status-before-proceeding-owner-local-test-v1",
        1,
    ),
    B4_TOKEN: (
        "sha256:0ffa7021f4cb5caaba9dc9c383ac9608a53bdc531b59dceeeb735fa354cd1922",
        "dspx-iw14b-open-decision-owner-local-test-v1",
        1,
    ),
}
FIXED_IMPORT_ORDER = (
    B0_TOKEN,
    B1_TOKEN,
    *B2_TOKENS,
    B3_TOKEN,
    B4_TOKEN,
)
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


def _fixed_import_fact(
    *, owner: str, family_id: str, transition_token: str, label: str
) -> tuple[str, str, int]:
    expected_family = TOKEN_FAMILY_IDS.get(transition_token)
    if owner != DSPX_OWNER or expected_family is None or family_id != expected_family:
        raise Layer12FixedFamilyPublicationError(
            f"{label} is outside the closed supported owner/token/family map"
        )
    return FIXED_IMPORT_FACTS[transition_token]


def _fixed_withdrawal_ref(*, family_id: str, epoch: int) -> str:
    return f"withdrawal:{DSPX_OWNER}:{family_id}:{epoch}"


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
    owner = result["owner"]
    family_id = result["family_id"]
    transition_token = result["transition_token"]
    expected_spec_digest, expected_publication_id, expected_epoch = _fixed_import_fact(
        owner=owner,
        family_id=family_id,
        transition_token=transition_token,
        label=label,
    )
    if result["spec_digest"] != expected_spec_digest:
        raise Layer12FixedFamilyPublicationError(
            f"{label}.spec_digest conflicts with immutable DSPx-owner fact"
        )
    if result["publication_id"] != expected_publication_id:
        raise Layer12FixedFamilyPublicationError(
            f"{label}.publication_id conflicts with immutable DSPx-owner fact"
        )
    if result["epoch"] != expected_epoch:
        raise Layer12FixedFamilyPublicationError(
            f"{label}.epoch conflicts with immutable DSPx-owner fact"
        )
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

    prior_import_tokens: list[str] = []
    for index, value in enumerate(prior_imports):
        append_import(value, f"prior_imports[{index}]", is_current=False)
        prior_import_tokens.append(cast(str, imports[-1]["transition_token"]))

    epoch_high_watermarks: dict[tuple[str, str], int] = {}
    watermark_tokens: list[str] = []
    watermark_family_keys: list[tuple[str, str]] = []
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
        transition_token = _text(
            watermark["transition_token"], f"{label}.transition_token"
        )
        expected_spec_digest, expected_publication_id, expected_epoch = (
            _fixed_import_fact(
                owner=owner,
                family_id=family_id,
                transition_token=transition_token,
                label=label,
            )
        )
        watermark_spec_digest = _digest(
            watermark["spec_digest"], f"{label}.spec_digest"
        )
        if watermark_spec_digest != expected_spec_digest:
            raise Layer12FixedFamilyPublicationError(
                f"{label}.spec_digest conflicts with immutable DSPx-owner fact"
            )
        if epoch != expected_epoch:
            raise Layer12FixedFamilyPublicationError(
                f"{label}.epoch conflicts with immutable DSPx-owner high-water fact"
            )
        watermark_contract = (transition_token, watermark_spec_digest)
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
        if used_ids != [expected_publication_id]:
            raise Layer12FixedFamilyPublicationError(
                f"{label}.used_publication_ids conflicts with immutable DSPx-owner history"
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
        watermark_tokens.append(transition_token)
        watermark_family_keys.append(family_key)

    candidate = (
        _canonical_import(current_import, "current_import")
        if current_import is not None
        else None
    )

    expected_watermark_tokens = list(FIXED_IMPORT_ORDER[: len(watermark_tokens)])
    if watermark_tokens != expected_watermark_tokens:
        raise Layer12FixedFamilyPublicationError(
            "prior epoch high-watermark history must be an exact ordered prefix "
            "of the sealed fixed-family history"
        )
    missing_watermarks = set(last_epochs) - set(epoch_high_watermarks)
    if missing_watermarks:
        raise Layer12FixedFamilyPublicationError(
            "prior imports require an epoch high-water mark for every owner/family"
        )
    retained_prior_tokens = set(prior_import_tokens)
    expected_prior_import_tokens = [
        token for token in watermark_tokens if token in retained_prior_tokens
    ]
    if prior_import_tokens != expected_prior_import_tokens:
        raise Layer12FixedFamilyPublicationError(
            "prior imports are not a lawful ordered sequence under the sealed "
            "fixed-family history"
        )
    family_order[:] = watermark_family_keys

    if candidate is not None:
        candidate_token = cast(str, candidate["transition_token"])
        candidate_position = FIXED_IMPORT_ORDER.index(candidate_token)
        expected_predecessor_tokens = list(FIXED_IMPORT_ORDER[:candidate_position])
        if (
            watermark_tokens != expected_predecessor_tokens
            or prior_import_tokens != expected_predecessor_tokens
        ):
            raise Layer12FixedFamilyPublicationError(
                "current_import does not follow the exact ordered sealed "
                "fixed-family predecessor history of imports"
            )
        append_import(candidate, "current_import", is_current=True)
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
        expected_withdrawal_ref = _fixed_withdrawal_ref(
            family_id=family_id, epoch=epoch
        )
        if withdrawal_ref != expected_withdrawal_ref:
            raise Layer12FixedFamilyPublicationError(
                "current_withdrawal.withdrawal_ref conflicts with exact owner/family/epoch identity"
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


REQUEST_OWNER_ROUTE_PROGRAM_ID = "dspx.generated.direction_controller.v1"
REQUEST_OWNER_ROUTE_SIGNATURES: tuple[
    tuple[str, tuple[str, ...], tuple[str, ...]], ...
] = (
    (
        "ExtractLayer12PolicyFacts",
        ("operator_intent", "direction_controller_status"),
        ("policy_facts", "non_authorizations"),
    ),
    (
        "DeriveLayer12StateVector",
        ("direction_controller_status",),
        ("state_vector", "missing_facts"),
    ),
    (
        "ProposeLayer12Transition",
        ("operator_intent", "state_vector", "legal_controls", "blocked_controls"),
        ("transition", "rationale"),
    ),
    (
        "CritiqueAuthorityDrift",
        ("proposed_transition", "non_authorizations"),
        ("authority_drift_risk", "required_repair"),
    ),
    (
        "CritiqueTheaterTraps",
        ("proposed_transition", "direction_controller_status"),
        ("theater_risk", "required_repair"),
    ),
    (
        "RepairLayer12IR",
        ("proposed_transition", "authority_drift_risk", "theater_risk"),
        ("repaired_transition", "verifier_expectation"),
    ),
)
REQUEST_OWNER_ROUTE_MISSING_PRECONDITIONS = (
    "owner_route_destination_resolved",
    "owner_route_dispatch_authorized",
)

# DSPx-owner-fixed TEST fixture anchors. Caller pins remain required inputs, but for
# B1 they cannot redefine the identity or lifecycle of this closed owner fixture.
# These anchors confer no AK trust; AK must independently pin any accepted key.
REQUEST_OWNER_ROUTE_PUBLICATION_ID = (
    "dspx-iw14b-request-owner-route-owner-local-test-v1"
)
REQUEST_OWNER_ROUTE_PUBLICATION_EPOCH = 1
REQUEST_OWNER_ROUTE_PUBLISHED_AT = "2026-07-12T00:00:00Z"
REQUEST_OWNER_ROUTE_KEY_ID = "dspx-iw14b-b1-test-fixture-key-v1"
REQUEST_OWNER_ROUTE_PUBLIC_KEY_B64 = "GRimrSyXK+wK5YcYE7ZnDM5lYWei4ccNXZtikAYqlH8="
REQUEST_OWNER_ROUTE_KEY_STATUS = "active"
REQUEST_OWNER_ROUTE_KEY_VALID_FROM = "2026-07-01T00:00:00Z"
REQUEST_OWNER_ROUTE_KEY_VALID_UNTIL = "2026-08-01T00:00:00Z"

B3_SCOPE_DIGEST = (
    "sha256:906123d6dae3a2da1e002b991f53e15103418ce4fd89d91409a748198044b4fb"
)
B3_TASK_KEY = "B3-DSPx-publication"
B3_AUTHORIZATION_EVIDENCE_ID = "4345"
B3_TASK_ID = "3869"
B3_PUBLICATION_ID = "dspx-iw14b-inspect-status-before-proceeding-owner-local-test-v1"
B3_PUBLICATION_EPOCH = 1
B3_PUBLISHED_AT = "2026-07-12T02:00:00Z"
B3_KEY_ID = "dspx-iw14b-b3-inspect-status-before-proceeding-test-key-v1"
B3_PUBLIC_KEY_B64 = "hehxCHXTRUebtBnVtshHR8gr3VB1NZu84ndlf16sk1g="
B3_PROGRAM_ID = "dspx.generated.inspect_status_before_proceeding.v1"

B4_SCOPE_DIGEST = (
    "sha256:170fc5f6509d43d65c95b4a29bbd85ec00089c38b7ba1d2c827848f25afc59bb"
)
B4_TASK_KEY = "B4-DSPx-publication"
B4_AUTHORIZATION_EVIDENCE_ID = "4429"
B4_TASK_ID = "3915"
B4_PUBLICATION_ID = "dspx-iw14b-open-decision-owner-local-test-v1"
B4_PUBLICATION_EPOCH = 1
B4_PUBLISHED_AT = "2026-07-12T03:00:00Z"
B4_KEY_ID = "dspx-iw14b-b4-open-decision-test-key-v1"
B4_PUBLIC_KEY_B64 = "3Gtaag9hUzAEq+dHb9GP0bAR9XgQlY1ZYbewrn5+Bx4="
B4_PROGRAM_ID = "dspx.generated.open_decision.v1"
B4_SUCCESSOR_AVAILABILITY: list[dict[str, str]] = [
    {"transition_token": token, "availability": "unavailable"}
    for token in (B0_TOKEN, B1_TOKEN, *B2_TOKENS, B3_TOKEN)
]

B2_SCOPE_DIGEST = (
    "sha256:8783fc9276dafc434003277b6a690b92fe466a8249a4e0e50f82071dc30b98ca"
)
B2_TASK_KEY = "B2-DSPx-publications"
B2_AUTHORIZATION_EVIDENCE_ID = "4231"
B2_TASK_ID = "3836"
B2_PUBLICATION_ANCHORS: dict[str, dict[str, object]] = {
    "close_implementation_wave": {
        "publication_id": "dspx-iw14b-close-implementation-wave-owner-local-test-v1",
        "epoch": 1,
        "published_at": "2026-07-12T01:00:00Z",
        "key_id": "dspx-iw14b-b2-close-implementation-wave-test-key-v1",
        "public_key_b64": "JIT4mN3K8+RjeDS1zFFj9Hc3Z6fIh1h1OjdB+oj4T78=",
    },
    "activate_guidance": {
        "publication_id": "dspx-iw14b-activate-guidance-owner-local-test-v1",
        "epoch": 1,
        "published_at": "2026-07-12T01:01:00Z",
        "key_id": "dspx-iw14b-b2-activate-guidance-test-key-v1",
        "public_key_b64": "qVm/c/f4VYGDQ6m5g/tR0Tvsd9KVtFHq2X9HI3l3tL4=",
    },
    "default_residual_adoption_hardening": {
        "publication_id": "dspx-iw14b-default-residual-adoption-hardening-owner-local-test-v1",
        "epoch": 1,
        "published_at": "2026-07-12T01:02:00Z",
        "key_id": "dspx-iw14b-b2-default-residual-adoption-hardening-test-key-v1",
        "public_key_b64": "niF7gGvJIPzdKUZYAMJbhF4H9FXi7kBDZnTuw6ZaS/k=",
    },
}
B2_PROGRAM_CONTRACTS: dict[str, dict[str, object]] = {
    "close_implementation_wave": {
        "name": "CloseImplementationWave",
        "program_id": "dspx.generated.close_implementation_wave.v1",
        "objective": "Produce blocked advisory evidence for closing an implementation wave.",
        "inputs": [
            "implementation_wave_status",
            "completion_evidence",
            "legal_controls",
        ],
        "outputs": ["blocked_transition", "verifier_expectation"],
        "signatures": [
            {
                "name": "AssessImplementationWave",
                "inputs": ["implementation_wave_status", "completion_evidence"],
                "outputs": ["readiness", "missing_evidence"],
            },
            {
                "name": "ProposeImplementationWaveClosure",
                "inputs": ["readiness", "missing_evidence"],
                "outputs": ["transition", "rationale"],
            },
            {
                "name": "BlockImplementationWaveClosure",
                "inputs": ["transition", "legal_controls"],
                "outputs": ["blocked_transition", "verifier_expectation"],
            },
        ],
        "edges": [
            {
                "source": "AssessImplementationWave.readiness",
                "target": "ProposeImplementationWaveClosure.readiness",
            },
            {
                "source": "AssessImplementationWave.missing_evidence",
                "target": "ProposeImplementationWaveClosure.missing_evidence",
            },
            {
                "source": "ProposeImplementationWaveClosure.transition",
                "target": "BlockImplementationWaveClosure.transition",
            },
        ],
        "missing_preconditions": [
            "implementation_wave_completion_authorized",
            "transition_execution_authorized",
        ],
    },
    "activate_guidance": {
        "name": "ActivateGuidance",
        "program_id": "dspx.generated.activate_guidance.v1",
        "objective": "Produce blocked advisory evidence for guidance activation.",
        "inputs": ["guidance_candidate", "validation_evidence", "legal_controls"],
        "outputs": ["blocked_transition", "verifier_expectation"],
        "signatures": [
            {
                "name": "AssessGuidanceCandidate",
                "inputs": ["guidance_candidate", "validation_evidence"],
                "outputs": ["activation_readiness", "missing_evidence"],
            },
            {
                "name": "ProposeGuidanceActivation",
                "inputs": ["activation_readiness", "missing_evidence"],
                "outputs": ["transition", "rationale"],
            },
            {
                "name": "BlockGuidanceActivation",
                "inputs": ["transition", "legal_controls"],
                "outputs": ["blocked_transition", "verifier_expectation"],
            },
        ],
        "edges": [
            {
                "source": "AssessGuidanceCandidate.activation_readiness",
                "target": "ProposeGuidanceActivation.activation_readiness",
            },
            {
                "source": "AssessGuidanceCandidate.missing_evidence",
                "target": "ProposeGuidanceActivation.missing_evidence",
            },
            {
                "source": "ProposeGuidanceActivation.transition",
                "target": "BlockGuidanceActivation.transition",
            },
        ],
        "missing_preconditions": [
            "guidance_activation_authorized",
            "transition_execution_authorized",
        ],
    },
    "default_residual_adoption_hardening": {
        "name": "DefaultResidualAdoptionHardening",
        "program_id": "dspx.generated.default_residual_adoption_hardening.v1",
        "objective": "Produce blocked advisory evidence for default residual-adoption hardening.",
        "inputs": ["residual_adoption_status", "hardening_evidence", "legal_controls"],
        "outputs": ["blocked_transition", "verifier_expectation"],
        "signatures": [
            {
                "name": "AssessResidualAdoption",
                "inputs": ["residual_adoption_status", "hardening_evidence"],
                "outputs": ["hardening_readiness", "missing_evidence"],
            },
            {
                "name": "ProposeResidualAdoptionHardening",
                "inputs": ["hardening_readiness", "missing_evidence"],
                "outputs": ["transition", "rationale"],
            },
            {
                "name": "BlockResidualAdoptionHardening",
                "inputs": ["transition", "legal_controls"],
                "outputs": ["blocked_transition", "verifier_expectation"],
            },
        ],
        "edges": [
            {
                "source": "AssessResidualAdoption.hardening_readiness",
                "target": "ProposeResidualAdoptionHardening.hardening_readiness",
            },
            {
                "source": "AssessResidualAdoption.missing_evidence",
                "target": "ProposeResidualAdoptionHardening.missing_evidence",
            },
            {
                "source": "ProposeResidualAdoptionHardening.transition",
                "target": "BlockResidualAdoptionHardening.transition",
            },
        ],
        "missing_preconditions": [
            "residual_adoption_hardening_authorized",
            "transition_execution_authorized",
        ],
    },
}


def _check_hash_bound(value: object, label: str) -> Mapping[str, Any]:
    item = _object(value, label)
    digest = _digest(item.get("digest"), f"{label}.digest")
    payload = {key: field for key, field in item.items() if key != "digest"}
    if sha256_digest(payload) != digest:
        raise Layer12FixedFamilyPublicationError(f"{label}.digest drift")
    return item


def _check_request_owner_route_program_evidence(
    value: object, *, expected_family_id: str
) -> None:
    evidence = _object(value, "spec.program_evidence")
    _closed(
        evidence,
        {"program_intent", "module_graph", "verification_sink", "controls_evidence"},
        "spec.program_evidence",
    )
    intent = _check_hash_bound(
        evidence["program_intent"], "spec.program_evidence.program_intent"
    )
    _exact(
        intent,
        {
            "schema_version": "program-intent-v2",
            "name": "DirectionController",
            "program_id": REQUEST_OWNER_ROUTE_PROGRAM_ID,
            "objective": "Produce advisory Layer-12 transition IR for deterministic AK verification.",
            "inputs": [
                "operator_intent",
                "direction_controller_status",
                "legal_controls",
                "blocked_controls",
            ],
            "outputs": ["repaired_transition", "verifier_expectation"],
            "family_id": expected_family_id,
            "transition_token": B1_TOKEN,
            "effects": "none",
            "digest": intent["digest"],
        },
        "spec.program_evidence.program_intent",
    )
    graph = _check_hash_bound(
        evidence["module_graph"], "spec.program_evidence.module_graph"
    )
    signatures = [
        {"name": name, "inputs": list(inputs), "outputs": list(outputs)}
        for name, inputs, outputs in REQUEST_OWNER_ROUTE_SIGNATURES
    ]
    _exact(
        graph,
        {
            "schema_version": "dspx-fixed-module-graph-v1",
            "program_id": REQUEST_OWNER_ROUTE_PROGRAM_ID,
            "signatures": signatures,
            "execution_order": [name for name, _, _ in REQUEST_OWNER_ROUTE_SIGNATURES],
            "edges": [
                {
                    "source": "DeriveLayer12StateVector.state_vector",
                    "target": "ProposeLayer12Transition.state_vector",
                },
                {
                    "source": "ExtractLayer12PolicyFacts.non_authorizations",
                    "target": "CritiqueAuthorityDrift.non_authorizations",
                },
                {
                    "source": "ProposeLayer12Transition.transition",
                    "target": "CritiqueAuthorityDrift.proposed_transition",
                },
                {
                    "source": "ProposeLayer12Transition.transition",
                    "target": "CritiqueTheaterTraps.proposed_transition",
                },
                {
                    "source": "ProposeLayer12Transition.transition",
                    "target": "RepairLayer12IR.proposed_transition",
                },
                {
                    "source": "CritiqueAuthorityDrift.authority_drift_risk",
                    "target": "RepairLayer12IR.authority_drift_risk",
                },
                {
                    "source": "CritiqueTheaterTraps.theater_risk",
                    "target": "RepairLayer12IR.theater_risk",
                },
            ],
            "entry_signature": "ExtractLayer12PolicyFacts",
            "terminal_signature": "RepairLayer12IR",
            "closed": True,
            "digest": graph["digest"],
        },
        "spec.program_evidence.module_graph",
    )
    sink = _object(
        evidence["verification_sink"], "spec.program_evidence.verification_sink"
    )
    _exact(
        sink,
        {
            "source_owner": "softwareco/owned/agent-kernel",
            "surface": "ak.direction_controller.verify",
            "expected_command": "ak direction-controller verify --repo . --proposal <saved-proposal.json> -F json",
            "declaration_is_trust_root": False,
            "apply_performed": False,
        },
        "spec.program_evidence.verification_sink",
    )
    controls = _check_hash_bound(
        evidence["controls_evidence"], "spec.program_evidence.controls_evidence"
    )
    _exact(
        controls,
        {
            "schema_version": "ak-direction-controller-controls-evidence-v1",
            "transition_token": B1_TOKEN,
            "legal": False,
            "verdict": "blocked",
            "dispatch_ready": False,
            "owner_route_sent": False,
            "missing_preconditions": list(REQUEST_OWNER_ROUTE_MISSING_PRECONDITIONS),
            "declaration_is_ak_authority": False,
            "digest": controls["digest"],
        },
        "spec.program_evidence.controls_evidence",
    )


def _check_b2_program_evidence(
    value: object, *, token: str, expected_family_id: str
) -> None:
    contract = B2_PROGRAM_CONTRACTS[token]
    evidence = _object(value, "spec.program_evidence")
    _closed(
        evidence,
        {"program_intent", "module_graph", "verification_sink", "controls_evidence"},
        "spec.program_evidence",
    )
    intent = _check_hash_bound(
        evidence["program_intent"], "spec.program_evidence.program_intent"
    )
    _exact(
        intent,
        {
            "schema_version": "program-intent-v2",
            "name": contract["name"],
            "program_id": contract["program_id"],
            "objective": contract["objective"],
            "inputs": contract["inputs"],
            "outputs": contract["outputs"],
            "family_id": expected_family_id,
            "transition_token": token,
            "effects": "none",
            "digest": intent["digest"],
        },
        "spec.program_evidence.program_intent",
    )
    graph = _check_hash_bound(
        evidence["module_graph"], "spec.program_evidence.module_graph"
    )
    signatures = cast(list[dict[str, object]], contract["signatures"])
    _exact(
        graph,
        {
            "schema_version": "dspx-fixed-module-graph-v1",
            "program_id": contract["program_id"],
            "signatures": signatures,
            "execution_order": [row["name"] for row in signatures],
            "edges": contract["edges"],
            "entry_signature": signatures[0]["name"],
            "terminal_signature": signatures[-1]["name"],
            "closed": True,
            "digest": graph["digest"],
        },
        "spec.program_evidence.module_graph",
    )
    _exact(
        _object(
            evidence["verification_sink"], "spec.program_evidence.verification_sink"
        ),
        {
            "source_owner": AK_OWNER,
            "surface": "ak.direction_controller.verify",
            "expected_command": "ak direction-controller verify --repo . --proposal <saved-proposal.json> -F json",
            "declaration_is_trust_root": False,
            "apply_performed": False,
        },
        "spec.program_evidence.verification_sink",
    )
    controls = _check_hash_bound(
        evidence["controls_evidence"], "spec.program_evidence.controls_evidence"
    )
    _exact(
        controls,
        {
            "schema_version": "ak-direction-controller-controls-evidence-v1",
            "task_key": B2_TASK_KEY,
            "transition_token": token,
            "legal": False,
            "verdict": "blocked",
            "dispatch_ready": False,
            "transition_action_performed": False,
            "missing_preconditions": contract["missing_preconditions"],
            "declaration_is_ak_authority": False,
            "digest": controls["digest"],
        },
        "spec.program_evidence.controls_evidence",
    )


def _check_b3_program_evidence(value: object, *, expected_family_id: str) -> None:
    evidence = _object(value, "spec.program_evidence")
    _closed(
        evidence,
        {"program_intent", "module_graph", "controls_evidence"},
        "spec.program_evidence",
    )
    intent = _check_hash_bound(
        evidence["program_intent"], "spec.program_evidence.program_intent"
    )
    _exact(
        intent,
        {
            "schema_version": "program-intent-v2",
            "name": "InspectStatusBeforeProceeding",
            "program_id": B3_PROGRAM_ID,
            "objective": "Inspect supplied execution state and emit read-only evidence without performing a transition.",
            "inputs": ["execution_state", "inspection_context"],
            "outputs": ["inspection_evidence", "verifier_expectation"],
            "family_id": expected_family_id,
            "transition_token": B3_TOKEN,
            "effects": "none",
            "read_only": True,
            "zero_mutation": True,
            "allowed_mutations": [],
            "digest": intent["digest"],
        },
        "spec.program_evidence.program_intent",
    )
    graph = _check_hash_bound(
        evidence["module_graph"], "spec.program_evidence.module_graph"
    )
    _exact(
        graph,
        {
            "schema_version": "dspx-fixed-module-graph-v1",
            "program_id": B3_PROGRAM_ID,
            "signatures": [
                {
                    "name": "InspectExecutionState",
                    "inputs": ["execution_state", "inspection_context"],
                    "outputs": ["observed_state", "missing_evidence"],
                },
                {
                    "name": "SealReadOnlyInspection",
                    "inputs": ["observed_state", "missing_evidence"],
                    "outputs": ["inspection_evidence", "verifier_expectation"],
                },
            ],
            "execution_order": ["InspectExecutionState", "SealReadOnlyInspection"],
            "edges": [
                {
                    "source": "InspectExecutionState.observed_state",
                    "target": "SealReadOnlyInspection.observed_state",
                },
                {
                    "source": "InspectExecutionState.missing_evidence",
                    "target": "SealReadOnlyInspection.missing_evidence",
                },
            ],
            "entry_signature": "InspectExecutionState",
            "terminal_signature": "SealReadOnlyInspection",
            "closed": True,
            "effects": "none",
            "read_only": True,
            "zero_mutation": True,
            "allowed_mutations": [],
            "digest": graph["digest"],
        },
        "spec.program_evidence.module_graph",
    )
    controls = _check_hash_bound(
        evidence["controls_evidence"], "spec.program_evidence.controls_evidence"
    )
    _exact(
        controls,
        {
            "schema_version": "dspx-read-only-controls-evidence-v1",
            "task_key": B3_TASK_KEY,
            "transition_token": B3_TOKEN,
            "effects": "none",
            "read_only": True,
            "zero_mutation": True,
            "allowed_mutations": [],
            "transition_action_performed": False,
            "generated_program_dispatch_ready": False,
            "declaration_is_ak_authority": False,
            "digest": controls["digest"],
        },
        "spec.program_evidence.controls_evidence",
    )


def _check_b4_program_evidence(value: object, *, expected_family_id: str) -> None:
    evidence = _object(value, "spec.program_evidence")
    _closed(
        evidence,
        {"program_intent", "module_graph", "controls_evidence"},
        "spec.program_evidence",
    )
    intent = _check_hash_bound(
        evidence["program_intent"], "spec.program_evidence.program_intent"
    )
    _exact(
        intent,
        {
            "schema_version": "program-intent-v2",
            "name": "OpenDecision",
            "program_id": B4_PROGRAM_ID,
            "objective": "Emit blocked owner-local evidence when an explicit current decision authorization is unavailable.",
            "inputs": ["decision_state", "decision_authorization_evidence"],
            "outputs": [
                "decision_evidence",
                "successor_availability",
                "verifier_expectation",
            ],
            "family_id": expected_family_id,
            "transition_token": B4_TOKEN,
            "effects": "none",
            "read_only": True,
            "zero_mutation": True,
            "allowed_mutations": [],
            "digest": intent["digest"],
        },
        "spec.program_evidence.program_intent",
    )
    graph = _check_hash_bound(
        evidence["module_graph"], "spec.program_evidence.module_graph"
    )
    _exact(
        graph,
        {
            "schema_version": "dspx-fixed-module-graph-v1",
            "program_id": B4_PROGRAM_ID,
            "signatures": [
                {
                    "name": "InspectDecisionAuthorization",
                    "inputs": [
                        "decision_state",
                        "decision_authorization_evidence",
                    ],
                    "outputs": [
                        "observed_decision_currentness",
                        "explicit_authorization_available",
                    ],
                },
                {
                    "name": "SealUnavailableDecisionSuccessors",
                    "inputs": [
                        "observed_decision_currentness",
                        "explicit_authorization_available",
                    ],
                    "outputs": [
                        "decision_evidence",
                        "successor_availability",
                        "verifier_expectation",
                    ],
                },
            ],
            "execution_order": [
                "InspectDecisionAuthorization",
                "SealUnavailableDecisionSuccessors",
            ],
            "edges": [
                {
                    "source": "InspectDecisionAuthorization.observed_decision_currentness",
                    "target": "SealUnavailableDecisionSuccessors.observed_decision_currentness",
                },
                {
                    "source": "InspectDecisionAuthorization.explicit_authorization_available",
                    "target": "SealUnavailableDecisionSuccessors.explicit_authorization_available",
                },
            ],
            "entry_signature": "InspectDecisionAuthorization",
            "terminal_signature": "SealUnavailableDecisionSuccessors",
            "closed": True,
            "effects": "none",
            "read_only": True,
            "zero_mutation": True,
            "allowed_mutations": [],
            "digest": graph["digest"],
        },
        "spec.program_evidence.module_graph",
    )
    controls = _check_hash_bound(
        evidence["controls_evidence"], "spec.program_evidence.controls_evidence"
    )
    _exact(
        controls,
        {
            "schema_version": "dspx-open-decision-controls-evidence-v1",
            "task_key": B4_TASK_KEY,
            "transition_token": B4_TOKEN,
            "effects": "none",
            "read_only": True,
            "zero_mutation": True,
            "allowed_mutations": [],
            "decision_currentness": "required_not_available",
            "explicit_decision_authorization_available": False,
            "open_decision_performed": False,
            "decision_mutation_performed": False,
            "other_mutation_performed": False,
            "successor_availability": B4_SUCCESSOR_AVAILABILITY,
            "all_successors_unavailable": True,
            "generated_program_dispatch_ready": False,
            "declaration_is_ak_authority": False,
            "digest": controls["digest"],
        },
        "spec.program_evidence.controls_evidence",
    )


def check_fixed_family_spec(
    spec: object,
    *,
    expected_owner: str,
    expected_family_id: str,
    expected_scope_digest: str,
    expected_transition_token: str,
    expected_ak_wire_source_owner: str,
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
            *({"program_evidence"} if "program_evidence" in item else set()),
            *(
                {"authorization_evidence"}
                if "authorization_evidence" in item
                else set()
            ),
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
    pinned_token = _text(expected_transition_token, "expected_transition_token")
    if pinned_token not in SUPPORTED_TOKENS:
        raise Layer12FixedFamilyPublicationError(
            "unsupported exact transition-token pin"
        )
    if item["transition_tokens"] != [pinned_token]:
        raise Layer12FixedFamilyPublicationError(
            "spec must contain exactly the one caller-pinned allowed token"
        )
    if _text(expected_owner, "expected_owner") != DSPX_OWNER:
        raise Layer12FixedFamilyPublicationError("unsupported external owner pin")
    expected_family_for_token = TOKEN_FAMILY_IDS[pinned_token]
    if _text(expected_family_id, "expected_family_id") != expected_family_for_token:
        raise Layer12FixedFamilyPublicationError("unsupported external family pin")
    if (
        _text(expected_ak_wire_source_owner, "expected_ak_wire_source_owner")
        != AK_OWNER
    ):
        raise Layer12FixedFamilyPublicationError(
            "unsupported external source_owner pin"
        )
    if _digest(item["scope_digest"], "scope_digest") != _digest(
        expected_scope_digest, "expected_scope_digest"
    ):
        raise Layer12FixedFamilyPublicationError("spec scope digest drift")

    wire = _object(item["ak_wire_evidence"], "spec.ak_wire_evidence")
    _exact(
        wire,
        {
            "source_owner": _text(
                expected_ak_wire_source_owner, "expected_ak_wire_source_owner"
            ),
            "wire_identity": _text(
                expected_ak_wire_identity, "expected_ak_wire_identity"
            ),
            "wire_digest": _digest(expected_ak_wire_digest, "expected_ak_wire_digest"),
            "declaration_is_trust_root": False,
        },
        "spec.ak_wire_evidence",
    )
    if pinned_token == B0_TOKEN:
        if "program_evidence" in item or "authorization_evidence" in item:
            raise Layer12FixedFamilyPublicationError("B0 program evidence drift")
    elif pinned_token == B1_TOKEN:
        if "authorization_evidence" in item:
            raise Layer12FixedFamilyPublicationError("B1 authorization evidence drift")
        _check_request_owner_route_program_evidence(
            item.get("program_evidence"), expected_family_id=expected_family_id
        )
    elif pinned_token == B3_TOKEN:
        if _digest(expected_scope_digest, "expected_scope_digest") != B3_SCOPE_DIGEST:
            raise Layer12FixedFamilyPublicationError("B3 authorization scope drift")
        authorization = _object(
            item.get("authorization_evidence"), "spec.authorization_evidence"
        )
        _exact(
            authorization,
            {
                "task_key": B3_TASK_KEY,
                "authorization_evidence_id": B3_AUTHORIZATION_EVIDENCE_ID,
                "task_id": B3_TASK_ID,
                "scope_digest": B3_SCOPE_DIGEST,
                "declaration_is_ak_authority": False,
                "transition_authorized": False,
            },
            "spec.authorization_evidence",
        )
        _check_b3_program_evidence(
            item.get("program_evidence"), expected_family_id=expected_family_id
        )
    elif pinned_token == B4_TOKEN:
        if _digest(expected_scope_digest, "expected_scope_digest") != B4_SCOPE_DIGEST:
            raise Layer12FixedFamilyPublicationError("B4 authorization scope drift")
        authorization = _object(
            item.get("authorization_evidence"), "spec.authorization_evidence"
        )
        _exact(
            authorization,
            {
                "task_key": B4_TASK_KEY,
                "authorization_evidence_id": B4_AUTHORIZATION_EVIDENCE_ID,
                "task_id": B4_TASK_ID,
                "scope_digest": B4_SCOPE_DIGEST,
                "declaration_is_ak_authority": False,
                "transition_authorized": False,
            },
            "spec.authorization_evidence",
        )
        _check_b4_program_evidence(
            item.get("program_evidence"), expected_family_id=expected_family_id
        )
    elif pinned_token in B2_TOKENS:
        if _digest(expected_scope_digest, "expected_scope_digest") != B2_SCOPE_DIGEST:
            raise Layer12FixedFamilyPublicationError("B2 authorization scope drift")
        authorization = _object(
            item.get("authorization_evidence"), "spec.authorization_evidence"
        )
        _exact(
            authorization,
            {
                "task_key": B2_TASK_KEY,
                "authorization_evidence_id": B2_AUTHORIZATION_EVIDENCE_ID,
                "task_id": B2_TASK_ID,
                "scope_digest": B2_SCOPE_DIGEST,
                "declaration_is_ak_authority": False,
                "transition_authorized": False,
            },
            "spec.authorization_evidence",
        )
        _check_b2_program_evidence(
            item.get("program_evidence"),
            token=pinned_token,
            expected_family_id=expected_family_id,
        )
    else:
        raise Layer12FixedFamilyPublicationError(
            "unsupported exact transition-token pin"
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
        "transition_token": pinned_token,
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
    expected_transition_token: str,
    expected_ak_wire_source_owner: str,
    expected_ak_wire_identity: str,
    expected_ak_wire_digest: str,
    expected_publication_id: str,
    expected_publication_epoch: int,
    expected_published_at: str | None = None,
    expected_publication_state: str,
    expected_withdrawal_ref: str | None,
    expected_key_id: str,
    trusted_public_key_b64: str,
    expected_key_status: str,
    expected_key_valid_from: str,
    expected_key_valid_until: str,
    verification_time: str,
) -> dict[str, object]:
    """Verify a publication against caller pins and closed owner fixture anchors."""

    if expected_transition_token in {B1_TOKEN, B3_TOKEN, B4_TOKEN, *B2_TOKENS}:
        if expected_transition_token == B1_TOKEN:
            owner_anchor = {
                "publication_id": REQUEST_OWNER_ROUTE_PUBLICATION_ID,
                "epoch": REQUEST_OWNER_ROUTE_PUBLICATION_EPOCH,
                "published_at": REQUEST_OWNER_ROUTE_PUBLISHED_AT,
                "key_id": REQUEST_OWNER_ROUTE_KEY_ID,
                "public_key_b64": REQUEST_OWNER_ROUTE_PUBLIC_KEY_B64,
            }
        elif expected_transition_token == B3_TOKEN:
            owner_anchor = {
                "publication_id": B3_PUBLICATION_ID,
                "epoch": B3_PUBLICATION_EPOCH,
                "published_at": B3_PUBLISHED_AT,
                "key_id": B3_KEY_ID,
                "public_key_b64": B3_PUBLIC_KEY_B64,
            }
        elif expected_transition_token == B4_TOKEN:
            owner_anchor = {
                "publication_id": B4_PUBLICATION_ID,
                "epoch": B4_PUBLICATION_EPOCH,
                "published_at": B4_PUBLISHED_AT,
                "key_id": B4_KEY_ID,
                "public_key_b64": B4_PUBLIC_KEY_B64,
            }
        elif expected_transition_token in B2_TOKENS:
            owner_anchor = B2_PUBLICATION_ANCHORS[expected_transition_token]
        else:
            raise Layer12FixedFamilyPublicationError(
                "unsupported owner-fixed fixture token"
            )
        owner_pins: tuple[tuple[object, object, str], ...] = (
            (
                expected_publication_id,
                owner_anchor["publication_id"],
                "publication_id",
            ),
            (
                expected_publication_epoch,
                owner_anchor["epoch"],
                "publication_epoch",
            ),
            (
                expected_published_at,
                owner_anchor["published_at"],
                "published_at",
            ),
            (expected_key_id, owner_anchor["key_id"], "key_id"),
            (
                trusted_public_key_b64,
                owner_anchor["public_key_b64"],
                "public_key_b64",
            ),
            (expected_key_status, REQUEST_OWNER_ROUTE_KEY_STATUS, "key_status"),
            (expected_key_valid_from, REQUEST_OWNER_ROUTE_KEY_VALID_FROM, "valid_from"),
            (
                expected_key_valid_until,
                REQUEST_OWNER_ROUTE_KEY_VALID_UNTIL,
                "valid_until",
            ),
        )
        for supplied, owner_fixed, label in owner_pins:
            if supplied != owner_fixed:
                raise Layer12FixedFamilyPublicationError(
                    f"{expected_transition_token} {label} conflicts with DSPx-owner-fixed TEST fixture"
                )

    spec_result = check_fixed_family_spec(
        spec,
        expected_owner=expected_owner,
        expected_family_id=expected_family_id,
        expected_scope_digest=expected_scope_digest,
        expected_transition_token=expected_transition_token,
        expected_ak_wire_source_owner=expected_ak_wire_source_owner,
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
    if expected_transition_token in {B1_TOKEN, B3_TOKEN, B4_TOKEN, *B2_TOKENS}:
        pinned_published_at = _text(expected_published_at, "expected_published_at")
        if item["published_at"] != pinned_published_at:
            raise Layer12FixedFamilyPublicationError(
                "published_at does not match external pin"
            )
        published_at = _time(pinned_published_at, "expected_published_at")
    else:
        # Preserve B0's artifact-time behavior; the later closed TEST fixtures
        # carry owner-fixed published_at lifecycle anchors.
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
            "transition_token": expected_transition_token,
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
            "source_owner": _text(
                expected_ak_wire_source_owner, "expected_ak_wire_source_owner"
            ),
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
        "transition_token": expected_transition_token,
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
            "transition_token": expected_transition_token,
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

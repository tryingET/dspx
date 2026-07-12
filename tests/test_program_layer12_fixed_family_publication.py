# summary: "Tests the closed one-token Layer-12 owner-local publication against trust and authority drift."
# read_when:
#   - "Changing the IW14b fixed-family spec, signed fixture, verifier pins, or authority flags."

from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, NotRequired, TypedDict, cast

import jsonschema
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from dspx.services.program_layer12_fixed_family_publication import (
    Layer12FixedFamilyPublicationError,
    canonical_json,
    check_fixed_family_publication,
    check_fixed_family_spec,
    reconstruct_fixed_family_imports,
    sha256_digest,
)

SPEC_PATH = Path(
    "docs/project/layer12/continue-current-execution-task-publication.v1.json"
)
PUBLICATION_PATH = Path(
    "docs/project/layer12/fixtures/iw14b-continue-current-execution-task-publication.v1.json"
)
SCHEMA_PATH = Path(
    "docs/project/layer12/layer12-fixed-family-publication.v1.schema.json"
)
OWNER = "softwareco/owned/dspx"
FAMILY_ID = "dspx.layer12.continue-current-execution-task.v1"
SCOPE_DIGEST = "sha256:46e7861e08304ee1fa2ececa5ab460137dcf3fd2eae40f7055b8252b7fa04393"
SPEC_DIGEST = "sha256:7c4686dcdf26b085a595d1b381660a3191d650c8d26be1bb22a8adaa533142cc"
PUBLICATION_ID = "dspx-iw14b-continue-current-execution-task-owner-local-v1"
AK_WIRE_IDENTITY = "ak.direction-controller.transition-token.v1"
AK_WIRE_DIGEST = (
    "sha256:b452d674c7439df87e41c5d84e91906a2586fa50b426513f49e5b405aec8a4f7"
)
KEY_ID = "dspx-iw14b-test-fixture-key-v1"
KEY_VALID_FROM = "2026-07-01T00:00:00Z"
KEY_VALID_UNTIL = "2026-08-01T00:00:00Z"
VERIFY_AT = "2026-07-12T12:00:00Z"
_TEST_SEED = hashlib.sha256(
    b"DSPx IW14b deterministic Ed25519 TEST FIXTURE ONLY v1"
).digest()
_TEST_PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(_TEST_SEED)
PUBLIC_KEY_B64 = base64.b64encode(
    _TEST_PRIVATE_KEY.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
).decode()


class PublicationKwargs(TypedDict):
    spec: object
    expected_owner: str
    expected_family_id: str
    expected_spec_digest: str
    expected_scope_digest: str
    expected_transition_token: str
    expected_ak_wire_source_owner: str
    expected_ak_wire_identity: str
    expected_ak_wire_digest: str
    expected_publication_id: str
    expected_publication_epoch: int
    expected_published_at: NotRequired[str]
    expected_publication_state: str
    expected_withdrawal_ref: str | None
    expected_key_id: str
    trusted_public_key_b64: str
    expected_key_status: str
    expected_key_valid_from: str
    expected_key_valid_until: str
    verification_time: str


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _kwargs(
    *,
    expected_key_status: str = "active",
    expected_key_valid_from: str = KEY_VALID_FROM,
    expected_key_valid_until: str = KEY_VALID_UNTIL,
    verification_time: str = VERIFY_AT,
    expected_publication_epoch: int = 1,
    expected_publication_state: str = "published",
    expected_withdrawal_ref: str | None = None,
) -> PublicationKwargs:
    return {
        "spec": _load(SPEC_PATH),
        "expected_owner": OWNER,
        "expected_family_id": FAMILY_ID,
        "expected_spec_digest": SPEC_DIGEST,
        "expected_scope_digest": SCOPE_DIGEST,
        "expected_transition_token": "continue_current_execution_task",
        "expected_ak_wire_source_owner": "softwareco/owned/agent-kernel",
        "expected_ak_wire_identity": AK_WIRE_IDENTITY,
        "expected_ak_wire_digest": AK_WIRE_DIGEST,
        "expected_publication_id": PUBLICATION_ID,
        "expected_publication_epoch": expected_publication_epoch,
        "expected_publication_state": expected_publication_state,
        "expected_withdrawal_ref": expected_withdrawal_ref,
        "expected_key_id": KEY_ID,
        "trusted_public_key_b64": PUBLIC_KEY_B64,
        "expected_key_status": expected_key_status,
        "expected_key_valid_from": expected_key_valid_from,
        "expected_key_valid_until": expected_key_valid_until,
        "verification_time": verification_time,
    }


def _resign(publication: dict[str, Any]) -> None:
    payload = {key: value for key, value in publication.items() if key != "signature"}
    publication["signature"].update(
        {
            "algorithm": "Ed25519",
            "key_id": KEY_ID,
            "signed_payload_digest": sha256_digest(payload),
            "signature_b64": base64.b64encode(
                _TEST_PRIVATE_KEY.sign(canonical_json(payload).encode())
            ).decode(),
        }
    )


def test_fixed_spec_and_publication_match_schema_and_external_pins() -> None:
    schema = _load(SCHEMA_PATH)
    spec = _load(SPEC_PATH)
    publication = _load(PUBLICATION_PATH)
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    )
    validator.validate(spec)
    validator.validate(publication)
    assert sha256_digest(spec) == SPEC_DIGEST
    assert PUBLIC_KEY_B64 == "x8BIz2mmuVjbSeeU27JtrWir71qLC9Q3a6vkUghjMgo="

    result = check_fixed_family_publication(publication, **_kwargs())

    assert result == {
        "verified": True,
        "publication_id": PUBLICATION_ID,
        "publication_epoch": 1,
        "publication_state": "published",
        "owner": OWNER,
        "family_id": FAMILY_ID,
        "transition_token": "continue_current_execution_task",
        "publication_scope": "owner_local_artifact_only",
        "spec_digest": SPEC_DIGEST,
        "ak_wire_trust_source": "external_pin",
        "signature_trust_source": "external_pin",
        "publication_lifecycle_source": "external_pin",
        "canonical_import": {
            "schema_version": "layer12-fixed-family-import-v1",
            "owner": OWNER,
            "family_id": FAMILY_ID,
            "publication_id": PUBLICATION_ID,
            "epoch": 1,
            "spec_digest": SPEC_DIGEST,
            "transition_token": "continue_current_execution_task",
            "publication_scope": "owner_local_artifact_only",
            "authority_granted": False,
        },
        "canonical_reconstruction": {
            "mode": "cumulative_owner_local_family_epochs",
            "family_identity": {"owner": OWNER, "family_id": FAMILY_ID},
            "epoch": 1,
            "action": "retain_published_epoch",
            "preserve_unrelated_imports": True,
        },
        "authority_granted": False,
    }


@pytest.mark.parametrize(
    "tokens",
    [
        [],
        ["request_owner_route"],
        ["continue_current_execution_task", "request_owner_route"],
        "continue_current_execution_task",
    ],
)
def test_spec_rejects_every_non_closed_token_family(tokens: object) -> None:
    spec = _load(SPEC_PATH)
    spec["transition_tokens"] = tokens
    kwargs = _kwargs()
    with pytest.raises(Layer12FixedFamilyPublicationError, match="exactly the one"):
        check_fixed_family_spec(
            spec,
            expected_owner=OWNER,
            expected_family_id=FAMILY_ID,
            expected_scope_digest=SCOPE_DIGEST,
            expected_transition_token="continue_current_execution_task",
            expected_ak_wire_source_owner="softwareco/owned/agent-kernel",
            expected_ak_wire_identity=AK_WIRE_IDENTITY,
            expected_ak_wire_digest=AK_WIRE_DIGEST,
        )
    assert kwargs["expected_owner"] == OWNER


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("identity", "owner"), "attacker/repo", "owner"),
        (("identity", "family_id"), "family:other", "family"),
        (("identity", "protocol_version"), "layer12-v2", "protocol"),
        (("identity", "transition_token"), "request_owner_route", "transition_token"),
        (("identity", "spec_digest"), "sha256:" + "0" * 64, "spec_digest"),
        (("identity", "scope_digest"), "sha256:" + "0" * 64, "scope_digest"),
        (("ak_wire_evidence", "wire_identity"), "ak.wire.other", "wire_identity"),
        (("ak_wire_evidence", "wire_digest"), "sha256:" + "0" * 64, "wire_digest"),
        (("signer_evidence", "key_id"), "attacker-key", "key_id"),
    ],
)
def test_publication_rejects_identity_and_digest_drift(
    path: tuple[str, str], value: object, message: str
) -> None:
    publication = _load(PUBLICATION_PATH)
    publication[path[0]][path[1]] = value
    _resign(publication)
    with pytest.raises(Layer12FixedFamilyPublicationError, match=message):
        check_fixed_family_publication(publication, **_kwargs())


@pytest.mark.parametrize(
    ("container", "field"),
    [
        ((), "embedded_trust_root"),
        (("publication_lifecycle",), "global_replace"),
        (("identity",), "recommendation"),
        (("ak_wire_evidence",), "trusted"),
        (("signer_evidence",), "self_authorized"),
        (("authority_boundary",), "publication_authorized"),
        (("signature",), "certificate_chain"),
    ],
)
def test_unknown_fields_fail_closed(container: tuple[str, ...], field: str) -> None:
    publication = _load(PUBLICATION_PATH)
    target: dict[str, Any] = publication
    for part in container:
        target = target[part]
    target[field] = True
    _resign(publication)
    with pytest.raises(Layer12FixedFamilyPublicationError, match="fields mismatch"):
        check_fixed_family_publication(publication, **_kwargs())


@pytest.mark.parametrize(
    ("container", "field"),
    [
        ((), "publication_id"),
        (("publication_lifecycle",), "epoch"),
        (("identity",), "owner"),
        (("ak_wire_evidence",), "source_owner"),
        (("signer_evidence",), "algorithm"),
        (("authority_boundary",), "apply"),
        (("signature",), "algorithm"),
    ],
)
def test_missing_fields_fail_closed_at_each_publication_boundary(
    container: tuple[str, ...], field: str
) -> None:
    publication = _load(PUBLICATION_PATH)
    target: dict[str, Any] = publication
    for part in container:
        target = target[part]
    del target[field]
    with pytest.raises(Layer12FixedFamilyPublicationError, match="fields mismatch"):
        check_fixed_family_publication(publication, **_kwargs())


@pytest.mark.parametrize(
    ("container", "field"),
    [
        ((), "owner"),
        (("ak_wire_evidence",), "wire_identity"),
        (("publication_contract",), "external_trust_required"),
        (("reconstruction_contract",), "preserve_unrelated_imports"),
        (("authority_boundary",), "activation"),
    ],
)
def test_spec_is_closed_at_each_object_boundary(
    container: tuple[str, ...], field: str
) -> None:
    spec = _load(SPEC_PATH)
    target: dict[str, Any] = spec
    for part in container:
        target = target[part]
    target[f"unknown_{field}"] = True
    with pytest.raises(Layer12FixedFamilyPublicationError, match="fields mismatch"):
        check_fixed_family_spec(
            spec,
            expected_owner=OWNER,
            expected_family_id=FAMILY_ID,
            expected_scope_digest=SCOPE_DIGEST,
            expected_transition_token="continue_current_execution_task",
            expected_ak_wire_source_owner="softwareco/owned/agent-kernel",
            expected_ak_wire_identity=AK_WIRE_IDENTITY,
            expected_ak_wire_digest=AK_WIRE_DIGEST,
        )


@pytest.mark.parametrize(
    "field",
    [
        "affected_use_publication",
        "ak_legality",
        "policy_selection",
        "apply",
        "promotion",
        "activation",
        "dogfood",
        "rollout",
    ],
)
def test_resigned_authority_widening_flags_are_rejected(field: str) -> None:
    publication = _load(PUBLICATION_PATH)
    publication["authority_boundary"][field] = True
    _resign(publication)
    with pytest.raises(Layer12FixedFamilyPublicationError, match=field):
        check_fixed_family_publication(publication, **_kwargs())


def test_spec_authority_widening_is_rejected() -> None:
    spec = _load(SPEC_PATH)
    spec["authority_boundary"]["affected_use_publication"] = True
    with pytest.raises(
        Layer12FixedFamilyPublicationError, match="affected_use_publication"
    ):
        check_fixed_family_spec(
            spec,
            expected_owner=OWNER,
            expected_family_id=FAMILY_ID,
            expected_scope_digest=SCOPE_DIGEST,
            expected_transition_token="continue_current_execution_task",
            expected_ak_wire_source_owner="softwareco/owned/agent-kernel",
            expected_ak_wire_identity=AK_WIRE_IDENTITY,
            expected_ak_wire_digest=AK_WIRE_DIGEST,
        )


def test_embedded_key_and_wire_declarations_cannot_self_authorize() -> None:
    publication = _load(PUBLICATION_PATH)
    publication["signer_evidence"]["declaration_is_trust_root"] = True
    publication["ak_wire_evidence"]["declaration_is_trust_root"] = True
    _resign(publication)
    with pytest.raises(Layer12FixedFamilyPublicationError, match="trust_root"):
        check_fixed_family_publication(publication, **_kwargs())

    attacker = Ed25519PrivateKey.from_private_bytes(b"A" * 32)
    attacker_public = base64.b64encode(
        attacker.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    ).decode()
    publication = _load(PUBLICATION_PATH)
    publication["signer_evidence"]["public_key_b64"] = attacker_public
    payload = {key: value for key, value in publication.items() if key != "signature"}
    publication["signature"]["signed_payload_digest"] = sha256_digest(payload)
    publication["signature"]["signature_b64"] = base64.b64encode(
        attacker.sign(canonical_json(payload).encode())
    ).decode()
    with pytest.raises(Layer12FixedFamilyPublicationError, match="public_key_b64"):
        check_fixed_family_publication(publication, **_kwargs())


@pytest.mark.parametrize(
    ("status", "valid_from", "valid_until", "verification_time", "message"),
    [
        ("revoked", KEY_VALID_FROM, KEY_VALID_UNTIL, VERIFY_AT, "key_status"),
        ("active", "2026-07-02T00:00:00Z", KEY_VALID_UNTIL, VERIFY_AT, "valid_from"),
        ("active", KEY_VALID_FROM, "2026-07-31T00:00:00Z", VERIFY_AT, "valid_until"),
        (
            "active",
            KEY_VALID_FROM,
            KEY_VALID_UNTIL,
            "2026-08-01T00:00:00Z",
            "lifecycle",
        ),
        (
            "active",
            KEY_VALID_FROM,
            KEY_VALID_UNTIL,
            "2026-07-11T00:00:00Z",
            "lifecycle",
        ),
    ],
)
def test_key_lifecycle_is_independently_pinned_and_time_bounded(
    status: str,
    valid_from: str,
    valid_until: str,
    verification_time: str,
    message: str,
) -> None:
    kwargs = _kwargs(
        expected_key_status=status,
        expected_key_valid_from=valid_from,
        expected_key_valid_until=valid_until,
        verification_time=verification_time,
    )
    with pytest.raises(Layer12FixedFamilyPublicationError, match=message):
        check_fixed_family_publication(_load(PUBLICATION_PATH), **kwargs)


def test_resigned_publication_id_drift_rejects_external_identity_pin() -> None:
    publication = _load(PUBLICATION_PATH)
    publication["publication_id"] = "attacker-chosen-but-validly-signed-id"
    _resign(publication)
    with pytest.raises(Layer12FixedFamilyPublicationError, match="publication_id"):
        check_fixed_family_publication(publication, **_kwargs())


def test_publication_epoch_is_externally_pinned() -> None:
    publication = _load(PUBLICATION_PATH)
    publication["publication_lifecycle"]["epoch"] = 2
    _resign(publication)
    with pytest.raises(Layer12FixedFamilyPublicationError, match="epoch"):
        check_fixed_family_publication(publication, **_kwargs())


def test_external_withdrawal_rejects_publication_without_revoking_shared_key() -> None:
    kwargs = _kwargs(
        expected_publication_state="withdrawn",
        expected_withdrawal_ref="dspx-owner-local-withdrawal:epoch-1",
    )
    assert kwargs["expected_key_status"] == "active"
    with pytest.raises(Layer12FixedFamilyPublicationError, match="withdrawn"):
        check_fixed_family_publication(_load(PUBLICATION_PATH), **kwargs)
    with pytest.raises(
        Layer12FixedFamilyPublicationError, match="expected_withdrawal_ref"
    ):
        check_fixed_family_publication(
            _load(PUBLICATION_PATH),
            **_kwargs(expected_publication_state="withdrawn"),
        )


def test_published_state_rejects_withdrawal_ref_and_preserves_cumulative_imports() -> (
    None
):
    with pytest.raises(Layer12FixedFamilyPublicationError, match="withdrawal ref"):
        check_fixed_family_publication(
            _load(PUBLICATION_PATH),
            **_kwargs(expected_withdrawal_ref="unexpected-withdrawal"),
        )
    result = check_fixed_family_publication(_load(PUBLICATION_PATH), **_kwargs())
    reconstruction = cast(dict[str, object], result["canonical_reconstruction"])
    assert reconstruction["mode"] == "cumulative_owner_local_family_epochs"
    assert reconstruction["family_identity"] == {
        "owner": OWNER,
        "family_id": FAMILY_ID,
    }
    assert reconstruction["preserve_unrelated_imports"] is True


def test_signature_payload_and_external_trust_drift_fail_closed() -> None:
    publication = _load(PUBLICATION_PATH)
    publication["published_at"] = "2026-07-12T00:00:01Z"
    with pytest.raises(Layer12FixedFamilyPublicationError, match="payload digest"):
        check_fixed_family_publication(publication, **_kwargs())

    publication = _load(PUBLICATION_PATH)
    publication["signature"]["signature_b64"] = base64.b64encode(b"0" * 64).decode()
    with pytest.raises(
        Layer12FixedFamilyPublicationError, match="invalid publication signature"
    ):
        check_fixed_family_publication(publication, **_kwargs())

    kwargs = _kwargs()
    kwargs["trusted_public_key_b64"] = base64.b64encode(b"1" * 32).decode()
    with pytest.raises(Layer12FixedFamilyPublicationError, match="public_key_b64"):
        check_fixed_family_publication(_load(PUBLICATION_PATH), **kwargs)


def test_spec_external_wire_and_scope_pins_cannot_be_inferred_from_artifact() -> None:
    spec = _load(SPEC_PATH)
    with pytest.raises(Layer12FixedFamilyPublicationError, match="wire_identity"):
        check_fixed_family_spec(
            spec,
            expected_owner=OWNER,
            expected_family_id=FAMILY_ID,
            expected_scope_digest=SCOPE_DIGEST,
            expected_transition_token="continue_current_execution_task",
            expected_ak_wire_source_owner="softwareco/owned/agent-kernel",
            expected_ak_wire_identity="artifact-chosen-wire",
            expected_ak_wire_digest=AK_WIRE_DIGEST,
        )
    with pytest.raises(Layer12FixedFamilyPublicationError, match="scope digest"):
        check_fixed_family_spec(
            spec,
            expected_owner=OWNER,
            expected_family_id=FAMILY_ID,
            expected_scope_digest="sha256:" + "f" * 64,
            expected_transition_token="continue_current_execution_task",
            expected_ak_wire_source_owner="softwareco/owned/agent-kernel",
            expected_ak_wire_identity=AK_WIRE_IDENTITY,
            expected_ak_wire_digest=AK_WIRE_DIGEST,
        )


def _family_import(
    owner: str,
    family_id: str,
    epoch: int,
    publication_id: str,
    transition_token: str = "continue_current_execution_task",
) -> dict[str, object]:
    return {
        "schema_version": "layer12-fixed-family-import-v1",
        "owner": owner,
        "family_id": family_id,
        "publication_id": publication_id,
        "epoch": epoch,
        "spec_digest": "sha256:"
        + hashlib.sha256(f"{owner}:{family_id}".encode()).hexdigest(),
        "transition_token": transition_token,
        "publication_scope": "owner_local_artifact_only",
        "authority_granted": False,
    }


def _withdrawal(
    owner: str, family_id: str, epoch: int, publication_id: str
) -> dict[str, object]:
    return {
        "schema_version": "layer12-fixed-family-withdrawal-v1",
        "owner": owner,
        "family_id": family_id,
        "publication_id": publication_id,
        "epoch": epoch,
        "withdrawal_ref": f"withdrawal:{owner}:{family_id}:{epoch}",
        "owner_local_only": True,
        "authority_granted": False,
    }


def _high_watermarks(*imports: dict[str, object]) -> list[dict[str, object]]:
    maxima: dict[tuple[str, str], dict[str, object]] = {}
    used_ids: dict[tuple[str, str], list[object]] = {}
    for item in imports:
        key = (cast(str, item["owner"]), cast(str, item["family_id"]))
        used_ids.setdefault(key, []).append(item["publication_id"])
        if key not in maxima or cast(int, item["epoch"]) > cast(
            int, maxima[key]["epoch"]
        ):
            maxima[key] = item
    return [
        {
            "schema_version": "layer12-fixed-family-epoch-high-watermark-v1",
            "owner": owner,
            "family_id": family_id,
            "epoch": item["epoch"],
            "transition_token": item["transition_token"],
            "spec_digest": item["spec_digest"],
            "used_publication_ids": used_ids[(owner, family_id)],
        }
        for (owner, family_id), item in maxima.items()
    ]


def test_reconstruction_appends_per_family_and_preserves_unrelated_imports() -> None:
    unrelated = _family_import(
        OWNER, "unrelated.family", 7, "unrelated:7", "unrelated_transition_token"
    )
    target_v1 = _family_import(OWNER, FAMILY_ID, 1, "target:1")
    target_v2 = _family_import(OWNER, FAMILY_ID, 2, "target:2")

    result = reconstruct_fixed_family_imports(
        prior_imports=[unrelated, target_v1],
        prior_epoch_high_watermarks=_high_watermarks(unrelated, target_v1),
        current_import=target_v2,
        current_withdrawal=None,
    )

    assert result["imports"] == [unrelated, target_v1, target_v2]
    assert result["withdrawal_applied"] is False
    assert result["preserve_unrelated_imports"] is True
    assert result["authority_granted"] is False
    schema = _load(SCHEMA_PATH)
    validator = jsonschema.Draft202012Validator(schema)
    for artifact in (unrelated, target_v1, target_v2, result):
        validator.validate(artifact)


def test_reconstruction_withdraws_only_exact_matching_family_epoch() -> None:
    unrelated = _family_import(
        OWNER, "unrelated.family", 4, "unrelated:4", "unrelated_transition_token"
    )
    target_v1 = _family_import(OWNER, FAMILY_ID, 1, "target:1")
    other_owner = _family_import("other/owner", FAMILY_ID, 1, "other:1")

    withdrawal = _withdrawal(OWNER, FAMILY_ID, 1, "target:1")
    result = reconstruct_fixed_family_imports(
        prior_imports=[unrelated, target_v1, other_owner],
        prior_epoch_high_watermarks=_high_watermarks(unrelated, target_v1, other_owner),
        current_import=None,
        current_withdrawal=withdrawal,
    )
    jsonschema.Draft202012Validator(_load(SCHEMA_PATH)).validate(withdrawal)

    assert result["imports"] == [unrelated, other_owner]
    assert result["withdrawal_applied"] is True
    assert result["withdrawn_identity"] == {
        "owner": OWNER,
        "family_id": FAMILY_ID,
        "epoch": 1,
        "publication_id": "target:1",
        "withdrawal_ref": f"withdrawal:{OWNER}:{FAMILY_ID}:1",
    }


@pytest.mark.parametrize(
    ("prior", "current", "message"),
    [
        (
            [_family_import(OWNER, FAMILY_ID, 1, "target:1")],
            _family_import(OWNER, FAMILY_ID, 1, "target:1"),
            "duplicates or conflicts",
        ),
        (
            [_family_import(OWNER, FAMILY_ID, 1, "target:1")],
            _family_import(OWNER, FAMILY_ID, 1, "target:conflict"),
            "duplicates or conflicts",
        ),
        (
            [_family_import(OWNER, FAMILY_ID, 2, "target:2")],
            _family_import(OWNER, FAMILY_ID, 1, "target:1"),
            "strictly monotonic",
        ),
        (
            [_family_import(OWNER, FAMILY_ID, 1, "target:1")],
            _family_import(
                OWNER, FAMILY_ID, 2, "target:2", "conflicting_transition_token"
            ),
            "owner/family contract",
        ),
        (
            [_family_import(OWNER, FAMILY_ID, 1, "shared-id")],
            _family_import(
                OWNER,
                "unrelated.family",
                1,
                "shared-id",
                "unrelated_transition_token",
            ),
            "publication_id",
        ),
    ],
)
def test_reconstruction_rejects_duplicate_conflicting_or_nonmonotonic_history(
    prior: list[object], current: object, message: str
) -> None:
    with pytest.raises(Layer12FixedFamilyPublicationError, match=message):
        reconstruct_fixed_family_imports(
            prior_imports=prior,
            prior_epoch_high_watermarks=_high_watermarks(
                *(cast(dict[str, object], item) for item in prior)
            ),
            current_import=current,
            current_withdrawal=None,
        )


def test_reconstruction_rejects_cross_family_and_conflicting_withdrawals() -> None:
    target = _family_import(OWNER, FAMILY_ID, 1, "target:1")
    unrelated = _family_import(
        OWNER, "unrelated.family", 1, "unrelated:1", "unrelated_transition_token"
    )
    with pytest.raises(Layer12FixedFamilyPublicationError, match="exactly one"):
        reconstruct_fixed_family_imports(
            prior_imports=[target, unrelated],
            prior_epoch_high_watermarks=_high_watermarks(target, unrelated),
            current_import=None,
            current_withdrawal=_withdrawal(OWNER, "missing.family", 1, "target:1"),
        )
    with pytest.raises(Layer12FixedFamilyPublicationError, match="publication_id"):
        reconstruct_fixed_family_imports(
            prior_imports=[target, unrelated],
            prior_epoch_high_watermarks=_high_watermarks(target, unrelated),
            current_import=None,
            current_withdrawal=_withdrawal(OWNER, FAMILY_ID, 1, "forged-id"),
        )


def test_chained_reconstruction_preserves_withdrawn_epoch_high_watermark() -> None:
    target_v2 = _family_import(OWNER, FAMILY_ID, 2, "target:2")
    unrelated = _family_import(
        OWNER, "unrelated.family", 9, "unrelated:9", "unrelated_token"
    )
    withdrawn = reconstruct_fixed_family_imports(
        prior_imports=[target_v2, unrelated],
        prior_epoch_high_watermarks=_high_watermarks(target_v2, unrelated),
        current_import=None,
        current_withdrawal=_withdrawal(OWNER, FAMILY_ID, 2, "target:2"),
    )
    imports = cast(list[object], withdrawn["imports"])
    watermarks = cast(list[object], withdrawn["family_epoch_high_watermarks"])
    assert imports == [unrelated]
    assert any(
        item["owner"] == OWNER and item["family_id"] == FAMILY_ID and item["epoch"] == 2
        for item in cast(list[dict[str, object]], watermarks)
    )

    for replay in (
        _family_import(OWNER, FAMILY_ID, 2, "target:2-reused"),
        _family_import(OWNER, FAMILY_ID, 1, "target:1-regressed"),
    ):
        with pytest.raises(Layer12FixedFamilyPublicationError, match="high-water"):
            reconstruct_fixed_family_imports(
                prior_imports=imports,
                prior_epoch_high_watermarks=watermarks,
                current_import=replay,
                current_withdrawal=None,
            )

    with pytest.raises(Layer12FixedFamilyPublicationError, match="durable"):
        reconstruct_fixed_family_imports(
            prior_imports=imports,
            prior_epoch_high_watermarks=watermarks,
            current_import=_family_import(OWNER, FAMILY_ID, 3, "target:2"),
            current_withdrawal=None,
        )

    target_v3 = _family_import(OWNER, FAMILY_ID, 3, "target:3")
    advanced = reconstruct_fixed_family_imports(
        prior_imports=imports,
        prior_epoch_high_watermarks=watermarks,
        current_import=target_v3,
        current_withdrawal=None,
    )
    assert advanced["imports"] == [unrelated, target_v3]
    assert any(
        item["owner"] == OWNER and item["family_id"] == FAMILY_ID and item["epoch"] == 3
        for item in cast(
            list[dict[str, object]], advanced["family_epoch_high_watermarks"]
        )
    )


def test_reconstruction_rejects_missing_duplicate_and_regressed_watermarks() -> None:
    target_v2 = _family_import(OWNER, FAMILY_ID, 2, "target:2")
    valid = _high_watermarks(target_v2)
    with pytest.raises(Layer12FixedFamilyPublicationError, match="require"):
        reconstruct_fixed_family_imports(
            prior_imports=[target_v2],
            prior_epoch_high_watermarks=[],
            current_import=None,
            current_withdrawal=None,
        )
    with pytest.raises(Layer12FixedFamilyPublicationError, match="duplicates"):
        reconstruct_fixed_family_imports(
            prior_imports=[target_v2],
            prior_epoch_high_watermarks=[*valid, *valid],
            current_import=None,
            current_withdrawal=None,
        )
    regressed = copy.deepcopy(valid)
    regressed[0]["epoch"] = 1
    with pytest.raises(Layer12FixedFamilyPublicationError, match="regresses"):
        reconstruct_fixed_family_imports(
            prior_imports=[target_v2],
            prior_epoch_high_watermarks=regressed,
            current_import=None,
            current_withdrawal=None,
        )
    omitted_id = copy.deepcopy(valid)
    omitted_id[0]["used_publication_ids"] = ["some-other-id"]
    with pytest.raises(Layer12FixedFamilyPublicationError, match="omits"):
        reconstruct_fixed_family_imports(
            prior_imports=[target_v2],
            prior_epoch_high_watermarks=omitted_id,
            current_import=None,
            current_withdrawal=None,
        )
    duplicate_id = copy.deepcopy(valid)
    duplicate_id[0]["used_publication_ids"] = ["target:2", "target:2"]
    with pytest.raises(Layer12FixedFamilyPublicationError, match="contains duplicates"):
        reconstruct_fixed_family_imports(
            prior_imports=[target_v2],
            prior_epoch_high_watermarks=duplicate_id,
            current_import=None,
            current_withdrawal=None,
        )


def test_fixture_private_key_is_deterministic_test_only_and_not_committed() -> None:
    fixture_text = PUBLICATION_PATH.read_text(encoding="utf-8")
    assert _TEST_SEED.hex() not in fixture_text
    assert "private" not in fixture_text.lower()
    assert PUBLIC_KEY_B64 in fixture_text
    assert copy.deepcopy(_load(PUBLICATION_PATH)) == _load(PUBLICATION_PATH)


B1_SPEC_PATH = Path("docs/project/layer12/request-owner-route-publication.v1.json")
B1_PUBLICATION_PATH = Path(
    "docs/project/layer12/fixtures/iw14b-request-owner-route-publication.v1.json"
)
B1_FAMILY_ID = "dspx.layer12.request-owner-route.v1"
B1_TOKEN = "request_owner_route"
B1_SCOPE_DIGEST = (
    "sha256:a96a880c99588b00a4c4c99e3035d10c792b02c91384f24ffb812438c0966583"
)
B1_SPEC_DIGEST = (
    "sha256:9c7fdfa7b13d13b803fecef1b57ed080a2b8462658f82b7f169521b84a4a893f"
)
B1_PUBLICATION_ID = "dspx-iw14b-request-owner-route-owner-local-test-v1"
B1_KEY_ID = "dspx-iw14b-b1-test-fixture-key-v1"
_B1_TEST_SEED = hashlib.sha256(
    b"DSPx IW14b B1 request_owner_route deterministic Ed25519 TEST FIXTURE ONLY v1"
).digest()
_B1_TEST_PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(_B1_TEST_SEED)
B1_PUBLIC_KEY_B64 = base64.b64encode(
    _B1_TEST_PRIVATE_KEY.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
).decode()


def _b1_kwargs() -> PublicationKwargs:
    return {
        "spec": _load(B1_SPEC_PATH),
        "expected_owner": OWNER,
        "expected_family_id": B1_FAMILY_ID,
        "expected_spec_digest": B1_SPEC_DIGEST,
        "expected_scope_digest": B1_SCOPE_DIGEST,
        "expected_transition_token": B1_TOKEN,
        "expected_ak_wire_source_owner": "softwareco/owned/agent-kernel",
        "expected_ak_wire_identity": AK_WIRE_IDENTITY,
        "expected_ak_wire_digest": AK_WIRE_DIGEST,
        "expected_publication_id": B1_PUBLICATION_ID,
        "expected_publication_epoch": 1,
        "expected_published_at": "2026-07-12T00:00:00Z",
        "expected_publication_state": "published",
        "expected_withdrawal_ref": None,
        "expected_key_id": B1_KEY_ID,
        "trusted_public_key_b64": B1_PUBLIC_KEY_B64,
        "expected_key_status": "active",
        "expected_key_valid_from": KEY_VALID_FROM,
        "expected_key_valid_until": KEY_VALID_UNTIL,
        "verification_time": VERIFY_AT,
    }


def _recompute_evidence_digest(record: dict[str, Any]) -> None:
    record["digest"] = sha256_digest(
        {key: value for key, value in record.items() if key != "digest"}
    )


def _resign_b1(
    publication: dict[str, Any],
    *,
    private_key: Ed25519PrivateKey = _B1_TEST_PRIVATE_KEY,
    key_id: str = B1_KEY_ID,
) -> None:
    payload = {key: value for key, value in publication.items() if key != "signature"}
    publication["signature"] = {
        "algorithm": "Ed25519",
        "key_id": key_id,
        "signed_payload_digest": sha256_digest(payload),
        "signature_b64": base64.b64encode(
            private_key.sign(canonical_json(payload).encode())
        ).decode(),
    }


def test_request_owner_route_spec_publication_and_program_graph_are_closed() -> None:
    schema = _load(SCHEMA_PATH)
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    )
    spec = _load(B1_SPEC_PATH)
    publication = _load(B1_PUBLICATION_PATH)
    validator.validate(spec)
    validator.validate(publication)
    assert sha256_digest(spec) == B1_SPEC_DIGEST
    result = check_fixed_family_publication(publication, **_b1_kwargs())
    assert result["transition_token"] == B1_TOKEN
    assert result["authority_granted"] is False

    evidence = spec["program_evidence"]
    assert evidence["program_intent"]["program_id"] == (
        "dspx.generated.direction_controller.v1"
    )
    assert [row["name"] for row in evidence["module_graph"]["signatures"]] == [
        "ExtractLayer12PolicyFacts",
        "DeriveLayer12StateVector",
        "ProposeLayer12Transition",
        "CritiqueAuthorityDrift",
        "CritiqueTheaterTraps",
        "RepairLayer12IR",
    ]
    assert evidence["verification_sink"]["surface"] == "ak.direction_controller.verify"
    assert evidence["controls_evidence"] == {
        "schema_version": "ak-direction-controller-controls-evidence-v1",
        "transition_token": B1_TOKEN,
        "legal": False,
        "verdict": "blocked",
        "dispatch_ready": False,
        "owner_route_sent": False,
        "missing_preconditions": [
            "owner_route_destination_resolved",
            "owner_route_dispatch_authorized",
        ],
        "declaration_is_ak_authority": False,
        "digest": "sha256:fc8463680fcd5505f8ac6b8ad6346afc85fa92e4fe6bf46ce2f6f8305cbfe182",
    }


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("expected_owner", "substituted/owner", "owner"),
        ("expected_family_id", FAMILY_ID, "family"),
        (
            "expected_transition_token",
            "continue_current_execution_task",
            "caller-pinned",
        ),
        ("expected_scope_digest", "sha256:" + "0" * 64, "scope"),
        ("expected_ak_wire_source_owner", "substituted/source", "source_owner"),
        ("expected_ak_wire_identity", "substituted.wire", "wire_identity"),
        ("expected_ak_wire_digest", "sha256:" + "0" * 64, "wire_digest"),
        ("expected_publication_id", "substituted-id", "publication_id"),
        ("expected_published_at", "2026-07-12T00:00:01Z", "published_at"),
        ("expected_key_id", "substituted-key", "key_id"),
        (
            "trusted_public_key_b64",
            base64.b64encode(b"x" * 32).decode(),
            "public_key_b64",
        ),
        ("expected_key_status", "revoked", "key_status"),
    ],
)
def test_request_owner_route_rejects_external_pin_co_substitution(
    field: str, value: object, message: str
) -> None:
    kwargs = _b1_kwargs()
    kwargs[field] = value  # ty: ignore[invalid-key]
    with pytest.raises(Layer12FixedFamilyPublicationError, match=message):
        check_fixed_family_publication(_load(B1_PUBLICATION_PATH), **kwargs)


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("program_intent", "program_id", "substituted.program"),
        ("program_intent", "transition_token", "continue_current_execution_task"),
        ("module_graph", "entry_signature", "ProposeLayer12Transition"),
        ("module_graph", "signatures", []),
        ("verification_sink", "source_owner", "substituted/authority"),
        ("verification_sink", "surface", "generic.verifier"),
        ("controls_evidence", "legal", True),
        ("controls_evidence", "verdict", "accepted"),
        ("controls_evidence", "dispatch_ready", True),
        ("controls_evidence", "owner_route_sent", True),
        ("controls_evidence", "missing_preconditions", []),
    ],
)
def test_request_owner_route_program_and_controls_drift_fail_closed(
    section: str, field: str, value: object
) -> None:
    spec = _load(B1_SPEC_PATH)
    spec["program_evidence"][section][field] = value
    with pytest.raises(Layer12FixedFamilyPublicationError):
        check_fixed_family_spec(
            spec,
            expected_owner=OWNER,
            expected_family_id=B1_FAMILY_ID,
            expected_scope_digest=B1_SCOPE_DIGEST,
            expected_transition_token=B1_TOKEN,
            expected_ak_wire_source_owner="softwareco/owned/agent-kernel",
            expected_ak_wire_identity=AK_WIRE_IDENTITY,
            expected_ak_wire_digest=AK_WIRE_DIGEST,
        )


def test_b0_and_b1_reconstruct_cumulatively_then_withdraw_only_b1() -> None:
    b0 = cast(
        dict[str, object],
        check_fixed_family_publication(_load(PUBLICATION_PATH), **_kwargs())[
            "canonical_import"
        ],
    )
    b1 = cast(
        dict[str, object],
        check_fixed_family_publication(_load(B1_PUBLICATION_PATH), **_b1_kwargs())[
            "canonical_import"
        ],
    )
    b0_bytes = canonical_json(b0).encode()
    cumulative = reconstruct_fixed_family_imports(
        prior_imports=[b0],
        prior_epoch_high_watermarks=_high_watermarks(b0),
        current_import=b1,
        current_withdrawal=None,
    )
    assert cumulative["imports"] == [b0, b1]
    assert len(cast(list[object], cumulative["family_epoch_high_watermarks"])) == 2

    withdrawn = reconstruct_fixed_family_imports(
        prior_imports=cast(list[object], cumulative["imports"]),
        prior_epoch_high_watermarks=cast(
            list[object], cumulative["family_epoch_high_watermarks"]
        ),
        current_import=None,
        current_withdrawal=_withdrawal(OWNER, B1_FAMILY_ID, 1, B1_PUBLICATION_ID),
    )
    retained = cast(list[dict[str, object]], withdrawn["imports"])
    assert len(retained) == 1
    assert canonical_json(retained[0]).encode() == b0_bytes
    watermarks = cast(
        list[dict[str, object]], withdrawn["family_epoch_high_watermarks"]
    )
    assert len(watermarks) == 2
    b1_history = next(row for row in watermarks if row["family_id"] == B1_FAMILY_ID)
    assert b1_history["epoch"] == 1
    assert b1_history["used_publication_ids"] == [B1_PUBLICATION_ID]


def test_request_owner_route_test_key_has_no_private_material_in_artifacts() -> None:
    publication_text = B1_PUBLICATION_PATH.read_text(encoding="utf-8")
    spec_text = B1_SPEC_PATH.read_text(encoding="utf-8")
    docs_text = Path(
        "docs/project/layer12/request-owner-route-publication.md"
    ).read_text(encoding="utf-8")
    for text in (publication_text, spec_text, docs_text):
        assert _B1_TEST_SEED.hex() not in text
        assert "private_key" not in text.lower()
    assert B1_PUBLIC_KEY_B64 in publication_text


def test_request_owner_route_graph_has_no_unbound_signature_inputs() -> None:
    evidence = _load(B1_SPEC_PATH)["program_evidence"]
    intent_inputs = set(evidence["program_intent"]["inputs"])
    produced: set[str] = set()
    edges = evidence["module_graph"]["edges"]
    for signature in evidence["module_graph"]["signatures"]:
        name = signature["name"]
        inbound = {
            edge["target"].split(".", 1)[1]
            for edge in edges
            if edge["target"].split(".", 1)[0] == name
        }
        assert set(signature["inputs"]) <= intent_inputs | inbound
        produced.update(f"{name}.{field}" for field in signature["outputs"])
    assert {edge["source"] for edge in edges} <= produced


@pytest.mark.parametrize("kind", ["owner", "family", "source"])
def test_artifact_and_caller_co_substitution_cannot_change_fixed_owners(
    kind: str,
) -> None:
    spec = _load(B1_SPEC_PATH)
    kwargs = {
        "expected_owner": OWNER,
        "expected_family_id": B1_FAMILY_ID,
        "expected_scope_digest": B1_SCOPE_DIGEST,
        "expected_transition_token": B1_TOKEN,
        "expected_ak_wire_source_owner": "softwareco/owned/agent-kernel",
        "expected_ak_wire_identity": AK_WIRE_IDENTITY,
        "expected_ak_wire_digest": AK_WIRE_DIGEST,
    }
    if kind == "owner":
        spec["owner"] = "substituted/owner"
        kwargs["expected_owner"] = "substituted/owner"
    elif kind == "family":
        spec["family_id"] = "substituted.family"
        spec["program_evidence"]["program_intent"]["family_id"] = "substituted.family"
        kwargs["expected_family_id"] = "substituted.family"
    else:
        spec["ak_wire_evidence"]["source_owner"] = "substituted/source"
        kwargs["expected_ak_wire_source_owner"] = "substituted/source"
    with pytest.raises(Layer12FixedFamilyPublicationError, match="unsupported"):
        check_fixed_family_spec(spec, **kwargs)


def test_b1_schema_rejects_validly_resigned_published_at_substitution() -> None:
    validator = jsonschema.Draft202012Validator(_load(SCHEMA_PATH))
    substituted = _load(B1_PUBLICATION_PATH)
    substituted["published_at"] = "2026-07-12T00:00:01Z"
    _resign_b1(substituted)
    assert not validator.is_valid(substituted)


def test_schema_couples_each_family_to_its_token_and_b1_evidence() -> None:
    validator = jsonschema.Draft202012Validator(_load(SCHEMA_PATH))
    b1_without_evidence = _load(B1_SPEC_PATH)
    del b1_without_evidence["program_evidence"]
    assert not validator.is_valid(b1_without_evidence)

    b0_with_b1_token = _load(SPEC_PATH)
    b0_with_b1_token["transition_tokens"] = [B1_TOKEN]
    assert not validator.is_valid(b0_with_b1_token)

    b1_with_b0_token = _load(B1_SPEC_PATH)
    b1_with_b0_token["transition_tokens"] = ["continue_current_execution_task"]
    assert not validator.is_valid(b1_with_b0_token)


@pytest.mark.parametrize(
    "substitution",
    ["objective", "signature", "edge", "verify_command", "precondition"],
)
def test_b1_schema_rejects_recomputed_digest_contract_substitutions(
    substitution: str,
) -> None:
    specimen = _load(B1_SPEC_PATH)
    evidence = specimen["program_evidence"]
    if substitution == "objective":
        evidence["program_intent"]["objective"] = "Substituted objective."
        _recompute_evidence_digest(evidence["program_intent"])
    elif substitution == "signature":
        evidence["module_graph"]["signatures"][0]["outputs"][0] = "other_facts"
        _recompute_evidence_digest(evidence["module_graph"])
    elif substitution == "edge":
        evidence["module_graph"]["edges"][0]["target"] = (
            "ProposeLayer12Transition.legal_controls"
        )
        _recompute_evidence_digest(evidence["module_graph"])
    elif substitution == "verify_command":
        evidence["verification_sink"]["expected_command"] = "ak verify substituted"
    else:
        evidence["controls_evidence"]["missing_preconditions"][0] = (
            "substituted_precondition"
        )
        _recompute_evidence_digest(evidence["controls_evidence"])

    validator = jsonschema.Draft202012Validator(_load(SCHEMA_PATH))
    assert not validator.is_valid(specimen)


@pytest.mark.parametrize(
    "substitution",
    [
        "signer_key_id",
        "signer_public_key",
        "publication_id",
        "publication_epoch",
        "valid_from",
        "valid_until",
        "published_at",
    ],
)
def test_b1_owner_fixture_anchors_reject_artifact_and_caller_co_substitution(
    substitution: str,
) -> None:
    publication = _load(B1_PUBLICATION_PATH)
    kwargs = _b1_kwargs()
    private_key = _B1_TEST_PRIVATE_KEY
    key_id = B1_KEY_ID
    if substitution == "signer_key_id":
        key_id = "co-substituted-test-key"
        publication["signer_evidence"]["key_id"] = key_id
        kwargs["expected_key_id"] = key_id
    elif substitution == "signer_public_key":
        private_key = Ed25519PrivateKey.from_private_bytes(b"B" * 32)
        public_key = base64.b64encode(
            private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        ).decode()
        publication["signer_evidence"]["public_key_b64"] = public_key
        kwargs["trusted_public_key_b64"] = public_key
    elif substitution == "publication_id":
        publication["publication_id"] = "co-substituted-publication"
        kwargs["expected_publication_id"] = "co-substituted-publication"
    elif substitution == "publication_epoch":
        publication["publication_lifecycle"]["epoch"] = 2
        kwargs["expected_publication_epoch"] = 2
    elif substitution == "valid_from":
        publication["signer_evidence"]["valid_from"] = "2026-06-01T00:00:00Z"
        kwargs["expected_key_valid_from"] = "2026-06-01T00:00:00Z"
    elif substitution == "valid_until":
        publication["signer_evidence"]["valid_until"] = "2026-09-01T00:00:00Z"
        kwargs["expected_key_valid_until"] = "2026-09-01T00:00:00Z"
    else:
        publication["published_at"] = "2026-07-12T00:00:01Z"
        kwargs["expected_published_at"] = "2026-07-12T00:00:01Z"
    _resign_b1(publication, private_key=private_key, key_id=key_id)

    with pytest.raises(Layer12FixedFamilyPublicationError, match="owner-fixed"):
        check_fixed_family_publication(publication, **kwargs)


B2_SCOPE_DIGEST = (
    "sha256:8783fc9276dafc434003277b6a690b92fe466a8249a4e0e50f82071dc30b98ca"
)
B2_CASES = {
    "close_implementation_wave": {
        "slug": "close-implementation-wave",
        "family_id": "dspx.layer12.close-implementation-wave.v1",
        "spec_digest": "sha256:ebd3b5f19be87179911029e552aa5bc00c4de774bd9264efd5fac397435ac06f",
        "publication_id": "dspx-iw14b-close-implementation-wave-owner-local-test-v1",
        "published_at": "2026-07-12T01:00:00Z",
        "key_id": "dspx-iw14b-b2-close-implementation-wave-test-key-v1",
        "public_key_b64": "JIT4mN3K8+RjeDS1zFFj9Hc3Z6fIh1h1OjdB+oj4T78=",
        "program_id": "dspx.generated.close_implementation_wave.v1",
    },
    "activate_guidance": {
        "slug": "activate-guidance",
        "family_id": "dspx.layer12.activate-guidance.v1",
        "spec_digest": "sha256:e58fb94f75ccd9cbf3a63216d779e0bf45791b37f128dc0a43e741858e9fb374",
        "publication_id": "dspx-iw14b-activate-guidance-owner-local-test-v1",
        "published_at": "2026-07-12T01:01:00Z",
        "key_id": "dspx-iw14b-b2-activate-guidance-test-key-v1",
        "public_key_b64": "qVm/c/f4VYGDQ6m5g/tR0Tvsd9KVtFHq2X9HI3l3tL4=",
        "program_id": "dspx.generated.activate_guidance.v1",
    },
    "default_residual_adoption_hardening": {
        "slug": "default-residual-adoption-hardening",
        "family_id": "dspx.layer12.default-residual-adoption-hardening.v1",
        "spec_digest": "sha256:eb4f1d7634fbade45cc80fcf2c753611ea41672603dcf04d42e595fa7258f86d",
        "publication_id": "dspx-iw14b-default-residual-adoption-hardening-owner-local-test-v1",
        "published_at": "2026-07-12T01:02:00Z",
        "key_id": "dspx-iw14b-b2-default-residual-adoption-hardening-test-key-v1",
        "public_key_b64": "niF7gGvJIPzdKUZYAMJbhF4H9FXi7kBDZnTuw6ZaS/k=",
        "program_id": "dspx.generated.default_residual_adoption_hardening.v1",
    },
}


def _b2_paths(token: str) -> tuple[Path, Path]:
    slug = B2_CASES[token]["slug"]
    return (
        Path(f"docs/project/layer12/{slug}-publication.v1.json"),
        Path(f"docs/project/layer12/fixtures/iw14b-{slug}-publication.v1.json"),
    )


def _b2_kwargs(token: str) -> PublicationKwargs:
    case = B2_CASES[token]
    spec_path, _ = _b2_paths(token)
    return {
        "spec": _load(spec_path),
        "expected_owner": OWNER,
        "expected_family_id": case["family_id"],
        "expected_spec_digest": case["spec_digest"],
        "expected_scope_digest": B2_SCOPE_DIGEST,
        "expected_transition_token": token,
        "expected_ak_wire_source_owner": "softwareco/owned/agent-kernel",
        "expected_ak_wire_identity": AK_WIRE_IDENTITY,
        "expected_ak_wire_digest": AK_WIRE_DIGEST,
        "expected_publication_id": case["publication_id"],
        "expected_publication_epoch": 1,
        "expected_published_at": case["published_at"],
        "expected_publication_state": "published",
        "expected_withdrawal_ref": None,
        "expected_key_id": case["key_id"],
        "trusted_public_key_b64": case["public_key_b64"],
        "expected_key_status": "active",
        "expected_key_valid_from": KEY_VALID_FROM,
        "expected_key_valid_until": KEY_VALID_UNTIL,
        "verification_time": VERIFY_AT,
    }


@pytest.mark.parametrize("token", list(B2_CASES))
def test_b2_publications_are_exact_closed_test_only_owner_local_artifacts(
    token: str,
) -> None:
    spec_path, publication_path = _b2_paths(token)
    spec = _load(spec_path)
    publication = _load(publication_path)
    validator = jsonschema.Draft202012Validator(
        _load(SCHEMA_PATH), format_checker=jsonschema.FormatChecker()
    )
    validator.validate(spec)
    validator.validate(publication)
    case = B2_CASES[token]
    assert sha256_digest(spec) == case["spec_digest"]
    result = check_fixed_family_publication(publication, **_b2_kwargs(token))
    assert result["verified"] is True
    assert result["transition_token"] == token
    assert result["family_id"] == case["family_id"]
    assert result["publication_scope"] == "owner_local_artifact_only"
    assert result["authority_granted"] is False
    assert spec["authorization_evidence"] == {
        "task_key": "B2-DSPx-publications",
        "authorization_evidence_id": "4231",
        "task_id": "3836",
        "scope_digest": B2_SCOPE_DIGEST,
        "declaration_is_ak_authority": False,
        "transition_authorized": False,
    }
    controls = spec["program_evidence"]["controls_evidence"]
    assert controls["legal"] is False
    assert controls["verdict"] == "blocked"
    assert controls["dispatch_ready"] is False
    assert controls["transition_action_performed"] is False
    assert spec["program_evidence"]["verification_sink"]["apply_performed"] is False
    assert (
        spec["program_evidence"]["program_intent"]["program_id"] == case["program_id"]
    )


@pytest.mark.parametrize(
    ("token", "wrong_family"),
    [
        (token, B2_CASES[other]["family_id"])
        for token in B2_CASES
        for other in B2_CASES
        if token != other
    ],
)
def test_b2_rejects_every_cross_token_family_pair(
    token: str, wrong_family: str
) -> None:
    spec_path, _ = _b2_paths(token)
    spec = _load(spec_path)
    spec["family_id"] = wrong_family
    spec["program_evidence"]["program_intent"]["family_id"] = wrong_family
    kwargs = _b2_kwargs(token)
    kwargs["expected_family_id"] = wrong_family
    with pytest.raises(
        Layer12FixedFamilyPublicationError, match="unsupported external family"
    ):
        check_fixed_family_spec(
            spec,
            expected_owner=kwargs["expected_owner"],
            expected_family_id=wrong_family,
            expected_scope_digest=B2_SCOPE_DIGEST,
            expected_transition_token=token,
            expected_ak_wire_source_owner=kwargs["expected_ak_wire_source_owner"],
            expected_ak_wire_identity=kwargs["expected_ak_wire_identity"],
            expected_ak_wire_digest=kwargs["expected_ak_wire_digest"],
        )


@pytest.mark.parametrize("token", list(B2_CASES))
def test_b2_owner_fixed_public_material_cannot_be_co_substituted(token: str) -> None:
    _, publication_path = _b2_paths(token)
    kwargs = _b2_kwargs(token)
    kwargs["trusted_public_key_b64"] = base64.b64encode(b"z" * 32).decode()
    with pytest.raises(Layer12FixedFamilyPublicationError, match="owner-fixed"):
        check_fixed_family_publication(_load(publication_path), **kwargs)


def _verified_b2_import(token: str) -> dict[str, object]:
    _, publication_path = _b2_paths(token)
    return cast(
        dict[str, object],
        check_fixed_family_publication(_load(publication_path), **_b2_kwargs(token))[
            "canonical_import"
        ],
    )


@pytest.mark.parametrize(
    "token",
    ["continue_current_execution_task", "request_owner_route", *B2_CASES],
)
def test_reconstruction_rejects_fixed_token_with_generic_family(token: str) -> None:
    escaped = _family_import(
        OWNER,
        "dspx.layer12.generic-family.v1",
        1,
        f"generic-family:{token}",
        token,
    )
    assert not jsonschema.Draft202012Validator(_load(SCHEMA_PATH)).is_valid(escaped)
    with pytest.raises(Layer12FixedFamilyPublicationError, match="token/family"):
        reconstruct_fixed_family_imports(
            prior_imports=[],
            prior_epoch_high_watermarks=[],
            current_import=escaped,
            current_withdrawal=None,
        )


@pytest.mark.parametrize("token", list(B2_CASES))
def test_reconstruction_rejects_known_fixed_family_cross_token_import(
    token: str,
) -> None:
    current = _verified_b2_import(token)
    current["transition_token"] = next(other for other in B2_CASES if other != token)
    with pytest.raises(Layer12FixedFamilyPublicationError, match="token/family"):
        reconstruct_fixed_family_imports(
            prior_imports=[],
            prior_epoch_high_watermarks=[],
            current_import=current,
            current_withdrawal=None,
        )


@pytest.mark.parametrize("withdrawal_mask", range(1, 8))
def test_all_seven_b2_withdrawal_subsets_preserve_b0_b1_and_history(
    withdrawal_mask: int,
) -> None:
    b0 = cast(
        dict[str, object],
        check_fixed_family_publication(_load(PUBLICATION_PATH), **_kwargs())[
            "canonical_import"
        ],
    )
    b1 = cast(
        dict[str, object],
        check_fixed_family_publication(_load(B1_PUBLICATION_PATH), **_b1_kwargs())[
            "canonical_import"
        ],
    )
    baseline_bytes = [canonical_json(item).encode() for item in (b0, b1)]
    imports: list[object] = [b0, b1]
    watermarks: list[object] = list(_high_watermarks(b0, b1))
    b2_imports = [_verified_b2_import(token) for token in B2_CASES]
    for current in b2_imports:
        cumulative = reconstruct_fixed_family_imports(
            prior_imports=imports,
            prior_epoch_high_watermarks=watermarks,
            current_import=current,
            current_withdrawal=None,
        )
        imports = cast(list[object], cumulative["imports"])
        watermarks = cast(list[object], cumulative["family_epoch_high_watermarks"])
    assert len(imports) == 5
    assert len(watermarks) == 5

    for index, current in enumerate(b2_imports):
        if withdrawal_mask & (1 << index):
            withdrawn = reconstruct_fixed_family_imports(
                prior_imports=imports,
                prior_epoch_high_watermarks=watermarks,
                current_import=None,
                current_withdrawal=_withdrawal(
                    OWNER,
                    cast(str, current["family_id"]),
                    cast(int, current["epoch"]),
                    cast(str, current["publication_id"]),
                ),
            )
            assert withdrawn["withdrawal_applied"] is True
            withdrawn_identity = cast(
                dict[str, object], withdrawn["withdrawn_identity"]
            )
            assert withdrawn_identity["family_id"] == current["family_id"]
            assert withdrawn_identity["publication_id"] == current["publication_id"]
            imports = cast(list[object], withdrawn["imports"])
            watermarks = cast(list[object], withdrawn["family_epoch_high_watermarks"])
    retained = cast(list[dict[str, object]], imports)
    assert [canonical_json(item).encode() for item in retained[:2]] == baseline_bytes
    expected_retained_b2 = [
        item
        for index, item in enumerate(b2_imports)
        if not withdrawal_mask & (1 << index)
    ]
    assert retained[2:] == expected_retained_b2
    assert len(retained) == 5 - withdrawal_mask.bit_count()
    assert len(watermarks) == 5
    watermark_by_family = {
        cast(str, row["family_id"]): row
        for row in cast(list[dict[str, object]], watermarks)
    }
    for current in b2_imports:
        history = watermark_by_family[cast(str, current["family_id"])]
        assert history["epoch"] == 1
        assert history["used_publication_ids"] == [current["publication_id"]]

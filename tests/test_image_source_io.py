"""Generation attachment custody and text/source binding compatibility."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from dspx.image_admission import ImageContractError
from dspx.image_source_io import contract_verification_metadata


def _attachment(source: Path) -> dict[str, object]:
    return {
        "schema_version": "program-architecture-contract-verification-v1",
        "status": "verified_contract_intent",
        "materialization_allowed_by_contract_verification": True,
        "materialization_gate": {
            "status": "verified_for_explicit_program_gen_materialization",
            "program_gen_must_match_intent_hash": hashlib.sha256(
                source.read_bytes()
            ).hexdigest(),
            "allows_live_tools": False,
            "allows_custom_imports": False,
            "allows_external_retrievers": False,
        },
        "non_authority": {"promotion_authority": False},
    }


@pytest.mark.parametrize("image_profile", [False, True])
def test_verification_attachment_keeps_exact_bytes_and_actual_source_binding(
    tmp_path: Path,
    image_profile: bool,
) -> None:
    source = tmp_path / "intent.json"
    source.write_text('{"objective":"safe"}\n', encoding="utf-8")
    attachment = tmp_path / "verification.json"
    raw = json.dumps(_attachment(source), indent=3) + "\n"
    attachment.write_text(raw, encoding="utf-8")
    root = tmp_path / "candidate"
    root.mkdir()
    result = contract_verification_metadata(
        attachment,
        root=root,
        intent_source=source,
        image_profile=image_profile,
    )
    assert result is not None
    assert result["content_hash"] == hashlib.sha256(raw.encode()).hexdigest()
    assert result["non_authority"] == {"promotion_authority": False}
    assert (
        root / "program_architecture_contract_verification.json"
    ).read_bytes() == raw.encode()
    different_root = tmp_path / "different"
    different_root.mkdir()
    source.write_text('{"objective":"changed"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="intent_hash_mismatch"):
        contract_verification_metadata(
            attachment,
            root=different_root,
            intent_source=source,
            image_profile=image_profile,
        )
    assert list(different_root.iterdir()) == []


@pytest.mark.parametrize(
    "payload", ["data:image/png;base64,QUJD", "<<CUSTOM-TYPE-END-IDENTIFIER>>"]
)
def test_attachment_privacy_branch_does_not_redefine_text_attachments(
    tmp_path: Path,
    payload: str,
) -> None:
    source = tmp_path / "intent.json"
    source.write_text('{"objective":"text"}', encoding="utf-8")
    record = _attachment(source)
    record["legacy_extra"] = payload
    attachment = tmp_path / "verification.json"
    raw = json.dumps(record)
    attachment.write_text(raw, encoding="utf-8")
    text_root = tmp_path / "text"
    image_root = tmp_path / "image"
    text_root.mkdir()
    image_root.mkdir()
    contract_verification_metadata(attachment, root=text_root, intent_source=source)
    assert (
        text_root / "program_architecture_contract_verification.json"
    ).read_text() == raw
    with pytest.raises(ImageContractError, match="image_generation_inputs_unsupported"):
        contract_verification_metadata(
            attachment,
            root=image_root,
            intent_source=source,
            image_profile=True,
        )
    assert list(image_root.iterdir()) == []

from __future__ import annotations

import pytest

from dspx.services.program_oracle_secret_policy import (
    ProgramOracleSecretPolicyError,
    build_onepassword_ref_descriptors,
    validate_publisher_assertion_no_secret,
)


def test_onepassword_ref_descriptor_redacts_and_hashes_ref() -> None:
    refs = build_onepassword_ref_descriptors(
        ["op://Private/DSPx-Oracle/password", "op://Private/DSPx-Oracle/password"]
    )

    assert refs == [
        {
            "provider": "1password",
            "ref_kind": "op_uri",
            "ref_redacted": "op://<redacted>/<redacted>/password",
            "ref_sha256": refs[0]["ref_sha256"],
            "sdk_resolution_attempted": False,
            "secret_value_persisted": False,
        }
    ]
    assert "Private" not in refs[0]["ref_redacted"]
    assert "DSPx-Oracle" not in refs[0]["ref_redacted"]
    assert len(refs[0]["ref_sha256"]) == 64


@pytest.mark.parametrize(
    "ref",
    [
        "",
        "https://example.com/secret",
        "op://VaultOnly",
        "op://Vault/Item With Space/password",
    ],
)
def test_onepassword_ref_descriptor_rejects_invalid_refs(ref: str) -> None:
    with pytest.raises(ProgramOracleSecretPolicyError):
        build_onepassword_ref_descriptors([ref])


@pytest.mark.parametrize(
    "assertion",
    [
        "database_url=postgresql://user:secret@example.invalid/db",
        "Bearer abcdefghijklmnopqrstuvwxyz0123456789",
        "api_key=abcdefghijklmnopqrstuvwxyz012345",
        "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----",
        "see op://Private/DSPx/password",
    ],
)
def test_publisher_assertion_rejects_secret_shaped_content(assertion: str) -> None:
    with pytest.raises(ProgramOracleSecretPolicyError):
        validate_publisher_assertion_no_secret(assertion)


def test_publisher_assertion_accepts_custody_text() -> None:
    validate_publisher_assertion_no_secret(
        "share synthetic behavior evidence for future Oracle retrieval"
    )

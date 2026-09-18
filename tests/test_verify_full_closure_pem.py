"""Feature: the closure admits public key material and nothing private.

Installed wheels legitimately ship public keys (litellm's proxy auth
``public_key.pem``). The closure must never be pruned to pass, so the rule has to
tell public from private rather than accept certificates only.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ci"))
import verify_full_closure as closure  # noqa: E402

CERT = b"-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n"
PUBLIC = b"-----BEGIN PUBLIC KEY-----\nMIIB\n-----END PUBLIC KEY-----\n"
RSA_PUBLIC = b"-----BEGIN RSA PUBLIC KEY-----\nMIIB\n-----END RSA PUBLIC KEY-----\n"


@pytest.mark.parametrize("pem", [CERT, PUBLIC, RSA_PUBLIC, CERT + PUBLIC])
def test_public_material_is_admitted(pem):
    """Scenario: a locked wheel ships a certificate bundle or a public key.

    Given a .pem containing only certificates and public keys
    When it is classified
    Then it is public
    """
    assert closure.pem_is_public(pem)


@pytest.mark.parametrize(
    "pem",
    [
        b"-----BEGIN PRIVATE KEY-----\nMIIB\n-----END PRIVATE KEY-----\n",
        b"-----BEGIN RSA PRIVATE KEY-----\nMIIB\n",
        b"-----BEGIN OPENSSH PRIVATE KEY-----\nb3Bl\n",
        b"-----BEGIN ENCRYPTED PRIVATE KEY-----\nMIIB\n",
        CERT + b"-----BEGIN EC PRIVATE KEY-----\nMHcC\n",
        b"not a pem at all\n",
        b"",
    ],
)
def test_private_or_unrecognised_material_is_rejected(pem):
    """Scenario: a key, a cert bundled with its key, or junk named .pem.

    Given a .pem with any private key block, or no recognised public block
    When it is classified
    Then it is not public
    """
    assert not closure.pem_is_public(pem)

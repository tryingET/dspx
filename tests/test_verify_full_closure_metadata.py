"""Feature: an installed package is identified by its METADATA headers only."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ci"))
import verify_full_closure as closure  # noqa: E402


def test_description_body_cannot_override_the_package_identity():
    """Scenario: a README embedded in METADATA contains ``Name:`` lines.

    Given METADATA whose long description quotes os-release style fields
    When the package identity is read
    Then it comes from the header block before the first blank line
    """
    text = (
        "Metadata-Version: 2.1\nName: distro\nVersion: 1.9.0\nSummary: x\n"
        "\n"
        "Example output:\n\nName: Antergos Linux\nVersion: 2015.10 (ISO-Rolling)\n"
    )
    assert closure.metadata_identity(text) == ("distro", "1.9.0")


def test_names_are_normalised_like_the_lock_file():
    """Scenario: distribution names differ in case and separators."""
    text = "Metadata-Version: 2.1\nName: Typing_Extensions\nVersion: 4.12.2\n"
    assert closure.metadata_identity(text) == ("typing-extensions", "4.12.2")


@pytest.mark.parametrize(
    "text", ["Metadata-Version: 2.1\nName: x\n", "\nName: x\nVersion: 1\n", ""]
)
def test_missing_header_identity_fails_closed(text):
    """Scenario: METADATA without a Name or Version header."""
    with pytest.raises(ValueError, match="identity"):
        closure.metadata_identity(text)

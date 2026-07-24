# summary: "Tests resolved installed-environment SBOM closure and subject binding."

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Any

import pytest
from packaging.markers import default_environment


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts/ci/core_release_environment_sbom.py"
SCRIPTS = SCRIPT.parent


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "core_release_environment_sbom", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS))
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(spec.name, None)
        sys.path.remove(str(SCRIPTS))


def _records() -> list[dict[str, Any]]:
    return [
        {
            "name": "dspx-core",
            "version": "0.1.0",
            "requirements": [
                "Alpha>=2",
                "beta==3; python_version >= '3.13'",
                "ignored; python_version < '3'",
            ],
        },
        {"name": "alpha", "version": "2.4.0", "requirements": ["gamma~=1.2"]},
        {"name": "beta", "version": "3", "requirements": ["gamma>=1"]},
        {"name": "gamma", "version": "1.2.5", "requirements": []},
    ]


def _environment() -> dict[str, str]:
    return dict(default_environment())


def _build(
    module: ModuleType, records: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return module.build_environment_sbom(
        wheel_raw=b"exact wheel bytes",
        wheel_filename="dspx_core-0.1.0-py3-none-any.whl",
        installed_proof_raw=b'{"proof":"exact"}',
        records=records or _records(),
        environment=_environment(),
    )


def test_environment_sbom_is_deterministic_complete_and_bound() -> None:
    module = _load()
    first = _build(module)
    second = _build(module)

    assert first == second
    assert first["bomFormat"] == "CycloneDX"
    assert first["specVersion"] == "1.6"
    assert sorted(row["name"] for row in first["components"]) == [
        "alpha",
        "beta",
        "gamma",
    ]
    root = first["metadata"]["component"]
    assert root["hashes"] == [
        {"alg": "SHA-256", "content": hashlib.sha256(b"exact wheel bytes").hexdigest()}
    ]
    assert (
        root["properties"][1]["value"]
        == hashlib.sha256(b'{"proof":"exact"}').hexdigest()
    )
    assert (
        module.validate_environment_sbom(
            first,
            wheel_raw=b"exact wheel bytes",
            wheel_filename="dspx_core-0.1.0-py3-none-any.whl",
            installed_proof_raw=b'{"proof":"exact"}',
            records=_records(),
            environment=_environment(),
        )
        == first
    )


def test_environment_sbom_propagates_extras_and_retains_complete_marker_identity() -> (
    None
):
    module = _load()
    sbom = module.build_environment_sbom(
        wheel_raw=b"exact wheel bytes",
        wheel_filename="dspx_core-0.1.0-py3-none-any.whl",
        installed_proof_raw=b'{"proof":"exact"}',
        records=[
            {
                "name": "dspx-core",
                "version": "0.1.0",
                "requirements": ["parent[feature]"],
            },
            {
                "name": "parent",
                "version": "1.0",
                "requirements": ["child; extra == 'feature'"],
            },
            {"name": "child", "version": "2.0", "requirements": []},
        ],
        environment=_environment(),
    )
    assert sorted(row["name"] for row in sbom["components"]) == ["child", "parent"]
    property_names = {row["name"] for row in sbom["properties"]}
    for key in default_environment():
        assert f"dspx:environment:{key.replace('_', '-')}" in property_names


def test_environment_sbom_rejects_missing_mismatched_and_unreachable_dependencies() -> (
    None
):
    module = _load()
    missing = [row for row in _records() if row["name"] != "gamma"]
    with pytest.raises(module.CoreReleaseEvidenceError, match="dependency is missing"):
        _build(module, missing)

    mismatched = _records()
    mismatched[-1]["version"] = "0.9"
    with pytest.raises(module.CoreReleaseEvidenceError, match="version mismatch"):
        _build(module, mismatched)

    unreachable = _records() + [
        {"name": "ambient-unrelated", "version": "1.0", "requirements": []}
    ]
    with pytest.raises(
        module.CoreReleaseEvidenceError, match="unreachable distributions"
    ):
        _build(module, unreachable)


def test_environment_sbom_rejects_duplicate_names_and_invalid_metadata() -> None:
    module = _load()
    duplicate_name = _records() + [
        {"name": "ALPHA", "version": "2.4.0", "requirements": []}
    ]
    with pytest.raises(
        module.CoreReleaseEvidenceError, match="canonical name is duplicated"
    ):
        _build(module, duplicate_name)

    invalid = _records()
    invalid[1]["requirements"] = ["not valid !!!"]
    with pytest.raises(module.CoreReleaseEvidenceError, match="requirement is invalid"):
        _build(module, invalid)


@pytest.mark.parametrize(
    ("wheel", "proof", "message"),
    [
        (b"substituted wheel", b'{"proof":"exact"}', "wheel binding drift"),
        (b"exact wheel bytes", b'{"proof":"other"}', "installed-proof binding drift"),
    ],
)
def test_retained_environment_sbom_rejects_subject_substitution(
    wheel: bytes,
    proof: bytes,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load()
    monkeypatch.setattr(module, "_wheel_metadata", lambda _raw: ("dspx-core", "0.1.0"))
    sbom = _build(module)
    with pytest.raises(module.CoreReleaseEvidenceError, match=message):
        module.validate_retained_environment_sbom(
            sbom,
            wheel_raw=wheel,
            wheel_filename="dspx_core-0.1.0-py3-none-any.whl",
            installed_proof_raw=proof,
        )


def test_environment_sbom_rejects_tamper_duplicate_json_and_secret_shaped_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load()
    monkeypatch.setattr(module, "_wheel_metadata", lambda _raw: ("dspx-core", "0.1.0"))
    sbom = _build(module)
    serialized = json.dumps(sbom, sort_keys=True)
    assert "/home/" not in serialized
    assert "https://" not in serialized
    assert "token" not in serialized.lower()

    sbom["properties"][0]["value"] = "broader"
    with pytest.raises(module.CoreReleaseEvidenceError, match="binding drift"):
        module.validate_environment_sbom(
            sbom,
            wheel_raw=b"exact wheel bytes",
            wheel_filename="dspx_core-0.1.0-py3-none-any.whl",
            installed_proof_raw=b'{"proof":"exact"}',
            records=_records(),
            environment=_environment(),
        )
    with pytest.raises(module.CoreReleaseEvidenceError, match="key is duplicated"):
        module.load_environment_sbom_bytes(
            b'{"bomFormat":"CycloneDX","bomFormat":"other"}'
        )

    retained = _build(module)
    retained["components"].append(
        {
            "type": "library",
            "bom-ref": "pkg:pypi/injected@9",
            "name": "injected",
            "version": "9",
            "purl": "pkg:pypi/injected@9",
        }
    )
    with pytest.raises(
        module.CoreReleaseEvidenceError,
        match="(dependency closure|component order|serial identity)",
    ):
        module.validate_retained_environment_sbom(
            retained,
            wheel_raw=b"exact wheel bytes",
            wheel_filename="dspx_core-0.1.0-py3-none-any.whl",
            installed_proof_raw=b'{"proof":"exact"}',
        )

    wrong_version = _build(module)
    wrong_version["metadata"]["component"].update(
        {
            "version": "9",
            "bom-ref": "pkg:pypi/dspx-core@9",
            "purl": "pkg:pypi/dspx-core@9",
        }
    )
    with pytest.raises(module.CoreReleaseEvidenceError, match="root identity drift"):
        module.validate_retained_environment_sbom(
            wrong_version,
            wheel_raw=b"exact wheel bytes",
            wheel_filename="dspx_core-0.1.0-py3-none-any.whl",
            installed_proof_raw=b'{"proof":"exact"}',
        )

    wrong_constant = _build(module)
    wrong_constant["version"] = 2
    with pytest.raises(module.CoreReleaseEvidenceError, match="constants drift"):
        module.validate_retained_environment_sbom(
            wrong_constant,
            wheel_raw=b"exact wheel bytes",
            wheel_filename="dspx_core-0.1.0-py3-none-any.whl",
            installed_proof_raw=b'{"proof":"exact"}',
        )

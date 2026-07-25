# summary: "Tests resolved installed-environment SBOM closure and subject binding."

from __future__ import annotations

import base64
import csv
from collections.abc import Iterator
import hashlib
import importlib.util
from io import BytesIO, StringIO
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Any
import zipfile

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
    environment: dict[str, str] = {}
    for key, value in default_environment().items():
        assert isinstance(value, str)
        environment[key] = value
    return environment


def _wheel_bytes(
    *,
    requirements: list[str] | None = None,
    marker: str = "original",
) -> bytes:
    declared = (
        requirements if requirements is not None else _records()[0]["requirements"]
    )
    metadata = (
        "Metadata-Version: 2.4\n"
        "Name: dspx-core\n"
        "Version: 0.1.0\n"
        + "".join(f"Requires-Dist: {value}\n" for value in declared)
        + "\n"
    ).encode()
    files = {
        "dspx_core-0.1.0.dist-info/METADATA": metadata,
        "dspx/__init__.py": f"MARKER = {marker!r}\n".encode(),
    }
    record_path = "dspx_core-0.1.0.dist-info/RECORD"
    record = StringIO()
    writer = csv.writer(record, lineterminator="\n")
    for name, raw in sorted(files.items()):
        digest = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b"=")
        writer.writerow([name, "sha256=" + digest.decode(), len(raw)])
    writer.writerow([record_path, "", ""])
    files[record_path] = record.getvalue().encode()
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            archive.writestr(info, raw)
    return output.getvalue()


def _build(
    module: ModuleType, records: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return module.build_environment_sbom(
        wheel_raw=_wheel_bytes(),
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
        {"alg": "SHA-256", "content": hashlib.sha256(_wheel_bytes()).hexdigest()}
    ]
    assert (
        root["properties"][1]["value"]
        == hashlib.sha256(b'{"proof":"exact"}').hexdigest()
    )
    assert (
        module.validate_environment_sbom(
            first,
            wheel_raw=_wheel_bytes(),
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
        wheel_raw=_wheel_bytes(requirements=["parent[feature]"]),
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


@pytest.mark.parametrize(
    "environment",
    [
        {},
        {"python_version": "3.13"},
        {**_environment(), "unexpected": "value"},
    ],
)
def test_environment_sbom_rejects_explicit_incomplete_or_widened_environment(
    environment: dict[str, str],
) -> None:
    module = _load()
    with pytest.raises(
        module.CoreReleaseEvidenceError,
        match="marker identity fields do not match contract",
    ):
        module.build_environment_sbom(
            wheel_raw=_wheel_bytes(),
            wheel_filename="dspx_core-0.1.0-py3-none-any.whl",
            installed_proof_raw=b'{"proof":"exact"}',
            records=_records(),
            environment=environment,
        )


def test_environment_sbom_rejects_invalid_complete_environment_value() -> None:
    module = _load()
    environment = _environment()
    environment["python_version"] = ""
    with pytest.raises(
        module.CoreReleaseEvidenceError,
        match="marker environment python_version is invalid",
    ):
        module.build_environment_sbom(
            wheel_raw=_wheel_bytes(),
            wheel_filename="dspx_core-0.1.0-py3-none-any.whl",
            installed_proof_raw=b'{"proof":"exact"}',
            records=_records(),
            environment=environment,
        )


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

    duplicate_root_requirement = _records()
    duplicate_root_requirement[0]["requirements"].append("alpha >= 2")
    with pytest.raises(
        module.CoreReleaseEvidenceError,
        match="Core requirement inventory contains a duplicate",
    ):
        _build(module, duplicate_root_requirement)

    duplicate_transitive_requirement = _records()
    duplicate_transitive_requirement[1]["requirements"].append("Gamma ~= 1.2")
    assert _build(module, duplicate_transitive_requirement)["bomFormat"] == "CycloneDX"


def test_environment_sbom_bounds_requirement_iterable_consumption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load()
    consumed: list[int] = []

    def requirements() -> Iterator[str]:
        index = 0
        while True:
            consumed.append(index)
            yield f"dependency-{index}"
            index += 1

    records = _records()
    records[0]["requirements"] = requirements()
    monkeypatch.setattr(module, "_MAX_REQUIREMENTS_PER_DISTRIBUTION", 2)
    with pytest.raises(
        module.CoreReleaseEvidenceError, match="requirement inventory is oversized"
    ):
        _build(module, records)
    assert consumed == [0, 1, 2]


def test_environment_sbom_rejects_exact_wheel_root_metadata_drift() -> None:
    module = _load()
    # The installed root must be an exact metadata observation of the wheel.
    wrong_version = _records()
    wrong_version[0]["version"] = "9.0.0"
    with pytest.raises(
        module.CoreReleaseEvidenceError, match="root identity.*exact Core wheel"
    ):
        _build(module, wrong_version)

    for requirements in (
        ["Alpha>=2", "beta==3; python_version >= '3.13'"],
        [*_records()[0]["requirements"], "injected>=1"],
        ["Alpha>=2", "gamma>=1", "ignored; python_version < '3'"],
    ):
        drifted = _records()
        drifted[0]["requirements"] = requirements
        with pytest.raises(
            module.CoreReleaseEvidenceError,
            match="root dependency inventory.*exact Core wheel",
        ):
            _build(module, drifted)


def test_environment_sbom_rejects_unproven_direct_url_dependencies() -> None:
    module = _load()
    direct_url = "alpha @ https://packages.example.invalid/alpha.whl"
    records = _records()
    records[0]["requirements"] = [
        direct_url,
        "beta==3; python_version >= '3.13'",
        "ignored; python_version < '3'",
    ]
    with pytest.raises(
        module.CoreReleaseEvidenceError,
        match="cannot prove exact-wheel direct URL dependencies",
    ):
        module.build_environment_sbom(
            wheel_raw=_wheel_bytes(requirements=records[0]["requirements"]),
            wheel_filename="dspx_core-0.1.0-py3-none-any.whl",
            installed_proof_raw=b'{"proof":"exact"}',
            records=records,
            environment=_environment(),
        )

    retained = _build(module)

    def direct_url_inventory(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        inventory = module._wheel_inventory(
            _wheel_bytes(),
            wheel_filename="dspx_core-0.1.0-py3-none-any.whl",
        )
        inventory["dependencies"][0]["requirement"] = direct_url
        return inventory

    with pytest.raises(
        module.CoreReleaseEvidenceError,
        match="cannot prove exact-wheel direct URL dependencies",
    ):
        module._validate_retained_environment_sbom(
            retained,
            wheel_raw=_wheel_bytes(),
            wheel_filename="dspx_core-0.1.0-py3-none-any.whl",
            installed_proof_raw=b'{"proof":"exact"}',
            wheel_inventory=direct_url_inventory,
        )


@pytest.mark.parametrize(
    ("substitute_wheel", "proof", "message"),
    [
        (True, b'{"proof":"exact"}', "wheel binding drift"),
        (False, b'{"proof":"other"}', "installed-proof binding drift"),
    ],
)
def test_retained_environment_sbom_rejects_subject_substitution(
    substitute_wheel: bool,
    proof: bytes,
    message: str,
) -> None:
    module = _load()
    sbom = _build(module)
    wheel = _wheel_bytes(marker="substituted") if substitute_wheel else _wheel_bytes()
    with pytest.raises(module.CoreReleaseEvidenceError, match=message):
        module.validate_retained_environment_sbom(
            sbom,
            wheel_raw=wheel,
            wheel_filename="dspx_core-0.1.0-py3-none-any.whl",
            installed_proof_raw=proof,
        )


def test_environment_sbom_rejects_tamper_duplicate_json_and_secret_shaped_output() -> (
    None
):
    module = _load()
    sbom = _build(module)
    serialized = json.dumps(sbom, sort_keys=True)
    assert "/home/" not in serialized
    assert "https://" not in serialized
    assert "token" not in serialized.lower()

    sbom["properties"][0]["value"] = "broader"
    with pytest.raises(module.CoreReleaseEvidenceError, match="binding drift"):
        module.validate_environment_sbom(
            sbom,
            wheel_raw=_wheel_bytes(),
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
            wheel_raw=_wheel_bytes(),
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
            wheel_raw=_wheel_bytes(),
            wheel_filename="dspx_core-0.1.0-py3-none-any.whl",
            installed_proof_raw=b'{"proof":"exact"}',
        )

    wrong_root_edges = _build(module)
    root_ref = wrong_root_edges["metadata"]["component"]["bom-ref"]
    dependencies = {row["ref"]: row for row in wrong_root_edges["dependencies"]}
    beta_ref = next(
        row["bom-ref"]
        for row in wrong_root_edges["components"]
        if row["name"] == "beta"
    )
    alpha_ref = next(
        row["bom-ref"]
        for row in wrong_root_edges["components"]
        if row["name"] == "alpha"
    )
    dependencies[root_ref]["dependsOn"].remove(beta_ref)
    dependencies[alpha_ref]["dependsOn"] = sorted(
        [*dependencies[alpha_ref]["dependsOn"], beta_ref]
    )
    with pytest.raises(
        module.CoreReleaseEvidenceError,
        match="root dependencies drift from exact Core wheel",
    ):
        module.validate_retained_environment_sbom(
            wrong_root_edges,
            wheel_raw=_wheel_bytes(),
            wheel_filename="dspx_core-0.1.0-py3-none-any.whl",
            installed_proof_raw=b'{"proof":"exact"}',
        )

    duplicate_name = _build(module)
    duplicate_alpha = dict(
        next(row for row in duplicate_name["components"] if row["name"] == "alpha")
    )
    duplicate_alpha.update(
        {
            "version": "9",
            "bom-ref": "pkg:pypi/alpha@9",
            "purl": "pkg:pypi/alpha@9",
        }
    )
    duplicate_name["components"].insert(1, duplicate_alpha)
    with pytest.raises(
        module.CoreReleaseEvidenceError, match="component identity drift"
    ):
        module.validate_retained_environment_sbom(
            duplicate_name,
            wheel_raw=_wheel_bytes(),
            wheel_filename="dspx_core-0.1.0-py3-none-any.whl",
            installed_proof_raw=b'{"proof":"exact"}',
        )

    wrong_core_inventory = _build(module)

    def other_wheel_inventory(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        inventory = module._wheel_inventory(
            _wheel_bytes(),
            wheel_filename="dspx_core-0.1.0-py3-none-any.whl",
        )
        inventory["package_name"] = "other-core"
        return inventory

    with pytest.raises(module.CoreReleaseEvidenceError, match="package identity drift"):
        module._validate_retained_environment_sbom(
            wrong_core_inventory,
            wheel_raw=_wheel_bytes(),
            wheel_filename="dspx_core-0.1.0-py3-none-any.whl",
            installed_proof_raw=b'{"proof":"exact"}',
            wheel_inventory=other_wheel_inventory,
        )

    wrong_constant = _build(module)
    wrong_constant["version"] = 2
    with pytest.raises(module.CoreReleaseEvidenceError, match="constants drift"):
        module.validate_retained_environment_sbom(
            wrong_constant,
            wheel_raw=_wheel_bytes(),
            wheel_filename="dspx_core-0.1.0-py3-none-any.whl",
            installed_proof_raw=b'{"proof":"exact"}',
        )

# summary: "Tests deterministic CycloneDX generation and exact Core wheel binding."

from __future__ import annotations

import base64
import csv
import hashlib
import importlib.util
from io import StringIO
from pathlib import Path
import stat
import subprocess
import sys
from types import ModuleType
from typing import Any
import zipfile

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts/ci/core_release_sbom.py"
SCRIPTS = SCRIPT.parent


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("core_release_sbom", SCRIPT)
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


def _record_hash(raw: bytes) -> str:
    encoded = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b"=")
    return "sha256=" + encoded.decode()


def _wheel(
    path: Path,
    *,
    marker: str = "original",
    requirements: tuple[str, ...] = (
        "httpx>=0.28.1",
        "PyYAML>=6; python_version >= '3.13'",
    ),
) -> None:
    metadata = (
        "Metadata-Version: 2.4\n"
        "Name: dspx-core\n"
        "Version: 0.1.0\n"
        "Requires-Python: >=3.13\n"
        + "".join(f"Requires-Dist: {requirement}\n" for requirement in requirements)
        + "\n"
    ).encode()
    files = {
        "dspx/__init__.py": f"MARKER = {marker!r}\n".encode(),
        "dspx_core-0.1.0.dist-info/METADATA": metadata,
    }
    record_path = "dspx_core-0.1.0.dist-info/RECORD"
    output = StringIO()
    writer = csv.writer(output, lineterminator="\n")
    for name, raw in sorted(files.items()):
        writer.writerow([name, _record_hash(raw), len(raw)])
    writer.writerow([record_path, "", ""])
    files[record_path] = output.getvalue().encode()
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, raw in sorted(files.items()):
            archive.writestr(name, raw)


def _named_wheel(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    return root / "dspx_core-0.1.0-py3-none-any.whl"


def _rewrite_wheel(source: Path, destination: Path, mutation: Any) -> None:
    with zipfile.ZipFile(source) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    mutation(members)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, raw in sorted(members.items()):
            archive.writestr(name, raw)


def test_sbom_is_deterministic_complete_and_exactly_validated(tmp_path: Path) -> None:
    module = _load()
    wheel = tmp_path / "dspx_core-0.1.0-py3-none-any.whl"
    _wheel(wheel)
    raw = wheel.read_bytes()

    first = module.build_sbom(wheel_raw=raw, wheel_filename=wheel.name)
    second = module.build_sbom(wheel_raw=raw, wheel_filename=wheel.name)

    assert first == second
    assert first["bomFormat"] == "CycloneDX"
    assert first["specVersion"] == "1.6"
    assert first["metadata"]["component"]["hashes"] == [
        {"alg": "SHA-256", "content": hashlib.sha256(raw).hexdigest()}
    ]
    file_components = [row for row in first["components"] if row["type"] == "file"]
    dependency_components = [
        row for row in first["components"] if row["type"] == "library"
    ]
    assert len(file_components) == 3
    assert sorted(row["name"] for row in dependency_components) == ["httpx", "pyyaml"]
    assert (
        module.validate_sbom(first, wheel_raw=raw, wheel_filename=wheel.name) == first
    )


def test_sbom_cli_writes_mode_0600_and_rejects_preexisting_output(
    tmp_path: Path,
) -> None:
    wheel = tmp_path / "dspx_core-0.1.0-py3-none-any.whl"
    sbom = tmp_path / "sbom.json"
    _wheel(wheel)

    generated = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "generate",
            "--wheel",
            str(wheel),
            "--out",
            str(sbom),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert generated.returncode == 0, generated.stderr
    assert stat.S_IMODE(sbom.stat().st_mode) == 0o600
    validated = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "validate",
            "--wheel",
            str(wheel),
            "--sbom",
            str(sbom),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert validated.returncode == 0, validated.stderr
    repeated = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "generate",
            "--wheel",
            str(wheel),
            "--out",
            str(sbom),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert repeated.returncode != 0
    assert "already exists" in repeated.stderr


def test_sbom_rejects_wheel_and_sbom_substitution(tmp_path: Path) -> None:
    module = _load()
    original = tmp_path / "dspx_core-0.1.0-py3-none-any.whl"
    substituted = tmp_path / "substituted.whl"
    _wheel(original)
    _wheel(substituted, marker="substituted")
    sbom = module.build_sbom(
        wheel_raw=original.read_bytes(), wheel_filename=original.name
    )

    with pytest.raises(module.CoreReleaseEvidenceError, match="binding drift"):
        module.validate_sbom(
            sbom, wheel_raw=substituted.read_bytes(), wheel_filename=original.name
        )
    sbom["properties"][0]["value"] = "broader-than-declared"
    with pytest.raises(module.CoreReleaseEvidenceError, match="binding drift"):
        module.validate_sbom(
            sbom, wheel_raw=original.read_bytes(), wheel_filename=original.name
        )


def test_sbom_rejects_record_hash_drift_and_unsupported_algorithm(
    tmp_path: Path,
) -> None:
    module = _load()
    valid = _named_wheel(tmp_path / "valid")
    _wheel(valid)
    drifted = _named_wheel(tmp_path / "drifted")
    _rewrite_wheel(
        valid,
        drifted,
        lambda members: members.__setitem__("dspx/__init__.py", b"substituted"),
    )
    with pytest.raises(
        module.CoreReleaseEvidenceError, match="RECORD (size|hash) drift"
    ):
        module.build_sbom(wheel_raw=drifted.read_bytes(), wheel_filename=drifted.name)

    unsupported = _named_wheel(tmp_path / "unsupported")

    def rewrite_record(members: dict[str, bytes]) -> None:
        name = "dspx_core-0.1.0.dist-info/RECORD"
        members[name] = members[name].replace(b"sha256=", b"sha512=", 1)

    _rewrite_wheel(valid, unsupported, rewrite_record)
    with pytest.raises(
        module.CoreReleaseEvidenceError, match="algorithm is unsupported"
    ):
        module.build_sbom(
            wheel_raw=unsupported.read_bytes(), wheel_filename=unsupported.name
        )


@pytest.mark.parametrize(
    "requirement",
    [
        "\x01invalid",
        "httpx totally-not-a-requirement",
        "httpx >=1 garbage",
        "httpx @ not a url",
    ],
)
def test_sbom_rejects_invalid_complete_requirement(
    tmp_path: Path, requirement: str
) -> None:
    module = _load()
    wheel = _named_wheel(tmp_path / hashlib.sha256(requirement.encode()).hexdigest())
    _wheel(wheel, requirements=(requirement,))
    with pytest.raises(
        module.CoreReleaseEvidenceError, match="Requires-Dist value is invalid"
    ):
        module.build_sbom(wheel_raw=wheel.read_bytes(), wheel_filename=wheel.name)


def test_sbom_rejects_record_alias_and_duplicate_json_keys(tmp_path: Path) -> None:
    module = _load()
    with pytest.raises(module.CoreReleaseEvidenceError, match="key is duplicated"):
        module.load_sbom_bytes(b'{"bomFormat":"CycloneDX","bomFormat":"other"}')

    valid = _named_wheel(tmp_path / "valid")
    aliased = _named_wheel(tmp_path / "aliased")
    _wheel(valid)

    def alias_record(members: dict[str, bytes]) -> None:
        name = "dspx_core-0.1.0.dist-info/RECORD"
        members[name] += b"dspx/../dspx/__init__.py,,\n"

    _rewrite_wheel(valid, aliased, alias_record)
    with pytest.raises(module.CoreReleaseEvidenceError, match="unsafe path"):
        module.build_sbom(wheel_raw=aliased.read_bytes(), wheel_filename=aliased.name)


def test_sbom_rejects_duplicate_requirements_and_noncanonical_record_hash(
    tmp_path: Path,
) -> None:
    module = _load()
    duplicate = _named_wheel(tmp_path / "duplicate")
    _wheel(duplicate, requirements=("HTTPX>=1", "httpx >= 1"))
    with pytest.raises(
        module.CoreReleaseEvidenceError, match="declaration is duplicated"
    ):
        module.build_sbom(
            wheel_raw=duplicate.read_bytes(), wheel_filename=duplicate.name
        )

    valid = _named_wheel(tmp_path / "valid-hash")
    malformed = _named_wheel(tmp_path / "malformed-hash")
    _wheel(valid)

    def widen_hash(members: dict[str, bytes]) -> None:
        name = "dspx_core-0.1.0.dist-info/RECORD"
        first_line, remainder = members[name].split(b"\n", 1)
        fields = first_line.split(b",")
        fields[1] += b"!!!!"
        members[name] = b",".join(fields) + b"\n" + remainder

    _rewrite_wheel(valid, malformed, widen_hash)
    with pytest.raises(module.CoreReleaseEvidenceError, match="hash is malformed"):
        module.build_sbom(
            wheel_raw=malformed.read_bytes(), wheel_filename=malformed.name
        )


def test_sbom_rejects_split_dist_info_and_filename_identity_drift(
    tmp_path: Path,
) -> None:
    # Exact identity checks below assume unambiguous parsed metadata.
    module = _load()
    valid = _named_wheel(tmp_path / "valid")
    split = _named_wheel(tmp_path / "split")
    _wheel(valid)

    def split_dist_info(members: dict[str, bytes]) -> None:
        old = "dspx_core-0.1.0.dist-info/RECORD"
        new = "other_core-0.1.0.dist-info/RECORD"
        members[new] = members.pop(old).replace(old.encode(), new.encode())

    _rewrite_wheel(valid, split, split_dist_info)
    with pytest.raises(
        module.CoreReleaseEvidenceError, match="dist-info identity drift"
    ):
        module.build_sbom(wheel_raw=split.read_bytes(), wheel_filename=split.name)

    with pytest.raises(
        module.CoreReleaseEvidenceError, match="filename and metadata identity drift"
    ):
        module.build_sbom(
            wheel_raw=valid.read_bytes(),
            wheel_filename="other_core-0.1.0-py3-none-any.whl",
        )


def test_sbom_rejects_ambiguous_or_malformed_metadata_identity(
    tmp_path: Path,
) -> None:
    module = _load()
    valid = _named_wheel(tmp_path / "valid-metadata")
    _wheel(valid)
    metadata_path = "dspx_core-0.1.0.dist-info/METADATA"

    mutations = {
        "duplicate-name": lambda raw: raw.replace(
            b"Name: dspx-core\n", b"Name: dspx-core\nName: other\n"
        ),
        "duplicate-version": lambda raw: raw.replace(
            b"Version: 0.1.0\n", b"Version: 0.1.0\nVersion: 9\n"
        ),
        "parser-defect": lambda raw: b"not-a-header\n" + raw,
    }
    for label, mutation in mutations.items():
        malformed = _named_wheel(tmp_path / label)

        def mutate(members: dict[str, bytes], mutation: Any = mutation) -> None:
            members[metadata_path] = mutation(members[metadata_path])

        _rewrite_wheel(valid, malformed, mutate)
        with pytest.raises(
            module.CoreReleaseEvidenceError,
            match="metadata identity headers are ambiguous or malformed",
        ):
            module.build_sbom(
                wheel_raw=malformed.read_bytes(), wheel_filename=malformed.name
            )


def test_sbom_validation_enforces_official_cyclonedx_1_6_schema(
    tmp_path: Path,
) -> None:
    module = _load()
    wheel = _named_wheel(tmp_path / "valid")
    _wheel(wheel)
    sbom = module.build_sbom(wheel_raw=wheel.read_bytes(), wheel_filename=wheel.name)
    sbom["dependencies"][0]["dependsOn"].append(sbom["dependencies"][0]["dependsOn"][0])

    with pytest.raises(
        module.CoreReleaseEvidenceError,
        match="CycloneDX 1.6 schema validation failed",
    ):
        module.validate_sbom(
            sbom, wheel_raw=wheel.read_bytes(), wheel_filename=wheel.name
        )


def test_sbom_bounds_zip_directory_and_record_rows_before_inventory_growth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load()
    wheel = _named_wheel(tmp_path / "valid")
    _wheel(wheel)
    raw = wheel.read_bytes()

    monkeypatch.setattr(module, "_MAX_WHEEL_FILES", 2)
    with pytest.raises(
        module.CoreReleaseEvidenceError, match="entry count is oversized"
    ):
        module.build_sbom(wheel_raw=raw, wheel_filename=wheel.name)

    monkeypatch.setattr(module, "_MAX_WHEEL_FILES", 20_000)
    monkeypatch.setattr(module, "_MAX_RECORD_ROWS", 1)
    with pytest.raises(module.CoreReleaseEvidenceError, match="row count is oversized"):
        module.build_sbom(wheel_raw=raw, wheel_filename=wheel.name)


def test_sbom_normalizes_crc_failure_to_release_evidence_error(tmp_path: Path) -> None:
    module = _load()
    wheel = _named_wheel(tmp_path / "valid")
    corrupt = _named_wheel(tmp_path / "corrupt")
    _wheel(wheel)
    raw = wheel.read_bytes()
    marker = b"MARKER = 'original'\n"
    position = raw.find(marker)
    assert position >= 0
    corrupt.write_bytes(raw[:position] + b"X" + raw[position + 1 :])

    with pytest.raises(
        module.CoreReleaseEvidenceError,
        match="Core wheel member dspx/__init__.py cannot be read safely",
    ):
        module.build_sbom(wheel_raw=corrupt.read_bytes(), wheel_filename=corrupt.name)

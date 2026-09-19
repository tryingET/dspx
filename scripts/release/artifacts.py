"""Exact-byte package manifest; no candidate imports or publication authority."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import subprocess
import tarfile
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA = "dspx-package-release-v1"
LICENSE = "LicenseRef-Apache-2.0-with-AI-Rider"
RIDER = b"ADDITIONAL RIDER / RESTRICTION"
PACKAGES = {"dspx-core": "packages/dspx-core", "dspx-forge": "apps/forge"}
MANIFEST = "release-manifest.json"
MAX_FILE = 512 * 1024 * 1024
MAX_TEXT = 256 * 1024


class ArtifactError(ValueError):
    """Artifact identity or metadata did not match the approved input."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ArtifactError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _plain(path: Path) -> None:
    require(
        not path.is_symlink() and path.is_file(), f"not a regular artifact: {path.name}"
    )
    require(0 < path.stat().st_size <= MAX_FILE, "artifact size outside budget")


def _text(stream: Any) -> bytes:
    data = stream.read(MAX_TEXT + 1)
    require(len(data) <= MAX_TEXT, "metadata exceeds budget")
    return data


def _members(names: list[str]) -> None:
    require(
        len(names) <= 100000 and len(names) == len(set(names)),
        "duplicate/oversized archive",
    )
    for name in names:
        path = PurePosixPath(name)
        require(
            not path.is_absolute() and ".." not in path.parts and "\\" not in name,
            "unsafe archive member",
        )


def _metadata(path: Path, package: str, version: str, kind: str) -> tuple[bytes, bytes]:
    stem = package.replace("-", "_") + "-" + version
    if kind == "wheel":
        with zipfile.ZipFile(path) as archive:
            _members(archive.namelist())
            require(
                all(
                    not stat.S_ISLNK(row.external_attr >> 16)
                    for row in archive.infolist()
                ),
                "linked wheel member",
            )
            metadata = f"{stem}.dist-info/METADATA"
            require(
                [n for n in archive.namelist() if n.endswith(".dist-info/METADATA")]
                == [metadata],
                "ambiguous wheel identity",
            )
            with archive.open(metadata) as stream:
                raw = _text(stream)
            with archive.open(f"{stem}.dist-info/licenses/LICENSE") as stream:
                license_bytes = _text(stream)
    else:
        with tarfile.open(path, "r:gz") as archive:
            members = archive.getmembers()
            _members([m.name for m in members])
            require(
                all(m.isfile() or m.isdir() for m in members), "nonregular sdist member"
            )
            require(
                all(PurePosixPath(m.name).parts[0] == stem for m in members),
                "foreign sdist root",
            )
            metadata_stream = archive.extractfile(f"{stem}/PKG-INFO")
            license_stream = archive.extractfile(f"{stem}/LICENSE")
            require(
                metadata_stream is not None and license_stream is not None,
                "missing sdist metadata/license",
            )
            assert metadata_stream is not None and license_stream is not None
            with metadata_stream, license_stream:
                raw, license_bytes = _text(metadata_stream), _text(license_stream)
    return raw, license_bytes


def inspect(
    path: Path, package: str, version: str, kind: str, license_hash: str
) -> None:
    raw, license_bytes = _metadata(path, package, version, kind)
    meta = BytesParser().parsebytes(raw)
    for header, expected in (
        ("Name", package),
        ("Version", version),
        ("License-Expression", LICENSE),
    ):
        require(meta.get_all(header) == [expected], f"metadata mismatch: {header}")
    python = meta.get_all("Requires-Python", [])
    require(
        len(python) == 1 and set(python[0].split(",")) == {">=3.13", "<3.15"},
        "Python support drift",
    )
    require(meta.get_all("License-File") == ["LICENSE"], "license inventory mismatch")
    require(
        hashlib.sha256(license_bytes).hexdigest() == license_hash,
        "packaged license bytes differ",
    )
    require(
        RIDER in license_bytes and b"no rights are granted" in license_bytes,
        "binding rider missing",
    )
    if package == "dspx-forge":
        dependencies = [
            r for r in meta.get_all("Requires-Dist", []) if r.startswith("dspx-core")
        ]
        major, minor, _ = map(int, version.split("."))
        expected = {f">={version}", f"<{major}.{minor + 1}.0"}
        require(
            len(dependencies) == 1
            and set(dependencies[0].removeprefix("dspx-core").split(",")) == expected,
            "paired Forge/Core compatibility mismatch",
        )


def _rows(versions: dict[str, str]) -> list[dict[str, str]]:
    require(set(versions) == set(PACKAGES), "package set mismatch")
    rows = []
    for package, version in sorted(versions.items()):
        require(
            isinstance(version, str)
            and re.fullmatch(r"0|[1-9][0-9]*", version.split(".")[0]) is not None
            and re.fullmatch(r"\d+\.\d+\.\d+", version) is not None,
            "stable numeric version required",
        )
        stem = package.replace("-", "_") + "-" + version
        for kind, suffix in (("wheel", "-py3-none-any.whl"), ("sdist", ".tar.gz")):
            rows.append(
                dict(
                    filename=stem + suffix, package=package, version=version, kind=kind
                )
            )
    require(
        len(set(versions.values())) == 1, "this workflow releases a coordinated pair"
    )
    return rows


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, "duplicate manifest key")
        result[key] = value
    return result


def load_and_verify(
    dist: Path, expected_commit: str, expected_manifest_sha256: str
) -> dict[str, Any]:
    manifest = dist / MANIFEST
    _plain(manifest)
    require(manifest.stat().st_size <= MAX_TEXT, "manifest exceeds budget")
    require(
        re.fullmatch(r"[a-f0-9]{40}", expected_commit) is not None,
        "invalid expected commit",
    )
    require(
        re.fullmatch(r"[a-f0-9]{64}", expected_manifest_sha256) is not None,
        "invalid expected manifest digest",
    )
    require(sha256(manifest) == expected_manifest_sha256, "manifest digest mismatch")
    data = json.loads(manifest.read_text(), object_pairs_hook=_unique)
    require(
        isinstance(data, dict)
        and set(data)
        == {
            "schema",
            "commit",
            "ak_scope_evidence",
            "versions",
            "license_sha256",
            "files",
        },
        "manifest shape mismatch",
    )
    require(
        data["schema"] == SCHEMA and data["commit"] == expected_commit,
        "source mismatch",
    )
    require(
        isinstance(data["ak_scope_evidence"], str)
        and re.fullmatch(r"AK-evidence:[1-9][0-9]*", data["ak_scope_evidence"])
        is not None,
        "host scope evidence reference missing",
    )
    require(
        isinstance(data["license_sha256"], str)
        and re.fullmatch(r"[a-f0-9]{64}", data["license_sha256"]) is not None,
        "invalid license digest",
    )
    require(isinstance(data["versions"], dict), "invalid versions")
    expected = _rows(data["versions"])
    require(
        isinstance(data["files"], list) and len(data["files"]) == 4,
        "file count mismatch",
    )
    require(
        {p.name for p in dist.iterdir()}
        == {MANIFEST, *(r["filename"] for r in expected)},
        "unexpected or missing distribution files",
    )
    for row, identity in zip(data["files"], expected, strict=True):
        require(
            isinstance(row, dict) and set(row) == {*identity, "sha256", "bytes"},
            "file row shape mismatch",
        )
        require(all(row[k] == v for k, v in identity.items()), "file identity mismatch")
        path = dist / identity["filename"]
        _plain(path)
        require(
            type(row["bytes"]) is int and row["bytes"] == path.stat().st_size,
            "file size mismatch",
        )
        require(row["sha256"] == sha256(path), "file digest mismatch")
        inspect(
            path,
            identity["package"],
            identity["version"],
            identity["kind"],
            data["license_sha256"],
        )
    return data


def create(dist: Path, repo: Path, commit: str, evidence: str) -> str:
    def git(*args: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(repo), *args], text=True
        ).strip()

    require(git("rev-parse", "HEAD") == commit, "wrong source checkout")
    require(
        git("status", "--porcelain") == "",
        "release build requires clean committed source",
    )
    versions = {}
    license_hash = sha256(repo / "LICENSE")
    for package, relative in PACKAGES.items():
        project = tomllib.loads((repo / relative / "pyproject.toml").read_text())[
            "project"
        ]
        require(
            project["name"] == package and project["license"] == LICENSE,
            "source package/license mismatch",
        )
        require(
            sha256(repo / relative / "LICENSE") == license_hash,
            "source license copies drifted",
        )
        versions[package] = project["version"]
    rows = []
    for identity in _rows(versions):
        path = dist / identity["filename"]
        _plain(path)
        rows.append(identity | {"sha256": sha256(path), "bytes": path.stat().st_size})
    data = dict(
        schema=SCHEMA,
        commit=commit,
        ak_scope_evidence=evidence,
        versions=versions,
        license_sha256=license_hash,
        files=rows,
    )
    with (dist / MANIFEST).open("x") as stream:
        stream.write(json.dumps(data, indent=2, sort_keys=True) + "\n")
    digest = sha256(dist / MANIFEST)
    load_and_verify(dist, commit, digest)
    return digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("create", "verify"))
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--scope-evidence")
    args = parser.parse_args()
    if args.mode == "create":
        require(
            args.repo is not None and args.scope_evidence is not None,
            "creation inputs missing",
        )
        digest = create(args.dist, args.repo, args.commit, args.scope_evidence)
        print(digest)
    else:
        require(args.manifest_sha256 is not None, "expected digest required")
        print(json.dumps(load_and_verify(args.dist, args.commit, args.manifest_sha256)))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# ---
# summary: "Builds and validates the fail-closed Core package release-evidence envelope."
# read_when:
#   - "Changing Core package provenance, SBOM/signature claims, or installed-wheel binding."
# ---

from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
from pathlib import Path
import tomllib
from typing import Any, cast

from core_release_evidence_io import (
    MAX_ARTIFACT_BYTES,
    MAX_JSON_BYTES,
    CoreReleaseEvidenceError,
    git as _git,
    is_sha256 as _is_sha256,
    sha256 as _sha256,
    stable_regular_bytes as _stable_regular_bytes,
    validate_sdist as _validate_sdist,
    wheel_metadata as _wheel_metadata,
    write_json as _write_json,
)


SCHEMA_VERSION = "dspx-core-release-evidence-v1"
INSTALLED_PROOF_SCHEMA = "dspx-installed-core-golden-path-proof-v2"
_TOP_LEVEL_FIELDS = {
    "schema_version",
    "status",
    "package",
    "source",
    "build_provenance",
    "subjects",
    "installed_wheel_proof",
    "sbom",
    "signature_verification",
    "claims",
}
_SUBJECT_FIELDS = {"role", "filename", "size", "sha256"}
_CLAIM_FIELDS = {
    "artifact_hashes_verified",
    "installed_wheel_bytes_bound",
    "source_commit_clean",
    "build_provenance_attested",
    "sbom_verified",
    "artifact_signature_verified",
    "technical_release_evidence_complete",
    "release_readiness",
    "release_authority",
    "publication_performed",
}


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CoreReleaseEvidenceError(f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def _exact_fields(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise CoreReleaseEvidenceError(
            f"{label} fields drift: expected {sorted(expected)!r}, "
            f"observed {sorted(value)!r}"
        )


def _expect(value: object, expected: object, label: str) -> None:
    if value != expected:
        raise CoreReleaseEvidenceError(
            f"{label} drift: expected {expected!r}, observed {value!r}"
        )


def _subject(*, role: str, path: Path, raw: bytes) -> dict[str, object]:
    return {
        "role": role,
        "filename": path.name,
        "size": len(raw),
        "sha256": _sha256(raw),
    }


def build_evidence(
    *,
    repo_root: Path,
    wheel_path: Path,
    sdist_path: Path,
    installed_proof_path: Path,
) -> dict[str, Any]:
    repo = repo_root.resolve()
    wheel_raw = _stable_regular_bytes(
        wheel_path, label="Core wheel", limit=MAX_ARTIFACT_BYTES
    )
    sdist_raw = _stable_regular_bytes(
        sdist_path, label="Core sdist", limit=MAX_ARTIFACT_BYTES
    )
    proof_raw = _stable_regular_bytes(
        installed_proof_path,
        label="installed Core proof",
        limit=MAX_JSON_BYTES,
    )
    try:
        proof = _mapping(json.loads(proof_raw), "installed Core proof")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoreReleaseEvidenceError(
            "installed Core proof is not valid JSON"
        ) from exc

    package_config = tomllib.loads(
        (repo / "packages/dspx-core/pyproject.toml").read_text(encoding="utf-8")
    )["project"]
    expected_name = str(package_config["name"])
    expected_version = str(package_config["version"])
    wheel_name, wheel_version = _wheel_metadata(wheel_raw)
    _expect(wheel_name, expected_name, "wheel package name")
    _expect(wheel_version, expected_version, "wheel package version")
    _validate_sdist(
        sdist_raw,
        expected_name=expected_name,
        expected_version=expected_version,
    )

    _expect(
        proof.get("schema_version"), INSTALLED_PROOF_SCHEMA, "installed proof schema"
    )
    _expect(proof.get("status"), "passed", "installed proof status")
    artifact = _mapping(proof.get("artifact_under_test"), "installed proof artifact")
    _exact_fields(
        artifact,
        {
            "filename",
            "sha256",
            "distribution_name",
            "distribution_version",
            "direct_url_bound",
        },
        "installed proof artifact",
    )
    wheel_hash = _sha256(wheel_raw)
    _expect(artifact.get("filename"), wheel_path.name, "installed wheel filename")
    _expect(artifact.get("sha256"), wheel_hash, "installed wheel hash")
    _expect(
        artifact.get("distribution_name"), expected_name, "installed distribution name"
    )
    _expect(
        artifact.get("distribution_version"),
        expected_version,
        "installed distribution version",
    )
    _expect(
        artifact.get("direct_url_bound"), True, "installed wheel direct URL binding"
    )

    commit = _git(repo, "rev-parse", "HEAD")
    dirty_lines = _git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    tree_clean = not dirty_lines
    source_status = (
        "commit_bound_clean_tree" if tree_clean else "working_tree_not_commit_bound"
    )
    subjects = [
        _subject(role="core-wheel", path=wheel_path, raw=wheel_raw),
        _subject(role="core-sdist", path=sdist_path, raw=sdist_raw),
    ]
    evidence: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "passed",
        "package": {
            "name": expected_name,
            "version": expected_version,
            "requires_python": str(package_config["requires-python"]),
        },
        "source": {
            "git_commit": commit,
            "tree_state": "clean" if tree_clean else "dirty",
            "commit_binding_status": source_status,
        },
        "build_provenance": {
            "status": "captured_local_statement_not_attested",
            "artifact_subjects_bound": True,
            "source_commit_recorded": True,
            "source_tree_clean": tree_clean,
        },
        "subjects": subjects,
        "installed_wheel_proof": {
            "schema_version": INSTALLED_PROOF_SCHEMA,
            "status": "passed",
            "sha256": _sha256(proof_raw),
            "wheel_sha256": wheel_hash,
            "direct_url_bound": True,
        },
        "sbom": {
            "status": "not_generated",
            "format": None,
            "sha256": None,
            "wheel_sha256": None,
            "completeness": "not_evaluated",
        },
        "signature_verification": {
            "status": "not_present_not_verified",
            "scheme": None,
            "signature_sha256": None,
            "subject_hashes_verified": False,
            "signer_identity_verified": False,
        },
        "claims": {
            "artifact_hashes_verified": True,
            "installed_wheel_bytes_bound": True,
            "source_commit_clean": tree_clean,
            "build_provenance_attested": False,
            "sbom_verified": False,
            "artifact_signature_verified": False,
            "technical_release_evidence_complete": False,
            "release_readiness": False,
            "release_authority": False,
            "publication_performed": False,
        },
    }
    validate_evidence(evidence)
    return evidence


def validate_evidence(value: object) -> dict[str, Any]:
    evidence = _mapping(value, "Core release evidence")
    _exact_fields(evidence, _TOP_LEVEL_FIELDS, "Core release evidence")
    _expect(evidence.get("schema_version"), SCHEMA_VERSION, "release evidence schema")
    _expect(evidence.get("status"), "passed", "release evidence status")

    package = _mapping(evidence.get("package"), "release evidence package")
    _exact_fields(
        package, {"name", "version", "requires_python"}, "release evidence package"
    )
    _expect(package.get("name"), "dspx-core", "release evidence package name")
    if not isinstance(package.get("version"), str) or not package["version"]:
        raise CoreReleaseEvidenceError(
            "release evidence package version must be non-empty"
        )

    source = _mapping(evidence.get("source"), "release evidence source")
    _exact_fields(
        source,
        {"git_commit", "tree_state", "commit_binding_status"},
        "release evidence source",
    )
    tree_state = source.get("tree_state")
    if tree_state not in {"clean", "dirty"}:
        raise CoreReleaseEvidenceError("release evidence source tree_state is invalid")
    expected_binding = (
        "commit_bound_clean_tree"
        if tree_state == "clean"
        else "working_tree_not_commit_bound"
    )
    _expect(
        source.get("commit_binding_status"), expected_binding, "source commit binding"
    )
    git_commit = source.get("git_commit")
    if (
        not isinstance(git_commit, str)
        or len(git_commit) not in {40, 64}
        or any(character not in "0123456789abcdef" for character in git_commit)
    ):
        raise CoreReleaseEvidenceError("release evidence Git commit is invalid")

    provenance = _mapping(evidence.get("build_provenance"), "build provenance")
    _exact_fields(
        provenance,
        {
            "status",
            "artifact_subjects_bound",
            "source_commit_recorded",
            "source_tree_clean",
        },
        "build provenance",
    )
    _expect(
        provenance.get("status"),
        "captured_local_statement_not_attested",
        "build provenance status",
    )
    _expect(provenance.get("artifact_subjects_bound"), True, "artifact subject binding")
    _expect(provenance.get("source_commit_recorded"), True, "source commit recording")
    _expect(
        provenance.get("source_tree_clean"), tree_state == "clean", "source tree truth"
    )

    subjects = evidence.get("subjects")
    if not isinstance(subjects, list) or len(subjects) != 2:
        raise CoreReleaseEvidenceError(
            "release evidence must contain wheel and sdist subjects"
        )
    roles: set[object] = set()
    hashes: dict[object, object] = {}
    for index, raw_subject in enumerate(subjects):
        subject = _mapping(raw_subject, f"release subject {index}")
        _exact_fields(subject, _SUBJECT_FIELDS, f"release subject {index}")
        role = subject.get("role")
        if role not in {"core-wheel", "core-sdist"} or role in roles:
            raise CoreReleaseEvidenceError(
                "release subject roles must be unique wheel and sdist"
            )
        roles.add(role)
        digest = subject.get("sha256")
        if not _is_sha256(digest):
            raise CoreReleaseEvidenceError(f"release subject {index} hash is invalid")
        if not isinstance(subject.get("size"), int) or subject["size"] <= 0:
            raise CoreReleaseEvidenceError(f"release subject {index} size is invalid")
        hashes[role] = digest

    installed = _mapping(evidence.get("installed_wheel_proof"), "installed wheel proof")
    _exact_fields(
        installed,
        {"schema_version", "status", "sha256", "wheel_sha256", "direct_url_bound"},
        "installed wheel proof",
    )
    _expect(
        installed.get("schema_version"),
        INSTALLED_PROOF_SCHEMA,
        "installed proof schema",
    )
    _expect(installed.get("status"), "passed", "installed proof status")
    if not _is_sha256(installed.get("sha256")):
        raise CoreReleaseEvidenceError("installed proof hash is invalid")
    if not _is_sha256(installed.get("wheel_sha256")):
        raise CoreReleaseEvidenceError("installed proof wheel hash is invalid")
    _expect(
        installed.get("wheel_sha256"),
        hashes["core-wheel"],
        "installed proof wheel binding",
    )
    _expect(
        installed.get("direct_url_bound"), True, "installed proof direct URL binding"
    )

    sbom = _mapping(evidence.get("sbom"), "release evidence SBOM")
    _exact_fields(
        sbom,
        {"status", "format", "sha256", "wheel_sha256", "completeness"},
        "release evidence SBOM",
    )
    _expect(sbom.get("status"), "not_generated", "SBOM status")
    _expect(sbom.get("format"), None, "SBOM format")
    _expect(sbom.get("sha256"), None, "SBOM hash")
    _expect(sbom.get("wheel_sha256"), None, "SBOM wheel binding")
    _expect(sbom.get("completeness"), "not_evaluated", "SBOM completeness")

    signature = _mapping(
        evidence.get("signature_verification"), "signature verification"
    )
    _exact_fields(
        signature,
        {
            "status",
            "scheme",
            "signature_sha256",
            "subject_hashes_verified",
            "signer_identity_verified",
        },
        "signature verification",
    )
    _expect(signature.get("status"), "not_present_not_verified", "signature status")
    _expect(signature.get("scheme"), None, "signature scheme")
    _expect(signature.get("signature_sha256"), None, "signature hash")
    _expect(
        signature.get("subject_hashes_verified"), False, "signature subject binding"
    )
    _expect(signature.get("signer_identity_verified"), False, "signer identity")

    claims = _mapping(evidence.get("claims"), "release evidence claims")
    _exact_fields(claims, _CLAIM_FIELDS, "release evidence claims")
    expected_claims = {
        "artifact_hashes_verified": True,
        "installed_wheel_bytes_bound": True,
        "source_commit_clean": tree_state == "clean",
        "build_provenance_attested": False,
        "sbom_verified": False,
        "artifact_signature_verified": False,
        "technical_release_evidence_complete": False,
        "release_readiness": False,
        "release_authority": False,
        "publication_performed": False,
    }
    _expect(dict(claims), expected_claims, "release evidence claim matrix")
    return dict(evidence)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--sdist", type=Path, required=True)
    parser.add_argument("--installed-proof", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    evidence = build_evidence(
        repo_root=args.repo_root,
        wheel_path=args.wheel,
        sdist_path=args.sdist,
        installed_proof_path=args.installed_proof,
    )
    _write_json(args.out, evidence)
    print(json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CoreReleaseEvidenceError as exc:
        raise SystemExit(f"Core release evidence failed: {exc}") from exc

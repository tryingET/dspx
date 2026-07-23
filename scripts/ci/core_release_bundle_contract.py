# ---
# summary: "Defines and validates the retained unsigned Core release bundle contract."
# read_when:
#   - "Changing retained Core bundle schemas, canonical ZIP closure, or provenance claims."
# ---

from __future__ import annotations

from collections.abc import Mapping
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
from typing import Any, cast
import zipfile

from core_release_evidence import validate_evidence
from core_release_evidence_io import (
    MAX_ARTIFACT_BYTES,
    MAX_JSON_BYTES,
    CoreReleaseEvidenceError,
    sha256 as _sha256,
    stable_regular_bytes as _stable_regular_bytes,
    validate_sdist as _validate_sdist,
    wheel_metadata as _wheel_metadata,
)
from core_release_proof_contract import validate_installed_proof

BUNDLE_SCHEMA = "dspx-core-release-bundle-v1"
PROVENANCE_SCHEMA = "dspx-core-local-build-provenance-v1"
_RELEASE_EVIDENCE_NAME = "dspx-core-release-evidence.json"
_INSTALLED_PROOF_NAME = "installed-core-golden-path-proof.json"
_PROVENANCE_NAME = "local-build-provenance.json"
_MANIFEST_NAME = "bundle-manifest.json"
_FIXED_NAMES = {
    _RELEASE_EVIDENCE_NAME,
    _INSTALLED_PROOF_NAME,
    _PROVENANCE_NAME,
    _MANIFEST_NAME,
}
_FILE_ROLES = {
    "core-wheel",
    "core-sdist",
    "installed-proof",
    "release-evidence",
    "local-build-provenance",
}
_BUNDLE_CLAIMS = {
    "artifact_bytes_retained": True,
    "installed_proof_retained": True,
    "release_evidence_retained": True,
    "local_provenance_retained": True,
    "build_provenance_attested": False,
    "sbom_generated": False,
    "sbom_verified": False,
    "signer_policy_supplied": False,
    "artifact_signature_verified": False,
    "technical_release_evidence_complete": False,
    "release_readiness": False,
    "release_authority": False,
    "publication_performed": False,
}
_PROVENANCE_CLAIMS = {
    "artifact_subjects_bound": True,
    "source_commit_recorded": True,
    "builder_identity_verified": False,
    "attestation_verified": False,
    "release_readiness": False,
    "release_authority": False,
}
_MAX_BUNDLE_BYTES = (2 * MAX_ARTIFACT_BYTES) + (4 * MAX_JSON_BYTES)


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CoreReleaseEvidenceError(f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise CoreReleaseEvidenceError(
            f"{label} fields drift: expected {sorted(fields)!r}, observed {sorted(value)!r}"
        )


def _json_object(raw: bytes, label: str) -> Mapping[str, Any]:
    if len(raw) > MAX_JSON_BYTES:
        raise CoreReleaseEvidenceError(f"{label} exceeds {MAX_JSON_BYTES} bytes")
    try:
        return _mapping(json.loads(raw), label)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoreReleaseEvidenceError(f"{label} is not valid JSON") from exc


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def _safe_member_name(name: str, label: str) -> str:
    if (
        not name
        or "\\" in name
        or name.startswith("/")
        or PurePosixPath(name).name != name
        or name in {".", ".."}
    ):
        raise CoreReleaseEvidenceError(f"{label} filename is unsafe")
    return name


def _release_subjects(release: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    subjects = release.get("subjects")
    if not isinstance(subjects, list):
        raise CoreReleaseEvidenceError("release evidence subjects must be a list")
    by_role: dict[str, Mapping[str, Any]] = {}
    for index, raw_subject in enumerate(subjects):
        subject = _mapping(raw_subject, f"release subject {index}")
        role = subject.get("role")
        if not isinstance(role, str) or role in by_role:
            raise CoreReleaseEvidenceError("release evidence subject roles are invalid")
        by_role[role] = subject
    return by_role


def _provenance_statement(release: Mapping[str, Any]) -> dict[str, Any]:
    subjects = _release_subjects(release)
    return {
        "schema_version": PROVENANCE_SCHEMA,
        "status": "local_unauthenticated_not_attested",
        "package": dict(_mapping(release.get("package"), "release package")),
        "source": dict(_mapping(release.get("source"), "release source")),
        "subjects": [dict(subjects[role]) for role in ("core-wheel", "core-sdist")],
        "observations": {
            "release_evidence_schema": release.get("schema_version"),
            "release_evidence_status": release.get("status"),
            "installed_proof_schema": _mapping(
                release.get("installed_wheel_proof"), "installed proof"
            ).get("schema_version"),
            "installed_proof_status": _mapping(
                release.get("installed_wheel_proof"), "installed proof"
            ).get("status"),
        },
        "claims": dict(_PROVENANCE_CLAIMS),
    }


def _file_entry(*, role: str, filename: str, raw: bytes) -> dict[str, object]:
    return {
        "role": role,
        "filename": filename,
        "size": len(raw),
        "sha256": _sha256(raw),
    }


def _manifest(
    release: Mapping[str, Any], members: Mapping[str, tuple[str, bytes]]
) -> dict[str, Any]:
    files = [
        _file_entry(role=role, filename=filename, raw=raw)
        for filename, (role, raw) in members.items()
    ]
    files.sort(key=lambda item: str(item["role"]))
    return {
        "schema_version": BUNDLE_SCHEMA,
        "status": "passed",
        "package": dict(_mapping(release.get("package"), "release package")),
        "source": dict(_mapping(release.get("source"), "release source")),
        "archive": {
            "format": "zip",
            "compression": "stored",
            "manifest_self_hash": False,
        },
        "files": files,
        "claims": dict(_BUNDLE_CLAIMS),
    }


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = 0o100600 << 16
    return info


def _archive_bytes(members: Mapping[str, bytes]) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(members):
            archive.writestr(_zip_info(name), members[name])
    return buffer.getvalue()


def _validate_provenance(
    value: object,
    *,
    release: Mapping[str, Any],
) -> Mapping[str, Any]:
    provenance = _mapping(value, "local build provenance")
    _exact(
        provenance,
        {
            "schema_version",
            "status",
            "package",
            "source",
            "subjects",
            "observations",
            "claims",
        },
        "local build provenance",
    )
    if provenance.get("schema_version") != PROVENANCE_SCHEMA:
        raise CoreReleaseEvidenceError("local build provenance schema drift")
    if provenance.get("status") != "local_unauthenticated_not_attested":
        raise CoreReleaseEvidenceError("local build provenance status drift")
    if provenance.get("package") != release.get("package"):
        raise CoreReleaseEvidenceError("local build provenance package drift")
    if provenance.get("source") != release.get("source"):
        raise CoreReleaseEvidenceError("local build provenance source drift")
    expected_subjects = [
        dict(_release_subjects(release)[role]) for role in ("core-wheel", "core-sdist")
    ]
    if provenance.get("subjects") != expected_subjects:
        raise CoreReleaseEvidenceError("local build provenance subject drift")
    observations = _mapping(provenance.get("observations"), "provenance observations")
    expected_observations = {
        "release_evidence_schema": release.get("schema_version"),
        "release_evidence_status": release.get("status"),
        "installed_proof_schema": _mapping(
            release.get("installed_wheel_proof"), "installed proof"
        ).get("schema_version"),
        "installed_proof_status": _mapping(
            release.get("installed_wheel_proof"), "installed proof"
        ).get("status"),
    }
    if dict(observations) != expected_observations:
        raise CoreReleaseEvidenceError("local build provenance observation drift")
    claims = _mapping(provenance.get("claims"), "provenance claims")
    if dict(claims) != _PROVENANCE_CLAIMS:
        raise CoreReleaseEvidenceError("local build provenance claim drift")
    return provenance


def _validate_bundle_raw(raw: bytes) -> dict[str, Any]:
    if len(raw) > _MAX_BUNDLE_BYTES:
        raise CoreReleaseEvidenceError(
            f"Core release bundle exceeds {_MAX_BUNDLE_BYTES} bytes"
        )
    try:
        archive = zipfile.ZipFile(BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise CoreReleaseEvidenceError(
            "Core release bundle is not a valid ZIP"
        ) from exc
    with archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise CoreReleaseEvidenceError("Core release bundle has duplicate members")
        for info in infos:
            _safe_member_name(info.filename, "bundle member")
            if info.is_dir() or info.compress_type != zipfile.ZIP_STORED:
                raise CoreReleaseEvidenceError("Core release bundle member type drift")
            limit = (
                MAX_ARTIFACT_BYTES
                if info.filename.endswith((".whl", ".tar.gz"))
                else MAX_JSON_BYTES
            )
            if info.file_size > limit or info.compress_size != info.file_size:
                raise CoreReleaseEvidenceError("Core release bundle member size drift")
        if _MANIFEST_NAME not in names:
            raise CoreReleaseEvidenceError("Core release bundle lacks its manifest")
        payloads = {name: archive.read(name) for name in names}
    if raw != _archive_bytes(payloads):
        raise CoreReleaseEvidenceError(
            "Core release bundle archive is not canonical or has trailing data"
        )

    manifest = _json_object(payloads[_MANIFEST_NAME], "bundle manifest")
    _exact(
        manifest,
        {"schema_version", "status", "package", "source", "archive", "files", "claims"},
        "bundle manifest",
    )
    if (
        manifest.get("schema_version") != BUNDLE_SCHEMA
        or manifest.get("status") != "passed"
    ):
        raise CoreReleaseEvidenceError("Core release bundle status drift")
    if manifest.get("archive") != {
        "format": "zip",
        "compression": "stored",
        "manifest_self_hash": False,
    }:
        raise CoreReleaseEvidenceError("Core release bundle archive contract drift")
    claims = _mapping(manifest.get("claims"), "bundle claims")
    if dict(claims) != _BUNDLE_CLAIMS:
        raise CoreReleaseEvidenceError("Core release bundle claim drift")
    files = manifest.get("files")
    if not isinstance(files, list) or len(files) != len(_FILE_ROLES):
        raise CoreReleaseEvidenceError("Core release bundle file inventory drift")
    by_role: dict[str, Mapping[str, Any]] = {}
    inventory_names: set[str] = set()
    for index, raw_entry in enumerate(files):
        entry = _mapping(raw_entry, f"bundle file {index}")
        _exact(entry, {"role", "filename", "size", "sha256"}, f"bundle file {index}")
        role = entry.get("role")
        filename = entry.get("filename")
        if not isinstance(role, str) or role not in _FILE_ROLES or role in by_role:
            raise CoreReleaseEvidenceError("Core release bundle file role drift")
        if not isinstance(filename, str):
            raise CoreReleaseEvidenceError("Core release bundle filename drift")
        _safe_member_name(filename, f"bundle file {index}")
        if filename in inventory_names or filename == _MANIFEST_NAME:
            raise CoreReleaseEvidenceError("Core release bundle filename collision")
        if filename not in payloads:
            raise CoreReleaseEvidenceError("Core release bundle member is missing")
        member = payloads[filename]
        if entry.get("size") != len(member) or entry.get("sha256") != _sha256(member):
            raise CoreReleaseEvidenceError("Core release bundle member hash drift")
        by_role[role] = entry
        inventory_names.add(filename)
    if set(by_role) != _FILE_ROLES or set(payloads) != inventory_names | {
        _MANIFEST_NAME
    }:
        raise CoreReleaseEvidenceError("Core release bundle closure drift")
    if by_role["installed-proof"]["filename"] != _INSTALLED_PROOF_NAME:
        raise CoreReleaseEvidenceError("Core release bundle installed-proof name drift")
    if by_role["release-evidence"]["filename"] != _RELEASE_EVIDENCE_NAME:
        raise CoreReleaseEvidenceError(
            "Core release bundle release-evidence name drift"
        )
    if by_role["local-build-provenance"]["filename"] != _PROVENANCE_NAME:
        raise CoreReleaseEvidenceError("Core release bundle provenance name drift")

    release = _json_object(payloads[_RELEASE_EVIDENCE_NAME], "Core release evidence")
    validate_evidence(release)
    if manifest.get("package") != release.get("package") or manifest.get(
        "source"
    ) != release.get("source"):
        raise CoreReleaseEvidenceError("Core release bundle identity drift")
    _validate_provenance(
        _json_object(payloads[_PROVENANCE_NAME], "local build provenance"),
        release=release,
    )
    subjects = _release_subjects(release)
    wheel_entry = by_role["core-wheel"]
    sdist_entry = by_role["core-sdist"]
    for role, entry in (("core-wheel", wheel_entry), ("core-sdist", sdist_entry)):
        if dict(subjects[role]) != dict(entry):
            raise CoreReleaseEvidenceError(f"Core release bundle {role} binding drift")
    wheel_raw = payloads[cast(str, wheel_entry["filename"])]
    sdist_raw = payloads[cast(str, sdist_entry["filename"])]
    package = _mapping(release.get("package"), "release package")
    if _wheel_metadata(wheel_raw) != (package.get("name"), package.get("version")):
        raise CoreReleaseEvidenceError("Core release bundle wheel metadata drift")
    _validate_sdist(
        sdist_raw,
        expected_name=cast(str, package["name"]),
        expected_version=cast(str, package["version"]),
    )
    proof_raw = payloads[_INSTALLED_PROOF_NAME]
    installed = _mapping(
        release.get("installed_wheel_proof"), "installed proof summary"
    )
    if installed.get("sha256") != _sha256(proof_raw):
        raise CoreReleaseEvidenceError("Core release bundle installed proof hash drift")
    validate_installed_proof(
        _json_object(proof_raw, "installed Core proof"),
        expected_name=cast(str, package["name"]),
        expected_version=cast(str, package["version"]),
        expected_wheel_filename=cast(str, wheel_entry["filename"]),
        expected_wheel_sha256=_sha256(wheel_raw),
    )
    return dict(manifest)


def validate_bundle(path: Path) -> dict[str, Any]:
    raw = _stable_regular_bytes(
        path, label="Core release bundle", limit=_MAX_BUNDLE_BYTES
    )
    return _validate_bundle_raw(raw)

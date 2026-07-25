#!/usr/bin/env python3
# ---
# summary: "Generates and verifies a deterministic CycloneDX SBOM for the exact Core wheel."
# read_when:
#   - "Changing Core wheel SBOM generation, RECORD closure, or release-evidence binding."
# ---

from __future__ import annotations

import argparse
import base64
import binascii
import csv
from email.parser import BytesParser
from email.policy import default as email_policy
import hashlib
from io import BytesIO, TextIOWrapper
import json
from pathlib import Path, PurePosixPath
import re
import stat
import struct
from typing import Any, cast
from urllib.parse import quote
import uuid
import zipfile
import zlib

from jsonschema import Draft7Validator
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import (
    InvalidWheelFilename,
    canonicalize_name,
    parse_wheel_filename,
)
from packaging.version import InvalidVersion, Version
from referencing import Registry, Resource

from core_release_evidence_io import (
    MAX_ARTIFACT_BYTES,
    MAX_JSON_BYTES,
    CoreReleaseEvidenceError,
    sha256 as _sha256,
    stable_regular_bytes as _stable_regular_bytes,
    write_json as _write_json,
)

BOM_FORMAT = "CycloneDX"
SPEC_VERSION = "1.6"
SBOM_FORMAT = "CycloneDX 1.6 JSON"
SBOM_COMPLETENESS = "wheel_payload_and_declared_direct_dependencies"
_SCOPE = "exact-wheel-payload-and-declared-direct-dependencies"
_RECORD_HASH = re.compile(r"^[A-Za-z0-9_-]{43}$")
_MAX_WHEEL_FILES = 20_000
_MAX_RECORD_ROWS = _MAX_WHEEL_FILES
_MAX_CENTRAL_DIRECTORY_BYTES = 16 * 1024 * 1024
_EOCD_SIGNATURE = b"PK\x05\x06"
_EOCD_SIZE = 22


def _preflight_zip_directory(raw: bytes) -> None:
    search_start = max(0, len(raw) - (65_535 + _EOCD_SIZE))
    position = len(raw)
    fields: tuple[int, int, int, int, int, int, int] | None = None
    while True:
        position = raw.rfind(_EOCD_SIGNATURE, search_start, position)
        if position < 0:
            break
        if position + _EOCD_SIZE <= len(raw):
            unpacked = struct.unpack_from("<4H2LH", raw, position + 4)
            comment_length = unpacked[-1]
            if position + _EOCD_SIZE + comment_length == len(raw):
                fields = unpacked
                break
        if position == search_start:
            break
    if fields is None:
        raise CoreReleaseEvidenceError("Core wheel ZIP directory is invalid")
    (
        disk_number,
        directory_disk,
        entries_on_disk,
        total_entries,
        directory_size,
        directory_offset,
        _comment_length,
    ) = fields
    if (
        disk_number != 0
        or directory_disk != 0
        or entries_on_disk != total_entries
        or total_entries in {0xFFFF}
        or directory_size == 0xFFFFFFFF
        or directory_offset == 0xFFFFFFFF
    ):
        raise CoreReleaseEvidenceError(
            "Core wheel ZIP64 or multi-disk directory is unsupported"
        )
    if total_entries > _MAX_WHEEL_FILES:
        raise CoreReleaseEvidenceError("Core wheel ZIP entry count is oversized")
    if directory_size > _MAX_CENTRAL_DIRECTORY_BYTES:
        raise CoreReleaseEvidenceError("Core wheel ZIP directory is oversized")
    if directory_offset + directory_size > position:
        raise CoreReleaseEvidenceError("Core wheel ZIP directory bounds are invalid")


def _read_member(
    archive: zipfile.ZipFile,
    path: PurePosixPath,
    *,
    label: str,
) -> bytes:
    try:
        return archive.read(path.as_posix())
    except (
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
        RuntimeError,
        OSError,
        EOFError,
        zlib.error,
    ) as exc:
        raise CoreReleaseEvidenceError(f"{label} cannot be read safely") from exc


_MAX_REQUIREMENTS = 2_000
_MAX_REQUIREMENT_CHARS = 4_096
_SCHEMA_ROOT = Path(__file__).with_name("schemas") / "cyclonedx-1.6"
_SCHEMA_HASHES = {
    "bom-1.6.schema.json": "3e92dddbc30cf7f6a02b80f0942b1a4cfd4fb1c26f1dfc4310afa9d613cafb93",
    "jsf-0.82.schema.json": "8bae002c25e723db7ee1f26afde680ae1a2b1a8f6b4b4b0fd65dc3becb090aae",
    "spdx.schema.json": "baa9d3bd1ed57b6751b0887edead6b5063ff53ff7429cf85d476c6c94af0166e",
}


def _official_schema_validator() -> Any:
    documents: dict[str, dict[str, Any]] = {}
    registry = Registry()
    for filename, expected_hash in _SCHEMA_HASHES.items():
        raw = _stable_regular_bytes(
            _SCHEMA_ROOT / filename,
            label=f"pinned CycloneDX schema {filename}",
            limit=512 * 1024,
        )
        if _sha256(raw) != expected_hash:
            raise CoreReleaseEvidenceError(
                f"pinned CycloneDX schema hash drift: {filename}"
            )
        try:
            document = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CoreReleaseEvidenceError(
                f"pinned CycloneDX schema is invalid: {filename}"
            ) from exc
        if not isinstance(document, dict) or not isinstance(document.get("$id"), str):
            raise CoreReleaseEvidenceError(
                f"pinned CycloneDX schema identity is invalid: {filename}"
            )
        documents[filename] = cast(dict[str, Any], document)
        registry = registry.with_resource(
            cast(str, document["$id"]), Resource.from_contents(document)
        )
    schema = documents["bom-1.6.schema.json"]
    Draft7Validator.check_schema(schema)
    return Draft7Validator(schema, registry=registry)


def _validate_official_schema(value: dict[str, Any]) -> None:
    errors = sorted(
        _official_schema_validator().iter_errors(value),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = ".".join(str(part) for part in error.absolute_path) or "<root>"
        raise CoreReleaseEvidenceError(
            f"CycloneDX 1.6 schema validation failed at {path}: {error.message}"
        )


def _safe_path(value: str) -> PurePosixPath:
    if not value or "\\" in value or value.startswith("/"):
        raise CoreReleaseEvidenceError("Core wheel contains an unsafe path")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise CoreReleaseEvidenceError("Core wheel contains an unsafe path")
    return PurePosixPath(*parts)


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def _decode_record_hash(value: str, *, path: PurePosixPath) -> bytes:
    try:
        algorithm, encoded = value.split("=", 1)
    except ValueError as exc:
        raise CoreReleaseEvidenceError(
            f"Core wheel RECORD hash is malformed for {path.as_posix()}"
        ) from exc
    if algorithm != "sha256":
        raise CoreReleaseEvidenceError(
            f"Core wheel RECORD hash algorithm is unsupported for {path.as_posix()}"
        )
    if _RECORD_HASH.fullmatch(encoded) is None:
        raise CoreReleaseEvidenceError(
            f"Core wheel RECORD hash is malformed for {path.as_posix()}"
        )
    try:
        decoded = base64.b64decode(encoded + "=", altchars=b"-_", validate=True)
    except (ValueError, binascii.Error) as exc:
        raise CoreReleaseEvidenceError(
            f"Core wheel RECORD hash is malformed for {path.as_posix()}"
        ) from exc
    canonical = base64.urlsafe_b64encode(decoded).rstrip(b"=").decode()
    if len(decoded) != 32 or canonical != encoded:
        raise CoreReleaseEvidenceError(
            f"Core wheel RECORD hash is malformed for {path.as_posix()}"
        )
    return decoded


def _dependency_row(requirement: str) -> dict[str, str]:
    if (
        not requirement
        or len(requirement) > _MAX_REQUIREMENT_CHARS
        or any(ord(character) < 32 for character in requirement)
    ):
        raise CoreReleaseEvidenceError("Core wheel Requires-Dist value is invalid")
    try:
        parsed = Requirement(requirement)
    except InvalidRequirement as exc:
        raise CoreReleaseEvidenceError(
            "Core wheel Requires-Dist value is invalid"
        ) from exc
    canonical_identity = json.dumps(
        {
            "name": canonicalize_name(parsed.name),
            "extras": sorted(canonicalize_name(extra) for extra in parsed.extras),
            "specifier": str(parsed.specifier),
            "url": parsed.url,
            "marker": str(parsed.marker) if parsed.marker is not None else None,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "name": canonicalize_name(parsed.name),
        "requirement": str(parsed),
        "identity": canonical_identity,
    }


def _wheel_inventory(raw: bytes, *, wheel_filename: str) -> dict[str, Any]:
    _preflight_zip_directory(raw)
    try:
        archive = zipfile.ZipFile(BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise CoreReleaseEvidenceError("Core wheel archive is invalid") from exc
    with archive:
        files: dict[PurePosixPath, zipfile.ZipInfo] = {}
        total_size = 0
        for info in archive.infolist():
            raw_name = info.filename[:-1] if info.is_dir() else info.filename
            path = _safe_path(raw_name)
            mode = (info.external_attr >> 16) & 0o170000
            if stat.S_ISLNK(mode) or (
                mode and not (stat.S_ISREG(mode) or info.is_dir())
            ):
                raise CoreReleaseEvidenceError(
                    "Core wheel contains an unsafe member type"
                )
            if info.flag_bits & 0x1:
                raise CoreReleaseEvidenceError(
                    "Core wheel contains an encrypted member"
                )
            if info.is_dir():
                continue
            if path in files:
                raise CoreReleaseEvidenceError("Core wheel archive path is duplicated")
            files[path] = info
            total_size += info.file_size
            if len(files) > _MAX_WHEEL_FILES or total_size > MAX_ARTIFACT_BYTES:
                raise CoreReleaseEvidenceError(
                    "Core wheel payload inventory is oversized"
                )
        metadata_paths = [
            path for path in files if path.as_posix().endswith(".dist-info/METADATA")
        ]
        record_paths = [
            path for path in files if path.as_posix().endswith(".dist-info/RECORD")
        ]
        if len(metadata_paths) != 1 or len(record_paths) != 1:
            raise CoreReleaseEvidenceError(
                "Core wheel must contain exactly one METADATA and RECORD"
            )
        metadata_path = metadata_paths[0]
        record_path = record_paths[0]
        if (
            metadata_path.parent != record_path.parent
            or len(metadata_path.parts) != 2
            or len(record_path.parts) != 2
        ):
            raise CoreReleaseEvidenceError(
                "Core wheel METADATA and RECORD dist-info identity drift"
            )
        if files[metadata_path].file_size > MAX_JSON_BYTES:
            raise CoreReleaseEvidenceError("Core wheel METADATA is oversized")
        metadata_raw = _read_member(archive, metadata_path, label="Core wheel METADATA")
        metadata = BytesParser(policy=email_policy).parsebytes(metadata_raw)
        package_names = metadata.get_all("Name", [])
        package_versions = metadata.get_all("Version", [])
        if metadata.defects or len(package_names) != 1 or len(package_versions) != 1:
            raise CoreReleaseEvidenceError(
                "Core wheel metadata identity headers are ambiguous or malformed"
            )
        package_name = str(package_names[0])
        package_version = str(package_versions[0])
        if not package_name or not package_version:
            raise CoreReleaseEvidenceError("Core wheel metadata lacks name or version")
        try:
            filename_name, filename_version, _build, _tags = parse_wheel_filename(
                wheel_filename
            )
            metadata_version = Version(package_version)
        except (InvalidWheelFilename, InvalidVersion) as exc:
            raise CoreReleaseEvidenceError(
                "Core wheel filename or metadata identity is invalid"
            ) from exc
        if (
            str(filename_name) != canonicalize_name(package_name)
            or filename_version != metadata_version
        ):
            raise CoreReleaseEvidenceError(
                "Core wheel filename and metadata identity drift"
            )
        filename_parts = wheel_filename[:-4].split("-")
        expected_dist_info = f"{filename_parts[0]}-{filename_parts[1]}.dist-info"
        if metadata_path.parent.as_posix() != expected_dist_info:
            raise CoreReleaseEvidenceError(
                "Core wheel dist-info directory identity drift"
            )
        requirements = [str(value) for value in metadata.get_all("Requires-Dist", [])]
        if len(requirements) > _MAX_REQUIREMENTS:
            raise CoreReleaseEvidenceError(
                "Core wheel dependency inventory is oversized"
            )
        dependency_rows: list[dict[str, str]] = []
        seen_requirements: set[str] = set()
        for requirement in requirements:
            dependency = _dependency_row(requirement)
            canonical_requirement = dependency["identity"]
            if canonical_requirement in seen_requirements:
                raise CoreReleaseEvidenceError(
                    "Core wheel Requires-Dist declaration is duplicated"
                )
            seen_requirements.add(canonical_requirement)
            dependency_rows.append(dependency)
        dependency_rows.sort(key=lambda row: (row["name"], row["requirement"]))

        if files[record_path].file_size > MAX_JSON_BYTES:
            raise CoreReleaseEvidenceError("Core wheel RECORD is oversized")
        record_raw = _read_member(archive, record_path, label="Core wheel RECORD")
        seen: set[PurePosixPath] = set()
        self_rows = 0
        try:
            reader = csv.reader(
                TextIOWrapper(BytesIO(record_raw), encoding="utf-8", newline="")
            )
            for row_index, row in enumerate(reader):
                if row_index >= _MAX_RECORD_ROWS:
                    raise CoreReleaseEvidenceError(
                        "Core wheel RECORD row count is oversized"
                    )
                if len(row) != 3:
                    raise CoreReleaseEvidenceError("Core wheel RECORD row is malformed")
                path = _safe_path(row[0])
                if path in seen:
                    raise CoreReleaseEvidenceError(
                        "Core wheel RECORD path is duplicated"
                    )
                seen.add(path)
                if path not in files:
                    raise CoreReleaseEvidenceError(
                        "Core wheel RECORD names a missing file"
                    )
                if path == record_path:
                    self_rows += 1
                    if row[1] or row[2]:
                        raise CoreReleaseEvidenceError(
                            "Core wheel RECORD self-row is malformed"
                        )
                    continue
                try:
                    expected_size = int(row[2])
                except ValueError as exc:
                    raise CoreReleaseEvidenceError(
                        "Core wheel RECORD size is invalid"
                    ) from exc
                if isinstance(expected_size, bool) or expected_size < 0:
                    raise CoreReleaseEvidenceError("Core wheel RECORD size is invalid")
                member_raw = _read_member(
                    archive, path, label=f"Core wheel member {path.as_posix()}"
                )
                if len(member_raw) != expected_size:
                    raise CoreReleaseEvidenceError(
                        f"Core wheel RECORD size drift: {path.as_posix()}"
                    )
                if (
                    _decode_record_hash(row[1], path=path)
                    != hashlib.sha256(member_raw).digest()
                ):
                    raise CoreReleaseEvidenceError(
                        f"Core wheel RECORD hash drift: {path.as_posix()}"
                    )
        except (UnicodeDecodeError, csv.Error) as exc:
            raise CoreReleaseEvidenceError("Core wheel RECORD is invalid") from exc
        if self_rows != 1 or seen != set(files):
            raise CoreReleaseEvidenceError(
                "Core wheel RECORD does not close the archive"
            )

        payload_rows = []
        for path in sorted(files, key=lambda item: item.as_posix()):
            member_raw = _read_member(
                archive, path, label=f"Core wheel member {path.as_posix()}"
            )
            payload_rows.append(
                {
                    "path": path.as_posix(),
                    "size": len(member_raw),
                    "sha256": _sha256(member_raw),
                }
            )
    return {
        "package_name": package_name,
        "package_version": package_version,
        "dependencies": dependency_rows,
        "payloads": payload_rows,
    }


def _purl_name(value: str) -> str:
    return quote(re.sub(r"[-_.]+", "-", value).lower(), safe="-")


def build_sbom(*, wheel_raw: bytes, wheel_filename: str) -> dict[str, Any]:
    if not wheel_filename or PurePosixPath(wheel_filename).name != wheel_filename:
        raise CoreReleaseEvidenceError("Core wheel filename is unsafe")
    inventory = _wheel_inventory(wheel_raw, wheel_filename=wheel_filename)
    package_name = cast(str, inventory["package_name"])
    package_version = cast(str, inventory["package_version"])
    wheel_hash = _sha256(wheel_raw)
    root_ref = (
        f"pkg:pypi/{_purl_name(package_name)}@{quote(package_version, safe='.-_')}"
    )
    components: list[dict[str, Any]] = []
    for payload in cast(list[dict[str, Any]], inventory["payloads"]):
        path = cast(str, payload["path"])
        components.append(
            {
                "type": "file",
                "bom-ref": f"urn:dspx:wheel-file:{hashlib.sha256(path.encode()).hexdigest()}",
                "name": path,
                "hashes": [{"alg": "SHA-256", "content": payload["sha256"]}],
                "properties": [
                    {"name": "dspx:wheel:file-size", "value": str(payload["size"])}
                ],
            }
        )
    dependency_refs: list[str] = []
    for dependency in cast(list[dict[str, str]], inventory["dependencies"]):
        requirement = dependency["requirement"]
        ref = f"urn:dspx:requires-dist:{hashlib.sha256(dependency['identity'].encode()).hexdigest()}"
        dependency_refs.append(ref)
        components.append(
            {
                "type": "library",
                "bom-ref": ref,
                "name": dependency["name"],
                "purl": f"pkg:pypi/{_purl_name(dependency['name'])}",
                "properties": [
                    {"name": "dspx:python:requires-dist", "value": requirement}
                ],
            }
        )
    components.sort(key=lambda component: cast(str, component["bom-ref"]))
    dependencies = [{"ref": root_ref, "dependsOn": sorted(dependency_refs)}]
    dependencies.extend(
        {"ref": ref, "dependsOn": []} for ref in sorted(dependency_refs)
    )
    sbom = {
        "$schema": "http://cyclonedx.org/schema/bom-1.6.schema.json",
        "bomFormat": BOM_FORMAT,
        "specVersion": SPEC_VERSION,
        "serialNumber": f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, 'urn:sha256:' + wheel_hash)}",
        "version": 1,
        "metadata": {
            "component": {
                "type": "library",
                "bom-ref": root_ref,
                "name": package_name,
                "version": package_version,
                "purl": root_ref,
                "hashes": [{"alg": "SHA-256", "content": wheel_hash}],
                "properties": [
                    {"name": "dspx:wheel:filename", "value": wheel_filename},
                    {"name": "dspx:wheel:size", "value": str(len(wheel_raw))},
                ],
            }
        },
        "components": components,
        "dependencies": dependencies,
        "properties": [
            {"name": "dspx:sbom:scope", "value": _SCOPE},
            {"name": "dspx:wheel:record-verified", "value": "true"},
            {
                "name": "dspx:wheel:payload-file-count",
                "value": str(len(cast(list[object], inventory["payloads"]))),
            },
            {
                "name": "dspx:python:declared-direct-dependency-count",
                "value": str(len(cast(list[object], inventory["dependencies"]))),
            },
        ],
    }
    _validate_official_schema(sbom)
    return sbom


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CoreReleaseEvidenceError(f"Core wheel SBOM key is duplicated: {key}")
        result[key] = value
    return result


def load_sbom_bytes(raw: bytes) -> dict[str, Any]:
    if len(raw) > MAX_JSON_BYTES:
        raise CoreReleaseEvidenceError(
            f"Core wheel SBOM exceeds {MAX_JSON_BYTES} bytes"
        )
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoreReleaseEvidenceError("Core wheel SBOM is not valid JSON") from exc
    if not isinstance(value, dict):
        raise CoreReleaseEvidenceError("Core wheel SBOM must be an object")
    return cast(dict[str, Any], value)


def validate_sbom(
    value: object, *, wheel_raw: bytes, wheel_filename: str
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CoreReleaseEvidenceError("Core wheel SBOM must be an object")
    _validate_official_schema(cast(dict[str, Any], value))
    expected = build_sbom(wheel_raw=wheel_raw, wheel_filename=wheel_filename)
    if value != expected:
        raise CoreReleaseEvidenceError("Core wheel SBOM content or wheel binding drift")
    return expected


def validate_sbom_path(*, wheel_path: Path, sbom_path: Path) -> dict[str, Any]:
    wheel_raw = _stable_regular_bytes(
        wheel_path, label="Core wheel", limit=MAX_ARTIFACT_BYTES
    )
    sbom_raw = _stable_regular_bytes(
        sbom_path, label="Core wheel SBOM", limit=MAX_JSON_BYTES
    )
    return validate_sbom(
        load_sbom_bytes(sbom_raw), wheel_raw=wheel_raw, wheel_filename=wheel_path.name
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate")
    generate.add_argument("--wheel", type=Path, required=True)
    generate.add_argument("--out", type=Path, required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--wheel", type=Path, required=True)
    validate.add_argument("--sbom", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "generate":
        wheel_raw = _stable_regular_bytes(
            args.wheel, label="Core wheel", limit=MAX_ARTIFACT_BYTES
        )
        payload = build_sbom(wheel_raw=wheel_raw, wheel_filename=args.wheel.name)
        _write_json(args.out, payload)
    else:
        payload = validate_sbom_path(wheel_path=args.wheel, sbom_path=args.sbom)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CoreReleaseEvidenceError as exc:
        raise SystemExit(f"Core wheel SBOM failed: {exc}") from exc

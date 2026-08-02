#!/usr/bin/env python3
# ---
# summary: "Generates and verifies a deterministic CycloneDX SBOM for the resolved Core environment."
# read_when:
#   - "Changing resolved Core dependency closure or release-evidence environment binding."
# ---

from __future__ import annotations

import argparse
from collections import deque
from collections.abc import Iterable, Mapping
from importlib import metadata
from itertools import islice
import json
from pathlib import Path, PurePosixPath
from typing import Any, cast
from urllib.parse import quote
import uuid

from packaging.markers import default_environment
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from core_release_environment_sbom_contract import (
    validate_retained_environment_sbom as _validate_retained_environment_sbom,
)
from core_release_evidence_io import (
    MAX_ARTIFACT_BYTES,
    MAX_JSON_BYTES,
    CoreReleaseEvidenceError,
    sha256 as _sha256,
    stable_regular_bytes as _stable_regular_bytes,
    write_json as _write_json,
)
from core_release_sbom import (
    BOM_FORMAT,
    SPEC_VERSION,
    _purl_name,
    _validate_official_schema,
    _wheel_inventory,
)

ENVIRONMENT_SBOM_COMPLETENESS = "observed_resolved_installed_distribution_closure"
_SCOPE = "exact-observed-resolved-installed-python-distribution-closure"
_MAX_DISTRIBUTIONS = 4_000
_MAX_REQUIREMENTS_PER_DISTRIBUTION = 2_000
_MAX_REQUIREMENT_CHARS = 4_096
_ROOT_NAME = "dspx-core"
_MARKER_ENVIRONMENT_KEYS = frozenset(default_environment())


def _safe_text(value: object, label: str, *, limit: int = 1_024) -> str:
    if not isinstance(value, str) or not value or len(value) > limit:
        raise CoreReleaseEvidenceError(f"{label} is invalid")
    if any(ord(character) < 32 for character in value):
        raise CoreReleaseEvidenceError(f"{label} is invalid")
    return value


def _requirement(value: str, owner: str) -> Requirement:
    _safe_text(
        value,
        f"installed distribution {owner} requirement",
        limit=_MAX_REQUIREMENT_CHARS,
    )
    try:
        return Requirement(value)
    except InvalidRequirement as exc:
        raise CoreReleaseEvidenceError(
            f"installed distribution {owner} requirement is invalid"
        ) from exc


def _requirement_identity(requirement: Requirement) -> str:
    return json.dumps(
        {
            "name": canonicalize_name(requirement.name),
            "extras": sorted(canonicalize_name(extra) for extra in requirement.extras),
            "specifier": str(requirement.specifier),
            "url": requirement.url,
            "marker": (
                str(requirement.marker) if requirement.marker is not None else None
            ),
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _record(name: str, version: str, requirements: Iterable[str]) -> dict[str, Any]:
    canonical_name = canonicalize_name(_safe_text(name, "installed distribution name"))
    try:
        normalized_version = str(
            Version(
                _safe_text(version, f"installed distribution {canonical_name} version")
            )
        )
    except InvalidVersion as exc:
        raise CoreReleaseEvidenceError(
            f"installed distribution {canonical_name} version is invalid"
        ) from exc
    raw_requirements = list(
        islice(iter(requirements), _MAX_REQUIREMENTS_PER_DISTRIBUTION + 1)
    )
    if len(raw_requirements) > _MAX_REQUIREMENTS_PER_DISTRIBUTION:
        raise CoreReleaseEvidenceError(
            f"installed distribution {canonical_name} requirement inventory is oversized"
        )
    parsed = [_requirement(value, canonical_name) for value in raw_requirements]
    unique_requirements: dict[str, str] = {}
    for item in parsed:
        identity = _requirement_identity(item)
        if identity in unique_requirements:
            if canonical_name == _ROOT_NAME:
                raise CoreReleaseEvidenceError(
                    "installed Core requirement inventory contains a duplicate"
                )
            continue
        unique_requirements[identity] = str(item)
    return {
        "name": canonical_name,
        "version": normalized_version,
        "requirements": [
            unique_requirements[identity] for identity in sorted(unique_requirements)
        ],
    }


def collect_installed_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for distribution in metadata.distributions():
        name = distribution.metadata.get("Name")
        version = distribution.metadata.get("Version")
        requirements = distribution.metadata.get_all("Requires-Dist", [])
        records.append(
            _record(str(name or ""), str(version or ""), map(str, requirements))
        )
    return records


def _normalize_records(
    records: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    for value in records:
        requirements = value.get("requirements", [])
        if not isinstance(requirements, Iterable) or isinstance(
            requirements, (str, bytes, Mapping)
        ):
            raise CoreReleaseEvidenceError(
                "installed distribution requirements are invalid"
            )
        row = _record(
            cast(str, value.get("name")),
            cast(str, value.get("version")),
            (cast(str, item) for item in requirements),
        )
        name = cast(str, row["name"])
        if name in normalized:
            raise CoreReleaseEvidenceError(
                "installed distribution canonical name is duplicated"
            )
        normalized[name] = row
        if len(normalized) > _MAX_DISTRIBUTIONS:
            raise CoreReleaseEvidenceError(
                "installed distribution inventory is oversized"
            )
    return normalized


def _validate_root_against_wheel(
    root: Mapping[str, Any],
    *,
    wheel_raw: bytes,
    wheel_filename: str,
    marker_environment: Mapping[str, str],
) -> None:
    inventory = _wheel_inventory(wheel_raw, wheel_filename=wheel_filename)
    wheel_name = canonicalize_name(
        _safe_text(inventory.get("package_name"), "Core wheel package name")
    )
    try:
        wheel_version = str(
            Version(
                _safe_text(
                    inventory.get("package_version"), "Core wheel package version"
                )
            )
        )
    except InvalidVersion as exc:
        raise CoreReleaseEvidenceError("Core wheel package version is invalid") from exc
    if (
        wheel_name != _ROOT_NAME
        or root.get("name") != wheel_name
        or root.get("version") != wheel_version
    ):
        raise CoreReleaseEvidenceError(
            "resolved environment root identity does not match exact Core wheel"
        )
    installed = [
        _requirement(raw, _ROOT_NAME) for raw in cast(list[str], root["requirements"])
    ]
    wheel_dependencies = cast(list[dict[str, str]], inventory["dependencies"])
    wheel = [_requirement(row["requirement"], _ROOT_NAME) for row in wheel_dependencies]
    for requirement in [*installed, *wheel]:
        if requirement.url is None:
            continue
        if requirement.marker is not None:
            try:
                enabled = requirement.marker.evaluate(
                    {**marker_environment, "extra": ""}
                )
            except Exception as exc:
                raise CoreReleaseEvidenceError(
                    "Core wheel dependency marker cannot be evaluated"
                ) from exc
            if not enabled:
                continue
        raise CoreReleaseEvidenceError(
            "resolved environment cannot prove active exact-wheel direct URL dependencies"
        )
    installed_requirements = {
        _requirement_identity(requirement) for requirement in installed
    }
    wheel_requirements = {row["identity"] for row in wheel_dependencies}
    if installed_requirements != wheel_requirements:
        raise CoreReleaseEvidenceError(
            "resolved environment root dependency inventory does not match exact Core wheel"
        )


def _active_dependency_names(
    row: Mapping[str, Any], marker_environment: Mapping[str, str]
) -> list[str]:
    dependencies: set[str] = set()
    for raw in cast(list[str], row["requirements"]):
        requirement = _requirement(raw, cast(str, row["name"]))
        if requirement.marker is not None:
            try:
                active = requirement.marker.evaluate(
                    {**marker_environment, "extra": ""}
                )
            except Exception as exc:
                raise CoreReleaseEvidenceError(
                    f"installed distribution {row['name']} marker cannot be evaluated"
                ) from exc
            if not active:
                continue
        target_name = canonicalize_name(requirement.name)
        dependencies.add(target_name)
    return sorted(dependencies)


def _resolved_closure(
    records: dict[str, dict[str, Any]], marker_environment: Mapping[str, str]
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    if _ROOT_NAME not in records:
        raise CoreReleaseEvidenceError("resolved environment lacks dspx-core")
    active_extras: dict[str, set[str]] = {_ROOT_NAME: set()}
    queue = deque([_ROOT_NAME])
    edges: dict[str, set[str]] = {}
    while queue:
        owner = queue.popleft()
        row = records[owner]
        dependencies = edges.setdefault(owner, set())
        marker_extras = {"", *active_extras.get(owner, set())}
        for raw in cast(list[str], row["requirements"]):
            requirement = _requirement(raw, owner)
            if requirement.marker is not None and not any(
                requirement.marker.evaluate({**marker_environment, "extra": extra})
                for extra in marker_extras
            ):
                continue
            target = canonicalize_name(requirement.name)
            installed = records.get(target)
            if installed is None:
                raise CoreReleaseEvidenceError(
                    f"resolved environment dependency is missing: {owner} -> {target}"
                )
            try:
                installed_version = Version(cast(str, installed["version"]))
            except InvalidVersion as exc:
                raise CoreReleaseEvidenceError(
                    f"resolved environment dependency version is invalid: {target}"
                ) from exc
            if requirement.specifier and installed_version not in requirement.specifier:
                raise CoreReleaseEvidenceError(
                    f"resolved environment dependency version mismatch: {owner} -> {target}"
                )
            dependencies.add(target)
            requested_extras = {
                canonicalize_name(extra) for extra in requirement.extras
            }
            previous_extras = active_extras.setdefault(target, set())
            extras_changed = not requested_extras.issubset(previous_extras)
            if extras_changed:
                previous_extras.update(requested_extras)
            if target not in edges or extras_changed:
                queue.append(target)
    unreachable = set(records) - set(edges)
    if unreachable:
        raise CoreReleaseEvidenceError(
            "resolved environment contains unreachable distributions: "
            + ", ".join(sorted(unreachable)[:10])
        )
    return (
        [records[name] for name in sorted(edges)],
        {name: sorted(targets) for name, targets in sorted(edges.items())},
    )


def _environment_identity() -> dict[str, str]:
    return {
        key: _safe_text(value, f"marker environment {key}")
        for key, value in sorted(default_environment().items())
    }


def _ref(name: str, version: str) -> str:
    return f"pkg:pypi/{_purl_name(name)}@{quote(version, safe='.-_')}"


def build_environment_sbom(
    *,
    wheel_raw: bytes,
    wheel_filename: str,
    installed_proof_raw: bytes,
    records: Iterable[Mapping[str, Any]] | None = None,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if not wheel_filename or PurePosixPath(wheel_filename).name != wheel_filename:
        raise CoreReleaseEvidenceError("Core wheel filename is unsafe")
    normalized = _normalize_records(
        records if records is not None else collect_installed_records()
    )
    if _ROOT_NAME not in normalized:
        raise CoreReleaseEvidenceError("resolved environment lacks dspx-core")
    root = normalized[_ROOT_NAME]
    observed_environment = dict(
        _environment_identity() if environment is None else environment
    )
    if set(observed_environment) != _MARKER_ENVIRONMENT_KEYS:
        raise CoreReleaseEvidenceError(
            "resolved environment marker identity fields do not match contract"
        )
    observed_environment = {
        key: _safe_text(value, f"marker environment {key}")
        for key, value in sorted(observed_environment.items())
    }
    _validate_root_against_wheel(
        root,
        wheel_raw=wheel_raw,
        wheel_filename=wheel_filename,
        marker_environment=observed_environment,
    )
    closure, edges = _resolved_closure(normalized, observed_environment)
    wheel_hash = _sha256(wheel_raw)
    proof_hash = _sha256(installed_proof_raw)
    root_ref = _ref(_ROOT_NAME, cast(str, root["version"]))
    components = [
        {
            "type": "library",
            "bom-ref": _ref(cast(str, row["name"]), cast(str, row["version"])),
            "name": row["name"],
            "version": row["version"],
            "purl": _ref(cast(str, row["name"]), cast(str, row["version"])),
        }
        for row in closure
        if row["name"] != _ROOT_NAME
    ]
    dependency_rows = [
        {
            "ref": _ref(name, cast(str, normalized[name]["version"])),
            "dependsOn": [
                _ref(target, cast(str, normalized[target]["version"]))
                for target in edges[name]
            ],
        }
        for name in sorted(edges)
    ]
    identity_json = json.dumps(
        observed_environment, sort_keys=True, separators=(",", ":")
    )
    graph_identity = json.dumps(edges, sort_keys=True, separators=(",", ":"))
    serial_seed = (
        f"{wheel_hash}:{proof_hash}:{identity_json}:{graph_identity}:"
        + ",".join(f"{row['name']}=={row['version']}" for row in closure)
    )
    sbom = {
        "$schema": "http://cyclonedx.org/schema/bom-1.6.schema.json",
        "bomFormat": BOM_FORMAT,
        "specVersion": SPEC_VERSION,
        "serialNumber": f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, serial_seed)}",
        "version": 1,
        "metadata": {
            "component": {
                "type": "library",
                "bom-ref": root_ref,
                "name": _ROOT_NAME,
                "version": root["version"],
                "purl": root_ref,
                "hashes": [{"alg": "SHA-256", "content": wheel_hash}],
                "properties": [
                    {"name": "dspx:wheel:filename", "value": wheel_filename},
                    {"name": "dspx:installed-proof:sha256", "value": proof_hash},
                ],
            }
        },
        "components": components,
        "dependencies": dependency_rows,
        "properties": [
            {"name": "dspx:sbom:scope", "value": _SCOPE},
            {
                "name": "dspx:environment:observation",
                "value": "point-in-time-resolver-dependent-not-lockfile-proof",
            },
            {"name": "dspx:environment:distribution-count", "value": str(len(closure))},
            *[
                {
                    "name": f"dspx:environment:{key.replace('_', '-')}",
                    "value": observed_environment[key],
                }
                for key in sorted(observed_environment)
            ],
        ],
    }
    _validate_official_schema(sbom)
    return sbom


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CoreReleaseEvidenceError(
                f"resolved environment SBOM key is duplicated: {key}"
            )
        result[key] = value
    return result


def load_environment_sbom_bytes(raw: bytes) -> dict[str, Any]:
    if len(raw) > MAX_JSON_BYTES:
        raise CoreReleaseEvidenceError(
            f"resolved environment SBOM exceeds {MAX_JSON_BYTES} bytes"
        )
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoreReleaseEvidenceError(
            "resolved environment SBOM is not valid JSON"
        ) from exc
    if not isinstance(value, dict):
        raise CoreReleaseEvidenceError("resolved environment SBOM must be an object")
    return cast(dict[str, Any], value)


def validate_environment_sbom(
    value: object,
    *,
    wheel_raw: bytes,
    wheel_filename: str,
    installed_proof_raw: bytes,
    records: Iterable[Mapping[str, Any]] | None = None,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CoreReleaseEvidenceError("resolved environment SBOM must be an object")
    _validate_official_schema(cast(dict[str, Any], value))
    expected = build_environment_sbom(
        wheel_raw=wheel_raw,
        wheel_filename=wheel_filename,
        installed_proof_raw=installed_proof_raw,
        records=records,
        environment=environment,
    )
    if value != expected:
        raise CoreReleaseEvidenceError(
            "resolved environment SBOM content or subject binding drift"
        )
    return expected


def validate_retained_environment_sbom(
    value: object, *, wheel_raw: bytes, wheel_filename: str, installed_proof_raw: bytes
) -> dict[str, Any]:
    return _validate_retained_environment_sbom(
        value,
        wheel_raw=wheel_raw,
        wheel_filename=wheel_filename,
        installed_proof_raw=installed_proof_raw,
        wheel_inventory=_wheel_inventory,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("generate", "validate"):
        sub = subparsers.add_parser(command)
        sub.add_argument("--wheel", type=Path, required=True)
        sub.add_argument("--installed-proof", type=Path, required=True)
        if command == "generate":
            sub.add_argument("--out", type=Path, required=True)
        else:
            sub.add_argument("--sbom", type=Path, required=True)
    args = parser.parse_args()
    wheel_raw = _stable_regular_bytes(
        args.wheel, label="Core wheel", limit=MAX_ARTIFACT_BYTES
    )
    proof_raw = _stable_regular_bytes(
        args.installed_proof, label="installed Core proof", limit=MAX_JSON_BYTES
    )
    if args.command == "generate":
        payload = build_environment_sbom(
            wheel_raw=wheel_raw,
            wheel_filename=args.wheel.name,
            installed_proof_raw=proof_raw,
        )
        _write_json(args.out, payload)
    else:
        sbom_raw = _stable_regular_bytes(
            args.sbom, label="resolved environment SBOM", limit=MAX_JSON_BYTES
        )
        payload = validate_environment_sbom(
            load_environment_sbom_bytes(sbom_raw),
            wheel_raw=wheel_raw,
            wheel_filename=args.wheel.name,
            installed_proof_raw=proof_raw,
        )
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CoreReleaseEvidenceError as exc:
        raise SystemExit(f"Core resolved environment SBOM failed: {exc}") from exc

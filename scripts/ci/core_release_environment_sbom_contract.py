#!/usr/bin/env python3
# ---
# summary: "Validates canonical retained resolved-environment SBOM contracts."
# read_when:
#   - "Changing retained Core environment SBOM semantic validation."
# ---

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping
import json
from urllib.parse import quote
from typing import Any, cast
import uuid

from packaging.markers import default_environment
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from core_release_evidence_io import (
    CoreReleaseEvidenceError,
    sha256 as _sha256,
)
from core_release_sbom import (
    BOM_FORMAT,
    SPEC_VERSION,
    _purl_name,
    _validate_official_schema,
    _wheel_inventory,
)

_SCOPE = "exact-observed-resolved-installed-python-distribution-closure"
_ROOT_NAME = "dspx-core"
_MAX_DISTRIBUTIONS = 4_000
_MARKER_ENVIRONMENT_KEYS = frozenset(default_environment())


def _safe_text(value: object, label: str, *, limit: int = 1_024) -> str:
    if not isinstance(value, str) or not value or len(value) > limit:
        raise CoreReleaseEvidenceError(f"{label} is invalid")
    if any(ord(character) < 32 for character in value):
        raise CoreReleaseEvidenceError(f"{label} is invalid")
    return value


def _ref(name: str, version: str) -> str:
    return f"pkg:pypi/{_purl_name(name)}@{quote(version, safe='.-_')}"


def _wheel_direct_dependencies(
    inventory: Mapping[str, Any],
    *,
    environment: Mapping[str, str],
    components_by_name: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    raw_dependencies = inventory.get("dependencies")
    if not isinstance(raw_dependencies, list):
        raise CoreReleaseEvidenceError("Core wheel dependency inventory drift")
    active: set[str] = set()
    for row in raw_dependencies:
        if not isinstance(row, Mapping) or not isinstance(row.get("requirement"), str):
            raise CoreReleaseEvidenceError("Core wheel dependency inventory drift")
        try:
            requirement = Requirement(cast(str, row["requirement"]))
        except InvalidRequirement as exc:
            raise CoreReleaseEvidenceError(
                "Core wheel dependency inventory drift"
            ) from exc
        if requirement.url is not None:
            raise CoreReleaseEvidenceError(
                "resolved environment cannot prove exact-wheel direct URL dependencies"
            )
        if requirement.marker is not None:
            try:
                enabled = requirement.marker.evaluate({**environment, "extra": ""})
            except Exception as exc:
                raise CoreReleaseEvidenceError(
                    "Core wheel dependency marker cannot be evaluated"
                ) from exc
            if not enabled:
                continue
        name = canonicalize_name(requirement.name)
        component = components_by_name.get(name)
        if component is None:
            raise CoreReleaseEvidenceError(
                f"resolved environment lacks exact-wheel dependency: {name}"
            )
        try:
            version = Version(cast(str, component["version"]))
        except (InvalidVersion, KeyError) as exc:
            raise CoreReleaseEvidenceError(
                f"resolved environment exact-wheel dependency version is invalid: {name}"
            ) from exc
        if requirement.specifier and version not in requirement.specifier:
            raise CoreReleaseEvidenceError(
                f"resolved environment exact-wheel dependency version mismatch: {name}"
            )
        active.add(name)
    return sorted(active)


def _component_row(value: object, *, root: bool) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise CoreReleaseEvidenceError("resolved environment SBOM component drift")
    row = cast(Mapping[str, Any], value)
    expected_fields = {"type", "bom-ref", "name", "version", "purl"}
    if root:
        expected_fields |= {"hashes", "properties"}
    if set(row) != expected_fields or row.get("type") != "library":
        raise CoreReleaseEvidenceError("resolved environment SBOM component drift")
    name = _safe_text(row.get("name"), "resolved environment component name")
    if name != canonicalize_name(name):
        raise CoreReleaseEvidenceError("resolved environment SBOM component name drift")
    version = _safe_text(
        row.get("version"), f"resolved environment component {name} version"
    )
    try:
        if str(Version(version)) != version:
            raise CoreReleaseEvidenceError(
                "resolved environment SBOM component version drift"
            )
    except InvalidVersion as exc:
        raise CoreReleaseEvidenceError(
            "resolved environment SBOM component version drift"
        ) from exc
    ref = _ref(name, version)
    if row.get("bom-ref") != ref or row.get("purl") != ref:
        raise CoreReleaseEvidenceError(
            "resolved environment SBOM component reference drift"
        )
    return dict(row)


def _validate_top_properties(value: object, distribution_count: int) -> dict[str, str]:
    if not isinstance(value, list):
        raise CoreReleaseEvidenceError("resolved environment SBOM properties drift")
    expected_environment_names = {
        f"dspx:environment:{key.replace('_', '-')}": key
        for key in _MARKER_ENVIRONMENT_KEYS
    }
    rows: list[dict[str, str]] = []
    for raw in value:
        if not isinstance(raw, Mapping) or set(raw) != {"name", "value"}:
            raise CoreReleaseEvidenceError("resolved environment SBOM properties drift")
        property_row = cast(Mapping[str, Any], raw)
        rows.append(
            {
                "name": _safe_text(
                    property_row.get("name"), "resolved environment property name"
                ),
                "value": _safe_text(
                    property_row.get("value"), "resolved environment property value"
                ),
            }
        )
    if len({row["name"] for row in rows}) != len(rows):
        raise CoreReleaseEvidenceError(
            "resolved environment SBOM property is duplicated"
        )
    expected_names = {
        "dspx:sbom:scope",
        "dspx:environment:observation",
        "dspx:environment:distribution-count",
        *expected_environment_names,
    }
    by_name = {row["name"]: row["value"] for row in rows}
    if set(by_name) != expected_names:
        raise CoreReleaseEvidenceError(
            "resolved environment SBOM marker identity drift"
        )
    if by_name["dspx:sbom:scope"] != _SCOPE:
        raise CoreReleaseEvidenceError("resolved environment SBOM scope drift")
    if by_name[
        "dspx:environment:observation"
    ] != "point-in-time-resolver-dependent-not-lockfile-proof" or by_name[
        "dspx:environment:distribution-count"
    ] != str(distribution_count):
        raise CoreReleaseEvidenceError("resolved environment SBOM observation drift")
    environment = {
        key: by_name[property_name]
        for property_name, key in expected_environment_names.items()
    }
    expected_rows = [
        {"name": "dspx:sbom:scope", "value": _SCOPE},
        {
            "name": "dspx:environment:observation",
            "value": "point-in-time-resolver-dependent-not-lockfile-proof",
        },
        {
            "name": "dspx:environment:distribution-count",
            "value": str(distribution_count),
        },
        *[
            {
                "name": f"dspx:environment:{key.replace('_', '-')}",
                "value": environment[key],
            }
            for key in sorted(environment)
        ],
    ]
    if rows != expected_rows:
        raise CoreReleaseEvidenceError("resolved environment SBOM property order drift")
    return environment


def validate_retained_environment_sbom(
    value: object,
    *,
    wheel_raw: bytes,
    wheel_filename: str,
    installed_proof_raw: bytes,
    wheel_inventory: Callable[..., dict[str, Any]] = _wheel_inventory,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CoreReleaseEvidenceError("resolved environment SBOM must be an object")
    payload = cast(dict[str, Any], value)
    _validate_official_schema(payload)
    if set(payload) != {
        "$schema",
        "bomFormat",
        "specVersion",
        "serialNumber",
        "version",
        "metadata",
        "components",
        "dependencies",
        "properties",
    }:
        raise CoreReleaseEvidenceError("resolved environment SBOM fields drift")
    if (
        payload.get("$schema") != "http://cyclonedx.org/schema/bom-1.6.schema.json"
        or payload.get("bomFormat") != BOM_FORMAT
        or payload.get("specVersion") != SPEC_VERSION
        or payload.get("version") != 1
    ):
        raise CoreReleaseEvidenceError("resolved environment SBOM constants drift")
    metadata_value = payload.get("metadata")
    if not isinstance(metadata_value, Mapping) or set(metadata_value) != {"component"}:
        raise CoreReleaseEvidenceError("resolved environment SBOM metadata drift")
    component = _component_row(metadata_value.get("component"), root=True)
    wheel_hash = _sha256(wheel_raw)
    proof_hash = _sha256(installed_proof_raw)
    inventory = wheel_inventory(wheel_raw, wheel_filename=wheel_filename)
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
    if wheel_name != _ROOT_NAME:
        raise CoreReleaseEvidenceError("Core wheel package identity drift")
    if component["name"] != wheel_name or component["version"] != wheel_version:
        raise CoreReleaseEvidenceError("resolved environment SBOM root identity drift")
    root_ref = _ref(wheel_name, wheel_version)
    if component["bom-ref"] != root_ref or component["purl"] != root_ref:
        raise CoreReleaseEvidenceError("resolved environment SBOM root reference drift")
    if component["hashes"] != [{"alg": "SHA-256", "content": wheel_hash}]:
        raise CoreReleaseEvidenceError("resolved environment SBOM wheel binding drift")
    expected_root_properties = [
        {"name": "dspx:wheel:filename", "value": wheel_filename},
        {"name": "dspx:installed-proof:sha256", "value": proof_hash},
    ]
    if component["properties"] != expected_root_properties:
        raise CoreReleaseEvidenceError(
            "resolved environment SBOM installed-proof binding drift"
        )

    raw_components = payload.get("components")
    if not isinstance(raw_components, list):
        raise CoreReleaseEvidenceError("resolved environment SBOM components drift")
    components = [_component_row(row, root=False) for row in raw_components]
    all_components = [component, *components]
    by_ref = {cast(str, row["bom-ref"]): row for row in all_components}
    name_by_ref = {ref: cast(str, row["name"]) for ref, row in by_ref.items()}
    canonical_names = [cast(str, row["name"]) for row in all_components]
    if (
        len(by_ref) != len(all_components)
        or len(set(canonical_names)) != len(canonical_names)
        or len(all_components) > _MAX_DISTRIBUTIONS
    ):
        raise CoreReleaseEvidenceError(
            "resolved environment SBOM component identity drift"
        )
    expected_components = sorted(components, key=lambda row: cast(str, row["name"]))
    if components != expected_components:
        raise CoreReleaseEvidenceError(
            "resolved environment SBOM component order drift"
        )

    raw_dependencies = payload.get("dependencies")
    if not isinstance(raw_dependencies, list) or len(raw_dependencies) != len(by_ref):
        raise CoreReleaseEvidenceError(
            "resolved environment SBOM dependency closure drift"
        )
    edges_by_ref: dict[str, list[str]] = {}
    for raw_row in raw_dependencies:
        if not isinstance(raw_row, Mapping) or set(raw_row) != {"ref", "dependsOn"}:
            raise CoreReleaseEvidenceError(
                "resolved environment SBOM dependency row drift"
            )
        ref = raw_row.get("ref")
        targets = raw_row.get("dependsOn")
        if (
            not isinstance(ref, str)
            or ref not in by_ref
            or ref in edges_by_ref
            or not isinstance(targets, list)
            or any(
                not isinstance(target, str) or target not in by_ref
                for target in targets
            )
            or len(targets) != len(set(targets))
            or targets
            != sorted(targets, key=lambda target: name_by_ref[cast(str, target)])
        ):
            raise CoreReleaseEvidenceError(
                "resolved environment SBOM dependency row drift"
            )
        edges_by_ref[ref] = cast(list[str], targets)
    if list(edges_by_ref) != sorted(edges_by_ref, key=lambda ref: name_by_ref[ref]):
        raise CoreReleaseEvidenceError(
            "resolved environment SBOM dependency order drift"
        )
    reachable = {root_ref}
    queue = deque([root_ref])
    while queue:
        current = queue.popleft()
        for target in edges_by_ref[current]:
            if target not in reachable:
                reachable.add(target)
                queue.append(target)
    if reachable != set(by_ref):
        raise CoreReleaseEvidenceError(
            "resolved environment SBOM dependency reachability drift"
        )

    environment = _validate_top_properties(payload.get("properties"), len(by_ref))
    components_by_name = {cast(str, row["name"]): row for row in all_components}
    expected_root_dependencies = _wheel_direct_dependencies(
        inventory,
        environment=environment,
        components_by_name=components_by_name,
    )
    observed_root_dependencies = sorted(
        name_by_ref[target] for target in edges_by_ref[root_ref]
    )
    if observed_root_dependencies != expected_root_dependencies:
        raise CoreReleaseEvidenceError(
            "resolved environment SBOM root dependencies drift from exact Core wheel"
        )
    graph_identity = {
        name_by_ref[ref]: sorted(name_by_ref[target] for target in targets)
        for ref, targets in edges_by_ref.items()
    }
    identity_json = json.dumps(environment, sort_keys=True, separators=(",", ":"))
    graph_json = json.dumps(graph_identity, sort_keys=True, separators=(",", ":"))
    versions = ",".join(
        f"{row['name']}=={row['version']}"
        for row in sorted(all_components, key=lambda row: cast(str, row["name"]))
    )
    serial_seed = f"{wheel_hash}:{proof_hash}:{identity_json}:{graph_json}:{versions}"
    expected_serial = f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, serial_seed)}"
    if payload.get("serialNumber") != expected_serial:
        raise CoreReleaseEvidenceError(
            "resolved environment SBOM serial identity drift"
        )
    return payload

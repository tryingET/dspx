# summary: "Fail-closed, read-only loader for misegraph-evidence-package-v1 directories (closed manifest, hashes, canonical form, schema, stray files)."
# read_when:
#   - "Changing what the DSPx importer accepts from a Misegraph evidence package."
#   - "Debugging why a package export is rejected by `dspx foundry import-misegraph-evidence`."

"""Read-only verification of a `misegraph-evidence-package-v1` directory.

The manifest shape, canonical JSON rule (pretty, sorted keys, trailing
newline) and `package_sha256` derivation mirror the Misegraph producer in
``src/evidence.rs`` and ``src/evidence/store.rs``. Every check fails closed:
unknown keys, wrong types, a non-canonical manifest, a hash or byte-length
mismatch, a missing or stray file, or a symlink inside the package all reject
the package. The loader never opens anything for writing.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

PACKAGE_SCHEMA_VERSION = "misegraph-evidence-package-v1"
BEHAVIOR_SCHEMA_VERSION = "misegraph-behavior-cases-v1"
MANIFEST_FILE = "manifest.json"
SOURCE_FILE = "source.mise"
CANONICAL_FILE = "canonical.json"
CHECK_FILE = "check.json"
SCHEMA_FILE = "schema.json"
BEHAVIOR_FILE = "behavior.json"
MALFORMED_FILE = "malformed.json"
EPISODE_FILE = "episode.json"
RENDER_TEXT_FILE = "render.text.txt"

REQUIRED_ARTIFACT_KINDS: Mapping[str, str] = {
    SOURCE_FILE: "mise_source",
    CANONICAL_FILE: "canonical_ir",
    CHECK_FILE: "diagnostics",
    SCHEMA_FILE: "ir_json_schema",
    BEHAVIOR_FILE: "behavior_cases",
    MALFORMED_FILE: "malformed_probes",
    EPISODE_FILE: "episode",
}

_MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "producer",
        "recipe",
        "artifacts",
        "conformance",
        "package_sha256",
        "non_authority",
    }
)
_PRODUCER_KEYS = frozenset({"name", "version", "ir_schema_version"})
_RECIPE_KEYS = frozenset({"id", "title"})
_ARTIFACT_KEYS = frozenset({"kind", "format", "profile", "sha256", "bytes"})
_CONFORMANCE_KEYS = frozenset(
    {"status", "error_count", "warning_count", "deny_warnings"}
)
_NON_AUTHORITY_KEYS = frozenset(
    {"acceptance_authority", "release_authority", "evidence_only"}
)
_BEHAVIOR_KEYS = frozenset({"schema_version", "cases"})
_CASE_KEYS = frozenset(
    {"id", "argv", "input_sha256", "exit_code", "output_artifact", "output_sha256"}
)

MANIFEST_BYTE_BOUND = 1 << 20
ARTIFACT_BYTE_BOUND = 32 << 20
_HEX64 = frozenset("0123456789abcdef")


class MisegraphEvidencePackageError(ValueError):
    """Raised when a package directory fails read-only verification."""


def canonical_json(value: Any) -> str:
    """Misegraph canonical JSON: pretty (2 spaces), sorted keys, trailing newline."""

    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def compact_canonical_json(value: Any) -> str:
    """Compact canonical JSON used for intent example evidence strings."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class MisegraphBehaviorCase:
    id: str
    argv: tuple[str, ...]
    input_sha256: str
    exit_code: int
    output_artifact: str
    output_sha256: str


@dataclass(frozen=True)
class MisegraphEvidencePackage:
    """A verified package: manifest, artifact bytes, and validation facts."""

    dir: Path
    manifest: dict[str, Any]
    manifest_bytes: bytes
    manifest_sha256: str
    package_sha256: str
    files: dict[str, bytes]
    behavior_cases: tuple[MisegraphBehaviorCase, ...]
    canonical_ir_validator: str

    def artifact_sha256(self, name: str) -> str:
        return str(self.manifest["artifacts"][name]["sha256"])

    def text(self, name: str) -> str:
        return self.files[name].decode("utf-8")

    def json(self, name: str) -> Any:
        return json.loads(self.text(name))

    def case(self, case_id: str) -> MisegraphBehaviorCase:
        for case in self.behavior_cases:
            if case.id == case_id:
                return case
        raise MisegraphEvidencePackageError(
            f"behavior case `{case_id}` is not in the package"
        )


def _fail(message: str) -> MisegraphEvidencePackageError:
    return MisegraphEvidencePackageError(message)


def _closed_object(
    value: Any, *, allowed: frozenset[str], required: frozenset[str], label: str
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _fail(f"{label} must be a JSON object")
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise _fail(f"{label} has unknown keys: {', '.join(unknown)}")
    missing = sorted(required - set(value))
    if missing:
        raise _fail(f"{label} is missing keys: {', '.join(missing)}")
    return value


def _string(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise _fail(f"{label} must be a non-empty string")
    return value


def _sha(value: Any, *, label: str) -> str:
    text = _string(value, label=label)
    if len(text) != 64 or set(text) - _HEX64:
        raise _fail(f"{label} must be lowercase hex sha256")
    return text


def _int(value: Any, *, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise _fail(f"{label} must be an integer >= {minimum}")
    return value


def _bool(value: Any, *, label: str, expected: bool | None = None) -> bool:
    if not isinstance(value, bool):
        raise _fail(f"{label} must be a boolean")
    if expected is not None and value is not expected:
        raise _fail(f"{label} must be {str(expected).lower()}")
    return value


def _plain_file_name(name: str) -> bool:
    return (
        bool(name)
        and name not in {".", ".."}
        and not name.startswith(".")
        and "/" not in name
        and "\\" not in name
        and "\0" not in name
    )


def _validate_manifest(payload: Any) -> dict[str, Any]:
    manifest = _closed_object(
        payload, allowed=_MANIFEST_KEYS, required=_MANIFEST_KEYS, label="manifest"
    )
    if manifest["schema_version"] != PACKAGE_SCHEMA_VERSION:
        raise _fail(
            f"manifest schema_version `{manifest['schema_version']}` is not "
            f"`{PACKAGE_SCHEMA_VERSION}`"
        )
    producer = _closed_object(
        manifest["producer"],
        allowed=_PRODUCER_KEYS,
        required=_PRODUCER_KEYS,
        label="manifest.producer",
    )
    if _string(producer["name"], label="producer.name") != "misegraph":
        raise _fail("manifest.producer.name must be `misegraph`")
    _string(producer["version"], label="producer.version")
    _int(producer["ir_schema_version"], label="producer.ir_schema_version", minimum=1)
    recipe = _closed_object(
        manifest["recipe"],
        allowed=_RECIPE_KEYS,
        required=_RECIPE_KEYS,
        label="manifest.recipe",
    )
    _string(recipe["id"], label="recipe.id")
    _string(recipe["title"], label="recipe.title")
    artifacts = manifest["artifacts"]
    if not isinstance(artifacts, dict) or not artifacts:
        raise _fail("manifest.artifacts must be a non-empty object")
    for name, entry in artifacts.items():
        if not _plain_file_name(name) or name == MANIFEST_FILE:
            raise _fail(f"artifact name `{name}` is not a plain file name")
        item = _closed_object(
            entry,
            allowed=_ARTIFACT_KEYS,
            required=frozenset({"kind", "sha256", "bytes"}),
            label=f"artifact `{name}`",
        )
        kind = _string(item["kind"], label=f"artifact `{name}`.kind")
        _sha(item["sha256"], label=f"artifact `{name}`.sha256")
        _int(item["bytes"], label=f"artifact `{name}`.bytes")
        if kind == "render":
            _string(item.get("format"), label=f"artifact `{name}`.format")
            _string(item.get("profile"), label=f"artifact `{name}`.profile")
        elif "format" in item or "profile" in item:
            raise _fail(f"artifact `{name}` carries render fields but is `{kind}`")
    for name, kind in REQUIRED_ARTIFACT_KINDS.items():
        if name not in artifacts:
            raise _fail(f"manifest lacks required artifact `{name}`")
        if artifacts[name]["kind"] != kind:
            raise _fail(f"artifact `{name}` must have kind `{kind}`")
    conformance = _closed_object(
        manifest["conformance"],
        allowed=_CONFORMANCE_KEYS,
        required=_CONFORMANCE_KEYS,
        label="manifest.conformance",
    )
    if conformance["status"] not in {"ok", "errors"}:
        raise _fail("manifest.conformance.status must be `ok` or `errors`")
    _int(conformance["error_count"], label="conformance.error_count")
    _int(conformance["warning_count"], label="conformance.warning_count")
    _bool(conformance["deny_warnings"], label="conformance.deny_warnings")
    non_authority = _closed_object(
        manifest["non_authority"],
        allowed=_NON_AUTHORITY_KEYS,
        required=_NON_AUTHORITY_KEYS,
        label="manifest.non_authority",
    )
    _bool(
        non_authority["acceptance_authority"],
        label="non_authority.acceptance_authority",
        expected=False,
    )
    _bool(
        non_authority["release_authority"],
        label="non_authority.release_authority",
        expected=False,
    )
    _bool(
        non_authority["evidence_only"],
        label="non_authority.evidence_only",
        expected=True,
    )
    _sha(manifest["package_sha256"], label="manifest.package_sha256")
    return manifest


def _open_package_dir(package_dir: Path) -> tuple[Path, int]:
    raw = package_dir.expanduser().absolute()
    if raw.is_symlink():
        raise _fail("package dir must not be a symlink")
    if not raw.is_dir():
        raise _fail(f"package dir is not a directory: {raw}")
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(raw, flags)
    except OSError as exc:
        raise _fail(f"package dir cannot be opened read-only: {exc}") from exc
    return raw.resolve(), descriptor


def _read_member(
    dir_fd: int, name: str, *, bound: int, expected_bytes: int | None = None
) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NOCTTY", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=dir_fd)
    except FileNotFoundError as exc:
        raise _fail(f"missing artifact `{name}`") from exc
    except OSError as exc:
        raise _fail(f"artifact `{name}` is not a readable regular file: {exc}") from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise _fail(f"artifact `{name}` must be a regular file")
        if info.st_size > bound:
            raise _fail(f"artifact `{name}` exceeds the {bound}-byte bound")
        if expected_bytes is not None and info.st_size != expected_bytes:
            raise _fail(f"artifact `{name}` does not match its manifest entry")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1 << 16)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _validate_behavior(
    payload: Any, *, manifest: Mapping[str, Any]
) -> tuple[MisegraphBehaviorCase, ...]:
    behavior = _closed_object(
        payload, allowed=_BEHAVIOR_KEYS, required=_BEHAVIOR_KEYS, label=BEHAVIOR_FILE
    )
    if behavior["schema_version"] != BEHAVIOR_SCHEMA_VERSION:
        raise _fail(
            f"{BEHAVIOR_FILE} schema_version is not `{BEHAVIOR_SCHEMA_VERSION}`"
        )
    if not isinstance(behavior["cases"], list) or not behavior["cases"]:
        raise _fail(f"{BEHAVIOR_FILE} cases must be a non-empty list")
    artifacts = manifest["artifacts"]
    source_sha = artifacts[SOURCE_FILE]["sha256"]
    cases: list[MisegraphBehaviorCase] = []
    seen: set[str] = set()
    for index, raw in enumerate(behavior["cases"]):
        label = f"{BEHAVIOR_FILE} cases[{index}]"
        item = _closed_object(raw, allowed=_CASE_KEYS, required=_CASE_KEYS, label=label)
        case_id = _string(item["id"], label=f"{label}.id")
        if case_id in seen:
            raise _fail(f"{BEHAVIOR_FILE} repeats case id `{case_id}`")
        seen.add(case_id)
        argv = item["argv"]
        if (
            not isinstance(argv, list)
            or not argv
            or not all(isinstance(token, str) and token for token in argv)
        ):
            raise _fail(f"{label}.argv must be a non-empty list of strings")
        if _sha(item["input_sha256"], label=f"{label}.input_sha256") != source_sha:
            raise _fail(f"{label}.input_sha256 does not match {SOURCE_FILE}")
        output = _string(item["output_artifact"], label=f"{label}.output_artifact")
        if output not in artifacts:
            raise _fail(f"{label}.output_artifact `{output}` is not a package artifact")
        output_sha = _sha(item["output_sha256"], label=f"{label}.output_sha256")
        if output_sha != artifacts[output]["sha256"]:
            raise _fail(f"{label}.output_sha256 does not match artifact `{output}`")
        exit_code = item["exit_code"]
        if isinstance(exit_code, bool) or not isinstance(exit_code, int):
            raise _fail(f"{label}.exit_code must be an integer")
        cases.append(
            MisegraphBehaviorCase(
                id=case_id,
                argv=tuple(argv),
                input_sha256=source_sha,
                exit_code=exit_code,
                output_artifact=output,
                output_sha256=output_sha,
            )
        )
    return tuple(cases)


def _structural_ir_check(canonical: Any, schema: Any) -> None:
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise _fail(f"{SCHEMA_FILE} is not an object schema")
    if not isinstance(canonical, dict):
        raise _fail(f"{CANONICAL_FILE} must be a JSON object")
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        raise _fail(f"{SCHEMA_FILE} lacks properties")
    required = schema.get("required") or []
    missing = [key for key in required if key not in canonical]
    if missing:
        raise _fail(f"{CANONICAL_FILE} is missing required keys: {', '.join(missing)}")
    if schema.get("additionalProperties") is False:
        unknown = sorted(set(canonical) - set(properties))
        if unknown:
            raise _fail(f"{CANONICAL_FILE} has unknown keys: {', '.join(unknown)}")


def _validate_canonical_ir(canonical_bytes: bytes, schema_bytes: bytes) -> str:
    try:
        canonical = json.loads(canonical_bytes.decode("utf-8"))
        schema = json.loads(schema_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _fail(
            f"{CANONICAL_FILE} or {SCHEMA_FILE} is not valid JSON: {exc}"
        ) from exc
    try:
        import jsonschema
    except ImportError:  # pragma: no cover - jsonschema is a declared dependency
        _structural_ir_check(canonical, schema)
        return "structural"
    try:
        validator_cls = jsonschema.validators.validator_for(schema)
        validator_cls.check_schema(schema)
        validator_cls(schema).validate(canonical)
    except jsonschema.exceptions.SchemaError as exc:
        raise _fail(f"{SCHEMA_FILE} is not a valid JSON Schema: {exc.message}") from exc
    except jsonschema.exceptions.ValidationError as exc:
        raise _fail(
            f"{CANONICAL_FILE} does not validate against {SCHEMA_FILE}: {exc.message}"
        ) from exc
    return "jsonschema"


def _validate_check(payload: Any) -> None:
    if not isinstance(payload, dict) or not isinstance(
        payload.get("diagnostics"), list
    ):
        raise _fail(f"{CHECK_FILE} must be an object with a diagnostics list")


def load_misegraph_evidence_package(package_dir: Path) -> MisegraphEvidencePackage:
    """Verify a package directory read-only and return its contents."""

    resolved, dir_fd = _open_package_dir(package_dir)
    try:
        manifest_bytes = _read_member(dir_fd, MANIFEST_FILE, bound=MANIFEST_BYTE_BOUND)
        try:
            payload = json.loads(manifest_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _fail(f"{MANIFEST_FILE} is not valid JSON: {exc}") from exc
        manifest = _validate_manifest(payload)
        if canonical_json(manifest).encode("utf-8") != manifest_bytes:
            raise _fail(f"{MANIFEST_FILE} is not in canonical form")
        unbound = {
            key: value for key, value in manifest.items() if key != "package_sha256"
        }
        if (
            sha256_hex(canonical_json(unbound).encode("utf-8"))
            != manifest["package_sha256"]
        ):
            raise _fail("package_sha256 does not match the manifest")
        files: dict[str, bytes] = {}
        for name, entry in sorted(manifest["artifacts"].items()):
            data = _read_member(
                dir_fd,
                name,
                bound=ARTIFACT_BYTE_BOUND,
                expected_bytes=int(entry["bytes"]),
            )
            if sha256_hex(data) != entry["sha256"]:
                raise _fail(f"artifact `{name}` does not match its manifest entry")
            files[name] = data
        allowed = set(manifest["artifacts"]) | {MANIFEST_FILE}
        stray = sorted(set(os.listdir(dir_fd)) - allowed)
        if stray:
            raise _fail(f"unexpected file `{stray[0]}` in package")
    finally:
        os.close(dir_fd)
    validator = _validate_canonical_ir(files[CANONICAL_FILE], files[SCHEMA_FILE])
    try:
        check_payload = json.loads(files[CHECK_FILE].decode("utf-8"))
        behavior_payload = json.loads(files[BEHAVIOR_FILE].decode("utf-8"))
        files[SOURCE_FILE].decode("utf-8")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _fail(f"package artifact is not decodable: {exc}") from exc
    _validate_check(check_payload)
    cases = _validate_behavior(behavior_payload, manifest=manifest)
    return MisegraphEvidencePackage(
        dir=resolved,
        manifest=manifest,
        manifest_bytes=manifest_bytes,
        manifest_sha256=sha256_hex(manifest_bytes),
        package_sha256=str(manifest["package_sha256"]),
        files=files,
        behavior_cases=cases,
        canonical_ir_validator=validator,
    )

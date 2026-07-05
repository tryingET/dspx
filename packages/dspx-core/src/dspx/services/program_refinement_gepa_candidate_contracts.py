from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Mapping, Sequence

PROGRAM_REFINEMENT_GEPA_CANDIDATE_RESULT_SCHEMA = (
    "program-refinement-gepa-candidate-result-v1"
)
PROGRAM_REFINEMENT_GEPA_RESULT_SCHEMA = "program-refinement-gepa-result-v1"
_MAX_OPTIMIZER_MANIFEST_BYTES = 2 * 1024 * 1024
_REQUIRED_FALSE_GEPA_EFFECT_FLAGS = (
    "local_gepa_candidate_generated",
    "source_program_files_mutated",
    "source_dataset_artifacts_mutated",
    "external_authority_mutated",
    "governance_mutated",
)
_REQUIRED_FALSE_GEPA_NON_AUTHORITY_FLAGS = (
    "automatic_promotion",
    "oracle_ranking",
    "oracle_pruning",
    "oracle_promotion",
    "winner_selection",
    "external_authority_export",
    "governance_authority",
    "external_mutation",
)


class ProgramRefinementGepaCandidateError(ValueError):
    """Raised when GEPA output cannot safely become a local candidate."""


def _safe_mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _safe_list(value: object) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _first_text(*values: object) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _json_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    source = path.expanduser().resolve()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProgramRefinementGepaCandidateError(
            f"{label} not found: {source}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ProgramRefinementGepaCandidateError(
            f"{label} must be valid JSON: {source}"
        ) from exc
    if not isinstance(payload, dict):
        raise ProgramRefinementGepaCandidateError(
            f"{label} must contain a JSON object: {source}"
        )
    return payload


def _identity_from_manifest(manifest: Mapping[str, Any]) -> dict[str, str | None]:
    request = _safe_mapping(manifest.get("request"))
    candidate_assembly = _safe_mapping(manifest.get("candidate_assembly"))
    execution_episode = _safe_mapping(manifest.get("execution_episode"))
    receipt_bundle = _safe_mapping(manifest.get("receipt_bundle"))
    return {
        "request_id": _first_text(
            request.get("request_id"),
            candidate_assembly.get("request_id"),
            execution_episode.get("request_id"),
            receipt_bundle.get("request_id"),
        ),
        "candidate_id": _first_text(
            candidate_assembly.get("candidate_id"),
            execution_episode.get("candidate_id"),
            receipt_bundle.get("candidate_id"),
        ),
        "assembly_id": _first_text(
            candidate_assembly.get("assembly_id"),
            execution_episode.get("assembly_id"),
            receipt_bundle.get("assembly_id"),
        ),
        "episode_id": _first_text(
            execution_episode.get("episode_id"),
            receipt_bundle.get("episode_id"),
        ),
        "receipt_bundle_id": _first_text(receipt_bundle.get("receipt_bundle_id")),
    }


def _assert_identity_matches(
    actual: Mapping[str, Any], expected: Mapping[str, str | None], *, label: str
) -> None:
    mismatches = [
        key
        for key, expected_value in expected.items()
        if expected_value is not None
        and actual.get(key) is not None
        and actual.get(key) != expected_value
    ]
    if mismatches:
        raise ProgramRefinementGepaCandidateError(
            f"{label} identity does not match source manifest identity: "
            + ", ".join(sorted(mismatches))
        )
    missing = [
        key
        for key, expected_value in expected.items()
        if expected_value and not actual.get(key)
    ]
    if missing:
        raise ProgramRefinementGepaCandidateError(
            f"{label} identity is missing source manifest identity fields: "
            + ", ".join(sorted(missing))
        )


def _is_same_or_descendant(path: Path, parent: Path) -> bool:
    return path == parent or path.is_relative_to(parent)


def _assert_no_overlap(
    *, label: str, path: Path, protected_label: str, protected: Path
) -> None:
    if _is_same_or_descendant(path, protected):
        raise ProgramRefinementGepaCandidateError(
            f"{label} must be outside {protected_label}: {path}"
        )
    if _is_same_or_descendant(protected, path):
        raise ProgramRefinementGepaCandidateError(
            f"{label} must not contain {protected_label}: {path}"
        )


def _candidate_root(manifest: Mapping[str, Any], manifest_path: Path) -> Path:
    manifest_root = manifest_path.expanduser().resolve().parent
    candidate_assembly = _safe_mapping(manifest.get("candidate_assembly"))
    raw_root = str(candidate_assembly.get("root_path") or "").strip()
    if not raw_root:
        return manifest_root
    declared_root = Path(raw_root).expanduser()
    if not declared_root.is_absolute():
        declared_root = manifest_root / declared_root
    declared_root = declared_root.resolve()
    if declared_root != manifest_root:
        raise ProgramRefinementGepaCandidateError(
            "source manifest candidate_assembly.root_path must match manifest parent"
        )
    return manifest_root


def _surface_path(
    manifest: Mapping[str, Any], manifest_path: Path, *, kind: str, default: str
) -> Path:
    root = manifest_path.expanduser().resolve().parent
    candidate_assembly = _safe_mapping(manifest.get("candidate_assembly"))
    for surface in _safe_list(candidate_assembly.get("surfaces")):
        if not isinstance(surface, Mapping) or surface.get("kind") != kind:
            continue
        raw_path = str(surface.get("path") or "").strip()
        if raw_path:
            path = Path(raw_path)
            resolved = (path if path.is_absolute() else root / path).resolve()
            if not _is_same_or_descendant(resolved, root):
                raise ProgramRefinementGepaCandidateError(
                    f"program surface path must stay under source candidate root: {resolved}"
                )
            return resolved
    return (root / default).resolve()


def _preflight_paths(
    *,
    source_root: Path,
    optimizer_root: Path,
    outdir: Path,
    result_out: Path | None,
    gepa_result_path: Path | None = None,
) -> None:
    optimizer_root = optimizer_root.expanduser().resolve()
    outdir = outdir.expanduser().resolve()
    _assert_no_overlap(
        label="GEPA candidate output directory",
        path=outdir,
        protected_label="source candidate root",
        protected=source_root,
    )
    _assert_no_overlap(
        label="GEPA candidate output directory",
        path=outdir,
        protected_label="GEPA optimizer output directory",
        protected=optimizer_root,
    )
    if result_out is None:
        return
    result_path = result_out.expanduser().resolve()
    _assert_no_overlap(
        label="GEPA candidate result sidecar path",
        path=result_path,
        protected_label="source candidate root",
        protected=source_root,
    )
    _assert_no_overlap(
        label="GEPA candidate result sidecar path",
        path=result_path,
        protected_label="GEPA optimizer output directory",
        protected=optimizer_root,
    )
    _assert_no_overlap(
        label="GEPA candidate result sidecar path",
        path=result_path,
        protected_label="GEPA candidate output directory",
        protected=outdir,
    )
    if gepa_result_path is not None:
        _assert_no_overlap(
            label="GEPA candidate result sidecar path",
            path=result_path,
            protected_label="GEPA refinement result sidecar",
            protected=gepa_result_path.expanduser().resolve(),
        )


def _validate_no_symlinks(root: Path) -> None:
    for path in [root, *root.rglob("*")]:
        if path.is_symlink():
            raise ProgramRefinementGepaCandidateError(
                f"GEPA optimizer output contains a symlink and cannot be copied: {path}"
            )


def _optimizer_payload_inventory(root: Path) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel == "manifest.json":
            continue
        files.append(
            {
                "path": rel,
                "sha256": _sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
    tree_text = json.dumps(
        files, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return {
        "hash_algorithm": "sha256",
        "tree_hash": hashlib.sha256(tree_text.encode("utf-8")).hexdigest(),
        "files": files,
        "excludes": ["manifest.json"],
    }


def _validate_optimizer_payload_inventory(
    root: Path, manifest: Mapping[str, Any]
) -> dict[str, Any]:
    declared = _safe_mapping(manifest.get("output_payload"))
    if declared.get("hash_algorithm") != "sha256":
        raise ProgramRefinementGepaCandidateError(
            "GEPA optimizer manifest must declare a sha256 output payload inventory"
        )
    declared_files = _safe_list(declared.get("files"))
    if not declared_files:
        raise ProgramRefinementGepaCandidateError(
            "GEPA optimizer manifest must hash-bind output payload files"
        )
    actual = _optimizer_payload_inventory(root)
    declared_by_path: dict[str, dict[str, Any]] = {}
    for item in declared_files:
        if not isinstance(item, Mapping):
            raise ProgramRefinementGepaCandidateError(
                "GEPA optimizer payload inventory entries must be objects"
            )
        rel = str(item.get("path") or "").strip()
        if not rel or rel.startswith("/") or ".." in Path(rel).parts:
            raise ProgramRefinementGepaCandidateError(
                "GEPA optimizer payload inventory contains an unsafe path"
            )
        declared_by_path[rel] = dict(item)
    actual_by_path = {str(item["path"]): item for item in actual["files"]}
    if set(actual_by_path) != set(declared_by_path):
        raise ProgramRefinementGepaCandidateError(
            "GEPA optimizer payload file set does not match manifest inventory"
        )
    for rel, actual_item in actual_by_path.items():
        declared_item = declared_by_path[rel]
        if declared_item.get("sha256") != actual_item.get("sha256"):
            raise ProgramRefinementGepaCandidateError(
                "GEPA optimizer payload hash does not match manifest inventory"
            )
        if declared_item.get("size_bytes") != actual_item.get("size_bytes"):
            raise ProgramRefinementGepaCandidateError(
                "GEPA optimizer payload size does not match manifest inventory"
            )
    if declared.get("tree_hash") != actual.get("tree_hash"):
        raise ProgramRefinementGepaCandidateError(
            "GEPA optimizer payload tree hash does not match manifest inventory"
        )
    return actual


def _copy_optimizer_output(
    source: Path, destination: Path, *, expected_manifest_hash: str
) -> dict[str, Any]:
    if not source.exists() or not source.is_dir():
        raise ProgramRefinementGepaCandidateError(
            f"GEPA optimizer output directory not found: {source}"
        )
    _validate_no_symlinks(source)
    manifest_path = source / "manifest.json"
    manifest = _load_json_object(manifest_path, label="GEPA optimizer manifest")
    if _sha256_file(manifest_path) != expected_manifest_hash:
        raise ProgramRefinementGepaCandidateError(
            "GEPA optimizer manifest hash changed before copy"
        )
    before = _validate_optimizer_payload_inventory(source, manifest)
    if destination.exists():
        raise ProgramRefinementGepaCandidateError(
            f"GEPA optimizer output destination already exists: {destination}"
        )
    try:
        shutil.copytree(source, destination, symlinks=False)
        _validate_no_symlinks(destination)
        copied_manifest_path = destination / "manifest.json"
        copied_manifest = _load_json_object(
            copied_manifest_path, label="copied GEPA optimizer manifest"
        )
        if _sha256_file(copied_manifest_path) != expected_manifest_hash:
            raise ProgramRefinementGepaCandidateError(
                "copied GEPA optimizer manifest hash changed during materialization"
            )
        after = _validate_optimizer_payload_inventory(destination, copied_manifest)
        if before.get("tree_hash") != after.get("tree_hash"):
            raise ProgramRefinementGepaCandidateError(
                "copied GEPA optimizer payload tree hash changed during materialization"
            )
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    return before


def _load_optimizer_manifest(
    *, optimizer_root: Path, expected_manifest_hash: str, source_program_hash: str
) -> tuple[dict[str, Any], Path]:
    manifest_path = optimizer_root / "manifest.json"
    try:
        size = manifest_path.stat().st_size
    except OSError as exc:
        raise ProgramRefinementGepaCandidateError(
            f"GEPA optimizer manifest is unreadable: {manifest_path}"
        ) from exc
    if size > _MAX_OPTIMIZER_MANIFEST_BYTES:
        raise ProgramRefinementGepaCandidateError(
            f"GEPA optimizer manifest is too large: {manifest_path}"
        )
    payload = _load_json_object(manifest_path, label="GEPA optimizer manifest")
    actual_hash = _sha256_file(manifest_path)
    if actual_hash != expected_manifest_hash:
        raise ProgramRefinementGepaCandidateError(
            "GEPA optimizer manifest hash does not match refinement sidecar"
        )
    program = _safe_mapping(payload.get("program"))
    program_hash = str(program.get("sha256") or "").strip()
    if not program_hash:
        raise ProgramRefinementGepaCandidateError(
            "GEPA optimizer manifest must hash-bind the source program"
        )
    if program_hash != source_program_hash:
        raise ProgramRefinementGepaCandidateError(
            "GEPA optimizer manifest source program hash does not match source candidate"
        )
    _validate_optimizer_payload_inventory(optimizer_root, payload)
    return payload, manifest_path


def _identity_matches_any(
    actual: Mapping[str, Any], expected_identities: Sequence[Mapping[str, str | None]]
) -> bool:
    if not actual:
        return False
    for expected in expected_identities:
        if all(
            expected_value is None or actual.get(key) == expected_value
            for key, expected_value in expected.items()
        ):
            return True
    return False


def _validate_gepa_result_base(
    payload: Mapping[str, Any],
    *,
    expected_identities: Sequence[Mapping[str, str | None]],
    label: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if payload.get("schema_version") != PROGRAM_REFINEMENT_GEPA_RESULT_SCHEMA:
        raise ProgramRefinementGepaCandidateError(
            f"{label} schema_version must be {PROGRAM_REFINEMENT_GEPA_RESULT_SCHEMA}"
        )
    source_identity = _safe_mapping(payload.get("source_identity"))
    if not _identity_matches_any(source_identity, expected_identities):
        raise ProgramRefinementGepaCandidateError(
            f"{label} identity does not match expected source identity"
        )
    if payload.get("candidate") is not None:
        raise ProgramRefinementGepaCandidateError(
            f"{label} must keep candidate null until explicit materialization"
        )
    effect = _safe_mapping(payload.get("effect"))
    invalid_effect = [
        key for key in _REQUIRED_FALSE_GEPA_EFFECT_FLAGS if effect.get(key) is not False
    ]
    if invalid_effect:
        raise ProgramRefinementGepaCandidateError(
            f"{label} widens effect flags: " + ", ".join(invalid_effect)
        )
    non_authority = _safe_mapping(payload.get("non_authority"))
    if non_authority.get("local_refinement_only") is not True:
        raise ProgramRefinementGepaCandidateError(
            f"{label} must be local-refinement-only"
        )
    invalid_non_authority = [
        key
        for key in _REQUIRED_FALSE_GEPA_NON_AUTHORITY_FLAGS
        if non_authority.get(key) is not False
    ]
    if invalid_non_authority:
        raise ProgramRefinementGepaCandidateError(
            f"{label} widens non-authority flags: " + ", ".join(invalid_non_authority)
        )
    return source_identity, _safe_mapping(payload.get("gepa_output"))


def validate_program_refinement_gepa_result_contract(
    payload: Mapping[str, Any],
    *,
    expected_identities: Sequence[Mapping[str, str | None]],
    label: str = "program GEPA refinement result",
    error_type: type[Exception] = ProgramRefinementGepaCandidateError,
    source_program_hash: str | None = None,
) -> dict[str, Any]:
    """Validate a GEPA refinement sidecar before a final consumer trusts it.

    The sidecar is local optimizer evidence only. When it claims materializer
    readiness and a current source program hash is supplied, this validator also
    re-reads the optimizer manifest and payload inventory so stale optimizer
    output cannot shape downstream summaries.
    """

    try:
        source_identity, gepa_output = _validate_gepa_result_base(
            payload,
            expected_identities=expected_identities,
            label=label,
        )
        readiness = _safe_mapping(gepa_output.get("readiness"))
        readiness_claim = readiness.get("ready_for_future_candidate_materializer")
        optimizer_manifest: dict[str, Any] | None = None
        optimizer_root: Path | None = None
        if readiness_claim is True:
            gepa = _safe_mapping(payload.get("gepa"))
            if payload.get("status") == "gepa_output_unverified":
                raise ProgramRefinementGepaCandidateError(
                    f"{label} readiness conflicts with unverified status"
                )
            if gepa.get("attempted") is not True or gepa.get("status") != "completed":
                raise ProgramRefinementGepaCandidateError(
                    f"{label} readiness requires a completed GEPA attempt"
                )
            if gepa_output.get("manifest_present") is not True:
                raise ProgramRefinementGepaCandidateError(
                    f"{label} readiness requires manifest_present true"
                )
            if gepa_output.get("manifest_valid") is not True:
                raise ProgramRefinementGepaCandidateError(
                    f"{label} readiness requires manifest_valid true"
                )
            if readiness.get("status") != "optimizer_output_hash_bound_not_candidate":
                raise ProgramRefinementGepaCandidateError(
                    f"{label} readiness status must be optimizer_output_hash_bound_not_candidate"
                )
            expected_hash = str(gepa_output.get("manifest_sha256") or "").strip()
            if not expected_hash:
                raise ProgramRefinementGepaCandidateError(
                    f"{label} readiness requires manifest_sha256"
                )
            optimizer_root = (
                Path(str(gepa_output.get("root_path") or "")).expanduser().resolve()
            )
            if source_program_hash is not None:
                optimizer_manifest, _ = _load_optimizer_manifest(
                    optimizer_root=optimizer_root,
                    expected_manifest_hash=expected_hash,
                    source_program_hash=source_program_hash,
                )
        return {
            "source_identity": source_identity,
            "ready_for_future_candidate_materializer": readiness_claim is True,
            "optimizer_root": optimizer_root,
            "optimizer_manifest": optimizer_manifest,
        }
    except ProgramRefinementGepaCandidateError as exc:
        if error_type is ProgramRefinementGepaCandidateError:
            raise
        raise error_type(str(exc)) from exc


def _load_ready_gepa_result(
    path: Path,
    *,
    source_identity: Mapping[str, str | None],
    source_program_hash: str,
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    payload = _load_json_object(path, label="program GEPA refinement result")
    validation = validate_program_refinement_gepa_result_contract(
        payload,
        expected_identities=[source_identity],
        source_program_hash=source_program_hash,
    )
    if validation["ready_for_future_candidate_materializer"] is not True:
        gepa_output = _safe_mapping(payload.get("gepa_output"))
        if gepa_output.get("manifest_present") is not True:
            raise ProgramRefinementGepaCandidateError(
                "GEPA optimizer output manifest must be present"
            )
        if gepa_output.get("manifest_valid") is not True:
            raise ProgramRefinementGepaCandidateError(
                "GEPA optimizer output manifest must be valid"
            )
        raise ProgramRefinementGepaCandidateError(
            "GEPA optimizer output is not ready for candidate materialization"
        )
    optimizer_manifest = validation.get("optimizer_manifest")
    optimizer_root = validation.get("optimizer_root")
    if not isinstance(optimizer_manifest, dict) or not isinstance(optimizer_root, Path):
        raise ProgramRefinementGepaCandidateError(
            "GEPA optimizer output was not revalidated for candidate materialization"
        )
    return payload, optimizer_manifest, optimizer_root

# summary: "Validates hash-bound deterministic program jury sidecars and their non-authority semantics."
# read_when:
#   - "Changing jury-result schemas, confined artifact refs, or behavior evidence binding."

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from dspx.services.artifact_boundary import (
    require_artifact_schema,
    require_false_envelope_flags,
    validate_confined_artifact,
)

PROGRAM_JURY_RESULTS_SCHEMA = "program-jury-results-v2"
ALLOWED_PROGRAM_JURY_RESULT_STATUSES = frozenset(
    {"executed", "insufficient_behavior_evidence"}
)

REQUIRED_FALSE_PROGRAM_JURY_EFFECT_FLAGS = (
    "program_files_mutated",
    "promotion_review_mutated",
    "new_candidate_generated",
    "oracle_index_mutated",
    "external_authority_mutated",
    "governance_mutated",
)

REQUIRED_FALSE_PROGRAM_JURY_NON_AUTHORITY_FLAGS = (
    "automatic_promotion",
    "winner_selection",
    "candidate_ranking",
    "oracle_ranking",
    "oracle_pruning",
    "oracle_promotion",
    "promotion_authority",
    "governance_authority",
    "external_mutation",
)

_CREATED_FROM_ARTIFACTS = (
    ("manifest_path", "manifest_sha256", "manifest", "manifest.json"),
    ("jury_path", "jury_sha256", "planned jury", "jury.json"),
    (
        "jury_selection_path",
        "jury_selection_sha256",
        "jury selection",
        "jury_selection.json",
    ),
    ("jury_rubric_path", "jury_rubric_sha256", "jury rubric", "jury_rubric.json"),
    (
        "behavior_results_path",
        "behavior_results_sha256",
        "behavior results",
        "behavior_results.json",
    ),
    (
        "behavior_episode_path",
        "behavior_episode_sha256",
        "behavior episode",
        "behavior_episode.json",
    ),
)


def _safe_mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _first_text(*values: object) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _resolve_valid_manifest_refs(
    valid_manifest_refs: Mapping[Path, str],
) -> dict[Path, str]:
    refs: dict[Path, str] = {}
    for path, digest in valid_manifest_refs.items():
        digest_text = str(digest or "").strip()
        if not digest_text:
            continue
        refs[path.expanduser().resolve()] = digest_text
    return refs


def _label_prefix(label: str) -> str:
    return str(label or "program jury results").strip() or "program jury results"


def validate_program_jury_results_contract(
    payload: Mapping[str, Any],
    *,
    valid_manifest_refs: Mapping[Path, str],
    label: str = "program jury results",
    error_type: type[ValueError] = ValueError,
    current_manifest_path: Path | None = None,
    current_behavior_results_sha256: str | None = None,
    current_behavior_episode_sha256: str | None = None,
    outside_root_message: str = "outside the bound manifest root",
    manifest_mismatch_message: str | None = None,
) -> Path:
    """Validate shared local-only deterministic program jury sidecar semantics.

    Returns the manifest path that the jury sidecar is bound to. Callers provide
    the set of manifest path/hash pairs that are legal in their context (for
    example current candidate only, or current plus source candidate).
    """

    prefix = _label_prefix(label)
    require_artifact_schema(
        payload,
        label=prefix,
        schema_version=PROGRAM_JURY_RESULTS_SCHEMA,
        error_type=error_type,
    )
    if payload.get("status") not in ALLOWED_PROGRAM_JURY_RESULT_STATUSES:
        raise error_type(
            f"{prefix} must have status executed or insufficient_behavior_evidence"
        )

    effect = _safe_mapping(payload.get("effect"))
    if effect.get("local_jury_evidence_only") is not True:
        raise error_type(f"{prefix} must be local jury evidence only")
    require_false_envelope_flags(
        payload,
        section="effect",
        keys=REQUIRED_FALSE_PROGRAM_JURY_EFFECT_FLAGS,
        label=prefix,
        error_type=error_type,
    )
    require_false_envelope_flags(
        payload,
        section="non_authority",
        keys=REQUIRED_FALSE_PROGRAM_JURY_NON_AUTHORITY_FLAGS,
        label=prefix,
        error_type=error_type,
    )
    created_from = _safe_mapping(payload.get("created_from"))
    raw_manifest_path = _first_text(created_from.get("manifest_path"))
    manifest_hash = _first_text(created_from.get("manifest_sha256"))
    if raw_manifest_path is None:
        raise error_type(
            f"{prefix} manifest_path is required for hash-bound v2 sidecars"
        )
    manifest_path = Path(raw_manifest_path).expanduser().resolve()
    resolved_refs = _resolve_valid_manifest_refs(valid_manifest_refs)
    expected_manifest_hash = resolved_refs.get(manifest_path)
    if expected_manifest_hash is None or manifest_hash != expected_manifest_hash:
        raise error_type(
            manifest_mismatch_message
            or f"{prefix} manifest sha256 does not match candidate/source manifest"
        )
    manifest_root = manifest_path.parent

    found_behavior_results_ref = False
    found_behavior_episode_ref = False
    for path_key, hash_key, artifact_label, expected_name in _CREATED_FROM_ARTIFACTS:
        raw_path = _first_text(created_from.get(path_key))
        if raw_path is None:
            if path_key in {"jury_path", "jury_selection_path", "jury_rubric_path"}:
                raise error_type(f"{prefix} {artifact_label} path is required")
            continue
        if path_key == "behavior_results_path":
            found_behavior_results_ref = True
        if path_key == "behavior_episode_path":
            found_behavior_episode_ref = True
        claimed_hash = _first_text(created_from.get(hash_key))
        if claimed_hash is None:
            raise error_type(
                f"{prefix} {hash_key} is required when {path_key} is present"
            )
        validate_confined_artifact(
            Path(raw_path),
            root=manifest_root,
            label=f"{prefix} {artifact_label}",
            expected_sha256=claimed_hash,
            expected_name=expected_name,
            error_type=error_type,
            outside_root_message=outside_root_message,
        )

    behavior_evidence = _safe_mapping(payload.get("behavior_evidence"))
    if behavior_evidence.get("behavior_results_present") is True:
        claimed_hash = _first_text(created_from.get("behavior_results_sha256"))
        if not found_behavior_results_ref or claimed_hash is None:
            raise error_type(
                f"{prefix} behavior_results evidence must include path and sha256"
            )
        if (
            current_manifest_path is not None
            and manifest_path == current_manifest_path.expanduser().resolve()
            and (
                current_behavior_results_sha256 is None
                or claimed_hash != current_behavior_results_sha256
            )
        ):
            raise error_type(
                f"{prefix} behavior_results_sha256 does not match current behavior results"
            )
    if behavior_evidence.get("behavior_episode_present") is True:
        claimed_hash = _first_text(created_from.get("behavior_episode_sha256"))
        if not found_behavior_episode_ref or claimed_hash is None:
            raise error_type(
                f"{prefix} behavior_episode evidence must include path and sha256"
            )
        if (
            current_manifest_path is not None
            and manifest_path == current_manifest_path.expanduser().resolve()
            and (
                current_behavior_episode_sha256 is None
                or claimed_hash != current_behavior_episode_sha256
            )
        ):
            raise error_type(
                f"{prefix} behavior_episode_sha256 does not match current behavior episode"
            )

    return manifest_path

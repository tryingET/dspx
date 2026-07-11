# summary: "Validates provider-backed program jury results, aggregates, evidence hashes, and non-authority envelopes."
# read_when:
#   - "Changing model-jury result schemas, aggregate consistency, or hash-bound evidence validation."

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

PROGRAM_MODEL_JURY_RESULTS_SCHEMA = "program-model-jury-results-v1"
ALLOWED_MODEL_JURY_RESULT_STATUSES = frozenset({"executed", "executed_with_failures"})
ALLOWED_MODEL_JURY_JUROR_STATUSES = frozenset({"judged", "failed"})
ALLOWED_MODEL_JURY_OUTCOMES = frozenset(
    {"supports_review_evidence", "withhold", "reject", "request_more_evidence"}
)

REQUIRED_FALSE_MODEL_JURY_EFFECT_FLAGS = (
    "program_files_mutated",
    "promotion_review_mutated",
    "new_candidate_generated",
    "oracle_index_mutated",
    "external_authority_mutated",
    "ak_mutated",
    "governance_mutated",
)

REQUIRED_FALSE_MODEL_JURY_NON_AUTHORITY_FLAGS = (
    "promotion_approval",
    "ranking_or_winner_selection",
    "domain_acceptance",
    "external_authority_apply",
    "canonical_mutation",
)


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


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve_valid_manifest_refs(
    valid_manifest_refs: Mapping[Path, str],
) -> dict[Path, str]:
    refs: dict[Path, str] = {}
    for path, digest in valid_manifest_refs.items():
        digest_text = str(digest or "").strip()
        if digest_text:
            refs[path.expanduser().resolve()] = digest_text
    return refs


def _validate_bound_artifact(
    *,
    path_text: str | None,
    hash_text: str | None,
    manifest_root: Path,
    expected_name: str,
    artifact_label: str,
    prefix: str,
    error_type: type[ValueError],
) -> None:
    if path_text is None:
        raise error_type(f"{prefix} {artifact_label} path is required")
    if hash_text is None:
        raise error_type(f"{prefix} {artifact_label} sha256 is required")
    path = Path(path_text).expanduser().resolve()
    if path.name != expected_name:
        raise error_type(f"{prefix} {artifact_label} path must be {expected_name}")
    try:
        path.relative_to(manifest_root)
    except ValueError as exc:
        raise error_type(
            f"{prefix} {artifact_label} path is outside the bound manifest root"
        ) from exc
    if not path.exists():
        raise error_type(f"{prefix} {artifact_label} path is missing: {path}")
    if _sha256_file(path) != hash_text:
        raise error_type(
            f"{prefix} {artifact_label} sha256 does not match current file"
        )


def _require_json_int(
    value: object,
    *,
    field_label: str,
    error_type: type[ValueError],
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise error_type(f"{field_label} must be an integer")
    return value


def _validate_juror_results(
    payload: Mapping[str, Any],
    *,
    label: str,
    error_type: type[ValueError],
) -> list[Mapping[str, Any]]:
    raw_results = payload.get("juror_results")
    if not isinstance(raw_results, list) or not raw_results:
        raise error_type(f"{label} must include juror_results")
    juror_results: list[Mapping[str, Any]] = []
    for index, raw_result in enumerate(raw_results):
        if not isinstance(raw_result, Mapping):
            raise error_type(f"{label} juror_results[{index}] must be an object")
        result = _safe_mapping(raw_result)
        status = result.get("status")
        if status not in ALLOWED_MODEL_JURY_JUROR_STATUSES:
            raise error_type(
                f"{label} juror_results[{index}].status must be judged or failed"
            )
        if status == "judged":
            judgment = result.get("judgment")
            if not isinstance(judgment, Mapping):
                raise error_type(
                    f"{label} juror_results[{index}].judgment must be an object"
                )
            outcome = judgment.get("outcome")
            if outcome not in ALLOWED_MODEL_JURY_OUTCOMES:
                raise error_type(
                    f"{label} juror_results[{index}].judgment.outcome must be "
                    "supports_review_evidence, withhold, reject, or request_more_evidence"
                )
        juror_results.append(result)
    return juror_results


def _expected_aggregate(juror_results: list[Mapping[str, Any]]) -> dict[str, Any]:
    counts = {
        "supports_review_evidence": 0,
        "withhold": 0,
        "reject": 0,
        "request_more_evidence": 0,
        "failed": 0,
    }
    for result in juror_results:
        if result.get("status") != "judged":
            counts["failed"] += 1
            continue
        judgment = _safe_mapping(result.get("judgment"))
        outcome = judgment.get("outcome")
        if outcome in counts:
            counts[outcome] += 1
        else:
            counts["failed"] += 1
    if counts["failed"]:
        recommendation = "withhold_until_failed_jurors_rerun"
    elif counts["reject"]:
        recommendation = "reject_or_redesign"
    elif counts["request_more_evidence"]:
        recommendation = "request_more_evidence"
    elif counts["withhold"]:
        recommendation = "withhold_for_owner_review"
    else:
        recommendation = "supports_review_evidence_only"
    return {"judgment_counts": counts, "recommendation": recommendation}


def _validate_model_jury_aggregate(
    payload: Mapping[str, Any],
    *,
    juror_results: list[Mapping[str, Any]],
    label: str,
    error_type: type[ValueError],
) -> None:
    expected = _expected_aggregate(juror_results)
    status = str(payload.get("status") or "")
    if expected["judgment_counts"]["failed"] and status != "executed_with_failures":
        raise error_type(
            f"{label} status must be executed_with_failures when jurors failed"
        )
    if not expected["judgment_counts"]["failed"] and status != "executed":
        raise error_type(f"{label} status must be executed when all jurors are judged")
    jury = _safe_mapping(payload.get("jury"))
    selected_count = _require_json_int(
        jury.get("selected_juror_count"),
        field_label=f"{label} selected_juror_count",
        error_type=error_type,
    )
    if selected_count != len(juror_results):
        raise error_type(
            f"{label} selected_juror_count must match juror_results length"
        )
    aggregate = _safe_mapping(payload.get("aggregate"))
    actual_counts = _safe_mapping(aggregate.get("judgment_counts"))
    for key, expected_count in expected["judgment_counts"].items():
        actual_count = _require_json_int(
            actual_counts.get(key),
            field_label=f"{label} aggregate judgment_counts.{key}",
            error_type=error_type,
        )
        if actual_count != expected_count:
            raise error_type(
                f"{label} aggregate judgment_counts do not match juror_results"
            )
    if aggregate.get("recommendation") != expected["recommendation"]:
        raise error_type(
            f"{label} aggregate recommendation does not match juror_results"
        )


def _validate_evidence_entry_hashes(
    payload: Mapping[str, Any],
    *,
    prefix: str,
    error_type: type[ValueError],
) -> None:
    evidence = _safe_mapping(payload.get("evidence"))
    entries = _safe_list(evidence.get("entries"))
    if not entries:
        raise error_type(f"{prefix} evidence entries are required")
    entry_count = _require_json_int(
        evidence.get("entry_count"),
        field_label=f"{prefix} evidence entry_count",
        error_type=error_type,
    )
    if entry_count != len(entries):
        raise error_type(f"{prefix} evidence entry_count must match entries length")
    for index, raw_entry in enumerate(entries):
        if not isinstance(raw_entry, Mapping):
            raise error_type(f"{prefix} evidence entry {index} must be an object")
        entry = _safe_mapping(raw_entry)
        path_text = _first_text(entry.get("path"))
        if path_text is None:
            raise error_type(f"{prefix} evidence entry {index} must include path")
        sha256 = _first_text(entry.get("sha256"))
        if sha256 is None:
            raise error_type(f"{prefix} evidence entry {index} must include sha256")
        path = Path(path_text).expanduser().resolve()
        if not path.exists():
            raise error_type(f"{prefix} evidence entry {index} path is missing: {path}")
        if _sha256_file(path) != sha256:
            raise error_type(
                f"{prefix} evidence entry {index} sha256 does not match current file"
            )


def validate_program_model_jury_results_contract(
    payload: Mapping[str, Any],
    *,
    label: str = "program model jury results",
    error_type: type[ValueError] = ValueError,
    valid_manifest_refs: Mapping[Path, str] | None = None,
) -> None:
    """Validate shared non-authoritative program model-jury evidence semantics."""

    if payload.get("schema_version") != PROGRAM_MODEL_JURY_RESULTS_SCHEMA:
        raise error_type(
            f"{label} schema_version must be {PROGRAM_MODEL_JURY_RESULTS_SCHEMA}"
        )
    if payload.get("status") not in ALLOWED_MODEL_JURY_RESULT_STATUSES:
        raise error_type(f"{label} must have status executed or executed_with_failures")
    non_authority = _safe_mapping(payload.get("non_authority"))
    invalid_non_authority = [
        key
        for key in REQUIRED_FALSE_MODEL_JURY_NON_AUTHORITY_FLAGS
        if non_authority.get(key) is not False
    ]
    if invalid_non_authority:
        raise error_type(
            f"{label} widens non-authority flags: " + ", ".join(invalid_non_authority)
        )
    effect = _safe_mapping(payload.get("effect"))
    if effect.get("model_jury_evidence_only") is not True:
        raise error_type(f"{label} must be evidence-only")
    invalid_effect = [
        key
        for key in REQUIRED_FALSE_MODEL_JURY_EFFECT_FLAGS
        if effect.get(key) is not False
    ]
    if invalid_effect:
        raise error_type(f"{label} widens effect flags: " + ", ".join(invalid_effect))
    jury = _safe_mapping(payload.get("jury"))
    if jury.get("provider_backed_model_calls") is not True:
        raise error_type(f"{label} must record provider-backed model calls")
    juror_results = _validate_juror_results(payload, label=label, error_type=error_type)
    if not any(str(item.get("status") or "") == "judged" for item in juror_results):
        raise error_type(f"{label} must include at least one judged juror result")
    _validate_model_jury_aggregate(
        payload, juror_results=juror_results, label=label, error_type=error_type
    )
    adjudicator = _safe_mapping(payload.get("adjudicator"))
    if adjudicator.get("promotion_authority") is not False:
        raise error_type(f"{label} adjudicator must not claim promotion authority")
    interpretation = _safe_mapping(payload.get("interpretation"))
    if interpretation.get("ready_for_promotion_decision") is not False:
        raise error_type(f"{label} must not claim promotion-decision readiness")

    if valid_manifest_refs is None:
        return
    created_from = _safe_mapping(payload.get("created_from"))
    raw_manifest_path = _first_text(created_from.get("manifest_path"))
    manifest_hash = _first_text(created_from.get("manifest_sha256"))
    if raw_manifest_path is None:
        raise error_type(f"{label} manifest_path is required for hash-bound sidecars")
    manifest_path = Path(raw_manifest_path).expanduser().resolve()
    if manifest_path.name != "manifest.json":
        raise error_type(f"{label} manifest path must be manifest.json")
    expected_manifest_hash = _resolve_valid_manifest_refs(valid_manifest_refs).get(
        manifest_path
    )
    if expected_manifest_hash is None or manifest_hash != expected_manifest_hash:
        raise error_type(f"{label} manifest sha256 does not match current manifest")
    manifest_root = manifest_path.parent
    for path_key, hash_key, artifact_label, expected_name in (
        ("jury_path", "jury_sha256", "planned jury", "jury.json"),
        (
            "jury_selection_path",
            "jury_selection_sha256",
            "jury selection",
            "jury_selection.json",
        ),
        ("jury_rubric_path", "jury_rubric_sha256", "jury rubric", "jury_rubric.json"),
    ):
        _validate_bound_artifact(
            path_text=_first_text(created_from.get(path_key)),
            hash_text=_first_text(created_from.get(hash_key)),
            manifest_root=manifest_root,
            expected_name=expected_name,
            artifact_label=artifact_label,
            prefix=label,
            error_type=error_type,
        )
    _validate_evidence_entry_hashes(payload, prefix=label, error_type=error_type)

# summary: "Records one deterministic receipt-bound local disposition from a foundry GEPA comparison jury."
# read_when:
#   - "Changing foundry comparison adjudication policy, local dispositions, or adjudication receipts."

from __future__ import annotations

import errno
import json
import os
import secrets
from pathlib import Path
from typing import Any, Mapping

from dspx.services.program_foundry_gepa_comparison_jury import (
    ProgramFoundryGepaComparisonJuryError,
    validate_successful_program_foundry_gepa_comparison_jury_receipt,
)
from dspx.services.program_foundry_gepa_proposal_io import (
    assert_path_descriptor_identity,
    read_regular_bytes,
)
from dspx.services.program_foundry_io import foundry_lock

PROGRAM_FOUNDRY_GEPA_COMPARISON_ADJUDICATION_SCHEMA = (
    "dspx-program-foundry-gepa-comparison-adjudication-v1"
)
PROGRAM_FOUNDRY_GEPA_COMPARISON_ADJUDICATION_POLICY = (
    "foundry-gepa-comparison-jury-disposition-v1"
)
ALLOWED_LOCAL_DISPOSITIONS = frozenset(
    {"promote_locally", "reject_locally", "require_review"}
)
_EXPECTED_COUNT_KEYS = frozenset(
    {
        "supports_review_evidence",
        "withhold",
        "reject",
        "request_more_evidence",
        "failed",
    }
)
_EXPECTED_AGGREGATE_KEYS = frozenset(
    {
        "judgment_counts",
        "blocking_concerns_present",
        "recommendation",
        "unique_improvement_requests",
    }
)
_ALLOWED_JURY_STATUSES = frozenset({"executed", "executed_with_failures"})


class ProgramFoundryGepaComparisonAdjudicationError(ValueError):
    """Raised when a comparison jury cannot be adjudicated safely."""


class ProgramFoundryGepaComparisonAdjudicationIndeterminateError(
    ProgramFoundryGepaComparisonAdjudicationError
):
    """Raised when an adjudication target may already have committed."""


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(read_regular_bytes(path, label=label).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProgramFoundryGepaComparisonAdjudicationError(
            f"{label} must be valid JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise ProgramFoundryGepaComparisonAdjudicationError(
            f"{label} must contain one JSON object"
        )
    return {str(key): value for key, value in payload.items()}


def _write_json_atomic_no_clobber(
    path: Path,
    payload: Mapping[str, Any],
    *,
    root_descriptor: int,
) -> None:
    target = path.expanduser().absolute()
    if (
        target.name != "comparison-adjudication.json"
        or target.parent.name != "gepa-experiment"
    ):
        raise ProgramFoundryGepaComparisonAdjudicationError(
            "comparison adjudication must use the canonical experiment path"
        )
    encoded = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    try:
        experiment_descriptor = os.open(
            "gepa-experiment",
            os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=root_descriptor,
        )
    except OSError as exc:
        raise ProgramFoundryGepaComparisonAdjudicationError(
            "comparison adjudication experiment directory cannot be opened safely"
        ) from exc
    temporary_name = (
        f".comparison-adjudication.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    )
    temporary_created = False
    published = False
    failure_in_flight = False
    try:
        assert_path_descriptor_identity(
            target.parent,
            experiment_descriptor,
            label="foundry GEPA experiment directory",
        )
        try:
            descriptor = os.open(
                temporary_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=experiment_descriptor,
            )
        except FileExistsError as exc:
            raise ProgramFoundryGepaComparisonAdjudicationError(
                "comparison adjudication temporary path collision"
            ) from exc
        temporary_created = True
        try:
            with os.fdopen(descriptor, "wb") as stream:
                descriptor = -1
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        os.link(
            temporary_name,
            target.name,
            src_dir_fd=experiment_descriptor,
            dst_dir_fd=experiment_descriptor,
            follow_symlinks=False,
        )
        published = True
        os.fsync(experiment_descriptor)
        os.fsync(root_descriptor)
    except ProgramFoundryGepaComparisonAdjudicationError:
        failure_in_flight = True
        raise
    except FileExistsError as exc:
        failure_in_flight = True
        raise ProgramFoundryGepaComparisonAdjudicationError(
            "comparison adjudication already exists"
        ) from exc
    except OSError as exc:
        failure_in_flight = True
        error_type = (
            ProgramFoundryGepaComparisonAdjudicationIndeterminateError
            if published
            else ProgramFoundryGepaComparisonAdjudicationError
        )
        raise error_type(
            "comparison adjudication persistence failed; a valid target may already be recorded"
            if published
            else "comparison adjudication persistence failed before publication"
        ) from exc
    finally:
        cleanup_error: OSError | None = None
        if temporary_created:
            try:
                os.unlink(temporary_name, dir_fd=experiment_descriptor)
            except OSError as exc:
                if exc.errno != errno.ENOENT:
                    cleanup_error = exc
        try:
            os.close(experiment_descriptor)
        except OSError as exc:
            cleanup_error = cleanup_error or exc
        if cleanup_error is not None and not failure_in_flight:
            error_type = (
                ProgramFoundryGepaComparisonAdjudicationIndeterminateError
                if published
                else ProgramFoundryGepaComparisonAdjudicationError
            )
            raise error_type(
                "comparison adjudication was recorded but temporary cleanup is indeterminate"
                if published
                else "comparison adjudication temporary cleanup failed before publication"
            ) from cleanup_error


def _validated_counts(aggregate: Mapping[str, Any]) -> dict[str, int]:
    raw_counts = aggregate.get("judgment_counts")
    if not isinstance(raw_counts, Mapping) or set(raw_counts) != _EXPECTED_COUNT_KEYS:
        raise ProgramFoundryGepaComparisonAdjudicationError(
            "comparison jury aggregate judgment_counts are not policy-recognized"
        )
    counts: dict[str, int] = {}
    for key in _EXPECTED_COUNT_KEYS:
        value = raw_counts.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ProgramFoundryGepaComparisonAdjudicationError(
                f"comparison jury aggregate count {key} must be a non-negative integer"
            )
        counts[key] = value
    if sum(counts.values()) < 1:
        raise ProgramFoundryGepaComparisonAdjudicationError(
            "comparison jury aggregate must contain at least one juror outcome"
        )
    return counts


def _validate_policy_aggregate(
    *,
    jury_status: object,
    aggregate: Mapping[str, Any],
) -> dict[str, int]:
    if jury_status not in _ALLOWED_JURY_STATUSES:
        raise ProgramFoundryGepaComparisonAdjudicationError(
            "comparison jury status is not policy-recognized"
        )
    if set(aggregate) != _EXPECTED_AGGREGATE_KEYS:
        raise ProgramFoundryGepaComparisonAdjudicationError(
            "comparison jury aggregate shape is not policy-recognized"
        )
    counts = _validated_counts(aggregate)
    if counts["failed"]:
        expected_status = "executed_with_failures"
        expected_recommendation = "withhold_until_failed_jurors_rerun"
    elif counts["reject"]:
        expected_status = "executed"
        expected_recommendation = "reject_or_redesign"
    elif counts["request_more_evidence"]:
        expected_status = "executed"
        expected_recommendation = "request_more_evidence"
    elif counts["withhold"]:
        expected_status = "executed"
        expected_recommendation = "withhold_for_owner_review"
    else:
        expected_status = "executed"
        expected_recommendation = "supports_review_evidence_only"
    if (
        jury_status != expected_status
        or aggregate.get("recommendation") != expected_recommendation
    ):
        raise ProgramFoundryGepaComparisonAdjudicationError(
            "comparison jury status or recommendation conflicts with judgment counts"
        )
    expected_blocking = bool(
        counts["reject"] or counts["request_more_evidence"] or counts["failed"]
    )
    if aggregate.get("blocking_concerns_present") is not expected_blocking:
        raise ProgramFoundryGepaComparisonAdjudicationError(
            "comparison jury blocking_concerns_present conflicts with judgment counts"
        )
    improvements = aggregate.get("unique_improvement_requests")
    if (
        not isinstance(improvements, list)
        or not all(isinstance(item, str) for item in improvements)
        or improvements != sorted(set(improvements))
    ):
        raise ProgramFoundryGepaComparisonAdjudicationError(
            "comparison jury improvement requests must be sorted unique strings"
        )
    return counts


def _local_disposition(
    *,
    jury_status: object,
    aggregate: Mapping[str, Any],
) -> tuple[str, str, list[str]]:
    counts = _validate_policy_aggregate(
        jury_status=jury_status,
        aggregate=aggregate,
    )
    recommendation = aggregate.get("recommendation")
    if (
        jury_status == "executed"
        and recommendation == "supports_review_evidence_only"
        and counts["supports_review_evidence"] > 0
        and all(
            counts[key] == 0
            for key in _EXPECTED_COUNT_KEYS - {"supports_review_evidence"}
        )
    ):
        return (
            "promote_locally",
            "eligible_local_candidate",
            ["all_jurors_support_review_evidence"],
        )
    if (
        jury_status == "executed"
        and recommendation == "reject_or_redesign"
        and counts["reject"] > 0
        and all(counts[key] == 0 for key in _EXPECTED_COUNT_KEYS - {"reject"})
    ):
        return (
            "reject_locally",
            "rejected_local_candidate",
            ["one_or_more_jurors_reject"],
        )
    reason_by_recommendation = {
        "withhold_until_failed_jurors_rerun": "juror_execution_failed_no_replay",
        "request_more_evidence": "jury_requests_more_evidence",
        "withhold_for_owner_review": "jury_withholds_for_review",
    }
    reason = reason_by_recommendation.get(
        str(recommendation),
        "jury_outcome_not_eligible_for_automatic_local_transition",
    )
    return "require_review", "held_for_local_review", [reason]


def build_program_foundry_gepa_comparison_adjudication(
    *,
    validated_jury: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a deterministic bounded-local disposition from validated jury evidence."""

    aggregate = validated_jury.get("aggregate")
    if not isinstance(aggregate, Mapping):
        raise ProgramFoundryGepaComparisonAdjudicationError(
            "comparison jury aggregate is required"
        )
    disposition, local_state, reason_codes = _local_disposition(
        jury_status=validated_jury.get("jury_status"),
        aggregate=aggregate,
    )
    return {
        "schema_version": PROGRAM_FOUNDRY_GEPA_COMPARISON_ADJUDICATION_SCHEMA,
        "status": "recorded",
        "disposition": disposition,
        "local_candidate_state": local_state,
        "proposal_id": validated_jury["proposal_id"],
        "policy": {
            "id": PROGRAM_FOUNDRY_GEPA_COMPARISON_ADJUDICATION_POLICY,
            "input_mode": "validated_comparison_jury_receipt_only",
            "deterministic": True,
            "models_rerun": False,
            "unknown_or_mixed_outcomes_fail_to_review": True,
        },
        "bindings": {
            "comparison_jury_receipt_path": str(validated_jury["jury_receipt_path"]),
            "comparison_jury_receipt_sha256": validated_jury["jury_receipt_sha256"],
            "jury_results_path": str(validated_jury["jury_result_path"]),
            "jury_results_sha256": validated_jury["jury_result_sha256"],
            "consumption_receipt_path": str(validated_jury["receipt_path"]),
            "consumption_receipt_sha256": validated_jury["receipt_sha256"],
            "source_manifest_path": str(validated_jury["source_manifest_path"]),
            "source_manifest_sha256": validated_jury["source_manifest_sha256"],
            "candidate_manifest_path": str(validated_jury["candidate_manifest_path"]),
            "candidate_manifest_sha256": validated_jury["candidate_manifest_sha256"],
            "comparison_path": str(validated_jury["comparison_path"]),
            "comparison_sha256": validated_jury["comparison_sha256"],
        },
        "jury_snapshot": {
            "jury_status": validated_jury["jury_status"],
            "aggregate": dict(aggregate),
        },
        "reason_codes": reason_codes,
        "effect": {
            "bounded_local_disposition_recorded": True,
            "candidate_files_mutated": False,
            "comparison_mutated": False,
            "models_rerun": False,
            "gepa_reexecuted": False,
            "winner_applied": False,
            "production_activation_applied": False,
            "external_authority_mutated": False,
            "governance_mutated": False,
            "ak_called": False,
        },
        "non_authority": {
            "bounded_local_disposition_only": True,
            "external_winner_selection": False,
            "production_promotion_authority": False,
            "activation_authority": False,
            "governance_authority": False,
            "external_authority_apply": False,
        },
    }


def validate_program_foundry_gepa_comparison_adjudication_contract(
    payload: Mapping[str, Any],
    *,
    validated_jury: Mapping[str, Any],
) -> None:
    """Require exact deterministic policy output for the current jury lineage."""

    expected = build_program_foundry_gepa_comparison_adjudication(
        validated_jury=validated_jury
    )
    if dict(payload) != expected:
        raise ProgramFoundryGepaComparisonAdjudicationError(
            "comparison adjudication or bound jury lineage drifted"
        )


def _adjudicate_program_foundry_gepa_comparison(
    *,
    comparison_jury_receipt_path: Path,
) -> dict[str, Any]:
    """Record or reuse one deterministic local disposition for a comparison jury."""

    jury_receipt_path = comparison_jury_receipt_path.expanduser().absolute()
    root = jury_receipt_path.parent.parent
    with foundry_lock(root) as root_descriptor:
        assert_path_descriptor_identity(root, root_descriptor, label="foundry root")
        try:
            validated_jury = (
                validate_successful_program_foundry_gepa_comparison_jury_receipt(
                    jury_receipt_path,
                    root_descriptor=root_descriptor,
                )
            )
        except ProgramFoundryGepaComparisonJuryError as exc:
            raise ProgramFoundryGepaComparisonAdjudicationError(str(exc)) from exc
        output_path = (
            Path(str(validated_jury["experiment_root"]))
            / "comparison-adjudication.json"
        )
        expected = build_program_foundry_gepa_comparison_adjudication(
            validated_jury=validated_jury
        )
        if output_path.exists():
            existing = _load_json(output_path, label="comparison adjudication")
            validate_program_foundry_gepa_comparison_adjudication_contract(
                existing,
                validated_jury=validated_jury,
            )
            return {**existing, "reused": True}
        if output_path.is_symlink():
            raise ProgramFoundryGepaComparisonAdjudicationError(
                "comparison adjudication must not be a symlink"
            )
        try:
            validated_after = (
                validate_successful_program_foundry_gepa_comparison_jury_receipt(
                    jury_receipt_path,
                    root_descriptor=root_descriptor,
                )
            )
        except ProgramFoundryGepaComparisonJuryError as exc:
            raise ProgramFoundryGepaComparisonAdjudicationError(str(exc)) from exc
        if validated_after != validated_jury:
            raise ProgramFoundryGepaComparisonAdjudicationError(
                "comparison jury lineage changed during adjudication"
            )
        _write_json_atomic_no_clobber(
            output_path,
            expected,
            root_descriptor=root_descriptor,
        )
        try:
            persisted = _load_json(output_path, label="comparison adjudication")
            validate_program_foundry_gepa_comparison_adjudication_contract(
                persisted,
                validated_jury=validated_jury,
            )
        except ProgramFoundryGepaComparisonAdjudicationIndeterminateError:
            raise
        except Exception as exc:
            raise ProgramFoundryGepaComparisonAdjudicationIndeterminateError(
                "comparison adjudication committed but terminal validation failed"
            ) from exc
        return {**persisted, "reused": False}


def adjudicate_program_foundry_gepa_comparison(
    *,
    comparison_jury_receipt_path: Path,
) -> dict[str, Any]:
    """Record or reuse one deterministic disposition with commit-aware errors."""

    receipt_path = comparison_jury_receipt_path.expanduser().absolute()
    output_path = receipt_path.parent / "comparison-adjudication.json"
    existed_before = output_path.exists() or output_path.is_symlink()
    try:
        return _adjudicate_program_foundry_gepa_comparison(
            comparison_jury_receipt_path=receipt_path,
        )
    except ProgramFoundryGepaComparisonAdjudicationIndeterminateError:
        raise
    except Exception as exc:
        if not existed_before and (output_path.exists() or output_path.is_symlink()):
            raise ProgramFoundryGepaComparisonAdjudicationIndeterminateError(
                "comparison adjudication may have committed before lock release"
            ) from exc
        if isinstance(exc, ProgramFoundryGepaComparisonAdjudicationError):
            raise
        raise ProgramFoundryGepaComparisonAdjudicationError(str(exc)) from exc

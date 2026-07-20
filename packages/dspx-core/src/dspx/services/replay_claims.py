# summary: "Defines the machine-readable claim boundary between receipt checks and replay reproduction evidence."
# read_when:
#   - "Changing receipt integrity, deterministic regeneration, runtime replay, semantic reproduction, or quality-reproduction claims."

"""Fail-closed claim taxonomy for DSPx receipt checks and local replay evidence."""

from __future__ import annotations

from typing import Any, Literal, Mapping

REPLAY_CLAIM_MATRIX_SCHEMA = "dspx-replay-claim-matrix-v1"

ReplayClaimMode = Literal[
    "check_only",
    "deterministic_regeneration",
    "runtime_execution_reproduction",
]
ReplayClaimStatus = Literal[
    "passed",
    "failed",
    "not_run",
    "not_evaluated",
    "not_established",
]

_DIMENSION_LEVELS = {
    "receipt_integrity_check": "current_receipt_and_declared_artifact_bindings",
    "deterministic_regeneration": "fresh_producer_output_identity",
    "runtime_execution_reproduction": "fresh_receipt_bound_runtime_evidence_identity",
    "semantic_reproduction": "independent_semantic_equivalence_evaluation",
    "quality_evaluation_reproduction": (
        "receipt_bound_quality_evaluation_identity_not_independent_approval"
    ),
}
_AUTHORITY_BOUNDARY = {
    "release_authority": False,
    "promotion_authority": False,
    "activation_authority": False,
    "governance_authority": False,
    "external_authority": False,
}
_ALLOWED_EXECUTION_STATUSES = {"passed", "failed", "not_established"}


def _dimension(status: ReplayClaimStatus, *, evidence_level: str) -> dict[str, str]:
    return {"status": status, "evidence_level": evidence_level}


def build_replay_claim_matrix(
    *,
    mode: ReplayClaimMode,
    receipt_integrity_status: ReplayClaimStatus,
    execution_status: ReplayClaimStatus = "not_established",
) -> dict[str, Any]:
    """Build and self-validate an additive replay claim matrix.

    ``check_only`` can establish receipt integrity only. Deterministic regeneration
    and runtime execution reproduction are mutually exclusive execution modes.
    Semantic equivalence is never inferred from byte/hash identity. Runtime replay
    can reproduce its receipt-bound quality evaluation, but that remains explicitly
    distinct from independent quality approval.
    """

    if receipt_integrity_status not in {"passed", "failed", "not_established"}:
        raise ValueError(
            "receipt integrity status must be passed, failed, or not_established"
        )
    if execution_status not in _ALLOWED_EXECUTION_STATUSES:
        raise ValueError("execution status must be passed, failed, or not_established")

    deterministic_status: ReplayClaimStatus = "not_run"
    runtime_status: ReplayClaimStatus = "not_run"
    quality_status: ReplayClaimStatus = "not_evaluated"
    if mode == "deterministic_regeneration":
        deterministic_status = execution_status
    elif mode == "runtime_execution_reproduction":
        runtime_status = execution_status
        quality_status = execution_status
    elif mode != "check_only":
        raise ValueError(f"unsupported replay claim mode: {mode!r}")

    payload = {
        "schema_version": REPLAY_CLAIM_MATRIX_SCHEMA,
        "mode": mode,
        "dimensions": {
            "receipt_integrity_check": _dimension(
                receipt_integrity_status,
                evidence_level=_DIMENSION_LEVELS["receipt_integrity_check"],
            ),
            "deterministic_regeneration": _dimension(
                deterministic_status,
                evidence_level=_DIMENSION_LEVELS["deterministic_regeneration"],
            ),
            "runtime_execution_reproduction": _dimension(
                runtime_status,
                evidence_level=_DIMENSION_LEVELS["runtime_execution_reproduction"],
            ),
            "semantic_reproduction": _dimension(
                "not_evaluated",
                evidence_level=_DIMENSION_LEVELS["semantic_reproduction"],
            ),
            "quality_evaluation_reproduction": _dimension(
                quality_status,
                evidence_level=_DIMENSION_LEVELS["quality_evaluation_reproduction"],
            ),
        },
        "release_claim_allowed": False,
        "authority": dict(_AUTHORITY_BOUNDARY),
    }
    validate_replay_claim_matrix(payload)
    return payload


def validate_replay_claim_matrix(
    value: object,
    *,
    expected_mode: ReplayClaimMode | None = None,
    require_success: bool = False,
) -> None:
    """Reject malformed, contradictory, or authority-widened claim matrices."""

    if not isinstance(value, Mapping):
        raise ValueError("replay claim matrix must be an object")
    payload = {str(key): item for key, item in value.items()}
    if set(payload) != {
        "schema_version",
        "mode",
        "dimensions",
        "release_claim_allowed",
        "authority",
    }:
        raise ValueError("replay claim matrix has unknown or missing fields")
    if payload.get("schema_version") != REPLAY_CLAIM_MATRIX_SCHEMA:
        raise ValueError("replay claim matrix schema_version is invalid")
    mode = payload.get("mode")
    if mode not in {
        "check_only",
        "deterministic_regeneration",
        "runtime_execution_reproduction",
    }:
        raise ValueError("replay claim matrix mode is invalid")
    if expected_mode is not None and mode != expected_mode:
        raise ValueError("replay claim matrix mode does not match expected mode")
    if payload.get("release_claim_allowed") is not False:
        raise ValueError("replay claim matrix must not grant a release claim")
    if payload.get("authority") != _AUTHORITY_BOUNDARY:
        raise ValueError("replay claim matrix authority boundary is invalid")

    raw_dimensions = payload.get("dimensions")
    if not isinstance(raw_dimensions, Mapping):
        raise ValueError("replay claim matrix dimensions must be an object")
    dimensions = {str(key): item for key, item in raw_dimensions.items()}
    if set(dimensions) != set(_DIMENSION_LEVELS):
        raise ValueError("replay claim matrix dimensions are incomplete or unknown")
    statuses: dict[str, str] = {}
    for name, evidence_level in _DIMENSION_LEVELS.items():
        raw_dimension = dimensions.get(name)
        if not isinstance(raw_dimension, Mapping):
            raise ValueError(f"replay claim dimension {name} must be an object")
        dimension = {str(key): item for key, item in raw_dimension.items()}
        if set(dimension) != {"status", "evidence_level"}:
            raise ValueError(f"replay claim dimension {name} has invalid fields")
        if dimension.get("evidence_level") != evidence_level:
            raise ValueError(f"replay claim dimension {name} evidence level is invalid")
        status = dimension.get("status")
        if status not in {
            "passed",
            "failed",
            "not_run",
            "not_evaluated",
            "not_established",
        }:
            raise ValueError(f"replay claim dimension {name} status is invalid")
        statuses[name] = str(status)

    receipt_status = statuses["receipt_integrity_check"]
    if receipt_status not in {"passed", "failed", "not_established"}:
        raise ValueError("receipt integrity claim status is incompatible")
    if statuses["semantic_reproduction"] != "not_evaluated":
        raise ValueError("replay evidence must not claim semantic reproduction")

    if mode == "check_only":
        if (
            statuses["deterministic_regeneration"] != "not_run"
            or statuses["runtime_execution_reproduction"] != "not_run"
        ):
            raise ValueError(
                "check-only evidence must not claim execution reproduction"
            )
        if statuses["quality_evaluation_reproduction"] != "not_evaluated":
            raise ValueError("check-only evidence must not claim quality reproduction")
    elif mode == "deterministic_regeneration":
        if statuses["deterministic_regeneration"] not in _ALLOWED_EXECUTION_STATUSES:
            raise ValueError("deterministic regeneration claim status is incompatible")
        if statuses["runtime_execution_reproduction"] != "not_run":
            raise ValueError("deterministic regeneration must not claim runtime replay")
        if statuses["quality_evaluation_reproduction"] != "not_evaluated":
            raise ValueError(
                "deterministic regeneration must not claim quality reproduction"
            )
    else:
        runtime_status = statuses["runtime_execution_reproduction"]
        if runtime_status not in _ALLOWED_EXECUTION_STATUSES:
            raise ValueError("runtime reproduction claim status is incompatible")
        if statuses["deterministic_regeneration"] != "not_run":
            raise ValueError(
                "runtime reproduction must not claim deterministic regeneration"
            )
        if statuses["quality_evaluation_reproduction"] != runtime_status:
            raise ValueError(
                "runtime and quality-evaluation reproduction statuses must match"
            )

    reproduction_passed = any(
        statuses[name] == "passed"
        for name in (
            "deterministic_regeneration",
            "runtime_execution_reproduction",
            "quality_evaluation_reproduction",
        )
    )
    if reproduction_passed and receipt_status != "passed":
        raise ValueError("passed reproduction claims require passed receipt integrity")

    if require_success:
        if receipt_status != "passed":
            raise ValueError(
                "successful replay claims require passed receipt integrity"
            )
        reproduced_dimension = {
            "deterministic_regeneration": "deterministic_regeneration",
            "runtime_execution_reproduction": "runtime_execution_reproduction",
        }.get(str(mode))
        if reproduced_dimension is None or statuses[reproduced_dimension] != "passed":
            raise ValueError(
                "successful replay claims require passed execution reproduction"
            )

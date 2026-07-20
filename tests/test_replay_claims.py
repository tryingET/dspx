# summary: "Tests the fail-closed taxonomy separating receipt checks from replay reproduction claims."
# read_when:
#   - "Changing replay claim modes, statuses, authority boundaries, or evidence validation."

from __future__ import annotations

from copy import deepcopy
from collections.abc import Mapping
from typing import cast

import pytest

from dspx.services.replay_claims import (
    build_replay_claim_matrix,
    validate_replay_claim_matrix,
)


def _mapping(value: object) -> Mapping[str, object]:
    assert isinstance(value, Mapping)
    return cast(Mapping[str, object], value)


def _status(matrix: Mapping[str, object], dimension: str) -> object:
    dimensions = _mapping(matrix["dimensions"])
    payload = _mapping(dimensions[dimension])
    return payload["status"]


def test_check_only_proves_receipt_integrity_and_no_reproduction() -> None:
    matrix = build_replay_claim_matrix(
        mode="check_only",
        receipt_integrity_status="passed",
    )

    assert matrix["schema_version"] == "dspx-replay-claim-matrix-v1"
    assert matrix["mode"] == "check_only"
    assert _status(matrix, "receipt_integrity_check") == "passed"
    assert _status(matrix, "deterministic_regeneration") == "not_run"
    assert _status(matrix, "runtime_execution_reproduction") == "not_run"
    assert _status(matrix, "semantic_reproduction") == "not_evaluated"
    assert _status(matrix, "quality_evaluation_reproduction") == "not_evaluated"
    assert matrix["release_claim_allowed"] is False
    assert not any(_mapping(matrix["authority"]).values())
    validate_replay_claim_matrix(matrix, expected_mode="check_only")


def test_deterministic_regeneration_does_not_claim_runtime_semantics_or_quality() -> (
    None
):
    matrix = build_replay_claim_matrix(
        mode="deterministic_regeneration",
        receipt_integrity_status="passed",
        execution_status="passed",
    )

    assert _status(matrix, "deterministic_regeneration") == "passed"
    assert _status(matrix, "runtime_execution_reproduction") == "not_run"
    assert _status(matrix, "semantic_reproduction") == "not_evaluated"
    assert _status(matrix, "quality_evaluation_reproduction") == "not_evaluated"
    validate_replay_claim_matrix(
        matrix,
        expected_mode="deterministic_regeneration",
        require_success=True,
    )


def test_runtime_reproduction_separates_semantics_from_quality_evidence() -> None:
    matrix = build_replay_claim_matrix(
        mode="runtime_execution_reproduction",
        receipt_integrity_status="passed",
        execution_status="passed",
    )

    assert _status(matrix, "deterministic_regeneration") == "not_run"
    assert _status(matrix, "runtime_execution_reproduction") == "passed"
    assert _status(matrix, "semantic_reproduction") == "not_evaluated"
    assert _status(matrix, "quality_evaluation_reproduction") == "passed"
    quality = matrix["dimensions"]["quality_evaluation_reproduction"]  # type: ignore[index]
    assert quality["evidence_level"] == (  # type: ignore[index]
        "receipt_bound_quality_evaluation_identity_not_independent_approval"
    )
    validate_replay_claim_matrix(
        matrix,
        expected_mode="runtime_execution_reproduction",
        require_success=True,
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda payload: payload.__setitem__("release_claim_allowed", True),
            "release claim",
        ),
        (
            lambda payload: payload["authority"].__setitem__(  # type: ignore[union-attr]
                "promotion_authority", True
            ),
            "authority boundary",
        ),
        (
            lambda payload: payload["dimensions"][  # type: ignore[index]
                "semantic_reproduction"
            ].__setitem__("status", "passed"),
            "semantic reproduction",
        ),
        (
            lambda payload: payload["dimensions"][  # type: ignore[index]
                "deterministic_regeneration"
            ].__setitem__("status", "passed"),
            "must not claim execution reproduction",
        ),
        (
            lambda payload: payload.__setitem__("unexpected", True),
            "unknown or missing fields",
        ),
    ],
)
def test_claim_matrix_rejects_authority_or_semantic_widening(
    mutation, message: str
) -> None:
    matrix = build_replay_claim_matrix(
        mode="check_only",
        receipt_integrity_status="passed",
    )
    tampered = deepcopy(matrix)
    mutation(tampered)

    with pytest.raises(ValueError, match=message):
        validate_replay_claim_matrix(tampered)


@pytest.mark.parametrize(
    "mode",
    ["deterministic_regeneration", "runtime_execution_reproduction"],
)
@pytest.mark.parametrize("receipt_status", ["failed", "not_established"])
def test_passed_reproduction_requires_passed_receipt_integrity(
    mode, receipt_status
) -> None:
    with pytest.raises(ValueError, match="require passed receipt integrity"):
        build_replay_claim_matrix(
            mode=mode,
            receipt_integrity_status=receipt_status,
            execution_status="passed",
        )


def test_success_validation_rejects_unestablished_execution() -> None:
    matrix = build_replay_claim_matrix(
        mode="runtime_execution_reproduction",
        receipt_integrity_status="passed",
        execution_status="not_established",
    )

    with pytest.raises(ValueError, match="passed execution reproduction"):
        validate_replay_claim_matrix(
            matrix,
            expected_mode="runtime_execution_reproduction",
            require_success=True,
        )


def test_expected_mode_rejects_signature_runtime_confusion() -> None:
    matrix = build_replay_claim_matrix(
        mode="deterministic_regeneration",
        receipt_integrity_status="passed",
        execution_status="passed",
    )

    with pytest.raises(ValueError, match="does not match expected mode"):
        validate_replay_claim_matrix(
            matrix,
            expected_mode="runtime_execution_reproduction",
        )

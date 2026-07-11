# summary: "Tests declared program quality criteria, scoring, and generated harness integration."
# read_when:
#   - "Changing quality criterion normalization, evaluation, or runtime status mapping."

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from dspx.services.program_intent import ProgramIntent
from dspx.services.program_quality_evaluation import (
    declared_quality_output_fields,
    evaluate_declared_quality,
    normalize_declared_quality_behavior_status,
    normalize_quality_criteria,
    runtime_status_with_declared_quality,
)
from dspx.services.program_service import materialize_program_from_intent


def _criteria() -> list[dict[str, object]]:
    return [
        {
            "id": "calibrated_response",
            "output_field": "response",
            "evaluator": "concept_coverage",
            "required_concept_groups": [
                ["failure", "failed"],
                ["unknown", "undetermined"],
                ["investigate", "investigation"],
            ],
            "forbidden_concepts": ["definitely caused"],
            "min_score": 1.0,
        }
    ]


def test_declared_quality_accepts_paraphrase_and_rejects_forbidden_claim() -> None:
    criteria = normalize_quality_criteria(_criteria(), outputs=["response"])

    passed = evaluate_declared_quality(
        criteria,
        {
            "response": "One test failed; the cause is undetermined and needs investigation."
        },
    )
    forbidden = evaluate_declared_quality(
        criteria,
        {
            "response": "One test failed for an unknown reason; investigate, but it was definitely caused by deployment."
        },
    )

    assert passed["status"] == "passed"
    assert passed["criteria"][0]["score"] == 1.0
    assert passed["quality_approved"] is False
    assert forbidden["status"] == "failed"
    assert forbidden["criteria"][0]["score"] == 0.0
    assert forbidden["criteria"][0]["forbidden_hits"] == ["definitely caused"]


def test_forbidden_claim_fails_even_when_min_score_is_zero() -> None:
    raw = _criteria()
    raw[0]["min_score"] = 0.0
    criteria = normalize_quality_criteria(raw, outputs=["response"])
    result = evaluate_declared_quality(
        criteria,
        {
            "response": "A failure is unknown; investigate, but it was definitely caused."
        },
    )
    assert result["status"] == "failed"
    assert result["criteria"][0]["forbidden_hits"] == ["definitely caused"]


def test_declared_quality_missing_output_fails_without_vacuous_score() -> None:
    criteria = normalize_quality_criteria(_criteria(), outputs=["response"])

    result = evaluate_declared_quality(criteria, {})

    assert result["status"] == "failed"
    assert result["criteria"][0]["missing_output"] is True
    assert result["criteria"][0]["score"] == 0.0


@pytest.mark.parametrize("threshold", [True, -0.1, 1.1, math.nan, math.inf])
def test_quality_threshold_must_be_finite_number(threshold: object) -> None:
    criteria = _criteria()
    criteria[0]["min_score"] = threshold
    with pytest.raises(ValueError, match="min_score must be finite"):
        normalize_quality_criteria(criteria, outputs=["response"])


def test_quality_contract_rejects_duplicate_unknown_and_wrong_output() -> None:
    duplicate = _criteria() * 2
    with pytest.raises(ValueError, match="duplicate quality criterion"):
        normalize_quality_criteria(duplicate, outputs=["response"])

    unknown = _criteria()
    unknown[0]["authority"] = True
    with pytest.raises(ValueError, match="unknown fields"):
        normalize_quality_criteria(unknown, outputs=["response"])

    wrong_output = _criteria()
    wrong_output[0]["output_field"] = "missing"
    with pytest.raises(ValueError, match="undeclared output"):
        normalize_quality_criteria(wrong_output, outputs=["response"])


def test_multiple_criteria_all_must_pass_and_ids_do_not_overwrite() -> None:
    criteria = _criteria()
    second = {
        **_criteria()[0],
        "id": "authority_boundary",
        "required_concept_groups": [["evidence"]],
        "forbidden_concepts": ["approved"],
    }
    normalized = normalize_quality_criteria([criteria[0], second], outputs=["response"])

    result = evaluate_declared_quality(
        normalized,
        {"response": "A failure has an unknown cause and needs investigation."},
    )

    assert result["status"] == "failed"
    assert result["criteria_total"] == 2
    assert [row["id"] for row in result["criteria"]] == [
        "calibrated_response",
        "authority_boundary",
    ]
    assert result["criteria_passed"] == 1


@pytest.mark.parametrize(
    ("execution_status", "quality_status", "expected"),
    [
        ("executed", "passed", "executed_quality_passed"),
        ("executed", "failed", "failed_quality"),
        ("executed_valid_review_only", "passed", "executed_valid_review_only"),
        ("executed_valid_review_only", "failed", "failed_quality"),
        ("failed_boundary", "passed", "failed_boundary"),
        ("degraded_missing_outputs", "failed", "degraded_missing_outputs"),
    ],
)
def test_declared_quality_runtime_status_compatibility_matrix(
    execution_status: str, quality_status: str, expected: str
) -> None:
    assert (
        runtime_status_with_declared_quality(execution_status, quality_status)
        == expected
    )


def test_declared_quality_helpers_expose_covered_fields_and_oracle_categories() -> None:
    criteria = normalize_quality_criteria(_criteria(), outputs=["response"])
    assert declared_quality_output_fields(criteria) == {"response"}
    assert (
        normalize_declared_quality_behavior_status("executed_quality_passed")
        == "passed"
    )
    assert normalize_declared_quality_behavior_status("failed_quality") == "failed"
    assert (
        normalize_declared_quality_behavior_status("executed_valid_review_only")
        == "executed"
    )
    assert normalize_declared_quality_behavior_status("executed") is None


def test_generated_example_harness_uses_declared_quality_instead_of_exact_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "0")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv(
        "DSPX_STUB_RESPONSE_JSON",
        json.dumps(
            {
                "reasoning": "bounded",
                "response": "One test failed; the cause is undetermined and needs investigation.",
            }
        ),
    )
    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="QualityHarnessProgram",
            objective="Produce calibrated evidence.",
            inputs=["observation"],
            outputs=["response"],
            examples=[
                {
                    "inputs": {"observation": "one failure"},
                    "outputs": {
                        "response": "This exact sentence is intentionally different."
                    },
                }
            ],
            quality_criteria=_criteria(),
        ),
        outdir=tmp_path / "candidate",
    )
    behavior = json.loads(
        (Path(artifact.root_path) / "behavior_results.json").read_text()
    )
    assert behavior["summary"]["status"] == "passed"
    assert behavior["examples"][0]["quality_evaluation"]["status"] == "passed"
    assert behavior["quality_evaluation"]["status"] == "passed"


def test_generated_example_harness_keeps_exact_match_for_uncovered_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "0")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv(
        "DSPX_STUB_RESPONSE_JSON",
        json.dumps(
            {
                "response": "One test failed for an unknown reason; investigate.",
                "citation": "WRONG",
            }
        ),
    )
    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="MixedQualityHarnessProgram",
            objective="Produce calibrated evidence with an exact citation.",
            inputs=["observation"],
            outputs=["response", "citation"],
            examples=[
                {
                    "inputs": {"observation": "one failure"},
                    "outputs": {
                        "response": "A different accepted paraphrase.",
                        "citation": "EXPECTED",
                    },
                }
            ],
            quality_criteria=_criteria(),
        ),
        outdir=tmp_path / "candidate",
    )

    behavior = json.loads(
        (Path(artifact.root_path) / "behavior_results.json").read_text()
    )

    assert behavior["quality_evaluation"]["status"] == "passed"
    assert behavior["summary"]["status"] == "failed"
    assert behavior["examples"][0]["notes"] == ["output mismatch: ['citation']"]


def test_no_declared_quality_remains_non_authoritative() -> None:
    result = evaluate_declared_quality([], {"response": "anything"})
    assert result == {
        "schema_version": "program-quality-evaluation-v1",
        "status": "not_declared",
        "criteria_total": 0,
        "criteria_passed": 0,
        "criteria_failed": 0,
        "criteria": [],
        "quality_approved": False,
    }

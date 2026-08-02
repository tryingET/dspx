# summary: "Scores AK-4506 codebook-constrained semantic responses against hidden exact labels."
# read_when:
#   - "Changing deterministic semantic code labels, evidence-reference metrics, or confidence gates."

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dspx.services.program_oracle_semantic_contract import (
    REQUIRED_ANALYSIS_FIELDS,
    OracleSemanticAnalysis,
)
from dspx.services.program_oracle_semantic_evaluation import (
    SemanticAnalysisEvaluationError,
    _mapping,
    _sequence,
)

_CODE_FIELDS = REQUIRED_ANALYSIS_FIELDS[:-1]


def _string_list(value: object, label: str) -> list[str]:
    items = _sequence(value, label)
    if any(not isinstance(item, str) or not item for item in items):
        raise SemanticAnalysisEvaluationError(f"{label} must contain non-empty strings")
    return [str(item) for item in items]


def score_analysis(
    case: Mapping[str, Any], analysis: Mapping[str, Any]
) -> dict[str, Any]:
    parsed = OracleSemanticAnalysis.from_mapping(analysis)
    normalized_analysis = parsed.to_dict()
    labels = _mapping(case.get("hidden_labels"), "case.hidden_labels")
    provider_request = _mapping(case.get("provider_request"), "case.provider_request")
    quality = _mapping(
        provider_request.get("quality_contract"),
        "case.provider_request.quality_contract",
    )
    codebook = _mapping(quality.get("analysis_codebook"), "analysis_codebook")
    expected_codes = _mapping(labels.get("expected_codes"), "expected_codes")
    forbidden_codes = _mapping(labels.get("forbidden_codes"), "forbidden_codes")

    field_results: list[dict[str, Any]] = []
    for field in _CODE_FIELDS:
        allowed = set(_string_list(codebook.get(field), f"codebook.{field}"))
        expected = set(
            _string_list(expected_codes.get(field), f"expected_codes.{field}")
        )
        forbidden = set(
            _string_list(forbidden_codes.get(field), f"forbidden_codes.{field}")
        )
        actual_list = _string_list(normalized_analysis[field], f"analysis.{field}")
        actual = set(actual_list)
        unknown_hits = sorted(actual - allowed)
        forbidden_hits = sorted(actual & forbidden)
        duplicates = len(actual_list) != len(actual)
        matched = (
            actual == expected
            and not unknown_hits
            and not forbidden_hits
            and not duplicates
        )
        field_results.append(
            {
                "field": field,
                "matched": matched,
                "contradiction": bool(forbidden_hits),
                "expected_codes": sorted(expected),
                "observed_codes": sorted(actual),
                "forbidden_code_hits": forbidden_hits,
                "unknown_code_hits": unknown_hits,
                "duplicate_codes": duplicates,
            }
        )
    matched_fields = sum(1 for item in field_results if item["matched"])
    expected_code_exactness = matched_fields / len(field_results)

    cited_refs = set(str(item) for item in normalized_analysis["evidence_refs"])
    expected_refs = set(
        _string_list(labels.get("expected_evidence_refs"), "expected_evidence_refs")
    )
    forbidden_refs = set(
        _string_list(labels.get("forbidden_evidence_refs"), "forbidden_evidence_refs")
    )
    expected_cited = cited_refs & expected_refs
    evidence_ref_recall = len(expected_cited) / len(expected_refs)
    evidence_ref_precision = (
        len(expected_cited) / len(cited_refs) if cited_refs else 0.0
    )
    forbidden_ref_hits = sorted(cited_refs & forbidden_refs)

    confidence = float(normalized_analysis["confidence"])
    confidence_min = labels.get("confidence_min")
    confidence_max = labels.get("confidence_max")
    if (
        isinstance(confidence_min, bool)
        or not isinstance(confidence_min, (int, float))
        or isinstance(confidence_max, bool)
        or not isinstance(confidence_max, (int, float))
    ):
        raise SemanticAnalysisEvaluationError("confidence label bounds must be numbers")
    confidence_ok = float(confidence_min) <= confidence <= float(confidence_max)
    status = (
        "passed"
        if expected_code_exactness == 1.0
        and evidence_ref_recall == 1.0
        and evidence_ref_precision == 1.0
        and not forbidden_ref_hits
        and confidence_ok
        else "failed"
    )
    return {
        "status": status,
        "score": 1.0 if status == "passed" else 0.0,
        "expected_code_exactness": expected_code_exactness,
        "evidence_ref_recall": evidence_ref_recall,
        "evidence_ref_precision": evidence_ref_precision,
        "forbidden_ref_hits": forbidden_ref_hits,
        "confidence_ok": confidence_ok,
        "field_results": field_results,
    }

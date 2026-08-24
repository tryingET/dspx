# summary: "Authority-false semantic validation for exact bound v11 cases."
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, final

from dspx.services.program_oracle_semantic_contract import OracleSemanticAnalysis
from dspx.services.program_oracle_semantic_contract_v11 import (
    BoundContractCase,
    SemanticV11Error,
    canonical,
    mapping,
    sha256,
)

SemanticResultOutcome = Literal["score_pass", "score_miss", "semantic_error"]


_CODE_FIELDS = (
    "observations",
    "failure_attractors",
    "quality_contract_violations",
    "hypotheses",
    "recommended_experiments",
)


def _provider_visible_refs(value: object) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key == "ref":
                if not isinstance(item, str) or not item:
                    raise SemanticV11Error("provider-visible evidence ref rejected")
                refs.add(item)
            else:
                refs.update(_provider_visible_refs(item))
    elif isinstance(value, list):
        for item in value:
            refs.update(_provider_visible_refs(item))
    return refs


def _validate_bounded_analysis(
    case: BoundContractCase, analysis: Mapping[str, Any]
) -> None:
    """Reject non-codebook or non-evidence strings before any retention write."""

    request = case.materialized_request()
    quality = request.quality_contract
    if not isinstance(quality, Mapping):
        raise SemanticV11Error("case semantic codebook unavailable")
    codebook = quality.get("analysis_codebook")
    if not isinstance(codebook, Mapping) or set(codebook) != set(_CODE_FIELDS):
        raise SemanticV11Error("case semantic codebook drift")
    for field in _CODE_FIELDS:
        allowed = codebook.get(field)
        selected = analysis.get(field)
        if (
            not isinstance(allowed, list)
            or not allowed
            or any(not isinstance(code, str) or not code for code in allowed)
            or not isinstance(selected, list)
            or any(
                not isinstance(code, str) or code not in allowed for code in selected
            )
            or len(selected) != len(set(selected))
        ):
            raise SemanticV11Error("semantic analysis code outside frozen codebook")
    refs = analysis.get("evidence_refs")
    visible = _provider_visible_refs(request.evidence)
    if (
        not isinstance(refs, list)
        or any(not isinstance(ref, str) or ref not in visible for ref in refs)
        or len(refs) != len(set(refs))
    ):
        raise SemanticV11Error("semantic analysis evidence ref not provider-visible")


def _closed(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    result = json.loads(canonical(value))
    if not isinstance(result, dict):
        raise SemanticV11Error("semantic report mapping drift")
    return result


@dataclass(frozen=True, slots=True)
class _SemanticRecord:
    case_id: str
    outcome: SemanticResultOutcome
    analysis: Mapping[str, Any] | None
    score: Mapping[str, Any] | None
    analysis_sha256: str | None


@final
class SemanticValidationReport:
    """Plain authority-false result of bounded semantic validation."""

    case_id: str
    outcome: SemanticResultOutcome
    analysis_sha256: str | None
    _analysis: dict[str, Any] | None
    _score: dict[str, Any] | None
    _sealed: bool

    __slots__ = (
        "case_id",
        "outcome",
        "analysis_sha256",
        "_analysis",
        "_score",
        "_sealed",
    )

    def __init__(
        self,
        case_id: str,
        outcome: SemanticResultOutcome,
        analysis: Mapping[str, Any] | None,
        score: Mapping[str, Any] | None,
        analysis_sha256: str | None,
    ) -> None:
        object.__setattr__(self, "case_id", case_id)
        object.__setattr__(self, "outcome", outcome)
        object.__setattr__(self, "analysis_sha256", analysis_sha256)
        object.__setattr__(self, "_analysis", _closed(analysis))
        object.__setattr__(self, "_score", _closed(score))
        object.__setattr__(self, "_sealed", True)

    def __init_subclass__(cls, **_kwargs: object) -> None:
        raise TypeError("SemanticValidationReport is sealed")

    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "_sealed", False):
            raise TypeError("SemanticValidationReport is immutable")
        object.__setattr__(self, name, value)

    @property
    def analysis(self) -> Mapping[str, Any] | None:
        return _closed(self._analysis)

    @property
    def score(self) -> Mapping[str, Any] | None:
        return _closed(self._score)

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "outcome": self.outcome,
            "analysis": _closed(self._analysis),
            "score": _closed(self._score),
            "analysis_sha256": self.analysis_sha256,
        }

    def payload(self) -> dict[str, Any]:
        return {
            **self.semantic_payload(),
            "fixture_only": True,
            "v11_authorized": False,
            "live_execution_authorized": False,
            "authority_granted": False,
        }


def _close_report(record: _SemanticRecord) -> SemanticValidationReport:
    return SemanticValidationReport(
        record.case_id,
        record.outcome,
        record.analysis,
        record.score,
        record.analysis_sha256,
    )


def _validate_semantic(case: BoundContractCase, raw: str) -> _SemanticRecord:
    """Parse and score bounded text without constructing a report capability."""

    if type(case) is not BoundContractCase or not isinstance(raw, str):
        raise SemanticV11Error("bound semantic case and text required")
    case.require_canonical()
    text = raw.strip()
    if text.startswith("```") and text.endswith("```"):
        text = "\n".join(text.splitlines()[1:-1]).strip()
    try:
        value = json.loads(text)
        analysis = OracleSemanticAnalysis.from_mapping(
            mapping(value, "analysis")
        ).to_dict()
        _validate_bounded_analysis(case, analysis)
        score = case.score(analysis)
    except (json.JSONDecodeError, SemanticV11Error, TypeError, ValueError):
        return _SemanticRecord(case.case_id, "semantic_error", None, None, None)
    outcome: SemanticResultOutcome = (
        "score_pass" if score.get("status") == "passed" else "score_miss"
    )
    return _SemanticRecord(
        case.case_id, outcome, analysis, score, sha256(canonical(analysis))
    )


def _semantic_error(case: BoundContractCase) -> _SemanticRecord:
    if type(case) is not BoundContractCase:
        raise SemanticV11Error("bound semantic case required")
    case.require_canonical()
    return _SemanticRecord(case.case_id, "semantic_error", None, None, None)


def validate_semantic_response(
    case: BoundContractCase, raw: str
) -> SemanticValidationReport:
    """Pure provider-text validator; no live function accepts its output."""

    return _close_report(_validate_semantic(case, raw))


def semantic_error_report(case: BoundContractCase) -> SemanticValidationReport:
    return _close_report(_semantic_error(case))


def validate_retained_semantic_result(
    case: BoundContractCase, value: object
) -> dict[str, Any]:
    """Independently re-score one retained bounded semantic payload."""

    if type(case) is not BoundContractCase or not isinstance(value, Mapping):
        raise SemanticV11Error("retained semantic result capability drift")
    case.require_canonical()
    semantic = dict(value)
    if (
        set(semantic) != {"case_id", "outcome", "analysis", "score", "analysis_sha256"}
        or semantic.get("case_id") != case.case_id
    ):
        raise SemanticV11Error("retained semantic result schema drift")
    outcome = semantic.get("outcome")
    if outcome == "semantic_error":
        if any(
            semantic.get(key) is not None
            for key in ("analysis", "score", "analysis_sha256")
        ):
            raise SemanticV11Error("retained semantic error custody drift")
        return semantic
    analysis = semantic.get("analysis")
    score = semantic.get("score")
    if not isinstance(analysis, Mapping) or not isinstance(score, Mapping):
        raise SemanticV11Error("retained semantic score custody drift")
    _validate_bounded_analysis(case, analysis)
    expected_score = case.score(analysis)
    expected_outcome = (
        "score_pass" if expected_score.get("status") == "passed" else "score_miss"
    )
    if (
        outcome != expected_outcome
        or canonical(score) != canonical(expected_score)
        or semantic.get("analysis_sha256") != sha256(canonical(analysis))
    ):
        raise SemanticV11Error("retained semantic score derivation drift")
    return semantic


# Compatibility name remains pure and authority-false; no live writer accepts it.
evaluate_semantic_response = validate_semantic_response

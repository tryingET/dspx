# summary: "Opaque, contract-bound deterministic semantic result custody for v11."
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Literal

from dspx.services.program_oracle_semantic_contract import OracleSemanticAnalysis
from dspx.services.program_oracle_semantic_contract_v11 import (
    BoundContractCase,
    SemanticV11Error,
    canonical,
    mapping,
    sha256,
)

SemanticResultOutcome = Literal["score_pass", "score_miss", "semantic_error"]
_SEMANTIC_RESULT_TOKEN = object()


class VerifiedSemanticResult:
    """Opaque result scored only against an exact bound contract case."""

    __slots__ = (
        "case_id",
        "outcome",
        "analysis_sha256",
        "_case",
        "_analysis_raw",
        "_score_raw",
        "_sealed",
    )

    case_id: str
    outcome: SemanticResultOutcome
    analysis_sha256: str | None
    _case: BoundContractCase
    _analysis_raw: bytes | None
    _score_raw: bytes | None
    _sealed: bool

    def __init__(
        self,
        *,
        case: BoundContractCase,
        outcome: SemanticResultOutcome,
        analysis: Mapping[str, Any] | None,
        score: Mapping[str, Any] | None,
        analysis_sha256: str | None,
        token: object,
    ) -> None:
        if token is not _SEMANTIC_RESULT_TOKEN:
            raise TypeError(
                "VerifiedSemanticResult is created by deterministic scoring"
            )
        if type(case) is not BoundContractCase:
            raise SemanticV11Error("semantic result case capability drift")
        case.require_canonical()
        object.__setattr__(self, "case_id", case.case_id)
        object.__setattr__(self, "outcome", outcome)
        object.__setattr__(self, "_case", case)
        object.__setattr__(
            self, "_analysis_raw", canonical(analysis) if analysis is not None else None
        )
        object.__setattr__(
            self, "_score_raw", canonical(score) if score is not None else None
        )
        object.__setattr__(self, "analysis_sha256", analysis_sha256)
        object.__setattr__(self, "_sealed", True)
        self.payload()

    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "_sealed", False):
            raise TypeError("VerifiedSemanticResult is immutable")
        object.__setattr__(self, name, value)

    @property
    def analysis(self) -> Mapping[str, Any] | None:
        """Return a fresh decoded projection, never retained mutable state."""

        if self._analysis_raw is None:
            return None
        value = json.loads(self._analysis_raw)
        if not isinstance(value, dict):
            raise SemanticV11Error("semantic analysis custody drift")
        return value

    @property
    def score(self) -> Mapping[str, Any] | None:
        """Return a fresh decoded projection, never retained mutable state."""

        if self._score_raw is None:
            return None
        value = json.loads(self._score_raw)
        if not isinstance(value, dict):
            raise SemanticV11Error("semantic score custody drift")
        return value

    def payload(self) -> dict[str, Any]:
        if type(self) is not VerifiedSemanticResult:
            raise SemanticV11Error("semantic result type drift")
        self._case.require_canonical()
        if self.case_id != self._case.case_id:
            raise SemanticV11Error("semantic result case drift")
        analysis = self.analysis
        score = self.score
        if self.outcome == "semantic_error":
            if (
                analysis is not None
                or score is not None
                or self.analysis_sha256 is not None
            ):
                raise SemanticV11Error("semantic error result custody drift")
        else:
            if analysis is None or score is None:
                raise SemanticV11Error("semantic scored result custody drift")
            expected_score = self._case.score(analysis)
            expected_outcome: SemanticResultOutcome = (
                "score_pass"
                if expected_score.get("status") == "passed"
                else "score_miss"
            )
            if (
                canonical(score) != canonical(expected_score)
                or self.outcome != expected_outcome
                or self.analysis_sha256 != sha256(canonical(analysis))
            ):
                raise SemanticV11Error("semantic scored result derivation drift")
        return {
            "case_id": self.case_id,
            "outcome": self.outcome,
            "analysis": analysis,
            "score": score,
            "analysis_sha256": self.analysis_sha256,
        }


def evaluate_semantic_response(
    case: BoundContractCase, raw: str
) -> VerifiedSemanticResult:
    """Parse and score one bounded response against the exact contract case."""

    if type(case) is not BoundContractCase:
        raise SemanticV11Error("bound semantic case required")
    case.require_canonical()
    text = raw.strip()
    if text.startswith("```") and text.endswith("```"):
        text = "\n".join(text.splitlines()[1:-1]).strip()
    try:
        value = json.loads(text)
        analysis = OracleSemanticAnalysis.from_mapping(
            mapping(value, "analysis")
        ).to_dict()
        score = case.score(analysis)
    except (json.JSONDecodeError, SemanticV11Error, TypeError, ValueError):
        return semantic_error_result(case)
    outcome: SemanticResultOutcome = (
        "score_pass" if score.get("status") == "passed" else "score_miss"
    )
    return VerifiedSemanticResult(
        case=case,
        outcome=outcome,
        analysis=analysis,
        score=score,
        analysis_sha256=sha256(canonical(analysis)),
        token=_SEMANTIC_RESULT_TOKEN,
    )


def semantic_error_result(case: BoundContractCase) -> VerifiedSemanticResult:
    if type(case) is not BoundContractCase:
        raise SemanticV11Error("bound semantic case required")
    case.require_canonical()
    return VerifiedSemanticResult(
        case=case,
        outcome="semantic_error",
        analysis=None,
        score=None,
        analysis_sha256=None,
        token=_SEMANTIC_RESULT_TOKEN,
    )

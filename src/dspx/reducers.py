from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence

from .multi_provider_lm import ProviderResult


@dataclass
class ReduceResult:
    winner_index: int
    scores: Dict[int, float]
    rationale: Optional[str] = None
    threshold_passed: bool = False


class HeuristicReducer:
    """Simple reducer using lightweight heuristics.

    Scoring combines:
    - JSON parse success bonus (if require_json is True, non-JSON gets 0).
    - Keyword coverage bonus.
    - Length score (log-scaled) with an upper cap.
    """

    def __init__(
        self,
        *,
        require_json: bool = False,
        keywords: Optional[Sequence[str]] = None,
        length_cap: int = 4000,
    ) -> None:
        self.require_json = require_json
        self.keywords = [k for k in (keywords or []) if k]
        self.length_cap = max(1, int(length_cap))

    def pick(self, candidates: Sequence[ProviderResult], context: Optional[Dict[str, Any]] = None) -> ReduceResult:
        scores: Dict[int, float] = {}
        best_i = 0
        best_s = float("-inf")
        for i, r in enumerate(candidates):
            s = 0.0
            text = (r.text or "").strip()
            # JSON bonus or requirement
            json_bonus = 0.0
            if text:
                if self.require_json:
                    try:
                        import json

                        json.loads(text)
                        json_bonus = 1.0
                    except Exception:
                        json_bonus = -1000.0  # effectively disqualify
                else:
                    try:
                        import json

                        json.loads(text)
                        json_bonus = 0.5
                    except Exception:
                        json_bonus = 0.0
            s += json_bonus
            # Keyword coverage
            if self.keywords:
                cov = sum(1 for k in self.keywords if k in text)
                s += cov / max(1, len(self.keywords))
            # Length (log scale, capped)
            L = min(len(text), self.length_cap)
            import math

            s += math.log(1 + L) / math.log(1 + self.length_cap)
            scores[i] = s
            if s > best_s:
                best_s, best_i = s, i
        return ReduceResult(winner_index=best_i, scores=scores, rationale=None, threshold_passed=False)


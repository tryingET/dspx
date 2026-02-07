from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class RouteCandidate:
    project_key: str
    score: int
    reasons: list[str]


def _load_project_keys() -> list[str]:
    mpj = os.getenv("DSPX_GITLAB_PROJECT_MAP_JSON")
    mpf = os.getenv("DSPX_GITLAB_PROJECT_MAP_FILE")
    data = None
    if mpj:
        try:
            data = json.loads(mpj)
        except Exception:
            data = None
    if data is None and mpf:
        try:
            data = json.loads(Path(mpf).read_text(encoding="utf-8"))
        except Exception:
            data = None
    if isinstance(data, dict):
        return sorted([str(k) for k in data.keys()])
    return [
        "core",
        "holdingco",
        "financeco",
        "healthco",
        "houseco",
        "teachingco",
        "softwareco",
    ]


_keyword_map = {
    "finance": "financeco",
    "health": "healthco",
    "house": "houseco",
    "teaching": "teachingco",
    "school": "teachingco",
    "software": "softwareco",
}


def route_candidates(
    text: str, *, project_keys: Iterable[str] | None = None
) -> list[RouteCandidate]:
    keys = list(project_keys) if project_keys is not None else _load_project_keys()
    t = (text or "").lower()
    scores: dict[str, RouteCandidate] = {
        k: RouteCandidate(project_key=k, score=0, reasons=[]) for k in keys
    }

    for kw, pk in _keyword_map.items():
        if kw in t and pk in scores:
            c = scores[pk]
            scores[pk] = RouteCandidate(
                project_key=pk,
                score=c.score + 10,
                reasons=c.reasons + [f"keyword:{kw}"],
            )

    # Slight bias to core if nothing else.
    if "core" in scores:
        c = scores["core"]
        scores["core"] = RouteCandidate(
            project_key="core", score=c.score + 1, reasons=c.reasons + ["default"]
        )

    return sorted(scores.values(), key=lambda c: (-c.score, c.project_key))[:3]

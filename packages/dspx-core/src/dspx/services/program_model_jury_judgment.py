"""Closed parsing contract for retained model-jury judgments."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from dspx.services.program_model_jury_provider_runtime import (
    ProgramModelJuryExecutionError,
)

_JUDGMENT_KEYS = {
    "outcome",
    "rationale",
    "evidence_strengths",
    "concerns",
    "improvement_requests",
    "confidence",
}
_OUTCOMES = {
    "supports_review_evidence",
    "withhold",
    "reject",
    "request_more_evidence",
}
_CONFIDENCE = {"low", "medium", "high", "unknown"}
_MAX_RATIONALE_BYTES = 4096
_MAX_LIST_ITEMS = 16
_MAX_LIST_ITEM_BYTES = 1024


def _strip_json_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2:
            return "\n".join(lines[1:-1]).strip()
    return text


def _bounded_text(value: object, *, label: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise ProgramModelJuryExecutionError(f"model juror {label} must be text")
    try:
        encoded = value.encode("utf-8")
    except UnicodeError as exc:
        raise ProgramModelJuryExecutionError(
            f"model juror {label} must be valid UTF-8"
        ) from exc
    if len(encoded) > maximum or any(
        (ord(char) < 32 and char not in {"\n", "\t"}) or ord(char) == 127
        for char in value
    ):
        raise ProgramModelJuryExecutionError(
            f"model juror {label} exceeds the retained text contract"
        )
    return value


def _bounded_text_list(value: object, *, label: str) -> list[str]:
    if not isinstance(value, list) or len(value) > _MAX_LIST_ITEMS:
        raise ProgramModelJuryExecutionError(
            f"model juror {label} must be a bounded text list"
        )
    return [
        _bounded_text(item, label=label, maximum=_MAX_LIST_ITEM_BYTES) for item in value
    ]


def parse_model_judgment(raw: object, *, juror_id: str) -> dict[str, Any]:
    """Return only the exact bounded judgment schema; reject all extra output."""

    if isinstance(raw, Mapping):
        payload = dict(raw)
    else:
        try:
            payload = json.loads(_strip_json_fence(str(raw or "")))
        except json.JSONDecodeError as exc:
            raise ProgramModelJuryExecutionError(
                f"model juror {juror_id} did not return valid JSON"
            ) from exc
    if not isinstance(payload, dict) or set(payload) != _JUDGMENT_KEYS:
        raise ProgramModelJuryExecutionError(
            f"model juror {juror_id} judgment must match the closed schema"
        )
    outcome = payload["outcome"]
    confidence = payload["confidence"]
    if outcome not in _OUTCOMES:
        raise ProgramModelJuryExecutionError(
            f"model juror {juror_id} outcome is outside the closed vocabulary"
        )
    if confidence not in _CONFIDENCE:
        raise ProgramModelJuryExecutionError(
            f"model juror {juror_id} confidence is outside the closed vocabulary"
        )
    return {
        "outcome": outcome,
        "rationale": _bounded_text(
            payload["rationale"],
            label=f"{juror_id} rationale",
            maximum=_MAX_RATIONALE_BYTES,
        ),
        "evidence_strengths": _bounded_text_list(
            payload["evidence_strengths"],
            label=f"{juror_id} evidence_strengths",
        ),
        "concerns": _bounded_text_list(
            payload["concerns"],
            label=f"{juror_id} concerns",
        ),
        "improvement_requests": _bounded_text_list(
            payload["improvement_requests"],
            label=f"{juror_id} improvement_requests",
        ),
        "confidence": confidence,
    }


def aggregate_model_judgments(
    juror_results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    counts = {
        "supports_review_evidence": 0,
        "withhold": 0,
        "reject": 0,
        "request_more_evidence": 0,
        "failed": 0,
    }
    improvement_requests: list[str] = []
    for result in juror_results:
        if result.get("status") != "judged":
            counts["failed"] += 1
            continue
        judgment = result.get("judgment")
        if not isinstance(judgment, Mapping):
            counts["failed"] += 1
            continue
        outcome = judgment.get("outcome")
        if isinstance(outcome, str) and outcome in counts:
            counts[outcome] += 1
        else:
            counts["failed"] += 1
        requests = judgment.get("improvement_requests")
        if isinstance(requests, list):
            improvement_requests.extend(
                item for item in requests if isinstance(item, str)
            )
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
    return {
        "judgment_counts": counts,
        "blocking_concerns_present": bool(
            counts["reject"] or counts["request_more_evidence"] or counts["failed"]
        ),
        "recommendation": recommendation,
        "unique_improvement_requests": sorted(set(improvement_requests)),
    }


__all__ = ["aggregate_model_judgments", "parse_model_judgment"]

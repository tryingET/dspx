"""Deterministic signature-quality events from provider corpus fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import dspx.services.signatures_service as signatures_service
from dspx.services.signature_quality import SignatureQualityGate


PROVIDER_CORPUS_GATE = SignatureQualityGate(
    max_fallback_rate=0.10,
    max_attempts_p95=1.0,
    min_validation_pass_rate=1.0,
    min_smoke_pass_rate=1.0,
)


def load_provider_corpus_cases(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"provider corpus must be a JSON list: {path}")

    out: list[dict[str, Any]] = []
    for idx, row in enumerate(data):
        if not isinstance(row, dict):
            raise ValueError(
                f"provider corpus entry at index {idx} must be an object: {path}"
            )
        out.append(cast(dict[str, Any], row))

    if not out:
        raise ValueError(f"provider corpus is empty: {path}")
    return out


def _event_from_provider_case(case: dict[str, Any]) -> dict[str, Any]:
    provider = str(case.get("provider") or "unknown")
    case_name = str(case.get("name") or provider)
    class_name_hint = str(case.get("class_name_hint") or "GeneratedSignature")
    expected_source = str(case.get("expected_source") or "")

    candidate = signatures_service._candidate_from_raw(
        str(case.get("raw") or ""),
        attempt=1,
        class_name_hint=class_name_hint,
        fallback_description=f"provider corpus fallback: {case_name}",
        enforce_class_name=True,
    )

    source_match = expected_source == "" or candidate.source == expected_source
    accepted = bool(candidate.valid and source_match)

    return {
        "run_kind": "signature-gen",
        "provider": provider,
        "case_name": case_name,
        "expected_source": expected_source or None,
        "candidate_source": candidate.source,
        "candidate_valid": bool(candidate.valid),
        "source_match": bool(source_match),
        "candidate_errors": list(candidate.errors),
        "attempts_used": 1,
        "fallback_used": bool(candidate.source == "fallback"),
        "validation_pass_count": 1 if accepted else 0,
        "validation_total": 1,
        "smoke_pass_count": 1 if accepted else 0,
        "smoke_total": 1,
    }


def build_provider_corpus_quality_events(
    cases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [_event_from_provider_case(case) for case in cases]


def write_quality_events_jsonl(events: list[dict[str, Any]], out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(event, ensure_ascii=False, sort_keys=True) for event in events]
    text = "\n".join(lines)
    if text:
        text += "\n"
    out_path.write_text(text, encoding="utf-8")
    return out_path

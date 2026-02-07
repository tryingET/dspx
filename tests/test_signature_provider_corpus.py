from __future__ import annotations

import json
from pathlib import Path

import dspx.services.signatures_service as sigsvc


_PROVIDER_CASES = Path(__file__).parent / "golden" / "signature_provider_cases.json"


def test_signature_provider_corpus_cases() -> None:
    cases = json.loads(_PROVIDER_CASES.read_text(encoding="utf-8"))
    assert isinstance(cases, list) and cases

    for case in cases:
        hint = str(case.get("class_name_hint") or "GeneratedSignature")
        candidate = sigsvc._candidate_from_raw(
            str(case.get("raw") or ""),
            attempt=1,
            class_name_hint=hint,
            fallback_description="provider corpus fallback",
            enforce_class_name=True,
        )

        assert candidate.source == case.get("expected_source"), case.get("name")
        assert candidate.valid, (case.get("name"), candidate.errors)
        assert candidate.signature_name == hint

        for token in case.get("must_contain") or []:
            assert token in candidate.code, (case.get("name"), token)

# summary: "Tests deterministic signature rendering against validation tokens and golden source hashes."
# read_when:
#   - "You are changing signature templates, renderer output, validation, or the signature golden corpus."

from __future__ import annotations

import json
from pathlib import Path

from dspx.cache import sha256_text
from dspx.templates import render_signature_from_spec
from dspx.services.signatures_service import validate_signature_code


_GOLDEN = Path(__file__).parent / "golden" / "signature_specs.json"


def test_signature_renderer_golden_corpus() -> None:
    cases = json.loads(_GOLDEN.read_text(encoding="utf-8"))
    assert isinstance(cases, list) and cases

    for case in cases:
        spec = case["spec"]
        code = render_signature_from_spec(
            spec["class_name"],
            spec["description"],
            inputs=spec.get("inputs"),
            outputs=spec.get("outputs"),
        )

        for token in case.get("must_contain") or []:
            assert token in code, (case.get("name"), token)

        ok, errs = validate_signature_code(
            code,
            expected_class_name=spec["class_name"],
        )
        assert ok, (case.get("name"), errs)

        expected_hash = str(case.get("sha256") or "")
        assert expected_hash, f"missing golden hash for {case.get('name')}"
        assert sha256_text(code) == expected_hash

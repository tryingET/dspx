from __future__ import annotations

from dspx.dtos import SignatureGenRequest
from dspx.services.signatures_service import run_generate_dto


def test_signatures_service_dto_template_only() -> None:
    req = SignatureGenRequest(
        prompt="Create a step that summarizes text",
        template_version="simple-v1",
        options={"class_name": "Sig_Summarize"},
    )
    res = run_generate_dto(req)
    assert res.code.startswith("import dspy\n\nclass Sig_Summarize(dspy.Signature):")
    assert "summarizes text" in res.code

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


def test_signatures_service_dto_native_generation_with_stub_provider(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")

    req = SignatureGenRequest(
        prompt="Classify sentiment",
        template_version="v1",
        options={"class_name": "Sig_Sentiment"},
    )
    res = run_generate_dto(req)
    assert res.signature_name == "Sig_Sentiment"
    assert "class Sig_Sentiment(dspy.Signature):" in res.code

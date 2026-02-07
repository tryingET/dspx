from __future__ import annotations

import builtins

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


def test_signatures_service_dto_native_fallback_when_vibe_missing(monkeypatch) -> None:
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setattr(
        "dspx.services.signatures_service.ensure_vibe_on_path", lambda: None
    )

    orig_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "signature_generator":
            raise ImportError("forced missing vibe")
        return orig_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    req = SignatureGenRequest(prompt="Classify sentiment", template_version="v1")
    res = run_generate_dto(req)
    assert "dspy.Signature" in res.code
    assert "class " in res.code

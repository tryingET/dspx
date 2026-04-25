from __future__ import annotations

from pathlib import Path

import pytest

from dspx.dtos import SignatureGenRequest
from dspx.services.signature_quality import read_quality_events
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
    assert res.metadata.get("strategy") == "simple"
    assert res.metadata.get("validation_pass_rate") == 1.0
    assert res.metadata.get("inputs") == ["context"]
    assert res.metadata.get("outputs") == ["output"]
    assert res.metadata.get("requested_inputs") == []
    assert res.metadata.get("requested_outputs") == []


def test_signatures_service_dto_template_only_validates_explicit_io() -> None:
    req = SignatureGenRequest(
        prompt="Classify support tickets",
        template_version="simple-v1",
        options={
            "class_name": "TicketSig",
            "inputs": ["ticket_text"],
            "outputs": ["urgency"],
        },
    )
    res = run_generate_dto(req)
    assert "ticket_text: str = dspy.InputField" in res.code
    assert "urgency: str = dspy.OutputField" in res.code
    assert res.metadata.get("inputs") == ["ticket_text"]
    assert res.metadata.get("outputs") == ["urgency"]
    assert res.metadata.get("requested_inputs") == ["ticket_text"]
    assert res.metadata.get("requested_outputs") == ["urgency"]


@pytest.mark.parametrize(
    "options,error",
    [
        ({"class_name": "not-valid"}, "invalid_class_name_identifier"),
        ({"class_name": "Sig", "inputs": ["first-name"]}, "invalid_input_identifier"),
        ({"class_name": "Sig", "inputs": ["text", "text"]}, "duplicate_input_fields"),
        (
            {"class_name": "Sig", "inputs": ["answer"], "outputs": ["answer"]},
            "input_output_field_overlap",
        ),
    ],
)
def test_signatures_service_dto_template_only_rejects_invalid_io(
    options: dict[str, object], error: str
) -> None:
    req = SignatureGenRequest(
        prompt="Classify support tickets",
        template_version="simple-v1",
        options=options,
    )
    with pytest.raises(ValueError, match=error):
        run_generate_dto(req)


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
    assert res.metadata.get("provider") == "stub"
    assert "fallback_used" in res.metadata
    assert "validation_pass_rate" in res.metadata


def test_signatures_service_emits_quality_event_log(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    log = tmp_path / "quality.jsonl"
    monkeypatch.setenv("DSPX_SIGNATURE_QUALITY_LOG", str(log))

    req = SignatureGenRequest(
        prompt="Extract product names",
        template_version="v1",
        options={"class_name": "SigProducts"},
    )
    res = run_generate_dto(req)
    assert "class SigProducts(dspy.Signature):" in res.code

    events = read_quality_events(log)
    assert len(events) == 1
    assert events[0].get("provider") == "stub"
    assert events[0].get("run_kind") == "signature-gen"

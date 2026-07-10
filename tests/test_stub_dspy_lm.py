from __future__ import annotations

import dspy
import pytest

from dspx.stub_dspy_lm import DSpyStubLM


class TicketSignature(dspy.Signature):
    ticket_text: str = dspy.InputField()
    urgency: str = dspy.OutputField()


def test_stub_response_json_supplies_deterministic_semantic_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DSPX_STUB_RESPONSE_JSON", '{"urgency":"high"}')
    previous_lm = dspy.settings.lm
    try:
        dspy.configure(lm=DSpyStubLM())
        prediction = dspy.Predict(TicketSignature)(ticket_text="Outage for all users")
    finally:
        dspy.configure(lm=previous_lm)

    assert prediction.urgency == "high"


@pytest.mark.parametrize("value", ["not-json", "[]"])
def test_stub_response_json_rejects_invalid_fixture(
    value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_STUB_RESPONSE_JSON", value)

    with pytest.raises(ValueError, match="DSPX_STUB_RESPONSE_JSON"):
        DSpyStubLM().forward(prompt="ignored")

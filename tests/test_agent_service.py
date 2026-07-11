# summary: "Tests agent-service ReAct construction, invocation, and answer extraction."
# read_when:
#   - "You are changing the DSPx agent service signature, tool wiring, iteration controls, or return handling."

from __future__ import annotations

from typing import Any

from dspx.services import agent_service


def test_agent_service_react_uses_signature_type(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class FakeAgent:
        def __init__(
            self, signature: type, *, tools: list[Any], max_iters: int
        ) -> None:
            captured["signature"] = signature
            captured["tools"] = tools
            captured["max_iters"] = max_iters

        def __call__(self, *, question: str) -> object:
            captured["question"] = question

            class Prediction:
                answer = "stubbed answer"

            return Prediction()

    monkeypatch.setattr(agent_service, "load_config_env", lambda: None)
    monkeypatch.setattr(agent_service, "enable_mlflow_from_env", lambda: None)
    monkeypatch.setattr(agent_service, "ensure_default_providers", lambda: None)
    monkeypatch.setattr(agent_service, "create_from_env", lambda: object())
    monkeypatch.setattr(agent_service.dspy, "configure", lambda **_kwargs: None)
    monkeypatch.setattr(agent_service.dspy, "ReAct", FakeAgent)

    answer = agent_service.run("What changed?", max_iters=5)

    assert answer == "stubbed answer"
    assert captured["signature"] is agent_service.AgentQuestionAnswer
    assert captured["tools"] == []
    assert captured["max_iters"] == 5
    assert captured["question"] == "What changed?"

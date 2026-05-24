from __future__ import annotations

import json

import dspx.provider_runtime as provider_runtime
from dspx.capabilities import ProviderCapabilities


class _ProviderWithSecrets:
    def __init__(self) -> None:
        self.model = "fake/model"
        self.model_type = "text"
        self.capabilities = ProviderCapabilities(
            supports_tools=False,
            code_exec=False,
            json_mode=False,
            multi_turn=False,
            structured_output_format="none",
        )

    def runtime_metadata(self) -> dict[str, object]:
        return {
            "base_url": "https://api.example.com/v1/chat?api_key=supersecret",
            "headers": {
                "Authorization": "Bearer supersecret-token",
                "X-Test": "ok",
            },
            "nested": {"token": "supersecret-token"},
        }


def test_provider_metadata_from_instance_sanitizes_runtime_metadata() -> None:
    payload = provider_runtime.provider_metadata_from_instance(
        "fake", _ProviderWithSecrets()
    )

    dumped = json.dumps(payload)
    assert "supersecret" not in dumped
    assert payload["runtime"]["headers"]["Authorization"] == "[REDACTED]"
    assert "[REDACTED]" in payload["runtime"]["base_url"]


def test_check_provider_health_without_healthcheck_is_unknown_until_probed(
    monkeypatch,
) -> None:
    monkeypatch.setattr(provider_runtime, "ensure_default_providers", lambda: None)
    monkeypatch.setattr(
        provider_runtime, "create", lambda _name: _ProviderWithSecrets()
    )

    payload = provider_runtime.check_provider_health("fake", probe=False)

    assert payload["ok"] is False
    assert payload["status"] == "unknown"
    assert "no healthcheck" in payload["error"]


def test_check_provider_health_sanitizes_probe_text_and_errors(monkeypatch) -> None:
    class _ProbeProvider(_ProviderWithSecrets):
        def forward(self, prompt=None, **kwargs):  # noqa: ANN001
            return {
                "choices": [
                    {
                        "text": (
                            "Authorization: Bearer supersecret-token "
                            "api_key=supersecret-value"
                        )
                    }
                ],
                "usage": {"total_tokens": 1},
            }

    monkeypatch.setattr(provider_runtime, "ensure_default_providers", lambda: None)
    monkeypatch.setattr(provider_runtime, "create", lambda _name: _ProbeProvider())

    payload = provider_runtime.check_provider_health("fake", probe=True)

    dumped = json.dumps(payload)
    assert payload["ok"] is True
    assert payload["probe"]["ok"] is True
    assert "supersecret" not in dumped
    assert "[REDACTED]" in payload["probe"]["text"]


def test_benchmark_providers_sanitizes_last_text_and_errors(monkeypatch) -> None:
    class _BenchmarkProvider(_ProviderWithSecrets):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        def forward(self, prompt=None, **kwargs):  # noqa: ANN001
            self.calls += 1
            if self.calls == 1:
                return {
                    "choices": [{"text": ("Bearer supersecret-token " + ("x" * 600))}]
                }
            raise RuntimeError("provider failure: api_key=supersecret-value")

    monkeypatch.setattr(provider_runtime, "ensure_default_providers", lambda: None)
    monkeypatch.setattr(provider_runtime, "create", lambda _name: _BenchmarkProvider())

    payload = provider_runtime.benchmark_providers(["fake"], prompt="hello", repeats=2)

    dumped = json.dumps(payload)
    row = payload["results"][0]
    assert row["failures"] == 1
    assert "supersecret" not in dumped
    assert "[REDACTED]" in dumped
    assert "…[truncated]" in row["last_text"]

from __future__ import annotations

from dspx.provider_registry import ensure_default_providers, available, create_from_env


def test_stub_provider_registered_and_creatable(monkeypatch) -> None:
    ensure_default_providers()
    reg = available()
    assert "stub" in reg

    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    lm = create_from_env()
    # DSpy-compatible stub exposes a `forward` attribute
    assert hasattr(lm, "forward")

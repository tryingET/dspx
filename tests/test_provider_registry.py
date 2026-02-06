from __future__ import annotations

from dspx.provider_registry import (
    ensure_default_providers,
    available,
    create_from_env,
)


def test_registry_defaults_available() -> None:
    ensure_default_providers()
    reg = available()
    # At least one provider should be registered by default
    assert any(
        k in reg for k in ("codex-exec", "claude-cli", "gemini-cli", "multi", "pi-rpc")
    )


def test_create_from_env_defaults(monkeypatch) -> None:
    monkeypatch.delenv("DSPX_PROVIDER", raising=False)
    # Should not raise if defaults are available
    ensure_default_providers()
    lm = create_from_env()
    assert lm is not None


def test_create_from_env_specific(monkeypatch) -> None:
    monkeypatch.setenv("DSPX_PROVIDER", "codex-exec")
    ensure_default_providers()
    lm = create_from_env()
    assert lm is not None

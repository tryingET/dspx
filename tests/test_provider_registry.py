from __future__ import annotations

import dspx.providers_register_multi as providers_register_multi
from dspx.provider_registry import (
    available,
    create_from_env,
    ensure_default_providers,
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


def test_multi_factory_keeps_names_aligned_with_resolved_providers(monkeypatch) -> None:
    class _Provider:
        def __init__(self, model: str) -> None:
            self.model = model

    def _fake_create(name: str):
        if name == "missing":
            raise RuntimeError("boom")
        return _Provider(name)

    monkeypatch.setenv("DSPX_MULTI_PROVIDERS", "good,missing,other")
    monkeypatch.setattr(
        providers_register_multi, "ensure_default_providers", lambda: None
    )
    monkeypatch.setattr(providers_register_multi, "create", _fake_create)

    lm = providers_register_multi._factory()

    assert [provider.model for provider in lm.providers] == ["good", "other"]
    assert lm.names == ["good", "other"]

from __future__ import annotations

from typing import Callable, Dict
import os

from .capabilities import ProviderCapabilities
from .policy import check_provider_allowed


class ProviderFactory:
    def __init__(
        self, factory: Callable[[], object], capabilities: ProviderCapabilities
    ):
        self.factory = factory
        self.capabilities = capabilities


DEFAULT_PROVIDER_OWNER_ATTR = "_dspx_default_owner"
_REGISTRY: Dict[str, ProviderFactory] = {}


def mark_default_provider_factory(
    factory: Callable[[], object], owner: str
) -> Callable[[], object]:
    setattr(factory, DEFAULT_PROVIDER_OWNER_ATTR, owner)
    return factory


def register_provider(
    name: str, factory: Callable[[], object], capabilities: ProviderCapabilities
) -> None:
    _REGISTRY[name] = ProviderFactory(factory, capabilities)


def create(name: str) -> object:
    check_provider_allowed(name)
    return _REGISTRY[name].factory()


def capabilities(name: str) -> ProviderCapabilities:
    return _REGISTRY[name].capabilities


def available() -> Dict[str, ProviderFactory]:
    return dict(_REGISTRY)


def _factory_owned_by_default_owner(name: str, owner: str) -> bool:
    factory = _REGISTRY.get(name)
    if factory is None:
        return False
    return getattr(factory.factory, DEFAULT_PROVIDER_OWNER_ATTR, None) == owner


def ensure_default_providers() -> None:
    """Ensure built-in providers are registered (idempotent)."""
    if "codex-exec" not in _REGISTRY:
        try:
            from .providers_register_codex import register as _reg_codex

            _reg_codex()
        except Exception:
            # Ignore if unavailable; callers may still register manually
            pass
    if "openrouter" not in _REGISTRY:
        try:
            from .providers_register_openrouter import register as _reg_openrouter

            _reg_openrouter()
        except Exception:
            pass
    if "claude-cli" not in _REGISTRY:
        try:
            from .providers_register_claude import register as _reg_claude

            _reg_claude()
        except Exception:
            pass
    if "multi" not in _REGISTRY:
        try:
            from .providers_register_multi import register as _reg_multi

            _reg_multi()
        except Exception:
            pass
    if "gemini-cli" not in _REGISTRY:
        try:
            from .providers_register_gemini import register as _reg_gemini

            _reg_gemini()
        except Exception:
            pass
    if "stub" not in _REGISTRY:
        try:
            from .providers_register_stub import register as _reg_stub

            _reg_stub()
        except Exception:
            pass
    if "pi-rpc" not in _REGISTRY:
        try:
            from .providers_register_pi import register as _reg_pi

            _reg_pi()
        except Exception:
            pass
    try:
        from .providers_register_openai_compatible import (
            register_openai_compatible as _reg_openai_compatible,
            register_vllm_local as _reg_vllm_local,
        )

        if "openai-compatible" not in _REGISTRY or _factory_owned_by_default_owner(
            "openai-compatible", "dspx.default.openai-compatible"
        ):
            _reg_openai_compatible()
        if "vllm-local" not in _REGISTRY or _factory_owned_by_default_owner(
            "vllm-local", "dspx.default.vllm-local"
        ):
            _reg_vllm_local()
    except Exception:
        pass
    if "dspy-lm-auth" not in _REGISTRY:
        try:
            from .providers_register_dspy_lm_auth import register as _reg_dspy_lm_auth

            _reg_dspy_lm_auth()
        except Exception:
            pass


def create_from_env(env_var: str = "DSPX_PROVIDER", default: str = "pi-rpc") -> object:
    """Create an LM instance from the registry based on an env var.

    Defaults to 'pi-rpc'. Callers should first call ensure_default_providers().
    """
    name = os.getenv(env_var, default)
    ensure_default_providers()
    if name not in _REGISTRY:
        raise KeyError(f"Provider '{name}' is not registered")
    return create(name)

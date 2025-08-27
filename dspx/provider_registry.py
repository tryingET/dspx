from __future__ import annotations

from typing import Callable, Dict, Optional

from .capabilities import ProviderCapabilities


class ProviderFactory:
    def __init__(self, factory: Callable[[], object], capabilities: ProviderCapabilities):
        self.factory = factory
        self.capabilities = capabilities


_REGISTRY: Dict[str, ProviderFactory] = {}


def register_provider(name: str, factory: Callable[[], object], capabilities: ProviderCapabilities) -> None:
    _REGISTRY[name] = ProviderFactory(factory, capabilities)


def create(name: str) -> object:
    return _REGISTRY[name].factory()


def capabilities(name: str) -> ProviderCapabilities:
    return _REGISTRY[name].capabilities


def available() -> Dict[str, ProviderFactory]:
    return dict(_REGISTRY)


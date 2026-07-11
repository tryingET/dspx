# summary: "Registers the deterministic DSPy stub LM used for local and offline execution."
# read_when:
#   - "Changing stub-provider construction, registration, or advertised capabilities."

from __future__ import annotations

from .capabilities import ProviderCapabilities
from .provider_registry import register_provider
from dspx.stub_dspy_lm import DSpyStubLM


def _factory() -> DSpyStubLM:
    return DSpyStubLM()


def register() -> None:
    caps = ProviderCapabilities(
        supports_tools=False, code_exec=False, json_mode=False, multi_turn=False
    )
    register_provider("stub", _factory, caps)

# summary: "Defines the minimal internal language-model provider interface."
# read_when:
#   - "Implementing or changing DSPx provider generation contracts."

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .capabilities import ProviderCapabilities
from .dtos import LMRequest, LMResponse


class LMBase(ABC):
    """Minimal provider interface used by services.

    Providers can also implement DSPy's BaseLM separately; this interface is for
    our internal service orchestration.
    """

    def __init__(self, *, capabilities: Optional[ProviderCapabilities] = None) -> None:
        self.capabilities = capabilities or ProviderCapabilities()

    @abstractmethod
    def generate(self, request: LMRequest, **kwargs) -> LMResponse:
        raise NotImplementedError

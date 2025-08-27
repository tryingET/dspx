from __future__ import annotations

from ..dtos import LMRequest, LMResponse
from ..lm_base import LMBase


class StubLM(LMBase):
    def generate(self, request: LMRequest, **kwargs) -> LMResponse:  # type: ignore[override]
        text = "stub: " + (request.prompt or "")
        return LMResponse(outputs=[text], model="stub", usage=None, raw=None)

# summary: "Provides the documented deterministic local stub LM for tests."
# read_when:
#   - "Changing the documented stub LM path or deterministic response behavior."

from __future__ import annotations

from ..dtos import LMRequest, LMResponse
from ..lm_base import LMBase


class StubLM(LMBase):
    """Deterministic local LM for tests.

    Mirrors src/dspx/providers/stub.py to match documented path.
    """

    def generate(self, request: LMRequest, **kwargs) -> LMResponse:
        text = "stub: " + (request.prompt or "")
        return LMResponse(outputs=[text], model="stub", usage=None, raw=None)

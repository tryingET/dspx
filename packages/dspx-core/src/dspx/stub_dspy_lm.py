# summary: "Implements a deterministic echo LM compatible with DSPy and DSPx request/response interfaces for offline testing."
# read_when:
#   - "Changing stub-provider responses, DSPy LM compatibility, or offline fixture injection."

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any, Dict, Iterable, List, Optional

try:
    from dspy import BaseLM as DSPyBaseLM
except Exception:  # pragma: no cover
    try:
        from dspy.models import BaseLM as DSPyBaseLM  # type: ignore
    except Exception:  # fallback dummy class

        class DSPyBaseLM:
            def __init__(
                self, model: str = "stub", model_type: str = "text", **kwargs
            ) -> None:
                self.model = model
                self.model_type = model_type


from .dtos import LMRequest, LMResponse
from .lm_base import LMBase
from .capabilities import ProviderCapabilities


@dataclass
class _MinimalResponse:
    model: str
    choices: List[Dict[str, Any]]
    usage: Dict[str, Any]


class DSpyStubLM(DSPyBaseLM, LMBase):
    """Deterministic LM that echoes prompts. Useful for offline tests.

    - For DSPy, implements `forward` and returns a minimal response.
    - For internal services, implements `generate(LMRequest)`.
    """

    def __init__(self, label: str = "stub/echo") -> None:
        DSPyBaseLM.__init__(self, model=label, model_type="text")
        LMBase.__init__(
            self,
            capabilities=ProviderCapabilities(
                code_exec=False,
                supports_tools=False,
                json_mode=False,
                structured_output_format="none",
            ),
        )

    # DSPy entrypoint
    def forward(
        self,
        prompt: Optional[str] = None,
        messages: Optional[Iterable[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> _MinimalResponse:
        text = self._make_text(prompt, messages)
        return _MinimalResponse(
            model=self.model,
            choices=[{"text": text}],
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        )

    # Internal DTO entrypoint
    def generate(self, request: LMRequest, **kwargs) -> LMResponse:
        text = self._make_text(request.prompt, None)
        return LMResponse(outputs=[text], model=self.model, usage=None, raw=None)

    @staticmethod
    def _make_text(
        prompt: Optional[str], messages: Optional[Iterable[Dict[str, Any]]]
    ) -> str:
        fixture_json = os.getenv("DSPX_STUB_RESPONSE_JSON")
        if fixture_json is not None:
            try:
                fixture = json.loads(fixture_json)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "DSPX_STUB_RESPONSE_JSON must contain valid JSON"
                ) from exc
            if not isinstance(fixture, dict):
                raise ValueError("DSPX_STUB_RESPONSE_JSON must contain a JSON object")
            return json.dumps(fixture, ensure_ascii=False, sort_keys=True)
        if prompt is not None:
            return f"stub: {prompt}"
        # flatten messages into a single string deterministically
        parts: List[str] = []
        for m in messages or []:
            role = str(m.get("role", "user"))
            content = str(m.get("content", ""))
            if content:
                parts.append(f"{role}: {content}")
        return "stub: " + "\n".join(parts).strip()

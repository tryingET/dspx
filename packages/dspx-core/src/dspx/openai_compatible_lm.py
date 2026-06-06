from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional
from urllib.parse import urlsplit

import httpx

from dspx.capabilities import ProviderCapabilities
from dspx.dtos import LMRequest, LMResponse
from dspx.lm_base import LMBase
from dspx.redaction import redact_headers, redact_url
from dspx.security import (
    DEFAULT_HTTP_RESPONSE_MAX_BYTES,
    response_json_or_raw_text_bounded,
)

try:
    from dspx.policy import check_capability as _check_capability
except Exception:  # pragma: no cover
    _check_capability = None  # type: ignore

if TYPE_CHECKING:
    from dspy import BaseLM as DSPyBaseLM
else:  # pragma: no cover
    try:
        from dspy import BaseLM as DSPyBaseLM
    except Exception:
        try:
            from dspy.models import BaseLM as DSPyBaseLM
        except Exception:

            class DSPyBaseLM:
                def __init__(
                    self,
                    model: str = "openai-compatible",
                    model_type: str = "text",
                    **kwargs: Any,
                ) -> None:
                    self.model = model
                    self.model_type = model_type


class _MinimalResponse(dict):
    def __init__(
        self, *, model: str, choices: list[dict[str, Any]], usage: dict[str, Any] | None
    ) -> None:
        super().__init__(model=model, choices=choices, usage=usage or {})
        self.model = model
        self.choices = choices
        self.usage = usage or {}


@dataclass
class OpenAICompatibleCall:
    model: str
    base_url: str
    status_code: int
    text: str
    raw: Any
    started_at: float
    ended_at: float


def _extract_text(resp_json: Any) -> str:
    try:
        if isinstance(resp_json, dict):
            choices = resp_json.get("choices") or []
            if isinstance(choices, list) and choices:
                c0 = choices[0]
                if isinstance(c0, dict):
                    msg = c0.get("message")
                    if isinstance(msg, dict) and msg.get("content") is not None:
                        return str(msg.get("content") or "").strip()
                    if c0.get("text") is not None:
                        return str(c0.get("text") or "").strip()
    except Exception:
        pass
    return ""


def _is_loopback_url(url: str) -> bool:
    try:
        host = (urlsplit(url).hostname or "").lower()
    except Exception:
        return False
    return host in {"localhost", "127.0.0.1", "::1"}


class OpenAICompatibleLM(DSPyBaseLM, LMBase):
    """Generic OpenAI-compatible chat completions provider.

    Useful for local vLLM/Ollama-compatible endpoints and generic OpenAI-style
    backends without inventing a provider per deployment.
    """

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:8000/v1",
        model: str = "local-model",
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        extra_headers: Optional[Dict[str, str]] = None,
        client: Optional[httpx.Client] = None,
        strict: bool = True,
        provider_label: str = "openai-compatible",
        json_mode: bool = False,
    ) -> None:
        DSPyBaseLM.__init__(self, model=f"{provider_label}/{model}", model_type="text")
        LMBase.__init__(
            self,
            capabilities=ProviderCapabilities(
                supports_tools=False,
                code_exec=False,
                json_mode=json_mode,
                multi_turn=True,
                structured_output_format="json" if json_mode else "none",
            ),
        )
        self.base_url = base_url.rstrip("/")
        self.model_id = model
        self.api_key = api_key
        self.timeout = timeout
        self.extra_headers = dict(extra_headers or {})
        self.strict = strict
        self.provider_label = provider_label
        self.history: List[OpenAICompatibleCall] = []
        self._client = client
        self._own_client = client is None
        if self._client is None:
            self._client = httpx.Client(base_url=self.base_url, timeout=self.timeout)

    def __del__(self) -> None:  # pragma: no cover
        try:
            if self._own_client and self._client is not None:
                self._client.close()
        except Exception:
            pass

    def _headers(self) -> Dict[str, str]:
        hdrs: Dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            hdrs["Authorization"] = f"Bearer {self.api_key}"
        hdrs.update(self.extra_headers)
        return hdrs

    def _request_payload(
        self, *, messages: List[Dict[str, Any]], kwargs: Dict[str, Any]
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"model": self.model_id, "messages": messages}
        for k in (
            "temperature",
            "max_tokens",
            "top_p",
            "frequency_penalty",
            "presence_penalty",
            "seed",
            "response_format",
        ):
            if k in kwargs and kwargs.get(k) is not None:
                payload[k] = kwargs[k]
        return payload

    def runtime_metadata(self) -> dict[str, Any]:
        return {
            "provider_family": self.provider_label,
            "base_url": redact_url(self.base_url),
            "model": self.model_id,
            "timeout": self.timeout,
            "loopback": _is_loopback_url(self.base_url),
            "headers": redact_headers(self._headers()),
        }

    def healthcheck(
        self,
        *,
        probe: bool = False,
        prompt: str = "Reply with the single word: hello",
        max_tokens: int | None = 16,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": True,
            "provider": self.provider_label,
            "model": self.model_id,
            "metadata": self.runtime_metadata(),
            "checks": [
                {
                    "name": "config",
                    "ok": bool(self.base_url and self.model_id),
                    "detail": f"base_url={redact_url(self.base_url)} model={self.model_id}",
                }
            ],
        }
        if not self.base_url or not self.model_id:
            payload["ok"] = False
            payload["error"] = "base_url and model are required"
            return payload
        if probe:
            started = time.time()
            try:
                resp = self.forward(prompt=prompt, max_tokens=max_tokens)
                payload["probe"] = {
                    "ok": True,
                    "duration_ms": round((time.time() - started) * 1000.0, 3),
                    "text": _extract_text(resp),
                }
            except Exception as e:
                payload["ok"] = False
                payload["error"] = str(e)
                payload["probe"] = {
                    "ok": False,
                    "duration_ms": round((time.time() - started) * 1000.0, 3),
                    "error": str(e),
                }
        return payload

    def forward(
        self,
        prompt: Optional[str] = None,
        messages: Optional[Iterable[Dict[str, Any]]] = None,
        **kwargs: Any,
    ):
        if _check_capability is not None:
            _check_capability("network.mutate")

        msgs: List[Dict[str, Any]]
        if messages is not None:
            msgs = [
                {"role": m.get("role"), "content": m.get("content")} for m in messages
            ]
        else:
            msgs = [{"role": "user", "content": prompt or ""}]

        client = self._client
        if client is None:
            raise RuntimeError("HTTP client is not initialized")

        started = time.time()
        with client.stream(
            "POST",
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            json=self._request_payload(messages=msgs, kwargs=dict(kwargs)),
            timeout=float(kwargs.get("timeout", self.timeout)),
        ) as r:
            raw = response_json_or_raw_text_bounded(
                r,
                max_bytes=DEFAULT_HTTP_RESPONSE_MAX_BYTES,
                label="OpenAI-compatible API response",
            )
            status_code = int(r.status_code)
        ended = time.time()
        text = _extract_text(raw)
        if not text and isinstance(raw, dict):
            err = raw.get("error")
            if isinstance(err, dict) and err.get("message"):
                text = str(err.get("message"))
        self.history.append(
            OpenAICompatibleCall(
                model=self.model_id,
                base_url=self.base_url,
                status_code=status_code,
                text=text,
                raw=raw,
                started_at=started,
                ended_at=ended,
            )
        )
        if status_code >= 400 and self.strict:
            raise RuntimeError(
                f"OpenAI-compatible API error (status={status_code}): {text}"
            )
        usage_raw = raw.get("usage") if isinstance(raw, dict) else None
        usage: dict[str, Any] | None = None
        if isinstance(usage_raw, dict):
            usage = {str(key): value for key, value in usage_raw.items()}
        return _MinimalResponse(
            model=self.model,
            choices=[{"text": text}],
            usage=usage,
        )

    def generate(self, request: LMRequest, **kwargs: Any) -> LMResponse:
        if request.prompt is not None:
            resp = self.forward(prompt=request.prompt, **kwargs)
        else:
            msgs = [
                {"role": m.role, "content": m.content} for m in (request.messages or [])
            ]
            resp = self.forward(messages=msgs, **kwargs)
        text = str(((resp.get("choices") or [{}])[0]).get("text") or "").strip()
        usage = resp.get("usage") if isinstance(resp, dict) else None
        return LMResponse(outputs=[text], model=self.model, usage=usage, raw=None)

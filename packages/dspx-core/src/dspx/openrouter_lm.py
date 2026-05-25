from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

import httpx

# Optional internal DTO/provider interface for services
try:
    from dspx.dtos import LMRequest, LMResponse
    from dspx.lm_base import LMBase as InternalLMBase
    from dspx.capabilities import ProviderCapabilities
except Exception:  # pragma: no cover
    LMRequest = None  # type: ignore
    LMResponse = None  # type: ignore

    class InternalLMBase:
        pass

    ProviderCapabilities = None  # type: ignore

# DSPy BaseLM (typing-friendly import pattern)
from typing import TYPE_CHECKING

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
                    self, model: str = "openrouter", model_type: str = "text", **kwargs
                ) -> None:
                    self.model = model
                    self.model_type = model_type


class _MinimalResponse(dict):
    """Tiny OpenAI-like response container for DSPy compatibility."""

    def __init__(
        self, *, model: str, choices: list[dict[str, Any]], usage: dict[str, Any] | None
    ) -> None:
        super().__init__(model=model, choices=choices, usage=usage or {})
        self.model = model
        self.choices = choices
        self.usage = usage or {}


def _messages_to_prompt(messages: Optional[Iterable[Dict[str, Any]]]) -> str:
    if not messages:
        return ""
    parts: list[str] = []
    for m in messages:
        try:
            role = str(m.get("role") or "user")
            content = str(m.get("content") or "")
        except Exception:
            continue
        parts.append(f"{role}: {content}".rstrip())
    return "\n".join(parts).strip()


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


@dataclass
class OpenRouterCall:
    model: str
    messages: List[Dict[str, Any]]
    status_code: int
    text: str
    raw: Any
    started_at: float
    ended_at: float


class OpenRouterLM(DSPyBaseLM):
    """DSPy-compatible LM that calls OpenRouter's OpenAI-compatible Chat Completions API."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: str = "https://openrouter.ai/api/v1",
        model: str = "meta-llama/llama-3.1-8b-instruct:free",
        timeout: float = 30.0,
        extra_headers: Optional[Dict[str, str]] = None,
        client: Optional[httpx.Client] = None,
        strict: bool = True,
    ) -> None:
        DSPyBaseLM.__init__(self, model=f"openrouter/{model}", model_type="text")
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.base_url = base_url
        self.model_id = model
        self.timeout = timeout
        self.extra_headers = dict(extra_headers or {})
        self.strict = strict
        self.verbose: bool = os.getenv("DSPX_OPENROUTER_VERBOSE", "0") == "1"
        self.history: List[OpenRouterCall] = []

        self._client = client
        self._own_client = client is None
        if self._client is None:
            self._client = httpx.Client(base_url=self.base_url, timeout=self.timeout)

        # capabilities
        try:
            if ProviderCapabilities is not None:
                caps = ProviderCapabilities(
                    supports_tools=False,
                    code_exec=False,
                    json_mode=False,  # OpenRouter proxies to various models; can't guarantee JSON
                    multi_turn=True,
                    structured_output_format="none",  # Depends on underlying model
                )
            else:
                caps = None
            if hasattr(InternalLMBase, "__init__"):
                InternalLMBase.__init__(self, capabilities=caps)  # type: ignore
        except Exception:
            pass

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

        # OpenRouter recommends these for attribution; keep env-driven.
        referer = os.getenv("OPENROUTER_HTTP_REFERER")
        title = os.getenv("OPENROUTER_APP_TITLE")
        if referer:
            hdrs["HTTP-Referer"] = str(referer)
        if title:
            hdrs["X-Title"] = str(title)

        hdrs.update(self.extra_headers)
        return hdrs

    def _request_payload(
        self, *, messages: List[Dict[str, Any]], kwargs: Dict[str, Any]
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"model": self.model_id, "messages": messages}

        # Env-driven defaults (so callers can avoid flags/kwargs).
        # These are applied only if the value is not provided explicitly in kwargs.
        env_defaults: dict[str, str] = {}
        for env_k, key in (
            ("OPENROUTER_TEMPERATURE", "temperature"),
            ("OPENROUTER_MAX_TOKENS", "max_tokens"),
            ("OPENROUTER_TOP_P", "top_p"),
            ("OPENROUTER_FREQUENCY_PENALTY", "frequency_penalty"),
            ("OPENROUTER_PRESENCE_PENALTY", "presence_penalty"),
            ("OPENROUTER_SEED", "seed"),
        ):
            v = os.getenv(env_k)
            if v is not None and key not in kwargs:
                env_defaults[key] = v

        for k in (
            "temperature",
            "max_tokens",
            "top_p",
            "frequency_penalty",
            "presence_penalty",
            "seed",
        ):
            if k in kwargs and kwargs.get(k) is not None:
                payload[k] = kwargs[k]
            elif k in env_defaults:
                # Best-effort parse; leave as string if parsing fails.
                raw = env_defaults[k]
                try:
                    if k in {"max_tokens", "seed"}:
                        payload[k] = int(str(raw).strip())
                    else:
                        payload[k] = float(str(raw).strip())
                except Exception:
                    payload[k] = raw
        return payload

    def forward(
        self,
        prompt: Optional[str] = None,
        messages: Optional[Iterable[Dict[str, Any]]] = None,
        **kwargs: Any,
    ):
        if not self.api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set (required for OpenRouterLM)"
            )

        # Capability gating: network.mutate (POST)
        try:
            from dspx.policy import check_capability as _cap
        except Exception:
            _cap = None  # type: ignore
        if _cap is not None:
            _cap("network.mutate")

        msgs: List[Dict[str, Any]]
        if messages is not None:
            msgs = [
                {"role": m.get("role"), "content": m.get("content")} for m in messages
            ]
        else:
            q = prompt or ""
            msgs = [{"role": "user", "content": q}]

        if self.verbose:
            ts = datetime.now().strftime("%H:%M:%S")
            print(
                f"[{ts}] OpenRouterLM: POST /chat/completions (model={self.model_id})…",
                flush=True,
            )

        client = self._client
        if client is None:
            raise RuntimeError("OpenRouter HTTP client is not initialized")

        t0 = time.time()
        r = client.post(
            f"{self.base_url.rstrip('/')}/chat/completions",
            headers=self._headers(),
            json=self._request_payload(messages=msgs, kwargs=dict(kwargs)),
            timeout=float(kwargs.get("timeout", self.timeout)),
        )
        t1 = time.time()

        raw: Any
        try:
            raw = r.json()
        except Exception:
            raw = {"raw_text": r.text}

        text = _extract_text(raw)
        if not text and isinstance(raw, dict):
            err = raw.get("error")
            if isinstance(err, dict) and err.get("message"):
                text = str(err.get("message"))

        self.history.append(
            OpenRouterCall(
                model=self.model_id,
                messages=msgs,
                status_code=int(r.status_code),
                text=text,
                raw=raw,
                started_at=t0,
                ended_at=t1,
            )
        )

        if r.status_code >= 400 and self.strict:
            raise RuntimeError(f"OpenRouter API error (status={r.status_code}): {text}")

        usage: dict[str, Any] | None = None
        if isinstance(raw, dict):
            raw_usage = raw.get("usage")
            if isinstance(raw_usage, dict):
                usage = raw_usage

        return _MinimalResponse(
            model=self.model,
            choices=[{"text": text}],
            usage=usage,
        )

    def generate(self, request: "LMRequest", **kwargs):
        if LMRequest is None or LMResponse is None:
            raise RuntimeError("Internal DTOs not available")
        if request is None:
            raise ValueError("LMRequest is required")
        if getattr(request, "prompt", None):
            prompt = request.prompt
            resp = self.forward(prompt=prompt, **kwargs)
        else:
            msgs = getattr(request, "messages", None)
            m = [{"role": mm.role, "content": mm.content} for mm in (msgs or [])]
            resp = self.forward(messages=m, **kwargs)
        text = ""
        try:
            text = str(((resp.get("choices") or [{}])[0]).get("text") or "").strip()
        except Exception:
            text = str(resp)
        return LMResponse(outputs=[text], model=self.model, usage=None, raw=None)

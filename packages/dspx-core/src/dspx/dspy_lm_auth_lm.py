from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional

from dspx.capabilities import ProviderCapabilities
from dspx.dtos import LMRequest, LMResponse
from dspx.lm_base import LMBase
from dspx.redaction import redact_headers

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
                    model: str = "dspy-lm-auth",
                    model_type: str = "text",
                    **kwargs: Any,
                ) -> None:
                    self.model = model
                    self.model_type = model_type


@dataclass
class DspyLmAuthCall:
    model: str
    auth_provider: str | None
    started_at: float
    ended_at: float
    text: str
    usage: dict[str, Any] | None
    error: str | None = None


class DspyLMAuthLM(DSPyBaseLM, LMBase):
    """DSPx provider wrapper around dspy-lm-auth.LM.

    This keeps auth-backed DSPy routing explicit inside the DSPx provider registry
    instead of monkeypatching `dspy.LM` process-wide.
    """

    def __init__(
        self,
        *,
        model: str = "codex/gpt-5.4",
        auth_provider: str | None = None,
        auth_storage: str | None = None,
        timeout: float | None = 60.0,
        strict: bool = True,
        kwargs: dict[str, Any] | None = None,
    ) -> None:
        label = f"dspy-lm-auth/{model}"
        DSPyBaseLM.__init__(self, model=label, model_type="text")
        LMBase.__init__(
            self,
            capabilities=ProviderCapabilities(
                supports_tools=False,
                code_exec=False,
                json_mode=True,
                multi_turn=True,
                structured_output_format="json",
            ),
        )
        self.requested_model = model
        self.auth_provider = auth_provider
        self.auth_storage = auth_storage
        self.timeout = timeout
        self.strict = strict
        self.kwargs = dict(kwargs or {})
        self.history: List[DspyLmAuthCall] = []
        self._inner: Any | None = None
        self._resolved_model: str | None = None
        self._resolved_model_type: str | None = None
        self._resolved_headers: dict[str, str] | None = None
        self._uses_codex_route: bool | None = None

    def _import_module(self):
        try:
            import dspy_lm_auth
        except ImportError as e:  # pragma: no cover - exercised in tests via message
            raise RuntimeError(
                "dspy-lm-auth is not installed. Install with 'pip install dspx-core[lm-auth]' "
                "or 'pip install dspy-lm-auth'."
            ) from e
        return dspy_lm_auth

    def _build_inner(self) -> Any:
        if self._inner is not None:
            return self._inner
        mod = self._import_module()
        init_kwargs = dict(self.kwargs)
        if self.timeout is not None and "timeout" not in init_kwargs:
            init_kwargs["timeout"] = self.timeout
        inner = mod.LM(
            self.requested_model,
            auth_provider=self.auth_provider,
            auth_storage=self.auth_storage,
            **init_kwargs,
        )
        self._inner = inner
        self._resolved_model = str(getattr(inner, "resolved_model_string", "") or "")
        self._resolved_model_type = str(getattr(inner, "model_type", "") or "")
        raw_headers = getattr(inner, "kwargs", {}).get("headers")
        if isinstance(raw_headers, dict):
            self._resolved_headers = {str(k): str(v) for k, v in raw_headers.items()}
        self._uses_codex_route = bool(getattr(inner, "_uses_codex_route", False))
        try:
            self.model = str(getattr(inner, "model", self.model))
            self.model_type = str(getattr(inner, "model_type", self.model_type))
        except Exception:
            pass
        return inner

    @staticmethod
    def _extract_text(resp: Any) -> str:
        try:
            if hasattr(resp, "output_text") and getattr(resp, "output_text"):
                return str(getattr(resp, "output_text") or "").strip()
        except Exception:
            pass
        try:
            output = getattr(resp, "output", None)
            if isinstance(output, list):
                texts: list[str] = []
                for item in output:
                    content = getattr(item, "content", None)
                    if not isinstance(content, list):
                        continue
                    for block in content:
                        text = getattr(block, "text", None)
                        if text:
                            texts.append(str(text))
                if texts:
                    return "\n".join(t.strip() for t in texts if str(t).strip()).strip()
        except Exception:
            pass
        try:
            if hasattr(resp, "choices"):
                choices = getattr(resp, "choices") or []
            elif isinstance(resp, dict):
                choices = resp.get("choices") or []
            else:
                choices = []
            if choices:
                choice0 = choices[0]
                if isinstance(choice0, dict):
                    msg = choice0.get("message")
                    if isinstance(msg, dict) and msg.get("content") is not None:
                        return str(msg.get("content") or "").strip()
                    if choice0.get("text") is not None:
                        return str(choice0.get("text") or "").strip()
        except Exception:
            pass
        return str(resp).strip()

    @staticmethod
    def _extract_usage(resp: Any) -> dict[str, Any] | None:
        try:
            usage = getattr(resp, "usage", None)
            if usage is None and isinstance(resp, dict):
                usage = resp.get("usage")
            if isinstance(usage, dict):
                return {str(k): usage[k] for k in usage}
            if usage is not None and hasattr(usage, "model_dump"):
                dumped = usage.model_dump()
                if isinstance(dumped, dict):
                    return dumped
        except Exception:
            pass
        return None

    def runtime_metadata(self) -> dict[str, Any]:
        storage_path = (
            Path(self.auth_storage).expanduser()
            if self.auth_storage
            else Path("~/.pi/agent/auth.json").expanduser()
        )
        data: dict[str, Any] = {
            "provider_family": "dspy-lm-auth",
            "requested_model": self.requested_model,
            "auth_provider": self.auth_provider,
            "auth_storage": str(storage_path),
            "auth_storage_exists": storage_path.exists(),
            "timeout": self.timeout,
        }
        if self._resolved_model:
            data["resolved_model"] = self._resolved_model
        if self._resolved_model_type:
            data["resolved_model_type"] = self._resolved_model_type
        if self._uses_codex_route is not None:
            data["uses_codex_route"] = self._uses_codex_route
        if self._resolved_headers:
            data["resolved_headers"] = redact_headers(self._resolved_headers)
        return data

    def healthcheck(
        self,
        *,
        probe: bool = False,
        prompt: str = "Reply with the single word: hello",
        max_tokens: int | None = 16,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": True,
            "provider": "dspy-lm-auth",
            "model": self.requested_model,
            "metadata": self.runtime_metadata(),
            "checks": [],
        }
        try:
            mod = self._import_module()
            payload["checks"].append(
                {"name": "dependency", "ok": True, "detail": "dspy-lm-auth import ok"}
            )
        except Exception as e:
            payload["ok"] = False
            payload["error"] = str(e)
            payload["checks"].append(
                {"name": "dependency", "ok": False, "detail": str(e)}
            )
            return payload

        try:
            storage = (
                mod.AuthStorage(self.auth_storage)
                if self.auth_storage
                else mod.AuthStorage()
            )
            provider = self.auth_provider or self.requested_model.split("/", 1)[0]
            has_auth = bool(storage.has_auth(provider))
            payload["checks"].append(
                {
                    "name": "credentials",
                    "ok": has_auth,
                    "detail": f"auth available for provider={provider}",
                }
            )
            if not has_auth:
                payload["ok"] = False
                payload["error"] = (
                    f"no credentials available for auth provider '{provider}'"
                )
                return payload
        except Exception as e:
            payload["ok"] = False
            payload["error"] = str(e)
            payload["checks"].append(
                {"name": "credentials", "ok": False, "detail": str(e)}
            )
            return payload

        if probe:
            started = time.time()
            try:
                resp = self.forward(prompt=prompt, max_tokens=max_tokens)
                text = self._extract_text(resp)
                payload["probe"] = {
                    "ok": True,
                    "duration_ms": round((time.time() - started) * 1000.0, 3),
                    "text": text,
                }
            except Exception as e:
                payload["ok"] = False
                payload["probe"] = {
                    "ok": False,
                    "duration_ms": round((time.time() - started) * 1000.0, 3),
                    "error": str(e),
                }
                payload["error"] = str(e)
        return payload

    def forward(
        self,
        prompt: Optional[str] = None,
        messages: Optional[Iterable[Dict[str, Any]]] = None,
        **kwargs: Any,
    ):
        if _check_capability is not None:
            _check_capability("network.mutate")
        inner = self._build_inner()
        started = time.time()
        err: str | None = None
        text = ""
        usage: dict[str, Any] | None = None
        call_kwargs = dict(kwargs)
        if bool(self._uses_codex_route):
            call_kwargs.pop("max_tokens", None)
        try:
            resp = inner.forward(
                prompt=prompt,
                messages=list(messages) if messages is not None else None,
                **call_kwargs,
            )
            text = self._extract_text(resp)
            usage = self._extract_usage(resp)
            return resp
        except Exception as e:
            err = str(e)
            text = err
            usage = None
            if self.strict:
                raise
            return {"choices": [{"text": text}], "usage": usage or {}}
        finally:
            self.history.append(
                DspyLmAuthCall(
                    model=self.requested_model,
                    auth_provider=self.auth_provider,
                    started_at=started,
                    ended_at=time.time(),
                    text=text,
                    usage=usage,
                    error=err,
                )
            )

    def generate(self, request: LMRequest, **kwargs: Any) -> LMResponse:
        if request.prompt is not None:
            resp = self.forward(prompt=request.prompt, **kwargs)
        else:
            msgs = [
                {"role": m.role, "content": m.content} for m in (request.messages or [])
            ]
            resp = self.forward(messages=msgs, **kwargs)
        return LMResponse(
            outputs=[self._extract_text(resp)],
            model=getattr(self, "model", None),
            usage=self._extract_usage(resp),
            raw=None,
        )

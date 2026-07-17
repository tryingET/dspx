# summary: "Adapts the Pi RPC client to DSPy and internal DSPx language-model calls."
# read_when:
#   - "Changing Pi RPC provider configuration, retry behavior, or LM response mapping."

from __future__ import annotations

import os
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional

from dspx.pi_rpc_client import PiRpcClient

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

if TYPE_CHECKING:  # typing-only import to keep mypy happy
    from dspy import BaseLM as DSPyBaseLM
else:  # pragma: no cover - runtime fallback binding
    try:
        from dspy import BaseLM as DSPyBaseLM
    except Exception:
        try:
            from dspy.models import BaseLM as DSPyBaseLM
        except Exception:

            class DSPyBaseLM:
                def __init__(
                    self, model: str = "pi-rpc", model_type: str = "text", **kwargs
                ) -> None:
                    self.model = model
                    self.model_type = model_type


@dataclass
class PiRpcRun:
    prompt: str
    text: str
    error: Optional[str] = None
    started_at: float | None = None
    ended_at: float | None = None
    duration_s: float | None = None


class PiRPCLM(DSPyBaseLM):
    """DSPy-compatible LM that talks to `pi --mode rpc` over a long-lived process."""

    def __init__(
        self,
        *,
        binary: str = "pi",
        provider: Optional[str] = None,
        model: Optional[str] = None,
        thinking: Optional[str] = None,
        no_tools: bool = True,
        no_session: bool = True,
        disable_resources: bool = True,
        extra_flags: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
        timeout: Optional[float] = 60.0,
        strict: bool = False,
    ) -> None:
        label = f"pi-rpc/{model or 'default'}"
        DSPyBaseLM.__init__(self, model=label, model_type="text")

        self.binary = binary
        self.provider = provider
        self.configured_model = model
        self.thinking = thinking
        self.no_tools = no_tools
        self.no_session = no_session
        self.disable_resources = disable_resources
        self.extra_flags = list(extra_flags or [])
        self.env = dict(env or {})
        self.cwd = cwd
        self.timeout = timeout
        self.strict = strict

        self.verbose: bool = os.getenv("DSPX_PI_VERBOSE", "0") == "1"
        self.history: List[PiRpcRun] = []

        try:
            if ProviderCapabilities is not None:
                caps = ProviderCapabilities(
                    supports_tools=False,
                    code_exec=False,
                    json_mode=False,
                    multi_turn=True,
                    structured_output_format="none",
                )
            else:
                caps = None
            if hasattr(InternalLMBase, "__init__"):
                InternalLMBase.__init__(self, capabilities=caps)  # type: ignore
        except Exception:
            pass

        self._bin_warned = False
        if shutil.which(self.binary) is None and not self._bin_warned:
            self._warn_missing_binary()

        self.client = PiRpcClient(
            binary=self.binary,
            provider=self.provider,
            model=self.configured_model,
            thinking=self.thinking,
            no_tools=self.no_tools,
            no_session=self.no_session,
            disable_resources=self.disable_resources,
            extra_flags=self.extra_flags,
            env=self.env,
            cwd=self.cwd,
            verbose=self.verbose,
        )

    @staticmethod
    def _should_retry_prompt_error(exc: Exception) -> bool:
        if isinstance(exc, TimeoutError):
            return False
        if isinstance(
            exc,
            (
                BrokenPipeError,
                ConnectionAbortedError,
                ConnectionResetError,
                EOFError,
            ),
        ):
            return True
        if isinstance(exc, OSError):
            return True
        text = str(exc).strip().lower()
        return any(
            marker in text
            for marker in (
                "broken pipe",
                "connection reset",
                "connection aborted",
                "pipe closed",
                "process exited",
                "process not running",
                "eof",
            )
        )

    def _call_prompt_with_retry(self, query: str) -> str:
        timeout = self.timeout
        try:
            return self.client.prompt(query, timeout=timeout).text
        except Exception as exc:
            if not self._should_retry_prompt_error(exc):
                raise
            # One best-effort restart + retry for process-level failures only.
            self.client.restart()
            return self.client.prompt(query, timeout=timeout).text

    def forward(
        self,
        prompt: Optional[str] = None,
        messages: Optional[Iterable[Dict[str, Any]]] = None,
        **kwargs: Any,
    ):
        query: str = (
            prompt if prompt is not None else self._messages_to_prompt(messages)
        ) or ""
        if self.verbose:
            ts = datetime.now().strftime("%H:%M:%S")
            print(f"[{ts}] PiRPCLM: prompting pi rpc …", file=sys.stderr)

        t0 = time.time()
        error: Optional[str] = None
        try:
            text = self._call_prompt_with_retry(query)
        except Exception as e:
            if self.strict:
                raise
            text = str(e)
            error = str(e)
        t1 = time.time()

        self.history.append(
            PiRpcRun(
                prompt=query,
                text=text,
                error=error,
                started_at=t0,
                ended_at=t1,
                duration_s=(t1 - t0),
            )
        )
        return _MinimalResponse(
            model=self.model,
            choices=[{"text": text}],
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        )

    def generate(self, request: "LMRequest", **kwargs):
        if LMRequest is None or LMResponse is None:
            raise RuntimeError("Internal DTOs not available")
        if request is None:
            raise ValueError("LMRequest is required")

        if getattr(request, "prompt", None):
            query = request.prompt
        else:
            msgs = getattr(request, "messages", None)
            query = self._messages_to_prompt(
                [{"role": m.role, "content": m.content} for m in (msgs or [])]
            )

        t0 = time.time()
        error: Optional[str] = None
        try:
            text = self._call_prompt_with_retry(query or "")
        except Exception as e:
            if self.strict:
                raise
            text = str(e)
            error = str(e)
        t1 = time.time()

        self.history.append(
            PiRpcRun(
                prompt=query or "",
                text=text,
                error=error,
                started_at=t0,
                ended_at=t1,
                duration_s=(t1 - t0),
            )
        )

        return LMResponse(outputs=[text], model=self.model, usage=None, raw=None)

    def close(self) -> None:
        self.client.close()

    @staticmethod
    def _messages_to_prompt(messages: Optional[Iterable[Dict[str, Any]]]) -> str:
        if not messages:
            return ""
        parts: List[str] = []
        for m in messages:
            role = str(m.get("role", "user"))
            content = str(m.get("content", "")).strip()
            if not content:
                continue
            parts.append(f"{role}: {content}")
        return "\n".join(parts).strip()

    def _warn_missing_binary(self) -> None:
        self._bin_warned = True
        try:
            print(
                f"[PiRPCLM] CLI '{self.binary}' not found in PATH. Install '@mariozechner/pi-coding-agent'.",
                file=sys.stderr,
            )
        except Exception:
            pass

    def __del__(self) -> None:  # pragma: no cover
        try:
            self.close()
        except Exception:
            pass


class _MinimalResponse:
    def __init__(
        self, model: str, choices: List[Dict[str, Any]], usage: Dict[str, Any]
    ):
        self.model = model
        self.choices = choices
        self.usage = usage

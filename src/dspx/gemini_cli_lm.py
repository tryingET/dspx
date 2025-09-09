"""
GeminiCLILM: DSPy-compatible wrapper around the `gemini` CLI headless mode.

Headless usage is `gemini -p "<prompt>"` per upstream docs.

This wrapper focuses on non-interactive runs and captures stdout as text.
Advanced flags and tooling are typically configured via settings.json; we
expose `env` and `extra_flags` to let callers influence behavior.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

# Internal DTO/provider base
try:
    from dspx.dtos import LMRequest, LMResponse  # type: ignore
    from dspx.lm_base import LMBase as InternalLMBase  # type: ignore
    from dspx.capabilities import ProviderCapabilities  # type: ignore
except Exception:  # pragma: no cover
    LMRequest = None  # type: ignore
    LMResponse = None  # type: ignore

    class InternalLMBase:  # type: ignore
        pass

    ProviderCapabilities = None  # type: ignore

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # typing-only import to keep mypy happy
    from dspy import BaseLM as DSPyBaseLM  # type: ignore
else:  # pragma: no cover - runtime fallback binding
    try:
        from dspy import BaseLM as DSPyBaseLM  # type: ignore
    except Exception:
        try:
            from dspy.models import BaseLM as DSPyBaseLM  # type: ignore
        except Exception:

            class DSPyBaseLM:  # type: ignore
                def __init__(
                    self, model: str = "gemini-cli", model_type: str = "text", **kwargs
                ) -> None:
                    self.model = model
                    self.model_type = model_type


@dataclass
class GeminiRun:
    prompt: str
    command: List[str]
    returncode: int
    stdout: str
    stderr: str
    text: str
    started_at: float | None = None
    ended_at: float | None = None
    duration_s: float | None = None


@dataclass
class _Running:
    command: List[str]
    cwd: Optional[str]
    env: dict
    popen: subprocess.Popen
    started_at: float


class GeminiCLILM(DSPyBaseLM, InternalLMBase):
    def __init__(
        self,
        *,
        binary: str = "gemini",
        cwd: Optional[str] = None,
        extra_flags: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        strict: bool = False,
    ) -> None:
        DSPyBaseLM.__init__(self, model="gemini-cli/text", model_type="text")
        self.binary = binary
        self.cwd = cwd
        self.extra_flags = list(extra_flags or [])
        self.env = dict(env or {})
        self.timeout = timeout
        self.strict = strict
        self.verbose: bool = os.getenv("DSPX_GEMINI_VERBOSE", "0") == "1"
        self.history: List[GeminiRun] = []

        try:
            if ProviderCapabilities is not None:
                caps = ProviderCapabilities(
                    supports_tools=True,
                    code_exec=False,
                    json_mode=False,
                    multi_turn=True,
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

    def forward(
        self,
        prompt: Optional[str] = None,
        messages: Optional[Iterable[Dict[str, Any]]] = None,
        **kwargs: Any,
    ):
        query: str = (
            prompt if prompt is not None else self._messages_to_prompt(messages)
        ) or ""
        cmd = self._build_command(query)
        if self.verbose:
            ts = datetime.now().strftime("%H:%M:%S")
            print(f"[{ts}] GeminiCLILM: launching gemini headless …")
        env = os.environ.copy()
        env.update(self.env)
        if shutil.which(self.binary) is None and not self._bin_warned:
            self._warn_missing_binary()
        t0 = time.time()
        # Capability: code.exec
        try:
            from dspx.policy import check_capability as _cap
        except Exception:
            _cap = None  # type: ignore
        if _cap is not None:
            _cap("code.exec")
        proc = subprocess.run(
            cmd,
            cwd=self.cwd or None,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=self.timeout,
            check=False,
        )
        t1 = time.time()
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        text = stdout if stdout else stderr
        if proc.returncode != 0 and self.strict:
            raise RuntimeError(
                f"gemini failed (exit={proc.returncode})\nCommand: {' '.join(cmd)}\nSTDERR:\n{stderr}\nSTDOUT:\n{stdout}"
            )
        self._store_history(query, cmd, proc.returncode, stdout, stderr, text, t0, t1)
        return _MinimalResponse(
            model=self.model,
            choices=[{"text": text}],
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        )

    def generate(self, request: "LMRequest", **kwargs):  # type: ignore[override]
        if LMRequest is None or LMResponse is None:
            raise RuntimeError("Internal DTOs not available")
        if request is None:
            raise ValueError("LMRequest is required")
        if getattr(request, "prompt", None):
            query = request.prompt  # type: ignore[attr-defined]
        else:
            msgs = getattr(request, "messages", None)  # type: ignore[attr-defined]
            query = self._messages_to_prompt(
                [{"role": m.role, "content": m.content} for m in (msgs or [])]
            )
        query_str: str = query or ""
        cmd = self._build_command(query_str)
        env = os.environ.copy()
        env.update(self.env)
        if shutil.which(self.binary) is None and not self._bin_warned:
            self._warn_missing_binary()
        t0 = time.time()
        # Capability: code.exec
        try:
            from dspx.policy import check_capability as _cap
        except Exception:
            _cap = None  # type: ignore
        if _cap is not None:
            _cap("code.exec")
        proc = subprocess.run(
            cmd,
            cwd=self.cwd or None,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=self.timeout,
            check=False,
        )
        t1 = time.time()
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        text = stdout if stdout else stderr
        if proc.returncode != 0 and self.strict:
            raise RuntimeError(
                f"gemini failed (exit={proc.returncode})\nCommand: {' '.join(cmd)}\nSTDERR:\n{stderr}\nSTDOUT:\n{stdout}"
            )
        self._store_history(
            query_str, cmd, proc.returncode, stdout, stderr, text, t0, t1
        )
        return LMResponse(outputs=[text], model=self.model, usage=None, raw=None)

    def start(
        self,
        *,
        prompt: Optional[str] = None,
        messages: Optional[Iterable[Dict[str, Any]]] = None,
    ) -> _Running:
        query: str = (
            prompt if prompt is not None else self._messages_to_prompt(messages)
        ) or ""
        env = os.environ.copy()
        env.update(self.env)
        cmd = self._build_command(query)
        # Capability: code.exec
        try:
            from dspx.policy import check_capability as _cap
        except Exception:
            _cap = None  # type: ignore
        if _cap is not None:
            _cap("code.exec")
        p = subprocess.Popen(
            cmd,
            cwd=self.cwd or None,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        return _Running(
            command=cmd, cwd=self.cwd or None, env=env, popen=p, started_at=time.time()
        )

    def collect(self, run: _Running) -> GeminiRun:
        proc = run.popen
        stdout, stderr = proc.communicate(timeout=self.timeout)
        stdout = (stdout or "").strip()
        stderr = (stderr or "").strip()
        text = stdout if stdout else stderr
        t1 = time.time()
        res = GeminiRun(
            prompt="",
            command=run.command,
            returncode=proc.returncode or 0,
            stdout=stdout,
            stderr=stderr,
            text=text,
            started_at=run.started_at,
            ended_at=t1,
            duration_s=(t1 - run.started_at),
        )
        self.history.append(res)
        return res

    def terminate(self, run: _Running) -> None:
        try:
            import os
            import signal

            os.killpg(run.popen.pid, signal.SIGTERM)
        except Exception:
            try:
                run.popen.terminate()
            except Exception:
                pass
        try:
            time.sleep(0.2)
            import os
            import signal

            os.killpg(run.popen.pid, signal.SIGKILL)
        except Exception:
            try:
                run.popen.kill()
            except Exception:
                pass

    def _build_command(self, query: str) -> List[str]:
        cmd: List[str] = [self.binary, "-p", query]
        if self.extra_flags:
            cmd.extend(self.extra_flags)
        return cmd

    def _store_history(
        self,
        prompt: str,
        cmd: List[str],
        rc: int,
        stdout: str,
        stderr: str,
        text: str,
        t0: float,
        t1: float,
    ) -> None:
        self.history.append(
            GeminiRun(
                prompt=prompt,
                command=cmd,
                returncode=rc,
                stdout=stdout,
                stderr=stderr,
                text=text,
                started_at=t0,
                ended_at=t1,
                duration_s=(t1 - t0),
            )
        )
        if self.verbose:
            ts = datetime.now().strftime("%H:%M:%S")
            dur = f"{(t1 - t0):.1f}s"
            snippet = text[:120].replace("\n", " ") + ("…" if len(text) > 120 else "")
            print(
                f"[{ts}] GeminiCLILM: finished (exit={rc}, dur={dur}). Output: {snippet}"
            )

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


class _MinimalResponse:
    def __init__(
        self, model: str, choices: List[Dict[str, Any]], usage: Dict[str, Any]
    ):
        self.model = model
        self.choices = choices
        self.usage = usage


def _print_safe(msg: str) -> None:
    try:
        print(msg)
    except Exception:
        pass


def _warn_msg(binary: str) -> str:
    return (
        f"[GeminiCLILM] CLI '{binary}' not found in PATH. "
        "Install '@google/gemini-cli' (npm/brew) and configure auth."
    )


def _missing_bin(binary: str) -> None:
    _print_safe(_warn_msg(binary))


# Bind as method to maintain consistency with other providers
def _warn_missing_binary(self) -> None:  # type: ignore
    self._bin_warned = True
    _missing_bin(self.binary)


# Attach method dynamically to class (keeps patch minimal)
setattr(GeminiCLILM, "_warn_missing_binary", _warn_missing_binary)

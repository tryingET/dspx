"""
ClaudeHeadlessLM: A DSPy-compatible wrapper around the "Claude Code" CLI
("claude") headless mode, so you can run it programmatically as an LM.

This mirrors the style of CodexExecLM and supports both DSPy's BaseLM
interface (forward) and the local InternalLMBase.generate() DTO.

Basic usage with DSPy directly:
    from dspx.claude_cli_lm import ClaudeHeadlessLM
    import dspy

    lm = ClaudeHeadlessLM(output_format="text")
    dspy.configure(lm=lm)
    qa = dspy.Predict("question -> answer")
    out = qa(question="Explain shell redirection > and >>")
    print(out.answer)

With FunctAI:
    from functai import configure
    from dspx.claude_cli_lm import ClaudeHeadlessLM

    configure(lm=ClaudeHeadlessLM(output_format="json"))

Notes:
- Requires the `claude` CLI installed and authenticated if needed.
- For multi-turn sessions, you can pass resume/continue flags or provide a
  session_id; when JSON output is used, returned session_id is stored on
  the instance (self.last_session_id) for convenience.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

# Optional internal DTO/provider interface for services
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

# Try to import BaseLM from DSPy (alias for clarity during type checking)
try:  # pragma: no cover
    from dspy import BaseLM as DSPyBaseLM  # type: ignore
except Exception:  # pragma: no cover
    try:
        from dspy.models import BaseLM as DSPyBaseLM  # type: ignore
    except Exception:  # pragma: no cover
        class DSPyBaseLM:
            def __init__(self, model: str = "claude-cli", model_type: str = "text", **kwargs) -> None:
                self.model = model
                self.model_type = model_type


@dataclass
class ClaudeRun:
    prompt: str
    command: List[str]
    returncode: int
    stdout: str
    stderr: str
    text: str
    json_obj: Optional[Dict[str, Any]] = None
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


class ClaudeHeadlessLM(DSPyBaseLM, InternalLMBase):
    """DSPy LM that shells out to `claude` CLI in headless mode.

    Parameters
    - binary: CLI binary name/path (default: "claude").
    - output_format: "text" | "json" | "stream-json" (default: "text").
    - append_system_prompt: Optional str to pass via --append-system-prompt.
    - allowed_tools: Optional str/list for --allowedTools.
    - disallowed_tools: Optional str/list for --disallowedTools.
    - permission_mode: e.g. "acceptEdits"; passed via --permission-mode (only with --print).
    - mcp_config: Optional path to JSON servers file for --mcp-config.
    - permission_prompt_tool: Optional tool name for --permission-prompt-tool.
    - resume: Optional session id for --resume.
    - continue_latest: If True, add --continue.
    - cwd: Optional working directory; if provided and use_cli_cwd is True, also pass --cwd.
    - extra_flags: Additional CLI flags.
    - env: Extra environment variables for subprocess.
    - timeout: Optional timeout (seconds) for the subprocess.
    - strict: If True, raise when CLI exits non-zero.
    - use_cli_cwd: If True, pass --cwd to CLI (else only set subprocess cwd).
    """

    def __init__(
        self,
        *,
        binary: str = "claude",
        output_format: str = "text",
        append_system_prompt: Optional[str] = None,
        allowed_tools: Optional[Iterable[str] | str] = None,
        disallowed_tools: Optional[Iterable[str] | str] = None,
        permission_mode: Optional[str] = None,
        mcp_config: Optional[str] = None,
        permission_prompt_tool: Optional[str] = None,
        resume: Optional[str] = None,
        continue_latest: bool = False,
        cwd: Optional[str] = None,
        extra_flags: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        strict: bool = False,
        use_cli_cwd: bool = False,
    ) -> None:
        model_label = f"claude-cli/{output_format}"
        DSPyBaseLM.__init__(self, model=model_label, model_type="text")
        # config
        self.binary = binary
        self.output_format = output_format
        self.append_system_prompt = append_system_prompt
        self.allowed_tools = allowed_tools
        self.disallowed_tools = disallowed_tools
        self.permission_mode = permission_mode
        self.mcp_config = mcp_config
        self.permission_prompt_tool = permission_prompt_tool
        self.resume = resume
        self.continue_latest = continue_latest
        self.cwd = cwd
        self.extra_flags = list(extra_flags or [])
        self.env = dict(env or {})
        self.timeout = timeout
        self.strict = strict
        self.use_cli_cwd = use_cli_cwd

        # runtime
        self.verbose: bool = os.getenv("DSPX_CLAUDE_VERBOSE", "0") == "1"
        self.history: List[ClaudeRun] = []
        self.last_session_id: Optional[str] = None

        # Attach capabilities if InternalLMBase exists
        try:
            if ProviderCapabilities is not None:
                caps = ProviderCapabilities(
                    supports_tools=True,  # via allowedTools
                    code_exec=False,  # CLI can call Bash via tools, but we don't assume local exec here
                    json_mode=(self.output_format in {"json", "stream-json"}),
                    multi_turn=True,
                )
            else:
                caps = None
            if hasattr(InternalLMBase, "__init__"):
                InternalLMBase.__init__(self, capabilities=caps)  # type: ignore
        except Exception:
            pass

        # Soft-check binary availability
        self._bin_warned = False
        if shutil.which(self.binary) is None and not self._bin_warned:
            self._warn_missing_binary()

    # DSPy entrypoint: forward(prompt|messages)
    def forward(
        self,
        prompt: Optional[str] = None,
        messages: Optional[Iterable[Dict[str, Any]]] = None,
        **kwargs: Any,
    ):
        query: str = (prompt if prompt is not None else self._messages_to_prompt(messages)) or ""
        cmd = self._build_command(query)

        if self.verbose:
            ts = datetime.now().strftime("%H:%M:%S")
            print(
                f"[{ts}] ClaudeHeadlessLM: launching claude (fmt={self.output_format})…"
            )

        env = os.environ.copy()
        env.update(self.env)
        if shutil.which(self.binary) is None and not self._bin_warned:
            self._warn_missing_binary()
        t0 = time.time()
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

        text, jobj = self._extract_text_and_json(stdout, stderr)
        if proc.returncode != 0 and self.strict:
            raise RuntimeError(
                f"claude failed (exit={proc.returncode})\nCommand: {' '.join(cmd)}\nSTDERR:\n{stderr}\nSTDOUT:\n{stdout}"
            )

        self._store_history(
            query, cmd, proc.returncode, stdout, stderr, text, jobj, t0, t1
        )

        response = _MinimalResponse(
            model=self.model,
            choices=[{"text": text}],
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        )
        return response

    # Internal DTO entrypoint
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

        cmd = self._build_command((query or ""))
        env = os.environ.copy()
        env.update(self.env)
        if shutil.which(self.binary) is None and not self._bin_warned:
            self._warn_missing_binary()
        t0 = time.time()
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
        text, jobj = self._extract_text_and_json(stdout, stderr)

        if proc.returncode != 0 and self.strict:
            raise RuntimeError(
                f"claude failed (exit={proc.returncode})\nCommand: {' '.join(cmd)}\nSTDERR:\n{stderr}\nSTDOUT:\n{stdout}"
            )

        self._store_history(
            query, cmd, proc.returncode, stdout, stderr, text, jobj, t0, t1
        )
        return LMResponse(outputs=[text], model=self.model, usage=None, raw=jobj)

    # Advanced: asynchronous helpers
    def start(
        self,
        *,
        prompt: Optional[str] = None,
        messages: Optional[Iterable[Dict[str, Any]]] = None,
    ) -> _Running:
        query: str = (prompt if prompt is not None else self._messages_to_prompt(messages)) or ""
        env = os.environ.copy()
        env.update(self.env)
        cmd = self._build_command(query)
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

    def collect(self, run: _Running) -> ClaudeRun:
        proc = run.popen
        stdout, stderr = proc.communicate(timeout=self.timeout)
        stdout = (stdout or "").strip()
        stderr = (stderr or "").strip()
        text, jobj = self._extract_text_and_json(stdout, stderr)
        t1 = time.time()
        res = ClaudeRun(
            prompt="",
            command=run.command,
            returncode=proc.returncode or 0,
            stdout=stdout,
            stderr=stderr,
            text=text,
            json_obj=jobj,
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

    # Helpers
    def _build_command(self, query: str) -> List[str]:
        cmd: List[str] = [self.binary, "-p", query]
        # Respect output format
        if self.output_format:
            cmd.extend(["--output-format", self.output_format])
        # Options
        if self.append_system_prompt:
            cmd.extend(["--append-system-prompt", self.append_system_prompt])
        if self.permission_mode:
            cmd.extend(["--permission-mode", self.permission_mode])
        if self.allowed_tools is not None:
            cmd.extend(["--allowedTools", self._format_tools(self.allowed_tools)])
        if self.disallowed_tools is not None:
            cmd.extend(["--disallowedTools", self._format_tools(self.disallowed_tools)])
        if self.mcp_config:
            cmd.extend(["--mcp-config", self.mcp_config])
        if self.permission_prompt_tool:
            cmd.extend(["--permission-prompt-tool", self.permission_prompt_tool])
        if self.resume:
            cmd.extend(["--resume", self.resume])
        elif self.continue_latest:
            cmd.append("--continue")
        # CLI cwd flag if requested (we also set subprocess cwd separately)
        if self.cwd and self.use_cli_cwd:
            cmd.extend(["--cwd", self.cwd])
        if self.extra_flags:
            cmd.extend(self.extra_flags)
        return cmd

    def _format_tools(self, tools: Iterable[str] | str) -> str:
        if isinstance(tools, str):
            return tools
        return ",".join([str(t) for t in tools])

    def _extract_text_and_json(
        self, stdout: str, stderr: str
    ) -> tuple[str, Optional[Dict[str, Any]]]:
        text = stdout if stdout else stderr
        jobj: Optional[Dict[str, Any]] = None
        if self.output_format == "json":
            try:
                jobj = json.loads(stdout)
                # common schema per docs: result, session_id
                text = str(jobj.get("result", "")) or text
                sid = jobj.get("session_id")
                if isinstance(sid, str) and sid:
                    self.last_session_id = sid
            except Exception:
                # fallback to raw text
                jobj = None
        elif self.output_format == "stream-json":
            # Best-effort: take last non-empty JSON line as result
            last_obj = None
            for line in (stdout or "").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    last_obj = json.loads(line)
                except Exception:
                    continue
            if isinstance(last_obj, dict):
                jobj = last_obj
                text = str(last_obj.get("result", "")) or text
                sid = last_obj.get("session_id")
                if isinstance(sid, str) and sid:
                    self.last_session_id = sid
        return text.strip(), jobj

    def _store_history(
        self,
        prompt: str,
        cmd: List[str],
        rc: int,
        stdout: str,
        stderr: str,
        text: str,
        jobj: Optional[Dict[str, Any]],
        t0: float,
        t1: float,
    ) -> None:
        self.history.append(
            ClaudeRun(
                prompt=prompt,
                command=cmd,
                returncode=rc,
                stdout=stdout,
                stderr=stderr,
                text=text,
                json_obj=jobj,
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
                f"[{ts}] ClaudeHeadlessLM: finished (exit={rc}, dur={dur}). Output: {snippet}"
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

    def _warn_missing_binary(self) -> None:
        self._bin_warned = True
        msg = (
            f"[ClaudeHeadlessLM] CLI '{self.binary}' not found in PATH. "
            "Install the 'claude' CLI and configure auth; use --print/-p for headless."
        )
        try:
            print(msg)
        except Exception:
            pass


class _MinimalResponse:
    def __init__(
        self, model: str, choices: List[Dict[str, Any]], usage: Dict[str, Any]
    ):
        self.model = model
        self.choices = choices
        self.usage = usage

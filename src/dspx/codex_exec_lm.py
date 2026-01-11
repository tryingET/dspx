"""
CodexExecLM: A minimal DSPy-compatible wrapper around the Codex CLI
(`codex exec`) so you can use Codex Exec as the active LM in DSPy.

Usage:
    from dspx.codex_exec_lm import CodexExecLM
    import dspy

    lm = CodexExecLM(model_flag="gpt-4.1", auto_mode=True)
    dspy.configure(lm=lm)

    qa = dspy.Predict("question -> answer")
    out = qa(question="Write a Python function to check if 37 is prime.")
    print(out.answer)

Notes:
- This wrapper shells out to `codex exec` and captures stdout as the LM output.
- It supports both `prompt` and `messages` input styles; messages are flattened
  into a simple prompt with role tags.

Requirements:
- Codex CLI installed and authenticated (`codex --version`, `codex auth whoami`).
- DSPy installed (`pip install dspy-ai`).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
import time
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


# Try to import BaseLM from DSPy, alias to avoid redefinition noise in type checkers.
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
                    self, model: str = "codex-exec", model_type: str = "text", **kwargs
                ) -> None:
                    self.model = model
                    self.model_type = model_type


@dataclass
class CodexExecResult:
    prompt: str
    command: List[str]
    returncode: int
    stdout: str
    stderr: str
    text: str  # Final text used as completion (stdout/last-message/stderr)
    started_at: float | None = None
    ended_at: float | None = None
    duration_s: float | None = None


@dataclass
class _Running:
    command: List[str]
    cwd: Optional[str]
    env: dict
    popen: subprocess.Popen
    last_msg_file: Optional[str]
    started_at: float


class CodexExecLM(DSPyBaseLM, InternalLMBase):
    """DSPy-compatible LM that proxies calls to `codex exec`.

    Parameters
    - model_flag: Optional model name to pass to Codex (e.g., "gpt-4.1").
    - auto_mode: If True, adds `--full-auto` for non-interactive runs.
    - binary: Codex CLI binary name/path (default: "codex").
    - workspace: Optional working directory for Codex to run in.
    - extra_flags: Additional CLI flags to pass to `codex exec`.
    - env: Extra environment variables for the subprocess.
    - timeout: Optional timeout (seconds) for the Codex subprocess.
    - strict: If True, raise an exception when Codex exits non-zero.
    - capture_stderr: If True, append stderr to output when stdout is empty.
    """

    def __init__(
        self,
        model_flag: Optional[str] = None,
        auto_mode: bool = True,
        *,
        binary: str = "codex",
        workspace: Optional[str] = None,
        extra_flags: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        strict: bool = False,
        capture_stderr: bool = True,
        capture_last_message: bool = True,
        dangerously_bypass: bool = False,
        reasoning_effort: Optional[str] = None,
        enable_search: bool = False,
    ) -> None:
        # Compose a descriptive model label for DSPy logs/history.
        model_label = f"codex-exec/{model_flag or 'default'}"
        # BaseLM in DSPy>=3 requires a model string and a model_type.
        DSPyBaseLM.__init__(self, model=model_label, model_type="text")
        self.model_flag = model_flag
        self.auto_mode = auto_mode
        self.binary = binary
        self.workspace = workspace
        self.extra_flags = list(extra_flags or [])
        self.env = dict(env or {})
        self.timeout = timeout
        self.strict = strict
        self.capture_stderr = capture_stderr
        self.capture_last_message = capture_last_message
        self.dangerously_bypass = dangerously_bypass
        self.reasoning_effort = reasoning_effort
        self.enable_search = enable_search
        # Verbose logging for visibility; set via env DSPX_CODEX_VERBOSE=1
        self.verbose: bool = os.getenv("DSPX_CODEX_VERBOSE", "0") == "1"

        # history of calls for debugging/inspection
        self.history: List[CodexExecResult] = []

        # Initialize internal LMBase (capabilities) if available
        try:
            caps = (
                ProviderCapabilities(code_exec=True, supports_tools=False)
                if ProviderCapabilities is not None
                else None
            )
            if hasattr(InternalLMBase, "__init__"):
                InternalLMBase.__init__(self, capabilities=caps)  # type: ignore
        except Exception:
            pass

        # Validate binary availability early (but don't hard-fail; soft warn once).
        self._bin_warned = False
        if shutil.which(self.binary) is None and not self._bin_warned:
            self._warn_missing_binary()

    # DSPy will call `forward`; return an OpenAI-like response object.
    def forward(
        self,
        prompt: Optional[str] = None,
        messages: Optional[Iterable[Dict[str, Any]]] = None,
        **kwargs: Any,
    ):
        query: str = (
            prompt if prompt is not None else self._messages_to_prompt(messages)
        ) or ""
        # Avoid passing large/unsafe prompts as argv. Use stdin when needed.
        use_stdin = (
            ("\x00" in query)
            or (len(query) > 32768)
            or os.getenv("DSPX_CODEX_STDIN", "0") == "1"
        )
        cmd = self._build_command("-" if use_stdin else query)

        if self.verbose:
            ts = datetime.now().strftime("%H:%M:%S")
            print(
                f"[{ts}] CodexExecLM: launching codex exec (model={self.model_flag or 'default'}, auto={self.auto_mode}, bypass={self.dangerously_bypass})…"
            )

        # Merge env with current process env; optionally filter via allowlist.
        env = self._build_subprocess_env()
        if shutil.which(self.binary) is None and not self._bin_warned:
            self._warn_missing_binary()

        # Optionally capture only the agent's last message via a temp file.
        last_msg_file: Optional[str] = None
        cmd_for_run = list(cmd)
        if self.capture_last_message:
            import tempfile

            fd, last_msg_file = tempfile.mkstemp(prefix="codex_last_", suffix=".txt")
            os.close(fd)
            cmd_for_run.extend(["--output-last-message", last_msg_file])

        # Capability: code.exec
        try:
            from dspx.policy import check_capability as _cap
        except Exception:
            _cap = None  # type: ignore
        if _cap is not None:
            _cap("code.exec")

        t0 = time.time()
        proc = subprocess.run(
            cmd_for_run,
            cwd=self.workspace or None,
            env=env,
            input=(query if use_stdin else None),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=self.timeout,
            check=False,
        )

        t1 = time.time()
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()

        if proc.returncode != 0 and self.strict:
            # Include captured logs for easier debugging.
            raise RuntimeError(
                f"codex exec failed (exit={proc.returncode}).\nCommand: {' '.join(cmd)}\nSTDERR:\n{stderr}\nSTDOUT:\n{stdout}"
            )

        # Prefer the last message file if present; else fallback to stdout/stderr.
        text = ""
        if last_msg_file and os.path.exists(last_msg_file):
            try:
                with open(last_msg_file, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read().strip()
            except Exception:
                text = ""
            finally:
                try:
                    os.remove(last_msg_file)
                except Exception:
                    pass
        if not text:
            # Optionally surface stderr if stdout is empty.
            text = stdout if stdout else (stderr if self.capture_stderr else "")

        # Record call history for inspection.
        self.history.append(
            CodexExecResult(
                prompt=query,
                command=cmd,
                returncode=proc.returncode,
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
            summary = text[:120].replace("\n", " ") + ("…" if len(text) > 120 else "")
            print(
                f"[{ts}] CodexExecLM: finished (exit={proc.returncode}, dur={dur}). Output: {summary}"
            )

        # Build a minimal OpenAI-like response object for DSPy to process.
        response = _MinimalResponse(
            model=self.model,
            choices=[
                {"text": text}
            ],  # BaseLM._process_completion supports dict choices
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        )
        return response

    # Advanced: asynchronous execution helpers for orchestration layers
    def start(
        self,
        *,
        prompt: Optional[str] = None,
        messages: Optional[Iterable[Dict[str, Any]]] = None,
    ) -> _Running:
        query: str = (
            prompt if prompt is not None else self._messages_to_prompt(messages)
        ) or ""
        env = self._build_subprocess_env()
        if shutil.which(self.binary) is None and not self._bin_warned:
            self._warn_missing_binary()
        last_msg_file: Optional[str] = None
        cmd_for_run = list(self._build_command(query))
        if self.capture_last_message:
            import tempfile

            fd, last_msg_file = tempfile.mkstemp(prefix="codex_last_", suffix=".txt")
            os.close(fd)
            cmd_for_run.extend(["--output-last-message", last_msg_file])
        p = subprocess.Popen(
            cmd_for_run,
            cwd=self.workspace or None,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        return _Running(
            command=cmd_for_run,
            cwd=self.workspace or None,
            env=env,
            popen=p,
            last_msg_file=last_msg_file,
            started_at=time.time(),
        )

    def collect(self, run: _Running) -> CodexExecResult:
        proc = run.popen
        stdout, stderr = proc.communicate(timeout=self.timeout)
        stdout = (stdout or "").strip()
        stderr = (stderr or "").strip()
        text = ""
        if run.last_msg_file and os.path.exists(run.last_msg_file):
            try:
                with open(
                    run.last_msg_file, "r", encoding="utf-8", errors="ignore"
                ) as f:
                    text = f.read().strip()
            finally:
                try:
                    os.remove(run.last_msg_file)
                except Exception:
                    pass
        if not text:
            text = stdout if stdout else (stderr if self.capture_stderr else "")
        t1 = time.time()
        res = CodexExecResult(
            prompt="",  # unknown here
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

            # Send SIGTERM to the whole process group
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
        if run.last_msg_file:
            try:
                if os.path.exists(run.last_msg_file):
                    os.remove(run.last_msg_file)
            except Exception:
                pass

    # Internal services entrypoint: DTO-based generate()
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
        env = self._build_subprocess_env()
        if shutil.which(self.binary) is None and not self._bin_warned:
            self._warn_missing_binary()

        # Optionally capture only the agent's last message via a temp file.
        last_msg_file: Optional[str] = None
        cmd_for_run = list(cmd)
        if self.capture_last_message:
            import tempfile

            fd, last_msg_file = tempfile.mkstemp(prefix="codex_last_", suffix=".txt")
            os.close(fd)
            cmd_for_run.extend(["--output-last-message", last_msg_file])

        # Capability: code.exec
        try:
            from dspx.policy import check_capability as _cap
        except Exception:
            _cap = None  # type: ignore
        if _cap is not None:
            _cap("code.exec")
        t0 = time.time()
        proc = subprocess.run(
            cmd_for_run,
            cwd=self.workspace or None,
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

        if proc.returncode != 0 and self.strict:
            raise RuntimeError(
                f"codex exec failed (exit={proc.returncode}).\nCommand: {' '.join(cmd_for_run)}\nSTDERR:\n{stderr}\nSTDOUT:\n{stdout}"
            )

        # Prefer last message file
        text = ""
        if last_msg_file and os.path.exists(last_msg_file):
            try:
                with open(last_msg_file, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read().strip()
            finally:
                try:
                    os.remove(last_msg_file)
                except Exception:
                    pass
        if not text:
            text = stdout if stdout else (stderr if self.capture_stderr else "")

        # Record history
        self.history.append(
            CodexExecResult(
                prompt=query_str,
                command=cmd_for_run,
                returncode=proc.returncode,
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
            summary = text[:120].replace("\n", " ") + ("…" if len(text) > 120 else "")
            print(
                f"[{ts}] CodexExecLM.generate: finished (exit={proc.returncode}, dur={dur}). Output: {summary}"
            )

        return LMResponse(outputs=[text], model=self.model, usage=None, raw=None)

    # Helpers
    def _build_command(self, query: str) -> List[str]:
        cmd: List[str] = [self.binary]
        if self.enable_search:
            cmd.append("--search")
        cmd.append("exec")
        if self.dangerously_bypass:
            cmd.append("--dangerously-bypass-approvals-and-sandbox")
        elif self.auto_mode:
            cmd.append("--full-auto")
        # Reduce noise in stdout for easier parsing
        cmd.extend(["--color", "never", "--skip-git-repo-check"])
        if self.model_flag:
            cmd.extend(["--model", self.model_flag])
        if self.reasoning_effort:
            # Pass as config override; Codex parses JSON if possible, otherwise literal
            cmd.extend(["-c", f'model_reasoning_effort="{self.reasoning_effort}"'])
        if self.extra_flags:
            cmd.extend(self.extra_flags)
        # The final argument is the query/prompt.
        cmd.append(query)
        return cmd

    @staticmethod
    def _messages_to_prompt(messages: Optional[Iterable[Dict[str, Any]]]) -> str:
        if not messages:
            return ""
        # Flatten chat messages into a simple prompt for the CLI.
        lines: List[str] = []
        for m in messages:
            role = str(m.get("role", "user"))
            content = str(m.get("content", "")).strip()
            if not content:
                continue
            lines.append(f"{role}: {content}")
        return "\n".join(lines).strip()

    def _warn_missing_binary(self) -> None:
        self._bin_warned = True
        msg = (
            f"[CodexExecLM] CLI '{self.binary}' not found in PATH. "
            "Install Codex CLI and authenticate (codex --version, codex auth whoami)."
        )
        try:
            print(msg)
        except Exception:
            pass

    # --- Sandbox helpers ---
    def _build_subprocess_env(self) -> Dict[str, str]:
        """Build the environment for Codex subprocess with optional allow/deny filtering.

        Controls (env vars):
        - DSPX_CODEX_ENV_ALLOWLIST: comma-separated names or prefixes with '*' suffix
          (e.g., "PATH,HOME,CODEX_*,OPENAI_*"). If unset/empty, inherit full env.
        - DSPX_CODEX_ENV_DENYLIST: comma-separated names to drop after allowlist processing.
        - Minimal baseline always kept: PATH, HOME, USER, LOGNAME, SHELL, TERM, TMPDIR, TEMP, PWD.

        Additionally merges any explicit env passed to CodexExecLM(env=...).
        """
        # Start from current process env
        base = os.environ.copy()
        # Always keep a minimal baseline set
        baseline_keep = {
            "PATH",
            "HOME",
            "USER",
            "LOGNAME",
            "SHELL",
            "TERM",
            "TMPDIR",
            "TEMP",
            "PWD",
        }

        allow_raw = os.getenv("DSPX_CODEX_ENV_ALLOWLIST", "").strip()
        deny_raw = os.getenv("DSPX_CODEX_ENV_DENYLIST", "").strip()

        # If no allowlist configured, behave as before (inherit all + overrides)
        if not allow_raw:
            env = base
        else:
            patterns = [p.strip() for p in allow_raw.split(",") if p.strip()]

            def allowed(name: str) -> bool:
                for p in patterns:
                    if p.endswith("*"):
                        if name.startswith(p[:-1]):
                            return True
                    elif name == p:
                        return True
                return False

            env = {k: v for k, v in base.items() if (k in baseline_keep) or allowed(k)}

        # Apply denylist last
        if deny_raw:
            for n in [p.strip() for p in deny_raw.split(",") if p.strip()]:
                env.pop(n, None)

        # Merge explicit overrides provided to the LM (highest precedence)
        try:
            # self.env is set in __init__
            env.update(self.env)
        except Exception:
            pass

        return env


class _MinimalResponse:
    """A lightweight, OpenAI-like response container for DSPy.

    Attributes required by DSPy BaseLM processing:
    - model: str
    - choices: list[dict | obj with .message.content]
    - usage: dict-like
    """

    def __init__(
        self, model: str, choices: List[Dict[str, Any]], usage: Dict[str, Any]
    ):
        self.model = model
        self.choices = choices
        self.usage = usage

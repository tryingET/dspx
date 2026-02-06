from __future__ import annotations

import json
import os
import queue
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class PiPromptResult:
    text: str
    raw_agent_end: Optional[dict[str, Any]] = None


class PiRpcClient:
    """Minimal client for `pi --mode rpc` over stdio.

    - single long-lived subprocess
    - serialized prompt calls (single-flight)
    - robust to non-JSON noise lines on stdout
    """

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
        verbose: bool = False,
    ) -> None:
        self.binary = binary
        self.provider = provider
        self.model = model
        self.thinking = thinking
        self.no_tools = no_tools
        self.no_session = no_session
        self.disable_resources = disable_resources
        self.extra_flags = list(extra_flags or [])
        self.env = dict(env or {})
        self.cwd = cwd
        self.verbose = verbose

        self._proc: Optional[subprocess.Popen[str]] = None
        self._stdout_queue: Optional[queue.Queue[Optional[str]]] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._seq = 0

    def _build_command(self) -> List[str]:
        cmd: List[str] = [self.binary, "--mode", "rpc"]
        if self.provider:
            cmd.extend(["--provider", self.provider])
        if self.model:
            cmd.extend(["--model", self.model])
        if self.thinking:
            cmd.extend(["--thinking", self.thinking])
        if self.no_session:
            cmd.append("--no-session")
        if self.no_tools:
            cmd.append("--no-tools")
        if self.disable_resources:
            cmd.extend(
                [
                    "--no-extensions",
                    "--no-skills",
                    "--no-prompt-templates",
                    "--no-themes",
                ]
            )
        if self.extra_flags:
            cmd.extend(self.extra_flags)
        return cmd

    def _start_reader(self, proc: subprocess.Popen[str]) -> None:
        q: queue.Queue[Optional[str]] = queue.Queue()
        self._stdout_queue = q

        def _reader() -> None:
            try:
                if proc.stdout is None:
                    q.put(None)
                    return
                for line in proc.stdout:
                    q.put(line)
            finally:
                q.put(None)

        th = threading.Thread(target=_reader, daemon=True)
        th.start()
        self._reader_thread = th

    def _ensure_started(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return

        env = os.environ.copy()
        env.update(self.env)
        cmd = self._build_command()

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            cwd=self.cwd or None,
            env=env,
            start_new_session=True,
        )
        self._proc = proc
        self._start_reader(proc)

    def close(self) -> None:
        proc = self._proc
        self._proc = None
        self._stdout_queue = None
        self._reader_thread = None

        if proc is None:
            return
        if proc.poll() is not None:
            return
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except Exception:
            try:
                proc.terminate()
            except Exception:
                pass
        try:
            proc.wait(timeout=0.5)
        except Exception:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def restart(self) -> None:
        self.close()
        self._ensure_started()

    def _send(self, payload: dict[str, Any]) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None:
            raise RuntimeError("pi rpc process is not running")
        line = json.dumps(payload, ensure_ascii=False)
        proc.stdin.write(line + "\n")
        proc.stdin.flush()

    def _read_json_line(self, *, deadline: Optional[float]) -> dict[str, Any]:
        q = self._stdout_queue
        if q is None:
            raise RuntimeError("pi rpc process is not running")

        while True:
            timeout: Optional[float]
            if deadline is None:
                timeout = None
            else:
                timeout = max(0.0, deadline - time.time())
                if timeout <= 0.0:
                    raise TimeoutError("timed out waiting for pi rpc output")

            try:
                line = q.get(timeout=timeout)
            except queue.Empty:
                raise TimeoutError("timed out waiting for pi rpc output") from None

            if line is None:
                rc = self._proc.poll() if self._proc is not None else None
                raise RuntimeError(f"pi rpc process exited (rc={rc})")

            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                # Tolerate unexpected non-JSON lines from wrappers/plugins.
                continue
            if isinstance(obj, dict):
                return obj

    @staticmethod
    def _extract_text_from_message(msg: dict[str, Any]) -> str:
        content = msg.get("content")
        if isinstance(content, str):
            return content.strip()
        if not isinstance(content, list):
            return ""
        parts: list[str] = []
        for c in content:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "text":
                txt = c.get("text")
                if isinstance(txt, str) and txt:
                    parts.append(txt)
        return "".join(parts).strip()

    def prompt(
        self, message: str, *, timeout: Optional[float] = None
    ) -> PiPromptResult:
        with self._lock:
            self._ensure_started()
            self._seq += 1
            req_id = f"prompt-{self._seq}"
            deadline = None if timeout is None else (time.time() + float(timeout))

            self._send({"id": req_id, "type": "prompt", "message": message})

            got_prompt_ack = False
            deltas: list[str] = []
            agent_end: Optional[dict[str, Any]] = None

            try:
                while True:
                    obj = self._read_json_line(deadline=deadline)
                    typ = str(obj.get("type") or "")

                    if typ == "response" and obj.get("id") == req_id:
                        if obj.get("command") == "prompt":
                            if not bool(obj.get("success", False)):
                                err = obj.get("error") or "prompt command failed"
                                raise RuntimeError(str(err))
                            got_prompt_ack = True
                        continue

                    if typ == "message_update":
                        ev = obj.get("assistantMessageEvent")
                        if isinstance(ev, dict) and ev.get("type") == "text_delta":
                            delta = ev.get("delta")
                            if isinstance(delta, str):
                                deltas.append(delta)
                        continue

                    if typ == "agent_end":
                        agent_end = obj
                        break
            except TimeoutError:
                # Try to abort current run so next call can proceed.
                try:
                    self._send({"type": "abort"})
                except Exception:
                    pass
                raise

            if not got_prompt_ack:
                raise RuntimeError("missing prompt ack from pi rpc")

            text = "".join(deltas).strip()
            if text:
                return PiPromptResult(text=text, raw_agent_end=agent_end)

            # Fallback: recover final assistant message from agent_end payload.
            if isinstance(agent_end, dict):
                msgs = agent_end.get("messages")
                if isinstance(msgs, list):
                    for m in reversed(msgs):
                        if isinstance(m, dict) and m.get("role") == "assistant":
                            txt = self._extract_text_from_message(m)
                            if txt:
                                return PiPromptResult(text=txt, raw_agent_end=agent_end)

            return PiPromptResult(text="", raw_agent_end=agent_end)

    def __del__(self) -> None:  # pragma: no cover
        try:
            self.close()
        except Exception:
            pass

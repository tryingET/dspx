from __future__ import annotations

import json
import queue
from pathlib import Path
from typing import Any, cast

from dspx.dtos import LMRequest
from dspx.pi_rpc_client import PiRpcClient
from dspx.pi_rpc_lm import PiRPCLM
from dspx.provider_registry import create_from_env, ensure_default_providers


class _DummyProc:
    def poll(self) -> int | None:
        return None


def _write_fake_pi_rpc_bin(path: Path) -> None:
    script = """#!/usr/bin/env python3
import json
import sys
import time

print(json.dumps({"type": "session", "version": 3, "id": "fake", "cwd": "."}), flush=True)

for raw in sys.stdin:
    raw = raw.strip()
    if not raw:
        continue
    try:
        cmd = json.loads(raw)
    except Exception:
        continue

    typ = cmd.get("type")
    if typ == "get_state":
        print(json.dumps({
            "type": "response",
            "id": cmd.get("id"),
            "command": "get_state",
            "success": True,
            "data": {"isStreaming": False},
        }), flush=True)
        continue

    if typ == "abort":
        print(json.dumps({
            "type": "response",
            "id": cmd.get("id"),
            "command": "abort",
            "success": True,
        }), flush=True)
        continue

    if typ == "prompt":
        msg = str(cmd.get("message") or "")
        req_id = cmd.get("id")
        print(json.dumps({
            "type": "response",
            "id": req_id,
            "command": "prompt",
            "success": True,
        }), flush=True)

        if msg.startswith("sleep:"):
            try:
                time.sleep(float(msg.split(":", 1)[1]))
            except Exception:
                pass

        if msg == "emit-noise":
            print("NON_JSON_NOISE", flush=True)

        text = f"echo: {msg}"
        print(json.dumps({
            "type": "message_update",
            "message": {"role": "assistant", "content": []},
            "assistantMessageEvent": {
                "type": "text_delta",
                "delta": text,
                "contentIndex": 0,
            },
        }), flush=True)
        print(json.dumps({
            "type": "agent_end",
            "messages": [
                {
                    "role": "assistant",
                    "content": [{"type": "text", "text": text}],
                }
            ],
        }), flush=True)
        continue

    print(json.dumps({
        "type": "response",
        "id": cmd.get("id"),
        "command": str(typ),
        "success": False,
        "error": "unsupported",
    }), flush=True)
"""
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)


def test_pi_rpc_client_drains_stale_buffer_before_prompt() -> None:
    client = PiRpcClient()
    stdout_queue: queue.Queue[str | None] = queue.Queue()
    client._proc = cast(Any, _DummyProc())
    client._stdout_queue = stdout_queue
    client._ensure_started = cast(Any, lambda: None)

    stale = {
        "type": "agent_end",
        "messages": [
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "stale-old-output"}],
            }
        ],
    }
    stdout_queue.put(json.dumps(stale))

    def _send(payload: dict[str, object]) -> None:
        req_id = str(payload.get("id") or "")
        text = f"fresh: {payload.get('message')}"
        stdout_queue.put(
            json.dumps(
                {
                    "type": "response",
                    "id": req_id,
                    "command": "prompt",
                    "success": True,
                }
            )
        )
        stdout_queue.put(
            json.dumps(
                {
                    "type": "message_update",
                    "assistantMessageEvent": {"type": "text_delta", "delta": text},
                }
            )
        )
        stdout_queue.put(
            json.dumps(
                {
                    "type": "agent_end",
                    "messages": [
                        {
                            "role": "assistant",
                            "content": [{"type": "text", "text": text}],
                        }
                    ],
                }
            )
        )

    cast(Any, client)._send = _send

    result = client.prompt("new-request", timeout=1.0)

    assert result.text == "fresh: new-request"


def test_pi_rpc_client_timeout_restarts_before_next_prompt() -> None:
    client = PiRpcClient()
    stdout_queue: queue.Queue[str | None] = queue.Queue()
    client._proc = cast(Any, _DummyProc())
    client._stdout_queue = stdout_queue
    client._ensure_started = cast(Any, lambda: None)

    restarts: list[str] = []

    def _restart() -> None:
        nonlocal stdout_queue
        restarts.append("restart")
        stdout_queue = queue.Queue()
        client._proc = cast(Any, _DummyProc())
        client._stdout_queue = stdout_queue

    def _send(payload: dict[str, object]) -> None:
        if str(payload.get("type")) != "prompt":
            return
        if str(payload.get("message")) == "fresh-after-timeout":
            req_id = str(payload.get("id") or "")
            text = "echo: fresh-after-timeout"
            stdout_queue.put(
                json.dumps(
                    {
                        "type": "response",
                        "id": req_id,
                        "command": "prompt",
                        "success": True,
                    }
                )
            )
            stdout_queue.put(
                json.dumps(
                    {
                        "type": "message_update",
                        "assistantMessageEvent": {"type": "text_delta", "delta": text},
                    }
                )
            )
            stdout_queue.put(
                json.dumps(
                    {
                        "type": "agent_end",
                        "messages": [
                            {
                                "role": "assistant",
                                "content": [{"type": "text", "text": text}],
                            }
                        ],
                    }
                )
            )

    cast(Any, client).restart = _restart
    cast(Any, client)._send = _send

    raised = False
    try:
        client.prompt("sleep-forever", timeout=0.01)
    except TimeoutError:
        raised = True

    assert raised is True
    assert restarts == ["restart"]
    assert (
        client.prompt("fresh-after-timeout", timeout=1.0).text
        == "echo: fresh-after-timeout"
    )


def test_pi_rpc_lm_forward_fake_process_handles_noise(tmp_path: Path) -> None:
    fake = tmp_path / "fake-pi"
    _write_fake_pi_rpc_bin(fake)

    lm = PiRPCLM(binary=str(fake), no_tools=True, strict=True, timeout=2.0)
    resp = lm.forward(prompt="emit-noise")
    text = str((resp.choices[0]).get("text") or "")
    assert "echo: emit-noise" in text


def test_pi_rpc_lm_does_not_require_code_exec_capability(
    tmp_path: Path, monkeypatch
) -> None:
    fake = tmp_path / "fake-pi"
    _write_fake_pi_rpc_bin(fake)
    monkeypatch.setenv("DSPX_POLICY_ALLOWED_CAPS", "network.read")

    lm = PiRPCLM(binary=str(fake), no_tools=True, strict=True, timeout=2.0)
    out = lm.generate(LMRequest(prompt="hello"))

    assert out.outputs[0] == "echo: hello"


def test_pi_rpc_lm_generate_fake_process(tmp_path: Path) -> None:
    fake = tmp_path / "fake-pi"
    _write_fake_pi_rpc_bin(fake)

    lm = PiRPCLM(binary=str(fake), no_tools=True, strict=True, timeout=2.0)
    out = lm.generate(LMRequest(prompt="hello"))
    assert out.outputs[0] == "echo: hello"


def test_provider_registry_create_pi_rpc_from_env(tmp_path: Path, monkeypatch) -> None:
    fake = tmp_path / "fake-pi"
    _write_fake_pi_rpc_bin(fake)

    monkeypatch.setenv("DSPX_PROVIDER", "pi-rpc")
    monkeypatch.setenv("DSPX_PI_BIN", str(fake))
    monkeypatch.setenv("DSPX_PI_STRICT", "1")

    ensure_default_providers()
    lm = cast(Any, create_from_env())
    res = lm.generate(LMRequest(prompt="provider-check"))
    assert res.outputs[0] == "echo: provider-check"


def test_pi_rpc_lm_timeout_strict_raises(tmp_path: Path) -> None:
    fake = tmp_path / "fake-pi"
    _write_fake_pi_rpc_bin(fake)

    lm = PiRPCLM(binary=str(fake), no_tools=True, strict=True, timeout=0.05)

    raised = False
    try:
        lm.forward(prompt="sleep:0.25")
    except TimeoutError:
        raised = True
    assert raised

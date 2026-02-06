from __future__ import annotations

from pathlib import Path

from dspx.dtos import LMRequest
from dspx.pi_rpc_lm import PiRPCLM
from dspx.provider_registry import create_from_env, ensure_default_providers


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


def test_pi_rpc_lm_forward_fake_process_handles_noise(tmp_path: Path) -> None:
    fake = tmp_path / "fake-pi"
    _write_fake_pi_rpc_bin(fake)

    lm = PiRPCLM(binary=str(fake), no_tools=True, strict=True, timeout=2.0)
    resp = lm.forward(prompt="emit-noise")
    text = str((resp.choices[0]).get("text") or "")
    assert "echo: emit-noise" in text


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
    lm = create_from_env()
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

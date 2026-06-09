from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast
import httpx
import pytest

from dspx.provider_registry import ensure_default_providers, create
from dspx.tools.openapi import load_spec
from dspx.tools.registry import register_openapi_operations, get_tool


def test_provider_policy_denies(monkeypatch) -> None:
    ensure_default_providers()
    monkeypatch.setenv("DSPX_POLICY_DISALLOWED_PROVIDERS", "stub")
    with pytest.raises(PermissionError):
        _ = create("stub")


def test_provider_policy_allows(monkeypatch) -> None:
    ensure_default_providers()
    monkeypatch.setenv("DSPX_POLICY_ALLOWED_PROVIDERS", "stub")
    # should not raise
    _ = create("stub")


def _spec(tmp_path: Path) -> str:
    data = {
        "openapi": "3.0.0",
        "servers": [{"url": "http://api.example.com"}],
        "paths": {
            "/echo/{msg}": {
                "get": {
                    "operationId": "echo",
                    "parameters": [{"name": "msg", "in": "path"}],
                }
            }
        },
    }
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


def test_tool_policy_allow_and_deny(tmp_path: Path, monkeypatch) -> None:
    spec_path = _spec(tmp_path)
    spec = load_spec(spec_path)
    names = register_openapi_operations(
        "ex", spec, allowed_hosts={"http://api.example.com": True}
    )
    assert any(n.endswith(".echo") for n in names)
    tool = get_tool("ex.echo")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=request.url.path.split("/echo/")[-1])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    # Allowed case
    monkeypatch.setenv("DSPX_POLICY_ALLOWED_TOOLS", "ex.echo")
    out = tool(params={"msg": "ok"}, client=client)
    assert (out or "").strip() == "ok"
    # Denied case
    monkeypatch.setenv("DSPX_POLICY_ALLOWED_TOOLS", "")
    monkeypatch.setenv("DSPX_POLICY_DISALLOWED_TOOLS", "ex.echo")
    with pytest.raises(PermissionError):
        _ = tool(params={"msg": "hi"}, client=client)


def test_openapi_mutation_denied_without_flag(tmp_path: Path, monkeypatch) -> None:
    # POST should be denied unless allow-network-mutate is enabled
    data = {
        "openapi": "3.0.0",
        "servers": [{"url": "http://api.example.com"}],
        "paths": {"/x": {"post": {"operationId": "create"}}},
    }
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    from dspx.tools.openapi.caller import call_operation
    from dspx.dtos import OpenAPICallRequest

    ops = {
        "create": {
            "operationId": "create",
            "method": "post",
            "path": "/x",
            "server": "http://api.example.com",
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    req = OpenAPICallRequest(operation_id="create", timeout=5)
    # Mutating OpenAPI calls fail closed by default unless explicitly allowed.
    monkeypatch.delenv("DSPX_POLICY_ENFORCE_NETWORK_MUTATE", raising=False)
    monkeypatch.delenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE", raising=False)
    with pytest.raises(PermissionError):
        _ = call_operation(
            req,
            operation=ops["create"],
            allowed_hosts={"http://api.example.com": True},
            client=client,
        )
    # allow and then it should pass
    monkeypatch.setenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE", "1")
    out = call_operation(
        req,
        operation=ops["create"],
        allowed_hosts={"http://api.example.com": True},
        client=client,
    )
    assert out.status_code == 201


def test_codex_generated_cli_wrappers_are_safe_by_default() -> None:
    from dspx.cli.vibegen import wrap_script as gen_wrap_script
    from dspx.cli.viberefine import wrap_script as refine_wrap_script

    for rendered in (
        gen_wrap_script("class Sig: pass"),
        refine_wrap_script("class Sig: pass"),
    ):
        assert "dangerously_bypass=False" in rendered
        assert "auto_mode=True" in rendered
        assert "dangerously_bypass=True" not in rendered


def test_codex_provider_defaults_to_safe_auto_mode(monkeypatch) -> None:
    ensure_default_providers()
    try:
        from dspx.provider_registry import available

        if "codex-exec" not in available():
            pytest.skip("codex provider not registered")
    except Exception:
        pytest.skip("codex provider not available")
    monkeypatch.delenv("CODEX_BYPASS", raising=False)
    monkeypatch.delenv("DSPX_SANDBOX_WORKTREE", raising=False)
    from dspx.provider_registry import create as create_provider

    lm = cast(Any, create_provider("codex-exec"))
    assert getattr(lm, "dangerously_bypass", None) is False
    assert "--dangerously-bypass-approvals-and-sandbox" not in lm._build_command("noop")


def test_codex_provider_uses_sandbox_when_enabled(monkeypatch) -> None:
    ensure_default_providers()
    # Only run if codex provider is present; if not present, skip
    try:
        from dspx.provider_registry import available

        if "codex-exec" not in available():
            pytest.skip("codex provider not registered")
    except Exception:
        pytest.skip("codex provider not available")
    monkeypatch.setenv("DSPX_SANDBOX_WORKTREE", "1")
    from dspx.provider_registry import create as create_provider

    lm = create_provider("codex-exec")
    # CodexExecLM has attribute 'workspace'
    assert getattr(lm, "workspace", None) is not None

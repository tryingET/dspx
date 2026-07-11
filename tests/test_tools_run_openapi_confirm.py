# summary: "Tests OpenAPI tool execution confirmation, temporary mutation-policy approval, and typed parameter coercion."
# read_when:
#   - "Changing tools run OpenAPI confirmation, --yes behavior, mutation environment restoration, or parameter coercion."

from __future__ import annotations

import json
import os

from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.dtos import OpenAPICallResult
from dspx.tools.registry import register_openapi_operations


runner = CliRunner()


def _register_mutating_tool(prefix: str = "t") -> str:
    spec = {
        "openapi": "3.0.0",
        "servers": [{"url": "http://api.example.com"}],
        "paths": {"/send": {"post": {"operationId": "send", "responses": {"200": {}}}}},
    }
    names = register_openapi_operations(
        prefix, spec, allowed_hosts={"http://api.example.com": True}
    )
    assert f"{prefix}.send" in names
    return f"{prefix}.send"


def test_tools_run_requires_confirmation_for_mutation(monkeypatch) -> None:
    monkeypatch.delenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE", raising=False)
    name = _register_mutating_tool()
    res = runner.invoke(app, ["tools", "run", name], input="n\n")
    assert res.exit_code == 2
    assert "confirmation required" in (res.stdout.lower() + res.stderr.lower())


def test_tools_run_skips_confirmation_with_yes() -> None:
    name = _register_mutating_tool(prefix="t2")
    res = runner.invoke(app, ["tools", "run", name, "--yes"], input="\n")
    # It proceeds past the confirmation; network may fail but exit code should not be 2
    assert res.exit_code != 2


def test_tools_run_prompt_confirmation_satisfies_mutation_policy(monkeypatch) -> None:
    from dspx.tools.openapi import caller

    monkeypatch.setenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE", "0")

    def fake_call_operation(*args, **kwargs):
        assert os.environ["DSPX_POLICY_ALLOW_NETWORK_MUTATE"] == "1"
        return OpenAPICallResult(status_code=200, raw_text="ok")

    monkeypatch.setattr(caller, "call_operation", fake_call_operation)
    name = _register_mutating_tool(prefix="t_prompt_env")
    res = runner.invoke(app, ["tools", "run", name], input="y\n")

    assert res.exit_code == 0, res.output
    assert res.stdout.strip().endswith('"ok"')
    assert os.environ["DSPX_POLICY_ALLOW_NETWORK_MUTATE"] == "0"


def test_tools_run_yes_overrides_falsey_mutation_env_then_restores(monkeypatch) -> None:
    from dspx.tools.openapi import caller

    monkeypatch.setenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE", "0")

    def fake_call_operation(*args, **kwargs):
        assert os.environ["DSPX_POLICY_ALLOW_NETWORK_MUTATE"] == "1"
        return OpenAPICallResult(status_code=200, raw_text="ok")

    monkeypatch.setattr(caller, "call_operation", fake_call_operation)
    name = _register_mutating_tool(prefix="t_yes_env")
    res = runner.invoke(app, ["tools", "run", name, "--yes"], input="\n")

    assert res.exit_code == 0, res.output
    assert json.loads(res.stdout) == "ok"
    assert os.environ["DSPX_POLICY_ALLOW_NETWORK_MUTATE"] == "0"


def test_tools_run_coerces_openapi_typed_params(monkeypatch) -> None:
    spec = {
        "openapi": "3.0.0",
        "servers": [{"url": "http://api.example.com"}],
        "paths": {
            "/search": {
                "get": {
                    "operationId": "searchItems",
                    "parameters": [
                        {
                            "in": "query",
                            "name": "ids",
                            "required": True,
                            "schema": {
                                "type": "array",
                                "items": {"type": "integer"},
                            },
                        }
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    name = register_openapi_operations(
        "t3", spec, allowed_hosts={"http://api.example.com": True}
    )[0]

    captured: dict[str, object] = {}

    from dspx.tools import registry as registry_mod

    original = registry_mod.get_tool(name)

    def _fake_tool(*, params=None, body=None):
        captured["params"] = dict(params or {})
        return "ok"

    for key, value in getattr(original, "__dict__", {}).items():
        if str(key).startswith("_dspx_"):
            setattr(_fake_tool, key, value)

    monkeypatch.setitem(registry_mod._TOOLS, name, _fake_tool)

    res = runner.invoke(app, ["tools", "run", name, "--params", "ids=1,2"])

    assert res.exit_code == 0
    assert captured["params"] == {"ids": [1, 2]}
    assert res.stdout.strip() == json.dumps("ok")

from __future__ import annotations

from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.tools.registry import register_openapi_operations


runner = CliRunner()


def _register_mutating_tool(prefix: str = "t") -> str:
    spec = {
        "openapi": "3.0.0",
        "servers": [{"url": "http://api.example.com"}],
        "paths": {"/send": {"post": {"operationId": "send", "responses": {"200": {}}}}},
    }
    names = register_openapi_operations(
        prefix, spec, allowed_hosts={"api.example.com": True}
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

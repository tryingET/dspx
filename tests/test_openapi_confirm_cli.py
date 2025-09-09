from __future__ import annotations

import json
from pathlib import Path
from typer.testing import CliRunner

from dspx.cli.dspx import app


runner = CliRunner()


def _make_post_spec(tmp_path: Path) -> str:
    spec = {
        "openapi": "3.0.0",
        "servers": [{"url": "http://api.example.com"}],
        "paths": {"/send": {"post": {"operationId": "send", "responses": {"200": {}}}}},
    }
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(spec), encoding="utf-8")
    return str(p)


def test_openapi_call_requires_confirmation_for_mutation(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE", raising=False)
    spec = _make_post_spec(tmp_path)
    # Invoke without --yes; respond "n" to prompt; expect exit code 2 and helpful message
    res = runner.invoke(
        app,
        [
            "tools",
            "openapi",
            "call",
            "--spec",
            spec,
            "--op",
            "send",
            "--allow-host",
            "api.example.com",
        ],
        input="n\n",
    )
    assert res.exit_code == 2
    assert "confirmation required" in (res.stdout.lower() + res.stderr.lower())


def test_openapi_call_skips_confirmation_with_yes(tmp_path: Path, monkeypatch) -> None:
    # With --yes, the confirmation is skipped; it will attempt network and likely fail.
    # We only verify it does not prompt and proceeds past the guard (exit code may be non-zero).
    spec = _make_post_spec(tmp_path)
    res = runner.invoke(
        app,
        [
            "tools",
            "openapi",
            "call",
            "--spec",
            spec,
            "--op",
            "send",
            "--allow-host",
            "api.example.com",
            "--yes",
        ],
        input="\n",
    )
    # Either network attempt fails (non-zero) or returns; key is not exit code 2 due to confirmation
    assert res.exit_code != 2

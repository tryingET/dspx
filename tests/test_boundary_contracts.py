# summary: "Tests security boundaries for cache paths, OpenAPI inputs, rate limits, and provider diagnostics."
# read_when:
#   - "You are changing filesystem confinement, OpenAPI handling, rate-limit buckets, or provider error sanitization."

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import dspx.provider_runtime as provider_runtime
from dspx.cli.dspx import app
from dspx.server.security import Rate, RateLimitConfig, RateLimitMiddleware
from dspx.tools.openapi.loader import extract_operations


runner = CliRunner()


def test_cache_cli_rejects_traversal_for_read_and_delete(
    tmp_path: Path, monkeypatch
) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    outside = tmp_path / "secret.json"
    outside.write_text(json.dumps({"secret": 1}), encoding="utf-8")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(cache))

    for command in (
        ["cache", "list", "--kind", ".."],
        ["cache", "show", "--kind", "..", "--key", "secret"],
        ["cache", "clear", "--kind", "..", "--key", "secret"],
        ["cache", "clear", "--kind", ".."],
        ["cache", "prune", "--kind", "..", "--older-than-days", "0"],
    ):
        result = runner.invoke(app, command)
        assert result.exit_code == 2, command
        assert "invalid cache kind" in result.output

    assert outside.exists()
    assert json.loads(outside.read_text(encoding="utf-8")) == {"secret": 1}


def test_openapi_prefix_rejects_path_traversal(tmp_path: Path) -> None:
    outdir = tmp_path / "mappings"
    spec = tmp_path / "spec.json"
    spec.write_text("{}", encoding="utf-8")

    load_result = runner.invoke(
        app,
        [
            "tools",
            "openapi",
            "load",
            "--prefix",
            "../escape",
            "--spec",
            str(spec),
            "--outdir",
            str(outdir),
        ],
    )
    env_result = runner.invoke(
        app, ["tools", "openapi", "env", "--prefix", "../escape"]
    )

    assert load_result.exit_code == 2
    assert env_result.exit_code == 2
    assert "invalid OpenAPI prefix" in load_result.output
    assert not (tmp_path / "escape.json").exists()


def test_openapi_env_shell_quotes_mapping_values(tmp_path: Path) -> None:
    mapping = tmp_path / "x.json"
    spec = "'; touch /tmp/dspx-openapi-pwn; #"
    host = "api.example.com'$(touch /tmp/dspx-openapi-host-pwn)'"
    mapping.write_text(
        json.dumps({"spec": spec, "allow_host": host}),
        encoding="utf-8",
    )

    result = runner.invoke(
        app, ["tools", "openapi", "env", "--prefix", "x", "--map", str(mapping)]
    )

    assert result.exit_code == 0
    lines = result.stdout.strip().splitlines()
    assert len(lines) == 2
    parsed = [shlex.split(line) for line in lines]
    assert parsed == [
        ["export", f"DSPX_OPENAPI_SPEC_X={spec}"],
        ["export", f"DSPX_OPENAPI_HOST_X={host}"],
    ]
    assert "=''; touch" not in result.stdout


def test_openapi_extract_operations_prefers_operation_server() -> None:
    spec = {
        "openapi": "3.0.0",
        "servers": [{"url": "https://root.example"}],
        "paths": {
            "/items": {
                "servers": [{"url": "https://path.example"}],
                "get": {
                    "operationId": "listItems",
                    "servers": [{"url": "https://operation.example"}],
                    "responses": {"200": {"description": "ok"}},
                },
                "post": {
                    "operationId": "createItem",
                    "responses": {"200": {"description": "ok"}},
                },
            }
        },
    }

    ops = extract_operations(spec)

    assert ops["listItems"]["server"] == "https://operation.example"
    assert ops["createItem"]["server"] == "https://path.example"


def test_rate_limit_generic_path_bucket_is_shared_across_methods() -> None:
    rate_app = FastAPI()
    rate_app.add_middleware(
        cast(Any, RateLimitMiddleware),
        config=RateLimitConfig(
            enabled=True,
            default=[],
            per_path={"/module": [Rate(1, 60.0)]},
            identity="ip",
            trusted_proxies=[],
            global_default=[],
            global_per_path={},
        ),
    )

    @rate_app.get("/module")
    def _get_module() -> dict[str, str]:
        return {"status": "ok"}

    @rate_app.post("/module")
    def _post_module() -> dict[str, str]:
        return {"status": "ok"}

    client = TestClient(rate_app)

    assert client.get("/module").status_code == 200
    assert client.post("/module").status_code == 429


def test_provider_diagnostics_sanitize_sensitive_payloads() -> None:
    payload = provider_runtime.sanitize_payload(
        {"error": "provider failed token=supersecret-token", "api_key": "secret"}
    )

    dumped = json.dumps(payload)
    assert "supersecret-token" not in dumped
    assert "secret" not in dumped
    assert "[REDACTED]" in dumped

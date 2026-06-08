from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.services import program_service
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_runtime_episode import _generated_program_module
from dspx.services.program_surfaces import render_direct_run_code

runner = CliRunner()


def test_generated_program_module_serializes_concurrent_global_imports(
    tmp_path: Path,
) -> None:
    for name, value in (("a", "A"), ("b", "B")):
        candidate = tmp_path / name
        candidate.mkdir()
        (candidate / "program.py").write_text(
            "def io_spec():\n"
            "    for _ in range(10000):\n"
            "        pass\n"
            f"    return {{'outputs': ['{value}']}}\n",
            encoding="utf-8",
        )

    def load(candidate: Path) -> str:
        with _generated_program_module(candidate) as module:
            return str(module.io_spec()["outputs"][0])

    for _ in range(10):
        with ThreadPoolExecutor(max_workers=2) as executor:
            assert list(executor.map(load, [tmp_path / "a", tmp_path / "b"])) == [
                "A",
                "B",
            ]


def test_generated_direct_run_accepts_plain_string_outputs(tmp_path: Path) -> None:
    program_dir = tmp_path / "program"
    program_dir.mkdir()
    (program_dir / "direct_run.py").write_text(
        render_direct_run_code(object()), encoding="utf-8"
    )
    (program_dir / "program.py").write_text(
        """
def io_spec(): return {"inputs": ["q"], "outputs": ["answer"]}
def configure_observability(**kw): return False
def end_observability_run(started, status="FINISHED"): pass
class P:
    def __call__(self, **kw): return "hello"
def build_program(): return P()
""",
        encoding="utf-8",
    )
    inputs = program_dir / "inputs.json"
    inputs.write_text('{"q": "x"}\n', encoding="utf-8")
    outdir = tmp_path / "out"
    env = {
        **os.environ,
        "DSPX_PROVIDER": "stub",
        "MLFLOW_ENABLE": "0",
    }

    result = subprocess.run(
        [
            sys.executable,
            str(program_dir / "direct_run.py"),
            "--inputs",
            str(inputs),
            "--outdir",
            str(outdir),
            "--json",
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads((outdir / "answer").read_text(encoding="utf-8")) == "hello"


@pytest.mark.parametrize(
    ("flag", "value", "message"),
    [
        ("--parallel", "0", "--parallel must be >= 1"),
        ("--timeout-seconds", "0", "--timeout-seconds must be > 0"),
        ("--retries", "-1", "--retries must be >= 0"),
    ],
)
def test_generated_direct_batch_rejects_invalid_limits(
    tmp_path: Path, flag: str, value: str, message: str
) -> None:
    program_dir = tmp_path / "program"
    program_dir.mkdir()
    (program_dir / "direct_run.py").write_text(
        render_direct_run_code(object()), encoding="utf-8"
    )
    inputs_root = tmp_path / "inputs"
    inputs_root.mkdir()
    (inputs_root / "case.json").write_text('{"q": "x"}\n', encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(program_dir / "direct_run.py"),
            "--inputs-root",
            str(inputs_root),
            "--out-root",
            str(tmp_path / "out"),
            flag,
            value,
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert message in result.stderr


def test_generated_direct_batch_records_timeout_without_crashing(
    tmp_path: Path,
) -> None:
    program_dir = tmp_path / "program"
    program_dir.mkdir()
    (program_dir / "direct_run.py").write_text(
        render_direct_run_code(object()), encoding="utf-8"
    )
    (program_dir / "program.py").write_text(
        """
import time

def io_spec(): return {"inputs": ["q"], "outputs": ["answer"]}
def configure_observability(**kw): return False
def end_observability_run(started, status="FINISHED"): pass
class P:
    def __call__(self, **kw):
        time.sleep(3)
        return {"answer": "late"}
def build_program(): return P()
""",
        encoding="utf-8",
    )
    inputs_root = tmp_path / "inputs"
    inputs_root.mkdir()
    (inputs_root / "case.json").write_text('{"q": "x"}\n', encoding="utf-8")
    out_root = tmp_path / "out"

    result = subprocess.run(
        [
            sys.executable,
            str(program_dir / "direct_run.py"),
            "--inputs-root",
            str(inputs_root),
            "--out-root",
            str(out_root),
            "--timeout-seconds",
            "1",
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    summary = json.loads((out_root / "direct_batch_receipt.json").read_text())
    assert summary["status"] == "failed"
    assert summary["failed"] == 1
    attempt = summary["results"][0]["attempts"][0]
    assert attempt["timed_out"] is True
    assert attempt["error_type"] == "TimeoutExpired"


def test_generated_direct_batch_records_internal_worker_exception(
    tmp_path: Path,
) -> None:
    namespace: dict[str, Any] = {"__file__": str(tmp_path / "direct_run.py")}
    exec(render_direct_run_code(object()), namespace, namespace)

    def boom(*args: object, **kwargs: object) -> dict[str, object]:
        raise ValueError("bad child receipt")

    namespace["_run_child"] = boom
    inputs_root = tmp_path / "inputs"
    inputs_root.mkdir()
    (inputs_root / "case.json").write_text('{"q": "x"}\n', encoding="utf-8")
    out_root = tmp_path / "out"

    summary = namespace["_batch_run"](inputs_root, out_root, 1, 1, 0, None)

    assert summary["status"] == "failed"
    assert summary["failed"] == 1
    result = summary["results"][0]
    assert result["target"] == "case"
    assert result["error_type"] == "ValueError"
    assert result["error"] == "bad child receipt"
    assert (
        json.loads((out_root / "direct_batch_receipt.json").read_text())["failed"] == 1
    )


def test_program_gen_failure_cleans_partial_outdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    root = tmp_path / "program"
    original = program_service._run_eval_smoke
    monkeypatch.setattr(
        program_service,
        "_run_eval_smoke",
        lambda _root: (_ for _ in ()).throw(RuntimeError("simulated smoke failure")),
    )

    with pytest.raises(RuntimeError, match="simulated smoke failure"):
        program_service.materialize_program_from_intent(
            ProgramIntent(name="X", objective="x", inputs=["q"], outputs=["a"]),
            outdir=root,
        )

    assert not root.exists()

    monkeypatch.setattr(program_service, "_run_eval_smoke", original)
    artifact = program_service.materialize_program_from_intent(
        ProgramIntent(name="X", objective="x", inputs=["q"], outputs=["a"]),
        outdir=root,
    )
    assert Path(artifact.root_path, "manifest.json").exists()


def test_program_gen_compile_failure_removes_new_empty_outdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "program"
    monkeypatch.setattr(
        program_service, "render_program_code", lambda _intent: "def broken(:\n"
    )

    with pytest.raises(SyntaxError):
        program_service.materialize_program_from_intent(
            ProgramIntent(name="X", objective="x", inputs=["q"], outputs=["a"]),
            outdir=root,
        )

    assert not root.exists()


def test_program_gen_rejects_existing_empty_outdir_without_partial_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "program"
    root.mkdir()

    def should_not_run(_root: Path) -> dict[str, object]:
        raise AssertionError("materialization should not start for existing outdir")

    monkeypatch.setattr(program_service, "_run_eval_smoke", should_not_run)

    with pytest.raises(ValueError, match="program-gen outdir already exists"):
        program_service.materialize_program_from_intent(
            ProgramIntent(name="X", objective="x", inputs=["q"], outputs=["a"]),
            outdir=root,
        )

    assert root.exists()
    assert list(root.iterdir()) == []


def test_cli_boundary_failures_are_concise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.delenv("DSPX_CONFIG", raising=False)

    provider_result = runner.invoke(
        app, ["providers", "resolve", "--provider", "no-such", "--json"]
    )
    assert provider_result.exit_code == 2
    assert "unknown provider: no-such" in provider_result.output
    assert "Traceback" not in provider_result.output

    spec = tmp_path / "spec.json"
    spec.write_text(
        json.dumps(
            {
                "openapi": "3.0.0",
                "info": {"title": "t", "version": "1"},
                "paths": {
                    "/x": {
                        "get": {
                            "operationId": "getX",
                            "responses": {"200": {"description": "ok"}},
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    missing_op = runner.invoke(
        app,
        ["tools", "openapi", "describe", "--spec", str(spec), "--op", "missing"],
    )
    assert missing_op.exit_code == 2
    assert "unknown OpenAPI operationId: missing" in missing_op.output
    assert "getX" in missing_op.output
    assert "Traceback" not in missing_op.output

    missing_spec = runner.invoke(
        app,
        ["tools", "openapi", "describe", "--spec", "/no/such", "--op", "nope"],
    )
    assert missing_spec.exit_code == 2
    assert "failed to load OpenAPI spec /no/such" in missing_spec.output
    assert "Traceback" not in missing_spec.output

    bad_config_dir = tmp_path / "bad-config"
    bad_config_dir.mkdir()
    (bad_config_dir / "config.toml").write_text("[provider\n", encoding="utf-8")
    with runner.isolated_filesystem(temp_dir=bad_config_dir):
        bad_config = runner.invoke(app, ["providers", "list", "--json"])
    assert bad_config.exit_code == 2
    assert "Failed to parse DSPx config TOML" in bad_config.output
    assert "Traceback" not in bad_config.output

    capabilities_result = runner.invoke(
        app, ["providers", "capabilities", "--provider", "no-such", "--json"]
    )
    assert capabilities_result.exit_code == 2
    assert "unknown provider: no-such" in capabilities_result.output
    assert "Traceback" not in capabilities_result.output

    missing_key = runner.invoke(
        app,
        [
            "--openrouter-api-key-file",
            str(tmp_path / "missing.key"),
            "providers",
            "health",
            "--provider",
            "openrouter",
            "--json",
        ],
    )
    assert missing_key.exit_code == 2
    assert "failed to read OpenRouter API key file" in missing_key.output
    assert "Traceback" not in missing_key.output

    invalid_key = tmp_path / "invalid.key"
    invalid_key.write_bytes(b"\xff\xfe")
    invalid_key_result = runner.invoke(
        app,
        [
            "--openrouter-api-key-file",
            str(invalid_key),
            "providers",
            "health",
            "--provider",
            "openrouter",
            "--json",
        ],
    )
    assert invalid_key_result.exit_code == 2
    assert "failed to read OpenRouter API key file" in invalid_key_result.output
    assert "Traceback" not in invalid_key_result.output


def test_cli_boundary_errors_redact_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    secret_error = (
        "request failed token=secret-token Authorization: Bearer bearer-secret "
        "https://user:pass@example.test/spec.json?api_key=url-secret&ok=1"
    )

    import dspx.provider_runtime as provider_runtime
    import dspx.tools.openapi as openapi_tools

    def raise_secret_provider(_name: str) -> dict[str, object]:
        raise RuntimeError(secret_error)

    def raise_secret_spec(
        _spec: str, *, allowed_hosts: object = None
    ) -> dict[str, object]:
        raise RuntimeError(secret_error)

    monkeypatch.setattr(provider_runtime, "describe_provider", raise_secret_provider)
    monkeypatch.setattr(openapi_tools, "load_spec", raise_secret_spec)

    provider_result = runner.invoke(
        app, ["providers", "resolve", "--provider", "secret-provider", "--json"]
    )
    assert provider_result.exit_code == 2
    assert "[REDACTED]" in provider_result.output
    assert "secret-token" not in provider_result.output
    assert "bearer-secret" not in provider_result.output
    assert "url-secret" not in provider_result.output
    assert "user:pass" not in provider_result.output
    assert "Traceback" not in provider_result.output

    spec_result = runner.invoke(
        app,
        [
            "tools",
            "openapi",
            "describe",
            "--spec",
            "https://user:pass@example.test/spec.json?api_key=url-secret&ok=1",
            "--op",
            "missing",
        ],
    )
    assert spec_result.exit_code == 2
    assert "[REDACTED]" in spec_result.output
    assert "secret-token" not in spec_result.output
    assert "bearer-secret" not in spec_result.output
    assert "url-secret" not in spec_result.output
    assert "user:pass" not in spec_result.output
    assert "Traceback" not in spec_result.output

from __future__ import annotations

from pathlib import Path
import json
import os

from typer.testing import CliRunner

import dspx.cli.dspx as dspx_cli


app = dspx_cli.app
runner = CliRunner()


def test_cli_signature_gen_prints_code(monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    result = runner.invoke(app, ["signature", "gen", "Extract names from text"])
    assert result.exit_code == 0
    out = result.stdout
    assert "class" in out and "dspy.Signature" in out


def test_cli_module_gen_prints_module(monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    result = runner.invoke(
        app,
        [
            "module-gen",
            "-n",
            "Summarizer",
            "-d",
            "Summarizes text",
            "-i",
            "text",
            "-o",
            "summary",
            "--template-version",
            "simple-v1",
        ],
    )
    assert result.exit_code == 0
    assert "class Summarizer(dspy.Module):" in result.stdout


def test_cli_codegen_prints_python(monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    result = runner.invoke(
        app,
        [
            "codegen",
            'A CLI that prints "smoke ok"',
            "-l",
            "python",
            "--template-version",
            "simple-v1",
        ],
    )
    assert result.exit_code == 0
    assert 'if __name__ == "__main__"' in result.stdout


def test_cli_mermaid_gen_creates_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    mermaid = "\n".join(
        [
            "graph TD",
            "  A[Start] --> B{Done}",
        ]
    )
    f = tmp_path / "flow.mmd"
    f.write_text(mermaid, encoding="utf-8")
    # Run in tmp cwd to avoid polluting repo
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        result = runner.invoke(
            app,
            [
                "mermaid",
                "gen",
                "-f",
                str(f),
                "-n",
                "t1",
            ],
        )
        assert result.exit_code == 0
        outdir = tmp_path / "generated" / "workflows" / "t1"
        assert (outdir / "program_predict.py").exists()
        assert (outdir / "workflow.mmd").exists()
    finally:
        os.chdir(cwd)


def test_cli_readonly_providers_list_skips_mlflow_bootstrap(monkeypatch) -> None:
    def _boom() -> bool:
        raise AssertionError("read-only providers list must not bootstrap MLflow")

    monkeypatch.setattr(dspx_cli, "enable_mlflow_from_env", _boom)
    result = runner.invoke(app, ["providers", "list"])
    assert result.exit_code == 0
    assert "stub" in result.stdout


def test_cli_readonly_openapi_ops_skips_mlflow_bootstrap(
    tmp_path: Path, monkeypatch
) -> None:
    def _boom() -> bool:
        raise AssertionError("read-only openapi ops must not bootstrap MLflow")

    monkeypatch.setattr(dspx_cli, "enable_mlflow_from_env", _boom)
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "demo", "version": "1.0.0"},
        "paths": {
            "/ping": {
                "get": {
                    "operationId": "ping",
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")

    result = runner.invoke(app, ["tools", "openapi", "ops", str(spec_path)])
    assert result.exit_code == 0
    assert "ping" in result.stdout


def test_cli_signature_gen_still_bootstraps_mlflow(monkeypatch) -> None:
    calls = {"n": 0}

    def _count() -> bool:
        calls["n"] += 1
        return False

    monkeypatch.setattr(dspx_cli, "enable_mlflow_from_env", _count)
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    result = runner.invoke(app, ["signature", "gen", "Extract names from text"])
    assert result.exit_code == 0
    assert calls["n"] >= 1

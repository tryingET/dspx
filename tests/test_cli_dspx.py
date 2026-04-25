from __future__ import annotations

from pathlib import Path
import json
import os

from typer.testing import CliRunner

import dspx.cli.dspx as dspx_cli
import dspx.cli.utils as dspx_utils


app = dspx_cli.app
runner = CliRunner()


def test_cli_signature_gen_prints_code(monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    result = runner.invoke(app, ["signature", "gen", "Extract names from text"])
    assert result.exit_code == 0
    out = result.stdout
    assert "class" in out and "dspy.Signature" in out


def test_cli_signature_gen_accepts_explicit_io_fields(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    out = tmp_path / "ticket_sig.py"
    summary = tmp_path / "ticket_sig.summary.json"

    result = runner.invoke(
        app,
        [
            "signature",
            "gen",
            "Classify support ticket urgency",
            "--template-version",
            "simple-v1",
            "--class-name",
            "TicketSig",
            "--input",
            "ticket_text",
            "--output",
            "urgency",
            "--outfile",
            str(out),
            "--summary-json-out",
            str(summary),
        ],
    )

    assert result.exit_code == 0, result.output
    code = out.read_text(encoding="utf-8")
    assert "class TicketSig(dspy.Signature):" in code
    assert "ticket_text: str = dspy.InputField" in code
    assert "urgency: str = dspy.OutputField" in code

    summary_payload = json.loads(summary.read_text(encoding="utf-8"))
    assert summary_payload["inputs"] == ["ticket_text"]
    assert summary_payload["outputs"] == ["urgency"]
    assert summary_payload["requested_inputs"] == ["ticket_text"]
    assert summary_payload["requested_outputs"] == ["urgency"]

    receipt = json.loads((tmp_path / "ticket_sig.py.meta.json").read_text())
    assert receipt["replay_inputs"]["options"] == {
        "class_name": "TicketSig",
        "inputs": ["ticket_text"],
        "outputs": ["urgency"],
    }


def test_cli_signature_gen_rejects_invalid_identifiers(monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    result = runner.invoke(
        app,
        ["signature", "gen", "Classify tickets", "--input", "first-name"],
    )
    assert result.exit_code == 2
    assert "valid Python identifiers" in (result.stdout + result.stderr)


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


def test_cli_module_gen_rejects_invalid_field_names(monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    result = runner.invoke(
        app,
        [
            "module-gen",
            "-n",
            "Summarizer",
            "-i",
            "first-name",
            "-o",
            "summary",
            "--template-version",
            "simple-v1",
        ],
    )
    assert result.exit_code == 2
    assert "valid python identifiers" in (result.stdout.lower() + result.stderr.lower())


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

    monkeypatch.setattr(dspx_utils, "enable_mlflow_from_env", _boom)
    result = runner.invoke(app, ["providers", "list"])
    assert result.exit_code == 0
    assert "stub" in result.stdout


def test_cli_readonly_openapi_ops_skips_mlflow_bootstrap(
    tmp_path: Path, monkeypatch
) -> None:
    def _boom() -> bool:
        raise AssertionError("read-only openapi ops must not bootstrap MLflow")

    monkeypatch.setattr(dspx_utils, "enable_mlflow_from_env", _boom)
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

    monkeypatch.setattr(dspx_utils, "enable_mlflow_from_env", _count)
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    result = runner.invoke(app, ["signature", "gen", "Extract names from text"])
    assert result.exit_code == 0
    assert calls["n"] >= 1


def test_cli_signature_quality_summary_json_and_gate(tmp_path: Path) -> None:
    log = tmp_path / "quality.jsonl"
    log.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "provider": "stub",
                        "run_kind": "signature-gen",
                        "attempts_used": 1,
                        "fallback_used": False,
                        "validation_pass_count": 1,
                        "validation_total": 1,
                        "smoke_pass_count": 1,
                        "smoke_total": 1,
                    }
                ),
                json.dumps(
                    {
                        "provider": "stub",
                        "run_kind": "signature-gen",
                        "attempts_used": 2,
                        "fallback_used": True,
                        "validation_pass_count": 1,
                        "validation_total": 2,
                        "smoke_pass_count": 1,
                        "smoke_total": 2,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    ok = runner.invoke(
        app,
        [
            "signature",
            "quality-summary",
            "--log-path",
            str(log),
            "--json",
            "--max-fallback-rate",
            "0.6",
        ],
    )
    assert ok.exit_code == 0
    payload = json.loads(ok.stdout)
    assert payload["summary"]["runs_total"] == 2
    assert abs(float(payload["summary"]["fallback_rate"]) - 0.5) < 1e-9

    fail = runner.invoke(
        app,
        [
            "signature",
            "quality-summary",
            "--log-path",
            str(log),
            "--fail-on-gate",
            "--max-fallback-rate",
            "0.1",
        ],
    )
    assert fail.exit_code == 2


def test_cli_signature_run_summary_outputs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")

    sig_summary = tmp_path / "sig.summary.json"
    sig_result = runner.invoke(
        app,
        [
            "signature",
            "gen",
            "Extract names from text",
            "--summary-json-out",
            str(sig_summary),
        ],
    )
    assert sig_result.exit_code == 0
    sig_payload = json.loads(sig_summary.read_text(encoding="utf-8"))
    assert "attempts_used" in sig_payload
    assert "validation_pass_rate" in sig_payload

    refine_summary = tmp_path / "refine.summary.json"
    refine_result = runner.invoke(
        app,
        [
            "signature",
            "refine",
            "Extract names from text",
            "--summary-json-out",
            str(refine_summary),
        ],
    )
    assert refine_result.exit_code == 0
    refine_payload = json.loads(refine_summary.read_text(encoding="utf-8"))
    assert refine_payload["run_kind"] == "signature-refine"
    assert "attempts_requested" in refine_payload


def test_cli_signature_gen_template_config_fast_fails_without_adapter(
    tmp_path: Path, monkeypatch
) -> None:
    """Test that --template-config fails fast when adapter not installed."""
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")

    # Force adapter to be unavailable
    monkeypatch.setattr(dspx_cli, "_TEMPLATE_ADAPTER_AVAILABLE", False)

    config_file = tmp_path / "template.yaml"
    config_file.write_text(
        "messages:\n  - role: user\n    content: test\n", encoding="utf-8"
    )

    result = runner.invoke(
        app,
        [
            "signature",
            "gen",
            "Extract names",
            "--template-config",
            str(config_file),
        ],
    )

    # Should exit with code 2
    assert result.exit_code == 2
    # Should have helpful error message
    assert (
        "dspy-template-adapter" in result.stderr
        or "dspy-template-adapter" in result.stdout
    )
    assert "pip install" in result.stderr or "pip install" in result.stdout


def test_cli_module_gen_template_config_fast_fails_without_adapter(
    tmp_path: Path, monkeypatch
) -> None:
    """Test that --template-config fails fast for module-gen when adapter not installed."""
    monkeypatch.setenv("MLFLOW_ENABLE", "0")

    # Force adapter to be unavailable
    monkeypatch.setattr(dspx_cli, "_TEMPLATE_ADAPTER_AVAILABLE", False)

    config_file = tmp_path / "template.yaml"
    config_file.write_text(
        "messages:\n  - role: user\n    content: test\n", encoding="utf-8"
    )

    result = runner.invoke(
        app,
        [
            "module-gen",
            "-n",
            "TestModule",
            "-i",
            "input",
            "-o",
            "output",
            "--template-config",
            str(config_file),
        ],
    )

    assert result.exit_code == 2
    assert (
        "dspy-template-adapter" in result.stderr
        or "dspy-template-adapter" in result.stdout
    )


def test_cli_codegen_template_config_fast_fails_without_adapter(
    tmp_path: Path, monkeypatch
) -> None:
    """Test that --template-config fails fast for codegen when adapter not installed."""
    monkeypatch.setenv("MLFLOW_ENABLE", "0")

    # Force adapter to be unavailable
    monkeypatch.setattr(dspx_cli, "_TEMPLATE_ADAPTER_AVAILABLE", False)

    config_file = tmp_path / "template.yaml"
    config_file.write_text(
        "messages:\n  - role: user\n    content: test\n", encoding="utf-8"
    )

    result = runner.invoke(
        app,
        [
            "codegen",
            "Generate a test function",
            "--template-config",
            str(config_file),
        ],
    )

    assert result.exit_code == 2
    assert (
        "dspy-template-adapter" in result.stderr
        or "dspy-template-adapter" in result.stdout
    )


def test_cli_signature_gen_template_config_fails_on_missing_file(
    monkeypatch,
) -> None:
    """Test that --template-config fails when file doesn't exist (before adapter check)."""
    monkeypatch.setenv("MLFLOW_ENABLE", "0")

    result = runner.invoke(
        app,
        [
            "signature",
            "gen",
            "test",
            "--template-config",
            "/nonexistent/path/template.yaml",
        ],
    )

    # Should exit with code 2
    assert result.exit_code == 2
    # Should report file not found (not adapter missing)
    assert "not found" in result.stderr.lower() or "not found" in result.stdout.lower()


def test_cli_module_gen_template_config_fails_on_missing_file(
    monkeypatch,
) -> None:
    """Test that --template-config fails for module-gen when file doesn't exist."""
    monkeypatch.setenv("MLFLOW_ENABLE", "0")

    result = runner.invoke(
        app,
        [
            "module-gen",
            "-n",
            "Test",
            "-i",
            "x",
            "-o",
            "y",
            "--template-config",
            "/nonexistent.yaml",
        ],
    )

    assert result.exit_code == 2
    assert "not found" in result.stderr.lower() or "not found" in result.stdout.lower()


def test_cli_codegen_template_config_fails_on_missing_file(monkeypatch) -> None:
    """Test that --template-config fails for codegen when file doesn't exist."""
    monkeypatch.setenv("MLFLOW_ENABLE", "0")

    result = runner.invoke(
        app,
        [
            "codegen",
            "test",
            "--template-config",
            "/nonexistent.yaml",
        ],
    )

    assert result.exit_code == 2
    assert "not found" in result.stderr.lower() or "not found" in result.stdout.lower()


# --- Tests for --dry-run flag ---


def test_cli_signature_gen_dry_run_requires_template_config(monkeypatch) -> None:
    """Test that --dry-run fails when --template-config is not provided."""
    monkeypatch.setenv("MLFLOW_ENABLE", "0")

    result = runner.invoke(
        app,
        [
            "signature",
            "gen",
            "test prompt",
            "--dry-run",
        ],
    )

    assert result.exit_code == 2
    assert "requires --template-config" in result.stderr.lower()


def test_cli_signature_gen_dry_run_validates_config(
    monkeypatch, tmp_path: Path
) -> None:
    """Test that --dry-run validates template config."""
    monkeypatch.setenv("MLFLOW_ENABLE", "0")

    # Create invalid config
    config_file = tmp_path / "invalid.yaml"
    config_file.write_text(
        """
parse_mode: invalid_mode
""",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "signature",
            "gen",
            "test prompt",
            "--template-config",
            str(config_file),
            "--dry-run",
        ],
    )

    # Should fail validation
    assert result.exit_code == 2
    assert "validation failed" in result.stderr.lower()


def test_cli_signature_gen_dry_run_with_valid_config(
    monkeypatch, tmp_path: Path
) -> None:
    """Test that --dry-run works with valid config (no adapter installed)."""
    monkeypatch.setenv("MLFLOW_ENABLE", "0")

    # Create valid config
    config_file = tmp_path / "valid.yaml"
    config_file.write_text(
        """
messages:
  - role: system
    content: "{instruction}"
  - role: user
    content: "{inputs(style='yaml')}"
parse_mode: json
""",
        encoding="utf-8",
    )

    # Mock adapter as unavailable to test the fallback path
    with _monkeypatch_adapter_available(False):
        result = runner.invoke(
            app,
            [
                "signature",
                "gen",
                "test prompt",
                "--template-config",
                str(config_file),
                "--dry-run",
            ],
        )

        # Should succeed even without adapter (shows summary only)
        assert result.exit_code == 0
        assert "validation passed" in result.stderr.lower()


def _monkeypatch_adapter_available(available: bool):
    """Context manager to mock adapter availability."""
    import contextlib

    @contextlib.contextmanager
    def ctx():
        original = dspx_cli._TEMPLATE_ADAPTER_AVAILABLE
        dspx_cli._TEMPLATE_ADAPTER_AVAILABLE = available
        try:
            yield
        finally:
            dspx_cli._TEMPLATE_ADAPTER_AVAILABLE = original

    return ctx()

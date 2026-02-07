from __future__ import annotations

import os
from pathlib import Path

from typer.testing import CliRunner

from dspx_forge.cli import app


runner = CliRunner()


def _run_in_tmp(tmp_path: Path, fn):
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        return fn()
    finally:
        os.chdir(cwd)


def test_forge_cli_apply_requires_allow_network_mutate(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.delenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE", raising=False)
    monkeypatch.delenv("DSPX_GITLAB_BASE_URL", raising=False)
    monkeypatch.delenv("DSPX_GITLAB_TOKEN", raising=False)
    monkeypatch.delenv("DSPX_GITLAB_PROJECT_MAP_JSON", raising=False)
    monkeypatch.delenv("DSPX_GITLAB_PROJECT_MAP_FILE", raising=False)

    def _run():
        res = runner.invoke(
            app,
            [
                "intake",
                "Build thing\nDo it safely",
                "--non-interactive",
                "--out-root",
                "generated/forge",
            ],
        )
        assert res.exit_code == 0
        workorder_yaml = res.stdout.strip()
        res2 = runner.invoke(
            app,
            ["issues", "apply", workorder_yaml, "--apply"],
        )
        assert res2.exit_code == 2
        msg = (res2.stdout + res2.stderr).lower()
        assert "allow-network-mutate" in msg

    _run_in_tmp(tmp_path, _run)


def test_forge_cli_apply_requires_gitlab_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE", "1")
    monkeypatch.delenv("DSPX_GITLAB_BASE_URL", raising=False)
    monkeypatch.delenv("DSPX_GITLAB_TOKEN", raising=False)
    monkeypatch.delenv("DSPX_GITLAB_PROJECT_MAP_JSON", raising=False)
    monkeypatch.delenv("DSPX_GITLAB_PROJECT_MAP_FILE", raising=False)

    def _run():
        res = runner.invoke(
            app,
            [
                "intake",
                "Build thing\nDo it safely",
                "--non-interactive",
                "--out-root",
                "generated/forge",
            ],
        )
        assert res.exit_code == 0
        workorder_yaml = res.stdout.strip()
        res2 = runner.invoke(
            app,
            [
                "issues",
                "apply",
                workorder_yaml,
                "--apply",
            ],
        )
        assert res2.exit_code == 2
        msg = (res2.stdout + res2.stderr).lower()
        assert "gitlab not configured" in msg

    _run_in_tmp(tmp_path, _run)

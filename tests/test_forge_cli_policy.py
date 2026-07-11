# summary: "Tests Forge CLI network-mutation gates and configuration failures."
# read_when:
#   - "Changing Forge apply flags, mutation policy, or DSPX configuration handling."

from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dspx_forge.cli import app


pytestmark = pytest.mark.forge

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


def test_forge_cli_apply_accepts_allow_network_mutate_flag(
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
            [
                "issues",
                "apply",
                workorder_yaml,
                "--apply",
                "--allow-network-mutate",
            ],
        )
        assert res2.exit_code == 2
        msg = (res2.stdout + res2.stderr).lower()
        assert "gitlab not configured" in msg
        assert "no such option" not in msg
        assert os.getenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE") is None

    _run_in_tmp(tmp_path, _run)


def test_forge_cli_close_duplicates_accepts_allow_network_mutate_flag(
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
            [
                "issues",
                "close-duplicates",
                workorder_yaml,
                "--apply",
                "--allow-issue-close",
                "--allow-network-mutate",
            ],
        )
        assert res2.exit_code == 2
        msg = (res2.stdout + res2.stderr).lower()
        assert "gitlab not configured" in msg
        assert "no such option" not in msg
        assert os.getenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE") is None

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


def test_forge_cli_fails_closed_for_missing_dspx_config(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_CONFIG", str(tmp_path / "missing.toml"))

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

    assert res.exit_code == 2
    assert "DSPX_CONFIG path not found" in res.output

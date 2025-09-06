from __future__ import annotations

import os
from pathlib import Path

from dspx.config_loader import load_config_env


def test_load_config_env_sets_env(monkeypatch, tmp_path: Path) -> None:
    # Start with clean env for keys we assert
    for k in [
        "MLFLOW_ENABLE",
        "MLFLOW_TRACKING_URI",
        "MLFLOW_EXPERIMENT",
        "CODEX_MODEL",
        "CODEX_REASONING",
        "CODEX_BYPASS",
        "CODEX_SEARCH",
        "DSPX_PROVIDER",
    ]:
        monkeypatch.delenv(k, raising=False)

    cfg = tmp_path / "config.toml"
    cfg.write_text(
        """
        [mlflow]
        enable = true
        tracking_uri = "http://localhost:5000"
        experiment = "TEST_EXP"

        [codex]
        model = "gpt-test"
        reasoning_effort = "minimal"
        bypass = true
        search = false

        [provider]
        name = "codex-exec"
        """,
        encoding="utf-8",
    )

    data = load_config_env(str(cfg))
    assert data["mlflow"]["tracking_uri"] == "http://localhost:5000"
    assert os.environ["MLFLOW_TRACKING_URI"] == "http://localhost:5000"
    assert os.environ["MLFLOW_ENABLE"] == "1"
    assert os.environ["MLFLOW_EXPERIMENT"] == "TEST_EXP"
    assert os.environ["CODEX_MODEL"] == "gpt-test"
    assert os.environ["CODEX_REASONING"] == "minimal"
    assert os.environ["CODEX_BYPASS"] == "1"
    assert os.environ["CODEX_SEARCH"] == "0"
    assert os.environ["DSPX_PROVIDER"] == "codex-exec"

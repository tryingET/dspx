from __future__ import annotations

import os
from pathlib import Path


def test_suite_defaults_are_offline_and_deterministic() -> None:
    # Enforced by tests/conftest.py (autouse fixture).
    assert os.environ.get("DSPX_PROVIDER") == "stub"
    assert os.environ.get("MLFLOW_ENABLE") == "0"

    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI") or ""
    assert tracking_uri.startswith("sqlite:///")
    db_path = Path(tracking_uri.removeprefix("sqlite:///"))
    worker = os.environ.get("PYTEST_XDIST_WORKER", "master")
    assert db_path.name.startswith(f"dspx_mlflow_tests_{worker}_")
    assert db_path.suffix == ".db"


def test_parallel_surfaces_use_per_test_scheduling() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    justfile = (repo_root / "Justfile").read_text(encoding="utf-8")
    shard_script = (repo_root / "scripts" / "ci" / "test-shard.sh").read_text(
        encoding="utf-8"
    )

    assert 'pytest -q tests -n "$workers" --dist load ' in justfile
    assert 'pytest_args=(-q -n "$jobs" --dist load -m "$marker")' in shard_script
    assert "--dist loadfile" not in shard_script

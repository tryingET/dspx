# summary: "Tests deterministic offline test defaults and the complete, disjoint partitioning of parallel test lanes."
# read_when:
#   - "Changing pytest environment defaults, MLflow test isolation, xdist scheduling, markers, or full-gate test recipes."

from __future__ import annotations

import itertools
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


def test_full_offline_lane_is_complete_and_disjoint_from_residual() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    justfile = (repo_root / "Justfile").read_text(encoding="utf-8")

    combined = "not live and not network and not model and not gpu and not postgres"
    residual = "live or network or model or gpu or postgres"
    assert f'-m "{combined}"' in justfile
    assert f'-m "{residual}"' in justfile

    # Exhaust the marker truth table: the combined pool and residual selection are
    # complements, and the compatible fast/slow recipes partition that same pool.
    for slow, live, network, model, gpu, postgres in itertools.product(
        (False, True), repeat=6
    ):
        infrastructure = live or network or model or gpu or postgres
        offline = not infrastructure
        fast_lane = not slow and offline
        slow_lane = slow and offline

        assert offline != infrastructure
        assert not (fast_lane and slow_lane)
        assert (fast_lane or slow_lane) == offline


def test_combined_offline_lane_is_full_gate_only() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    justfile = (repo_root / "Justfile").read_text(encoding="utf-8")
    verify_full = (repo_root / "scripts" / "ci" / "verify-full.sh").read_text(
        encoding="utf-8"
    )

    assert 'DSPX_VERIFY_FULL_COMBINED_OFFLINE:-0}" = "1"' in justfile
    assert "just test-full-offline-parallel jobs=16" in justfile
    assert "just test-parallel jobs=16" in justfile
    assert "just test-slow-parallel jobs=16" in justfile
    assert "DSPX_VERIFY_FULL_COMBINED_OFFLINE=1 just verify-tests" in verify_full

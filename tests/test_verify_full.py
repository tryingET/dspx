# summary: "Tests verify-full aggregation across parallel runtime and test branches."
# read_when:
#   - "Changing the verify-full shell orchestrator, non-overlap environment contracts, or branch failure reporting."

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFY_FULL = REPO_ROOT / "scripts" / "ci" / "verify-full.sh"


def _init_repo(repo: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "pi@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Pi"],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _write_fake_just(bin_dir: Path, *, runtime_exit: int, tests_exit: int) -> None:
    script = f"""#!/bin/sh
set -eu
case \"$1\" in
  verify-fast)
    exit 0
    ;;
  verify-runtime)
    if [ "${{DSPX_VERIFY_FULL_NONOVERLAP:-0}}" != "1" ]; then
      echo missing-nonoverlap-mode >&2
      exit 98
    fi
    echo runtime-failed >&2
    exit {runtime_exit}
    ;;
  verify-tests)
    if [ "${{DSPX_VERIFY_FULL_COMBINED_OFFLINE:-0}}" != "1" ]; then
      echo missing-combined-offline-mode >&2
      exit 97
    fi
    echo tests-failed >&2
    exit {tests_exit}
    ;;
  *)
    echo \"unexpected just target: $1\" >&2
    exit 99
    ;;
esac
"""
    path = bin_dir / "just"
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)


def test_verify_full_fails_when_parallel_branch_fails(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    scripts_ci = repo / "scripts" / "ci"
    scripts_ci.mkdir(parents=True)
    shutil.copy2(VERIFY_FULL, scripts_ci / "verify-full.sh")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_fake_just(bin_dir, runtime_exit=7, tests_exit=0)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"

    result = subprocess.run(
        ["sh", str(scripts_ci / "verify-full.sh")],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    combined = result.stdout + result.stderr
    assert "error: verify-full failed" in combined
    assert "- verify-runtime exit=7" in combined


def test_verify_full_succeeds_when_both_parallel_branches_pass(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    scripts_ci = repo / "scripts" / "ci"
    scripts_ci.mkdir(parents=True)
    shutil.copy2(VERIFY_FULL, scripts_ci / "verify-full.sh")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_fake_just(bin_dir, runtime_exit=0, tests_exit=0)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"

    result = subprocess.run(
        ["sh", str(scripts_ci / "verify-full.sh")],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "ok: verify-full" in result.stdout

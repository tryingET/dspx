"""Tests for the G3 pilot run guards (AK 5092).

Covers: receipt idempotency, in-flight refusal, stale-lock takeover, and a
real two-process race (exactly one winner) reproducing the v3b
duplicate-session incident class.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "benchmarks" / "g3-pilot"))

from g3ps_run_guard import PairRunGuard, RunGuardError  # noqa: E402  # ty: ignore[unresolved-import]


def make_guard(tmp_path: Path) -> PairRunGuard:
    return PairRunGuard(
        lock_dir=tmp_path / "locks", receipts_path=tmp_path / "receipts.jsonl"
    )


def receipt(pair_id: str) -> dict[str, str]:
    return {"pair_id": pair_id, "schema": "test", "run_label": "successor"}


def test_receipt_idempotency_refuses_duplicate(tmp_path: Path) -> None:
    g = make_guard(tmp_path)
    g.append_receipt("P1", receipt("P1"))
    with pytest.raises(RunGuardError, match="already exists"):
        g.append_receipt("P1", receipt("P1"))
    lines = (tmp_path / "receipts.jsonl").read_text().splitlines()
    assert len(lines) == 1


def test_append_receipt_rejects_mismatched_pair_id(tmp_path: Path) -> None:
    g = make_guard(tmp_path)
    with pytest.raises(RunGuardError, match="mismatch"):
        g.append_receipt("P1", receipt("P2"))


def test_inflight_refusal_and_release(tmp_path: Path) -> None:
    g = make_guard(tmp_path)
    with g.pair("P1", pid=os.getpid()):  # this test process is alive
        with pytest.raises(RunGuardError, match="in-flight"):
            g.begin_pair("P1")
    # after release a new run may begin
    info = g.begin_pair("P1")
    assert info["pair_id"] == "P1"
    g.end_pair("P1")


def test_begin_refuses_when_receipt_exists(tmp_path: Path) -> None:
    g = make_guard(tmp_path)
    g.append_receipt("P1", receipt("P1"))
    with pytest.raises(RunGuardError, match="receipt"):
        g.begin_pair("P1")


def test_stale_lock_takeover_records_incident(tmp_path: Path) -> None:
    g = make_guard(tmp_path)
    dead_pid = _spawn_and_reap()
    (g.lock_dir / "P1.inflight.json").write_text(
        json.dumps(
            {
                "pair_id": "P1",
                "pid": dead_pid,
                "started_at": "2026-08-26T00:00:00+00:00",
            }
        )
    )
    info = g.begin_pair("P1")  # dead holder -> takeover allowed
    assert info["pid"] != dead_pid
    takeover = json.loads((g.lock_dir / "P1.takeover.json").read_text())
    assert takeover["pid"] == dead_pid


def _spawn_and_reap() -> int:
    """Return the pid of a short-lived subprocess that has already exited."""
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait(timeout=60)
    assert proc.returncode == 0
    return proc.pid or 0


_RACE_DRIVER = """
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from g3ps_run_guard import PairRunGuard, RunGuardError
g = PairRunGuard(lock_dir=Path(sys.argv[2]), receipts_path=Path(sys.argv[3]))
try:
    with g.pair("RACE"):
        print("WON", flush=True)
        import time; time.sleep(float(sys.argv[4]))
except RunGuardError as exc:
    print("REFUSED", str(exc), flush=True)
"""


def test_two_processes_exactly_one_winner(tmp_path: Path) -> None:
    """Reproduces the v3b duplicate-session race class: two concurrent runs,
    one must lose."""
    import subprocess

    driver = tmp_path / "race_driver.py"
    driver.write_text(_RACE_DRIVER)
    hold_s = "1.5"
    procs = [
        subprocess.Popen(
            [
                sys.executable,
                str(driver),
                str(REPO_ROOT / "benchmarks" / "g3-pilot"),
                str(tmp_path / "locks"),
                str(tmp_path / "receipts.jsonl"),
                hold_s,
            ],
            stdout=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    outputs = [p.communicate(timeout=60)[0].strip() for p in procs]
    winners = sum(1 for out in outputs if out.startswith("WON"))
    refusers = sum(1 for out in outputs if out.startswith("REFUSED"))
    assert winners == 1, outputs
    assert refusers == 1, outputs


def test_race_receipt_append_exactly_one(tmp_path: Path) -> None:
    """Two processes appending the same pair receipt: one line survives."""
    import subprocess

    driver = tmp_path / "append_driver.py"
    driver.write_text(
        "import sys\nfrom pathlib import Path\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from g3ps_run_guard import PairRunGuard, RunGuardError\n"
        "g = PairRunGuard(lock_dir=Path(sys.argv[2]), receipts_path=Path(sys.argv[3]))\n"
        "try:\n"
        "    g.append_receipt('R2', {'pair_id': 'R2', 'who': sys.argv[4]})\n"
        "    print('APPENDED')\n"
        "except RunGuardError:\n"
        "    print('REFUSED')\n"
    )
    procs = [
        subprocess.Popen(
            [
                sys.executable,
                str(driver),
                str(REPO_ROOT / "benchmarks" / "g3-pilot"),
                str(tmp_path / "locks"),
                str(tmp_path / "receipts.jsonl"),
                str(i),
            ],
            stdout=subprocess.PIPE,
            text=True,
        )
        for i in range(2)
    ]
    outputs = [p.communicate(timeout=60)[0].strip() for p in procs]
    lines = (tmp_path / "receipts.jsonl").read_text().splitlines()
    assert sum(1 for o in outputs if o == "APPENDED") == 1, outputs
    assert sum(1 for o in outputs if o == "REFUSED") == 1, outputs
    assert len(lines) == 1
    assert json.loads(lines[0])["pair_id"] == "R2"

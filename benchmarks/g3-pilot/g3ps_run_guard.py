"""Single-writer run guards for G3 pilot runners (AK 5092).

Closes the duplicate-session race class recorded in the v3b run (AK 5085
incidents): (a) an in-flight pair lock so a second concurrent ``run`` for the
same pair fails closed instead of racing; (b) per-pair receipt idempotency so
a duplicate receipt can never be appended; (c) atomic receipt append under
the same lock discipline. Designed for the successor runner (g3ps_*); the
frozen v3/v3b modules are intentionally untouched.
"""

from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class RunGuardError(RuntimeError):
    """Raised when a guard refuses an operation (fail-closed)."""


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # alive but owned by another user
    return True


class PairRunGuard:
    """In-flight + receipt-idempotency guards for one pilot run.

    ``lock_dir`` holds per-pair in-flight lock files; ``receipts_path`` is the
    JSONL receipt log. Both are guarded by an flock on ``guard.lock`` so
    check-then-act sequences are single-writer.
    """

    def __init__(self, lock_dir: Path, receipts_path: Path) -> None:
        self.lock_dir = Path(lock_dir)
        self.receipts_path = Path(receipts_path)
        self.lock_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------ internals

    @contextmanager
    def _guard_lock(self) -> Iterator[None]:
        path = self.lock_dir / "guard.lock"
        with open(path, "a+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    def _pair_lock_path(self, pair_id: str) -> Path:
        return self.lock_dir / f"{pair_id}.inflight.json"

    # ------------------------------------------------------ receipt side

    def _load_receipt_pair_ids(self) -> set[str]:
        if not self.receipts_path.exists():
            return set()
        ids: set[str] = set()
        for line in self.receipts_path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                ids.add(json.loads(line)["pair_id"])
            except (json.JSONDecodeError, KeyError) as exc:  # pragma: no cover
                raise RunGuardError(f"corrupt receipts line: {line[:80]!r}") from exc
        return ids

    def pair_has_receipt(self, pair_id: str) -> bool:
        with self._guard_lock():
            return pair_id in self._load_receipt_pair_ids()

    def append_receipt(self, pair_id: str, record: dict[str, Any]) -> None:
        """Append exactly one receipt for ``pair_id``; refuse duplicates."""
        with self._guard_lock():
            if pair_id in self._load_receipt_pair_ids():
                raise RunGuardError(f"receipt already exists for {pair_id}")
            if record.get("pair_id") != pair_id:
                raise RunGuardError("record pair_id mismatch")
            line = json.dumps(record, sort_keys=True)
            with open(self.receipts_path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()
                os.fsync(fh.fileno())

    # ---------------------------------------------------- in-flight side

    def begin_pair(self, pair_id: str, pid: int | None = None) -> dict[str, Any]:
        """Mark ``pair_id`` in-flight; refuse when already in-flight (live)."""
        pid = os.getpid() if pid is None else pid
        with self._guard_lock():
            if pair_id in self._load_receipt_pair_ids():
                raise RunGuardError(f"pair {pair_id} already has a receipt; not-run protocol violated")
            lock_path = self._pair_lock_path(pair_id)
            if lock_path.exists():
                existing = json.loads(lock_path.read_text())
                if _pid_alive(int(existing["pid"])):
                    raise RunGuardError(
                        f"pair {pair_id} is in-flight (pid {existing['pid']} since {existing['started_at']})"
                    )
                # stale lock: the holder died; take over and record it
                existing["superseded_by_takeover_at"] = _now()
                (self.lock_dir / f"{pair_id}.takeover.json").write_text(
                    json.dumps(existing, sort_keys=True)
                )
            info = {"pair_id": pair_id, "pid": pid, "started_at": _now()}
            lock_path.write_text(json.dumps(info, sort_keys=True))
            return info

    def end_pair(self, pair_id: str) -> None:
        """Clear the in-flight mark for ``pair_id`` (idempotent)."""
        with self._guard_lock():
            self._pair_lock_path(pair_id).unlink(missing_ok=True)

    @contextmanager
    def pair(self, pair_id: str, pid: int | None = None) -> Iterator[dict[str, Any]]:
        """Begin/end guard context: refuses concurrent runs, always clears."""
        info = self.begin_pair(pair_id, pid)
        try:
            yield info
        finally:
            self.end_pair(pair_id)

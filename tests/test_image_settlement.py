# summary: "Custody settlement follow-ups: one IO window across response chunks, and reconciliation of unready roots and link-window residue."
# read_when:
#   - "Changing the image response read window, record publication or read-only reconciliation."
"""AK6811, the AK6756 S47 review follow-ups, inside the guarded clean worker.

The worker and the supervising parent are the production ones from
`test_image_custody`; this module only adds faults (a trickle against a short admitted
IO window, a kill inside one publication's link window, an initializer killed between
its claim and `ready.json`) and asserts on durable records and read-only reconciliation.
"""

from __future__ import annotations

import gzip
import os
import signal
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest

import test_image_custody as custody
from dspx.image_admission import ImageContractError, canonical, digest, parse_json, sha
from dspx.image_artifacts import ImageRunAnchor, verify_image_run
from dspx.image_record_validation import read_only_custody, reconcile
from dspx.image_records import residue
from dspx.image_worker import worker_entry
from test_image_custody import _Case, _Run, _assert_spent, _commitment, _reconciled
from test_image_custody import _replace, _status

_ENTRY = "test_image_settlement:_settlement_entry"
case, run = custody.case, custody.run  # the shared prepared candidate and fresh roots


@pytest.fixture(autouse=True)
def _synthetic_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE", "1")


def _sigkill(*args: object, **kwargs: object) -> None:
    os.kill(os.getpid(), signal.SIGKILL)


def _kill_inside_link_window(patch: pytest.MonkeyPatch, prefix: str) -> None:
    """Kill the worker after `os.link` published one record, before its `os.unlink`."""
    link, unlink, linked = os.link, os.unlink, []

    def tracked(src, dst, **kwargs):
        link(src, dst, **kwargs)
        linked.append(dst)

    def killing(path, **kwargs):
        if linked and str(linked[-1]).startswith(prefix) and residue(str(path)):
            _sigkill()
        unlink(path, **kwargs)

    patch.setattr(os, "link", tracked)
    patch.setattr(os, "unlink", killing)


@worker_entry
def _settlement_entry(params: dict[str, Any]) -> dict[str, object]:
    """`_custody_entry`, plus the caller's fixed code folded into the commitment."""
    fault, caught = params["fault"], []
    denied = custody._denied_after

    def observed(*args: object) -> dict[str, object]:
        error = sys.exc_info()[1]  # the refusal `_flow` is handling right now
        caught.append(error.code if type(error) is ImageContractError else "other")
        status = denied(*args)
        state = {"caller": caught, "status": status["commitment_sha256"]}
        return {**status, "commitment_sha256": digest("settlement-case-v1", state)}

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(custody, "_denied_after", observed)
        if fault.startswith("window:"):
            _kill_inside_link_window(patch, fault.removeprefix("window:"))
        if fault.startswith("gzip_"):
            patch.setattr(custody, "_transport", _coded_transport)
        return custody._custody_entry(params)


class _CodedTrickle(httpx.SyncByteStream):
    """A gzip header whose comment never ends: raw bytes arrive, none ever decode."""

    def __iter__(self):
        yield b"\x1f\x8b\x08\x10\x00\x00\x00\x00\x00\xff"  # FCOMMENT set
        while True:
            time.sleep(0.1)
            yield b"c"


def _coded_transport(params: dict[str, Any], fault: str) -> httpx.MockTransport:
    from dspx.image_effects import fixture_transport

    owner = fixture_transport(params["fixture"], custody._MODEL)

    def handler(request: httpx.Request) -> httpx.Response:
        plain = owner.handler(request)  # the owner fixture records exactly this send
        assert isinstance(plain, httpx.Response)
        headers = {"Content-Encoding": "gzip"}
        if fault == "gzip_trickle":
            return httpx.Response(200, headers=headers, stream=_CodedTrickle())
        body = gzip.compress(plain.read())  # a valid completion behind a coding
        return httpx.Response(200, headers=headers, content=body, request=request)

    return httpx.MockTransport(handler)


def _raw(run: _Run, name: str) -> bytes:
    """Test-side bytes of one custody name, whatever its link count."""
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=run.fds["custody"])
    try:
        return os.read(fd, 65_536)
    finally:
        os.close(fd)


def _anchor(run: _Run, closure_sha256: str) -> ImageRunAnchor:
    return ImageRunAnchor(
        run.fds["custody"],
        run.fds["artifacts"],
        closure_sha256,
        run.admission_raw,
        canonical(run.prepared["source"]),
        canonical(run.manifest),
        run.prepared["output_slots"],
    )


def _links(run: _Run, name: str) -> tuple[int, int]:
    row = os.stat(name, dir_fd=run.fds["custody"], follow_symlinks=False)
    return row.st_ino, row.st_nlink


# ------------------------------------------------- one IO window across chunks


def test_io_timeout_bounds_a_trickling_read_and_settles_inside_the_worker(
    case: _Case, tmp_path: Path
) -> None:
    """Chunks that each beat the per-read timeout cannot outlast the admitted window.

    The worker stops at `per_request_io_timeout_ms`, long before its wall deadline,
    and itself writes the one fixed `effect_indeterminate` terminal: it never races
    the parent's SIGTERM, never retries or falls back, and latches.
    """
    run = _Run(case, tmp_path, wall_ms=20_000, io_ms=1_000)
    try:
        result = run.execute("trickle", entry=_ENTRY)
        names = run.names()
        inner = _commitment(names, poisoned=True, latched=True, sends=1)
        state = {"caller": ["image_finalization"], "status": inner}
        assert result == _status("failed", digest("settlement-case-v1", state))
        assert names == ["intent-1.json", "lock", "ready.json", "terminal-1.json"]
        intent, terminal = run.record("intent-1.json"), run.record("terminal-1.json")
        assert terminal["provider_disposition"] == "effect_indeterminate"
        assert terminal["failure_code"] == "io" and terminal["dispatch_count"] == 1
        assert terminal["response_sha256"] is None  # no body was ever accepted
        elapsed = terminal["terminal_utc_ms"] - intent["reserved_utc_ms"]
        assert 1_000 <= elapsed < 1_000 + 2_000  # the IO window, not the wall budget
        assert len(run.names("wire")) == 1  # one send, no retry or fallback request
        _reconciled(_assert_spent(run, sends=1), "effect_indeterminate", terminal=True)
    finally:
        run.close()


def test_a_content_coding_cannot_hide_a_trickle_from_the_io_window(
    case: _Case, tmp_path: Path
) -> None:
    """Review follow-up: raw chunks that decode to nothing still meet the window."""
    run = _Run(case, tmp_path, wall_ms=20_000, io_ms=1_000)
    try:
        result = run.execute("gzip_trickle", entry=_ENTRY)
        assert type(result) is dict and result["status"] == "failed", result
        intent, terminal = run.record("intent-1.json"), run.record("terminal-1.json")
        assert terminal["provider_disposition"] == "effect_indeterminate"
        assert terminal["failure_code"] == "io" and terminal["response_sha256"] is None
        elapsed = terminal["terminal_utc_ms"] - intent["reserved_utc_ms"]
        assert 1_000 <= elapsed < 1_000 + 2_000
        assert len(run.names("wire")) == 1
    finally:
        run.close()


def test_a_coded_response_is_a_completed_failure_and_never_decoded(run: _Run) -> None:
    """Review follow-up: only identity bodies are read; a coding is never inflated."""
    result = run.execute("gzip_body", entry=_ENTRY)
    assert type(result) is dict and result["status"] == "failed", result
    terminal = run.record("terminal-1.json")
    assert terminal["provider_disposition"] == "completed_failure"
    assert terminal["failure_code"] == "response" and terminal["dispatch_count"] == 1
    assert run.names("artifacts") == [] and len(run.names("wire")) == 1
    _reconciled(_assert_spent(run, sends=1), "completed_failure", terminal=True)


# ----------------------------------------- a claimed root that never got ready


def _dying_initializer(run: _Run, stage: str):
    """The real parent initializer, killed after its O_EXCL claim, before ready."""
    import dspx.image_custody as owner

    initialize = run.initializer()

    def action(ready: dict[str, object]) -> None:
        with pytest.MonkeyPatch.context() as patch:  # only in the forked delegate
            if stage == "claimed":
                patch.setattr(owner, "publish", _sigkill)
            else:
                patch.setattr(os, "link" if stage == "written" else "unlink", _sigkill)
            initialize(ready)

    return action


@pytest.mark.parametrize(
    ("stage", "pending"),
    [
        ("claimed", 0),  # killed before ready.json publication started
        ("written", 1),  # complete pending ready, never linked
        ("linked", 1),  # ready.json linked twice: killed inside its link window
    ],
)
def test_claimed_root_without_ready_reconciles_as_spent_without_attempts(
    run: _Run, stage: str, pending: int
) -> None:
    """Nothing could dispatch without a settled ready.json; no record is trusted."""
    assert run.execute(parent_action=_dying_initializer(run, stage)) == (
        "image_durability"
    )
    names = run.names()
    durable = {name for name in names if not name.startswith(".pending-")}
    assert durable == ({"lock", "ready.json"} if stage == "linked" else {"lock"})
    assert len(names) - len(durable) == pending
    assert run.names("wire") == []
    before = run.snapshot()
    with pytest.raises(ImageContractError, match="^image_spent$"):
        run.initializer()
    with pytest.raises(ImageContractError, match="^image_(spent|custody)$"):
        verify_image_run(_anchor(run, "0" * 64))
    assert run.reconcile() == {
        "schema_version": "dspx-image-custody-reconciliation-v1",
        "status": "spent",
        "dispatch_available": False,
        "ready_present": False,
        "planned_dispatches": 1,
        "consumed_dispatches": 0,
        "publication_residue": pending,
        "closure_present": False,
        "terminal_effect": "none",
        "attempts": [],
    }
    assert run.snapshot() == before  # pure read: nothing written, nothing minted
    # A view taken while unready is re-checked on reconcile's own listing (review).
    view = read_only_custody(
        run.fds["custody"],
        admission_raw=run.admission_raw,
        source_raw=canonical(run.prepared["source"]),
        manifest_raw=canonical(run.manifest),
        unready=True,
    )
    # Any record without a settled ready.json is not a state the protocol can reach.
    _replace(run, "intent-1.json", {"schema_version": "dspx-image-dispatch-intent-v1"})
    with pytest.raises(ImageContractError, match="^image_custody$"):
        run.reconcile()
    with pytest.raises(ImageContractError, match="^image_custody$"):
        reconcile(view)


# ------------------------------------------------------- link-window residue


@pytest.mark.parametrize(
    ("record", "sends"),
    [("intent-1.json", 0), ("terminal-1.json", 1), ("closure.json", 1)],
)
def test_worker_killed_inside_a_link_window_reconciles_conservatively(
    run: _Run, record: str, sends: int
) -> None:
    """A record linked twice with its own pending twin is reported, never trusted."""
    prefix = record.removesuffix("1.json")  # intent-, terminal- or closure.json
    assert run.execute(f"window:{prefix}", entry=_ENTRY) == "image_interruption"
    names = run.names()
    (twin,) = [name for name in names if name.startswith(".pending-")]
    assert residue(twin) and record in names
    assert _links(run, record) == _links(run, twin) and _links(run, twin)[1] == 2
    assert len(run.names("wire")) == sends
    before = run.snapshot()
    with pytest.raises(ImageContractError, match="^image_spent$"):
        run.initializer()
    closure = sha(_raw(run, "closure.json")) if record == "closure.json" else "0" * 64
    with pytest.raises(ImageContractError, match="^image_spent$"):
        verify_image_run(_anchor(run, closure))
    state = run.reconcile()
    assert run.snapshot() == before
    assert state["ready_present"] is True and state["closure_present"] is False
    assert state["publication_residue"] == 1 and state["dispatch_available"] is False
    (attempt,) = state["attempts"]
    assert attempt["intent_sha256"] == sha(_raw(run, "intent-1.json"))
    if record == "closure.json":  # settled success terminal; only closure unsettled
        assert attempt["publication_unsettled"] is False
        assert state["terminal_effect"] == "completed_success"
        return
    assert attempt["publication_unsettled"] is True
    assert attempt["provider_disposition"] == "effect_indeterminate"
    assert attempt["dispatch_count"] is None  # an unconfirmed record mints no send
    assert state["terminal_effect"] == "effect_indeterminate"
    if record == "terminal-1.json":  # it records success; unconfirmed, never trusted
        assert attempt["terminal_sha256"] == sha(_raw(run, record))
        assert parse_json(_raw(run, record))["provider_disposition"] == (
            "completed_success"
        )
    else:
        assert attempt["terminal_sha256"] is None


def test_only_one_own_pending_twin_makes_a_link_window(run: _Run) -> None:
    """A test-owned hard link to a canonical pending name; a second link refuses."""
    assert run.execute()["status"] == "completed"
    root = run.fds["custody"]
    os.unlink("closure.json", dir_fd=root)
    success = run.reconcile()
    assert success["terminal_effect"] == "completed_success"
    first = f".pending-{uuid.uuid4()}"
    os.link("terminal-1.json", first, src_dir_fd=root, dst_dir_fd=root)
    state = run.reconcile()
    (attempt,) = state["attempts"]
    assert attempt["provider_disposition"] == "effect_indeterminate"  # never success
    assert attempt["publication_unsettled"] is True
    assert attempt["terminal_sha256"] == success["attempts"][0]["terminal_sha256"]
    assert state["terminal_effect"] == "effect_indeterminate"
    with pytest.raises(ImageContractError, match="^image_spent$"):
        verify_image_run(_anchor(run, "0" * 64))
    second = f".pending-{uuid.uuid4()}"
    os.link("terminal-1.json", second, src_dir_fd=root, dst_dir_fd=root)
    with pytest.raises(ImageContractError, match="^image_custody$"):
        run.reconcile()
    os.unlink(second, dir_fd=root)
    os.unlink(first, dir_fd=root)
    os.link("terminal-1.json", ".pending-foreign", src_dir_fd=root, dst_dir_fd=root)
    with pytest.raises(ImageContractError, match="^image_custody$"):
        run.reconcile()

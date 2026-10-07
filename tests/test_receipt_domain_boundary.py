"""Explicit image-route refusal precedes caller path access; legacy text is unchanged."""

from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path
import subprocess
import tempfile

import pytest

from dspx import image_artifacts
from dspx.services import run_replay_service as replay
from run_receipts_helpers import _generate_signature_receipt


def _fuzz_call(entry: Callable[..., object], *args: object, **kwargs: object) -> object:
    """Invoke deliberately invalid nominal arguments without declaring them valid."""
    return entry(*args, **kwargs)


class _Poison:
    def __init__(self, hits: list[str], label: str):
        object.__setattr__(self, "_hits", hits)
        object.__setattr__(self, "_label", label)

    def _touch(self, action):
        object.__getattribute__(self, "_hits").append(
            object.__getattribute__(self, "_label") + ":" + action
        )
        raise AssertionError("unavailable route inspected caller data")

    def __getattribute__(self, name):
        object.__getattribute__(self, "_touch")("attribute:" + name)

    def __str__(self):
        object.__getattribute__(self, "_touch")("str")

    def __repr__(self):
        object.__getattribute__(self, "_touch")("repr")

    def __fspath__(self):
        object.__getattribute__(self, "_touch")("fspath")

    def __bool__(self):
        object.__getattribute__(self, "_touch")("truth")

    def __eq__(self, other):
        object.__getattribute__(self, "_touch")("equality")

    def __iter__(self):
        object.__getattribute__(self, "_touch")("iteration")


_CHECK_REFUSAL = {
    "status": "invalid",
    "error_codes": ["image_execution_unavailable"],
    "execution_reproduction": False,
    "dispatch_available": False,
}
_EXECUTION_REFUSAL = {
    "status": "invalid",
    "error_codes": ["image_execution_replay_unsupported"],
    "execution": {"attempted": False, "strategy": None},
    "execution_reproduction": False,
    "dispatch_available": False,
}


@pytest.mark.parametrize("api", ["check", "execute"])
@pytest.mark.parametrize(
    "anchor_kind", ["poison", "false", "zero", "dict", "list", "copied", "text"]
)
@pytest.mark.parametrize("guise", ["poisoned-path", "renamed-text", "image-schema"])
def test_anchored_receipt_refusal_before_parent_access(
    api: str,
    anchor_kind: str,
    guise: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    hits: list[str] = []
    anchors = {
        "poison": _Poison(hits, "anchor"),
        "false": False,
        "zero": 0,
        "dict": {},
        "list": [],
        "copied": {"mode": "live", "approval_ref": "ak://evidence/13933"},
        "text": "ordinary",
    }
    path = tmp_path / "ordinary.json"
    path.write_text(
        json.dumps(
            {
                "run_kind": "signature-gen"
                if guise == "renamed-text"
                else "program-runtime-image",
                "schema_version": "dspx-image-run-receipt-v1",
                "fixture_payload": "data:image/png;base64,c3ludGhldGlj",
            }
        )
    )
    meta = _Poison(hits, "meta") if guise == "poisoned-path" else path
    output = _Poison(hits, "output")

    def trap(label: str):
        def forbidden(*args, **kwargs):
            hits.append(label)
            raise AssertionError("unavailable route entered " + label)

        return forbidden

    # Scope global/path traps to the call so pytest and fixture IO remain unaffected.
    with monkeypatch.context() as patch:
        for owner, names in (
            (replay, ("load_run_receipt", "_exclusive_write_confined")),
            (image_artifacts, ("verify_image_run",)),
            (
                Path,
                (
                    "exists",
                    "is_file",
                    "stat",
                    "read_text",
                    "read_bytes",
                    "write_text",
                    "write_bytes",
                    "mkdir",
                ),
            ),
            (replay.os, ("open", "fstat")),
            (subprocess, ("run",)),
            (tempfile, ("TemporaryDirectory", "mkstemp")),
        ):
            for name in names:
                patch.setattr(owner, name, trap(name))
        if api == "check":
            result = _fuzz_call(
                replay.check_run_receipt, meta, image_anchor=anchors[anchor_kind]
            )
        else:
            result = _fuzz_call(
                replay.execute_run_receipt,
                meta,
                output,
                image_anchor=anchors[anchor_kind],
            )
    assert hits == []  # independent counter also catches swallowed spy exceptions
    assert result == (_CHECK_REFUSAL if api == "check" else _EXECUTION_REFUSAL)


@pytest.mark.parametrize("api", ["check", "execute"])
@pytest.mark.parametrize("input_kind", ["genuine-ordinary", "missing", "malformed"])
def test_anchored_refusal_ignores_contents_and_keeps_concrete_target_absent(
    api: str,
    input_kind: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    if input_kind == "genuine-ordinary":
        meta = _generate_signature_receipt(
            tmp_path, monkeypatch, output_name="ordinary.py"
        )
        assert replay.check_run_receipt(meta)["status"] == "ok"
    else:
        meta = tmp_path / "unknown.json"
        if input_kind == "malformed":
            meta.write_text("{not-json")
    output = tmp_path / "forbidden-output.json"
    existing = set(tmp_path.rglob("*"))
    hits = []

    def forbidden(*args, **kwargs):
        hits.append(True)
        raise AssertionError("explicit refusal inspected concrete paths")

    with monkeypatch.context() as patch:
        patch.setattr(replay, "load_run_receipt", forbidden)
        patch.setattr(replay, "_exclusive_write_confined", forbidden)
        patch.setattr(image_artifacts, "verify_image_run", forbidden)
        patch.setattr(subprocess, "run", forbidden)
        for name in (
            "exists",
            "is_file",
            "stat",
            "read_text",
            "read_bytes",
            "write_text",
            "write_bytes",
        ):
            patch.setattr(Path, name, forbidden)
        if api == "check":
            result = replay.check_run_receipt(meta, image_anchor=False)
        else:
            result = replay.execute_run_receipt(meta, output, image_anchor=False)
    assert hits == []
    assert result == (_CHECK_REFUSAL if api == "check" else _EXECUTION_REFUSAL)
    assert not output.exists()
    assert set(tmp_path.rglob("*")) == existing


@pytest.mark.parametrize("drift", [False, True])
def test_ordinary_check_none_keeps_complete_legacy_report(
    drift: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    meta = _generate_signature_receipt(tmp_path, monkeypatch, output_name="source.py")
    if drift:
        (tmp_path / "source.py").write_text("print('changed')\n")
    omitted = replay.check_run_receipt(meta)
    explicit_none = replay.check_run_receipt(meta, image_anchor=None)
    assert explicit_none == omitted  # no identity or semantic normalization
    assert omitted["status"] == ("failed" if drift else "ok")
    assert omitted["checks"] and omitted["receipt_hash"]
    assert "replay_claims" in omitted and "receipt_path" in omitted
    if drift:
        assert "output_hash_mismatch" in omitted["error_codes"]
    else:
        assert (
            omitted["replay_claims"]["dimensions"]["receipt_integrity_check"]["status"]
            == "passed"
        )


@pytest.mark.parametrize("explicit_none", [False, True])
def test_ordinary_execution_retains_real_strategy_and_evidence(
    explicit_none: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    meta = _generate_signature_receipt(tmp_path, monkeypatch, output_name="source.py")
    target = tmp_path / "replayed.py"
    result = (
        replay.execute_run_receipt(meta, target, image_anchor=None)
        if explicit_none
        else replay.execute_run_receipt(meta, target)
    )
    assert type(result) is dict
    assert result["status"] == "executed"
    execution = result["execution"]
    assert execution["strategy"] == "signature-gen-local-reexecution"
    assert execution["provider"] == "stub"
    assert execution["effects"]["subprocess"] is True
    assert execution["effects"]["network_access_requested"] is False
    assert execution["actual_hash"] == result["receipt_hash"]
    assert result["checks"]["execution_replay_reexecuted_output_hash_match"] is True
    assert result["checks"]["execution_replay_source_output_preserved"] is True
    assert execution["evidence"]["schema_version"] == "execution-replay-evidence-v1"
    assert execution["evidence"]["replay_claims"] == result["replay_claims"]
    assert (
        result["replay_claims"]["dimensions"]["deterministic_regeneration"]["status"]
        == "passed"
    )
    assert target.read_bytes() == (tmp_path / "source.py").read_bytes()


def test_unanchored_image_schema_receipt_gets_the_exact_replay_refusal(
    tmp_path: Path,
) -> None:
    """A dspx-image-* schema is image domain even with an ordinary run_kind."""
    receipt = tmp_path / "manifest.json.meta.json"
    receipt.write_text(
        json.dumps({"run_kind": "program-runtime", "schema_version": "dspx-image-x"}),
        encoding="utf-8",
    )
    target = tmp_path / "replay.json"
    report = replay.execute_run_receipt(receipt, target)
    assert list(report) == [
        "status",
        "error_codes",
        "execution",
        "execution_reproduction",
        "dispatch_available",
    ]
    assert report["error_codes"] == ["image_execution_replay_unsupported"]
    assert report["execution"] == {"attempted": False, "strategy": None}
    assert not target.exists()
    checked = replay.check_run_receipt(receipt)
    assert checked["status"] == "invalid" and checked["error_codes"] == [
        "image_custody"
    ]

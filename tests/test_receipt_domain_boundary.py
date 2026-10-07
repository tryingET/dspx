"""Explicit image-route refusal precedes caller path access; legacy text is unchanged.

AK6756 rows here: S18 replay capture, S49 mixed v1/image rows, S51 echoed payloads.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
import json
from pathlib import Path
import subprocess
import tempfile

import pytest

from dspx import image_artifacts
from dspx.image_execution import ImageExecutionRequest
from dspx.image_records import list_root
from dspx.services import run_replay_service as replay
from dspx.services.program_runtime_episode import run_program_runtime_episode
from run_receipts_helpers import _generate_signature_receipt
from test_image_execution import (
    _ANSWER,
    _PRIVATE_ROOTS,
    _RefusalPoison,
    _admitted_request,
    _execute_route,
    _payload_free,
    _prepare_route,
    _records,
    _route_fds,
    _shipped_inputs,
)


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


# AK6756 S18: image replay capture is refused before any episode work.
@pytest.mark.parametrize("request_kind", ["poison", "prepared"])
def test_s18_replay_capture_with_image_execution_refuses_before_any_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request_kind: str
):
    """S18: image replay capture is unsupported; nothing is set up, spent or written."""
    from dspx import image_execution, image_source_io
    from dspx.image_admission import ImageContractError
    from dspx.services import program_runtime_episode as episode

    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE", "1")
    _shipped_inputs(tmp_path, media="image/png")
    entries: list[str] = []

    def trap(label: str) -> Callable[..., object]:
        def forbidden(*args: object, **kwargs: object) -> object:
            entries.append(label)
            raise AssertionError("replay capture refusal crossed " + label)

        return forbidden

    with _route_fds(tmp_path) as fds:
        request: object = _RefusalPoison()
        if request_kind == "prepared":
            prepared = _prepare_route(fds, use_cot=False)
            request = _admitted_request(
                fds, prepared, route="episode", completion=_ANSWER
            )
        with monkeypatch.context() as patch:
            for owner, names in (
                (
                    image_execution,
                    (
                        "execute_image_program",
                        "supervise_image_worker",
                        "parent_initializer",
                        "validate_admission",
                        "private_root",
                    ),
                ),
                (image_source_io, ("open_root",)),
                (
                    episode,
                    (
                        "_load_inputs",
                        "_materialize_runtime_inputs",
                        "_safe_stub_response_for_replay",
                        "_generated_program_module",
                        "_configure_provider",
                    ),
                ),
            ):
                for name in names:
                    patch.setattr(owner, name, trap(name))
            with pytest.raises(ImageContractError) as caught:
                run_program_runtime_episode(
                    manifest_path=tmp_path / "candidate" / "manifest.json",
                    inputs_path=tmp_path / "inputs" / "inputs.json",
                    outdir=tmp_path / "artifacts",
                    capture_replay_fixture=True,
                    image_execution=request,
                )
        assert str(caught.value) == caught.value.code == "image_replay_unsupported"
        assert caught.value.__cause__ is None and caught.value.__suppress_context__
        assert entries == []
        assert [list_root(fds[name]) for name in ("artifacts", "custody", "wire")] == [
            [],
            [],
            [],
        ]
        if type(request) is ImageExecutionRequest:
            # Nothing was reserved or spent: the same admitted request still runs once.
            anchor = _execute_route(tmp_path, request, route="episode")
            assert image_artifacts.verify_image_run(anchor)["status"] == "ok"
            receipt = tmp_path / "artifacts" / "runtime_image_episode.json.meta.json"
            refused = replay.execute_run_receipt(
                receipt, tmp_path / "artifacts" / "replay.json"
            )
            assert refused["error_codes"] == ["image_execution_replay_unsupported"]
    assert not (tmp_path / "artifacts" / "runtime_replay_fixture.json").exists()
    assert not (tmp_path / "artifacts" / "runtime_inputs.json").exists()


# AK6756 S49: new image rows never relabel or mix with historical v1 rows.
_V1_NAMES = frozenset(
    {
        "runtime_inputs.json",
        "runtime_replay_fixture.json",
        "runtime_episode.json",
        "runtime_episode.json.meta.json",
        "behavior_results.json",
        "oracle_evidence.json",
        "program_runtime_traces.json",
    }
)


def test_s49_image_episode_keeps_new_names_and_rejects_mixed_v1_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from dspx.image_admission import ImageContractError
    from dspx.run_receipts import build_run_receipt

    v1_meta = _generate_signature_receipt(tmp_path, monkeypatch, output_name="v1.py")
    v1_raw = v1_meta.read_bytes()
    v1_report = replay.check_run_receipt(v1_meta)
    assert v1_report["status"] == "ok"
    monkeypatch.setenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE", "1")
    root = tmp_path / "run"
    artifacts = root / "artifacts"
    _shipped_inputs(root, media="image/png")
    with _route_fds(root) as fds:
        prepared = _prepare_route(fds, use_cot=False)
        request = _admitted_request(fds, prepared, route="episode", completion=_ANSWER)
        anchor = _execute_route(root, request, route="episode")
        names = set(list_root(fds["artifacts"]))
        assert not names & _V1_NAMES
        assert all(name.startswith(("image_", "runtime_image_")) for name in names)
        schemas = {
            name: json.loads((artifacts / name).read_bytes())["schema_version"]
            for name in names
        }
        assert schemas == {
            name: image_artifacts._SCHEMAS.get(name, "program-image-output-v1")
            for name in names
        }
        assert all("-image-" in schema for schema in schemas.values())
        # A v1 row beside the image rows is rejected, never adopted or ignored.
        for name in sorted(_V1_NAMES):
            (artifacts / name).write_bytes(v1_raw)
            with pytest.raises(ImageContractError, match="^image_custody$"):
                image_artifacts.verify_image_run(anchor)
            (artifacts / name).unlink()
        assert image_artifacts.verify_image_run(anchor)["status"] == "ok"
    image_row = json.loads(
        (artifacts / "runtime_image_episode.json.meta.json").read_text()
    )
    v1_row = json.loads(v1_raw)
    mixed = {
        "image-row-with-v1-fields": {**v1_row, **image_row},
        "v1-row-with-image-run-kind": {**v1_row, "run_kind": image_row["run_kind"]},
        "v1-row-with-image-schema": {
            **v1_row,
            "schema_version": image_row["schema_version"],
        },
    }
    # A genuine v1 row that also carries an image-only commitment is mixed, never v1.
    for key in (
        "admission_sha256",
        "caller_run_id",
        "content_artifact_manifest_sha256",
        "input_manifest_sha256",
        "source_package_sha256",
    ):
        mixed[f"v1-row-with-{key}"] = {**v1_row, key: image_row.get(key, "0" * 64)}
    for name, row in mixed.items():
        path = tmp_path / f"{name}.meta.json"
        path.write_text(json.dumps(row))
        assert replay.check_run_receipt(path) == {
            **_CHECK_REFUSAL,
            "error_codes": ["image_custody"],
        }
        target = tmp_path / f"{name}.replayed"
        assert replay.execute_run_receipt(path, target) == _EXECUTION_REFUSAL
        assert not target.exists()
    # The v1 writer cannot emit an image row; the v1 row's bytes and meaning are unchanged.
    with pytest.raises(ImageContractError, match="^image_custody$"):
        build_run_receipt(
            run_kind=image_row["run_kind"],
            output_path=tmp_path / "never.json",
            output_hash="0" * 64,
            template_version=None,
            cache_key=None,
            cache_file=None,
            cache_enabled=False,
        )
    assert v1_meta.read_bytes() == v1_raw
    assert replay.check_run_receipt(v1_meta) == v1_report


# AK6756 S51: a completed response echoing the input is refused and copied nowhere.
@pytest.mark.parametrize("route", ["episode", "direct"])
@pytest.mark.parametrize("echo", ["base64", "data-uri", "marker"])
def test_s51_echoed_payload_leaves_no_copy_in_files_streams_caches_or_traces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    route: str,
    echo: str,
):
    import base64

    from dspx.image_admission import ImageContractError, parse_json, sha
    from dspx.image_input_contract import END, START
    from dspx.image_records import read_record
    from dspx.services import program_runtime_episode as episode

    root = tmp_path / "run"
    pixels = _shipped_inputs(root, media="image/png")
    uri = "data:image/png;base64," + base64.b64encode(pixels).decode("ascii")
    echoed = {
        "base64": uri.partition(",")[2],
        "data-uri": uri,
        "marker": START
        + json.dumps(
            [{"type": "image_url", "image_url": {"url": uri}}], separators=(",", ":")
        )
        + END,
    }[echo]
    sinks = [tmp_path / name for name in ("home", "tmp", "dspy-cache", "dspx-cache")]
    for path in sinks:
        path.mkdir()
    for key, value in zip(("HOME", "TMPDIR", "DSPY_CACHEDIR", "DSPX_CACHE_DIR"), sinks):
        monkeypatch.setenv(key, str(value))
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{tmp_path / 'mlflow.db'}")
    monkeypatch.setenv("DSPX_ORACLE_INDEX_PATH", str(tmp_path / "oracle.db"))
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE", "1")
    streams: list[tuple[object, ...]] = []
    popen = subprocess.Popen

    def spawn_spy(*args: Any, **kwargs: Any) -> Any:
        streams.append(tuple(kwargs.get(key) for key in ("stdin", "stdout", "stderr")))
        return popen(*args, **kwargs)

    def no_parent_program(*args: object, **kwargs: object) -> None:
        raise AssertionError("parent loaded the generated program (trace source)")

    monkeypatch.setattr(subprocess, "Popen", spawn_spy)
    monkeypatch.setattr(episode, "_generated_program_module", no_parent_program)
    completion = "[[ ## reasoning ## ]]\n" + echoed + "\n" + _ANSWER
    with _route_fds(root) as fds:
        prepared = _prepare_route(fds, use_cot=True)
        request = _admitted_request(fds, prepared, route=route, completion=completion)
        with pytest.raises(ImageContractError) as caught:
            _execute_route(root, request, route=route)
        wire = _records(fds["wire"])
        names = set(list_root(fds["custody"]))
        terminal = parse_json(read_record(fds["custody"], "terminal-1.json"))
        assert list_root(fds["artifacts"]) == []
    assert str(caught.value) == caught.value.code
    assert caught.value.code in {"image_privacy", "image_finalization"}
    assert caught.value.__cause__ is None and caught.value.__suppress_context__
    # The worker's streams are /dev/null; the parent's own streams stay payload-free.
    assert streams and set(streams) == {(subprocess.DEVNULL,) * 3}
    out, err = capfd.readouterr()
    assert not [
        text for text in (out, err) for needle in (echoed, uri) if needle in text
    ]
    assert [row["image_sha256"] for row in wire] == [[sha(pixels)]]
    # Only a payload-free digest, length and outcome of the echo remain.
    body = json.dumps(
        {
            "model": "synthetic-vision-fixture",
            "choices": [{"message": {"role": "assistant", "content": completion}}],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    assert {"ready.json", "intent-1.json", "terminal-1.json"} <= names
    assert "closure.json" not in names
    assert (
        terminal["provider_disposition"],
        terminal["failure_code"],
        terminal["dispatch_count"],
        terminal["typed_finalization_completed"],
        terminal["response_sha256"],
        terminal["response_byte_count"],
    ) == ("completed_failure", "privacy", 1, False, sha(body), len(body))
    scanned = [*(root / name for name in (*_PRIVATE_ROOTS, "candidate")), *sinks]
    assert _payload_free(scanned, pixels) == []
    assert (
        not (tmp_path / "oracle.db").exists() and not (tmp_path / "mlflow.db").exists()
    )

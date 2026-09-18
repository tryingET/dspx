"""Actual generated DSPy + native runtime, injected StubProvider transport only."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from dspx.services.program_reading_contracts import (
    canonical_bytes,
    identity,
    raw_hash,
    strict_json,
)
from dspx.services.program_reading_receipts import capture, consume_reading_receipt
from dspx.services.program_reading_runtime import (
    materialize_reading_candidate,
    run_reading_producer,
)
import reading_suite_posture as posture
from test_program_reading_contracts import (
    FIXTURES,
    reading_test_environment as reading_test_environment,
    make_inputs,
    missing_transport,
    malformed_transport,
    no_fit_transport,
    review_invalid_transport,
    forged_proposal_transport,
    rebind_inputs,
    transport,
)

reading_suite_posture = posture.reading_suite_posture


@pytest.fixture(scope="module")
def candidates(tmp_path_factory, reading_suite_posture):
    root = tmp_path_factory.mktemp("reading-candidates")
    results = {}
    for stage, filename in [
        ("reading", "reading_intent.yaml"),
        ("proposal", "reading_proposal_intent.yaml"),
    ]:
        results[stage] = materialize_reading_candidate(
            intent_path=FIXTURES / filename, candidate_root=root / stage, stage=stage
        )
    return results


@pytest.fixture
def run_factory(candidates, tmp_path):
    def run(
        stage="reading",
        purpose_index=0,
        request_id="synthetic",
        current=None,
        mode="puzzle",
        transport_fn=transport,
        previous=None,
        linkage=None,
    ):
        candidate = candidates[stage]
        inputs, expected, intent = make_inputs(
            stage=stage,
            candidate_hash=candidate["candidate_manifest_sha256"],
            purpose_index=purpose_index,
            request_id=request_id,
            mode=mode,
            previous=previous,
            revision=previous["revision"] + 1 if previous else 1,
        )
        if linkage is not None:
            intent["candidate_provenance"] = linkage
            intent["candidate_puzzle_ids"] = linkage["candidate_puzzle_ids"]
            expected = rebind_inputs(inputs, expected, intent)
        callback = (
            current if current is not None else ((lambda: intent) if intent else None)
        )
        result = run_reading_producer(
            manifest_path=candidate["manifest_path"],
            requests_root=tmp_path,
            expected=expected,
            inputs=inputs,
            synthetic_transport=transport_fn,
            current_intent=callback,
        )
        return result, inputs, expected, intent, callback

    return run


@pytest.fixture
def executed(run_factory, candidates):
    result, inputs, expected, intent, callback = run_factory()
    return {
        "result": result,
        "inputs": inputs,
        "expected": expected,
        "intent": intent,
        "callback": callback,
        "manifest_path": candidates["reading"]["manifest_path"],
    }


def consume(executed, **overrides):
    result = executed["result"]
    # Deliberately heterogeneous: adversarial callers override fields with invalid types.
    arguments: dict[str, Any] = dict(
        root=result["root"],
        trusted_receipt_sha256=result["receipt_sha256"],
        manifest_path=executed["manifest_path"],
        expected=executed["expected"],
        inputs=executed["inputs"],
        expected_native_episode_id=result["native_episode_id"],
        expected_native_index=0,
        current_intent=executed["callback"],
    )
    arguments.update(overrides)
    return consume_reading_receipt(**arguments)


def test_review_hold_unchecked_bytecode_never_executes(
    candidates, run_factory, tmp_path
):
    import importlib.util
    import py_compile
    from dspx.services.program_reading_runtime import capture_candidate

    manifest = candidates["reading"]["manifest_path"]
    module = manifest.parent / "module.py"
    before = capture_candidate(manifest)
    sentinel = tmp_path / "unchecked-bytecode-sentinel"
    injected = tmp_path / "injected_module.py"
    injected.write_text(
        module.read_text()
        + "\nopen("
        + repr(str(sentinel))
        + ", 'w').write('unchecked bytecode executed')\n"
    )
    cache = Path(importlib.util.cache_from_source(str(module)))
    cache.parent.mkdir(exist_ok=True)
    previous = cache.read_bytes() if cache.exists() else None
    py_compile.compile(
        str(injected),
        cfile=str(cache),
        dfile=str(module),
        invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
        doraise=True,
    )
    try:
        result, _, _, _, _ = run_factory(request_id="bytecode-hold")
        assert result["status"] == "local_synthetic_execution_only"
        assert not sentinel.exists()
        assert capture_candidate(manifest) == before
        episode = strict_json(capture(result["root"], "runtime_episode.json"))
        assert episode["candidate_manifest_path"] == str(manifest)
    finally:
        if previous is None:
            cache.unlink()
        else:
            cache.write_bytes(previous)


@pytest.mark.parametrize(
    "route",
    [
        "package",
        "namespace",
        "nested_pyc",
        "resolved_alias",
        "sys_path_descendant",
        "sys_path_alias",
        "cwd_path",
    ],
)
def test_source_loader_excludes_nested_candidate_paths(tmp_path, monkeypatch, route):
    """Focused import boundary probe, not an arbitrary-code/OS sandbox claim."""
    import importlib
    import py_compile
    import sys
    from dspx.services.program_reading_runtime import _CapturedLoader

    root = tmp_path / "candidate"
    nested = root / "nested"
    nested.mkdir(parents=True)
    external = tmp_path / "external"
    external.mkdir()
    name = "ak5456_import_" + route
    package = external / name
    package.mkdir()
    if route != "namespace":
        (package / "__init__.py").write_text("ALLOWED = True\n")
    (package / "safe.py").write_text("ALLOWED = True\n")
    sentinel = tmp_path / "undeclared-import-sentinel"
    payload = "open(" + repr(str(sentinel)) + ", 'w').write('undeclared executed')\n"
    (nested / "unsafe.py").write_text(payload)
    if route == "nested_pyc":
        py_compile.compile(
            str(nested / "unsafe.py"),
            cfile=str(nested / "unsafe.pyc"),
            invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
            doraise=True,
        )
        (nested / "unsafe.py").unlink()
    alias = tmp_path / "alias"
    alias.symlink_to(nested, target_is_directory=True)
    # Use a real generated-module name only for the loader's explicit exception.
    finder = _CapturedLoader({"program": "CAPTURED = True\n"}, root)
    monkeypatch.setattr(sys, "meta_path", [finder, *sys.meta_path])
    monkeypatch.syspath_prepend(str(external))
    monkeypatch.syspath_prepend(str(root))  # Exactly what native import does.
    parent = importlib.import_module(name)
    assert importlib.import_module(name + ".safe").ALLOWED is True
    try:
        if route.startswith("sys_path") or route == "cwd_path":
            entry = alias if route == "sys_path_alias" else nested
            if route == "cwd_path":
                monkeypatch.chdir(nested)
                entry = ""
            monkeypatch.syspath_prepend(str(entry))
            target = "unsafe"
        else:
            parent.__path__.append(str(alias if route == "resolved_alias" else nested))
            target = name + ".unsafe"
        importlib.invalidate_caches()
        with pytest.raises(ImportError):
            importlib.import_module(target)
        assert not sentinel.exists()
        assert str(root) not in sys.path
        assert finder.find_spec("program") is not None
    finally:
        for key in [name, name + ".safe", name + ".unsafe", "unsafe"]:
            sys.modules.pop(key, None)


def test_proposal_runtime_rejects_forged_authority_and_accepts_no_fit(
    run_factory, candidates, tmp_path
):
    with pytest.raises(ValueError):
        run_factory(
            stage="proposal",
            request_id="forged-proposal",
            transport_fn=forged_proposal_transport,
        )
    failed = list(tmp_path.glob("*/runtime"))
    assert len(failed) == 1
    episode = strict_json(capture(failed[0], "runtime_episode.json"))
    assert episode["execution_status"] == "executed"
    assert not (failed[0] / "reading_receipt.json").exists()
    result, inputs, expected, _, _ = run_factory(
        stage="proposal", request_id="valid-no-fit", transport_fn=no_fit_transport
    )
    outputs = consume_reading_receipt(
        root=result["root"],
        trusted_receipt_sha256=result["receipt_sha256"],
        manifest_path=candidates["proposal"]["manifest_path"],
        expected=expected,
        inputs=inputs,
        expected_native_episode_id=result["native_episode_id"],
        expected_native_index=0,
        current_intent=None,
    )
    assert outputs["reading_proposal_json"]["disposition"] == "no_match"


def test_original_reviewer_probes(candidates, tmp_path, monkeypatch):
    """Optional exact reviewer script, retargeted only to fresh synthetic scratch."""
    import importlib
    import os

    path = os.environ.get("AK5456_REVIEW_PROBES")
    if not path:
        pytest.skip("independent reviewer script not supplied")
    monkeypatch.syspath_prepend(str(Path(path).parent))
    probes = importlib.import_module(Path(path).stem)
    monkeypatch.setattr(probes, "BASE", tmp_path)
    monkeypatch.setattr(probes, "MANIFEST", candidates["reading"]["manifest_path"])
    (tmp_path / "probes").mkdir()
    with pytest.raises(ValueError):
        probes.test_invalid_packet_is_receipted_and_consumed()
    invalid = list((tmp_path / "probes/invalid-packet-v2").glob("*/runtime"))
    assert len(invalid) == 1 and (invalid[0] / "runtime_episode.json").exists()
    assert not (invalid[0] / "reading_receipt.json").exists()
    with pytest.raises(FileNotFoundError) as error:
        probes.test_undeclared_bytecode_executes_despite_source_capture()
    sentinel = tmp_path / "probes/undeclared-bytecode-sentinel.txt"
    assert error.value.filename == str(sentinel) and not sentinel.exists()
    receipts = list(
        (tmp_path / "probes/cached-code-v2").glob("*/runtime/reading_receipt.json")
    )
    assert (
        len(receipts) == 1
    )  # The original probe reached its sentinel assertion after consumption.


def test_review_hold_draft_rejected_after_real_execution(run_factory, tmp_path):
    with pytest.raises(ValueError):
        run_factory(request_id="invalid-draft", transport_fn=review_invalid_transport)
    roots = list(tmp_path.glob("*/runtime"))
    assert len(roots) == 1 and (roots[0] / "runtime_episode.json").exists()
    assert not (roots[0] / "reading_receipt.json").exists()


def test_actual_runtime_and_nonfocused_descriptors(executed):
    outputs = consume(executed)
    root = executed["result"]["root"]
    calls = strict_json(capture(root, "synthetic_requests.json"))
    assert len(calls) == 1
    assert executed["intent"]["reader_purpose"] in calls[0]["messages"][-1]["text"]
    module = capture(executed["manifest_path"].parent, "module.py").decode()
    signature = capture(executed["manifest_path"].parent, "signature.py").decode()
    assert "dspy.Predict" in module or "dspy.ChainOfThought" in module
    assert "FULL Obsidian" in signature
    assert "whole_synthesis" in outputs["distillation_frames_json"]["rows"][0]
    episode = strict_json(capture(root, "runtime_episode.json"))
    assert episode["provider"]["effect_evidence"]["attempt_total"] == 1
    assert (root / "oracle_evidence.json").is_file()
    assert not (root / "oracle").exists()
    workflow = strict_json(capture(root, "synthetic_workflow.json"))
    assert workflow["oracle_index_path"] is None
    assert workflow["oracle_semantic_path"] is None
    assert workflow["publication_preflight_path"] is None


def test_proposal_owner_review_a_b_flow(run_factory, candidates):
    proposal, pi, pe, _, _ = run_factory(stage="proposal", request_id="proposal")
    values = consume_reading_receipt(
        root=proposal["root"],
        trusted_receipt_sha256=proposal["receipt_sha256"],
        manifest_path=candidates["proposal"]["manifest_path"],
        expected=pe,
        inputs=pi,
        expected_native_episode_id=proposal["native_episode_id"],
        expected_native_index=0,
        current_intent=None,
    )
    linkage = values["reading_proposal_json"]["later_puzzle_linkage"]
    a, ai, ae, intent_a, ca = run_factory(
        request_id="owner-reviewed-A", linkage=linkage
    )
    b, bi, be, intent_b, cb = run_factory(
        request_id="owner-reviewed-B",
        purpose_index=1,
        previous=intent_a,
        linkage=linkage,
    )
    assert intent_b["supersedes"] == identity(intent_a)
    assert ai["marker_markdown"] == bi["marker_markdown"]
    assert ae.source_sha256 == be.source_sha256
    observed = []
    for result, inputs, expected, callback in [(a, ai, ae, ca), (b, bi, be, cb)]:
        value = consume_reading_receipt(
            root=result["root"],
            trusted_receipt_sha256=result["receipt_sha256"],
            manifest_path=candidates["reading"]["manifest_path"],
            expected=expected,
            inputs=inputs,
            expected_native_episode_id=result["native_episode_id"],
            expected_native_index=0,
            current_intent=callback,
        )
        observed.append(value)
    af = observed[0]["distillation_frames_json"]["rows"][0]
    bf = observed[1]["distillation_frames_json"]["rows"][0]
    assert af["whole_map"] == bf["whole_map"]
    assert af["selected_parts"] != bf["selected_parts"]
    assert af["evidence"]["excerpt_sha256"] != bf["evidence"]["excerpt_sha256"]
    assert af["whole_synthesis"] != bf["whole_synthesis"]
    assert (
        "infiltration" in af["whole_synthesis"]
        and "temperature" in bf["whole_synthesis"]
    )
    assert capture(a["root"], "synthetic_requests.json") != capture(
        b["root"], "synthetic_requests.json"
    )
    assert a["native_episode_id"] != b["native_episode_id"]
    assert (
        capture(a["root"].parent, "working_reading_intent.json")
        == canonical_bytes(intent_a) + b"\n"
    )


@pytest.mark.parametrize("mode", ["defer", "source_only"])
def test_modes_zero_calls(candidates, tmp_path, mode):
    inputs, expected, intent = make_inputs(
        mode=mode, candidate_hash=candidates["reading"]["candidate_manifest_sha256"]
    )
    result = run_reading_producer(
        manifest_path=candidates["reading"]["manifest_path"],
        requests_root=tmp_path,
        expected=expected,
        inputs=inputs,
        synthetic_transport=transport,
        current_intent=lambda: intent,
    )
    assert result == {"status": "blocked_mode", "transport_calls": 0}
    assert list(tmp_path.iterdir()) == []


def test_no_fit_proposal_actual_runtime(run_factory):
    result, _, _, _, _ = run_factory(
        stage="proposal", request_id="no-fit", transport_fn=no_fit_transport
    )
    output = strict_json(capture(result["root"], "reading_proposal_json"))
    assert output["disposition"] == "no_match"
    assert output["later_puzzle_linkage"]["candidate_puzzle_ids"] == []
    assert output["reading_intent_binding"] is None


def test_direct_null_puzzle(run_factory):
    result, _, _, intent, _ = run_factory(mode="wiki_atlas_direct")
    assert intent["selected_puzzle_id"] is None and intent["exception_reason"]
    assert result["status"] == "local_synthetic_execution_only"


@pytest.mark.parametrize(
    "defect", ["input", "source", "candidate", "binding", "request"]
)
def test_bad_input_zero_calls(candidates, tmp_path, defect):
    candidate = candidates["reading"]
    inputs, expected, intent = make_inputs(
        candidate_hash=candidate["candidate_manifest_sha256"]
    )
    fields = {
        "input": "input_raw_sha256",
        "source": "source_sha256",
        "candidate": "candidate_manifest_sha256",
        "binding": "reading_intent_binding",
        "request": "request_id",
    }
    expected = replace(
        expected, **{fields[defect]: {} if defect == "binding" else "wrong"}
    )
    with pytest.raises(ValueError):
        run_reading_producer(
            manifest_path=candidate["manifest_path"],
            requests_root=tmp_path,
            expected=expected,
            inputs=inputs,
            synthetic_transport=transport,
            current_intent=lambda: intent,
        )
    assert list(tmp_path.iterdir()) == []


def test_stale_completion_retained_without_receipt(run_factory, tmp_path):
    _, _, intent = make_inputs()
    calls = 0

    def current():
        nonlocal calls
        calls += 1
        return intent if calls == 1 else {**intent, "revision": 2}

    with pytest.raises(ValueError, match="stale"):
        run_factory(current=current)
    roots = list(tmp_path.glob("*/runtime"))
    assert len(roots) == 1 and (roots[0] / "runtime_episode.json").exists()
    assert not (roots[0] / "reading_receipt.json").exists()


@pytest.mark.parametrize("response_transport", [missing_transport, malformed_transport])
def test_missing_adapter_families_retains_failure_no_retry(
    run_factory, tmp_path, response_transport
):
    with pytest.raises(ValueError):
        run_factory(transport_fn=response_transport)
    roots = list(tmp_path.glob("*/runtime"))
    assert len(roots) == 1
    assert len(strict_json(capture(roots[0], "synthetic_requests.json"))) == 1
    assert not (roots[0] / "reading_receipt.json").exists()
    episode = strict_json(capture(roots[0], "runtime_episode.json"))
    assert episode["provider"]["effect_evidence"]["attempt_total"] == 1
    assert not (roots[0] / "synthetic_retry_rejected.json").exists()
    with pytest.raises(FileExistsError):
        run_factory(transport_fn=response_transport)


def test_repeated_request_is_immutable(executed, tmp_path):
    root = executed["result"]["root"]
    before = capture(root, "reading_receipt.json")
    with pytest.raises(FileExistsError):
        run_reading_producer(
            manifest_path=executed["manifest_path"],
            requests_root=tmp_path,
            expected=executed["expected"],
            inputs=executed["inputs"],
            synthetic_transport=transport,
            current_intent=executed["callback"],
        )
    assert capture(root, "reading_receipt.json") == before


@pytest.mark.parametrize(
    "key,value",
    [
        ("DSPX_PROVIDER", "openai-compatible"),
        ("DSPX_CUSTODY", "x"),
        ("DSPX_CONFIG", "private-config-not-opened"),
        ("DSPX_FALLBACK", "stub"),
        ("DSPX_ACTIVATION", "1"),
        ("DSPX_REPLAY_FIXTURE_JSON", "{}"),
    ],
)
def test_ambient_nonstub_rejected_before_create(monkeypatch, tmp_path, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(ValueError, match="environment|ambient"):
        materialize_reading_candidate(
            intent_path=Path("/not-opened"),
            candidate_root=tmp_path / "candidate",
            stage="reading",
        )
    assert list(tmp_path.iterdir()) == []


def test_canonical_sentinel_unchanged(run_factory, tmp_path):
    sentinel = tmp_path / "canonical-sentinel.md"
    sentinel.write_text("Canonical owner state must not change.\n")
    before = raw_hash(sentinel.read_bytes())
    run_factory(request_id="sentinel-test")
    assert raw_hash(sentinel.read_bytes()) == before

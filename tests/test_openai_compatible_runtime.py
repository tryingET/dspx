# summary: "Tests OpenAI-compatible runtime evidence, compatibility, integrity, and lifecycle."
# read_when:
#   - "Changing OpenAI-compatible runtime episode or receipt evidence."

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Iterator

import dspy
import httpx
import pytest

from dspx.cache import make_key
import dspx.openai_compatible_provider as openai_provider
from dspx.run_receipts import build_execution_replay_policy
from dspx.services.program_intent import ProgramIntent
import dspx.services.program_runtime_episode as runtime_episode_module
from dspx.services.program_runtime_episode import (
    _validate_provider_evidence,
    load_validated_program_runtime_episode_bundle,
    run_program_runtime_episode,
)
from dspx.services.program_service import materialize_program_from_intent
from dspx.services.run_replay_service import check_run_receipt, execute_run_receipt
from test_program_execution_replay import _openai_runtime, _single_runtime
import dspx.provider_runtime as provider_runtime_module


@pytest.fixture
def replay_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    values = {
        "DSPX_PROVIDER": "stub",
        "DSPX_REPLAY_FIXTURE_JSON": json.dumps(
            {
                "reasoning": "bounded",
                "urgency": "high",
                "route": "support",
                "response": "bounded response",
            }
        ),
        "DSPX_CACHE_ENABLE": "0",
        "DSPX_CACHE_DIR": str(tmp_path / "cache"),
        "MLFLOW_ENABLE": "0",
        "DSPX_ORACLE_EMBEDDING_BACKEND": "mock",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    yield


def _load_runtime_bundle(candidate: Path, runtime: Path) -> None:
    manifest_path = candidate / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    load_validated_program_runtime_episode_bundle(
        runtime_episode_path=runtime / "runtime_episode.json",
        expected_manifest_path=manifest_path,
        expected_manifest=manifest,
        expected_manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    )


def test_runtime_redacts_provider_controlled_mismatched_model_everywhere(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    replay_env: None,
) -> None:
    candidate, runtime, requests = _openai_runtime(
        tmp_path, monkeypatch, outcome="model_mismatch"
    )
    assert len(requests) == 1
    for path in (
        runtime / "behavior_results.json",
        runtime / "runtime_episode.json",
        runtime / "runtime_episode.json.meta.json",
    ):
        assert "secret-value" not in path.read_text()
    behavior = json.loads((runtime / "behavior_results.json").read_text())
    attempt = behavior["provider"]["effect_evidence"]["attempts"][0]
    assert attempt["observed_model"] is None
    assert behavior["examples"][0]["error"]["code"] == "completed_failure"
    _load_runtime_bundle(candidate, runtime)


@pytest.mark.parametrize(
    "field,value",
    [
        ("DSPX_OPENAI_COMPAT_MODEL", None),
        ("DSPX_OPENAI_COMPAT_API_BASE", "http://example.com/v1"),
        ("DSPX_OPENAI_COMPAT_TIMEOUT", "not-a-timeout"),
    ],
)
def test_unavailable_provider_still_emits_bounded_failure_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    replay_env: None,
    field: str,
    value: str | None,
) -> None:
    candidate, _, _ = _single_runtime(tmp_path, capture_replay_fixture=False)
    monkeypatch.setenv("DSPX_PROVIDER", "openai-compatible")
    monkeypatch.setenv("DSPX_OPENAI_COMPAT_MODEL", "local-model")
    monkeypatch.setenv("DSPX_OPENAI_COMPAT_API_BASE", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("DSPX_OPENAI_COMPAT_TIMEOUT", "10")
    if value is None:
        monkeypatch.delenv(field, raising=False)
    else:
        monkeypatch.setenv(field, value)
    runtime = tmp_path / f"runtime-unavailable-{field.lower()}"
    run_program_runtime_episode(
        manifest_path=candidate / "manifest.json",
        inputs_path=tmp_path / "inputs.json",
        outdir=runtime,
        skip_oracle_index=True,
    )
    receipt = json.loads((runtime / "runtime_episode.json.meta.json").read_text())
    assert receipt["provider"] == "unavailable"
    assert receipt["provider_details"] == {
        "provider": "unavailable",
        "provider_family": "unavailable",
        "model": None,
        "effect_contract": "dspx-provider-effect-v1",
        "runtime": {"configuration_status": "unavailable"},
    }
    assert receipt["execution_replay"]["supported"] is False
    assert "unsupported_provider" in receipt["execution_replay"]["unsupported_reasons"]
    _load_runtime_bundle(candidate, runtime)


def test_runtime_closes_openai_provider_after_success_and_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    replay_env: None,
) -> None:
    closed: list[object] = []
    previous_lm = getattr(dspy.settings, "lm", None)
    original = openai_provider.OpenAICompatibleProvider.close

    def close(provider: object) -> None:
        closed.append(provider)
        original(provider)  # type: ignore[arg-type]

    monkeypatch.setattr(openai_provider.OpenAICompatibleProvider, "close", close)
    success_root = tmp_path / "success"
    failure_root = tmp_path / "failure"
    success_root.mkdir()
    failure_root.mkdir()
    _openai_runtime(success_root, monkeypatch, outcome="success")
    _openai_runtime(failure_root, monkeypatch, outcome="completed_failure")
    assert len(closed) == 2
    assert getattr(dspy.settings, "lm", None) is previous_lm


def test_runtime_validator_rejects_corrupted_receipt_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    replay_env: None,
) -> None:
    candidate, runtime, _ = _openai_runtime(tmp_path, monkeypatch, outcome="success")
    receipt_path = runtime / "runtime_episode.json.meta.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["hash"] = "0" * 64
    receipt_path.write_text(json.dumps(receipt, sort_keys=True) + "\n")
    with pytest.raises(ValueError, match="receipt must pass replay validation"):
        _load_runtime_bundle(candidate, runtime)


def test_runtime_validator_rejects_receipt_symlink_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    replay_env: None,
) -> None:
    candidate, runtime, _ = _openai_runtime(tmp_path, monkeypatch, outcome="success")
    receipt_path = runtime / "runtime_episode.json.meta.json"
    escaped = tmp_path / "escaped-receipt.json"
    receipt_path.replace(escaped)
    receipt_path.symlink_to(escaped)
    with pytest.raises(ValueError, match="receipt path escapes"):
        _load_runtime_bundle(candidate, runtime)


def test_pre_ak4778_stub_runtime_remains_valid_and_replay_readable(
    tmp_path: Path,
    replay_env: None,
) -> None:
    candidate, runtime, receipt_path = _single_runtime(tmp_path)
    behavior_path = runtime / "behavior_results.json"
    behavior = json.loads(behavior_path.read_text())
    behavior["provider"] = {"status": "configured", "provider": "stub/echo"}
    behavior_path.write_text(json.dumps(behavior, sort_keys=True) + "\n")
    behavior_hash = hashlib.sha256(behavior_path.read_bytes()).hexdigest()

    traces_path = runtime / "program_runtime_traces.json"
    traces = json.loads(traces_path.read_text())
    for source in traces["sources"]:
        if source.get("path") == "behavior_results.json":
            source["content_hash"] = behavior_hash
    traces_path.write_text(json.dumps(traces, sort_keys=True) + "\n")
    traces_hash = hashlib.sha256(traces_path.read_bytes()).hexdigest()

    oracle_path = runtime / "oracle_evidence.json"
    oracle = json.loads(oracle_path.read_text())
    oracle["behavior"]["result_hash"] = behavior_hash
    for source in oracle["source_artifacts"]:
        if source.get("path") == "behavior_results.json":
            source["content_hash"] = behavior_hash
        elif source.get("path") == "program_runtime_traces.json":
            source["content_hash"] = traces_hash
    oracle_path.write_text(json.dumps(oracle, sort_keys=True) + "\n")
    oracle_hash = hashlib.sha256(oracle_path.read_bytes()).hexdigest()

    runtime_manifest_path = runtime / "manifest.json"
    runtime_manifest = json.loads(runtime_manifest_path.read_text())
    runtime_manifest["runtime_episode"]["behavior_results_sha256"] = behavior_hash
    runtime_manifest_path.write_text(
        json.dumps(runtime_manifest, sort_keys=True) + "\n"
    )

    episode_path = runtime / "runtime_episode.json"
    episode = json.loads(episode_path.read_text())
    episode.pop("provider")
    episode["artifact_hashes"].update(
        {
            "behavior_results_sha256": behavior_hash,
            "program_runtime_traces_sha256": traces_hash,
            "oracle_evidence_sha256": oracle_hash,
        }
    )
    episode_path.write_text(json.dumps(episode, sort_keys=True) + "\n")
    episode_hash = hashlib.sha256(episode_path.read_bytes()).hexdigest()

    receipt = json.loads(receipt_path.read_text())
    receipt["hash"] = episode_hash
    receipt["provider"] = "stub"
    receipt["provider_details"] = {
        "provider": "stub",
        "provider_family": "stub",
        "model": "stub/echo",
        "effect_contract": "dspx-provider-effect-v1",
    }
    receipt["run_summary"].pop("provider")
    receipt["run_summary"]["behavior_results_sha256"] = behavior_hash
    receipt["run_summary"]["program_runtime_traces_sha256"] = traces_hash
    receipt["run_summary"]["oracle_evidence_sha256"] = oracle_hash
    expected = receipt["replay_inputs"]["expected_episode"]
    expected["behavior_results_sha256"] = behavior_hash
    expected["program_runtime_traces_sha256"] = traces_hash
    expected["oracle_evidence_sha256"] = oracle_hash
    expected["runtime_episode_sha256"] = episode_hash
    receipt["cache_key"] = make_key(
        {"kind": "program-runtime", "replay_inputs": receipt["replay_inputs"]}
    )
    receipt["cache_file"] = str(
        runtime / ".cache" / "program-runtime" / f"{receipt['cache_key']}.json"
    )
    receipt["execution_replay"] = build_execution_replay_policy(
        run_kind="program-runtime",
        provider="stub",
        provider_details=receipt["provider_details"],
        replay_inputs=receipt["replay_inputs"],
        output_hash=episode_hash,
    )
    receipt_path.write_text(json.dumps(receipt, sort_keys=True) + "\n")

    receipt_check = check_run_receipt(receipt_path)
    assert receipt_check["status"] == "ok", json.dumps(receipt_check, sort_keys=True)
    assert receipt["execution_replay"]["supported"] is True
    _load_runtime_bundle(candidate, runtime)
    report = execute_run_receipt(receipt_path, Path("legacy-replay.json"))
    assert report["status"] == "executed", json.dumps(report, sort_keys=True)
    assert report["checks"]["legacy_behavior_normalized_match"] is True
    assert report["checks"]["legacy_runtime_traces_normalized_match"] is True
    assert report["checks"]["legacy_oracle_evidence_normalized_match"] is True


def test_runtime_provider_validator_rejects_events_after_indeterminate_and_bad_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    replay_env: None,
) -> None:
    _, runtime, _ = _openai_runtime(tmp_path, monkeypatch, outcome="indeterminate")
    provider = json.loads((runtime / "behavior_results.json").read_text())["provider"]
    evidence = provider["effect_evidence"]
    evidence["attempts"].append(
        {
            "provider_kind": "openai-compatible",
            "requested_model": "local-model",
            "observed_model": "local-model",
            "dispatch_count": 1,
            "effect_disposition": "completed_success",
        }
    )
    evidence["attempt_total"] = 2
    evidence["terminal_effect"] = "completed_success"
    with pytest.raises(ValueError, match="attempt fields"):
        _validate_provider_evidence(provider)

    evidence["attempts"] = evidence["attempts"][:1]
    evidence["terminal_effect"] = "effect_indeterminate"
    with pytest.raises(ValueError, match="attempt counts"):
        _validate_provider_evidence(provider)


@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), float("-inf")])
def test_runtime_provider_validator_rejects_nonfinite_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    replay_env: None,
    timeout: float,
) -> None:
    _, runtime, _ = _openai_runtime(tmp_path, monkeypatch, outcome="success")
    provider = json.loads((runtime / "behavior_results.json").read_text())["provider"]
    provider["metadata"]["runtime"]["effective_timeout"] = timeout
    with pytest.raises(ValueError, match="timeout"):
        _validate_provider_evidence(provider)


def _rebind_legacy_runtime(runtime: Path) -> Path:
    behavior_path = runtime / "behavior_results.json"
    behavior_hash = hashlib.sha256(behavior_path.read_bytes()).hexdigest()
    traces_path = runtime / "program_runtime_traces.json"
    traces = json.loads(traces_path.read_text())
    for source in traces["sources"]:
        if source.get("path") == "behavior_results.json":
            source["content_hash"] = behavior_hash
    traces_path.write_text(json.dumps(traces, sort_keys=True) + "\n")
    traces_hash = hashlib.sha256(traces_path.read_bytes()).hexdigest()

    oracle_path = runtime / "oracle_evidence.json"
    oracle = json.loads(oracle_path.read_text())
    oracle["behavior"]["result_hash"] = behavior_hash
    for source in oracle["source_artifacts"]:
        if source.get("path") == "behavior_results.json":
            source["content_hash"] = behavior_hash
        elif source.get("path") == "program_runtime_traces.json":
            source["content_hash"] = traces_hash
    oracle_path.write_text(json.dumps(oracle, sort_keys=True) + "\n")
    oracle_hash = hashlib.sha256(oracle_path.read_bytes()).hexdigest()

    runtime_manifest_path = runtime / "manifest.json"
    runtime_manifest = json.loads(runtime_manifest_path.read_text())
    runtime_manifest["runtime_episode"]["behavior_results_sha256"] = behavior_hash
    runtime_manifest_path.write_text(
        json.dumps(runtime_manifest, sort_keys=True) + "\n"
    )

    episode_path = runtime / "runtime_episode.json"
    episode = json.loads(episode_path.read_text())
    episode["artifact_hashes"].update(
        {
            "behavior_results_sha256": behavior_hash,
            "program_runtime_traces_sha256": traces_hash,
            "oracle_evidence_sha256": oracle_hash,
        }
    )
    episode_path.write_text(json.dumps(episode, sort_keys=True) + "\n")
    episode_hash = hashlib.sha256(episode_path.read_bytes()).hexdigest()

    receipt_path = runtime / "runtime_episode.json.meta.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["hash"] = episode_hash
    receipt["run_summary"]["behavior_results_sha256"] = behavior_hash
    receipt["run_summary"]["program_runtime_traces_sha256"] = traces_hash
    receipt["run_summary"]["oracle_evidence_sha256"] = oracle_hash
    expected = receipt["replay_inputs"]["expected_episode"]
    expected["behavior_results_sha256"] = behavior_hash
    expected["program_runtime_traces_sha256"] = traces_hash
    expected["oracle_evidence_sha256"] = oracle_hash
    expected["runtime_episode_sha256"] = episode_hash
    receipt["cache_key"] = make_key(
        {"kind": "program-runtime", "replay_inputs": receipt["replay_inputs"]}
    )
    receipt["cache_file"] = str(
        runtime / ".cache" / "program-runtime" / f"{receipt['cache_key']}.json"
    )
    receipt["execution_replay"] = build_execution_replay_policy(
        run_kind="program-runtime",
        provider="stub",
        provider_details=receipt["provider_details"],
        replay_inputs=receipt["replay_inputs"],
        output_hash=episode_hash,
    )
    receipt_path.write_text(json.dumps(receipt, sort_keys=True) + "\n")
    return receipt_path


def _legacy_runtime(tmp_path: Path) -> tuple[Path, Path, Path]:
    candidate, runtime, receipt_path = _single_runtime(tmp_path)
    behavior_path = runtime / "behavior_results.json"
    behavior = json.loads(behavior_path.read_text())
    behavior["provider"] = {"status": "configured", "provider": "stub/echo"}
    behavior_path.write_text(json.dumps(behavior, sort_keys=True) + "\n")
    episode_path = runtime / "runtime_episode.json"
    episode = json.loads(episode_path.read_text())
    episode.pop("provider")
    episode_path.write_text(json.dumps(episode, sort_keys=True) + "\n")
    receipt = json.loads(receipt_path.read_text())
    receipt["provider_details"] = {
        "provider": "stub",
        "provider_family": "stub",
        "model": "stub/echo",
        "effect_contract": "dspx-provider-effect-v1",
    }
    receipt["run_summary"].pop("provider")
    receipt_path.write_text(json.dumps(receipt, sort_keys=True) + "\n")
    return candidate, runtime, _rebind_legacy_runtime(runtime)


def test_legacy_runtime_rejects_coherently_drifted_receipt_provider_identity(
    tmp_path: Path,
    replay_env: None,
) -> None:
    candidate, runtime, receipt_path = _legacy_runtime(tmp_path)
    receipt = json.loads(receipt_path.read_text())
    receipt["provider"] = "coherently-drifted"
    receipt["provider_details"] = {
        "provider": "coherently-drifted",
        "provider_family": "coherently-drifted",
        "model": "drift/model",
        "effect_contract": "dspx-provider-effect-v1",
    }
    receipt["execution_replay"] = build_execution_replay_policy(
        run_kind="program-runtime",
        provider=receipt["provider"],
        provider_details=receipt["provider_details"],
        replay_inputs=receipt["replay_inputs"],
        output_hash=receipt["hash"],
    )
    receipt_path.write_text(json.dumps(receipt, sort_keys=True) + "\n")

    receipt_check = check_run_receipt(receipt_path)
    assert receipt_check["status"] == "ok", json.dumps(receipt_check, sort_keys=True)
    with pytest.raises(
        ValueError, match="legacy runtime receipt provider identity drifts"
    ):
        _load_runtime_bundle(candidate, runtime)


@pytest.mark.parametrize(
    "artifact,field,check",
    [
        (
            "behavior_results.json",
            "unrelated_behavior_drift",
            "legacy_behavior_normalized_match",
        ),
        (
            "program_runtime_traces.json",
            "unrelated_trace_drift",
            "legacy_runtime_traces_normalized_match",
        ),
        (
            "oracle_evidence.json",
            "unrelated_oracle_drift",
            "legacy_oracle_evidence_normalized_match",
        ),
    ],
)
def test_legacy_replay_rejects_unrelated_normalized_artifact_drift(
    tmp_path: Path,
    replay_env: None,
    artifact: str,
    field: str,
    check: str,
) -> None:
    _, runtime, _ = _legacy_runtime(tmp_path)
    path = runtime / artifact
    payload = json.loads(path.read_text())
    payload[field] = "must-not-normalize"
    path.write_text(json.dumps(payload, sort_keys=True) + "\n")
    receipt_path = _rebind_legacy_runtime(runtime)
    report = execute_run_receipt(receipt_path, Path(f"{field}.json"))
    assert report["status"] == "failed"
    assert report["checks"][check] is False


def test_legacy_runtime_rejects_receipt_hash_drift(
    tmp_path: Path,
    replay_env: None,
) -> None:
    candidate, runtime, receipt_path = _legacy_runtime(tmp_path)
    receipt = json.loads(receipt_path.read_text())
    receipt["hash"] = "0" * 64
    receipt_path.write_text(json.dumps(receipt, sort_keys=True) + "\n")
    with pytest.raises(ValueError, match="receipt must pass replay validation"):
        _load_runtime_bundle(candidate, runtime)


def test_legacy_runtime_rejects_receipt_symlink_escape(
    tmp_path: Path,
    replay_env: None,
) -> None:
    candidate, runtime, receipt_path = _legacy_runtime(tmp_path)
    escaped = tmp_path / "legacy-escaped-receipt.json"
    receipt_path.replace(escaped)
    receipt_path.symlink_to(escaped)
    with pytest.raises(ValueError, match="receipt path escapes"):
        _load_runtime_bundle(candidate, runtime)


@pytest.mark.parametrize("provider_name", ["stub", "openai-compatible"])
def test_generated_preflight_is_nested_effect_free_and_closes_runtime_lm(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider_name: str,
) -> None:
    candidate = tmp_path / "candidate"
    materialize_program_from_intent(
        ProgramIntent(
            name="PreflightProgram",
            objective="Check provider setup.",
            inputs=["text"],
            outputs=["answer"],
        ),
        outdir=candidate,
    )
    monkeypatch.setenv("DSPX_PROVIDER", f"  {provider_name.upper()}  ")
    requests: list[httpx.Request] = []
    closed: list[object] = []
    original_close = openai_provider.OpenAICompatibleProvider.close

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise AssertionError("preflight must not dispatch")

    def close(provider: object) -> None:
        closed.append(provider)
        original_close(provider)  # type: ignore[arg-type]

    if provider_name == "openai-compatible":
        monkeypatch.setenv("DSPX_OPENAI_COMPAT_MODEL", "local-model")
        monkeypatch.setenv("DSPX_OPENAI_COMPAT_API_BASE", "http://127.0.0.1:8000/v1")
        monkeypatch.setenv("DSPX_OPENAI_COMPAT_TIMEOUT", "10")
        monkeypatch.setattr(
            openai_provider,
            "_default_transport",
            lambda: httpx.MockTransport(handler),
        )
        monkeypatch.setattr(openai_provider.OpenAICompatibleProvider, "close", close)

    module_name = f"direct_preflight_{provider_name.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(
        module_name, candidate / "direct_run.py"
    )
    assert spec is not None and spec.loader is not None
    direct_run = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(direct_run)
    for name in ("program", "module", "signature"):
        sys.modules.pop(name, None)
    result = direct_run._preflight()
    metadata = result["provider"]["metadata"]
    evidence = result["provider"]["effect_evidence"]
    assert metadata["provider"] == provider_name
    assert evidence["attempt_total"] == 0
    assert evidence["attempts"] == []
    assert direct_run._RUNTIME_LM is None
    assert requests == []
    assert len(closed) == (1 if provider_name == "openai-compatible" else 0)


def test_runtime_metadata_failure_closes_partial_openai_and_restores_global_lm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DSPX_PROVIDER", "openai-compatible")
    monkeypatch.setenv("DSPX_OPENAI_COMPAT_MODEL", "local-model")
    monkeypatch.setenv("DSPX_OPENAI_COMPAT_API_BASE", "http://127.0.0.1:8000/v1")
    previous_lm = getattr(dspy.settings, "lm", None)
    closed: list[object] = []
    original_close = openai_provider.OpenAICompatibleProvider.close

    def close(provider: object) -> None:
        closed.append(provider)
        original_close(provider)  # type: ignore[arg-type]

    def fail_metadata(*args: object, **kwargs: object) -> dict[str, object]:
        del args, kwargs
        raise ValueError("metadata failure")

    monkeypatch.setattr(openai_provider.OpenAICompatibleProvider, "close", close)
    monkeypatch.setattr(
        provider_runtime_module, "provider_metadata_from_instance", fail_metadata
    )
    provider, adapter, restored_lm = runtime_episode_module._configure_provider()
    assert provider["status"] == "unavailable"
    assert adapter is None
    assert restored_lm is previous_lm
    assert len(closed) == 1
    assert getattr(dspy.settings, "lm", None) is previous_lm

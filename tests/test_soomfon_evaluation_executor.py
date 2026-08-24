from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
import dspx.openai_compatible_provider as openai_provider
from dspx.services import soomfon_evaluation_executor as executor
from dspx.services import soomfon_evaluation_custody as custody
from dspx.services import soomfon_evaluation_ledger as soomfon_ledger
from dspx.services import soomfon_evaluation_contract as contract_module
from dspx.services import program_runtime_episode as runtime_episode_module
from dspx.run_receipts import build_run_receipt, write_run_receipt
from dspx.services.run_replay_service import check_run_receipt
from dspx.services.program_runtime_episode import (
    load_validated_program_runtime_episode_bundle,
    run_program_runtime_episode,
)
from dspx.services.soomfon_evaluation_contract import (
    CONTRACT_RELATIVE_PATH,
    EXPECTED_INPUT_SHA256,
    EXPECTED_RECEIPT_SHA256,
    REQUIRED_ENVIRONMENT,
    SoomfonEvaluationContractError,
    build_sanitized_child_environment,
    classify_provider_disposition,
    load_hash_bound_soomfon_contract,
    validate_case_artifact_bindings,
    validate_exact_provider_environment,
    validate_exact_runtime_identity,
    validate_soomfon_contract,
)
from dspx.services.soomfon_evaluation_custody import SoomfonCustodyError
from test_program_execution_replay import _single_runtime


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_SHA256 = "a8afebcd131d59f1bf6794d7a4748906af3fc2a99c7230f7a1256d78bafe2b18"


def _patch_roots(monkeypatch: pytest.MonkeyPatch, state_root: Path) -> None:
    monkeypatch.setattr(executor, "_repo_root", lambda: REPO_ROOT)
    monkeypatch.setattr(executor, "default_state_root", lambda: state_root)


def _effect_behavior(
    disposition: str,
    *,
    dispatch_count: int,
    terminal_effect: str | None = None,
    truncated: bool = False,
) -> dict[str, Any]:
    return {
        "provider": {
            "metadata": {
                "provider": "openai-compatible",
                "model": "baseline-text",
                "runtime": {
                    "provider_kind": "openai-compatible",
                    "base_endpoint": "http://127.0.0.1:1234/v1",
                    "effective_timeout": 30.0,
                },
            },
            "effect_evidence": {
                "schema_version": "dspx-provider-effect-evidence-v1",
                "attempt_total": 1,
                "attempts_truncated": truncated,
                "terminal_effect": disposition
                if terminal_effect is None
                else terminal_effect,
                "attempts": [
                    {
                        "provider_kind": "openai-compatible",
                        "requested_model": "baseline-text",
                        "observed_model": "baseline-text",
                        "dispatch_count": dispatch_count,
                        "effect_disposition": disposition,
                    }
                ],
            },
        }
    }


def _write_mock_runtime_evidence(
    raw_root: Path,
    *,
    disposition: str = "completed_success",
    dispatch_count: int = 1,
) -> tuple[str, str, str, str]:
    runtime = raw_root / "runtime"
    runtime.mkdir(mode=0o700)
    behavior = _effect_behavior(disposition, dispatch_count=dispatch_count)
    output_files: list[str] = []
    if disposition == "completed_success":
        behavior["examples"] = [
            {"observed_outputs": {"response": "bounded mock response"}}
        ]
        output_files = ["response"]
    artifacts = {
        "runtime_inputs.json": b"{}\n",
        "behavior_results.json": (json.dumps(behavior, sort_keys=True) + "\n").encode(),
        "program_runtime_traces.json": b"{}\n",
        "oracle_evidence.json": b"{}\n",
        "manifest.json": b"{}\n",
    }
    artifact_hashes = {
        key.replace(".json", "_sha256"): hashlib.sha256(raw).hexdigest()
        for key, raw in artifacts.items()
        if key != "manifest.json"
    }
    runtime_episode = (
        json.dumps(
            {
                "execution_status": "executed",
                "output_files": output_files,
                "artifact_hashes": artifact_hashes,
            },
            sort_keys=True,
        )
        + "\n"
    ).encode()
    artifacts["runtime_episode.json"] = runtime_episode
    if output_files:
        artifacts["response"] = b"bounded mock response\n"
    for name, raw in artifacts.items():
        path = runtime / name
        path.write_bytes(raw)
        path.chmod(0o600)
    behavior_results = artifacts["behavior_results.json"]
    runtime_sha256 = hashlib.sha256(runtime_episode).hexdigest()
    receipt = build_run_receipt(
        run_kind="program-runtime",
        output_path=runtime / "runtime_episode.json",
        output_hash=runtime_sha256,
        template_version=None,
        cache_key="mock-cache-key",
        cache_file=str(runtime / "mock-cache.json"),
        cache_enabled=False,
        provider_details_override={
            "provider": "openai-compatible",
            "provider_family": "openai-compatible",
            "model": "baseline-text",
            "effect_contract": "dspx-provider-effect-v1",
            "runtime": {
                "provider_kind": "openai-compatible",
                "base_endpoint": "http://127.0.0.1:1234/v1",
                "effective_timeout": 30.0,
            },
        },
        replay_inputs={
            "candidate_manifest_path": "manifest.json",
            "candidate_manifest_sha256": "a" * 64,
            "candidate_receipt_path": "manifest.json.meta.json",
            "candidate_receipt_sha256": "b" * 64,
            "runtime_inputs_sha256": "c" * 64,
            "replay_fixture_path": None,
            "replay_fixture_sha256": None,
            "contract_mode": "none",
            "skip_oracle_index": True,
            "publication_preflight_requested": False,
            "expected_episode": {},
        },
        capture_context=False,
    )
    receipt_path = write_run_receipt(runtime / "runtime_episode.json", receipt)
    expected_key = check_run_receipt(receipt_path)["expected_cache_key"]
    receipt["cache_key"] = expected_key
    receipt["cache_file"] = str(
        runtime / ".cache" / "program-runtime" / f"{expected_key}.json"
    )
    receipt_path = write_run_receipt(runtime / "runtime_episode.json", receipt)
    receipt_path.chmod(0o600)
    runtime_fd = os.open(runtime, os.O_RDONLY | os.O_DIRECTORY)
    try:
        tree_sha256 = soomfon_ledger.private_runtime_tree_sha256(runtime_fd)
    finally:
        os.close(runtime_fd)
    return (
        runtime_sha256,
        tree_sha256,
        hashlib.sha256(behavior_results).hexdigest(),
        hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
    )


def test_hash_bound_loader_validates_before_parse(tmp_path: Path) -> None:
    contract_path = tmp_path / CONTRACT_RELATIVE_PATH
    contract_path.parent.mkdir(parents=True)
    contract_path.write_bytes(b"not-json")
    with pytest.raises(SoomfonEvaluationContractError, match="does not match"):
        load_hash_bound_soomfon_contract(
            repo_root=tmp_path,
            expected_sha256=CONTRACT_SHA256,
        )


def test_frozen_contract_and_case_artifacts_validate() -> None:
    contract, observed, path = load_hash_bound_soomfon_contract(
        repo_root=REPO_ROOT,
        expected_sha256=CONTRACT_SHA256,
    )
    assert observed == CONTRACT_SHA256
    assert path == REPO_ROOT / CONTRACT_RELATIVE_PATH
    cases = validate_case_artifact_bindings(repo_root=REPO_ROOT, contract=contract)
    assert [case["mode"] for case in cases] == [
        "simple",
        "elaborate",
        "researched",
        "deep-research",
        "socratic",
        "bloom",
    ]
    for case in cases:
        payload = {
            "inputs": {
                "transcription": case["transcription"],
                "persona_intent": case["persona_intent"],
            }
        }
        raw = (
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        ).encode()
        assert hashlib.sha256(raw).hexdigest() == EXPECTED_INPUT_SHA256[case["mode"]]
        assert case["manifest_receipt_sha256"] == EXPECTED_RECEIPT_SHA256[case["mode"]]


def test_all_successor_candidate_sources_pass_unchanged_snapshot_policy() -> None:
    contract, _, _ = load_hash_bound_soomfon_contract(
        repo_root=REPO_ROOT,
        expected_sha256=CONTRACT_SHA256,
    )
    cases = validate_case_artifact_bindings(repo_root=REPO_ROOT, contract=contract)
    for case in cases:
        candidate_root = case["manifest_path"].parent
        runtime_episode_module.validate_generated_program_snapshot_sources(
            {
                name: (candidate_root / f"{name}.py").read_text(encoding="utf-8")
                for name in ("program", "module", "signature")
            }
        )


@pytest.mark.parametrize(
    "manifest_relative",
    [
        "examples/voice_turn_brains/canaries/dspy-3.3.0/simple/candidate/manifest.json",
        "examples/voice_turn_brains/canaries/dspy-3.3.0/successors/AK-4971/simple/candidate/manifest.json",
    ],
)
def test_generic_program_runtime_refuses_protected_manifest(
    tmp_path: Path, manifest_relative: str
) -> None:
    manifest = REPO_ROOT / manifest_relative
    with pytest.raises(SoomfonCustodyError, match="requires executor custody"):
        run_program_runtime_episode(
            manifest_path=manifest,
            inputs_path=tmp_path / "missing-inputs.json",
            outdir=tmp_path / "runtime",
            skip_oracle_index=True,
        )


def test_direct_child_refuses_without_fixed_custody_fds(tmp_path: Path) -> None:
    manifest = (
        REPO_ROOT
        / "examples/voice_turn_brains/canaries/dspy-3.3.0/simple/candidate/manifest.json"
    )
    result = executor._child_main(
        [
            "--child",
            "--manifest",
            str(manifest),
            "--expected-manifest-sha256",
            "a" * 64,
            "--expected-receipt-sha256",
            "c" * 64,
            "--mode",
            "simple",
            "--contract-sha256",
            CONTRACT_SHA256,
            "--marker-fd",
            "-1",
            "--ledger-fd",
            "-1",
            "--lock-fd",
            "-1",
            "--raw-root-fd",
            "-1",
            "--cwd-fd",
            "-1",
            "--parent-pid",
            "1",
            "--inputs",
            str(tmp_path / "missing-inputs.json"),
            "--expected-inputs-sha256",
            "b" * 64,
            "--outdir",
            str(tmp_path / "runtime"),
        ]
    )
    assert result == 2
    assert not (tmp_path / "runtime").exists()


def test_contract_unknown_field_fails_closed_schema() -> None:
    payload = json.loads((REPO_ROOT / CONTRACT_RELATIVE_PATH).read_text())
    payload["unexpected"] = True
    with pytest.raises(SoomfonEvaluationContractError, match="schema is not exact"):
        validate_soomfon_contract(payload)


def test_alternate_self_consistent_contract_digest_is_rejected(tmp_path: Path) -> None:
    payload = json.loads((REPO_ROOT / CONTRACT_RELATIVE_PATH).read_text())
    payload["purpose"] = "alternate"
    raw = json.dumps(payload).encode()
    contract_path = tmp_path / CONTRACT_RELATIVE_PATH
    contract_path.parent.mkdir(parents=True)
    contract_path.write_bytes(raw)
    with pytest.raises(SoomfonEvaluationContractError, match="reviewed trust anchor"):
        load_hash_bound_soomfon_contract(
            repo_root=tmp_path,
            expected_sha256=hashlib.sha256(raw).hexdigest(),
        )


@pytest.mark.parametrize(
    "section",
    [
        "source_state",
        "runtime_target",
        "executor_contract",
        "effect_budget",
        "attempt_ledger",
        "retention",
        "rubric",
        "deep_research_disposition",
        "nonclaims",
    ],
)
def test_contract_nested_unknown_field_fails(section: str) -> None:
    payload = json.loads((REPO_ROOT / CONTRACT_RELATIVE_PATH).read_text())
    payload[section]["unexpected"] = True
    with pytest.raises(SoomfonEvaluationContractError, match="invalid"):
        validate_soomfon_contract(payload)


@pytest.mark.parametrize(
    "section",
    ["runtime_target", "executor_contract", "attempt_ledger", "retention", "rubric"],
)
def test_contract_nested_missing_field_fails(section: str) -> None:
    payload = json.loads((REPO_ROOT / CONTRACT_RELATIVE_PATH).read_text())
    payload[section].pop(next(iter(payload[section])))
    with pytest.raises(SoomfonEvaluationContractError, match="invalid"):
        validate_soomfon_contract(payload)


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (
            ("executor_contract", "required_environment", "DSPX_OPENAI_COMPAT_MODEL"),
            "other",
        ),
        (("retention", "raw_response_handling", "stdout_allowed"), True),
        (("effect_budget", "stop_on_first_non_success"), False),
        (("deep_research_disposition", "bounded_inline_corpus"), False),
        (("nonclaims", "routing"), True),
    ],
)
def test_contract_safety_value_drift_fails(
    path: tuple[str, ...], replacement: object
) -> None:
    payload = json.loads((REPO_ROOT / CONTRACT_RELATIVE_PATH).read_text())
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement
    with pytest.raises(SoomfonEvaluationContractError, match="invalid"):
        validate_soomfon_contract(payload)


def test_exact_runtime_identity_matches_frozen_environment() -> None:
    assert validate_exact_runtime_identity() == {
        "python": "3.13.12",
        "dspx-core": "0.2.1",
        "dspy": "3.3.1",
        "dspy-ai": "3.3.1",
        "gepa": "0.1.4",
    }


def test_runtime_identity_rejects_wrong_python(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(contract_module.platform, "python_version", lambda: "3.13.11")
    with pytest.raises(SoomfonEvaluationContractError, match="does not match"):
        validate_exact_runtime_identity()


def test_runtime_identity_rejects_wrong_distribution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_version = contract_module.version
    monkeypatch.setattr(
        contract_module,
        "version",
        lambda name: "0.1.5" if name == "gepa" else real_version(name),
    )
    with pytest.raises(SoomfonEvaluationContractError, match="does not match"):
        validate_exact_runtime_identity()


def test_case_artifact_manifest_hash_drift_fails() -> None:
    payload = json.loads((REPO_ROOT / CONTRACT_RELATIVE_PATH).read_text())
    payload["cases"][0]["manifest_sha256"] = "0" * 64
    with pytest.raises(SoomfonEvaluationContractError, match="artifact SHA-256"):
        validate_case_artifact_bindings(repo_root=REPO_ROOT, contract=payload)


def test_case_artifact_canary_index_hash_drift_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.loads((REPO_ROOT / CONTRACT_RELATIVE_PATH).read_text())
    stable_read = contract_module._read_stable_regular_file

    def drift_index(path: Path, *, max_bytes: int) -> bytes:
        raw = stable_read(path, max_bytes=max_bytes)
        return raw + b" " if path.name == "canary-index.json" else raw

    monkeypatch.setattr(contract_module, "_read_stable_regular_file", drift_index)
    with pytest.raises(SoomfonEvaluationContractError, match="artifact SHA-256"):
        validate_case_artifact_bindings(repo_root=REPO_ROOT, contract=payload)


def test_case_artifact_receipt_hash_drift_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.loads((REPO_ROOT / CONTRACT_RELATIVE_PATH).read_text())
    stable_read = contract_module._read_stable_regular_file

    def drift_receipt(path: Path, *, max_bytes: int) -> bytes:
        raw = stable_read(path, max_bytes=max_bytes)
        return raw + b" " if path.name.endswith(".meta.json") else raw

    monkeypatch.setattr(contract_module, "_read_stable_regular_file", drift_receipt)
    with pytest.raises(SoomfonEvaluationContractError, match="receipt SHA-256"):
        validate_case_artifact_bindings(repo_root=REPO_ROOT, contract=payload)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("DSPX_OPENAI_COMPAT_API_BASE", None),
        ("DSPX_OPENAI_COMPAT_API_BASE", "http://localhost:1234/v1"),
        ("DSPX_OPENAI_COMPAT_API_BASE", "http://[::1]:1234/v1"),
        ("DSPX_OPENAI_COMPAT_API_BASE", "http://127.0.0.1:9999/v1"),
        ("DSPX_OPENAI_COMPAT_API_BASE", "http://127.0.0.1:1234/"),
        ("DSPX_OPENAI_COMPAT_MODEL", "other-model"),
        ("DSPX_OPENAI_COMPAT_TIMEOUT", "30.0"),
        ("DSPX_POLICY_ALLOW_NETWORK_MUTATE", "0"),
    ],
)
def test_provider_environment_drift_fails(key: str, value: str | None) -> None:
    environment = dict(REQUIRED_ENVIRONMENT)
    if value is None:
        environment.pop(key)
    else:
        environment[key] = value
    with pytest.raises(SoomfonEvaluationContractError, match="does not match"):
        validate_exact_provider_environment(environment)


def test_credential_environment_fails() -> None:
    environment = {
        **REQUIRED_ENVIRONMENT,
        "DSPX_OPENAI_COMPAT_API_KEY": "forbidden",
    }
    with pytest.raises(SoomfonEvaluationContractError, match="credential"):
        validate_exact_provider_environment(environment)


def test_child_environment_is_allowlisted(tmp_path: Path) -> None:
    environment = {
        **REQUIRED_ENVIRONMENT,
        "OPENAI_API_KEY": "must-not-propagate",
        "UNRELATED": "must-not-propagate",
    }
    child = build_sanitized_child_environment(environment, private_tmp=tmp_path)
    assert child == {
        **REQUIRED_ENVIRONMENT,
        "TMPDIR": str(tmp_path),
        "NO_PROXY": "127.0.0.1",
        "no_proxy": "127.0.0.1",
        "PYTHONUNBUFFERED": "1",
        "DSPX_MLFLOW_ENABLE": "0",
    }


def test_provider_disposition_is_conservative() -> None:
    assert classify_provider_disposition({})[0] == "effect_indeterminate"
    assert (
        classify_provider_disposition(
            _effect_behavior("completed_success", dispatch_count=1)
        )[0]
        == "succeeded"
    )
    assert (
        classify_provider_disposition(
            _effect_behavior("preflight_rejected", dispatch_count=0)
        )[0]
        == "failed_no_effect_proved"
    )
    assert (
        classify_provider_disposition(
            _effect_behavior("completed_failure", dispatch_count=1)
        )[0]
        == "effect_indeterminate"
    )
    assert (
        classify_provider_disposition(
            _effect_behavior(
                "effect_indeterminate",
                dispatch_count=1,
                terminal_effect="effect_indeterminate",
            )
        )[0]
        == "effect_indeterminate"
    )
    assert (
        classify_provider_disposition(
            _effect_behavior("completed_success", dispatch_count=1, truncated=True)
        )[0]
        == "effect_indeterminate"
    )
    boolean_dispatch = _effect_behavior("completed_success", dispatch_count=True)
    assert classify_provider_disposition(boolean_dispatch)[0] == "effect_indeterminate"
    mismatched_total = _effect_behavior("completed_success", dispatch_count=1)
    mismatched_total["provider"]["effect_evidence"]["attempt_total"] = 2
    assert classify_provider_disposition(mismatched_total)[0] == "effect_indeterminate"


def test_real_validated_receipt_maps_completed_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_REPLAY_FIXTURE_JSON", '{"urgency":"high"}')
    candidate, _, _ = _single_runtime(tmp_path, capture_replay_fixture=False)
    for key, value in REQUIRED_ENVIRONMENT.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("DSPX_OPENAI_COMPAT_API_KEY", raising=False)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "model": "baseline-text",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "[[ ## urgency ## ]]\nhigh\n[[ ## completed ## ]]",
                        }
                    }
                ],
            },
            request=request,
        )

    monkeypatch.setattr(
        openai_provider, "_default_transport", lambda: httpx.MockTransport(handler)
    )
    runtime = tmp_path / "runtime-exact"
    run_program_runtime_episode(
        manifest_path=candidate / "manifest.json",
        inputs_path=tmp_path / "inputs.json",
        outdir=runtime,
        skip_oracle_index=True,
    )
    manifest = json.loads((candidate / "manifest.json").read_text())
    bundle = load_validated_program_runtime_episode_bundle(
        runtime_episode_path=runtime / "runtime_episode.json",
        expected_manifest_path=candidate / "manifest.json",
        expected_manifest=manifest,
        expected_manifest_sha256=hashlib.sha256(
            (candidate / "manifest.json").read_bytes()
        ).hexdigest(),
    )
    assert requests
    state, details = classify_provider_disposition(bundle.behavior_results)
    assert state == "succeeded"
    assert details["terminal_effect"] == "completed_success"


def test_suite_consumes_all_cases_once_without_exposing_responses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def fake_evaluate_case(**kwargs: Any) -> tuple[str, dict[str, object]]:
        case = kwargs["case"]
        calls.append(case["mode"])
        runtime_sha256, tree_sha256, behavior_sha256, receipt_sha256 = (
            _write_mock_runtime_evidence(kwargs["raw_root"])
        )
        return "succeeded", {
            "latency_ms": 1,
            "runtime_episode_sha256": runtime_sha256,
            "runtime_tree_sha256": tree_sha256,
            "runtime_receipt_sha256": receipt_sha256,
            "behavior_results_sha256": behavior_sha256,
            "response_sha256": hashlib.sha256(b"bounded mock response").hexdigest(),
            "response_length": len("bounded mock response"),
            "provider": {
                "terminal_effect": "completed_success",
                "attempt_total": 1,
                "dispositions": ["completed_success"],
                "dispatch_counts": [1],
            },
        }

    monkeypatch.setattr(executor, "_evaluate_case", fake_evaluate_case)
    state_root = tmp_path / "state"
    monkeypatch.setattr(executor, "_repo_root", lambda: REPO_ROOT)
    monkeypatch.setattr(executor, "default_state_root", lambda: state_root)
    payload = executor.execute_soomfon_evaluation_suite(
        expected_contract_sha256=CONTRACT_SHA256,
        environment=REQUIRED_ENVIRONMENT,
    )
    assert payload["state"] == "succeeded"
    assert payload["backend_locality"] == "not_verified"
    assert calls == [
        "simple",
        "elaborate",
        "researched",
        "deep-research",
        "socratic",
        "bloom",
    ]
    encoded = json.dumps(payload)
    assert "transcription" not in encoded
    assert "persona_intent" not in encoded
    assert "observed_outputs" not in encoded
    assert payload["routing_mutated"] is False
    assert payload["promotion"] is False
    assert payload["activation"] is False

    suite_root = state_root / CONTRACT_SHA256
    markers = sorted((suite_root / "ledger").glob("*.jsonl"))
    assert len(markers) == 6
    for marker in markers:
        records = [json.loads(line) for line in marker.read_text().splitlines()]
        assert [record["state"] for record in records] == [
            "attempted_outcome_unknown",
            "succeeded",
        ]
        assert oct(marker.stat().st_mode & 0o777) == "0o600"
    assert oct((suite_root / "suite-result.json").stat().st_mode & 0o777) == "0o600"

    with pytest.raises(RuntimeError, match="already consumed"):
        executor.execute_soomfon_evaluation_suite(
            expected_contract_sha256=CONTRACT_SHA256,
            environment=REQUIRED_ENVIRONMENT,
        )


def test_suite_stops_after_first_non_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def fake_evaluate_case(**kwargs: Any) -> tuple[str, dict[str, object]]:
        calls.append(kwargs["case"]["mode"])
        runtime_sha256, tree_sha256, behavior_sha256, receipt_sha256 = (
            _write_mock_runtime_evidence(
                kwargs["raw_root"],
                disposition="preflight_rejected",
                dispatch_count=0,
            )
        )
        return "failed_no_effect_proved", {
            "latency_ms": 1,
            "runtime_episode_sha256": runtime_sha256,
            "runtime_tree_sha256": tree_sha256,
            "runtime_receipt_sha256": receipt_sha256,
            "behavior_results_sha256": behavior_sha256,
            "provider": {
                "terminal_effect": "preflight_rejected",
                "attempt_total": 1,
                "dispositions": ["preflight_rejected"],
                "dispatch_counts": [0],
            },
        }

    monkeypatch.setattr(executor, "_evaluate_case", fake_evaluate_case)
    state_root = tmp_path / "state"
    monkeypatch.setattr(executor, "_repo_root", lambda: REPO_ROOT)
    monkeypatch.setattr(executor, "default_state_root", lambda: state_root)
    payload = executor.execute_soomfon_evaluation_suite(
        expected_contract_sha256=CONTRACT_SHA256,
        environment=REQUIRED_ENVIRONMENT,
    )
    assert calls == ["simple"]
    assert payload["state"] == "stopped_non_success"
    case_results = payload["case_results"]
    assert isinstance(case_results, list)
    assert isinstance(case_results[0], dict)
    case_result = cast(dict[str, object], case_results[0])
    assert case_result["state"] == "failed_no_effect_proved"


def test_cli_exposes_no_bypass_options() -> None:
    result = CliRunner().invoke(app, ["soomfon", "evaluate-originals", "--help"])
    assert result.exit_code == 0
    assert "--expected-contract-sha256" in result.stdout
    for forbidden in (
        "--contract ",
        "--mode",
        "--state-root",
        "--repo-root",
        "--endpoint",
        "--model",
        "--retry",
        "--resume",
    ):
        assert forbidden not in result.stdout


def test_suite_result_failure_does_not_enable_rerun(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = tmp_path / "state"
    _patch_roots(monkeypatch, state_root)

    def fake_success(**kwargs: Any) -> tuple[str, dict[str, object]]:
        runtime_sha256, tree_sha256, behavior_sha256, receipt_sha256 = (
            _write_mock_runtime_evidence(kwargs["raw_root"])
        )
        return "succeeded", {
            "latency_ms": 1,
            "response_sha256": hashlib.sha256(b"bounded mock response").hexdigest(),
            "response_length": len("bounded mock response"),
            "runtime_episode_sha256": runtime_sha256,
            "runtime_tree_sha256": tree_sha256,
            "runtime_receipt_sha256": receipt_sha256,
            "behavior_results_sha256": behavior_sha256,
            "provider": {
                "terminal_effect": "completed_success",
                "attempt_total": 1,
                "dispositions": ["completed_success"],
                "dispatch_counts": [1],
            },
        }

    monkeypatch.setattr(executor, "_evaluate_case", fake_success)
    private_write = executor._write_private_json

    def fail_suite_result(path: Path, payload: object) -> str:
        if path.name == "suite-result.json":
            raise OSError("simulated suite result failure")
        return private_write(path, payload)

    monkeypatch.setattr(executor, "_write_private_json", fail_suite_result)
    with pytest.raises(OSError, match="suite result"):
        executor.execute_soomfon_evaluation_suite(
            expected_contract_sha256=CONTRACT_SHA256,
            environment=REQUIRED_ENVIRONMENT,
        )
    with pytest.raises(custody.SoomfonCustodyError, match="already consumed"):
        executor.execute_soomfon_evaluation_suite(
            expected_contract_sha256=CONTRACT_SHA256,
            environment=REQUIRED_ENVIRONMENT,
        )


def test_terminal_persistence_failure_retains_unknown_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = tmp_path / "state"
    _patch_roots(monkeypatch, state_root)
    monkeypatch.setattr(
        executor,
        "_evaluate_case",
        lambda **_: ("succeeded", {"response_sha256": "b" * 64}),
    )
    monkeypatch.setattr(
        executor,
        "append_terminal",
        lambda **_: (_ for _ in ()).throw(OSError("simulated fsync failure")),
    )
    payload = executor.execute_soomfon_evaluation_suite(
        expected_contract_sha256=CONTRACT_SHA256,
        environment=REQUIRED_ENVIRONMENT,
    )
    assert payload["state"] == "stopped_non_success"
    marker = next((state_root / CONTRACT_SHA256 / "ledger").glob("*.jsonl"))
    records = [json.loads(line) for line in marker.read_text().splitlines()]
    assert [record["state"] for record in records] == ["attempted_outcome_unknown"]
    sidecars = list(marker.parent.glob("*.reconciled-indeterminate.json"))
    assert len(sidecars) == 1
    assert json.loads(sidecars[0].read_text())["state"] == "effect_indeterminate"


def test_private_tree_fsync_rejects_symlink_and_public_file(tmp_path: Path) -> None:
    root, root_fd = custody.ensure_private_tree(tmp_path / "raw")
    os.close(root_fd)
    unsafe = root / "unsafe.json"
    unsafe.write_text("{}")
    unsafe.chmod(0o644)
    with pytest.raises(custody.SoomfonCustodyError, match="file identity"):
        custody.fsync_private_tree(root)
    unsafe.chmod(0o600)
    (root / "link").symlink_to(unsafe)
    with pytest.raises(custody.SoomfonCustodyError, match="identity"):
        custody.fsync_private_tree(root)


def test_private_tree_fsync_rejects_hardlink(tmp_path: Path) -> None:
    root, root_fd = custody.ensure_private_tree(tmp_path / "raw")
    os.close(root_fd)
    source = root / "response"
    source.write_text("private", encoding="utf-8")
    source.chmod(0o600)
    os.link(source, tmp_path / "linked-response")
    with pytest.raises(custody.SoomfonCustodyError, match="file identity"):
        custody.fsync_private_tree(root)


def test_child_runtime_directory_rejects_preexisting_symlink(tmp_path: Path) -> None:
    raw, raw_fd = custody.ensure_private_tree(tmp_path / "raw")
    executor._write_private_json(raw / "inputs.json", {"inputs": {"x": "y"}})
    _, cwd_fd = custody.ensure_private_tree(raw / "empty-cwd")
    os.close(cwd_fd)
    target = tmp_path / "public-target"
    target.mkdir(mode=0o700)
    (raw / "runtime").symlink_to(target, target_is_directory=True)
    try:
        with pytest.raises(ValueError, match="entries"):
            executor.create_child_runtime_directory(
                raw_root_fd=raw_fd,
                inputs_path=raw / "inputs.json",
                outdir=raw / "runtime",
            )
        assert not list(target.iterdir())
    finally:
        os.close(raw_fd)


def test_marker_open_flags_include_append_exclusive_and_nofollow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, ledger_fd = custody.ensure_private_tree(tmp_path / "ledger")
    observed_flags: list[int] = []
    real_open = os.open

    def recording_open(
        path: str | bytes | os.PathLike[str],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        observed_flags.append(flags)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(custody.os, "open", recording_open)
    try:
        marker_fd, _ = custody.create_attempt_marker(
            ledger_fd=ledger_fd,
            contract_sha256=CONTRACT_SHA256,
            mode="simple",
        )
        os.close(marker_fd)
    finally:
        os.close(ledger_fd)
    flags = observed_flags[0]
    assert flags & os.O_CREAT
    assert flags & os.O_EXCL
    assert flags & os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        assert flags & os.O_NOFOLLOW


def test_descriptor_bound_writer_survives_runtime_path_replacement(
    tmp_path: Path,
) -> None:
    raw, raw_fd = custody.ensure_private_tree(tmp_path / "raw")
    os.mkdir("runtime", 0o700, dir_fd=raw_fd)
    runtime_fd = os.open(
        "runtime",
        os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=raw_fd,
    )
    displaced = raw / "displaced-runtime"
    try:
        (raw / "runtime").rename(displaced)
        (raw / "runtime").mkdir(mode=0o700)
        bound = Path(f"/proc/self/fd/{runtime_fd}")
        written = runtime_episode_module._write_observed_output_files(
            bound, {"response": "bound"}
        )
        assert written == ["response"]
        assert (displaced / "response").is_file()
        assert not (raw / "runtime/response").exists()
    finally:
        os.close(runtime_fd)
        os.close(raw_fd)


def test_reconciled_predecessor_cannot_authorize_next_mode(tmp_path: Path) -> None:
    suite, suite_fd = custody.ensure_private_tree(tmp_path / "suite")
    os.close(suite_fd)
    ledger, ledger_fd = custody.ensure_private_tree(suite / "ledger")
    raw, raw_fd = custody.ensure_private_tree(suite / "raw/simple")
    os.close(raw_fd)
    runtime_sha256, tree_sha256, behavior_sha256, receipt_sha256 = (
        _write_mock_runtime_evidence(raw)
    )
    marker_fd, name = custody.create_attempt_marker(
        ledger_fd=ledger_fd,
        contract_sha256=CONTRACT_SHA256,
        mode="simple",
    )
    try:
        custody.append_terminal(
            marker_fd=marker_fd,
            ledger_fd=ledger_fd,
            contract_sha256=CONTRACT_SHA256,
            mode="simple",
            state="succeeded",
            details={
                "latency_ms": 1,
                "runtime_episode_sha256": runtime_sha256,
                "runtime_tree_sha256": tree_sha256,
                "runtime_receipt_sha256": receipt_sha256,
                "behavior_results_sha256": behavior_sha256,
                "response_sha256": hashlib.sha256(b"bounded mock response").hexdigest(),
                "response_length": len("bounded mock response"),
                "provider": {
                    "terminal_effect": "completed_success",
                    "attempt_total": 1,
                    "dispositions": ["completed_success"],
                    "dispatch_counts": [1],
                },
            },
        )
    finally:
        os.close(marker_fd)
    (raw / "runtime/runtime_episode.json.meta.json").unlink()
    assert not soomfon_ledger.prior_modes_succeeded(ledger_fd, "elaborate")
    custody.reconcile_marker_indeterminate(
        ledger_fd=ledger_fd,
        marker_name=name,
        reason="terminal_persistence_failed",
    )
    try:
        assert not soomfon_ledger.prior_modes_succeeded(ledger_fd, "elaborate")
    finally:
        os.close(ledger_fd)

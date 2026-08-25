from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, cast
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.services import soomfon_evaluation_child as child_runtime
from dspx.services import soomfon_evaluation_executor as executor
from dspx.services import soomfon_evaluation_custody as custody
from dspx.services import soomfon_evaluation_ledger as soomfon_ledger
from dspx.services import soomfon_evaluation_contract as contract_module
from dspx.services import program_runtime_episode as runtime_episode_module
from dspx.run_receipts import build_run_receipt, write_run_receipt
from dspx.services.run_replay_service import check_run_receipt
from dspx.services.program_runtime_episode import (
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


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_SHA256 = "56b2f269bd6b494a2d4d08c716787449cde5dd5a63bbbfc5d4666feb32306e3a"


@pytest.fixture(autouse=True)
def _provider_free_execution_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    from dspx.services import soomfon_evaluation_authorization as auth
    from dspx.services import soomfon_evaluation_provider as provider
    from dspx.services import soomfon_evaluation_dspx_identity as dspx_identity

    monkeypatch.setattr(
        auth,
        "validate_execution_authorization",
        lambda **_: SimpleNamespace(
            execution_task_id=6000,
            authorization_sha256="f" * 64,
            ak_reconciliation_sha256="e" * 64,
            authorization_path=Path("fixture-authorization.json"),
            dspx_artifact={"kind": "reviewed_source_commit_tree"},
            maximum_provider_transports=12,
        ),
    )
    monkeypatch.setattr(
        dspx_identity, "preload_security_critical_dspx_modules", lambda: None
    )
    monkeypatch.setattr(
        dspx_identity, "verify_executing_dspx_artifact", lambda **_: None
    )
    monkeypatch.setattr(
        provider,
        "verify_soomfon_owner_source",
        lambda *_: {"commit": "7" * 40},
    )
    monkeypatch.setattr(
        executor,
        "validate_exact_runtime_identity",
        lambda: {
            "python": "3.13.12",
            "dspx-core": "0.2.1",
            "dspy": "3.3.1",
            "dspy-ai": "3.3.1",
            "gepa": "0.1.4",
            "litellm": "1.82.1",
            "httpx": "0.28.1",
            "httpcore": "1.0.9",
        },
    )


def _execute_suite(**kwargs: Any) -> dict[str, object]:
    return executor.execute_soomfon_evaluation_suite(
        execution_authorization_path=Path("fixture-authorization.json"),
        expected_authorization_sha256="f" * 64,
        owner_source_root=REPO_ROOT,
        **kwargs,
    )


def _patch_roots(monkeypatch: pytest.MonkeyPatch, state_root: Path) -> None:
    monkeypatch.setattr(executor, "_repo_root", lambda: REPO_ROOT)
    monkeypatch.setattr(executor, "default_state_root", lambda: state_root)


def _effect_behavior(
    disposition: str,
    *,
    dispatch_count: int,
    terminal_effect: str | None = None,
    truncated: bool = False,
    mode: str = "simple",
) -> dict[str, Any]:
    del terminal_effect, truncated
    accepted = disposition == "completed_success" and dispatch_count == 1
    second_signatures = {
        "simple": "AnswerSimple",
        "elaborate": "AnswerElaborate",
        "researched": "AnswerResearched",
        "deep-research": "SynthesizeDeepResearch",
        "socratic": "GuideSocratically",
        "bloom": "TeachWithBloom",
    }
    record = {
        "call_ordinal": 1,
        "signature_name": "DefinePersona",
        "reservation_id": "1" * 64 if accepted else None,
        "journal_sha256": "2" * 64 if accepted else None,
        "provider_outcome_receipt": "accepted" if accepted else "rejected",
        "request_acknowledged": True if accepted else None,
        "external_effect_possible": dispatch_count == 1,
        "producer_terminal": "provider_response_completed" if accepted else None,
        "empirical_disposition": "not_evaluated"
        if accepted
        else ("effect_indeterminate" if dispatch_count else "error"),
        "reason": "attributable_completion_not_evaluated"
        if accepted
        else "fixture_non_success",
    }
    records = [record]
    if accepted:
        records.append(
            {
                **record,
                "call_ordinal": 2,
                "signature_name": second_signatures[mode],
                "reservation_id": "3" * 64,
                "journal_sha256": "4" * 64,
            }
        )
    return {
        "provider": {
            "status": "configured",
            "metadata": {
                "schema_version": "soomfon-dspy-lm-auth-runtime-v1",
                "provider": "soomfon-dspy-lm-auth",
                "model": "codex/gpt-5.6-luna",
                "requested_route": "dspy-lm-auth:codex:gpt-5.6-luna:xhigh",
                "resolved_route": "openai:gpt-5.6-luna:responses",
                "auth_provider": "codex",
                "credential_mode": "no-refresh",
                "reasoning_effort": "xhigh",
                "num_retries": 0,
                "cache": False,
                "timeout_seconds": 60.0,
                "sync_only": True,
                "fallback_allowed": False,
                "health_probe_allowed": False,
                "contract_sha256": CONTRACT_SHA256,
                "mode": mode,
                "source_identity_sha256": "5" * 64,
                "dependency_identity_sha256": "6" * 64,
            },
            "effect_evidence": {
                "schema_version": "soomfon-provider-outcome-evidence-v1",
                "artifact_verification": "accepted_exact",
                "logical_call_total": len(records),
                "maximum_logical_calls": 2,
                "maximum_provider_transports": 2,
                "sync_only": True,
                "fallback_allowed": False,
                "health_probe_allowed": False,
                "retry_count": 0,
                "call_records": records,
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
    behavior = _effect_behavior(
        disposition, dispatch_count=dispatch_count, mode=raw_root.name
    )
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
        provider_details_override=runtime_episode_module._receipt_provider_details(
            cast(dict[str, object], behavior["provider"])
        ),
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
            "--provider-journal-fd",
            "-1",
            "--execution-task-id",
            "6000",
            "--authorization-sha256",
            "f" * 64,
            "--ak-reconciliation-sha256",
            "e" * 64,
            "--authorization-path",
            str(tmp_path / "authorization.json"),
            "--repo-root",
            str(REPO_ROOT),
            "--owner-source-root",
            str(REPO_ROOT),
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
            ("runtime_target", "requested_model"),
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


def test_exact_runtime_identity_matches_frozen_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = {
        "python": "3.13.12",
        "dspx-core": "0.2.1",
        "dspy": "3.3.1",
        "dspy-ai": "3.3.1",
        "gepa": "0.1.4",
        "litellm": "1.82.1",
        "httpx": "0.28.1",
        "httpcore": "1.0.9",
    }
    monkeypatch.setattr(contract_module.platform, "python_version", lambda: "3.13.12")
    monkeypatch.setattr(contract_module, "version", lambda name: expected[name])
    assert validate_exact_runtime_identity() == expected


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
        ("DSPX_PROVIDER", "dspy-lm-auth"),
        ("DSPX_OPENAI_COMPAT_API_BASE", "http://127.0.0.1:1234/v1"),
        ("DSPX_OPENAI_COMPAT_MODEL", "other-model"),
        ("DSPX_OPENAI_COMPAT_TIMEOUT", "30"),
        ("OPENAI_API_KEY", "forbidden"),
    ],
)
def test_provider_environment_drift_fails(key: str, value: str) -> None:
    with pytest.raises(SoomfonEvaluationContractError, match="forbidden"):
        validate_exact_provider_environment({key: value})


def test_credential_environment_fails() -> None:
    with pytest.raises(SoomfonEvaluationContractError, match="forbidden"):
        validate_exact_provider_environment({"DSPX_OPENAI_COMPAT_API_KEY": "forbidden"})


def test_child_environment_is_allowlisted(tmp_path: Path) -> None:
    child = build_sanitized_child_environment(
        {"UNRELATED": "must-not-propagate"}, private_tmp=tmp_path
    )
    assert child == {
        "TMPDIR": str(tmp_path),
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "DSPX_MLFLOW_ENABLE": "0",
    }


def test_provider_disposition_is_conservative() -> None:
    assert classify_provider_disposition({})[0] == "effect_indeterminate"
    behavior = _effect_behavior("completed_success", dispatch_count=1)
    state, details = classify_provider_disposition(behavior)
    assert state == "succeeded"
    assert details["logical_call_total"] == 2
    assert (
        classify_provider_disposition(
            _effect_behavior("preflight_rejected", dispatch_count=0)
        )[0]
        == "effect_indeterminate"
    )
    forged = json.loads(json.dumps(behavior))
    forged["provider"]["effect_evidence"]["maximum_provider_transports"] = 3
    assert classify_provider_disposition(forged)[0] == "effect_indeterminate"
    forged = json.loads(json.dumps(behavior))
    forged["provider"]["metadata"]["cache"] = True
    assert classify_provider_disposition(forged)[0] == "effect_indeterminate"


def test_parent_verifies_exact_full_provider_evidence_envelope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dspx.services import soomfon_evaluation_provider as provider_service

    behavior = _effect_behavior("completed_success", dispatch_count=1)
    behavior["examples"] = [{"observed_outputs": {"response": "bounded"}}]
    provider = cast(dict[str, Any], behavior["provider"])
    full_evidence = cast(dict[str, Any], provider["effect_evidence"])
    received: list[object] = []

    raw, raw_fd = custody.ensure_private_tree(tmp_path / "raw")
    os.close(raw_fd)
    (raw / "runtime").mkdir(mode=0o700)
    monkeypatch.setattr(executor, "_run_child", lambda **_: (0, 4))
    monkeypatch.setattr(executor, "fsync_private_tree", lambda *_: None)
    monkeypatch.setattr(
        executor, "private_runtime_tree_sha256_path", lambda _: "d" * 64
    )
    monkeypatch.setattr(
        executor,
        "load_validated_program_runtime_episode_bundle",
        lambda **_: SimpleNamespace(
            runtime_episode={"execution_status": "executed"},
            behavior_results=behavior,
            runtime_episode_sha256="a" * 64,
            runtime_receipt_sha256="c" * 64,
            behavior_results_sha256="b" * 64,
        ),
    )
    monkeypatch.setattr(
        executor,
        "runtime_evidence_hashes",
        lambda *_: {"runtime_tree_sha256": "d" * 64},
    )
    monkeypatch.setattr(executor, "marker_sha256", lambda *_: "e" * 64)
    monkeypatch.setattr(provider_service, "verify_soomfon_owner_source", lambda *_: {})

    def capture_full_envelope(
        _journal_parent: Path, evidence: object, **_: object
    ) -> None:
        provider_service.validate_soomfon_provider_evidence(
            cast(dict[str, Any], evidence), mode="simple"
        )
        received.append(evidence)

    monkeypatch.setattr(
        provider_service, "verify_retained_soomfon_journals", capture_full_envelope
    )
    state, details = executor._evaluate_case(
        case={"manifest_payload": {}, "manifest_sha256": "c" * 64, "mode": "simple"},
        staged_manifest=tmp_path / "manifest.json",
        raw_root=raw,
        child_environment={},
        contract_sha256=CONTRACT_SHA256,
        marker_fd=-1,
        ledger_fd=-1,
        lock_fd=-1,
        provider_journal_fd=-1,
        execution_task_id=6000,
        authorization_sha256="f" * 64,
        ak_reconciliation_sha256="e" * 64,
        owner_source_root=REPO_ROOT,
        authorization_path=Path("fixture-authorization.json"),
        repo_root=REPO_ROOT,
    )

    assert state == "succeeded"
    assert received == [full_evidence]
    outward = cast(dict[str, Any], details["provider"])
    assert "schema_version" not in outward
    assert outward["logical_call_total"] == 2


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
            "provider": classify_provider_disposition(
                _effect_behavior(
                    "completed_success", dispatch_count=1, mode=str(case["mode"])
                )
            )[1],
        }

    monkeypatch.setattr(executor, "_evaluate_case", fake_evaluate_case)
    state_root = tmp_path / "state"
    monkeypatch.setattr(executor, "_repo_root", lambda: REPO_ROOT)
    monkeypatch.setattr(executor, "default_state_root", lambda: state_root)
    payload = _execute_suite(
        expected_contract_sha256=CONTRACT_SHA256,
        environment=REQUIRED_ENVIRONMENT,
    )
    assert payload["state"] == "succeeded"
    assert (
        payload["backend_locality"] == "external_provider_route_not_local_backend_claim"
    )
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
        _execute_suite(
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
            "provider": {"reason": "fixture_preflight_rejected"},
        }

    monkeypatch.setattr(executor, "_evaluate_case", fake_evaluate_case)
    state_root = tmp_path / "state"
    monkeypatch.setattr(executor, "_repo_root", lambda: REPO_ROOT)
    monkeypatch.setattr(executor, "default_state_root", lambda: state_root)
    payload = _execute_suite(
        expected_contract_sha256=CONTRACT_SHA256,
        environment=REQUIRED_ENVIRONMENT,
    )
    assert calls == ["simple"]
    assert payload["state"] == "stopped_non_success"
    case_results = payload["case_results"]
    assert isinstance(case_results, list)
    assert isinstance(case_results[0], dict)
    case_result = cast(dict[str, object], case_results[0])
    assert case_result["state"] == "effect_indeterminate"


def test_cli_exposes_no_bypass_options() -> None:
    result = CliRunner().invoke(app, ["soomfon", "evaluate-originals", "--help"])
    assert result.exit_code == 0
    for required in (
        "--expected-contract-sha256",
        "--execution-authorization",
        "--expected-authorization-sha",
        "--owner-source-root",
    ):
        assert required in result.stdout
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
            "provider": classify_provider_disposition(
                _effect_behavior(
                    "completed_success",
                    dispatch_count=1,
                    mode=str(kwargs["case"]["mode"]),
                )
            )[1],
        }

    monkeypatch.setattr(executor, "_evaluate_case", fake_success)
    private_write = executor._write_private_json

    def fail_suite_result(path: Path, payload: object) -> str:
        if path.name == "suite-result.json":
            raise OSError("simulated suite result failure")
        return private_write(path, payload)

    monkeypatch.setattr(executor, "_write_private_json", fail_suite_result)
    with pytest.raises(OSError, match="suite result"):
        _execute_suite(
            expected_contract_sha256=CONTRACT_SHA256,
            environment=REQUIRED_ENVIRONMENT,
        )
    with pytest.raises(custody.SoomfonCustodyError, match="already consumed"):
        _execute_suite(
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
    payload = _execute_suite(
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
            child_runtime.create_child_runtime_directory(
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
            execution_task_id=6000,
            authorization_sha256="f" * 64,
            ak_reconciliation_sha256="e" * 64,
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
        execution_task_id=6000,
        authorization_sha256="f" * 64,
        ak_reconciliation_sha256="e" * 64,
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
                "provider": classify_provider_disposition(
                    _effect_behavior("completed_success", dispatch_count=1)
                )[1],
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


def test_parent_reconciles_canonical_ak_again_immediately_before_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dspx.services import soomfon_evaluation_authorization as auth

    validated = SimpleNamespace(
        execution_task_id=6000,
        authorization_sha256="f" * 64,
        ak_reconciliation_sha256="e" * 64,
        authorization_path=Path("fixture-authorization.json"),
        dspx_artifact={"kind": "reviewed_source_commit_tree"},
        maximum_provider_transports=12,
    )
    calls = 0

    def reconcile(**_: object) -> object:
        nonlocal calls
        calls += 1
        if calls == 1:
            return validated
        raise auth.SoomfonExecutionAuthorizationError("canonical AK state")

    markers: list[str] = []
    monkeypatch.setattr(auth, "validate_execution_authorization", reconcile)
    monkeypatch.setattr(executor, "default_state_root", lambda: tmp_path / "state")
    monkeypatch.setattr(
        executor,
        "_persist_attempt_before_effect",
        lambda **_: markers.append("marker"),
    )
    with pytest.raises(auth.SoomfonExecutionAuthorizationError, match="canonical AK"):
        _execute_suite(
            expected_contract_sha256=CONTRACT_SHA256,
            environment=REQUIRED_ENVIRONMENT,
        )
    assert calls == 2
    assert markers == []

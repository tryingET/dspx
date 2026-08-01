# summary: "Tests three-strata installed-wheel live semantic verification and fail-closed claim boundaries."
# read_when:
#   - "Changing the opt-in installed live semantic runner, verifier, or evidence packet."

from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFIER_PATH = REPO_ROOT / "scripts/ci/verify_installed_core_live_semantic.py"
SCORING_PATH = REPO_ROOT / "scripts/ci/installed_core_live_semantic_scoring.py"
RUNNER_PATH = REPO_ROOT / "scripts/run_installed_core_live_semantic.sh"
CASE_IDS = (
    "single-module-authority-boundary",
    "pipeline-evidence-calibration",
    "pdf-transition-review-runtime-replay",
)
PROVIDER = "dspy-lm-auth"
MODEL = "codex/gpt-5.6-sol"


def _load_module(path: Path, name: str) -> ModuleType:
    script_dir = str(path.parent)
    sys.path.insert(0, script_dir)
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(script_dir)


def _load_verifier() -> ModuleType:
    return _load_module(VERIFIER_PATH, "verify_installed_core_live_semantic")


def _load_scoring() -> ModuleType:
    return _load_module(SCORING_PATH, "installed_core_live_semantic_scoring")


def _write_json(path: Path, payload: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _canonical_hash(value: object) -> str:
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def _behavior_non_authority() -> dict[str, bool]:
    return {
        "external_authority_mutated": False,
        "external_mutation": False,
        "governance_authority": False,
        "optimization_authority": False,
        "oracle_promotion": False,
        "oracle_pruning": False,
        "oracle_ranking": False,
        "promotion_authority": False,
        "winner_selection": False,
    }


def _workflow_effect() -> dict[str, bool]:
    return {
        "ak_called": False,
        "external_authority_mutated": False,
        "governance_mutated": False,
        "promotion_applied": False,
        "shared_oracle_mutated": False,
        "winner_selected": False,
    }


def _replay_payload() -> dict[str, Any]:
    return {
        "status": "ok",
        "error_codes": [],
        "replay_claims": {
            "schema_version": "dspx-replay-claim-matrix-v1",
            "mode": "check_only",
            "dimensions": {
                "receipt_integrity_check": {"status": "passed"},
                "deterministic_regeneration": {"status": "not_run"},
                "runtime_execution_reproduction": {"status": "not_run"},
                "semantic_reproduction": {"status": "not_evaluated"},
                "quality_evaluation_reproduction": {"status": "not_evaluated"},
            },
            "release_claim_allowed": False,
            "authority": {
                "release_authority": False,
                "promotion_authority": False,
                "activation_authority": False,
                "governance_authority": False,
                "external_authority": False,
            },
        },
    }


def _valid_journey(root: Path) -> dict[str, Any]:
    root.mkdir(mode=0o700)
    corpus_source = REPO_ROOT / "benchmarks/semantic/program-corpus-v2.json"
    contract_source = (
        REPO_ROOT / "benchmarks/semantic/installed-live-oracle-evaluation-v1.json"
    )
    corpus = json.loads(corpus_source.read_text())
    (root / "corpus.json").write_bytes(corpus_source.read_bytes())
    (root / "evaluation-contract.json").write_bytes(contract_source.read_bytes())

    rows: list[dict[str, Any]] = []
    case_paths: dict[str, dict[str, Path]] = {}
    oracle_rows: list[tuple[str, str, str]] = []
    for index, case in enumerate(corpus["cases"], start=1):
        case_id = case["id"]
        assert case_id == CASE_IDS[index - 1]
        candidate_root = root / "benchmark" / case_id
        identity = {
            "assembly_id": f"assembly-live-{index}",
            "candidate_id": f"candidate-live-{index}",
            "receipt_bundle_id": f"receipt-live-{index}",
        }
        declared_example = case["intent"]["examples"][0]
        response_field = case["response_field"]
        response = declared_example["outputs"][response_field]
        groups = case["required_concept_groups"]
        manifest_hash = _write_json(
            candidate_root / "manifest.json",
            {
                "candidate_assembly": {
                    "assembly_id": identity["assembly_id"],
                    "candidate_id": identity["candidate_id"],
                },
                "receipt_bundle": {"receipt_bundle_id": identity["receipt_bundle_id"]},
            },
        )
        receipt_hash = _write_json(
            candidate_root / "manifest.json.meta.json", {"run_kind": "program-gen"}
        )
        behavior = {
            "authority": "behavior_evidence_only_non_authoritative",
            "provider": {
                "provider": f"{PROVIDER}/{MODEL}",
                "status": "configured",
            },
            "summary": {"status": "passed", "total": 1, "passed": 1},
            "examples": [
                {
                    "status": "passed",
                    "inputs": declared_example["inputs"],
                    "expected_outputs": declared_example["outputs"],
                    "observed_outputs": {response_field: response},
                    "quality_evaluation": {
                        "status": "passed",
                        "quality_approved": False,
                        "criteria": [
                            {
                                "id": case["intent"]["quality_criteria"][0]["id"],
                                "score": 1.0,
                                "missing_group_indexes": [],
                                "forbidden_hits": [],
                            }
                        ],
                    },
                }
            ],
            "non_authority": _behavior_non_authority(),
        }
        behavior_hash = _write_json(candidate_root / "behavior_results.json", behavior)
        episode_hash = _write_json(
            candidate_root / "behavior_episode.json", {"status": "passed"}
        )
        oracle_evidence_path = candidate_root / "oracle_evidence.json"
        _write_json(
            oracle_evidence_path,
            {
                "behavior": {
                    "summary": {"status": "passed"},
                    "result_hash": behavior_hash,
                }
            },
        )
        workflow_hash = _write_json(
            candidate_root / "program_loop.json",
            {"status": "ok", "effect": _workflow_effect()},
        )
        rows.append(
            {
                "id": case_id,
                "status": "passed",
                "score": 1.0,
                "required_groups_total": len(groups),
                "required_groups_matched": len(groups),
                "missing_group_indexes": [],
                "forbidden_hits": [],
                "response_sha256": hashlib.sha256(response.encode()).hexdigest(),
                "error": None,
                "runtime_replay": None,
                "runtime_replay_status": (
                    "not_run_live_unsupported"
                    if case.get("runtime_contract") is not None
                    else "not_required"
                ),
                "candidate": identity,
                "artifacts": {
                    "manifest_sha256": manifest_hash,
                    "receipt_sha256": receipt_hash,
                    "behavior_results_sha256": behavior_hash,
                    "behavior_episode_sha256": episode_hash,
                    "workflow_sha256": workflow_hash,
                },
            }
        )
        replay_path = root / "replay" / f"{case_id}.json"
        _write_json(replay_path, _replay_payload())
        oracle_rows.append(
            (
                f"program-oracle-evidence:{identity['receipt_bundle_id']}",
                "program-oracle-evidence",
                json.dumps({"behavior": {"result_hash": behavior_hash}}),
            )
        )
        case_paths[case_id] = {
            "behavior": candidate_root / "behavior_results.json",
            "oracle_evidence": oracle_evidence_path,
            "replay": replay_path,
        }

    result = {
        "schema_version": "dspx-program-semantic-benchmark-result-v2",
        "corpus": {"sha256": _canonical_hash(corpus)},
        "execution": {
            "mode": "live",
            "provider": PROVIDER,
            "network_allowed": True,
            "deterministic": False,
            "generated_program_path": True,
            "oracle_indexed": False,
        },
        "thresholds": {
            "min_overall_score": 1.0,
            "min_case_score": 1.0,
            "max_failed_cases": 0,
        },
        "summary": {
            "cases_total": 3,
            "cases_passed": 3,
            "cases_failed": 0,
            "overall_score": 1.0,
            "threshold_pass": True,
        },
        "cases": rows,
        "authority": {
            "evidence_only": True,
            "authoritative_decision": False,
            "promotion_approved": False,
            "activation_applied": False,
            "shared_oracle_mutated": False,
            "external_authority_mutated": False,
            "governance_mutated": False,
            "ak_called": False,
            "winner_selected": False,
        },
    }
    result_path = root / "benchmark-result.json"
    _write_json(result_path, result)
    _write_json(
        root / "oracle-index-result.json",
        {
            "scanned": 3,
            "indexed": 3,
            "errors": 0,
            "backend": "mock",
            "semantic_claim": "plumbing_only_not_production_semantics",
            "production_semantic_claim_allowed": False,
            "non_authority_confirmed": True,
        },
    )
    _write_json(
        root / "oracle-report.json",
        {
            "schema_version": "program-oracle-evidence-report-v1",
            "status": "ok",
            "total_records": 3,
            "non_authority": {
                "oracle_ranking": False,
                "oracle_pruning": False,
                "oracle_promotion": False,
                "governance_authority": False,
                "external_mutation": False,
            },
        },
    )
    _write_json(
        root / "runtime-environment.json",
        {
            "provider": PROVIDER,
            "requested_model": MODEL,
            "resolved_model_identity": "not_proven",
            "pythonpath_unset": True,
            "auth_store_nonmutation_proven": False,
            "network_isolation_proven": False,
            "dspy_lm_auth_wheel_sha256": "67102c73bf20e2e5736ae65fba4aff05c7d8a8f6a5dec302ea71c78bf097491f",
            "dspx_stream_compatibility_retry_enabled": False,
            "provider_internal_retry_behavior": "not_proven",
            "unbounded_raw_provider_response_retained": False,
            "bounded_benchmark_behavior_output_retained": True,
        },
    )
    _write_json(
        root / "provider-attempt.json",
        {
            "benchmark_invocation_count": 1,
            "schema_version": "dspx-installed-core-live-attempt-v2",
            "disposition": "passed",
            "dspx_stream_compatibility_retry_enabled": False,
            "provider_internal_retry_behavior": "not_proven",
            "separate_health_probe_run": False,
            "mechanical_retry_run": False,
            "selective_quality_rerun_allowed": False,
            "case_execution_order": list(CASE_IDS),
        },
    )
    oracle_path = root / "oracle" / "coordinates.db"
    oracle_path.parent.mkdir()
    connection = sqlite3.connect(oracle_path)
    connection.execute(
        "CREATE TABLE coordinates (run_id TEXT, run_kind TEXT, metadata_json TEXT)"
    )
    connection.executemany("INSERT INTO coordinates VALUES (?, ?, ?)", oracle_rows)
    connection.commit()
    connection.close()
    return {"result": result_path, "cases": case_paths, "oracle": oracle_path}


def test_installed_live_just_recipe_preserves_documented_argument_order() -> None:
    result = subprocess.run(
        [
            "just",
            "--dry-run",
            "installed-core-live-semantic",
            "wheel=/proof/core.whl",
            f"wheel_sha256={'a' * 64}",
            f"provider={PROVIDER}",
            f"model={MODEL}",
            "root=/proof/journey",
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    rendered = result.stdout + result.stderr
    assert 'selected_provider="provider=dspy-lm-auth"' in rendered
    assert 'selected_model="model=codex/gpt-5.6-sol"' in rendered
    assert 'work="root=/proof/journey"' in rendered


def test_semantic_word_boundaries_match_benchmark_contract() -> None:
    scoring = _load_scoring()
    assert scoring._contains("activate the program", "activate")
    assert not scoring._contains("inactivate the program", "activate")
    assert not scoring._contains("preapproval granted", "approval granted")


def test_current_replay_checks_every_declared_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_verifier()
    root = tmp_path / "journey"
    for case_id in CASE_IDS:
        payload = {"status": "ok", "case_id": case_id}
        _write_json(root / "replay" / f"{case_id}.json", payload)
    observed: list[str] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        receipt = command[command.index("--from") + 1]
        case_id = Path(receipt).parts[1]
        observed.append(case_id)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"status": "ok", "case_id": case_id}),
            stderr="",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    module._verify_current_replay(journey_root=root, venv_root=root / "venv")
    assert observed == list(CASE_IDS)


def test_valid_journey_proves_only_declared_strata(tmp_path: Path) -> None:
    module = _load_verifier()
    root = tmp_path / "journey"
    _valid_journey(root)
    proof = module.verify_journey_artifacts(
        root, provider=PROVIDER, requested_model=MODEL
    )
    assert proof["status"] == "passed"
    assert proof["case_order"] == list(CASE_IDS)
    assert [case["semantic_score"] for case in proof["cases"]] == [1.0, 1.0, 1.0]
    assert proof["oracle_record_count"] == 3
    assert (
        proof["coverage_claim"]
        == "declared_strata_only_not_statistically_representative"
    )
    assert proof["effect"]["corpus_process_invocations"] == 1
    assert proof["effect"]["provider_transport_call_count"] == "not_proven"
    assert proof["nonclaims"]["statistical_representativeness"] is False
    assert proof["nonclaims"]["release_authority"] is False


def test_corpus_order_drift_is_rejected(tmp_path: Path) -> None:
    module = _load_verifier()
    root = tmp_path / "journey"
    _valid_journey(root)
    corpus_path = root / "corpus.json"
    corpus = json.loads(corpus_path.read_text())
    corpus["cases"].reverse()
    _write_json(corpus_path, corpus)
    with pytest.raises(module.InstalledCoreGoldenPathError, match="corpus file hash"):
        module.verify_journey_artifacts(root, provider=PROVIDER, requested_model=MODEL)


def test_partial_failure_fails_closed(tmp_path: Path) -> None:
    module = _load_verifier()
    root = tmp_path / "journey"
    paths = _valid_journey(root)
    result = json.loads(paths["result"].read_text())
    result["summary"].update(cases_passed=2, cases_failed=1, threshold_pass=False)
    result["cases"][1]["status"] = "failed"
    _write_json(paths["result"], result)
    with pytest.raises(module.InstalledCoreGoldenPathError, match="cases_passed"):
        module.verify_journey_artifacts(root, provider=PROVIDER, requested_model=MODEL)


def test_route_drift_in_any_case_is_rejected(tmp_path: Path) -> None:
    module = _load_verifier()
    root = tmp_path / "journey"
    paths = _valid_journey(root)
    behavior_path = paths["cases"][CASE_IDS[1]]["behavior"]
    behavior = json.loads(behavior_path.read_text())
    behavior["provider"]["provider"] = "other-provider/model"
    behavior_hash = _write_json(behavior_path, behavior)
    result = json.loads(paths["result"].read_text())
    result["cases"][1]["artifacts"]["behavior_results_sha256"] = behavior_hash
    _write_json(paths["result"], result)
    with pytest.raises(
        module.InstalledCoreGoldenPathError, match="selected live route"
    ):
        module.verify_journey_artifacts(root, provider=PROVIDER, requested_model=MODEL)


def test_requested_model_drift_in_any_case_is_rejected(tmp_path: Path) -> None:
    module = _load_verifier()
    root = tmp_path / "journey"
    paths = _valid_journey(root)
    behavior_path = paths["cases"][CASE_IDS[1]]["behavior"]
    behavior = json.loads(behavior_path.read_text())
    behavior["provider"]["provider"] = f"{PROVIDER}/codex/other-model"
    behavior_hash = _write_json(behavior_path, behavior)
    result = json.loads(paths["result"].read_text())
    result["cases"][1]["artifacts"]["behavior_results_sha256"] = behavior_hash
    _write_json(paths["result"], result)
    with pytest.raises(
        module.InstalledCoreGoldenPathError, match="exact selected live route"
    ):
        module.verify_journey_artifacts(root, provider=PROVIDER, requested_model=MODEL)


def test_attempt_schema_rejects_contradictory_extension_fields(tmp_path: Path) -> None:
    module = _load_verifier()
    root = tmp_path / "journey"
    _valid_journey(root)
    attempt_path = root / "provider-attempt.json"
    attempt = json.loads(attempt_path.read_text())
    attempt["observed_corpus_process_invocations"] = 2
    _write_json(attempt_path, attempt)
    with pytest.raises(module.InstalledCoreGoldenPathError, match="attempt fields"):
        module.verify_journey_artifacts(root, provider=PROVIDER, requested_model=MODEL)


def test_attempt_schema_rejects_boolean_integer_confusion(tmp_path: Path) -> None:
    module = _load_verifier()
    root = tmp_path / "journey"
    _valid_journey(root)
    attempt_path = root / "provider-attempt.json"
    attempt = json.loads(attempt_path.read_text())
    attempt["benchmark_invocation_count"] = True
    attempt["separate_health_probe_run"] = 0
    _write_json(attempt_path, attempt)
    with pytest.raises(module.InstalledCoreGoldenPathError, match="invocation_count"):
        module.verify_journey_artifacts(root, provider=PROVIDER, requested_model=MODEL)


def test_result_threshold_weakening_is_rejected(tmp_path: Path) -> None:
    module = _load_verifier()
    root = tmp_path / "journey"
    paths = _valid_journey(root)
    result = json.loads(paths["result"].read_text())
    result["thresholds"] = {
        "min_overall_score": 0.0,
        "min_case_score": 0.0,
        "max_failed_cases": 3,
    }
    _write_json(paths["result"], result)
    with pytest.raises(module.InstalledCoreGoldenPathError, match="thresholds"):
        module.verify_journey_artifacts(root, provider=PROVIDER, requested_model=MODEL)


def test_result_thresholds_reject_boolean_number_confusion(tmp_path: Path) -> None:
    module = _load_verifier()
    root = tmp_path / "journey"
    paths = _valid_journey(root)
    result = json.loads(paths["result"].read_text())
    result["thresholds"] = {
        "min_overall_score": True,
        "min_case_score": True,
        "max_failed_cases": False,
    }
    _write_json(paths["result"], result)
    with pytest.raises(module.InstalledCoreGoldenPathError, match="thresholds"):
        module.verify_journey_artifacts(root, provider=PROVIDER, requested_model=MODEL)


def test_duplicate_receipt_identity_cannot_collapse_oracle_coverage(
    tmp_path: Path,
) -> None:
    module = _load_verifier()
    root = tmp_path / "journey"
    paths = _valid_journey(root)
    result = json.loads(paths["result"].read_text())
    duplicate = result["cases"][0]["candidate"]["receipt_bundle_id"]
    result["cases"][1]["candidate"]["receipt_bundle_id"] = duplicate
    manifest_path = root / "benchmark" / CASE_IDS[1] / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["receipt_bundle"]["receipt_bundle_id"] = duplicate
    result["cases"][1]["artifacts"]["manifest_sha256"] = _write_json(
        manifest_path, manifest
    )
    _write_json(paths["result"], result)
    with pytest.raises(module.InstalledCoreGoldenPathError, match="must be unique"):
        module.verify_journey_artifacts(root, provider=PROVIDER, requested_model=MODEL)


def test_selective_quality_rerun_claim_is_rejected(tmp_path: Path) -> None:
    module = _load_verifier()
    root = tmp_path / "journey"
    _valid_journey(root)
    attempt_path = root / "provider-attempt.json"
    attempt = json.loads(attempt_path.read_text())
    attempt["selective_quality_rerun_allowed"] = True
    _write_json(attempt_path, attempt)
    with pytest.raises(module.InstalledCoreGoldenPathError, match="selective_quality"):
        module.verify_journey_artifacts(root, provider=PROVIDER, requested_model=MODEL)


def test_hollow_semantic_case_is_rejected(tmp_path: Path) -> None:
    module = _load_verifier()
    root = tmp_path / "journey"
    _valid_journey(root)
    corpus_path = root / "corpus.json"
    corpus = json.loads(corpus_path.read_text())
    corpus["cases"][0] = {"id": CASE_IDS[0]}
    _write_json(corpus_path, corpus)
    with pytest.raises(module.InstalledCoreGoldenPathError, match="corpus file hash"):
        module.verify_journey_artifacts(root, provider=PROVIDER, requested_model=MODEL)


def test_semantic_miss_fails_closed(tmp_path: Path) -> None:
    module = _load_verifier()
    root = tmp_path / "journey"
    paths = _valid_journey(root)
    result = json.loads(paths["result"].read_text())
    result["cases"][0]["score"] = 0.75
    _write_json(paths["result"], result)
    with pytest.raises(module.InstalledCoreGoldenPathError, match="row score"):
        module.verify_journey_artifacts(root, provider=PROVIDER, requested_model=MODEL)


def test_behavior_drift_after_benchmark_is_rejected(tmp_path: Path) -> None:
    module = _load_verifier()
    root = tmp_path / "journey"
    paths = _valid_journey(root)
    behavior_path = paths["cases"][CASE_IDS[0]]["behavior"]
    behavior = json.loads(behavior_path.read_text())
    behavior["summary"]["status"] = "failed"
    _write_json(behavior_path, behavior)
    with pytest.raises(
        module.InstalledCoreGoldenPathError, match="behavior_results_sha256"
    ):
        module.verify_journey_artifacts(root, provider=PROVIDER, requested_model=MODEL)


def test_replay_claim_widening_is_rejected(tmp_path: Path) -> None:
    module = _load_verifier()
    root = tmp_path / "journey"
    paths = _valid_journey(root)
    replay_path = paths["cases"][CASE_IDS[2]]["replay"]
    replay = json.loads(replay_path.read_text())
    replay["replay_claims"]["dimensions"]["runtime_execution_reproduction"][
        "status"
    ] = "passed"
    _write_json(replay_path, replay)
    with pytest.raises(
        module.InstalledCoreGoldenPathError, match="runtime_execution_reproduction"
    ):
        module.verify_journey_artifacts(root, provider=PROVIDER, requested_model=MODEL)


def test_oracle_index_must_bind_every_current_behavior(tmp_path: Path) -> None:
    module = _load_verifier()
    root = tmp_path / "journey"
    paths = _valid_journey(root)
    connection = sqlite3.connect(paths["oracle"])
    connection.execute(
        "UPDATE coordinates SET metadata_json=? WHERE run_id LIKE ?",
        (json.dumps({"behavior": {"result_hash": "0" * 64}}), "%receipt-live-2"),
    )
    connection.commit()
    connection.close()
    with pytest.raises(
        module.InstalledCoreGoldenPathError, match="Oracle behavior hash"
    ):
        module.verify_journey_artifacts(root, provider=PROVIDER, requested_model=MODEL)


def test_oracle_intermediate_symlink_is_rejected(tmp_path: Path) -> None:
    module = _load_verifier()
    root = tmp_path / "journey"
    _valid_journey(root)
    oracle = root / "oracle"
    real = root / "oracle-real"
    oracle.rename(real)
    oracle.symlink_to(real, target_is_directory=True)
    with pytest.raises(module.InstalledCoreGoldenPathError, match="Oracle index"):
        module.verify_journey_artifacts(root, provider=PROVIDER, requested_model=MODEL)


def test_runtime_requested_model_must_match(tmp_path: Path) -> None:
    module = _load_verifier()
    root = tmp_path / "journey"
    _valid_journey(root)
    with pytest.raises(
        module.InstalledCoreGoldenPathError, match="evaluation contract requested model"
    ):
        module.verify_journey_artifacts(
            root, provider=PROVIDER, requested_model="codex/other-model"
        )


def test_runner_is_valid_bash_and_freezes_one_full_corpus_attempt(
    tmp_path: Path,
) -> None:
    syntax = subprocess.run(["bash", "-n", str(RUNNER_PATH)], check=False)
    assert syntax.returncode == 0
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert source.count("run_program_semantic_benchmarks.py") == 1
    assert "snapshot_exact_three_strata_contract" in source
    assert "selective_quality_rerun_allowed" in source
    assert "--stop-after-case-error --live" in source
    assert "oracle index --from-program-evidence --path benchmark" in source
    wheel = tmp_path / "dspx_core-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"fixture")
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    result = subprocess.run(
        [
            "bash",
            str(RUNNER_PATH),
            "--wheel",
            str(wheel),
            "--wheel-sha256",
            digest,
            "--root",
            str(tmp_path / "journey"),
            "--provider",
            "stub",
            "--model",
            MODEL,
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 2
    assert "only dspy-lm-auth is supported" in result.stderr
    assert not (tmp_path / "journey").exists()

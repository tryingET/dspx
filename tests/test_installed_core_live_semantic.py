# summary: "Tests installed-wheel live semantic evidence verification and fail-closed claim boundaries."
# read_when:
#   - "Changing the opt-in installed live semantic runner, verifier, or evidence packet."

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import ModuleType
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFIER_PATH = REPO_ROOT / "scripts/ci/verify_installed_core_live_semantic.py"
SCORING_PATH = REPO_ROOT / "scripts/ci/installed_core_live_semantic_scoring.py"
RUNNER_PATH = REPO_ROOT / "scripts/run_installed_core_live_semantic.sh"
CASE_ID = "single-module-authority-boundary"
PROVIDER = "dspy-lm-auth"
MODEL = "codex/gpt-5.6-sol"


def _load_verifier() -> ModuleType:
    script_dir = str(VERIFIER_PATH.parent)
    sys.path.insert(0, script_dir)
    try:
        spec = importlib.util.spec_from_file_location(
            "verify_installed_core_live_semantic", VERIFIER_PATH
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(script_dir)


def _load_scoring() -> ModuleType:
    script_dir = str(SCORING_PATH.parent)
    sys.path.insert(0, script_dir)
    try:
        spec = importlib.util.spec_from_file_location(
            "installed_core_live_semantic_scoring", SCORING_PATH
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(script_dir)


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


def test_semantic_word_boundaries_match_benchmark_contract() -> None:
    scoring = _load_scoring()
    assert scoring._contains("activate the program", "activate")
    assert not scoring._contains("inactivate the program", "activate")
    assert not scoring._contains("preapproval granted", "approval granted")


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


def _valid_journey(root: Path) -> dict[str, Path]:
    root.mkdir(mode=0o700)
    candidate_root = root / "benchmark" / CASE_ID
    identity = {
        "assembly_id": "assembly-live-1",
        "candidate_id": "candidate-live-1",
        "receipt_bundle_id": "receipt-live-1",
    }
    corpus = json.loads(
        (REPO_ROOT / "benchmarks/semantic/program-corpus-v2.json").read_text()
    )
    corpus["cases"] = [case for case in corpus["cases"] if case["id"] == CASE_ID]
    assert len(corpus["cases"]) == 1
    case = corpus["cases"][0]
    declared_example = case["intent"]["examples"][0]
    answer = declared_example["outputs"]["answer"]
    groups = case["required_concept_groups"]
    _write_json(root / "corpus.json", corpus)
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
    behavior_hash = _write_json(
        candidate_root / "behavior_results.json",
        {
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
                    "observed_outputs": {"answer": answer},
                    "quality_evaluation": {
                        "status": "passed",
                        "quality_approved": False,
                        "criteria": [
                            {
                                "id": "authority_boundary",
                                "score": 1.0,
                                "missing_group_indexes": [],
                                "forbidden_hits": [],
                            }
                        ],
                    },
                }
            ],
            "non_authority": _behavior_non_authority(),
        },
    )
    episode_hash = _write_json(
        candidate_root / "behavior_episode.json", {"status": "passed"}
    )
    _write_json(
        candidate_root / "oracle_evidence.json",
        {
            "behavior": {
                "summary": {"status": "passed"},
                "result_hash": behavior_hash,
            }
        },
    )
    workflow_hash = _write_json(
        candidate_root / "program_loop.json",
        {
            "status": "ok",
            "effect": {
                "ak_called": False,
                "external_authority_mutated": False,
                "governance_mutated": False,
                "promotion_applied": False,
                "shared_oracle_mutated": False,
                "winner_selected": False,
            },
        },
    )
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
        "summary": {
            "cases_total": 1,
            "cases_passed": 1,
            "cases_failed": 0,
            "overall_score": 1.0,
            "threshold_pass": True,
        },
        "cases": [
            {
                "id": CASE_ID,
                "status": "passed",
                "score": 1.0,
                "required_groups_total": len(groups),
                "required_groups_matched": len(groups),
                "missing_group_indexes": [],
                "forbidden_hits": [],
                "response_sha256": hashlib.sha256(answer.encode()).hexdigest(),
                "error": None,
                "runtime_replay_status": "not_required",
                "candidate": identity,
                "artifacts": {
                    "manifest_sha256": manifest_hash,
                    "receipt_sha256": receipt_hash,
                    "behavior_results_sha256": behavior_hash,
                    "behavior_episode_sha256": episode_hash,
                    "workflow_sha256": workflow_hash,
                },
            }
        ],
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
    _write_json(root / "benchmark-result.json", result)
    replay_claims = {
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
    }
    _write_json(
        root / "replay-check.json",
        {"status": "ok", "error_codes": [], "replay_claims": replay_claims},
    )
    _write_json(
        root / "oracle-index-result.json",
        {
            "scanned": 1,
            "indexed": 1,
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
            "total_records": 1,
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
            "disposition": "passed",
            "dspx_stream_compatibility_retry_enabled": False,
            "provider_internal_retry_behavior": "not_proven",
            "separate_health_probe_run": False,
            "mechanical_retry_run": False,
        },
    )
    oracle_path = root / "oracle" / "coordinates.db"
    oracle_path.parent.mkdir()
    connection = sqlite3.connect(oracle_path)
    connection.execute(
        "CREATE TABLE coordinates (run_id TEXT, run_kind TEXT, metadata_json TEXT)"
    )
    connection.execute(
        "INSERT INTO coordinates VALUES (?, ?, ?)",
        (
            f"program-oracle-evidence:{identity['receipt_bundle_id']}",
            "program-oracle-evidence",
            json.dumps({"behavior": {"result_hash": behavior_hash}}),
        ),
    )
    connection.commit()
    connection.close()
    return {
        "result": root / "benchmark-result.json",
        "behavior": candidate_root / "behavior_results.json",
        "replay": root / "replay-check.json",
        "oracle": oracle_path,
        "oracle_evidence": candidate_root / "oracle_evidence.json",
    }


def test_valid_journey_proves_only_bounded_live_semantics(tmp_path: Path) -> None:
    module = _load_verifier()
    root = tmp_path / "journey"
    _valid_journey(root)

    proof = module.verify_journey_artifacts(
        root, provider=PROVIDER, requested_model=MODEL
    )

    assert proof["status"] == "passed"
    assert proof["behavior_status"] == "passed"
    assert proof["receipt_check_status"] == "ok"
    assert proof["effect"]["candidate_local_oracle_mutated"] is True
    assert proof["effect"]["shared_oracle_mutated"] is False
    assert proof["effect"]["workflow_declared_ak_called"] is False
    assert proof["effect"]["ak_path_canary_observation"] == "not_observed"
    assert proof["effect"]["broad_ak_invocation_absence_proven"] is False
    assert proof["nonclaims"]["release_authority"] is False
    assert proof["nonclaims"]["runtime_execution_reproduction"] == "not_run"
    assert proof["nonclaims"]["exact_resolved_model_identity_proven"] is False


def test_hollow_semantic_case_is_rejected(tmp_path: Path) -> None:
    module = _load_verifier()
    root = tmp_path / "journey"
    _valid_journey(root)
    corpus_path = root / "corpus.json"
    corpus = json.loads(corpus_path.read_text())
    corpus["cases"] = [{"id": CASE_ID}]
    _write_json(corpus_path, corpus)
    result_path = root / "benchmark-result.json"
    result = json.loads(result_path.read_text())
    result["corpus"]["sha256"] = _canonical_hash(corpus)
    _write_json(result_path, result)

    with pytest.raises(module.InstalledCoreGoldenPathError, match="exact checked-in"):
        module.verify_journey_artifacts(root, provider=PROVIDER, requested_model=MODEL)


def test_semantic_miss_fails_closed(tmp_path: Path) -> None:
    module = _load_verifier()
    root = tmp_path / "journey"
    paths = _valid_journey(root)
    result = json.loads(paths["result"].read_text())
    result["summary"]["cases_passed"] = 0
    result["summary"]["cases_failed"] = 1
    result["summary"]["threshold_pass"] = False
    result["cases"][0]["status"] = "failed"
    _write_json(paths["result"], result)

    with pytest.raises(module.InstalledCoreGoldenPathError, match="cases_passed"):
        module.verify_journey_artifacts(root, provider=PROVIDER, requested_model=MODEL)


def test_behavior_drift_after_benchmark_is_rejected(tmp_path: Path) -> None:
    module = _load_verifier()
    root = tmp_path / "journey"
    paths = _valid_journey(root)
    behavior = json.loads(paths["behavior"].read_text())
    behavior["summary"]["status"] = "failed"
    _write_json(paths["behavior"], behavior)

    with pytest.raises(
        module.InstalledCoreGoldenPathError, match="behavior_results_sha256"
    ):
        module.verify_journey_artifacts(root, provider=PROVIDER, requested_model=MODEL)


def test_replay_claim_widening_is_rejected(tmp_path: Path) -> None:
    module = _load_verifier()
    root = tmp_path / "journey"
    paths = _valid_journey(root)
    replay = json.loads(paths["replay"].read_text())
    replay["replay_claims"]["dimensions"]["runtime_execution_reproduction"][
        "status"
    ] = "passed"
    _write_json(paths["replay"], replay)

    with pytest.raises(
        module.InstalledCoreGoldenPathError, match="runtime_execution_reproduction"
    ):
        module.verify_journey_artifacts(root, provider=PROVIDER, requested_model=MODEL)


def test_oracle_index_must_bind_current_behavior(tmp_path: Path) -> None:
    module = _load_verifier()
    root = tmp_path / "journey"
    paths = _valid_journey(root)
    connection = sqlite3.connect(paths["oracle"])
    connection.execute(
        "UPDATE coordinates SET metadata_json=?",
        (json.dumps({"behavior": {"result_hash": "0" * 64}}),),
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

    with pytest.raises(module.InstalledCoreGoldenPathError, match="requested model"):
        module.verify_journey_artifacts(
            root, provider=PROVIDER, requested_model="codex/other-model"
        )


def test_runner_is_valid_bash_and_rejects_non_auth_provider(tmp_path: Path) -> None:
    syntax = subprocess.run(["bash", "-n", str(RUNNER_PATH)], check=False)
    assert syntax.returncode == 0
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

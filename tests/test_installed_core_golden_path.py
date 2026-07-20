# summary: "Tests installed-wheel Core proof verification and fail-closed path handling."

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
VERIFIER_PATH = REPO_ROOT / "scripts/ci/verify_installed_core_golden_path.py"
RUNNER_PATH = REPO_ROOT / "scripts/ci/installed-core-golden-path.sh"
GOLDEN_INTENT = {
    "name": "InstalledWheelTicketProgram",
    "objective": "Classify support ticket urgency from the supplied ticket text.",
    "inputs": ["ticket_text"],
    "outputs": ["urgency"],
    "metric": "exact_match",
    "examples": [
        {
            "inputs": {"ticket_text": "Production outage for all users"},
            "outputs": {"urgency": "high"},
        }
    ],
}


EXPECTED_NORMALIZED_INTENT = {
    "capabilities": {},
    "constraints": [],
    "dataset": {},
    "datasets": {},
    "examples": GOLDEN_INTENT["examples"],
    "input_fields": [],
    "inputs": GOLDEN_INTENT["inputs"],
    "jury": {},
    "metric": GOLDEN_INTENT["metric"],
    "name": GOLDEN_INTENT["name"],
    "objective": GOLDEN_INTENT["objective"],
    "options": {},
    "output_fields": [],
    "outputs": GOLDEN_INTENT["outputs"],
    "promotion": {},
    "quality_criteria": [],
    "runtime": {},
    "schema_version": "program-intent-v2",
    "task_type": "single_module",
    "topology": {},
}


def _load_verifier() -> ModuleType:
    script_dir = str(VERIFIER_PATH.parent)
    sys.path.insert(0, script_dir)
    try:
        spec = importlib.util.spec_from_file_location(
            "verify_installed_core_golden_path", VERIFIER_PATH
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(script_dir)


def _write_json(path: Path, payload: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload).encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _check_only_replay_claims() -> dict[str, Any]:
    return {
        "schema_version": "dspx-replay-claim-matrix-v1",
        "mode": "check_only",
        "dimensions": {
            "receipt_integrity_check": {
                "status": "passed",
                "evidence_level": "current_receipt_and_declared_artifact_bindings",
            },
            "deterministic_regeneration": {
                "status": "not_run",
                "evidence_level": "fresh_producer_output_identity",
            },
            "runtime_execution_reproduction": {
                "status": "not_run",
                "evidence_level": "fresh_receipt_bound_runtime_evidence_identity",
            },
            "semantic_reproduction": {
                "status": "not_evaluated",
                "evidence_level": "independent_semantic_equivalence_evaluation",
            },
            "quality_evaluation_reproduction": {
                "status": "not_evaluated",
                "evidence_level": (
                    "receipt_bound_quality_evaluation_identity_not_independent_approval"
                ),
            },
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


def _valid_artifacts(root: Path) -> None:
    program = root / "program"
    _write_json(root / "intent.json", GOLDEN_INTENT)
    identity = {
        "assembly_id": "assembly-1",
        "candidate_id": "candidate-1",
        "episode_id": "episode-1",
        "receipt_bundle_id": "bundle-1",
        "request_id": "request-1",
    }
    manifest_hash = _write_json(
        program / "manifest.json",
        {
            "candidate_assembly": {
                "assembly_id": identity["assembly_id"],
                "candidate_id": identity["candidate_id"],
                "root_path": str(program),
            },
            "receipt_bundle": {"receipt_bundle_id": identity["receipt_bundle_id"]},
        },
    )
    behavior_non_authority = {
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
    behavior_results_hash = _write_json(
        program / "behavior_results.json",
        {
            "schema_version": "program-behavior-results-v1",
            "authority": "behavior_evidence_only_non_authoritative",
            "non_authority": behavior_non_authority,
            "provider": {"provider": "stub/echo", "status": "configured"},
            "summary": {"status": "passed", "total": 1, "passed": 1},
            "examples": [
                {
                    "status": "passed",
                    "inputs": {"ticket_text": "Production outage for all users"},
                    "expected_outputs": {"urgency": "high"},
                    "observed_outputs": {"urgency": "high"},
                }
            ],
        },
    )
    behavior_episode_hash = _write_json(
        program / "behavior_episode.json",
        {
            "schema_version": "program-behavior-episode-v1",
            "status": "passed",
            "authority": "behavior_evidence_only_non_authoritative",
            "non_authority": behavior_non_authority,
            "summary": {"status": "passed", "total": 1, "passed": 1},
            "sources": [
                {
                    "status": "passed",
                    "returncode": 0,
                    "count": 1,
                    "behavior_results_path": "behavior_results.json",
                    "behavior_results_hash": behavior_results_hash,
                    "provider": {"provider": "stub/echo", "status": "configured"},
                }
            ],
        },
    )
    oracle_hash = _write_json(
        program / "oracle_evidence.json",
        {
            "schema_version": "program-oracle-evidence-v1",
            "evidence_kind": "program_execution_episode",
            "authority": "oracle_readability_only_non_authoritative",
            "identity": identity,
            "non_authority": {
                "external_mutation": False,
                "governance_authority": False,
                "oracle_promotion": False,
                "oracle_pruning": False,
                "oracle_ranking": False,
            },
            "behavior": {
                "summary": {"status": "passed", "total": 1},
                "result_path": "behavior_results.json",
                "result_hash": behavior_results_hash,
            },
            "oracle_facets": {
                "behavior_status": "passed",
                "total_evaluation_count": 1,
            },
            "source_artifacts": [
                {
                    "kind": "behavior_results",
                    "path": "behavior_results.json",
                    "content_hash": behavior_results_hash,
                }
            ],
        },
    )
    report_hash = _write_json(
        program / "program_oracle_report.json",
        {
            "schema_version": "program-oracle-evidence-report-v1",
            "status": "ok",
            "index_path": str(program / "oracle/coordinates.db"),
            "total_records": 1,
            "records": [
                {
                    "identity": identity,
                    "run_id": "program-oracle-evidence:bundle-1",
                    "evidence_hash": oracle_hash,
                    "evidence_path": str(program / "oracle_evidence.json"),
                }
            ],
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
        program / "program_candidate_state.json",
        {
            "schema_version": "program-candidate-state-v1",
            "created_from": {
                "manifest_path": str(program / "manifest.json"),
                "oracle_report_path": str(program / "program_oracle_report.json"),
            },
            "artifact_hashes": {
                "manifest_sha256": manifest_hash,
                "oracle_report_sha256": report_hash,
                "oracle_evidence_sha256": oracle_hash,
                "behavior_episode_sha256": behavior_episode_hash,
                "behavior_results_sha256": behavior_results_hash,
            },
            "truth_summary": {
                "program_materialized": True,
                "behavior_evidence_present": True,
                "oracle_report_present": True,
                "promotion_applied": False,
                "ak_called": False,
                "governance_mutated": False,
                "external_authority_mutated": False,
                "winner_selected": False,
                "oracle_publication_ref_present": False,
            },
        },
    )
    _write_json(
        program / "manifest.json.meta.json",
        {
            "receipt_version": "v2",
            "run_kind": "program-gen",
            "provider": "stub",
            "output_path": str(program / "manifest.json"),
            "hash": manifest_hash,
            "replay_inputs": {"intent": EXPECTED_NORMALIZED_INTENT},
            "run_summary": {
                "receipt_bundle_id": identity["receipt_bundle_id"],
                "behavior_episode_hash": behavior_episode_hash,
                "behavior_results_hash": behavior_results_hash,
            },
        },
    )
    _write_json(
        root / "replay-check.json",
        {
            "status": "ok",
            "receipt_path": str(program / "manifest.json.meta.json"),
            "output_path": str(program / "manifest.json"),
            "receipt_hash": manifest_hash,
            "actual_output_hash": manifest_hash,
            "checks": {"output_hash_match": True},
            "errors": [],
            "replay_claims": _check_only_replay_claims(),
        },
    )
    _write_json(
        root / "program-loop-result.json",
        {
            "schema_version": "program-loop-workflow-v2",
            "status": "ok",
            "candidate": {
                "assembly_id": identity["assembly_id"],
                "candidate_id": identity["candidate_id"],
                "receipt_bundle_id": identity["receipt_bundle_id"],
                "root_path": str(program),
                "manifest_path": str(program / "manifest.json"),
                "receipt_path": str(program / "manifest.json.meta.json"),
            },
            "steps": {
                "program_gen": {
                    "status": "ok",
                    "materialization_status": "materialized",
                },
                "behavior_evaluation": {
                    "status": "passed",
                    "passed": True,
                    "sha256": behavior_episode_hash,
                },
                "replay_check": {"status": "ok"},
                "oracle_index": {
                    "status": "ok",
                    "index_path": str(program / "oracle/coordinates.db"),
                    "result": {"indexed": 1, "errors": 0, "backend": "mock"},
                },
                "oracle_report": {
                    "status": "ok",
                    "path": str(program / "program_oracle_report.json"),
                },
                "candidate_state": {
                    "status": "not_promoted_materialized",
                    "path": str(program / "program_candidate_state.json"),
                },
            },
            "effect": {
                "shared_oracle_mutated": False,
                "ak_called": False,
                "external_authority_mutated": False,
                "governance_mutated": False,
                "promotion_applied": False,
                "winner_selected": False,
                "oracle_index_scope": "candidate-local explicit path",
            },
            "non_authority": {"promotion_authority": False},
        },
    )
    index = program / "oracle/coordinates.db"
    index.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(index)
    try:
        connection.execute(
            "CREATE TABLE coordinates (run_id TEXT, run_kind TEXT, provider TEXT)"
        )
        connection.execute(
            "INSERT INTO coordinates VALUES (?, ?, ?)",
            (
                "program-oracle-evidence:bundle-1",
                "program-oracle-evidence",
                "program-gen",
            ),
        )
        connection.commit()
    finally:
        connection.close()


def test_artifact_verifier_accepts_only_truthful_offline_core_proof(
    tmp_path: Path,
) -> None:
    verifier = _load_verifier()
    _valid_artifacts(tmp_path)

    proof = verifier.verify_artifacts(tmp_path)

    assert proof["status"] == "passed"
    assert proof["provider"] == "stub"
    assert proof["oracle_embedding_backend"] == "mock"
    assert proof["oracle_semantic_claim"] == "plumbing_only_not_production_semantics"
    assert proof["replay_claim_matrix_schema"] == "dspx-replay-claim-matrix-v1"
    assert proof["non_authority"]["release_readiness"] is False
    assert proof["non_authority"]["network_isolation_proven"] is False
    assert proof["workflow_declared_effects"]["ak_called"] is False


def test_artifact_verifier_rejects_check_only_reproduction_overclaim(
    tmp_path: Path,
) -> None:
    verifier = _load_verifier()
    _valid_artifacts(tmp_path)
    replay_path = tmp_path / "replay-check.json"
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    replay["replay_claims"]["dimensions"]["semantic_reproduction"]["status"] = "passed"
    replay_path.write_text(json.dumps(replay), encoding="utf-8")

    with pytest.raises(
        verifier.InstalledCoreGoldenPathError,
        match="semantic_reproduction status drift",
    ):
        verifier.verify_artifacts(tmp_path)


@pytest.mark.parametrize("location", ["matrix", "dimension"])
def test_artifact_verifier_rejects_unknown_success_shaped_replay_claim_fields(
    tmp_path: Path, location: str
) -> None:
    verifier = _load_verifier()
    _valid_artifacts(tmp_path)
    replay_path = tmp_path / "replay-check.json"
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    if location == "matrix":
        replay["replay_claims"]["release_readiness"] = True
        expected = "replay claim fields drift"
    else:
        replay["replay_claims"]["dimensions"]["receipt_integrity_check"][
            "independently_verified"
        ] = True
        expected = "receipt_integrity_check fields drift"
    replay_path.write_text(json.dumps(replay), encoding="utf-8")

    with pytest.raises(verifier.InstalledCoreGoldenPathError, match=expected):
        verifier.verify_artifacts(tmp_path)


def test_artifact_verifier_rejects_success_shaped_authority_widening(
    tmp_path: Path,
) -> None:
    verifier = _load_verifier()
    _valid_artifacts(tmp_path)
    payload_path = tmp_path / "program-loop-result.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["effect"]["ak_called"] = True
    payload_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        verifier.InstalledCoreGoldenPathError,
        match=r"loop\.effect\.ak_called drift",
    ):
        verifier.verify_artifacts(tmp_path)


def test_bounded_json_reader_rejects_escape_symlink_and_huge_input(
    tmp_path: Path,
) -> None:
    verifier = _load_verifier()
    outside = tmp_path.parent / f"{tmp_path.name}-outside.json"
    outside.write_text("{}", encoding="utf-8")
    (tmp_path / "linked.json").symlink_to(outside)

    with pytest.raises(verifier.InstalledCoreGoldenPathError, match="symlinked"):
        verifier.read_bounded_json(tmp_path, "linked.json", label="linked")
    with pytest.raises(
        verifier.InstalledCoreGoldenPathError, match="confined and relative"
    ):
        verifier.read_bounded_json(tmp_path, "../escape.json", label="escaped")

    huge = tmp_path / "huge.json"
    huge.write_bytes(b" " * (verifier.MAX_JSON_BYTES + 1))
    with pytest.raises(verifier.InstalledCoreGoldenPathError, match="exceeds"):
        verifier.read_bounded_json(tmp_path, "huge.json", label="huge")


def test_artifact_verifier_rejects_fresh_but_substituted_report(
    tmp_path: Path,
) -> None:
    verifier = _load_verifier()
    _valid_artifacts(tmp_path)
    report_path = tmp_path / "program/program_oracle_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["records"][0]["identity"] = {
        **report["records"][0]["identity"],
        "candidate_id": "substituted-candidate",
    }
    report_path.write_text(json.dumps(report), encoding="utf-8")
    state_path = tmp_path / "program/program_candidate_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["artifact_hashes"]["oracle_report_sha256"] = hashlib.sha256(
        report_path.read_bytes()
    ).hexdigest()
    state_path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(
        verifier.InstalledCoreGoldenPathError, match="report Oracle identity drift"
    ):
        verifier.verify_artifacts(tmp_path)


def test_artifact_verifier_rejects_coherently_changed_golden_result(
    tmp_path: Path,
) -> None:
    verifier = _load_verifier()
    _valid_artifacts(tmp_path)
    intent_path = tmp_path / "intent.json"
    intent = json.loads(intent_path.read_text(encoding="utf-8"))
    intent["examples"][0]["outputs"]["urgency"] = "low"
    intent_path.write_text(json.dumps(intent), encoding="utf-8")
    results_path = tmp_path / "program/behavior_results.json"
    results = json.loads(results_path.read_text(encoding="utf-8"))
    results["examples"][0]["expected_outputs"]["urgency"] = "low"
    results["examples"][0]["observed_outputs"]["urgency"] = "low"
    results_path.write_text(json.dumps(results), encoding="utf-8")

    with pytest.raises(
        verifier.InstalledCoreGoldenPathError, match="golden-path intent drift"
    ):
        verifier.verify_artifacts(tmp_path)


def test_artifact_verifier_rejects_receipt_only_intent_drift(tmp_path: Path) -> None:
    verifier = _load_verifier()
    _valid_artifacts(tmp_path)
    receipt_path = tmp_path / "program/manifest.json.meta.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["replay_inputs"]["intent"]["constraints"] = ["weakened"]
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(
        verifier.InstalledCoreGoldenPathError,
        match="complete normalized receipt intent drift",
    ):
        verifier.verify_artifacts(tmp_path)


def test_runner_rejects_unsafe_roots_before_effects(tmp_path: Path) -> None:
    venv = tmp_path / "venv"
    venv.mkdir()
    existing = tmp_path / "existing"
    existing.mkdir()
    for unsafe in (existing,):
        result = subprocess.run(
            ["bash", str(RUNNER_PATH), str(venv), str(unsafe), str(REPO_ROOT)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 2
        assert "must not already exist" in result.stderr

    target = tmp_path / "target"
    target.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(target, target_is_directory=True)
    result = subprocess.run(
        ["bash", str(RUNNER_PATH), str(venv), str(linked), str(REPO_ROOT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "must not already exist" in result.stderr
    assert not (target / "intent.json").exists()

    checkout_child = REPO_ROOT / ".installed-core-proof-forbidden"
    assert not checkout_child.exists()
    result = subprocess.run(
        [
            "bash",
            str(RUNNER_PATH),
            str(venv),
            str(checkout_child),
            str(REPO_ROOT),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "outside the source checkout" in result.stderr
    assert not checkout_child.exists()

    partial_root = tmp_path / "partial-journey"
    result = subprocess.run(
        ["bash", str(RUNNER_PATH), str(venv), str(partial_root), str(REPO_ROOT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert not partial_root.exists()

    unwritable = tmp_path / "unwritable"
    unwritable.mkdir(mode=0o500)
    try:
        permission_root = unwritable / "journey"
        result = subprocess.run(
            [
                "bash",
                str(RUNNER_PATH),
                str(venv),
                str(permission_root),
                str(REPO_ROOT),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0
        assert not permission_root.exists()
    finally:
        unwritable.chmod(0o700)

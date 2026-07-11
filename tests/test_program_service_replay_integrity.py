# summary: "Tests replay detection of drift across generated program evidence and declarations."
# read_when:
#   - "Changing run-receipt integrity checks for program surfaces, behavior, Oracle, or episodes."

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dspx.services.program_service import ProgramIntent, materialize_program_from_intent
from dspx.services.run_replay_service import check_run_receipt

runner = CliRunner()


@pytest.mark.slow
def test_program_replay_fails_when_generated_module_policy_drifts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="GeneratedPolicyDriftReplayProgram",
            objective="Answer safely.",
            inputs=["question"],
            outputs=["answer"],
        ),
        outdir=tmp_path / "program",
    )
    root = Path(artifact.root_path)
    policy_path = root / "generated_module_policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["violations"] = [{"code": "dspy_call_not_allowed", "detail": "dspy.Tool"}]
    policy_path.write_text(
        json.dumps(policy, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    replay = check_run_receipt(root / "manifest.json.meta.json")

    assert replay["status"] == "failed"
    assert replay["checks"]["program_generated_module_policy_semantic_valid"] is False
    assert "program_evidence_declaration_mismatch" in replay["error_codes"]


@pytest.mark.slow
def test_program_replay_fails_when_runtime_outcomes_claim_tool_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="UnsafeRuntimeOutcomeReplayProgram",
            objective="Answer safely.",
            inputs=["question"],
            outputs=["answer"],
        ),
        outdir=tmp_path / "program",
    )
    root = Path(artifact.root_path)
    outcomes_path = root / "program_runtime_outcomes.json"
    outcomes = json.loads(outcomes_path.read_text(encoding="utf-8"))
    outcomes["runtime_policy"]["tool_binding_allowed"] = True
    outcomes_path.write_text(
        json.dumps(outcomes, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    replay = check_run_receipt(root / "manifest.json.meta.json")

    assert replay["status"] == "failed"
    assert replay["checks"]["program_runtime_outcomes_semantic_valid"] is False
    assert "program_evidence_declaration_mismatch" in replay["error_codes"]


@pytest.mark.slow
def test_program_replay_fails_when_module_surfaces_claim_unsafe_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="UnsafeModuleSurfaceReplayProgram",
            objective="Answer safely.",
            inputs=["question"],
            outputs=["answer"],
        ),
        outdir=tmp_path / "program",
    )
    root = Path(artifact.root_path)
    surfaces_path = root / "module_surfaces.json"
    surfaces = json.loads(surfaces_path.read_text(encoding="utf-8"))
    surfaces["module_surfaces"][0]["effects"]["network"] = True
    surfaces_path.write_text(
        json.dumps(surfaces, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    replay = check_run_receipt(root / "manifest.json.meta.json")

    assert replay["status"] == "failed"
    assert replay["checks"]["program_module_surfaces_semantic_valid"] is False
    assert "program_evidence_declaration_mismatch" in replay["error_codes"]


@pytest.mark.slow
def test_program_replay_detects_behavior_result_artifact_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent = ProgramIntent(
        name="ReplayEvidenceProgram",
        objective="Classify a short support ticket.",
        inputs=["ticket_text"],
        outputs=["urgency"],
        metric="exact_match",
        examples=[
            {
                "inputs": {"ticket_text": "Server is down for all users"},
                "outputs": {"urgency": "high"},
            }
        ],
    )

    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    root = Path(artifact.root_path)
    replay = check_run_receipt(root / "manifest.json.meta.json")
    assert replay["status"] == "ok"
    assert replay["checks"]["program_behavior_results_hash_match"] is True
    assert replay["checks"]["program_oracle_evidence_hash_match"] is True

    behavior_path = root / "behavior_results.json"
    behavior_payload = json.loads(behavior_path.read_text(encoding="utf-8"))
    behavior_payload["summary"]["status"] = "drifted"
    behavior_path.write_text(
        json.dumps(behavior_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    drift = check_run_receipt(root / "manifest.json.meta.json")

    assert drift["status"] == "failed"
    assert drift["checks"]["output_hash_match"] is True
    assert drift["checks"]["program_behavior_results_exists"] is True
    assert drift["checks"]["program_behavior_results_hash_match"] is False
    assert drift["checks"]["program_oracle_evidence_hash_match"] is True
    assert "program_evidence_hash_mismatch" in drift["error_codes"]
    assert any(
        detail.get("code") == "program_evidence_hash_mismatch"
        and detail.get("check") == "program_behavior_results_hash_match"
        for detail in drift["error_details"]
    )


@pytest.mark.slow
def test_program_replay_detects_oracle_evidence_artifact_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent = ProgramIntent(
        name="ReplayOracleEvidenceProgram",
        objective="Classify a short support ticket.",
        inputs=["ticket_text"],
        outputs=["urgency"],
        metric="exact_match",
        examples=[
            {
                "inputs": {"ticket_text": "Server is down for all users"},
                "outputs": {"urgency": "high"},
            }
        ],
    )

    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    root = Path(artifact.root_path)
    oracle_path = root / "oracle_evidence.json"
    oracle_payload = json.loads(oracle_path.read_text(encoding="utf-8"))
    oracle_payload["oracle_text"] = "drifted oracle evidence"
    oracle_path.write_text(
        json.dumps(oracle_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    drift = check_run_receipt(root / "manifest.json.meta.json")

    assert drift["status"] == "failed"
    assert drift["checks"]["output_hash_match"] is True
    assert drift["checks"]["program_oracle_evidence_exists"] is True
    assert drift["checks"]["program_oracle_evidence_hash_match"] is False
    assert drift["checks"]["program_behavior_results_hash_match"] is True
    assert "program_evidence_hash_mismatch" in drift["error_codes"]
    assert any(
        detail.get("code") == "program_evidence_hash_mismatch"
        and detail.get("check") == "program_oracle_evidence_hash_match"
        for detail in drift["error_details"]
    )


@pytest.mark.slow
def test_program_replay_detects_execution_episode_artifact_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent = ProgramIntent(
        name="ReplayExecutionEpisodeProgram",
        objective="Classify a short support ticket.",
        inputs=["ticket_text"],
        outputs=["urgency"],
        examples=[
            {
                "inputs": {"ticket_text": "Server is down for all users"},
                "outputs": {"urgency": "high"},
            }
        ],
    )

    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    root = Path(artifact.root_path)
    episode_path = root / "execution_episode.json"
    episode_payload = json.loads(episode_path.read_text(encoding="utf-8"))
    episode_payload["status"] = "drifted"
    episode_path.write_text(
        json.dumps(episode_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    drift = check_run_receipt(root / "manifest.json.meta.json")

    assert drift["status"] == "failed"
    assert drift["checks"]["output_hash_match"] is True
    assert drift["checks"]["program_execution_episode_exists"] is True
    assert drift["checks"]["program_execution_episode_hash_match"] is False
    assert drift["checks"]["program_behavior_results_hash_match"] is True
    assert drift["checks"]["program_oracle_evidence_hash_match"] is True
    assert "program_evidence_hash_mismatch" in drift["error_codes"]
    assert any(
        detail.get("code") == "program_evidence_hash_mismatch"
        and detail.get("check") == "program_execution_episode_hash_match"
        for detail in drift["error_details"]
    )


@pytest.mark.slow
def test_program_replay_detects_missing_execution_episode_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent = ProgramIntent(
        name="ReplayMissingExecutionEpisodeProgram",
        objective="Classify a short support ticket.",
        inputs=["ticket_text"],
        outputs=["urgency"],
        examples=[
            {
                "inputs": {"ticket_text": "Server is down for all users"},
                "outputs": {"urgency": "high"},
            }
        ],
    )

    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    root = Path(artifact.root_path)
    (root / "execution_episode.json").unlink()

    missing = check_run_receipt(root / "manifest.json.meta.json")

    assert missing["status"] == "failed"
    assert missing["checks"]["output_hash_match"] is True
    assert missing["checks"]["program_execution_episode_exists"] is False
    assert missing["checks"]["program_behavior_results_exists"] is True
    assert "program_evidence_artifact_missing" in missing["error_codes"]
    assert any(
        detail.get("code") == "program_evidence_artifact_missing"
        and detail.get("check") == "program_execution_episode_exists"
        for detail in missing["error_details"]
    )


@pytest.mark.slow
def test_program_replay_detects_execution_episode_declaration_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent = ProgramIntent(
        name="ReplayExecutionDeclarationMismatchProgram",
        objective="Classify a short support ticket.",
        inputs=["ticket_text"],
        outputs=["urgency"],
        examples=[
            {
                "inputs": {"ticket_text": "Server is down for all users"},
                "outputs": {"urgency": "high"},
            }
        ],
    )

    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    root = Path(artifact.root_path)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["execution_episode_artifact"]["content_hash"] = "0" * 64
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    mismatch = check_run_receipt(root / "manifest.json.meta.json")

    assert mismatch["status"] == "failed"
    assert mismatch["checks"]["output_hash_match"] is False
    assert mismatch["checks"]["program_execution_episode_exists"] is True
    assert (
        mismatch["checks"]["program_execution_episode_declaration_consistent"] is False
    )
    assert "program_evidence_declaration_mismatch" in mismatch["error_codes"]
    assert any(
        detail.get("code") == "program_evidence_declaration_mismatch"
        and detail.get("check") == "program_execution_episode_declaration_consistent"
        for detail in mismatch["error_details"]
    )


@pytest.mark.slow
def test_program_replay_detects_missing_program_evidence_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent = ProgramIntent(
        name="ReplayMissingEvidenceProgram",
        objective="Classify a short support ticket.",
        inputs=["ticket_text"],
        outputs=["urgency"],
        examples=[
            {
                "inputs": {"ticket_text": "Server is down for all users"},
                "outputs": {"urgency": "high"},
            }
        ],
    )

    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    root = Path(artifact.root_path)
    (root / "behavior_results.json").unlink()

    missing = check_run_receipt(root / "manifest.json.meta.json")

    assert missing["status"] == "failed"
    assert missing["checks"]["output_hash_match"] is True
    assert missing["checks"]["program_behavior_results_exists"] is False
    assert missing["checks"]["program_oracle_evidence_exists"] is True
    assert "program_evidence_artifact_missing" in missing["error_codes"]
    assert any(
        detail.get("code") == "program_evidence_artifact_missing"
        and detail.get("check") == "program_behavior_results_exists"
        for detail in missing["error_details"]
    )


@pytest.mark.slow
def test_program_replay_detects_program_evidence_declaration_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent = ProgramIntent(
        name="ReplayDeclarationMismatchProgram",
        objective="Classify a short support ticket.",
        inputs=["ticket_text"],
        outputs=["urgency"],
        examples=[
            {
                "inputs": {"ticket_text": "Server is down for all users"},
                "outputs": {"urgency": "high"},
            }
        ],
    )

    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    root = Path(artifact.root_path)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["execution_episode"]["behavior_results"]["content_hash"] = "0" * 64
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    mismatch = check_run_receipt(root / "manifest.json.meta.json")

    assert mismatch["status"] == "failed"
    assert mismatch["checks"]["output_hash_match"] is False
    assert mismatch["checks"]["program_behavior_results_exists"] is True
    assert (
        mismatch["checks"]["program_behavior_results_declaration_consistent"] is False
    )
    assert "program_evidence_declaration_mismatch" in mismatch["error_codes"]
    assert any(
        detail.get("code") == "program_evidence_declaration_mismatch"
        and detail.get("check") == "program_behavior_results_declaration_consistent"
        for detail in mismatch["error_details"]
    )

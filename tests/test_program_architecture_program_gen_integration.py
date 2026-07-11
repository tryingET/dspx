# summary: "Tests architecture contract and intent-portfolio integration with program generation and replay."
# read_when:
#   - "Changing program-gen contract verification or architecture portfolio materialization."

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dspx.cache import sha256_text
from dspx.cli.dspx import app
from dspx.services.program_architecture import (
    build_program_architecture_candidates,
    verify_architecture_contract_intent,
    write_architecture_contract_drafts,
)
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_service import materialize_program_from_intent
from dspx.services.run_replay_service import check_run_receipt
from program_architecture_shared import (
    _write_intent,
    runner,
)


@pytest.mark.slow
def test_program_gen_records_matching_contract_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    payload = build_program_architecture_candidates(
        ProgramIntent(
            name="ReactContractMaterializeProgram",
            objective="Use ReAct to answer without tools.",
            inputs=["question"],
            outputs=["answer"],
        )
    )
    index = write_architecture_contract_drafts(payload, tmp_path / "contracts")
    record = next(
        item
        for item in index["contract_drafts"]
        if item["candidate_id"] == "preview_react_declared_only"
    )
    verification = verify_architecture_contract_intent(Path(record["intent_path"]))
    verification_path = tmp_path / "contract_verification.json"
    verification_path.write_text(
        json.dumps(verification, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "program-gen",
            "--intent",
            record["intent_path"],
            "--outdir",
            str(tmp_path / "program"),
            "--contract-verification",
            str(verification_path),
        ],
    )

    assert result.exit_code == 0, result.output
    manifest = json.loads((tmp_path / "program" / "manifest.json").read_text())
    recorded = manifest["program_architecture_contract_verification"]
    assert recorded["schema_version"] == (
        "program-architecture-contract-verification-v1"
    )
    assert recorded["status"] == "verified_contract_intent"
    assert recorded["content_hash"] == sha256_text(
        verification_path.read_text(encoding="utf-8")
    )
    assert recorded["materialization_gate"]["allows_live_tools"] is False
    replay = check_run_receipt(tmp_path / "program" / "manifest.json.meta.json")
    assert replay["status"] == "ok"
    assert replay["checks"]["program_contract_verification_exists"] is True
    assert replay["checks"]["program_contract_verification_hash_match"] is True
    assert replay["checks"]["program_contract_verification_semantic_valid"] is True


@pytest.mark.slow
def test_program_gen_rejects_mismatched_contract_verification(tmp_path: Path) -> None:
    intent_path = tmp_path / "intent.json"
    other_intent_path = tmp_path / "other_intent.json"
    base_intent = {
        "schema_version": "program-intent-v2",
        "name": "MismatchProgram",
        "objective": "Answer safely.",
        "inputs": ["question"],
        "outputs": ["answer"],
    }
    intent_path.write_text(json.dumps(base_intent), encoding="utf-8")
    other_intent_path.write_text(
        json.dumps({**base_intent, "name": "OtherProgram"}), encoding="utf-8"
    )
    verification = {
        "schema_version": "program-architecture-contract-verification-v1",
        "status": "verified_contract_intent",
        "materialization_allowed_by_contract_verification": True,
        "materialization_gate": {
            "status": "verified_for_explicit_program_gen_materialization",
            "program_gen_must_match_intent_hash": sha256_text(
                other_intent_path.read_text(encoding="utf-8")
            ),
            "allows_live_tools": False,
            "allows_custom_imports": False,
            "allows_external_retrievers": False,
        },
    }
    verification_path = tmp_path / "verification.json"
    verification_path.write_text(json.dumps(verification), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "program-gen",
            "--intent",
            str(intent_path),
            "--outdir",
            str(tmp_path / "program"),
            "--contract-verification",
            str(verification_path),
        ],
    )

    assert result.exit_code == 2
    assert "intent_hash_mismatch" in result.output
    assert not (tmp_path / "program").exists()


@pytest.mark.slow
def test_architecture_plan_portfolio_dogfoods_program_gen_and_replay(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    intent_path = tmp_path / "intent.yaml"
    plan_path = tmp_path / "architecture_plan.json"
    portfolio_dir = tmp_path / "portfolio"
    _write_intent(
        intent_path,
        "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
    )
    result = runner.invoke(
        app,
        [
            "program-architect",
            "plan",
            "--intent",
            str(intent_path),
            "--out",
            str(plan_path),
            "--portfolio-outdir",
            str(portfolio_dir),
        ],
    )
    assert result.exit_code == 0, result.output

    candidate_intent = (
        portfolio_dir / "candidate_intents" / "prompt_inferred_pipeline.json"
    )
    artifact = materialize_program_from_intent(
        ProgramIntent.model_validate(json.loads(candidate_intent.read_text())),
        outdir=tmp_path / "generated" / "prompt_inferred_pipeline",
    )
    root = Path(artifact.root_path)
    generated_surfaces = json.loads((root / "module_surfaces.json").read_text())
    planned = json.loads(plan_path.read_text())
    planned_inferred = next(
        candidate
        for candidate in planned["candidates"]
        if candidate["candidate_id"] == "prompt_inferred_pipeline"
    )

    assert generated_surfaces == planned_inferred["module_surface_preview"]
    assert check_run_receipt(root / "manifest.json.meta.json")["status"] == "ok"

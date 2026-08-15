# summary: "Tests program-architecture CLI planning, portfolio and contract-draft outputs, and write guards."
# read_when:
#   - "Changing program-architect plan or verify-contract commands and their output boundaries."

from __future__ import annotations

import json
from pathlib import Path


from dspx.cache import sha256_text
from dspx.cli.dspx import app
from dspx.services.program_architecture import (
    build_program_architecture_candidates,
    write_architecture_contract_drafts,
)
from dspx.services.program_intent import ProgramIntent
from program_architecture_shared import (
    _write_intent,
    runner,
)


def test_architecture_planner_cli_writes_plan_and_intent_portfolio(
    tmp_path: Path,
) -> None:
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
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    stdout_plan = json.loads(result.output)
    assert stdout_plan["schema_version"] == "program-architecture-candidates-v1"
    stdout_without_artifact = dict(stdout_plan)
    stdout_artifact = dict(stdout_without_artifact.pop("artifact"))
    assert stdout_artifact["payload_hash_excluding_artifact"] == sha256_text(
        json.dumps(
            stdout_without_artifact, ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n"
    )
    assert plan["portfolio"]["schema_version"] == (
        "program-architecture-intent-portfolio-v1"
    )
    assert "content_hash" not in plan["artifact"]
    assert "payload_hash_excluding_artifact" in plan["artifact"]
    assert plan["effect"]["candidate_materialized"] is False
    assert plan["effect"]["portfolio_materialized"] is True
    assert not (portfolio_dir / "manifest.json").exists()
    assert not (portfolio_dir / "program.py").exists()
    index = json.loads((portfolio_dir / "portfolio_index.json").read_text())
    assert index["candidate_intent_count"] == 2
    assert sorted(
        path.name for path in (portfolio_dir / "candidate_intents").glob("*.json")
    ) == [
        "baseline_single_predict.json",
        "prompt_inferred_pipeline.json",
    ]


def test_architecture_planner_cli_writes_contract_drafts(tmp_path: Path) -> None:
    intent_path = tmp_path / "intent.yaml"
    plan_path = tmp_path / "architecture_plan.json"
    contract_dir = tmp_path / "contracts"
    _write_intent(intent_path, "Use ReActV2 tools later to answer the question.")

    result = runner.invoke(
        app,
        [
            "program-architect",
            "plan",
            "--intent",
            str(intent_path),
            "--out",
            str(plan_path),
            "--contract-outdir",
            str(contract_dir),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan["contract_drafts"]["schema_version"] == (
        "program-architecture-contract-drafts-v1"
    )
    assert plan["effect"]["contract_drafts_written"] is True
    assert plan["effect"]["candidate_materialized"] is False
    index = json.loads((contract_dir / "contract_drafts_index.json").read_text())
    assert index["contract_draft_count"] >= 1
    assert (
        contract_dir / "contract_intents" / "preview_reactv2_declared_only.json"
    ).exists()
    assert not (contract_dir / "manifest.json").exists()
    assert not (contract_dir / "program.py").exists()


def test_architecture_planner_cli_records_react_v2_contract_rejection(tmp_path: Path) -> None:
    payload = build_program_architecture_candidates(
        ProgramIntent(
            name="ReactV2CliVerifyProgram",
            objective="Use ReActV2 to answer with tools later.",
            inputs=["question"],
            outputs=["answer"],
        )
    )
    index = write_architecture_contract_drafts(payload, tmp_path / "contracts")
    record = next(
        item
        for item in index["contract_drafts"]
        if item["candidate_id"] == "preview_reactv2_declared_only"
    )
    out = tmp_path / "contract_verification.json"

    result = runner.invoke(
        app,
        [
            "program-architect",
            "verify-contract",
            "--intent",
            record["intent_path"],
            "--out",
            str(out),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    verification = json.loads(out.read_text(encoding="utf-8"))
    assert verification["status"] == "failed"
    assert verification["materialization_allowed_by_contract_verification"] is False
    assert any("unavailable" in item for item in verification["violations"])
    assert verification["effect"]["candidate_program_materialized"] is False
    assert not (tmp_path / "manifest.json").exists()


def test_architecture_planner_refuses_candidate_artifact_output(tmp_path: Path) -> None:
    intent_path = tmp_path / "intent.yaml"
    _write_intent(intent_path, "Answer a question from context.")

    result = runner.invoke(
        app,
        [
            "program-architect",
            "plan",
            "--intent",
            str(intent_path),
            "--out",
            str(tmp_path / "manifest.json"),
        ],
    )

    assert result.exit_code == 2
    assert "refusing to write architecture plan" in result.output

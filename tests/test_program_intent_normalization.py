from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from dspx.cache import sha256_text
from dspx.cli.dspx import app
from dspx.services.program_architecture import build_program_architecture_candidates
from dspx.services.program_intent import ProgramIntent, load_program_intent
from dspx.services.program_intent_normalization import (
    normalize_program_intent_from_prompt,
)

runner = CliRunner()


def test_prompt_normalization_emits_valid_intent_hints_and_missing_evidence() -> None:
    payload = normalize_program_intent_from_prompt(
        "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale."
    )

    assert payload["schema_version"] == "program-intent-normalization-v1"
    assert payload["status"] == "normalized"
    intent = ProgramIntent.model_validate(payload["normalized_intent"])
    assert intent.inputs == ["ticket_text"]
    assert intent.outputs == ["response"]
    assert intent.examples == []
    assert {item["kind"] for item in payload["missing_evidence"]} >= {
        "examples",
        "dataset",
    }
    assert [hint["hint"] for hint in payload["topology_hints"]] == [
        "route_then_generate",
        "reasoned_single_module",
    ]
    assert [hint["primitive"] for hint in payload["primitive_hints"]] == [
        "Predict",
        "ChainOfThought",
    ]
    assert payload["effect"]["program_materialized"] is False
    assert payload["effect"]["provider_called"] is False
    assert payload["effect"]["oracle_index_mutated"] is False
    assert payload["non_authority"]["normalization_only"] is True
    assert payload["non_authority"]["winner_selection"] is False


def test_prompt_normalization_surfaces_unsupported_primitive_risk() -> None:
    payload = normalize_program_intent_from_prompt(
        "Use retrieval and ReAct tools to answer the question from documents.",
        inputs=["question", "document_text"],
        outputs=["answer"],
    )

    primitive_hints = payload["primitive_hints"]
    assert any(hint["primitive"] == "Retriever" for hint in primitive_hints)
    assert any(hint["primitive"] == "ReAct" for hint in primitive_hints)
    assert any(
        risk["kind"] == "unsupported_primitive" for risk in payload["generation_risks"]
    )
    intent = ProgramIntent.model_validate(payload["normalized_intent"])
    assert intent.inputs == ["question", "document_text"]
    assert intent.outputs == ["answer"]


def test_normalize_intent_cli_writes_sidecar_and_loadable_intent(
    tmp_path: Path,
) -> None:
    sidecar_path = tmp_path / "normalization.json"
    intent_path = tmp_path / "normalized_intent.json"

    result = runner.invoke(
        app,
        [
            "program-gen",
            "normalize-intent",
            "--prompt",
            "Review evidence and explain the strongest recommendation.",
            "--input",
            "evidence",
            "--output",
            "recommendation",
            "--out",
            str(sidecar_path),
            "--normalized-intent-out",
            str(intent_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
    stdout_payload = json.loads(result.output)
    assert stdout_payload == payload
    without_artifact = dict(payload)
    artifact = dict(without_artifact.pop("artifact"))
    assert artifact["payload_hash_excluding_artifact"] == sha256_text(
        json.dumps(without_artifact, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    )
    loaded = load_program_intent(intent_path)
    assert loaded.inputs == ["evidence"]
    assert loaded.outputs == ["recommendation"]
    assert payload["normalized_intent_artifact"]["path"] == str(intent_path.resolve())
    assert payload["effect"]["normalized_intent_written"] is True
    assert not (tmp_path / "manifest.json").exists()
    assert not (tmp_path / "program.py").exists()
    assert not (tmp_path / "oracle" / "coordinates.db").exists()


def test_normalized_intent_feeds_architecture_plan_without_materialization(
    tmp_path: Path,
) -> None:
    sidecar_path = tmp_path / "normalization.json"
    intent_path = tmp_path / "normalized_intent.json"
    plan_path = tmp_path / "architecture_plan.json"

    normalize_result = runner.invoke(
        app,
        [
            "program-gen",
            "normalize-intent",
            "--prompt",
            "Route support tickets by classifying billing versus technical issues, then draft a helpful response with rationale.",
            "--out",
            str(sidecar_path),
            "--normalized-intent-out",
            str(intent_path),
        ],
    )
    assert normalize_result.exit_code == 0, normalize_result.output

    plan_result = runner.invoke(
        app,
        [
            "program-architect",
            "plan",
            "--intent",
            str(intent_path),
            "--out",
            str(plan_path),
        ],
    )

    assert plan_result.exit_code == 0, plan_result.output
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan["schema_version"] == "program-architecture-candidates-v1"
    assert plan["recommended_candidate_id"] == "prompt_inferred_pipeline"
    assert plan["effect"]["candidate_materialized"] is False
    assert not (tmp_path / "manifest.json").exists()
    assert not (tmp_path / "program.py").exists()
    assert (
        build_program_architecture_candidates(load_program_intent(intent_path))[
            "recommended_candidate_id"
        ]
        == "prompt_inferred_pipeline"
    )


def test_normalize_intent_cli_requires_exactly_one_source(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "program-gen",
            "normalize-intent",
            "--out",
            str(tmp_path / "normalization.json"),
        ],
    )

    assert result.exit_code == 2
    assert "exactly one" in result.output

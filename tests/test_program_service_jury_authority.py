from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.services import program_service
from dspx.services.program_service import ProgramIntent, materialize_program_from_intent

runner = CliRunner()


@pytest.mark.slow
def test_program_gen_cli_materializes_explicit_perspectives_without_bound_jurors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent_path = tmp_path / "intent.yaml"
    intent_path.write_text(
        "\n".join(
            [
                "name: ReviewProgram",
                "objective: Create review-only transition artifacts from source text.",
                "inputs:",
                "  - source_text",
                "outputs:",
                "  - review_packet_json",
                "jury:",
                "  selection_model: perspective_balanced_explicit_pool",
                "  minimum_jurors: 3",
                "  perspectives:",
                "    - source_grounding",
                "    - authority_boundaries",
                "    - transition_artifact_quality",
            ]
        ),
        encoding="utf-8",
    )
    outdir = tmp_path / "candidate"

    result = runner.invoke(
        app,
        ["program-gen", "--intent", str(intent_path), "--outdir", str(outdir)],
    )

    assert result.exit_code == 0, result.output
    jury = json.loads((outdir / "jury.json").read_text(encoding="utf-8"))
    assert jury["perspectives"] == [
        "source_grounding",
        "authority_boundaries",
        "transition_artifact_quality",
    ]
    assert jury["pool"]["explicit_juror_count"] == 0
    assert jury["pool"]["explicit_perspective_count"] == 3
    assert jury["pool"]["explicit_perspective_juror_count"] == 3
    assert jury["jurors"][:3] == [
        {
            "id": "explicit_source_grounding",
            "model": None,
            "perspective": "source_grounding",
            "source": "explicit_perspective",
            "reason": "declared in jury.perspectives without a bound juror model",
        },
        {
            "id": "explicit_authority_boundaries",
            "model": None,
            "perspective": "authority_boundaries",
            "source": "explicit_perspective",
            "reason": "declared in jury.perspectives without a bound juror model",
        },
        {
            "id": "explicit_transition_artifact_quality",
            "model": None,
            "perspective": "transition_artifact_quality",
            "source": "explicit_perspective",
            "reason": "declared in jury.perspectives without a bound juror model",
        },
    ]
    selection = json.loads((outdir / "jury_selection.json").read_text(encoding="utf-8"))
    assert selection["selected_perspectives"] == [
        "source_grounding",
        "authority_boundaries",
        "transition_artifact_quality",
    ]
    assert [item["id"] for item in selection["selected_jurors"]] == [
        "explicit_source_grounding",
        "explicit_authority_boundaries",
        "explicit_transition_artifact_quality",
    ]
    rubric = json.loads((outdir / "jury_rubric.json").read_text(encoding="utf-8"))
    assert [item["criteria"] for item in rubric["juror_rubrics"]] == [
        ["source_refs_preserved", "source_identity_not_invented"],
        ["canonical_mutation_forbidden", "review_authority_explicit"],
        ["artifact_family_clarity", "proposal_reviewability"],
    ]


@pytest.mark.slow
def test_program_gen_cli_carries_explicit_jury_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent_path = tmp_path / "intent.yaml"
    intent_path.write_text(
        "\n".join(
            [
                "name: JuryProgram",
                "objective: Answer with evidence.",
                "inputs:",
                "  - question",
                "outputs:",
                "  - answer",
                "jury:",
                "  selection_model: perspective_balanced_explicit_pool",
                "  minimum_jurors: 3",
                "  perspectives:",
                "    - correctness",
                "    - robustness",
                "    - clarity",
                "  jurors:",
                "    - id: correctness_local",
                "      model: local-small",
                "      perspective: correctness",
                "    - id: robustness_remote",
                "      model: remote-large",
                "      provider: pi-rpc",
                "      perspective: robustness",
                "    - id: clarity_local",
                "      model: local-medium",
                "      perspective: clarity",
                "promotion:",
                "  adjudicator:",
                "    kind: ai_council",
                "    id: safety_quality_council",
                "    members:",
                "      - safety_agent",
                "      - quality_agent",
            ]
        ),
        encoding="utf-8",
    )
    outdir = tmp_path / "candidate"

    result = runner.invoke(
        app,
        ["program-gen", "--intent", str(intent_path), "--outdir", str(outdir)],
    )

    assert result.exit_code == 0, result.output
    plan = json.loads((outdir / "plan.json").read_text(encoding="utf-8"))
    jury = plan["evaluation_strategy"]
    assert json.loads((outdir / "jury.json").read_text(encoding="utf-8")) == jury
    assert jury["schema_version"] == "program-jury-v1"
    assert jury["mode"] == "jury"
    assert jury["minimum_jurors"] == 3
    assert jury["perspectives"] == ["correctness", "robustness", "clarity"]
    assert jury["jurors"][0] == {
        "id": "correctness_local",
        "model": "local-small",
        "perspective": "correctness",
        "source": "explicit_user",
    }
    assert jury["jurors"][1] == {
        "id": "robustness_remote",
        "model": "remote-large",
        "perspective": "robustness",
        "provider": "pi-rpc",
        "source": "explicit_user",
    }
    assert jury["jurors"][2] == {
        "id": "clarity_local",
        "model": "local-medium",
        "perspective": "clarity",
        "source": "explicit_user",
    }
    selection = json.loads((outdir / "jury_selection.json").read_text(encoding="utf-8"))
    assert selection["schema_version"] == "program-jury-selection-v1"
    assert selection["status"] == "selected"
    assert selection["selected_juror_count"] == 3
    assert selection["selected_perspectives"] == [
        "correctness",
        "robustness",
        "clarity",
    ]
    assert [item["id"] for item in selection["selected_jurors"]] == [
        "correctness_local",
        "robustness_remote",
        "clarity_local",
    ]
    assert selection["authority"] == "selection_contract_only_non_authoritative"
    rubric = json.loads((outdir / "jury_rubric.json").read_text(encoding="utf-8"))
    assert rubric["schema_version"] == "program-jury-rubric-v1"
    assert rubric["selected_juror_count"] == 3
    assert [item["perspective"] for item in rubric["juror_rubrics"]] == [
        "correctness",
        "robustness",
        "clarity",
    ]
    assert rubric["juror_rubrics"][0]["criteria"] == [
        "answer_correctness",
        "objective_satisfaction",
    ]
    assert rubric["authority"] == "rubric_contract_only_non_authoritative"
    assert jury["status"] == "planned_not_executed"
    assert jury["authority"] == "advisory_evidence_only"
    manifest = json.loads((outdir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["intent"]["jury"]["minimum_jurors"] == 3
    receipt = json.loads(
        (outdir / "manifest.json.meta.json").read_text(encoding="utf-8")
    )
    promotion_review = json.loads(
        (outdir / "promotion_review.json").read_text(encoding="utf-8")
    )
    assert promotion_review["adjudicator"] == {
        "kind": "ai_council",
        "id": "safety_quality_council",
        "authority": "required_for_promotion",
        "status": "pending",
        "members": ["safety_agent", "quality_agent"],
    }
    assert promotion_review["decision"]["status"] == "pending"
    assert (
        "no_promotion_adjudicator_decision" in promotion_review["blocking_conditions"]
    )
    adjudication_request = json.loads(
        (outdir / "promotion_adjudication_request.json").read_text(encoding="utf-8")
    )
    assert adjudication_request["adjudicator"] == promotion_review["adjudicator"]
    decision_template = json.loads(
        (outdir / "promotion_decision_template.json").read_text(encoding="utf-8")
    )
    assert decision_template == {
        "schema_version": "program-promotion-decision-v1",
        "status": "pending",
        "outcome": None,
        "decided_by": None,
        "adjudicator_ref": "safety_quality_council",
        "adjudicator_kind": "ai_council",
        "rationale": None,
        "evidence_refs": [],
    }
    assert adjudication_request["decision_record_template"] == decision_template
    assert receipt["program_plan"]["evaluation_strategy"] == jury
    assert receipt["program_jury_selection"] == selection
    assert receipt["program_jury_rubric"] == rubric
    assert receipt["program_promotion_review"] == promotion_review
    assert receipt["program_promotion_adjudication_request"] == adjudication_request
    assert receipt["program_promotion_decision_template"] == decision_template


@pytest.mark.slow
def test_program_gen_cli_preserves_external_authority_refs_without_adapter_coupling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    real_run = program_service.subprocess.run
    subprocess_calls: list[list[str]] = []

    def spy_run(
        command: list[str], *args: Any, **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        command_text = [str(part) for part in command]
        command_names = [Path(part).name for part in command_text]
        assert "ak" not in command_names
        subprocess_calls.append(command_text)
        return cast(
            subprocess.CompletedProcess[str], real_run(command, *args, **kwargs)
        )

    monkeypatch.setattr(program_service.subprocess, "run", spy_run)
    intent_path = tmp_path / "intent.yaml"
    intent_path.write_text(
        "\n".join(
            [
                "name: ExternalAuthorityProgram",
                "objective: Answer with portable local evidence only.",
                "inputs:",
                "  - question",
                "outputs:",
                "  - answer",
                "promotion:",
                "  adjudicator:",
                "    kind: human_operator",
                "    id: local_operator",
                "  external_authority:",
                "    refs:",
                "      - system: agent_kernel",
                "        ref: AK-1234",
                "        role: optional_authority_export_target",
            ]
        ),
        encoding="utf-8",
    )
    outdir = tmp_path / "candidate"

    result = runner.invoke(
        app,
        ["program-gen", "--intent", str(intent_path), "--outdir", str(outdir)],
    )

    assert result.exit_code == 0, result.output
    assert subprocess_calls
    assert all(
        "ak" not in [Path(part).name for part in command]
        for command in subprocess_calls
    )
    promotion_review = json.loads(
        (outdir / "promotion_review.json").read_text(encoding="utf-8")
    )
    assert promotion_review["adjudicator"] == {
        "kind": "human_operator",
        "id": "local_operator",
        "authority": "required_for_promotion",
        "status": "pending",
    }
    assert promotion_review["external_authority"] == {
        "status": "not_exported",
        "refs": [
            {
                "system": "agent_kernel",
                "ref": "AK-1234",
                "role": "optional_authority_export_target",
                "status": "not_exported",
                "source": "promotion.external_authority.refs",
            }
        ],
        "notes": [
            "External authority references are preserved as opaque metadata.",
            "DSPx core does not validate, call, or mutate external authority systems.",
        ],
    }
    assert "supported_adapters" not in promotion_review["external_authority"]
    assert promotion_review["promotion_state"] == "not_promoted"
    assert promotion_review["non_authority"]["automatic_promotion"] is False
    assert promotion_review["non_authority"]["ranking_pruning_promotion"] is False
    assert promotion_review["non_authority"]["external_authority_export"] is False
    adjudication_request = json.loads(
        (outdir / "promotion_adjudication_request.json").read_text(encoding="utf-8")
    )
    assert adjudication_request["adjudicator"] == promotion_review["adjudicator"]
    assert (
        adjudication_request["external_authority"]
        == promotion_review["external_authority"]
    )
    decision_template = json.loads(
        (outdir / "promotion_decision_template.json").read_text(encoding="utf-8")
    )
    assert decision_template == adjudication_request["decision_record_template"]
    assert decision_template["adjudicator_kind"] == "human_operator"
    assert decision_template["adjudicator_ref"] == "local_operator"
    assert decision_template["decided_by"] is None
    assert "external_authority" not in decision_template
    manifest = json.loads((outdir / "manifest.json").read_text(encoding="utf-8"))
    assert (
        manifest["intent"]["promotion"]["external_authority"]["refs"][0]["ref"]
        == "AK-1234"
    )
    assert manifest["program_promotion_review"] == promotion_review
    assert manifest["program_promotion_adjudication_request"] == adjudication_request
    assert manifest["program_promotion_decision_template"] == decision_template
    receipt = json.loads(
        (outdir / "manifest.json.meta.json").read_text(encoding="utf-8")
    )
    assert receipt["program_promotion_review"] == promotion_review
    assert receipt["program_promotion_adjudication_request"] == adjudication_request
    assert receipt["program_promotion_decision_template"] == decision_template


@pytest.mark.slow
def test_program_service_rejects_external_adapter_as_adjudicator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent = ProgramIntent(
        name="WrongLayerProgram",
        objective="Preserve the adjudicator versus adapter boundary.",
        inputs=["question"],
        outputs=["answer"],
        promotion={"adjudicator": {"kind": "external_adapter", "id": "AK-1234"}},
    )

    with pytest.raises(ValueError, match="decision actor/process"):
        materialize_program_from_intent(intent, outdir=tmp_path / "wrong-layer")

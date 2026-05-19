from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from dspx.cli.dspx import app


runner = CliRunner()
FIXTURE_INTENT = Path("tests/fixtures/program_gen/pdf_transition/intent.yaml")


def _designmd_requirements_packet() -> dict:
    return {
        "schemaVersion": "designmd.dspx-visual-dossier-requirements.v1",
        "id": "vdspx_cli",
        "projectId": "default",
        "sourceId": "vsrc_cli",
        "analysisRunId": "vrun_cli",
        "dossierDraftId": "vdossier_cli",
        "generatedAt": "2026-05-18T00:00:00.000Z",
        "ownerBoundary": {
            "designmdMayDefineRequirements": True,
            "dspxOwnsTargetProtocol": True,
            "noProgramGenExecution": True,
            "statement": "DSPx owner surface must own/review target protocol.",
        },
        "inputRefs": {
            "sourceIndexSchema": "designmd.visual-source-index.v1",
            "analysisRunSchema": "designmd.analysis-run.v1",
            "dossierDraftSchema": "designmd.dossier-draft.v1",
            "sourceIndexSha256": "source-sha",
            "designMdSha256": "design-sha",
            "designMdCurrentSha256": "design-sha",
            "freshness": {"status": "current"},
        },
        "requiredTargetProtocolContent": ["Authority statements"],
        "requiredOutputSchemas": ["designmd.component-inventory.v1"],
        "roleCoverage": ["visual designer"],
        "fixtureRequirements": ["stale DESIGN.md hash case"],
        "fitnessGates": ["DSPx target-protocol owner review"],
        "failClosedBlockers": ["Candidate attempts to mutate DESIGN.md"],
        "acceptedOutputPosture": ["proposal_context", "review_evidence"],
        "forbiddenClaims": ["accepted_contract_truth", "reviewed_dossier_guidance"],
        "authority": {"statement": "Does not mutate DESIGN.md."},
    }


def test_program_gen_requirements_intake_cli_emits_native_gate_artifacts(
    tmp_path: Path,
) -> None:
    requirements = tmp_path / "designmd_requirements.json"
    outdir = tmp_path / "intake"
    requirements.write_text(
        json.dumps(_designmd_requirements_packet()), encoding="utf-8"
    )

    result = runner.invoke(
        app,
        [
            "program-gen",
            "requirements-intake",
            "--profile",
            "designmd-visual-dossier",
            "--requirements",
            str(requirements),
            "--outdir",
            str(outdir),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "gen-requirements-intake-v1"
    assert payload["generation_gate_preflight"]["generation_allowed"] is True
    assert outdir.joinpath("generation_target_contract.json").exists()
    assert outdir.joinpath("generation_fitness_suite.json").exists()
    assert outdir.joinpath("generation_gate_preflight.json").exists()
    contract_payload = json.loads(
        outdir.joinpath("generation_target_contract.json").read_text(encoding="utf-8")
    )
    assert contract_payload["schema_version"] == "gen-target-contract-v1"
    assert contract_payload["target"]["id"] == "designmd_visual_dossier"


def test_program_gen_requirements_intake_cli_blocks_incomplete_packet(
    tmp_path: Path,
) -> None:
    requirements = tmp_path / "designmd_requirements.json"
    outdir = tmp_path / "intake"
    requirements.write_text(json.dumps({"schemaVersion": "wrong"}), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "program-gen",
            "requirements-intake",
            "--profile",
            "designmd-visual-dossier",
            "--requirements",
            str(requirements),
            "--outdir",
            str(outdir),
            "--json",
        ],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["generation_gate_preflight"]["status"] == "generation_blocked"
    assert payload["generation_gate_preflight"]["generation_allowed"] is False
    assert (
        "invalid_schema_version"
        in payload["generation_gate_preflight"]["fail_closed_reasons"]
    )
    assert outdir.joinpath("generation_gate_preflight.json").exists()


def test_program_gen_target_fidelity_cli_preflight_and_gated_generation(
    tmp_path: Path,
) -> None:
    contract = tmp_path / "generation_target_contract.json"
    suite = tmp_path / "generation_fitness_suite.json"
    preflight = tmp_path / "generation_gate_preflight.json"
    outdir = tmp_path / "program"
    traceability = tmp_path / "generation_traceability.json"
    fitness_results = tmp_path / "generation_fitness_results.json"

    result = runner.invoke(
        app,
        [
            "program-gen",
            "target-contract",
            "--intent",
            str(FIXTURE_INTENT),
            "--out",
            str(contract),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    contract_payload = json.loads(result.stdout)
    assert contract_payload["schema_version"] == "gen-target-contract-v1"
    assert contract_payload["risk_tier"] == "authority_adjacent"
    assert contract.exists()

    result = runner.invoke(
        app,
        [
            "program-gen",
            "fitness-suite",
            "--target-contract",
            str(contract),
            "--out",
            str(suite),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    suite_payload = json.loads(result.stdout)
    assert suite_payload["schema_version"] == "gen-fitness-suite-v1"
    assert suite.exists()

    result = runner.invoke(
        app,
        [
            "program-gen",
            "verify-generation-gate",
            "--intent",
            str(FIXTURE_INTENT),
            "--target-contract",
            str(contract),
            "--fitness-suite",
            str(suite),
            "--out",
            str(preflight),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    preflight_payload = json.loads(result.stdout)
    assert preflight_payload["schema_version"] == "gen-generation-gate-preflight-v1"
    assert preflight_payload["generation_allowed"] is True
    assert preflight.exists()

    result = runner.invoke(
        app,
        [
            "program-gen",
            "--intent",
            str(FIXTURE_INTENT),
            "--outdir",
            str(outdir),
            "--generation-gate-preflight",
            str(preflight),
            "--print-manifest",
        ],
    )

    assert result.exit_code == 0, result.output
    manifest = json.loads(result.stdout)
    assert manifest["schema_version"] == "program-candidate-assembly-v1"
    assert outdir.joinpath("manifest.json").exists()

    result = runner.invoke(
        app,
        [
            "program-gen",
            "traceability",
            "--manifest",
            str(outdir / "manifest.json"),
            "--target-contract",
            str(contract),
            "--out",
            str(traceability),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    traceability_payload = json.loads(result.stdout)
    assert traceability_payload["schema_version"] == "gen-traceability-v1"
    assert traceability_payload["requirements"]
    assert traceability.exists()

    result = runner.invoke(
        app,
        [
            "program-gen",
            "fitness-results",
            "--manifest",
            str(outdir / "manifest.json"),
            "--target-contract",
            str(contract),
            "--fitness-suite",
            str(suite),
            "--traceability",
            str(traceability),
            "--out",
            str(fitness_results),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    fitness_payload = json.loads(result.stdout)
    assert fitness_payload["schema_version"] == "gen-fitness-results-v1"
    assert fitness_payload["status"] == "fitness_passed"
    assert (
        fitness_payload["rendered_state"] == "eligible_for_downstream_evidence_review"
    )
    assert fitness_results.exists()


def test_program_gen_blocks_candidate_creation_when_preflight_blocks(
    tmp_path: Path,
) -> None:
    blocked = tmp_path / "blocked_generation_gate_preflight.json"
    blocked.write_text(
        json.dumps(
            {
                "schema_version": "gen-generation-gate-preflight-v1",
                "status": "generation_blocked",
                "generation_allowed": False,
                "fail_closed_reasons": ["insufficient_target_contract"],
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "program-gen",
            "--intent",
            str(FIXTURE_INTENT),
            "--outdir",
            str(tmp_path / "program"),
            "--generation-gate-preflight",
            str(blocked),
        ],
    )

    assert result.exit_code == 2
    assert "generation gate blocked candidate creation" in result.output
    assert not tmp_path.joinpath("program", "manifest.json").exists()

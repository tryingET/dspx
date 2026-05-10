from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from dspx.cli.dspx import app


runner = CliRunner()
FIXTURE_INTENT = Path("tests/fixtures/program_gen/pdf_transition/intent.yaml")


def test_program_gen_target_fidelity_cli_preflight_and_gated_generation(
    tmp_path: Path,
) -> None:
    contract = tmp_path / "generation_target_contract.json"
    suite = tmp_path / "generation_fitness_suite.json"
    preflight = tmp_path / "generation_gate_preflight.json"
    outdir = tmp_path / "program"

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

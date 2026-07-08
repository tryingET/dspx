from __future__ import annotations

import hashlib
import json
from pathlib import Path

from typer.testing import CliRunner

from dspx.coordinates import reset_embedding_engine
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_service import materialize_program_from_intent

runner = CliRunner()
QUARANTINED_NEGATIVE_FIXTURE = Path(
    "tests/fixtures/program_gen/pdf_transition/quarantined_invalid_outputs.json"
)


def _quarantined_negative_fixture() -> dict:
    return json.loads(QUARANTINED_NEGATIVE_FIXTURE.read_text(encoding="utf-8"))


def _setup_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    reset_embedding_engine()


def _materialize_obsidian_like_candidate(tmp_path: Path, monkeypatch) -> Path:
    _setup_env(tmp_path, monkeypatch)
    intent = ProgramIntent(
        name="ObsidianPdfTransitionReviewer",
        objective=(
            "Transform PDF source package evidence into review-only Obsidian Wiki "
            "transition proposals without canonical Atlas or Wiki mutation."
        ),
        inputs=["marker_markdown", "source_package_json", "existing_wiki_index_json"],
        outputs=["review_packet_json", "merge_create_proposals_json"],
        metric="exact_match",
        constraints=[
            "Preserve Zotero/source identity and source refs.",
            "All Wiki or Atlas targets require review_required=true.",
            "Canonical mutation is forbidden during generation.",
        ],
        examples=[
            {
                "inputs": {
                    "marker_markdown": "# Close Reading\nUse source-grounded evidence.",
                    "source_package_json": '{"source_id":"zotero:user:demo/DEMO2026"}',
                    "existing_wiki_index_json": "{}",
                },
                "outputs": {
                    "review_packet_json": '{"canonical_mutation_performed":false}',
                    "merge_create_proposals_json": "[]",
                },
            }
        ],
        promotion={
            "adjudicator": {"kind": "ai_agent", "id": "dspx_program_adjudicator_v1"}
        },
    )
    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    return Path(artifact.root_path)


def _write_minimal_activation_packet(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "generated-cognition-program-production-activation-packet-v1",
                "canonical_binding_ref": None,
                "boundary_checks": {
                    "dspx_activation_authority": False,
                    "jury_promotion_authority": False,
                    "oracle_promotion_authority": False,
                },
                "effect": {
                    "production_activation_applied": False,
                    "ak_mutated": False,
                    "external_authority_mutated": False,
                },
                "non_authority": {"governance_authority": False},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _candidate_manifest_hash_for_sidecar(path: Path) -> str:
    manifest_path = path.parent / "manifest.json"
    if manifest_path.exists():
        return hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    return "candidate-sha"


def _write_generation_fitness_results(
    path: Path, *, status: str = "fitness_passed"
) -> None:
    rendered_state = (
        "eligible_for_downstream_evidence_review"
        if status == "fitness_passed"
        else "withheld_for_target_protocol_failure"
    )
    candidate_sha = _candidate_manifest_hash_for_sidecar(path)
    path.write_text(
        json.dumps(
            {
                "schema_version": "gen-fitness-results-v1",
                "identity": {
                    "candidate_manifest_sha256": candidate_sha,
                    "target_contract_sha256": "contract-sha",
                    "fitness_suite_sha256": "suite-sha",
                },
                "status": status,
                "rendered_state": rendered_state,
                "cases": [
                    {
                        "case_id": "target-protocol-fidelity",
                        "status": "passed" if status == "fitness_passed" else "failed",
                        "evidence_refs": ["generation_traceability.json"],
                    }
                ],
                "non_authority": {
                    "activation_authority": False,
                    "promotion_authority": False,
                    "oracle_authority": False,
                    "governance_authority": False,
                    "external_mutation": False,
                },
                "effect": {
                    "candidate_files_mutated": False,
                    "canonical_target_mutated": False,
                    "ak_mutated": False,
                    "governance_mutated": False,
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_generation_traceability(path: Path) -> None:
    candidate_sha = _candidate_manifest_hash_for_sidecar(path)
    path.write_text(
        json.dumps(
            {
                "schema_version": "gen-traceability-v1",
                "identity": {
                    "candidate_manifest_sha256": candidate_sha,
                    "target_contract_sha256": "contract-sha",
                },
                "requirements": [
                    {
                        "requirement_id": "review-boundary",
                        "generated_surfaces": ["program.py", "module.py"],
                        "evidence_refs": ["generation_fitness_results.json"],
                        "status": "covered",
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import yaml
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.coordinates import reset_embedding_engine

runner = CliRunner()

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "program_gen" / "pdf_transition"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _all_files(root: Path) -> set[Path]:
    if not root.exists():
        return set()
    return {path for path in root.rglob("*") if path.is_file()}


def _load_json_text(value: object) -> object:
    assert isinstance(value, str)
    return json.loads(value)


def test_pdf_transition_program_gen_scenario_materializes_reviewable_artifacts_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    reset_embedding_engine()

    wiki_root = tmp_path / "vault" / "Wiki"
    wiki_root.mkdir(parents=True)
    canonical_note = wiki_root / "Close Reading.md"
    canonical_note.write_text(
        "# Close Reading\n\nCanonical note must not be mutated by program-gen.\n",
        encoding="utf-8",
    )
    canonical_before = _sha256(canonical_note)
    transition_root = tmp_path / "vault" / "_System" / "pdf-pipeline" / "transition"
    transition_before = _all_files(transition_root)

    intent_path = FIXTURE_ROOT / "intent.yaml"
    examples_path = FIXTURE_ROOT / "examples.yaml"
    intent_payload = yaml.safe_load(intent_path.read_text(encoding="utf-8"))
    example_payload = yaml.safe_load(examples_path.read_text(encoding="utf-8"))[0]
    outdir = tmp_path / "program"

    result = runner.invoke(
        app,
        [
            "program-gen",
            "--intent",
            str(intent_path),
            "--outdir",
            str(outdir),
            "--print-manifest",
        ],
    )

    assert result.exit_code == 0, result.output
    manifest = json.loads(result.stdout)
    assert manifest["schema_version"] == "program-candidate-assembly-v1"
    assert manifest["intent"]["options"]["scenario_name"] == (
        "pdf-transition-program-gen"
    )
    assert manifest["intent"]["options"]["authority_model"] == {
        "source": "raw extraction/source package artifact",
        "transition": "section units, distillation frames, and evidence cards",
        "proposal": "merge/create candidates",
        "review": "review packet",
        "canonical": "Wiki/Atlas note only after explicit review",
    }
    assert set(manifest["intent"]["outputs"]) == set(intent_payload["outputs"])
    assert manifest["program_promotion_review"]["promotion_state"] == "not_promoted"
    assert manifest["program_promotion_review"]["candidate_status"] == "exploratory"

    expected_outputs = example_payload["outputs"]
    section_units = _load_json_text(expected_outputs["section_units_json"])
    distillation_frames = _load_json_text(expected_outputs["distillation_frames_json"])
    evidence_cards = _load_json_text(expected_outputs["evidence_cards_json"])
    merge_create = _load_json_text(expected_outputs["merge_create_proposals_json"])
    review_packet = _load_json_text(expected_outputs["review_packet_json"])
    contract = _load_json_text(expected_outputs["artifact_contract_manifest_json"])

    assert section_units[0]["artifact_family"] == "transition"
    assert section_units[0]["artifact_type"] == "section_unit_candidate"
    assert distillation_frames[0]["artifact_family"] == "transition"
    assert set(distillation_frames[0]) >= {
        "paraphrase",
        "thesis",
        "logic",
        "evaluation",
        "application",
    }
    assert evidence_cards[0]["artifact_family"] == "transition"
    assert evidence_cards[0]["source_refs"]
    assert merge_create[0]["artifact_family"] == "proposal"
    assert merge_create[0]["proposed_action"] == "enrich"
    assert merge_create[0]["target_path"] == "Wiki/Close Reading.md"
    assert merge_create[0]["canonical_mutation_allowed"] is False
    assert merge_create[0]["review_required"] is True
    assert review_packet["artifact_family"] == "review"
    assert review_packet["canonical_mutation_performed"] is False
    assert contract["schema_version"] == "pdf-transition-artifact-contract-v1"
    assert contract["artifact_family_authority"] == {
        "source": "raw extraction/source package authority",
        "transition": "regenerable source-grounded transition artifacts",
        "proposal": "merge/create proposal artifacts only",
        "review": "human/operator review artifacts",
        "canonical": "Wiki/Atlas artifacts only after explicit review",
    }
    assert contract["canonical_mutation_performed"] is False
    assert "canonical_wiki_mutation" in contract["forbidden_effects"]

    module_spec = importlib.util.spec_from_file_location(
        "pdf_transition_generated_module", outdir / "module.py"
    )
    assert module_spec is not None
    assert module_spec.loader is not None
    generated_module = importlib.util.module_from_spec(module_spec)
    old_path = list(sys.path)
    try:
        sys.path.insert(0, str(outdir))
        module_spec.loader.exec_module(generated_module)
    finally:
        sys.path[:] = old_path
    gold, pred = generated_module.normalize_output(
        "section_units_json",
        expected_outputs["section_units_json"],
        json.dumps(section_units, separators=(",", ":")),
    )
    assert gold == pred

    behavior_results = json.loads((outdir / "behavior_results.json").read_text())
    behavior_episode = json.loads((outdir / "behavior_episode.json").read_text())
    receipt_meta = json.loads((outdir / "manifest.json.meta.json").read_text())
    assert behavior_results["schema_version"] == "program-behavior-results-v1"
    assert behavior_results["examples"][0]["expected_outputs"] == expected_outputs
    assert behavior_episode["schema_version"] == "program-behavior-episode-v1"
    assert behavior_episode["authority"] == "behavior_evidence_only_non_authoritative"
    assert receipt_meta["run_kind"] == "program-gen"
    assert receipt_meta["run_summary"]["backend"] == "program_candidate_assembly"
    assert receipt_meta["program_promotion_review"]["promotion_state"] == "not_promoted"

    replay = runner.invoke(
        app,
        [
            "run",
            "replay",
            "--from",
            str(outdir / "manifest.json.meta.json"),
            "--check-only",
            "--json",
        ],
    )
    assert replay.exit_code == 0, replay.output
    replay_payload = json.loads(replay.stdout)
    assert replay_payload["status"] == "ok"
    assert replay_payload["checks"]["program_execution_episode_hash_match"] is True
    assert replay_payload["checks"]["program_behavior_results_hash_match"] is True

    assert canonical_note.exists()
    assert _sha256(canonical_note) == canonical_before
    assert _all_files(transition_root) == transition_before
    assert not (wiki_root / "Close Reading.proposal.md").exists()
    assert not (wiki_root / "Close Reading.transition.json").exists()
    assert not (tmp_path / "generated" / "oracle" / "coordinates.db").exists()
    assert all(path.is_relative_to(outdir) for path in _all_files(outdir))

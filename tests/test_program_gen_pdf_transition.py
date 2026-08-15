# summary: "End-to-end tests for PDF-transition program generation, review artifacts, replay evidence, and MLflow observability."
# read_when:
#   - "Changing the PDF-transition generation scenario, generated artifact contract, replay checks, or program observability."

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any, cast

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


def _load_json_text(value: object) -> Any:
    assert isinstance(value, str)
    return json.loads(value)


class _FakeRun:
    pass


class _FakeMlflowBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.logged_artifact_files: list[str] = []
        self.fail_log_artifacts = False
        self._active: _FakeRun | None = None

    def set_tracking_uri(self, uri: str) -> None:
        self.calls.append(("set_tracking_uri", uri))

    def set_experiment(self, name: str) -> None:
        self.calls.append(("set_experiment", name))

    def active_run(self):
        return self._active

    def start_run(self, run_name: str | None = None) -> _FakeRun:
        self.calls.append(("start_run", run_name))
        self._active = _FakeRun()
        return self._active

    def end_run(self, status: str | None = None) -> None:
        self.calls.append(("end_run", status) if status is not None else ("end_run",))
        self._active = None

    def set_tag(self, key: str, value: str) -> None:
        self.calls.append(("set_tag", key, value))

    def log_param(self, key: str, value: str) -> None:
        self.calls.append(("log_param", key, value))

    def log_metric(self, key: str, value: float) -> None:
        self.calls.append(("log_metric", key, value))

    def log_artifacts(self, path: str) -> None:
        self.calls.append(("log_artifacts", path))
        if self.fail_log_artifacts:
            raise RuntimeError("artifact store down")
        root = Path(path)
        if root.exists():
            self.logged_artifact_files = sorted(
                item.relative_to(root).as_posix()
                for item in root.rglob("*")
                if item.is_file()
            )

    def dspy_autolog(self, **kwargs: object) -> None:
        self.calls.append(("dspy.autolog", tuple(sorted(kwargs))))


def _install_fake_mlflow(monkeypatch) -> _FakeMlflowBackend:
    backend = _FakeMlflowBackend()
    mod = types.ModuleType("mlflow")
    setattr(mod, "set_tracking_uri", backend.set_tracking_uri)
    setattr(mod, "set_experiment", backend.set_experiment)
    setattr(mod, "active_run", backend.active_run)
    setattr(mod, "start_run", backend.start_run)
    setattr(mod, "end_run", backend.end_run)
    setattr(mod, "set_tag", backend.set_tag)
    setattr(mod, "log_param", backend.log_param)
    setattr(mod, "log_metric", backend.log_metric)
    setattr(mod, "log_artifacts", backend.log_artifacts)
    setattr(mod, "dspy", types.SimpleNamespace(autolog=backend.dspy_autolog))
    monkeypatch.setitem(sys.modules, "mlflow", mod)
    return backend


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
        "frontmatter_plan": "separated review artifact, proposed note, and source/work frontmatter candidates",
        "draft": "footnoted wikilinked Wiki note previews for review only",
        "review": "review packet",
        "canonical": "Wiki/Atlas note only after explicit review/apply outside program-gen",
    }
    assert set(manifest["intent"]["outputs"]) == set(intent_payload["outputs"])
    assert manifest["program_promotion_review"]["promotion_state"] == "not_promoted"
    assert manifest["program_promotion_review"]["candidate_status"] == "exploratory"
    assert manifest["program_promotion_review"]["adjudicator"] == {
        "kind": "ai_agent",
        "id": "dspx_program_adjudicator_v1",
        "authority": "required_for_promotion",
        "status": "pending",
    }
    program_jury = json.loads((outdir / "jury.json").read_text(encoding="utf-8"))
    jury_selection = json.loads(
        (outdir / "jury_selection.json").read_text(encoding="utf-8")
    )
    jury_rubric = json.loads((outdir / "jury_rubric.json").read_text(encoding="utf-8"))
    expected_perspectives = [
        "source_grounding",
        "authority_boundaries",
        "transition_artifact_quality",
        "language_fidelity",
        "zotero_footnote_linkage",
        "zotero_identity_derivation",
        "ontological_role_separation",
        "wiki_link_key_concepts",
        "purpose_framing",
        "authorial_purpose_and_structure",
        "metacognitive_uncertainty",
        "how_to_read_concept_enrichment",
    ]
    assert program_jury["perspectives"] == expected_perspectives
    assert program_jury["minimum_jurors"] == 12
    assert jury_selection["selected_perspectives"] == expected_perspectives
    assert [item["source"] for item in jury_selection["selected_jurors"]] == [
        "explicit_perspective" for _ in expected_perspectives
    ]
    assert [item["criteria"] for item in jury_rubric["juror_rubrics"]] == [
        ["source_refs_preserved", "source_identity_not_invented"],
        ["canonical_mutation_forbidden", "review_authority_explicit"],
        ["artifact_family_clarity", "proposal_reviewability"],
        ["source_language_preserved", "review_text_language_consistent"],
        ["zotero_refs_preferred", "source_provenance_footnotes_only"],
        [
            "zotero_uris_derived_from_manifest_keys",
            "package_folder_not_renamed_to_zotero_key",
        ],
        [
            "review_note_source_roles_separated",
            "source_material_type_not_confused_with_note_kind",
        ],
        [
            "durable_concepts_wikilinked",
            "source_authors_wikilinked_in_frontmatter",
            "ordinary_words_not_overlinked",
        ],
        ["reading_purpose_explicit", "note_usefulness_purpose_clear"],
        ["authorial_purpose_inferred", "argument_structure_preserved"],
        ["uncertainty_visible", "grounding_status_distinguished"],
        [
            "relevant_how_to_read_concepts_applied",
            "applied_and_weak_absent_sets_disjoint",
            "elements_of_thought_presence_consistent",
            "concept_absence_or_weak_fit_explained",
            "source_value_enriched_beyond_summary",
        ],
    ]

    example_inputs = example_payload["inputs"]
    source_manifest = _load_json_text(example_inputs["source_package_manifest_json"])
    assert source_manifest["doc_id"] == "doc:pdf-transition-demo"
    assert source_manifest["package_root"].endswith("/doc:pdf-transition-demo")
    assert source_manifest["item_key"] == "DEMO2026"
    assert source_manifest["source_material_type"] == "guide"
    assert source_manifest["work_type"] == "guide"
    assert source_manifest["figure_inventory_rows"][0]["figure_id"] == (
        "fig:doc:pdf-transition-demo:0001"
    )
    assert source_manifest["figure_inventory_rows"][0]["image_path"].endswith(
        "page_12_close_reading.jpeg"
    )
    assert "zotero_item_uri" not in source_manifest
    assert "zotero_attachment_uri" not in source_manifest

    expected_outputs = example_payload["outputs"]
    section_units = _load_json_text(expected_outputs["section_units_json"])
    distillation_frames = _load_json_text(expected_outputs["distillation_frames_json"])
    evidence_cards = _load_json_text(expected_outputs["evidence_cards_json"])
    merge_create = _load_json_text(expected_outputs["merge_create_proposals_json"])
    frontmatter_plans = _load_json_text(expected_outputs["frontmatter_plans_json"])
    wiki_note_drafts = _load_json_text(expected_outputs["wiki_note_drafts_json"])
    review_packet = _load_json_text(expected_outputs["review_packet_json"])
    contract = _load_json_text(expected_outputs["artifact_contract_manifest_json"])

    assert section_units[0]["artifact_family"] == "transition"
    assert section_units[0]["artifact_type"] == "section_unit_candidate"
    assert section_units[0]["figure_refs"][0]["figure_id"] == (
        "fig:doc:pdf-transition-demo:0001"
    )
    assert distillation_frames[0]["artifact_family"] == "transition"
    assert set(distillation_frames[0]) >= {
        "paraphrase",
        "thesis",
        "logic",
        "evaluation",
        "application",
        "close_reading_program_rubric",
    }
    assert distillation_frames[0]["close_reading_program_rubric"] == {
        "reading_purpose": "Make interpretation reviewable before canonical note mutation.",
        "authorial_purpose": "Teach a staged method for close reading rather than merely naming a concept.",
        "structure_role": "method_overview",
        "elements_of_thought": {
            "purpose": "reviewable interpretation",
            "question": "How should a reader move from passage to accepted understanding?",
            "concepts": ["[[Close Reading]]", "[[Paraphrase]]", "[[Logic Analysis]]"],
            "implications": [
                "Canonicalization should wait until interpretation has been inspected."
            ],
        },
        "metacognitive_status": "source_grounded_with_review_needed",
        "how_to_read_concept_enrichment": {
            "applied_concepts": [
                "Purpose-Driven Reading",
                "Authorial Purpose in Reading",
                "Elements of Thought",
                "Structural Reading",
                "Active Annotation",
                "Analyzing the Logic of an Article",
            ],
            "weak_or_absent_concepts": [
                "Reading Within Disciplines",
                "Map of Knowledge",
            ],
            "enrichment_value": "Turns the excerpt into a reviewable method artifact with purpose, authorial intent, structure, action, and logic instead of a plain summary.",
        },
    }
    enrichment = distillation_frames[0]["close_reading_program_rubric"][
        "how_to_read_concept_enrichment"
    ]
    assert set(enrichment["applied_concepts"]).isdisjoint(
        enrichment["weak_or_absent_concepts"]
    )
    assert "Elements of Thought" in enrichment["applied_concepts"]
    assert "Elements of Thought" not in enrichment["weak_or_absent_concepts"]
    assert evidence_cards[0]["artifact_family"] == "transition"
    assert evidence_cards[0]["source_refs"]
    assert evidence_cards[0]["source_grounding_status"] == (
        "quote_verified_from_marker_excerpt"
    )
    assert evidence_cards[0]["figure_refs"][0]["image_path"].endswith(
        "page_12_close_reading.jpeg"
    )
    assert evidence_cards[0]["purpose_served"] == (
        "Evaluate whether close-reading stages should enrich an existing Wiki concept note."
    )
    assert merge_create[0]["artifact_family"] == "proposal"
    assert merge_create[0]["proposed_action"] == "enrich"
    assert merge_create[0]["target_path"] == "Wiki/Close Reading.md"
    assert merge_create[0]["canonical_mutation_allowed"] is False
    assert merge_create[0]["review_required"] is True
    assert merge_create[0]["draft_ref"] == "draft:doc-pdf-transition-demo:close-reading"
    assert merge_create[0]["puzzle_fit"]["status"] == "candidate_context_needed"
    assert frontmatter_plans["artifact_family"] == "frontmatter_plan"
    assert frontmatter_plans["role_separation_policy"] == (
        "review_artifact_vs_proposed_note_vs_source_work"
    )
    assert frontmatter_plans["source_material_type"] == "guide"
    assert frontmatter_plans["review_artifacts"][0]["artifact_type"] == (
        "wiki_note_draft_preview"
    )
    assert frontmatter_plans["review_artifacts"][0]["review_status"] == "pending"
    proposed_note_fm = frontmatter_plans["proposed_notes"][0]["frontmatter"]
    assert proposed_note_fm["space"] == "wiki"
    assert proposed_note_fm["kind"] == "concept"
    assert proposed_note_fm["state"] == "seed"
    assert proposed_note_fm["needs_review"] is True
    assert proposed_note_fm["source_authors"] == ["[[Example Author]]"]
    source_work_fm = frontmatter_plans["source_work_candidates"][0]["frontmatter"]
    assert source_work_fm["space"] == "atlas"
    assert source_work_fm["kind"] == "source"
    assert source_work_fm["work_type"] == "guide"
    assert source_work_fm["authors"] == ["[[Example Author]]"]
    assert source_work_fm["primary_source_id"] == "zotero:user:demo/DEMO2026"
    assert wiki_note_drafts[0]["artifact_family"] == "draft"
    assert wiki_note_drafts[0]["state"] == "proposed"
    assert wiki_note_drafts[0]["source_language"] == "en"
    assert wiki_note_drafts[0]["language_policy"] == "match_source_language"
    assert wiki_note_drafts[0]["review_artifact_frontmatter"]["review_status"] == (
        "pending"
    )
    assert wiki_note_drafts[0]["proposed_note_frontmatter"]["kind"] == "concept"
    assert wiki_note_drafts[0]["proposed_note_frontmatter"]["needs_review"] is True
    assert wiki_note_drafts[0]["proposed_note_frontmatter"]["source_authors"] == [
        "[[Example Author]]"
    ]
    assert wiki_note_drafts[0]["image_refs"][0]["figure_id"] == (
        "fig:doc:pdf-transition-demo:0001"
    )
    assert wiki_note_drafts[0]["image_refs"][0]["embed"] == (
        "![[how-to-read-a-paragraph-page-12-close-reading.jpeg]]"
    )
    assert wiki_note_drafts[0]["program_improvement_criteria"] == {
        "reading_purpose": "Help a reviewer decide whether to enrich an existing close-reading note.",
        "authorial_purpose": "Preserve the source's instructional intent: make interpretation staged and reviewable.",
        "structure_role": "method_overview",
        "review_question_role": "Expose remaining merge/link decisions without implying canonical acceptance.",
    }
    assert "space: wiki" in wiki_note_drafts[0]["markdown"]
    assert "kind: concept" in wiki_note_drafts[0]["markdown"]
    assert "state: seed" in wiki_note_drafts[0]["markdown"]
    assert "state: accepted" not in wiki_note_drafts[0]["markdown"]
    assert "accepted: true" not in wiki_note_drafts[0]["markdown"]
    assert '  - "[[Example Author]]"' in wiki_note_drafts[0]["markdown"]
    assert "artifact_type: wiki_note" not in wiki_note_drafts[0]["markdown"]
    assert "[[Close Reading]]" in wiki_note_drafts[0]["markdown"]
    assert (
        "![[how-to-read-a-paragraph-page-12-close-reading.jpeg]]"
        in wiki_note_drafts[0]["markdown"]
    )
    assert (
        "figure: `fig:doc:pdf-transition-demo:0001`" in wiki_note_drafts[0]["markdown"]
    )
    assert "## Source" not in wiki_note_drafts[0]["markdown"]
    assert "## Quelle" not in wiki_note_drafts[0]["markdown"]
    assert "[^close-reading-demo]: Zotero item:" in wiki_note_drafts[0]["markdown"]
    assert (
        wiki_note_drafts[0]["footnotes"][0]["zotero_item_uri"]
        == "zotero://select/items/DEMO2026"
    )
    assert (
        wiki_note_drafts[0]["footnotes"][0]["link_derivation"]
        == "derived_from_item_key_and_attachment_record_id"
    )
    assert wiki_note_drafts[0]["footnotes"][0]["package_root"].endswith(
        "/doc:pdf-transition-demo"
    )
    assert "citekey: `demoCloseReading2026`" in wiki_note_drafts[0]["markdown"]
    assert review_packet["artifact_family"] == "review"
    assert review_packet["canonical_mutation_performed"] is False
    assert review_packet["source_language"] == "en"
    assert review_packet["draft_refs"] == [
        "draft:doc-pdf-transition-demo:close-reading"
    ]
    assert review_packet["program_improvement_rubric"] == {
        "reading_purpose_visible": True,
        "authorial_purpose_visible": True,
        "structure_role_visible": True,
        "metacognitive_uncertainty_visible": True,
        "puzzle_fit_visible": True,
        "how_to_read_concept_enrichment_visible": True,
        "how_to_read_applied_and_weak_absent_sets_disjoint": True,
        "elements_of_thought_presence_consistent": True,
        "image_refs_visible_when_marker_figures_present": True,
    }
    assert review_packet["how_to_read_concept_enrichment"][
        "Purpose-Driven Reading"
    ] == ("Each artifact should state the purpose it serves.")
    assert review_packet["how_to_read_concept_enrichment"][
        "Analyzing the Logic of an Article"
    ] == ("Argumentative sources should expose claim/reason/implication structure.")
    assert contract["schema_version"] == "pdf-transition-artifact-contract-v1"
    assert contract["artifact_family_authority"] == {
        "source": "raw extraction/source package authority",
        "transition": "regenerable source-grounded transition artifacts",
        "proposal": "merge/create proposal artifacts only",
        "frontmatter_plan": "separated review artifact, proposed note, and source/work frontmatter candidates",
        "draft": "review-only Wiki note draft previews with source-language text, wikilinks, and footnote provenance",
        "review": "human/operator review artifacts",
        "canonical": "Wiki/Atlas artifacts only after explicit review",
    }
    assert contract["canonical_mutation_performed"] is False
    assert contract["draft_requirements"] == {
        "language_fidelity": "match_source_language",
        "wikilink_key_concepts": True,
        "source_provenance_location": "footnotes_only",
        "prefer_zotero_links": True,
        "derive_zotero_uris_from_manifest_keys": True,
        "package_folder_semantics": "doc_id_hash_keyed_not_zotero_keyed",
        "frontmatter_role_separation": "review_artifact_vs_proposed_note_vs_source_work",
        "source_material_type_separate_from_note_kind": True,
        "source_author_wikilinks_in_frontmatter": True,
        "forbid_source_heading_block": True,
        "reading_purpose_visible": True,
        "authorial_purpose_visible": True,
        "structure_role_visible": True,
        "metacognitive_uncertainty_visible": True,
        "puzzle_fit_visible": True,
        "how_to_read_concept_enrichment_visible": True,
        "how_to_read_applied_and_weak_absent_sets_disjoint": True,
        "elements_of_thought_presence_consistent": True,
        "accepted_canonical_status_not_copied_into_review_draft": True,
        "image_refs_visible_when_marker_figures_present": True,
    }
    assert "canonical_wiki_mutation" in contract["forbidden_effects"]
    assert (
        "source_language_translation_without_request" in contract["forbidden_effects"]
    )

    direct_run_text = (outdir / "direct_run.py").read_text(encoding="utf-8")
    assert "generated-dspy-direct-run-v1" in direct_run_text
    assert "generated-dspy-direct-batch-run-v1" in direct_run_text
    assert "--inputs-root" in direct_run_text
    assert "direct_batch_receipt.json" in direct_run_text
    assert "dspx_program_run_wrapper_used" in direct_run_text
    assert "--config" in direct_run_text
    assert "--preflight" in direct_run_text
    assert "generated-dspy-direct-run-preflight-v1" in direct_run_text
    assert "model_call_performed': False" in direct_run_text
    assert (
        "CONFIG_CANDIDATES = ('dspx-local.config.toml', 'config.toml')"
        in direct_run_text
    )
    assert "from dspx.config_loader import load_config_env" in direct_run_text
    assert "def _apply_runtime_config_env(data: object) -> None:" in direct_run_text
    assert "_set_env_from_config(provider, 'name', 'DSPX_PROVIDER')" in direct_run_text
    assert "'provider': 'stub'" in direct_run_text
    assert "'model': getattr(lm, 'model', None)" in direct_run_text
    assert "DSPX_LM_AUTH" not in direct_run_text
    assert "lm_auth" not in direct_run_text
    assert (
        "configure_observability(run_name='program-runtime', run_kind='program-runtime')"
        in direct_run_text
    )
    assert (
        "mlflow.log_artifacts(str(outdir), artifact_path='direct_run_outputs')"
        in direct_run_text
    )
    assert "def _write_direct_run_receipt(" in direct_run_text
    assert "status='failed'" in direct_run_text
    assert "receipt['error']" in direct_run_text
    assert (
        "from program import build_program, configure_observability, end_observability_run, io_spec"
        in direct_run_text
    )
    assert any(
        surface["kind"] == "direct_runner" and surface["path"] == "direct_run.py"
        for surface in manifest["candidate_assembly"]["surfaces"]
    )

    module_text = (outdir / "module.py").read_text(encoding="utf-8")
    assert "FocusedPdfTransitionProgramModuleBundleSignature" in module_text
    assert "note_bundle_json" in module_text
    assert "_collect_image_refs" in module_text
    assert "dspy.Prediction(section_units_json=" in module_text

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
    assert behavior_results["summary"]["status"] == "failed"
    assert behavior_results["examples"][0]["status"] == "failed"
    assert "error" not in behavior_results["examples"][0]
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


def test_program_gen_logs_materialized_assembly_to_mlflow_when_configured(
    tmp_path: Path,
    monkeypatch,
) -> None:
    backend = _install_fake_mlflow(monkeypatch)
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "1")
    tracking_uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", tracking_uri)
    monkeypatch.setenv("MLFLOW_EXPERIMENT", "DSPxProgramGenTest")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    reset_embedding_engine()

    outdir = tmp_path / "program"
    (tmp_path / "preexisting-secret.txt").write_text(
        "must not upload\n", encoding="utf-8"
    )
    result = runner.invoke(
        app,
        [
            "program-gen",
            "--intent",
            str(FIXTURE_ROOT / "intent.yaml"),
            "--outdir",
            str(outdir),
        ],
    )

    assert result.exit_code == 0, result.output
    assert ("set_tracking_uri", tracking_uri) in backend.calls
    assert ("set_experiment", "DSPxProgramGenTest") in backend.calls
    assert ("start_run", "program-gen") in backend.calls
    assert ("set_tag", "service", "program") in backend.calls
    assert ("set_tag", "dspx.run_kind", "program-gen") in backend.calls
    assert any(call[0] == "log_artifacts" for call in backend.calls)
    assert ("set_tag", "program.artifacts.upload_status", "logged") in backend.calls
    assert ("log_metric", "program.artifacts.upload_error", 0.0) in backend.calls
    assert "manifest.json" in backend.logged_artifact_files
    assert "program.py" in backend.logged_artifact_files
    assert "preexisting-secret.txt" not in backend.logged_artifact_files
    file_count_calls = [
        call
        for call in backend.calls
        if call[:2] == ("log_param", "program.generated_file_count")
    ]
    assert file_count_calls
    assert int(str(file_count_calls[-1][2])) >= 24
    program_spec = importlib.util.spec_from_file_location(
        "pdf_transition_generated_program_mlflow", outdir / "program.py"
    )
    assert program_spec is not None
    assert program_spec.loader is not None
    generated_program = importlib.util.module_from_spec(program_spec)
    old_path = list(sys.path)
    try:
        sys.path.insert(0, str(outdir))
        program_spec.loader.exec_module(generated_program)
    finally:
        sys.path[:] = old_path

    receipt_hash = json.loads((outdir / "manifest.json.meta.json").read_text())["hash"]
    assert (
        generated_program.program_observability_tags()["program.manifest_hash"]
        == receipt_hash
    )
    manifest_payload = json.loads((outdir / "manifest.json").read_text())
    manifest_payload["post_generation_note"] = (
        "runtime metadata must not alter receipt-bound hash"
    )
    (outdir / "manifest.json").write_text(
        json.dumps(manifest_payload), encoding="utf-8"
    )
    assert generated_program._current_manifest_hash() != receipt_hash
    assert (
        generated_program.program_observability_tags()["program.manifest_hash"]
        == receipt_hash
    )

    started = generated_program.configure_observability(
        run_name="program-runtime", run_kind="program-runtime"
    )
    assert started is True
    try:
        tags = generated_program.program_observability_tags()
        assert tags["program.name"] == "PdfTransitionProgram"
        assert tags["program.assembly_id"]
        assert tags["program.manifest_hash"]
        assert ("start_run", "program-runtime") in backend.calls
        assert ("set_tag", "dspx.run_kind", "program-runtime") in backend.calls
        assert ("set_tag", "program.name", "PdfTransitionProgram") in backend.calls
    finally:
        generated_program.end_observability_run(started)

    def _failing_program() -> object:
        raise RuntimeError("forced runtime observability failure")

    cast(Any, generated_program).build_program = _failing_program
    try:
        generated_program.run_with_observability(
            source_package_manifest_json="{}",
            marker_markdown="",
            existing_wiki_index_json="{}",
            declared_output_root="x",
        )
    except RuntimeError:
        pass
    assert ("set_tag", "program.runtime.status", "failed") in backend.calls
    assert any(
        call == ("log_metric", "program.runtime.error", 1.0) for call in backend.calls
    )
    assert ("end_run", "FAILED") in backend.calls

    eval_behavior_source = (outdir / "eval_behavior.py").read_text(encoding="utf-8")
    assert (
        "configure_observability(run_name='program-eval', run_kind='program-eval')"
        in eval_behavior_source
    )
    assert (
        "mlflow.log_metric(f'program.behavior.{key}', float(value))"
        in eval_behavior_source
    )
    assert any(call[0] == "end_run" for call in backend.calls)


def test_program_gen_surfaces_mlflow_artifact_upload_failures(
    tmp_path: Path,
    monkeypatch,
) -> None:
    backend = _install_fake_mlflow(monkeypatch)
    backend.fail_log_artifacts = True
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "1")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{tmp_path / 'mlflow.db'}")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    reset_embedding_engine()

    result = runner.invoke(
        app,
        [
            "program-gen",
            "--intent",
            str(FIXTURE_ROOT / "intent.yaml"),
            "--outdir",
            str(tmp_path / "program"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert ("set_tag", "program.artifacts.upload_status", "failed") in backend.calls
    assert ("set_tag", "program.artifacts.error_type", "RuntimeError") in backend.calls
    assert (
        "set_tag",
        "program.artifacts.error",
        "artifact store down",
    ) in backend.calls
    assert ("log_metric", "program.artifacts.upload_error", 1.0) in backend.calls
    assert any(call[0] == "end_run" for call in backend.calls)

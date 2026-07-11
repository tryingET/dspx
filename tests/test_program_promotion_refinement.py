from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.coordinates import reset_embedding_engine
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_oracle_index import index_program_oracle_evidence_path
from dspx.services.program_oracle_report import build_program_oracle_evidence_report
from dspx.services.program_refinement import build_program_refinement_proposal
from dspx.services import artifact_boundary, program_promotion_refinement
from dspx.services.program_promotion_refinement import (
    ProgramPromotionRefinementError,
    _identity_matches,
    _load_program_behavior_episode,
    validate_program_promotion_review_refined_contract,
    build_program_promotion_refinement,
    write_program_promotion_refinement,
)
from dspx.services.program_runtime_episode import run_program_runtime_episode
from dspx.services.program_service import materialize_program_from_intent

runner = CliRunner()


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.iterdir())
        if path.is_file()
    }


def _setup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    reset_embedding_engine()


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _write_minimal_candidate_closure(root: Path) -> tuple[Path, Path]:
    decision_template: dict[str, object] = {
        "schema_version": "program-promotion-decision-v1"
    }
    artifacts: dict[str, tuple[str, dict[str, object] | str]] = {
        "promotion_review": (
            "promotion_review.json",
            {
                "schema_version": "program-promotion-review-v1",
                "promotion_state": "not_promoted",
            },
        ),
        "promotion_adjudication_request": (
            "promotion_adjudication_request.json",
            {
                "schema_version": "program-promotion-adjudication-request-v1",
                "decision_record_template": decision_template,
            },
        ),
        "promotion_decision_template": (
            "promotion_decision_template.json",
            decision_template,
        ),
        "future_surface": ("future.json", {"value": "current"}),
    }
    surfaces: list[dict[str, str]] = []
    for kind, (name, payload) in artifacts.items():
        path = root / name
        if isinstance(payload, str):
            path.write_text(payload, encoding="utf-8")
        else:
            _write_json(path, payload)
        surfaces.append(
            {
                "kind": kind,
                "path": name,
                "content_hash": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    manifest_path = root / "manifest.json"
    _write_json(
        manifest_path,
        {
            "schema_version": "program-candidate-assembly-v1",
            "candidate_assembly": {"surfaces": surfaces},
        },
    )
    return manifest_path, root / "future.json"


def _mock_minimal_promotion_sources(
    monkeypatch: pytest.MonkeyPatch,
    *,
    manifest: dict[str, Any],
) -> None:
    monkeypatch.setattr(
        program_promotion_refinement,
        "load_program_manifest",
        lambda _path: manifest,
    )
    monkeypatch.setattr(
        program_promotion_refinement,
        "load_program_behavior_results",
        lambda _manifest, _path: (None, None, None),
    )

    def stable_observation(path: Path, *, label: str, **_kwargs: object) -> object:
        payload = (
            {
                "schema_version": "program-oracle-evidence-report-v1",
                "status": "empty",
                "total_records": 0,
            }
            if "Oracle" in label
            else {
                "schema_version": "program-refinement-proposal-v1",
                "status": "insufficient_behavior_evidence",
            }
        )
        content_hash = (
            hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "0" * 64
        )
        return program_promotion_refinement.StableJsonArtifact(
            path=path.resolve(),
            sha256=content_hash,
            payload=payload,
        )

    monkeypatch.setattr(
        program_promotion_refinement,
        "read_stable_json_artifact",
        stable_observation,
    )
    monkeypatch.setattr(
        program_promotion_refinement,
        "validate_program_oracle_report_non_authority",
        lambda _report: None,
    )
    monkeypatch.setattr(
        program_promotion_refinement,
        "_validate_oracle_report_identity",
        lambda _report, _identity: ({}, False),
    )
    monkeypatch.setattr(
        program_promotion_refinement,
        "_validate_refinement_proposal",
        lambda *_args, **_kwargs: {
            "schema_version": "program-refinement-proposal-v1",
            "status": "insufficient_behavior_evidence",
        },
    )


def test_program_promotion_refinement_rejects_stale_unknown_candidate_surface(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    manifest_path, future_path = _write_minimal_candidate_closure(candidate)
    future_path.write_text('{"value":"substituted"}\n', encoding="utf-8")

    with pytest.raises(
        ProgramPromotionRefinementError,
        match="candidate artifact closure is invalid.*future_surface hash",
    ):
        program_promotion_refinement.load_program_promotion_inputs(
            manifest_path=manifest_path,
            oracle_report_path=tmp_path / "unused-report.json",
            refinement_proposal_path=tmp_path / "unused-proposal.json",
        )


def test_program_promotion_refinement_rechecks_candidate_during_input_loading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    manifest_path, future_path = _write_minimal_candidate_closure(candidate)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _mock_minimal_promotion_sources(monkeypatch, manifest=manifest)
    report_path = tmp_path / "report.json"
    _write_json(report_path, {})

    def mutate_during_proposal_load(
        *_args: object, **_kwargs: object
    ) -> dict[str, str]:
        future_path.write_text('{"value":"raced"}\n', encoding="utf-8")
        return {
            "schema_version": "program-refinement-proposal-v1",
            "status": "insufficient_behavior_evidence",
        }

    monkeypatch.setattr(
        program_promotion_refinement,
        "_validate_refinement_proposal",
        mutate_during_proposal_load,
    )

    with pytest.raises(
        ProgramPromotionRefinementError,
        match="changed during promotion review construction.*future_surface hash",
    ):
        program_promotion_refinement.load_program_promotion_inputs(
            manifest_path=manifest_path,
            oracle_report_path=report_path,
            refinement_proposal_path=tmp_path / "proposal.json",
        )


def test_program_promotion_refinement_rechecks_candidate_before_packet_return(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    manifest_path, future_path = _write_minimal_candidate_closure(candidate)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _mock_minimal_promotion_sources(monkeypatch, manifest=manifest)
    report_path = tmp_path / "report.json"
    _write_json(report_path, {})
    proposal_path = tmp_path / "proposal.json"
    _write_json(proposal_path, {})
    original_status = program_promotion_refinement._status_for_packet

    def mutate_during_packet_build(
        *,
        behavior_present: bool,
        oracle_matched: bool,
        proposal: Mapping[str, Any],
    ) -> str:
        future_path.write_text('{"value":"late-race"}\n', encoding="utf-8")
        return original_status(
            behavior_present=behavior_present,
            oracle_matched=oracle_matched,
            proposal=proposal,
        )

    monkeypatch.setattr(
        program_promotion_refinement,
        "_status_for_packet",
        mutate_during_packet_build,
    )

    with pytest.raises(
        ProgramPromotionRefinementError,
        match="changed during promotion review construction.*future_surface hash",
    ):
        build_program_promotion_refinement(
            manifest_path=manifest_path,
            oracle_report_path=report_path,
            refinement_proposal_path=proposal_path,
        )


def test_program_promotion_refinement_rechecks_candidate_before_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    manifest_path, future_path = _write_minimal_candidate_closure(candidate)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _mock_minimal_promotion_sources(monkeypatch, manifest=manifest)
    report_path = tmp_path / "report.json"
    proposal_path = tmp_path / "proposal.json"
    _write_json(report_path, {})
    _write_json(proposal_path, {})
    packet = build_program_promotion_refinement(
        manifest_path=manifest_path,
        oracle_report_path=report_path,
        refinement_proposal_path=proposal_path,
    )
    future_path.write_text('{"value":"post-build-race"}\n', encoding="utf-8")
    out_path = tmp_path / "promotion" / "review.json"

    with pytest.raises(
        ProgramPromotionRefinementError,
        match="candidate artifact closure is invalid.*future_surface hash",
    ):
        write_program_promotion_refinement(packet, out_path)

    assert not out_path.exists()


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def _model_jury_evidence_ref(path: Path) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "schema_version": json.loads(path.read_text(encoding="utf-8")).get(
            "schema_version"
        ),
    }


def _model_jury_result_for_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    request = dict(manifest["request"])
    candidate = dict(manifest["candidate_assembly"])
    execution = dict(manifest["execution_episode"])
    receipt = dict(manifest["receipt_bundle"])
    root = Path(str(candidate["root_path"]))
    manifest_path = root / "manifest.json"
    jury_path = root / "jury.json"
    selection_path = root / "jury_selection.json"
    rubric_path = root / "jury_rubric.json"
    evidence_entries = [
        _model_jury_evidence_ref(path)
        for path in (root / "behavior_results.json", root / "behavior_episode.json")
        if path.exists()
    ]
    return {
        "schema_version": "program-model-jury-results-v1",
        "status": "executed",
        "identity": {
            "request_id": request["request_id"],
            "candidate_id": candidate["candidate_id"],
            "assembly_id": candidate["assembly_id"],
            "episode_id": execution["episode_id"],
            "receipt_bundle_id": receipt["receipt_bundle_id"],
        },
        "created_from": {
            "manifest_path": str(manifest_path.resolve()),
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "jury_path": str(jury_path.resolve()),
            "jury_sha256": hashlib.sha256(jury_path.read_bytes()).hexdigest(),
            "jury_selection_path": str(selection_path.resolve()),
            "jury_selection_sha256": hashlib.sha256(
                selection_path.read_bytes()
            ).hexdigest(),
            "jury_rubric_path": str(rubric_path.resolve()),
            "jury_rubric_sha256": hashlib.sha256(rubric_path.read_bytes()).hexdigest(),
        },
        "jury": {
            "execution_mode": "provider_backed_model",
            "provider_backed_model_calls": True,
            "selected_juror_count": 1,
        },
        "adjudicator": {
            "repo": "target-repo",
            "promotion_authority": False,
        },
        "evidence": {"entry_count": len(evidence_entries), "entries": evidence_entries},
        "juror_results": [
            {
                "juror_id": "authority_agent",
                "status": "judged",
                "judgment": {"outcome": "request_more_evidence"},
            }
        ],
        "aggregate": {
            "judgment_counts": {
                "supports_review_evidence": 0,
                "withhold": 0,
                "reject": 0,
                "request_more_evidence": 1,
                "failed": 0,
            },
            "recommendation": "request_more_evidence",
            "unique_improvement_requests": ["add more target evidence"],
        },
        "interpretation": {"ready_for_promotion_decision": False},
        "effect": {
            "model_jury_evidence_only": True,
            "program_files_mutated": False,
            "promotion_review_mutated": False,
            "new_candidate_generated": False,
            "oracle_index_mutated": False,
            "external_authority_mutated": False,
            "ak_mutated": False,
            "governance_mutated": False,
        },
        "non_authority": {
            "promotion_approval": False,
            "ranking_or_winner_selection": False,
            "domain_acceptance": False,
            "external_authority_apply": False,
            "canonical_mutation": False,
        },
    }


def _materialize_program_report_and_proposal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, Path]:
    _setup_env(tmp_path, monkeypatch)
    intent = ProgramIntent(
        name="TicketProgram",
        objective="Classify support ticket urgency.",
        inputs=["ticket_text"],
        outputs=["urgency"],
        metric="exact_match",
        constraints=["use only the supplied ticket text"],
        examples=[
            {
                "inputs": {"ticket_text": "Server is down for all users"},
                "outputs": {"urgency": "high"},
            }
        ],
    )
    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    program_root = Path(artifact.root_path)
    assert (program_root / "behavior_results.json").exists()
    assert (program_root / "oracle_evidence.json").exists()

    index_path = tmp_path / "oracle" / "coordinates.db"
    index_result = index_program_oracle_evidence_path(
        program_root,
        index_path=index_path,
    )
    assert index_result["indexed"] == 1
    assert index_result["errors"] == 0

    report = build_program_oracle_evidence_report(index_path=index_path)
    report_path = tmp_path / "oracle" / "program-evidence-report.json"
    _write_json(report_path, report)

    proposal = build_program_refinement_proposal(
        manifest_path=program_root / "manifest.json",
        oracle_report_path=report_path,
    )
    proposal_path = tmp_path / "refinement" / "refinement_proposal.json"
    _write_json(proposal_path, proposal)
    return program_root, report_path, proposal_path


def _write_runtime_episode(program_root: Path, tmp_path: Path) -> Path:
    runtime_inputs = tmp_path / "runtime" / "runtime-inputs.json"
    _write_json(
        runtime_inputs,
        {"inputs": {"ticket_text": "Server is down for all users"}},
    )
    runtime_root = tmp_path / "runtime" / "episode"
    run_program_runtime_episode(
        manifest_path=program_root / "manifest.json",
        inputs_path=runtime_inputs,
        outdir=runtime_root,
        skip_oracle_index=True,
    )
    return runtime_root / "runtime_episode.json"


def test_program_promotion_refinement_rejects_absolute_behavior_episode_path(
    tmp_path: Path,
) -> None:
    episode = tmp_path / "forged_behavior_episode.json"
    _write_json(
        episode,
        {"schema_version": "program-behavior-episode-v1", "summary": {}},
    )
    manifest = {
        "schema_version": "program-candidate-assembly-v1",
        "behavior_episode_artifact": {"path": str(episode)},
    }
    manifest_path = tmp_path / "candidate" / "manifest.json"
    manifest_path.parent.mkdir()
    _write_json(manifest_path, manifest)

    with pytest.raises(ProgramPromotionRefinementError, match="candidate-relative"):
        _load_program_behavior_episode(manifest, manifest_path)


def test_program_promotion_refinement_rejects_hashless_behavior_episode(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    episode = candidate / "behavior_episode.json"
    _write_json(
        episode,
        {"schema_version": "program-behavior-episode-v1", "summary": {}},
    )
    manifest = {
        "schema_version": "program-candidate-assembly-v1",
        "behavior_episode_artifact": {"path": "behavior_episode.json"},
    }
    manifest_path = candidate / "manifest.json"
    _write_json(manifest_path, manifest)

    with pytest.raises(ProgramPromotionRefinementError, match="content hash"):
        _load_program_behavior_episode(manifest, manifest_path)


def test_program_promotion_refinement_rejects_partial_oracle_identity_match() -> None:
    assert (
        _identity_matches(
            {"candidate_id": "cand-1"},
            {
                "request_id": "req-1",
                "candidate_id": "cand-1",
                "assembly_id": "asm-1",
                "episode_id": "ep-1",
                "receipt_bundle_id": "rb-1",
            },
        )
        is False
    )


def test_program_promotion_refinement_cli_builds_local_review_packet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    manifest = json.loads((program_root / "manifest.json").read_text(encoding="utf-8"))
    behavior = json.loads(
        (program_root / "behavior_results.json").read_text(encoding="utf-8")
    )
    behavior_episode = json.loads(
        (program_root / "behavior_episode.json").read_text(encoding="utf-8")
    )
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    before = _file_hashes(program_root)
    before_names = sorted(before)
    out_path = tmp_path / "promotion" / "promotion_review_refined.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "review",
            "--manifest",
            str(program_root / "manifest.json"),
            "--oracle-report",
            str(report_path),
            "--refinement-proposal",
            str(proposal_path),
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert out_path.exists()
    assert json.loads(out_path.read_text(encoding="utf-8")) == payload
    assert payload["schema_version"] == "program-promotion-review-refined-v1"
    assert payload["status"] == "review_packet_ready"
    assert payload["promotion_state"] == "not_promoted"
    assert payload["candidate_status"] == "exploratory"
    assert payload["identity"] == {
        "request_id": manifest["request"]["request_id"],
        "candidate_id": manifest["candidate_assembly"]["candidate_id"],
        "assembly_id": manifest["candidate_assembly"]["assembly_id"],
        "episode_id": manifest["execution_episode"]["episode_id"],
        "receipt_bundle_id": manifest["receipt_bundle"]["receipt_bundle_id"],
    }
    assert payload["created_from"]["manifest_path"] == str(
        (program_root / "manifest.json").resolve()
    )
    assert payload["created_from"]["behavior_results_path"] == str(
        (program_root / "behavior_results.json").resolve()
    )
    assert payload["created_from"]["behavior_episode_path"] == str(
        (program_root / "behavior_episode.json").resolve()
    )
    assert payload["created_from"]["oracle_report_path"] == str(report_path.resolve())
    assert payload["created_from"]["refinement_proposal_path"] == str(
        proposal_path.resolve()
    )
    assert payload["created_from"]["original_promotion_review_path"] == str(
        (program_root / "promotion_review.json").resolve()
    )
    assert payload["created_from"][
        "original_promotion_adjudication_request_path"
    ] == str((program_root / "promotion_adjudication_request.json").resolve())
    assert payload["created_from"]["original_promotion_decision_template_path"] == str(
        (program_root / "promotion_decision_template.json").resolve()
    )
    assert (
        payload["created_from"]["manifest_sha256"]
        == hashlib.sha256((program_root / "manifest.json").read_bytes()).hexdigest()
    )
    assert (
        payload["created_from"]["behavior_results_sha256"]
        == hashlib.sha256(
            (program_root / "behavior_results.json").read_bytes()
        ).hexdigest()
    )
    assert (
        payload["created_from"]["behavior_episode_sha256"]
        == hashlib.sha256(
            (program_root / "behavior_episode.json").read_bytes()
        ).hexdigest()
    )
    assert (
        payload["created_from"]["oracle_report_sha256"]
        == hashlib.sha256(report_path.read_bytes()).hexdigest()
    )
    assert (
        payload["created_from"]["refinement_proposal_sha256"]
        == hashlib.sha256(proposal_path.read_bytes()).hexdigest()
    )
    assert (
        payload["created_from"]["original_promotion_review_sha256"]
        == hashlib.sha256(
            (program_root / "promotion_review.json").read_bytes()
        ).hexdigest()
    )
    assert (
        payload["created_from"]["original_promotion_adjudication_request_sha256"]
        == hashlib.sha256(
            (program_root / "promotion_adjudication_request.json").read_bytes()
        ).hexdigest()
    )
    assert (
        payload["created_from"]["original_promotion_decision_template_sha256"]
        == hashlib.sha256(
            (program_root / "promotion_decision_template.json").read_bytes()
        ).hexdigest()
    )

    assert payload["evidence_summary"]["behavior"] == {
        "present": True,
        "status": behavior["summary"]["status"],
        "example_count": behavior["summary"]["total"],
        "source_count": behavior_episode["summary"]["source_count"],
        "status_counts": behavior["summary"]["status_counts"],
        "behavior_results_present": True,
        "behavior_episode_present": True,
        "behavior_evidence_kind": "behavior_results",
    }
    assert payload["evidence_summary"]["oracle_report"] == {
        "present": True,
        "status": "ok",
        "total_records": 1,
        "record_matched": True,
    }
    assert payload["evidence_summary"]["refinement_proposal"] == {
        "present": True,
        "status": proposal["status"],
        "proposal_id": proposal["proposal_id"],
    }
    readiness = payload["review_readiness"]
    assert readiness["behavior_evidence_present"] is True
    assert readiness["oracle_report_present"] is True
    assert readiness["refinement_proposal_present"] is True
    assert readiness["model_jury_execution_present"] is False
    assert readiness["adjudicator_decision_present"] is False
    assert readiness["ready_for_adjudicator_review"] is False
    assert readiness["missing_required_evidence"] == [
        "no_model_jury_execution_episode",
        "no_promotion_adjudicator_decision",
    ]
    assert payload["promotion_review_delta"] == {
        "behavioral_evaluation_episode": "satisfied_by_current_behavior_episode",
        "oracle_interpretation": "satisfied_by_explicit_oracle_report",
        "bounded_refinement_proposal": "available_non_authoritative",
        "model_jury_execution": "missing_model_jury_execution",
        "promotion_authority": "unchanged_required_adjudicator",
    }
    adjudication = payload["adjudication_packet"]
    assert adjudication["status"] == "not_ready_missing_required_evidence"
    assert adjudication["original_allowed_outcomes"] == [
        "promote",
        "withhold",
        "reject",
        "request_more_evidence",
    ]
    assert adjudication["local_packet_recommended_review_outcomes"] == [
        "withhold",
        "reject",
        "request_more_evidence",
    ]
    assert adjudication["forbidden_outcomes_without_explicit_adjudicator"] == [
        "promote"
    ]
    assert "behavior_results.json" in adjudication["evidence_refs"]
    assert payload["non_authority"] == {
        "local_review_packet_only": True,
        "automatic_promotion": False,
        "oracle_ranking": False,
        "oracle_pruning": False,
        "oracle_promotion": False,
        "program_mutation": False,
        "new_candidate_generation": False,
        "promotion_authority": False,
        "governance_authority": False,
        "external_mutation": False,
    }

    assert _file_hashes(program_root) == before
    assert sorted(_file_hashes(program_root)) == before_names
    assert not (program_root / "promotion_review_refined.json").exists()
    assert (program_root / "eval_behavior.py").exists()
    assert (program_root / "behavior_episode.json").exists()


def test_program_promotion_refinement_consumes_runtime_episode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    runtime_episode = _write_runtime_episode(program_root, tmp_path)
    out_path = tmp_path / "promotion" / "promotion_review_refined.runtime.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "review",
            "--manifest",
            str(program_root / "manifest.json"),
            "--oracle-report",
            str(report_path),
            "--refinement-proposal",
            str(proposal_path),
            "--runtime-episode",
            str(runtime_episode),
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    runtime_summary = payload["evidence_summary"]["runtime_episode"]
    assert payload["created_from"]["runtime_episode_path"] == str(
        runtime_episode.resolve()
    )
    assert (
        payload["created_from"]["runtime_episode_sha256"]
        == hashlib.sha256(runtime_episode.read_bytes()).hexdigest()
    )
    assert runtime_summary["present"] is True
    assert runtime_summary["schema_version"] == "program-runtime-episode-v1"
    assert runtime_summary["status"] == "executed"
    assert runtime_summary["evidence_only"] is True
    assert runtime_summary["promotion_authority"] is False
    assert runtime_summary["activation_authority"] is False
    assert "runtime_episode" in payload["adjudication_packet"]["evidence_refs"]
    assert payload["promotion_state"] == "not_promoted"
    assert payload["review_readiness"]["ready_for_adjudicator_review"] is False
    assert payload["non_authority"]["promotion_authority"] is False


def test_program_promotion_refinement_rejects_stale_runtime_episode_manifest_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    runtime_episode = _write_runtime_episode(program_root, tmp_path)
    payload = json.loads(runtime_episode.read_text(encoding="utf-8"))
    payload["artifact_hashes"]["source_manifest_sha256"] = "0" * 64
    _write_json(runtime_episode, payload)

    result = runner.invoke(
        app,
        [
            "program-promote",
            "review",
            "--manifest",
            str(program_root / "manifest.json"),
            "--oracle-report",
            str(report_path),
            "--refinement-proposal",
            str(proposal_path),
            "--runtime-episode",
            str(runtime_episode),
            "--out",
            str(tmp_path / "promotion" / "bad.json"),
        ],
    )

    assert result.exit_code == 2
    assert "source_manifest_sha256" in result.output


def test_program_promotion_refinement_rejects_cross_candidate_runtime_episode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    other_root, _other_report, _other_proposal = (
        _materialize_program_report_and_proposal(
            tmp_path / "other",
            monkeypatch,
        )
    )
    runtime_episode = _write_runtime_episode(other_root, tmp_path)

    result = runner.invoke(
        app,
        [
            "program-promote",
            "review",
            "--manifest",
            str(program_root / "manifest.json"),
            "--oracle-report",
            str(report_path),
            "--refinement-proposal",
            str(proposal_path),
            "--runtime-episode",
            str(runtime_episode),
            "--out",
            str(tmp_path / "promotion" / "bad.json"),
        ],
    )

    assert result.exit_code == 2
    assert "candidate_manifest_path" in result.output


def test_program_promotion_refinement_rejects_runtime_episode_trace_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    runtime_episode = _write_runtime_episode(program_root, tmp_path)
    traces_path = runtime_episode.parent / "program_runtime_traces.json"
    traces = json.loads(traces_path.read_text(encoding="utf-8"))
    traces["status"] = "no_runtime_traces_captured"
    _write_json(traces_path, traces)

    result = runner.invoke(
        app,
        [
            "program-promote",
            "review",
            "--manifest",
            str(program_root / "manifest.json"),
            "--oracle-report",
            str(report_path),
            "--refinement-proposal",
            str(proposal_path),
            "--runtime-episode",
            str(runtime_episode),
            "--out",
            str(tmp_path / "promotion" / "bad.json"),
        ],
    )

    assert result.exit_code == 2
    assert "program_runtime_traces_sha256" in result.output


def test_program_promotion_refinement_rejects_runtime_episode_wrong_path_fresh_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    runtime_episode = _write_runtime_episode(program_root, tmp_path)
    runtime_manifest_path = runtime_episode.parent / "manifest.json"
    runtime_manifest = json.loads(runtime_manifest_path.read_text(encoding="utf-8"))
    nested_behavior = runtime_episode.parent / "nested" / "behavior_results.json"
    nested_behavior.parent.mkdir(parents=True, exist_ok=True)
    nested_behavior.write_bytes(
        (runtime_episode.parent / "behavior_results.json").read_bytes()
    )
    runtime_manifest["runtime_episode"]["behavior_results_path"] = (
        "nested/behavior_results.json"
    )
    runtime_manifest["runtime_episode"]["behavior_results_sha256"] = hashlib.sha256(
        nested_behavior.read_bytes()
    ).hexdigest()
    _write_json(runtime_manifest_path, runtime_manifest)

    result = runner.invoke(
        app,
        [
            "program-promote",
            "review",
            "--manifest",
            str(program_root / "manifest.json"),
            "--oracle-report",
            str(report_path),
            "--refinement-proposal",
            str(proposal_path),
            "--runtime-episode",
            str(runtime_episode),
            "--out",
            str(tmp_path / "promotion" / "bad.json"),
        ],
    )

    assert result.exit_code == 2
    assert "behavior_results_path" in result.output


def test_program_promotion_refinement_rejects_runtime_episode_symlink_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    runtime_episode = _write_runtime_episode(program_root, tmp_path)
    outside_trace = tmp_path / "outside-program-runtime-traces.json"
    outside_trace.write_bytes(
        (runtime_episode.parent / "program_runtime_traces.json").read_bytes()
    )
    (runtime_episode.parent / "program_runtime_traces.json").unlink()
    (runtime_episode.parent / "program_runtime_traces.json").symlink_to(outside_trace)

    result = runner.invoke(
        app,
        [
            "program-promote",
            "review",
            "--manifest",
            str(program_root / "manifest.json"),
            "--oracle-report",
            str(report_path),
            "--refinement-proposal",
            str(proposal_path),
            "--runtime-episode",
            str(runtime_episode),
            "--out",
            str(tmp_path / "promotion" / "bad.json"),
        ],
    )

    assert result.exit_code == 2
    assert "escapes runtime episode root" in result.output


def test_program_promotion_refinement_rejects_runtime_episode_authority_spoof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    runtime_episode = _write_runtime_episode(program_root, tmp_path)
    payload = json.loads(runtime_episode.read_text(encoding="utf-8"))
    payload["non_authority"]["promotion_authority"] = True
    _write_json(runtime_episode, payload)

    result = runner.invoke(
        app,
        [
            "program-promote",
            "review",
            "--manifest",
            str(program_root / "manifest.json"),
            "--oracle-report",
            str(report_path),
            "--refinement-proposal",
            str(proposal_path),
            "--runtime-episode",
            str(runtime_episode),
            "--out",
            str(tmp_path / "promotion" / "bad.json"),
        ],
    )

    assert result.exit_code == 2
    assert "non_authority" in result.output


def test_program_promotion_refinement_consumes_model_jury_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    manifest = json.loads((program_root / "manifest.json").read_text(encoding="utf-8"))
    model_jury_path = tmp_path / "promotion" / "model_jury_results.json"
    _write_json(model_jury_path, _model_jury_result_for_manifest(manifest))
    before = _file_hashes(program_root)

    result = runner.invoke(
        app,
        [
            "program-promote",
            "review",
            "--manifest",
            str(program_root / "manifest.json"),
            "--oracle-report",
            str(report_path),
            "--refinement-proposal",
            str(proposal_path),
            "--model-jury-results",
            str(model_jury_path),
            "--out",
            str(tmp_path / "promotion" / "promotion_review_refined.json"),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["created_from"]["model_jury_results_path"] == str(
        model_jury_path.resolve()
    )
    assert payload["evidence_summary"]["model_jury_results"] == {
        "present": True,
        "path": str(model_jury_path.resolve()),
        "sha256": hashlib.sha256(model_jury_path.read_bytes()).hexdigest(),
        "schema_version": "program-model-jury-results-v1",
        "status": "executed",
        "execution_mode": "provider_backed_model",
        "provider_backed_model_calls": True,
        "selected_juror_count": 1,
        "judgment_counts": {
            "supports_review_evidence": 0,
            "withhold": 0,
            "reject": 0,
            "request_more_evidence": 1,
            "failed": 0,
        },
        "recommendation": "request_more_evidence",
        "improvement_request_count": 1,
        "adjudicator_repo": "target-repo",
        "promotion_authority": False,
    }
    readiness = payload["review_readiness"]
    assert readiness["model_jury_execution_present"] is True
    assert readiness["ready_for_adjudicator_review"] is False
    assert readiness["missing_required_evidence"] == [
        "no_promotion_adjudicator_decision"
    ]
    assert payload["promotion_review_delta"]["model_jury_execution"] == (
        "satisfied_by_explicit_model_jury_results"
    )
    assert "model_jury_results" in payload["adjudication_packet"]["evidence_refs"]
    assert payload["non_authority"]["promotion_authority"] is False
    assert _file_hashes(program_root) == before


def test_program_promotion_refinement_rejects_model_jury_identity_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    manifest = json.loads((program_root / "manifest.json").read_text(encoding="utf-8"))
    model_jury = _model_jury_result_for_manifest(manifest)
    identity = dict(model_jury["identity"])
    identity["candidate_id"] = "prog-cand-other"
    model_jury["identity"] = identity
    bad_model_jury_path = tmp_path / "promotion" / "bad-model-jury.json"
    _write_json(bad_model_jury_path, model_jury)

    result = runner.invoke(
        app,
        [
            "program-promote",
            "review",
            "--manifest",
            str(program_root / "manifest.json"),
            "--oracle-report",
            str(report_path),
            "--refinement-proposal",
            str(proposal_path),
            "--model-jury-results",
            str(bad_model_jury_path),
            "--out",
            str(tmp_path / "promotion" / "review.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "candidate_id" in (result.stdout + result.stderr)
    assert not (tmp_path / "promotion" / "review.json").exists()


def test_program_promotion_refinement_rejects_authority_widened_model_jury(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    manifest = json.loads((program_root / "manifest.json").read_text(encoding="utf-8"))
    model_jury = _model_jury_result_for_manifest(manifest)
    effect = dict(model_jury["effect"])
    effect["external_authority_mutated"] = True
    model_jury["effect"] = effect
    bad_model_jury_path = tmp_path / "promotion" / "bad-model-jury.json"
    _write_json(bad_model_jury_path, model_jury)

    with pytest.raises(
        ProgramPromotionRefinementError,
        match="external_authority_mutated",
    ):
        build_program_promotion_refinement(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            refinement_proposal_path=proposal_path,
            model_jury_results_path=bad_model_jury_path,
        )


def test_program_promotion_refinement_rejects_model_jury_promotion_authority_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    manifest = json.loads((program_root / "manifest.json").read_text(encoding="utf-8"))
    model_jury = _model_jury_result_for_manifest(manifest)
    adjudicator = dict(model_jury["adjudicator"])
    adjudicator["promotion_authority"] = True
    model_jury["adjudicator"] = adjudicator
    bad_model_jury_path = tmp_path / "promotion" / "bad-model-jury.json"
    _write_json(bad_model_jury_path, model_jury)

    with pytest.raises(ProgramPromotionRefinementError, match="promotion authority"):
        build_program_promotion_refinement(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            refinement_proposal_path=proposal_path,
            model_jury_results_path=bad_model_jury_path,
        )


def test_program_promotion_refinement_rejects_unjudged_model_jury_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    manifest = json.loads((program_root / "manifest.json").read_text(encoding="utf-8"))
    model_jury = _model_jury_result_for_manifest(manifest)
    model_jury["juror_results"] = [{"juror_id": "authority_agent", "status": "failed"}]
    bad_model_jury_path = tmp_path / "promotion" / "bad-model-jury.json"
    _write_json(bad_model_jury_path, model_jury)

    with pytest.raises(ProgramPromotionRefinementError, match="judged juror"):
        build_program_promotion_refinement(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            refinement_proposal_path=proposal_path,
            model_jury_results_path=bad_model_jury_path,
        )


def test_program_promotion_refinement_rejects_authority_widened_oracle_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["non_authority"]["oracle_promotion"] = True
    bad_report_path = tmp_path / "oracle" / "bad-report.json"
    _write_json(bad_report_path, report)

    result = runner.invoke(
        app,
        [
            "program-promote",
            "review",
            "--manifest",
            str(program_root / "manifest.json"),
            "--oracle-report",
            str(bad_report_path),
            "--refinement-proposal",
            str(proposal_path),
            "--out",
            str(tmp_path / "promotion" / "review.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "oracle_promotion" in (result.stdout + result.stderr)
    assert not (tmp_path / "promotion" / "review.json").exists()


def test_program_promotion_refinement_rejects_authority_widened_proposal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    proposal["non_authority"]["promotion_authority"] = True
    bad_proposal_path = tmp_path / "refinement" / "bad-proposal.json"
    _write_json(bad_proposal_path, proposal)

    with pytest.raises(ProgramPromotionRefinementError, match="promotion_authority"):
        build_program_promotion_refinement(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            refinement_proposal_path=bad_proposal_path,
        )


def test_program_promotion_refinement_rejects_stale_proposal_oracle_report_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["total_records"] = int(report.get("total_records") or 0) + 1
    _write_json(report_path, report)

    with pytest.raises(ProgramPromotionRefinementError, match="Oracle report hash"):
        build_program_promotion_refinement(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            refinement_proposal_path=proposal_path,
        )


def test_program_promotion_refinement_rejects_oracle_report_partial_identity_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    manifest = json.loads((program_root / "manifest.json").read_text(encoding="utf-8"))
    record = report["records"][0]
    record["identity"]["request_id"] = manifest["request"]["request_id"]
    record["identity"]["candidate_id"] = "prog-cand-other"
    bad_report_path = tmp_path / "oracle" / "partial-collision-report.json"
    _write_json(bad_report_path, report)

    with pytest.raises(
        ProgramPromotionRefinementError, match="matching manifest identity"
    ):
        build_program_promotion_refinement(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=bad_report_path,
            refinement_proposal_path=proposal_path,
        )


def test_program_promotion_refinement_rejects_oracle_report_identity_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    record = report["records"][0]
    record["identity"]["receipt_bundle_id"] = "prog-rb-other"
    record["identity"]["episode_id"] = "prog-ep-other"
    record["identity"]["assembly_id"] = "prog-asm-other"
    record["identity"]["candidate_id"] = "prog-cand-other"
    record["identity"]["request_id"] = "prog-req-other"
    bad_report_path = tmp_path / "oracle" / "mismatch-report.json"
    _write_json(bad_report_path, report)

    with pytest.raises(
        ProgramPromotionRefinementError, match="matching manifest identity"
    ):
        build_program_promotion_refinement(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=bad_report_path,
            refinement_proposal_path=proposal_path,
        )


def test_program_promotion_refinement_rejects_proposal_identity_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    proposal["identity"]["candidate_id"] = "prog-cand-other"
    bad_proposal_path = tmp_path / "refinement" / "mismatch-proposal.json"
    _write_json(bad_proposal_path, proposal)

    result = runner.invoke(
        app,
        [
            "program-promote",
            "review",
            "--manifest",
            str(program_root / "manifest.json"),
            "--oracle-report",
            str(report_path),
            "--refinement-proposal",
            str(bad_proposal_path),
            "--out",
            str(tmp_path / "promotion" / "review.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "candidate_id" in (result.stdout + result.stderr)
    assert not (tmp_path / "promotion" / "review.json").exists()


def test_program_promotion_refinement_rejects_output_inside_program_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    packet = build_program_promotion_refinement(
        manifest_path=program_root / "manifest.json",
        oracle_report_path=report_path,
        refinement_proposal_path=proposal_path,
    )

    with pytest.raises(
        ProgramPromotionRefinementError, match="protected artifact root"
    ):
        write_program_promotion_refinement(
            packet,
            program_root / "promotion_review_refined.json",
        )
    with pytest.raises(
        ProgramPromotionRefinementError, match="protected artifact root"
    ):
        write_program_promotion_refinement(
            packet,
            program_root / "local_review_packet.json",
        )


def test_program_promotion_refinement_uses_behavior_episode_for_dataset_only_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    dataset_path = tmp_path / "data" / "tickets.jsonl"
    _write_jsonl(
        dataset_path,
        [
            {
                "inputs": {"ticket_text": f"ticket {index}"},
                "outputs": {"urgency": "high" if index % 2 else "low"},
            }
            for index in range(8)
        ],
    )
    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="DatasetReviewProgram",
            objective="Classify support ticket urgency.",
            inputs=["ticket_text"],
            outputs=["urgency"],
            metric="exact_match",
            dataset={
                "path": str(dataset_path),
                "input_fields": ["ticket_text"],
                "output_fields": ["urgency"],
                "split": {
                    "strategy": "ratio",
                    "train": 0.5,
                    "validation": 0.25,
                    "test": 0.25,
                    "seed": 7,
                },
            },
        ),
        outdir=tmp_path / "program",
    )
    program_root = Path(artifact.root_path)
    assert not (program_root / "behavior_results.json").exists()
    behavior_episode = json.loads(
        (program_root / "behavior_episode.json").read_text(encoding="utf-8")
    )
    index_path = tmp_path / "oracle" / "coordinates.db"
    index_result = index_program_oracle_evidence_path(
        program_root,
        index_path=index_path,
    )
    assert index_result["indexed"] == 1
    report = build_program_oracle_evidence_report(index_path=index_path)
    report_path = tmp_path / "oracle" / "program-evidence-report.json"
    _write_json(report_path, report)
    proposal = build_program_refinement_proposal(
        manifest_path=program_root / "manifest.json",
        oracle_report_path=report_path,
    )
    proposal_path = tmp_path / "refinement" / "refinement_proposal.json"
    _write_json(proposal_path, proposal)
    before = _file_hashes(program_root)

    payload = build_program_promotion_refinement(
        manifest_path=program_root / "manifest.json",
        oracle_report_path=report_path,
        refinement_proposal_path=proposal_path,
    )

    assert payload["schema_version"] == "program-promotion-review-refined-v1"
    assert payload["status"] == "review_packet_ready"
    assert payload["created_from"]["behavior_results_path"] is None
    assert payload["created_from"]["behavior_episode_path"] == str(
        (program_root / "behavior_episode.json").resolve()
    )
    expected_status_counts = behavior_episode["summary"]["status_counts"]
    assert payload["evidence_summary"]["behavior"] == {
        "present": True,
        "status": behavior_episode["summary"]["status"],
        "example_count": behavior_episode["summary"]["total"],
        "source_count": behavior_episode["summary"]["source_count"],
        "status_counts": expected_status_counts,
        "behavior_results_present": False,
        "behavior_episode_present": True,
        "behavior_evidence_kind": "behavior_episode",
    }
    assert payload["review_readiness"]["behavior_evidence_present"] is True
    assert payload["review_readiness"]["missing_required_evidence"] == [
        "no_model_jury_execution_episode",
        "no_promotion_adjudicator_decision",
    ]
    assert (
        "behavior_results.json" not in payload["adjudication_packet"]["evidence_refs"]
    )
    assert "behavior_episode.json" in payload["adjudication_packet"]["evidence_refs"]
    assert payload["non_authority"]["promotion_authority"] is False
    assert _file_hashes(program_root) == before


def test_program_promotion_refinement_degrades_without_behavior_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    intent = ProgramIntent(
        name="NoExamplesProgram",
        objective="Answer a question.",
        inputs=["question"],
        outputs=["answer"],
    )
    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    program_root = Path(artifact.root_path)
    assert not (program_root / "behavior_results.json").exists()
    assert not (program_root / "oracle_evidence.json").exists()
    report = build_program_oracle_evidence_report(
        index_path=tmp_path / "oracle" / "coordinates.db"
    )
    report_path = tmp_path / "oracle-report.json"
    _write_json(report_path, report)
    proposal = build_program_refinement_proposal(
        manifest_path=program_root / "manifest.json",
        oracle_report_path=report_path,
    )
    proposal_path = tmp_path / "refinement" / "refinement_proposal.json"
    _write_json(proposal_path, proposal)
    before = _file_hashes(program_root)

    result = runner.invoke(
        app,
        [
            "program-promote",
            "review",
            "--manifest",
            str(program_root / "manifest.json"),
            "--oracle-report",
            str(report_path),
            "--refinement-proposal",
            str(proposal_path),
            "--out",
            str(tmp_path / "promotion" / "promotion_review_refined.json"),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "program-promotion-review-refined-v1"
    assert payload["status"] == "insufficient_behavior_evidence"
    assert payload["promotion_state"] == "not_promoted"
    assert payload["created_from"]["behavior_results_path"] is None
    assert payload["created_from"]["behavior_episode_path"] is None
    assert payload["evidence_summary"]["behavior"] == {
        "present": False,
        "status": "insufficient_behavior_evidence",
        "example_count": 0,
        "source_count": 0,
        "status_counts": {},
        "behavior_results_present": False,
        "behavior_episode_present": False,
        "behavior_evidence_kind": None,
    }
    assert payload["evidence_summary"]["oracle_report"] == {
        "present": True,
        "status": "no_program_oracle_evidence",
        "total_records": 0,
        "record_matched": False,
    }
    assert payload["evidence_summary"]["refinement_proposal"]["status"] == (
        "insufficient_behavior_evidence"
    )
    assert payload["review_readiness"]["missing_required_evidence"] == [
        "no_behavioral_evaluation_episode",
        "no_model_jury_execution_episode",
        "no_promotion_adjudicator_decision",
    ]
    assert (
        "behavior_results.json" not in payload["adjudication_packet"]["evidence_refs"]
    )
    assert payload["non_authority"]["automatic_promotion"] is False
    assert _file_hashes(program_root) == before
    assert not (tmp_path / "oracle" / "coordinates.db").exists()


def test_refined_review_contract_rejects_forged_evidence_summaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    packet = build_program_promotion_refinement(
        manifest_path=program_root / "manifest.json",
        oracle_report_path=report_path,
        refinement_proposal_path=proposal_path,
    )
    forged_oracle = json.loads(json.dumps(packet))
    forged_oracle["evidence_summary"]["oracle_report"]["status"] = "forged-success"
    with pytest.raises(
        ProgramPromotionRefinementError,
        match="Oracle summary does not match current evidence",
    ):
        validate_program_promotion_review_refined_contract(forged_oracle)

    forged_runtime = json.loads(json.dumps(packet))
    forged_runtime["created_from"]["runtime_episode_path"] = str(
        tmp_path / "missing-runtime.json"
    )
    forged_runtime["created_from"]["runtime_episode_sha256"] = "0" * 64
    forged_runtime["evidence_summary"]["runtime_episode"] = {
        "present": True,
        "status": "executed_quality_passed",
        "runtime_episode_id": "forged",
    }
    with pytest.raises(
        ProgramPromotionRefinementError,
        match="runtime-episode ref not found",
    ):
        validate_program_promotion_review_refined_contract(forged_runtime)


def test_program_promotion_refinement_rejects_symlink_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    packet = build_program_promotion_refinement(
        manifest_path=program_root / "manifest.json",
        oracle_report_path=report_path,
        refinement_proposal_path=proposal_path,
    )
    victim = tmp_path / "victim.json"
    victim.write_text("preserve me\n", encoding="utf-8")
    out_path = tmp_path / "review-link.json"
    out_path.symlink_to(victim)

    with pytest.raises(
        ProgramPromotionRefinementError,
        match="must not resolve through symlink components",
    ):
        write_program_promotion_refinement(packet, out_path)

    assert victim.read_text(encoding="utf-8") == "preserve me\n"


def test_program_promotion_refinement_atomic_write_preserves_existing_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    packet = build_program_promotion_refinement(
        manifest_path=program_root / "manifest.json",
        oracle_report_path=report_path,
        refinement_proposal_path=proposal_path,
    )
    out_path = tmp_path / "promotion" / "review.json"
    out_path.parent.mkdir()
    out_path.write_text("existing packet\n", encoding="utf-8")
    real_write = artifact_boundary.os.write
    calls = 0

    def fail_after_short_write(descriptor: int, content: bytes) -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            return real_write(descriptor, content[:7])
        raise OSError("simulated output failure")

    monkeypatch.setattr(artifact_boundary.os, "write", fail_after_short_write)
    with pytest.raises(
        ProgramPromotionRefinementError,
        match="failed before atomic replacement",
    ):
        write_program_promotion_refinement(packet, out_path)

    assert out_path.read_text(encoding="utf-8") == "existing packet\n"
    assert list(out_path.parent.glob(".*.tmp")) == []


def test_program_promotion_refinement_rejects_output_parent_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    packet = build_program_promotion_refinement(
        manifest_path=program_root / "manifest.json",
        oracle_report_path=report_path,
        refinement_proposal_path=proposal_path,
    )
    parent = tmp_path / "safe-output"
    parent.mkdir()
    parked_parent = tmp_path / "parked-output"
    out_path = parent / "review.json"
    real_validate = program_promotion_refinement._validate_packet_candidate_closure
    validation_calls = 0

    def validate_then_swap(value: Mapping[str, Any]) -> None:
        nonlocal validation_calls
        validation_calls += 1
        real_validate(value)
        if validation_calls == 2:
            parent.rename(parked_parent)
            parent.symlink_to(program_root, target_is_directory=True)

    monkeypatch.setattr(
        program_promotion_refinement,
        "_validate_packet_candidate_closure",
        validate_then_swap,
    )
    with pytest.raises(
        ProgramPromotionRefinementError,
        match="failed before atomic replacement",
    ):
        write_program_promotion_refinement(packet, out_path)

    assert not (program_root / "review.json").exists()
    assert not (parked_parent / "review.json").exists()
    assert list(parked_parent.glob(".*.tmp")) == []


def test_program_promotion_refinement_rejects_oversized_oracle_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    report_path.write_bytes(b"{" + b" " * (16 * 1024 * 1024) + b"}")

    with pytest.raises(
        ProgramPromotionRefinementError,
        match="exceeds the .* size limit",
    ):
        build_program_promotion_refinement(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            refinement_proposal_path=proposal_path,
        )


def test_refined_review_contract_rejects_symlinked_external_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    packet = build_program_promotion_refinement(
        manifest_path=program_root / "manifest.json",
        oracle_report_path=report_path,
        refinement_proposal_path=proposal_path,
    )
    report_link = tmp_path / "oracle-report-link.json"
    report_link.symlink_to(report_path)
    packet["created_from"]["oracle_report_path"] = str(report_link)

    with pytest.raises(
        ProgramPromotionRefinementError,
        match="descriptor read failed.*symbolic links",
    ):
        validate_program_promotion_review_refined_contract(packet)


@pytest.mark.parametrize("linked_input", ["manifest", "oracle", "proposal"])
def test_program_promotion_refinement_rejects_symlinked_build_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    linked_input: str,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    paths = {
        "manifest": program_root / "manifest.json",
        "oracle": report_path,
        "proposal": proposal_path,
    }
    link = tmp_path / f"{linked_input}-link.json"
    link.symlink_to(paths[linked_input])

    with pytest.raises(
        ProgramPromotionRefinementError,
        match="symlink|symbolic links",
    ):
        build_program_promotion_refinement(
            manifest_path=link if linked_input == "manifest" else paths["manifest"],
            oracle_report_path=link if linked_input == "oracle" else paths["oracle"],
            refinement_proposal_path=link
            if linked_input == "proposal"
            else paths["proposal"],
        )


def test_stable_evidence_read_wraps_descriptor_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    real_read = artifact_boundary.os.read
    failed = False

    def fail_first_read(descriptor: int, size: int) -> bytes:
        nonlocal failed
        descriptor_path = Path(f"/proc/self/fd/{descriptor}").resolve()
        if not failed and descriptor_path == report_path:
            failed = True
            raise OSError("simulated descriptor failure")
        return real_read(descriptor, size)

    monkeypatch.setattr(artifact_boundary.os, "read", fail_first_read)
    with pytest.raises(
        ProgramPromotionRefinementError,
        match="descriptor read failed",
    ):
        build_program_promotion_refinement(
            manifest_path=program_root / "manifest.json",
            oracle_report_path=report_path,
            refinement_proposal_path=proposal_path,
        )


def test_atomic_publication_surfaces_temporary_cleanup_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, proposal_path = _materialize_program_report_and_proposal(
        tmp_path,
        monkeypatch,
    )
    packet = build_program_promotion_refinement(
        manifest_path=program_root / "manifest.json",
        oracle_report_path=report_path,
        refinement_proposal_path=proposal_path,
    )
    out_path = tmp_path / "promotion" / "review.json"
    real_write = artifact_boundary.os.write

    def fail_write(descriptor: int, content: bytes) -> int:
        real_write(descriptor, content[:3])
        raise OSError("simulated write failure")

    def fail_unlink(*_args: object, **_kwargs: object) -> None:
        raise OSError("simulated cleanup failure")

    monkeypatch.setattr(artifact_boundary.os, "write", fail_write)
    monkeypatch.setattr(artifact_boundary.os, "unlink", fail_unlink)
    with pytest.raises(
        ProgramPromotionRefinementError,
        match="cleanup also failed",
    ):
        write_program_promotion_refinement(packet, out_path)

    assert not out_path.exists()

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import os
from typing import Any, Mapping

from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_service import materialize_program_from_intent
from dspx.services import program_model_jury_execution as model_jury
from dspx.services.program_model_jury_validation import (
    validate_program_model_jury_results_contract,
)

runner = CliRunner()


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _setup_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")


def _materialize_program(tmp_path: Path, monkeypatch) -> Path:
    _setup_env(tmp_path, monkeypatch)
    intent = ProgramIntent(
        name="DesignReviewProgram",
        objective="Extract DesignMD visual dossier evidence.",
        inputs=["visual_source_packet_json"],
        outputs=["role_findings_json", "component_inventory_json"],
        metric="exact_match",
        constraints=[
            "preserve observed inferred unverified labels",
            "do not claim design acceptance",
        ],
        examples=[
            {
                "inputs": {"visual_source_packet_json": '{"image_count": 1}'},
                "outputs": {
                    "role_findings_json": "{}",
                    "component_inventory_json": "{}",
                },
            }
        ],
        jury={
            "selection_model": "perspective_balanced_explicit_pool",
            "minimum_jurors": 2,
            "perspectives": ["role_coverage", "authority_boundaries"],
            "jurors": [
                {
                    "id": "role_coverage_agent",
                    "model": "stub",
                    "provider": "stub",
                    "perspective": "role_coverage",
                },
                {
                    "id": "authority_agent",
                    "model": "stub",
                    "provider": "stub",
                    "perspective": "authority_boundaries",
                },
            ],
        },
    )
    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    return Path(artifact.root_path)


def _fake_provider(provider: str | None = None) -> dict[str, Any]:
    return {"status": "configured", "provider": provider or "stub"}


def _fake_juror_model(
    *,
    juror: Mapping[str, Any],
    rubric: Mapping[str, Any],
    candidate_identity: Mapping[str, Any],
    evidence_json: str,
    adjudicator: Mapping[str, Any],
) -> dict[str, Any]:
    assert candidate_identity["schema_version"] == "program-candidate-assembly-v1"
    assert "candidate_id" in candidate_identity["identity"]
    assert "component_inventory" in evidence_json
    assert adjudicator["repo"] == "calisthenics-ai-coach"
    perspective = str(juror.get("perspective"))
    return {
        "outcome": "request_more_evidence"
        if perspective == "role_coverage"
        else "withhold",
        "rationale": f"{perspective} needs explicit review before acceptance.",
        "evidence_strengths": ["evidence was supplied"],
        "concerns": ["not accepted authority"],
        "improvement_requests": [f"improve {perspective}"],
        "confidence": "medium",
        "rubric_seen": rubric.get("juror_id"),
    }


def test_model_jury_service_calls_provider_backed_jurors_without_mutating_candidate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    extra_evidence = tmp_path / "component_inventory_json"
    extra_evidence.write_text(
        json.dumps(
            {
                "schemaVersion": "designmd.component-inventory.v1",
                "items": [{"name": "WorkoutCameraPanel"}],
            }
        ),
        encoding="utf-8",
    )
    before = _file_hashes(program_root)
    monkeypatch.setattr(model_jury, "_configure_provider", _fake_provider)
    monkeypatch.setattr(model_jury, "_run_juror_model", _fake_juror_model)

    payload = model_jury.build_program_model_jury_execution_result(
        manifest_path=program_root / "manifest.json",
        evidence_paths=[extra_evidence],
        provider="stub",
        adjudicator_repo="calisthenics-ai-coach",
    )

    assert payload["schema_version"] == "program-model-jury-results-v1"
    assert payload["status"] == "executed"
    assert payload["created_from"]["manifest_path"] == str(
        (program_root / "manifest.json").resolve()
    )
    assert (
        payload["created_from"]["manifest_sha256"]
        == hashlib.sha256((program_root / "manifest.json").read_bytes()).hexdigest()
    )
    assert (
        payload["created_from"]["jury_sha256"]
        == hashlib.sha256((program_root / "jury.json").read_bytes()).hexdigest()
    )
    assert payload["jury"]["execution_mode"] == "provider_backed_model"
    assert payload["jury"]["provider_backed_model_calls"] is True
    assert payload["adjudicator"] == {
        "id": "target_repo_product_manager_agent",
        "kind": "target_repo_product_manager_agent",
        "repo": "calisthenics-ai-coach",
        "authority": "downstream_domain_review_recommendation_only",
        "promotion_authority": False,
    }
    assert payload["evidence"]["default_behavior"]["present"] is True
    assert payload["evidence"]["extra_evidence_count"] == 1
    assert len(payload["juror_results"]) == 2
    assert {item["status"] for item in payload["juror_results"]} == {"judged"}
    assert payload["aggregate"]["judgment_counts"]["request_more_evidence"] == 1
    assert payload["aggregate"]["judgment_counts"]["withhold"] == 1
    assert payload["aggregate"]["recommendation"] == "request_more_evidence"
    assert (
        "improve role_coverage" in payload["aggregate"]["unique_improvement_requests"]
    )
    assert payload["effect"]["program_files_mutated"] is False
    assert _file_hashes(program_root) == before


def test_model_jury_contract_rejects_missing_bound_jury_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    extra_evidence = tmp_path / "component_inventory_json"
    extra_evidence.write_text(
        json.dumps({"schemaVersion": "designmd.component-inventory.v1"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(model_jury, "_configure_provider", _fake_provider)
    monkeypatch.setattr(model_jury, "_run_juror_model", _fake_juror_model)
    payload = model_jury.build_program_model_jury_execution_result(
        manifest_path=program_root / "manifest.json",
        evidence_paths=[extra_evidence],
        provider="stub",
        adjudicator_repo="calisthenics-ai-coach",
    )
    payload["created_from"].pop("jury_path")

    try:
        validate_program_model_jury_results_contract(
            payload,
            valid_manifest_refs={
                (program_root / "manifest.json").resolve(): hashlib.sha256(
                    (program_root / "manifest.json").read_bytes()
                ).hexdigest()
            },
        )
    except ValueError as exc:
        assert "planned jury path is required" in str(exc)
    else:  # pragma: no cover - defensive assertion for missing-ref rejection
        raise AssertionError("model-jury missing jury ref was accepted")


def test_model_jury_contract_rejects_missing_evidence_entries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    extra_evidence = tmp_path / "component_inventory_json"
    extra_evidence.write_text(
        json.dumps({"schemaVersion": "designmd.component-inventory.v1"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(model_jury, "_configure_provider", _fake_provider)
    monkeypatch.setattr(model_jury, "_run_juror_model", _fake_juror_model)
    payload = model_jury.build_program_model_jury_execution_result(
        manifest_path=program_root / "manifest.json",
        evidence_paths=[extra_evidence],
        provider="stub",
        adjudicator_repo="calisthenics-ai-coach",
    )
    payload["evidence"] = {"entry_count": 99}

    try:
        validate_program_model_jury_results_contract(
            payload,
            valid_manifest_refs={
                (program_root / "manifest.json").resolve(): hashlib.sha256(
                    (program_root / "manifest.json").read_bytes()
                ).hexdigest()
            },
        )
    except ValueError as exc:
        assert "evidence entries are required" in str(exc)
    else:  # pragma: no cover - defensive assertion for missing-evidence rejection
        raise AssertionError("model-jury missing evidence entries was accepted")


def test_model_jury_contract_rejects_stale_evidence_hash(
    tmp_path: Path,
    monkeypatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    extra_evidence = tmp_path / "component_inventory_json"
    extra_evidence.write_text(
        json.dumps(
            {
                "schemaVersion": "designmd.component-inventory.v1",
                "items": [{"name": "WorkoutCameraPanel"}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(model_jury, "_configure_provider", _fake_provider)
    monkeypatch.setattr(model_jury, "_run_juror_model", _fake_juror_model)
    payload = model_jury.build_program_model_jury_execution_result(
        manifest_path=program_root / "manifest.json",
        evidence_paths=[extra_evidence],
        provider="stub",
        adjudicator_repo="calisthenics-ai-coach",
    )
    extra_evidence.write_text('{"changed": true}', encoding="utf-8")

    try:
        validate_program_model_jury_results_contract(
            payload,
            valid_manifest_refs={
                (program_root / "manifest.json").resolve(): hashlib.sha256(
                    (program_root / "manifest.json").read_bytes()
                ).hexdigest()
            },
        )
    except ValueError as exc:
        assert "evidence entry" in str(exc)
        assert "sha256 does not match" in str(exc)
    else:  # pragma: no cover - defensive assertion for stale-evidence rejection
        raise AssertionError("stale model-jury evidence hash was accepted")


def test_model_jury_contract_rejects_status_and_aggregate_drift(
    tmp_path: Path,
    monkeypatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    extra_evidence = tmp_path / "component_inventory_json"
    extra_evidence.write_text(
        json.dumps({"schemaVersion": "designmd.component-inventory.v1"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(model_jury, "_configure_provider", _fake_provider)
    monkeypatch.setattr(model_jury, "_run_juror_model", _fake_juror_model)
    payload = model_jury.build_program_model_jury_execution_result(
        manifest_path=program_root / "manifest.json",
        evidence_paths=[extra_evidence],
        provider="stub",
        adjudicator_repo="calisthenics-ai-coach",
    )
    valid_manifest_refs = {
        (program_root / "manifest.json").resolve(): hashlib.sha256(
            (program_root / "manifest.json").read_bytes()
        ).hexdigest()
    }

    bad_aggregate = json.loads(json.dumps(payload))
    bad_aggregate["aggregate"]["judgment_counts"]["request_more_evidence"] = 99
    try:
        validate_program_model_jury_results_contract(
            bad_aggregate, valid_manifest_refs=valid_manifest_refs
        )
    except ValueError as exc:
        assert "aggregate judgment_counts do not match juror_results" in str(exc)
    else:  # pragma: no cover - defensive assertion for aggregate drift rejection
        raise AssertionError("model-jury aggregate drift was accepted")

    bad_status = json.loads(json.dumps(payload))
    bad_status["juror_results"][0]["status"] = "failed"
    try:
        validate_program_model_jury_results_contract(
            bad_status, valid_manifest_refs=valid_manifest_refs
        )
    except ValueError as exc:
        assert "status must be executed_with_failures when jurors failed" in str(exc)
    else:  # pragma: no cover - defensive assertion for status drift rejection
        raise AssertionError("model-jury status drift was accepted")


def test_model_jury_contract_rejects_malformed_juror_and_noncanonical_counts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    extra_evidence = tmp_path / "component_inventory_json"
    extra_evidence.write_text(
        json.dumps({"schemaVersion": "designmd.component-inventory.v1"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(model_jury, "_configure_provider", _fake_provider)
    monkeypatch.setattr(model_jury, "_run_juror_model", _fake_juror_model)
    payload = model_jury.build_program_model_jury_execution_result(
        manifest_path=program_root / "manifest.json",
        evidence_paths=[extra_evidence],
        provider="stub",
        adjudicator_repo="calisthenics-ai-coach",
    )
    valid_manifest_refs = {
        (program_root / "manifest.json").resolve(): hashlib.sha256(
            (program_root / "manifest.json").read_bytes()
        ).hexdigest()
    }

    malformed_juror = json.loads(json.dumps(payload))
    malformed_juror["juror_results"].append("not-an-object")
    try:
        validate_program_model_jury_results_contract(
            malformed_juror, valid_manifest_refs=valid_manifest_refs
        )
    except ValueError as exc:
        assert "juror_results[2] must be an object" in str(exc)
    else:  # pragma: no cover - defensive assertion for juror shape rejection
        raise AssertionError("malformed model-jury juror result was accepted")

    bad_juror_status = json.loads(json.dumps(payload))
    bad_juror_status["juror_results"][0]["status"] = "finished"
    try:
        validate_program_model_jury_results_contract(
            bad_juror_status, valid_manifest_refs=valid_manifest_refs
        )
    except ValueError as exc:
        assert "juror_results[0].status must be judged or failed" in str(exc)
    else:  # pragma: no cover - defensive assertion for status enum rejection
        raise AssertionError("invalid model-jury juror status was accepted")

    bad_judgment_outcome = json.loads(json.dumps(payload))
    bad_judgment_outcome["juror_results"][0]["judgment"]["outcome"] = "approve"
    try:
        validate_program_model_jury_results_contract(
            bad_judgment_outcome, valid_manifest_refs=valid_manifest_refs
        )
    except ValueError as exc:
        assert "juror_results[0].judgment.outcome must be" in str(exc)
    else:  # pragma: no cover - defensive assertion for outcome enum rejection
        raise AssertionError("invalid model-jury judgment outcome was accepted")

    bad_selected_count = json.loads(json.dumps(payload))
    bad_selected_count["jury"]["selected_juror_count"] = True
    try:
        validate_program_model_jury_results_contract(
            bad_selected_count, valid_manifest_refs=valid_manifest_refs
        )
    except ValueError as exc:
        assert "selected_juror_count must be an integer" in str(exc)
    else:  # pragma: no cover - defensive assertion for bool count rejection
        raise AssertionError(
            "noncanonical model-jury selected_juror_count was accepted"
        )

    bad_aggregate_count = json.loads(json.dumps(payload))
    bad_aggregate_count["aggregate"]["judgment_counts"]["withhold"] = "1"
    try:
        validate_program_model_jury_results_contract(
            bad_aggregate_count, valid_manifest_refs=valid_manifest_refs
        )
    except ValueError as exc:
        assert "aggregate judgment_counts.withhold must be an integer" in str(exc)
    else:  # pragma: no cover - defensive assertion for string count rejection
        raise AssertionError("noncanonical model-jury aggregate count was accepted")

    bad_entry_count = json.loads(json.dumps(payload))
    bad_entry_count["evidence"]["entry_count"] = 1.9
    try:
        validate_program_model_jury_results_contract(
            bad_entry_count, valid_manifest_refs=valid_manifest_refs
        )
    except ValueError as exc:
        assert "evidence entry_count must be an integer" in str(exc)
    else:  # pragma: no cover - defensive assertion for float count rejection
        raise AssertionError(
            "noncanonical model-jury evidence entry_count was accepted"
        )


def test_program_promote_model_jury_cli_writes_sidecar(
    tmp_path: Path,
    monkeypatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    extra_evidence = tmp_path / "role_findings_json"
    extra_evidence.write_text(
        json.dumps(
            {
                "schemaVersion": "designmd.role-findings.bundle.v1",
                "roles": [{"role": "visual designer", "findings": []}],
            }
        ),
        encoding="utf-8",
    )
    out_path = tmp_path / "promotion" / "model_jury_results.json"
    monkeypatch.setattr(model_jury, "_configure_provider", _fake_provider)
    monkeypatch.setattr(model_jury, "_run_juror_model", _fake_juror_model)

    result = runner.invoke(
        app,
        [
            "program-promote",
            "model-jury",
            "--manifest",
            str(program_root / "manifest.json"),
            "--evidence",
            str(extra_evidence),
            "--provider",
            "stub",
            "--adjudicator-repo",
            "calisthenics-ai-coach",
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert out_path.exists()
    assert json.loads(out_path.read_text(encoding="utf-8")) == payload
    assert payload["schema_version"] == "program-model-jury-results-v1"
    assert payload["created_from"]["evidence_paths"] == [str(extra_evidence.resolve())]
    assert payload["adjudicator"]["repo"] == "calisthenics-ai-coach"
    assert payload["non_authority"]["promotion_approval"] is False


def test_model_jury_rejects_oversized_evidence_before_provider_calls(
    tmp_path: Path,
    monkeypatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    huge_evidence = tmp_path / "huge.json"
    huge_evidence.write_text(
        "x" * (model_jury.MAX_MODEL_JURY_EVIDENCE_BYTES + 1), encoding="utf-8"
    )

    def fail_provider(provider: str | None = None) -> dict[str, Any]:
        raise AssertionError("provider should not be configured for oversized evidence")

    monkeypatch.setattr(model_jury, "_configure_provider", fail_provider)

    result = runner.invoke(
        app,
        [
            "program-promote",
            "model-jury",
            "--manifest",
            str(program_root / "manifest.json"),
            "--evidence",
            str(huge_evidence),
            "--provider",
            "stub",
            "--out",
            str(tmp_path / "promotion" / "model_jury_results.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "byte limit" in result.output


def test_configure_provider_restores_provider_env_on_success(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DSPX_PROVIDER", "before")

    class FakeDspy:
        @staticmethod
        def configure(*, lm: object) -> None:
            assert lm is not None

    class FakeProvider:
        model = "stub"

    original_import = __import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> object:
        if name == "dspy":
            return FakeDspy
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    monkeypatch.setattr("dspx.provider_registry.ensure_default_providers", lambda: None)
    monkeypatch.setattr(
        "dspx.provider_registry.create_from_env", lambda default: FakeProvider()
    )

    assert model_jury._configure_provider("temporary")["provider"] == "stub"
    assert os.environ["DSPX_PROVIDER"] == "before"


def test_program_promote_model_jury_rejects_evidence_output_overlap_before_provider_calls(
    tmp_path: Path,
    monkeypatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text('{"ok": true}', encoding="utf-8")

    def fail_provider(provider: str | None = None) -> dict[str, Any]:
        raise AssertionError("provider should not be configured for unsafe output")

    monkeypatch.setattr(model_jury, "_configure_provider", fail_provider)

    result = runner.invoke(
        app,
        [
            "program-promote",
            "model-jury",
            "--manifest",
            str(program_root / "manifest.json"),
            "--evidence",
            str(evidence_path),
            "--provider",
            "stub",
            "--out",
            str(evidence_path),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "must not overwrite an input artifact" in result.output
    assert evidence_path.read_text(encoding="utf-8") == '{"ok": true}'


def test_program_promote_model_jury_rejects_evidence_directory_output_before_provider_calls(
    tmp_path: Path,
    monkeypatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    (evidence_dir / "evidence.json").write_text('{"ok": true}', encoding="utf-8")

    def fail_provider(provider: str | None = None) -> dict[str, Any]:
        raise AssertionError("provider should not be configured for unsafe output")

    monkeypatch.setattr(model_jury, "_configure_provider", fail_provider)

    result = runner.invoke(
        app,
        [
            "program-promote",
            "model-jury",
            "--manifest",
            str(program_root / "manifest.json"),
            "--evidence",
            str(evidence_dir),
            "--provider",
            "stub",
            "--out",
            str(evidence_dir / "model_jury_results.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "protected artifact root" in result.output
    assert not (evidence_dir / "model_jury_results.json").exists()


def test_program_promote_model_jury_rejects_candidate_root_output_before_provider_calls(
    tmp_path: Path,
    monkeypatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)

    def fail_provider(provider: str | None = None) -> dict[str, Any]:
        raise AssertionError("provider should not be configured for unsafe output")

    monkeypatch.setattr(model_jury, "_configure_provider", fail_provider)

    result = runner.invoke(
        app,
        [
            "program-promote",
            "model-jury",
            "--manifest",
            str(program_root / "manifest.json"),
            "--provider",
            "stub",
            "--out",
            str(program_root / "model_jury_results.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert (
        "program model jury results output must not be written inside" in result.output
    )
    assert not (program_root / "model_jury_results.json").exists()

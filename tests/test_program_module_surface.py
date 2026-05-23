from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest

from dspx.services import program_service
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_service import materialize_program_from_intent
from dspx.services.run_replay_service import check_run_receipt


def _configure_local(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")


def test_single_module_program_gen_emits_module_surface_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_local(tmp_path, monkeypatch)
    intent = ProgramIntent(
        name="AnswerQuestion",
        objective="Answer a question from supplied context.",
        inputs=["context", "question"],
        outputs=["answer"],
    )

    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    root = Path(artifact.root_path)
    module_surfaces_path = root / "module_surfaces.json"
    assert module_surfaces_path.exists()

    module_surfaces = json.loads(module_surfaces_path.read_text(encoding="utf-8"))
    assert module_surfaces["schema_version"] == "program-module-surfaces-v1"
    assert module_surfaces["status"] == "materialized"
    assert module_surfaces["module_surface_count"] == 1
    assert module_surfaces["authority"] == (
        "module_surface_contracts_only_non_authoritative"
    )
    surface = module_surfaces["module_surfaces"][0]
    assert surface["schema_version"] == "program-module-surface-v1"
    assert surface["module_id"] == "generated_module"
    assert surface["source_kind"] == "generated_single_module_scaffold"
    assert surface["primitive"] == "Predict"
    assert surface["signature"] == {
        "name": "AnswerQuestionSignature",
        "inputs": ["context", "question"],
        "outputs": ["answer"],
    }
    assert surface["generated"] == {
        "signature_class": "AnswerQuestionSignature",
        "module_class": "AnswerQuestionModule",
        "signature_path": "signature.py",
        "module_path": "module.py",
    }
    assert surface["capability_ref"] == {
        "schema_version": "program-capability-contract-v1",
        "capability_id": "dspy.primitive.Predict",
        "primitive": "Predict",
        "status": "materializable",
        "materializable": True,
        "runtime_binding": "generated_dspy_primitive",
    }
    assert surface["io"] == {"inputs": ["context", "question"], "outputs": ["answer"]}
    assert surface["effects"] == {
        "provider_called": False,
        "tool_called": False,
        "custom_import_loaded": False,
        "network": False,
        "filesystem_read": False,
        "filesystem_write": False,
        "subprocess": False,
        "external_authority": False,
    }
    assert surface["non_authority"] == {
        "oracle_ranking": False,
        "oracle_pruning": False,
        "oracle_promotion": False,
        "promotion_authority": False,
        "governance_authority": False,
        "external_mutation": False,
    }

    module_surfaces_hash = hashlib.sha256(module_surfaces_path.read_bytes()).hexdigest()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    receipt = json.loads((root / "manifest.json.meta.json").read_text(encoding="utf-8"))
    assert "module_surfaces" in manifest["program_plan"]["surfaces"][8]["kind"]
    assert "module_surfaces" in manifest["candidate_assembly"]["surface_kinds"]
    assert manifest["request"]["module_surfaces_hash"] == module_surfaces_hash
    assert manifest["module_surfaces_artifact"] == {
        "path": "module_surfaces.json",
        "content_hash": module_surfaces_hash,
        "schema_version": "program-module-surfaces-v1",
    }
    assert manifest["program_module_surfaces"] == module_surfaces
    assert manifest["receipt_bundle"]["evidence"]["module_surfaces_hash"] == (
        module_surfaces_hash
    )
    assert (
        manifest["receipt_bundle"]["evidence"]["surface_hashes"]["module_surfaces.json"]
        == module_surfaces_hash
    )
    capability_registry_path = root / "program_capability_registry.json"
    capability_registry = json.loads(
        capability_registry_path.read_text(encoding="utf-8")
    )
    capability_registry_hash = hashlib.sha256(
        capability_registry_path.read_bytes()
    ).hexdigest()
    assert capability_registry["schema_version"] == "program-capability-registry-v1"
    assert capability_registry["status"] == "descriptor_only_no_runtime_binding"
    assert capability_registry["effects"]["tool_called"] is False
    assert capability_registry["effects"]["custom_import_loaded"] is False
    assert manifest["request"]["capability_registry_hash"] == capability_registry_hash
    assert manifest["capability_registry_artifact"] == {
        "path": "program_capability_registry.json",
        "content_hash": capability_registry_hash,
        "schema_version": "program-capability-registry-v1",
    }
    assert manifest["program_capability_registry"] == capability_registry
    assert receipt["run_summary"]["module_surfaces_hash"] == module_surfaces_hash
    assert (
        receipt["run_summary"]["capability_registry_hash"] == capability_registry_hash
    )
    assert receipt["program_module_surfaces"] == module_surfaces
    assert receipt["program_capability_registry"] == capability_registry

    replay = check_run_receipt(root / "manifest.json.meta.json")
    assert replay["status"] == "ok"
    assert replay["checks"]["program_module_surfaces_exists"] is True
    assert replay["checks"]["program_module_surfaces_hash_match"] is True
    assert replay["program_module_surfaces_hash"] == module_surfaces_hash
    assert replay["checks"]["program_capability_registry_exists"] is True
    assert replay["checks"]["program_capability_registry_hash_match"] is True
    assert replay["program_capability_registry_hash"] == capability_registry_hash


def test_pipeline_program_gen_emits_one_module_surface_per_topology_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_local(tmp_path, monkeypatch)
    real_run = program_service.subprocess.run
    subprocess_calls: list[list[str]] = []

    def spy_run(
        command: list[str], *args: Any, **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        command_text = [str(part) for part in command]
        command_names = [Path(part).name for part in command_text]
        assert "ak" not in command_names
        assert "oracle" not in command_names
        assert "program-refine" not in command_names
        assert "program-promote" not in command_names
        subprocess_calls.append(command_text)
        return cast(
            subprocess.CompletedProcess[str], real_run(command, *args, **kwargs)
        )

    monkeypatch.setattr(program_service.subprocess, "run", spy_run)
    intent = ProgramIntent(
        name="SupportRouterProgram",
        objective="Route a support ticket to a billing or technical answer path.",
        inputs=["ticket_text"],
        outputs=["answer"],
        metric="exact_match",
        constraints=["use only the supplied ticket text"],
        topology={
            "kind": "pipeline",
            "execution_status": "declared_not_materialized",
            "modules": [
                {
                    "id": "classify_intent",
                    "primitive": "Predict",
                    "signature": {
                        "name": "ClassifyIntent",
                        "inputs": ["ticket_text"],
                        "outputs": ["intent"],
                    },
                },
                {
                    "id": "answer_billing",
                    "primitive": "ChainOfThought",
                    "signature": {
                        "name": "AnswerBillingQuestion",
                        "inputs": ["ticket_text"],
                        "outputs": ["answer"],
                    },
                },
                {
                    "id": "answer_technical",
                    "primitive": "ChainOfThought",
                    "signature": {
                        "name": "AnswerTechnicalQuestion",
                        "inputs": ["ticket_text"],
                        "outputs": ["answer"],
                    },
                },
            ],
            "edges": [
                {"from": "input", "to": "classify_intent"},
                {
                    "from": "classify_intent",
                    "to": "answer_billing",
                    "when": {"field": "intent", "equals": "billing"},
                },
                {
                    "from": "classify_intent",
                    "to": "answer_technical",
                    "when": {"field": "intent", "equals": "technical"},
                },
            ],
        },
        examples=[
            {
                "inputs": {"ticket_text": "My invoice is wrong"},
                "outputs": {"answer": "billing"},
            }
        ],
    )

    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    root = Path(artifact.root_path)
    module_surfaces = json.loads(
        (root / "module_surfaces.json").read_text(encoding="utf-8")
    )

    assert module_surfaces["schema_version"] == "program-module-surfaces-v1"
    assert module_surfaces["module_surface_count"] == 3
    surfaces = module_surfaces["module_surfaces"]
    assert [surface["module_id"] for surface in surfaces] == [
        "classify_intent",
        "answer_billing",
        "answer_technical",
    ]
    assert [surface["primitive"] for surface in surfaces] == [
        "Predict",
        "ChainOfThought",
        "ChainOfThought",
    ]
    assert [surface["signature"]["name"] for surface in surfaces] == [
        "ClassifyIntent",
        "AnswerBillingQuestion",
        "AnswerTechnicalQuestion",
    ]
    assert [surface["generated"]["module_class"] for surface in surfaces] == [
        "ClassifyIntentModule",
        "AnswerBillingQuestionModule",
        "AnswerTechnicalQuestionModule",
    ]
    assert all(
        surface["source_kind"] == "generated_topology_module" for surface in surfaces
    )
    assert all(
        surface["capability_ref"]["materializable"] is True for surface in surfaces
    )
    assert all(surface["effects"]["provider_called"] is False for surface in surfaces)
    assert all(surface["effects"]["tool_called"] is False for surface in surfaces)
    assert all(surface["effects"]["network"] is False for surface in surfaces)
    assert all(surface["effects"]["filesystem_read"] is False for surface in surfaces)
    assert all(surface["effects"]["filesystem_write"] is False for surface in surfaces)
    assert all(
        surface["effects"]["external_authority"] is False for surface in surfaces
    )
    assert all(
        surface["non_authority"]["external_mutation"] is False for surface in surfaces
    )
    assert all(
        surface["non_authority"]["oracle_ranking"] is False for surface in surfaces
    )

    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["topology_execution"]["status"] == "pipeline_materialized"
    assert manifest["program_promotion_review"]["promotion_state"] == "not_promoted"
    assert manifest["execution_episode"]["non_authority"]["oracle_ranking"] is False
    assert manifest["execution_episode"]["non_authority"]["external_mutation"] is False
    assert "module_surfaces" in manifest["candidate_assembly"]["surface_kinds"]
    surface_payload = json.dumps(surfaces).lower()
    assert "module_ref" not in surface_payload
    assert "custommodule" not in surface_payload
    assert (root / "behavior_results.json").exists()
    assert (root / "oracle_evidence.json").exists()
    assert (root / "eval_behavior.py").exists()
    assert (root / "behavior_episode.json").exists()
    assert subprocess_calls
    assert check_run_receipt(root / "manifest.json.meta.json")["status"] == "ok"


def test_module_surface_contract_drift_is_replay_checked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_local(tmp_path, monkeypatch)
    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="ReplayModuleSurfaceProgram",
            objective="Answer a short question.",
            inputs=["question"],
            outputs=["answer"],
        ),
        outdir=tmp_path / "program",
    )
    root = Path(artifact.root_path)
    assert check_run_receipt(root / "manifest.json.meta.json")["status"] == "ok"

    module_surfaces_path = root / "module_surfaces.json"
    payload = json.loads(module_surfaces_path.read_text(encoding="utf-8"))
    payload["status"] = "drifted"
    module_surfaces_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    drift = check_run_receipt(root / "manifest.json.meta.json")
    assert drift["status"] == "failed"
    assert drift["checks"]["output_hash_match"] is True
    assert drift["checks"]["program_module_surfaces_exists"] is True
    assert drift["checks"]["program_module_surfaces_hash_match"] is False
    assert "program_evidence_hash_mismatch" in drift["error_codes"]


def test_prompt_inferred_pipeline_capability_registry_matches_module_surfaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_local(tmp_path, monkeypatch)
    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="PromptInferredCapabilityProgram",
            objective="Route support tickets and draft a response.",
            inputs=["ticket_text"],
            outputs=["response"],
        ),
        outdir=tmp_path / "program",
    )
    root = Path(artifact.root_path)

    module_surfaces = json.loads(
        (root / "module_surfaces.json").read_text(encoding="utf-8")
    )
    registry = json.loads(
        (root / "program_capability_registry.json").read_text(encoding="utf-8")
    )
    surface_refs = {
        (surface["module_id"], surface["capability_ref"]["capability_id"])
        for surface in module_surfaces["module_surfaces"]
    }
    registry_refs = {
        (ref["module_id"], ref["capability_id"])
        for ref in registry["used_capability_refs"]
    }

    assert module_surfaces["module_surface_count"] == 2
    assert surface_refs == registry_refs
    assert ("classify_route", "dspy.primitive.Predict") in registry_refs
    assert ("produce_response", "dspy.primitive.ChainOfThought") in registry_refs
    assert check_run_receipt(root / "manifest.json.meta.json")["status"] == "ok"


def test_capability_registry_contract_drift_is_replay_checked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_local(tmp_path, monkeypatch)
    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="ReplayCapabilityRegistryProgram",
            objective="Answer a short question.",
            inputs=["question"],
            outputs=["answer"],
        ),
        outdir=tmp_path / "program",
    )
    root = Path(artifact.root_path)
    assert check_run_receipt(root / "manifest.json.meta.json")["status"] == "ok"

    registry_path = root / "program_capability_registry.json"
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    payload["status"] = "drifted"
    registry_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    drift = check_run_receipt(root / "manifest.json.meta.json")
    assert drift["status"] == "failed"
    assert drift["checks"]["output_hash_match"] is True
    assert drift["checks"]["program_capability_registry_exists"] is True
    assert drift["checks"]["program_capability_registry_hash_match"] is False
    assert "program_evidence_hash_mismatch" in drift["error_codes"]

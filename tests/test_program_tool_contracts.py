from __future__ import annotations

import json
from pathlib import Path

import pytest

from dspx.services.program_generated_policy import build_program_generated_module_policy
from dspx.services.program_service import ProgramIntent, materialize_program_from_intent
from dspx.services.program_promotion import promotion_policy
from dspx.services.program_tool_contracts import build_program_tool_contracts
from dspx.services.run_replay_service import check_run_receipt


MODULE_SURFACES = {
    "schema_version": "program-module-surfaces-v1",
    "module_surfaces": [
        {
            "module_id": "generated_module",
            "primitive": "Predict",
            "effects": {
                "provider_called": False,
                "tool_called": False,
                "custom_import_loaded": False,
                "network": False,
                "filesystem_read": False,
                "filesystem_write": False,
                "subprocess": False,
                "external_authority": False,
            },
        }
    ],
}


def _configure_local(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")


def _tool_intent() -> ProgramIntent:
    return ProgramIntent(
        name="ToolContractProgram",
        objective="Answer using an explicitly declared future pure lookup tool.",
        inputs=["question"],
        outputs=["answer"],
        capabilities={
            "declarations": [
                {
                    "id": "lookup_policy",
                    "kind": "tool",
                    "name": "lookup_policy",
                    "description": "Descriptor-only pure lookup contract.",
                    "inputs": ["question"],
                    "outputs": ["answer"],
                    "args_schema": {
                        "type": "object",
                        "properties": {"question": {"type": "string"}},
                        "required": ["question"],
                        "additionalProperties": False,
                    },
                    "return_schema": {
                        "type": "object",
                        "properties": {"answer": {"type": "string"}},
                        "required": ["answer"],
                        "additionalProperties": False,
                    },
                    "effect_class": "pure",
                    "allowlists": {"tool_ids": ["lookup_policy"]},
                    "timeout_policy": {
                        "timeout_seconds": 0.5,
                        "retry_policy": "none",
                    },
                    "redaction_policy": {
                        "redact_inputs": ["question"],
                        "redact_secrets": True,
                    },
                    "mutation_allowed": False,
                }
            ]
        },
    )


def test_tool_contract_builder_emits_descriptor_only_contract_fields() -> None:
    payload = build_program_tool_contracts(_tool_intent())
    contract = payload["contracts"][0]

    assert payload["schema_version"] == "program-tool-contracts-v1"
    assert payload["status"] == "descriptor_only_no_tool_binding"
    assert payload["tool_contract_count"] == 1
    assert payload["runtime_policy"] == {
        "dspy_tool_materialization_allowed": False,
        "tool_execution_allowed": False,
        "generated_adapters_allowed": False,
        "network_allowed": False,
        "filesystem_allowed": False,
        "subprocess_allowed": False,
        "mutation_allowed": False,
        "fail_closed_without_explicit_future_adapter": True,
    }
    assert contract["schema_version"] == "program-tool-contract-v1"
    assert contract["tool_id"] == "lookup_policy"
    assert contract["name"] == "lookup_policy"
    assert contract["args_schema"]["required"] == ["question"]
    assert contract["return_schema"]["required"] == ["answer"]
    assert contract["effect_class"] == "pure"
    assert contract["allowlists"]["tool_ids"] == ["lookup_policy"]
    assert contract["timeout_policy"]["timeout_seconds"] == 0.5
    assert contract["redaction_policy"]["redact_inputs"] == ["question"]
    assert contract["dry_run_mutation_posture"] == {
        "dry_run_required": True,
        "declared_mutation_allowed": False,
        "mutation_allowed_in_generated_program": False,
        "network_allowed_in_generated_program": False,
        "filesystem_allowed_in_generated_program": False,
        "subprocess_allowed_in_generated_program": False,
        "posture": "descriptor_only_no_runtime_effects",
    }
    assert contract["generated_adapter"] == {
        "exists": False,
        "content_hash": None,
        "provenance": None,
    }
    assert contract["non_authority"]["tool_execution_authority"] is False
    assert contract["non_authority"]["external_mutation"] is False


def test_tool_contract_builder_preserves_quoted_false_mutation_allowed() -> None:
    intent = ProgramIntent(
        name="ToolContractProgram",
        objective="Answer using an explicitly declared future pure lookup tool.",
        inputs=["question"],
        outputs=["answer"],
        capabilities={
            "declarations": [
                {
                    "id": "lookup_policy",
                    "kind": "tool",
                    "effect_class": "pure",
                    "mutation_allowed": "false",
                }
            ]
        },
    )

    contract = build_program_tool_contracts(intent)["contracts"][0]

    assert contract["dry_run_mutation_posture"]["declared_mutation_allowed"] is False


def test_promotion_policy_preserves_quoted_false_values() -> None:
    intent = ProgramIntent(
        name="PromotionPolicyProgram",
        objective="Answer locally.",
        inputs=["question"],
        outputs=["answer"],
        promotion={
            "policy": {
                "automatic_promotion": "false",
                "requires_behavioral_evaluation": "false",
                "requires_jury_execution": "false",
                "requires_adjudicator_decision": "false",
            }
        },
    )

    policy = promotion_policy(intent)

    assert policy == {
        "requires_behavioral_evaluation": False,
        "requires_jury_execution": False,
        "requires_adjudicator_decision": False,
        "automatic_promotion": False,
    }


def test_program_gen_writes_and_replay_checks_tool_contracts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_local(tmp_path, monkeypatch)
    artifact = materialize_program_from_intent(
        _tool_intent(),
        outdir=tmp_path / "program",
    )
    root = Path(artifact.root_path)
    contracts_path = root / "program_tool_contracts.json"
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    receipt = json.loads((root / "manifest.json.meta.json").read_text(encoding="utf-8"))
    contracts = json.loads(contracts_path.read_text(encoding="utf-8"))

    assert contracts["tool_contract_count"] == 1
    assert manifest["program_tool_contracts"] == contracts
    assert manifest["tool_contracts_artifact"]["path"] == "program_tool_contracts.json"
    assert manifest["receipt_bundle"]["evidence"]["tool_contracts_path"] == (
        "program_tool_contracts.json"
    )
    assert (
        manifest["receipt_bundle"]["evidence"]["surface_generation"]["tool_contracts"]
        == "program-gen"
    )
    assert receipt["program_tool_contracts"] == contracts
    assert receipt["run_summary"]["tool_contracts_path"] == (
        "program_tool_contracts.json"
    )

    replay = check_run_receipt(root / "manifest.json.meta.json")
    assert replay["status"] == "ok"
    assert replay["checks"]["program_tool_contracts_exists"] is True
    assert replay["checks"]["program_tool_contracts_hash_match"] is True
    assert replay["checks"]["program_tool_contracts_semantic_valid"] is True

    contracts["status"] = "drifted"
    contracts_path.write_text(
        json.dumps(contracts, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    drift = check_run_receipt(root / "manifest.json.meta.json")
    assert drift["status"] == "failed"
    assert drift["checks"]["program_tool_contracts_hash_match"] is False
    assert drift["checks"]["program_tool_contracts_semantic_valid"] is False
    assert "program_evidence_hash_mismatch" in drift["error_codes"]
    assert "program_evidence_declaration_mismatch" in drift["error_codes"]


def test_tool_contracts_do_not_enable_dspy_tool_materialization() -> None:
    policy = build_program_generated_module_policy(
        "import json\nimport dspy\nfrom signature import X\ndspy.Tool(lambda x: x)\n",
        module_surfaces=MODULE_SURFACES,
    )

    assert policy["status"] == "failed"
    assert any(item["code"] == "dspy_call_not_allowed" for item in policy["violations"])

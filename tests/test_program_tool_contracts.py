from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from dspx.cache import sha256_text
from dspx.services.program_generated_policy import build_program_generated_module_policy
from dspx.services.program_service import ProgramIntent, materialize_program_from_intent
from dspx.services.program_promotion import promotion_policy
from dspx.services.program_tool_contracts import build_program_tool_contracts
from dspx.services.run_replay_service import (
    _generated_tool_adapter_dry_run_valid,
    _generated_tool_adapter_source_semantic_valid,
    check_run_receipt,
)


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


def _stable_json_hash(payload: object) -> str:
    text = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
    assert payload["react_v2_tool_readiness"]["react_v2_requested"] is False
    assert (
        payload["react_v2_tool_readiness"]["ready_for_react_v2_tool_binding"] is False
    )
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
    assert contract["generated_adapter"]["exists"] is False
    assert contract["generated_adapter"]["content_hash"] is None
    assert contract["generated_adapter"]["provenance"] is None
    assert contract["generated_adapter"]["execution_allowed"] is False
    assert contract["generated_adapter"]["dspy_tool_binding_allowed"] is False
    assert contract["generated_adapter"]["imported_by_generated_program"] is False
    assert contract["generated_adapter"]["source_hash"] == sha256_text(
        contract["generated_adapter"]["source_preview"]
    )
    assert contract["generated_adapter_blueprint"]["schema_version"] == (
        "program-tool-adapter-blueprint-v1"
    )
    assert contract["generated_adapter_blueprint"]["status"] == (
        "blueprint_recorded_not_executable"
    )
    assert contract["generated_adapter_blueprint"]["tool_id"] == "lookup_policy"
    assert contract["generated_adapter_blueprint"]["execution_allowed"] is False
    assert contract["generated_adapter_blueprint"]["dspy_tool_binding_allowed"] is False
    assert contract["generated_adapter_blueprint"]["source_hash"] == sha256_text(
        contract["generated_adapter_blueprint"]["source_preview"]
    )
    assert contract["generated_adapter_policy"] == {
        "schema_version": "program-tool-generated-adapter-policy-v1",
        "status": "adapter_not_generated",
        "adapter_kind": "future_dspy_tool_adapter",
        "required_before_enablement": [
            "adapter source hash and provenance must be recorded",
            "tool input/output schemas must be enforced at adapter boundary",
            "timeout and redaction policy must be enforced before tool call",
            "effect class and allowlists must be checked before tool call",
            "runtime trace must record dry-run/tool-call posture without secrets",
            "receipt replay must verify adapter hash and trace consistency",
        ],
        "execution_allowed": False,
        "dspy_tool_binding_allowed": False,
    }
    assert payload["tool_adapter_policy"] == {
        "schema_version": "program-tool-adapter-policy-v1",
        "status": "adapter_blueprints_recorded_not_executable",
        "generated_adapter_count": 0,
        "adapter_blueprint_count": 1,
        "all_adapters_hash_bound": False,
        "all_adapters_replay_checked": False,
        "dspy_tool_binding_allowed": False,
        "tool_execution_allowed": False,
        "next_required_slice": "generate_hash_bound_dspy_tool_adapters_with_replay_visible_traces",
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


def test_replay_tool_adapter_dry_run_validation_is_structural_not_executing() -> None:
    contracts = build_program_tool_contracts(_tool_intent())
    contract = contracts["contracts"][0]
    source = contract["generated_adapter"]["source_preview"]
    source_with_top_level_effect = (
        source + "\nraise RuntimeError('top-level execution')\n"
    )
    expected_result = {
        "schema_version": "program-tool-adapter-dry-run-v1",
        "tool_id": "lookup_policy",
        "status": "validated_not_executed",
        "args_fields": ["question"],
        "return_fields": ["answer"],
        "return_validated": True,
        "effects": {
            "tool_called": False,
            "dspy_tool_bound": False,
            "network": False,
            "filesystem": False,
            "subprocess": False,
            "external_authority_mutated": False,
        },
    }

    assert (
        _generated_tool_adapter_dry_run_valid(
            source_with_top_level_effect,
            tool_id="lookup_policy",
            args_schema=contract["args_schema"],
            return_schema=contract["return_schema"],
            expected_result=expected_result,
        )
        is True
    )
    assert (
        _generated_tool_adapter_source_semantic_valid(
            source_with_top_level_effect,
            tool_id="lookup_policy",
            effect_class="pure",
            args_schema=contract["args_schema"],
            return_schema=contract["return_schema"],
        )
        is False
    )


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
    blueprint = contracts["contracts"][0]["generated_adapter_blueprint"]
    assert blueprint["artifact"] == {
        "path": "tool_adapters/lookup_policy_adapter_blueprint.py",
        "content_hash": blueprint["source_hash"],
        "executable": False,
        "imported_by_generated_program": False,
    }
    blueprint_path = root / blueprint["artifact"]["path"]
    assert blueprint_path.exists()
    assert blueprint_path.read_text(encoding="utf-8") == blueprint["source_preview"]
    generated_adapter = contracts["contracts"][0]["generated_adapter"]
    original_adapter_hash = str(generated_adapter["content_hash"])
    assert generated_adapter["exists"] is True
    expected_dry_run_effects = {
        "tool_called": False,
        "dspy_tool_bound": False,
        "network": False,
        "filesystem": False,
        "subprocess": False,
        "external_authority_mutated": False,
    }
    expected_dry_run_with_return = {
        "schema_version": "program-tool-adapter-dry-run-v1",
        "tool_id": "lookup_policy",
        "status": "validated_not_executed",
        "args_fields": ["question"],
        "return_fields": ["answer"],
        "return_validated": True,
        "effects": expected_dry_run_effects,
    }
    assert generated_adapter["validation"] == {
        "schema_version": "program-tool-generated-adapter-validation-v1",
        "status": "validated_not_bound_not_executed",
        "source_compiles": True,
        "constants_match_contract": True,
        "source_hash_matches_artifact": True,
        "dry_run_supported": True,
        "dry_run_expected_result": expected_dry_run_with_return,
        "execution_allowed": False,
        "dspy_tool_binding_allowed": False,
        "imported_by_generated_program": False,
    }
    namespace: dict[str, object] = {}
    exec(
        compile(
            generated_adapter["source_preview"], "lookup_policy_adapter.py", "exec"
        ),
        namespace,
    )
    assert namespace["validate_args"]({"question": "q"}) == {"question": "q"}
    assert namespace["validate_return"]({"answer": "a"}) == {"answer": "a"}
    assert namespace["adapter_dry_run"]({"question": "q"}) == {
        "schema_version": "program-tool-adapter-dry-run-v1",
        "tool_id": "lookup_policy",
        "status": "validated_not_executed",
        "args_fields": ["question"],
        "return_fields": [],
        "return_validated": False,
        "effects": expected_dry_run_effects,
    }
    assert (
        namespace["adapter_dry_run"]({"question": "q"}, expected_return={"answer": "a"})
        == expected_dry_run_with_return
    )
    with pytest.raises(RuntimeError, match="not execution-enabled"):
        namespace["adapter"]({"question": "q"})
    with pytest.raises(ValueError, match="unexpected tool args fields"):
        namespace["validate_args"]({"question": "q", "extra": "nope"})
    with pytest.raises(TypeError, match="does not match schema type"):
        namespace["validate_return"]({"answer": 3})
    assert generated_adapter["artifact"] == {
        "path": "tool_adapters/lookup_policy_adapter.py",
        "content_hash": generated_adapter["source_hash"],
        "executable": False,
        "imported_by_generated_program": False,
    }
    adapter_path = root / generated_adapter["artifact"]["path"]
    assert adapter_path.exists()
    assert (
        adapter_path.read_text(encoding="utf-8") == generated_adapter["source_preview"]
    )
    assert "EXECUTION_ALLOWED = False" in generated_adapter["source_preview"]
    assert contracts["tool_adapter_policy"]["status"] == (
        "adapter_source_artifacts_written_not_bound"
    )
    assert contracts["tool_adapter_policy"]["adapter_blueprint_artifact_count"] == 1
    assert contracts["tool_adapter_policy"]["generated_adapter_count"] == 1
    assert contracts["tool_adapter_policy"]["all_adapters_hash_bound"] is True
    assert contracts["contracts"][0]["generated_adapter_policy"]["status"] == (
        "adapter_source_materialized_not_bound"
    )
    assert (
        contracts["contracts"][0]["generated_adapter_policy"]["source_hash_bound"]
        is True
    )
    assert (
        contracts["contracts"][0]["generated_adapter_policy"]["artifact_hash_bound"]
        is True
    )
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
    assert replay["checks"]["program_tool_adapter_blueprints_valid"] is True
    assert replay["checks"]["program_tool_adapter_artifacts_valid"] is True

    contracts["contracts"][0]["generated_adapter"]["artifact"] = {}
    contracts_path.write_text(
        json.dumps(contracts, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    missing_adapter_artifact = check_run_receipt(root / "manifest.json.meta.json")
    assert missing_adapter_artifact["status"] == "failed"
    assert (
        missing_adapter_artifact["checks"]["program_tool_adapter_artifacts_valid"]
        is False
    )
    assert (
        "program_evidence_declaration_mismatch"
        in missing_adapter_artifact["error_codes"]
    )
    contracts["contracts"][0]["generated_adapter"]["artifact"] = {
        "path": "tool_adapters/lookup_policy_adapter.py",
        "content_hash": generated_adapter["source_hash"],
        "executable": False,
        "imported_by_generated_program": False,
    }
    contracts_path.write_text(
        json.dumps(contracts, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    adapter_path.write_text("# drifted\n", encoding="utf-8")
    adapter_drift = check_run_receipt(root / "manifest.json.meta.json")
    assert adapter_drift["status"] == "failed"
    assert adapter_drift["checks"]["program_tool_contracts_hash_match"] is True
    assert adapter_drift["checks"]["program_tool_adapter_artifacts_valid"] is False
    assert "program_evidence_declaration_mismatch" in adapter_drift["error_codes"]
    adapter_path.write_text(generated_adapter["source_preview"], encoding="utf-8")

    broken_dry_run_source = generated_adapter["source_preview"].replace(
        "'status': 'validated_not_executed'", "'status': 'executed'"
    )
    broken_dry_run_hash = sha256_text(broken_dry_run_source)
    adapter_path.write_text(broken_dry_run_source, encoding="utf-8")
    contracts["contracts"][0]["generated_adapter"]["content_hash"] = broken_dry_run_hash
    contracts["contracts"][0]["generated_adapter"]["artifact"]["content_hash"] = (
        broken_dry_run_hash
    )
    contracts_path.write_text(
        json.dumps(contracts, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    broken_dry_run = check_run_receipt(root / "manifest.json.meta.json")
    assert broken_dry_run["status"] == "failed"
    assert broken_dry_run["checks"]["program_tool_adapter_artifacts_valid"] is False
    assert "program_evidence_declaration_mismatch" in broken_dry_run["error_codes"]
    adapter_path.write_text(generated_adapter["source_preview"], encoding="utf-8")
    contracts["contracts"][0]["generated_adapter"]["content_hash"] = (
        original_adapter_hash
    )
    contracts["contracts"][0]["generated_adapter"]["artifact"]["content_hash"] = (
        original_adapter_hash
    )
    contracts_path.write_text(
        json.dumps(contracts, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    unsafe_source = generated_adapter["source_preview"].replace(
        "EXECUTION_ALLOWED = False", "EXECUTION_ALLOWED = True"
    )
    unsafe_hash = sha256_text(unsafe_source)
    adapter_path.write_text(unsafe_source, encoding="utf-8")
    contracts["contracts"][0]["generated_adapter"]["content_hash"] = unsafe_hash
    contracts["contracts"][0]["generated_adapter"]["artifact"]["content_hash"] = (
        unsafe_hash
    )
    contracts_path.write_text(
        json.dumps(contracts, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    unsafe_adapter = check_run_receipt(root / "manifest.json.meta.json")
    assert unsafe_adapter["status"] == "failed"
    assert unsafe_adapter["checks"]["program_tool_contracts_hash_match"] is False
    assert unsafe_adapter["checks"]["program_tool_adapter_artifacts_valid"] is False
    assert "program_evidence_declaration_mismatch" in unsafe_adapter["error_codes"]
    adapter_path.write_text(generated_adapter["source_preview"], encoding="utf-8")
    contracts["contracts"][0]["generated_adapter"]["content_hash"] = (
        original_adapter_hash
    )
    contracts["contracts"][0]["generated_adapter"]["artifact"]["content_hash"] = (
        original_adapter_hash
    )
    contracts_path.write_text(
        json.dumps(contracts, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    mismatched_source = generated_adapter["source_preview"].replace(
        "TOOL_ID = 'lookup_policy'", "TOOL_ID = 'other_tool'"
    )
    mismatched_hash = sha256_text(mismatched_source)
    adapter_path.write_text(mismatched_source, encoding="utf-8")
    contracts["contracts"][0]["generated_adapter"]["content_hash"] = mismatched_hash
    contracts["contracts"][0]["generated_adapter"]["artifact"]["content_hash"] = (
        mismatched_hash
    )
    contracts_path.write_text(
        json.dumps(contracts, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    mismatched_adapter = check_run_receipt(root / "manifest.json.meta.json")
    assert mismatched_adapter["status"] == "failed"
    assert mismatched_adapter["checks"]["program_tool_adapter_artifacts_valid"] is False
    assert "program_evidence_declaration_mismatch" in mismatched_adapter["error_codes"]
    adapter_path.write_text(generated_adapter["source_preview"], encoding="utf-8")
    contracts["contracts"][0]["generated_adapter"]["validation"][
        "constants_match_contract"
    ] = False
    contracts_path.write_text(
        json.dumps(contracts, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    validation_drift = check_run_receipt(root / "manifest.json.meta.json")
    assert validation_drift["status"] == "failed"
    assert validation_drift["checks"]["program_tool_adapter_artifacts_valid"] is False
    assert "program_evidence_declaration_mismatch" in validation_drift["error_codes"]
    contracts["contracts"][0]["generated_adapter"]["validation"][
        "constants_match_contract"
    ] = True
    contracts["contracts"][0]["generated_adapter"]["validation"][
        "dry_run_expected_result"
    ]["status"] = "executed"
    contracts_path.write_text(
        json.dumps(contracts, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    dry_run_record_drift = check_run_receipt(root / "manifest.json.meta.json")
    assert dry_run_record_drift["status"] == "failed"
    assert (
        dry_run_record_drift["checks"]["program_tool_adapter_artifacts_valid"] is False
    )
    assert (
        "program_evidence_declaration_mismatch" in dry_run_record_drift["error_codes"]
    )
    contracts["contracts"][0]["generated_adapter"]["validation"][
        "dry_run_expected_result"
    ]["status"] = "validated_not_executed"
    contracts["contracts"][0]["generated_adapter_policy"]["source_hash_bound"] = False
    contracts_path.write_text(
        json.dumps(contracts, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    policy_drift = check_run_receipt(root / "manifest.json.meta.json")
    assert policy_drift["status"] == "failed"
    assert policy_drift["checks"]["program_tool_adapter_artifacts_valid"] is False
    assert "program_evidence_declaration_mismatch" in policy_drift["error_codes"]
    contracts["contracts"][0]["generated_adapter_policy"]["source_hash_bound"] = True

    contracts["contracts"][0]["generated_adapter_policy"]["adapter_kind"] = (
        "live_adapter"
    )
    contracts_path.write_text(
        json.dumps(contracts, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    adapter_kind_drift = check_run_receipt(root / "manifest.json.meta.json")
    assert adapter_kind_drift["status"] == "failed"
    assert adapter_kind_drift["checks"]["program_tool_adapter_artifacts_valid"] is False
    contracts["contracts"][0]["generated_adapter_policy"]["adapter_kind"] = (
        "future_dspy_tool_adapter"
    )

    required_policy = contracts["contracts"][0]["generated_adapter_policy"][
        "required_before_enablement"
    ]
    contracts["contracts"][0]["generated_adapter_policy"][
        "required_before_enablement"
    ] = [
        item
        for item in required_policy
        if item != "timeout and redaction policy must be enforced before tool call"
    ]
    contracts_path.write_text(
        json.dumps(contracts, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    required_policy_drift = check_run_receipt(root / "manifest.json.meta.json")
    assert required_policy_drift["status"] == "failed"
    assert (
        required_policy_drift["checks"]["program_tool_adapter_artifacts_valid"] is False
    )
    contracts["contracts"][0]["generated_adapter_policy"][
        "required_before_enablement"
    ] = required_policy

    contracts["contracts"][0]["generated_adapter"]["provenance"]["status"] = (
        "materialized_and_bound"
    )
    contracts_path.write_text(
        json.dumps(contracts, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    provenance_drift = check_run_receipt(root / "manifest.json.meta.json")
    assert provenance_drift["status"] == "failed"
    assert provenance_drift["checks"]["program_tool_adapter_artifacts_valid"] is False
    contracts["contracts"][0]["generated_adapter"]["provenance"]["status"] = (
        "materialized_not_bound_not_executed"
    )

    contracts["contracts"][0]["generated_adapter"]["content_hash"] = (
        original_adapter_hash
    )
    contracts["contracts"][0]["generated_adapter"]["artifact"]["content_hash"] = (
        original_adapter_hash
    )
    contracts_path.write_text(
        json.dumps(contracts, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    contracts["contracts"][0]["generated_adapter"]["source_preview"] += (
        "\n# preview drift"
    )
    contracts_path.write_text(
        json.dumps(contracts, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    adapter_preview_drift = check_run_receipt(root / "manifest.json.meta.json")
    assert adapter_preview_drift["status"] == "failed"
    assert (
        adapter_preview_drift["checks"]["program_tool_adapter_artifacts_valid"] is False
    )
    assert (
        "program_evidence_declaration_mismatch" in adapter_preview_drift["error_codes"]
    )
    contracts["contracts"][0]["generated_adapter"]["source_preview"] = (
        generated_adapter["source_preview"]
    )

    forbidden_call_source = generated_adapter["source_preview"].replace(
        "    validated = validate_args(payload)",
        "    globals()\n    validated = validate_args(payload)",
    )
    forbidden_call_hash = sha256_text(forbidden_call_source)
    adapter_path.write_text(forbidden_call_source, encoding="utf-8")
    contracts["contracts"][0]["generated_adapter"]["source_preview"] = (
        forbidden_call_source
    )
    contracts["contracts"][0]["generated_adapter"]["source_hash"] = forbidden_call_hash
    contracts["contracts"][0]["generated_adapter"]["content_hash"] = forbidden_call_hash
    contracts["contracts"][0]["generated_adapter"]["artifact"]["content_hash"] = (
        forbidden_call_hash
    )
    contracts_path.write_text(
        json.dumps(contracts, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    forbidden_call_drift = check_run_receipt(root / "manifest.json.meta.json")
    assert forbidden_call_drift["status"] == "failed"
    assert (
        forbidden_call_drift["checks"]["program_tool_adapter_artifacts_valid"] is False
    )
    adapter_path.write_text(generated_adapter["source_preview"], encoding="utf-8")
    contracts["contracts"][0]["generated_adapter"]["source_preview"] = (
        generated_adapter["source_preview"]
    )
    contracts["contracts"][0]["generated_adapter"]["source_hash"] = (
        original_adapter_hash
    )
    contracts["contracts"][0]["generated_adapter"]["content_hash"] = (
        original_adapter_hash
    )
    contracts["contracts"][0]["generated_adapter"]["artifact"]["content_hash"] = (
        original_adapter_hash
    )

    contracts["tool_adapter_policy"]["status"] = "execution_ready"
    contracts_path.write_text(
        json.dumps(contracts, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    top_policy_status_drift = check_run_receipt(root / "manifest.json.meta.json")
    assert top_policy_status_drift["status"] == "failed"
    assert (
        top_policy_status_drift["checks"]["program_tool_contracts_semantic_valid"]
        is False
    )
    contracts["tool_adapter_policy"]["status"] = (
        "adapter_source_artifacts_written_not_bound"
    )

    contracts["tool_adapter_policy"]["generated_adapter_count"] = 2
    contracts_path.write_text(
        json.dumps(contracts, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    adapter_count_drift = check_run_receipt(root / "manifest.json.meta.json")
    assert adapter_count_drift["status"] == "failed"
    assert (
        adapter_count_drift["checks"]["program_tool_adapter_artifacts_valid"] is False
    )
    contracts["tool_adapter_policy"]["generated_adapter_count"] = 1

    contracts["tool_adapter_policy"]["adapter_blueprint_artifact_count"] = 2
    contracts_path.write_text(
        json.dumps(contracts, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    blueprint_count_drift = check_run_receipt(root / "manifest.json.meta.json")
    assert blueprint_count_drift["status"] == "failed"
    assert (
        blueprint_count_drift["checks"]["program_tool_adapter_blueprints_valid"]
        is False
    )
    contracts["tool_adapter_policy"]["adapter_blueprint_artifact_count"] = 1
    contracts_path.write_text(
        json.dumps(contracts, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    adapter_copy_path = root / "tool_adapters" / "lookup_policy_adapter_copy.py"
    adapter_copy_path.write_text(generated_adapter["source_preview"], encoding="utf-8")
    contracts["contracts"][0]["generated_adapter"]["artifact"]["path"] = (
        "tool_adapters/lookup_policy_adapter_copy.py"
    )
    contracts_path.write_text(
        json.dumps(contracts, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    adapter_path_drift = check_run_receipt(root / "manifest.json.meta.json")
    assert adapter_path_drift["status"] == "failed"
    assert adapter_path_drift["checks"]["program_tool_adapter_artifacts_valid"] is False
    contracts["contracts"][0]["generated_adapter"]["artifact"]["path"] = (
        "tool_adapters/lookup_policy_adapter.py"
    )

    blueprint_copy_path = root / "tool_adapters" / "lookup_policy_blueprint_copy.py"
    blueprint_copy_path.write_text(blueprint["source_preview"], encoding="utf-8")
    contracts["contracts"][0]["generated_adapter_blueprint"]["artifact"]["path"] = (
        "tool_adapters/lookup_policy_blueprint_copy.py"
    )
    contracts_path.write_text(
        json.dumps(contracts, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    blueprint_path_drift = check_run_receipt(root / "manifest.json.meta.json")
    assert blueprint_path_drift["status"] == "failed"
    assert (
        blueprint_path_drift["checks"]["program_tool_adapter_blueprints_valid"] is False
    )
    contracts["contracts"][0]["generated_adapter_blueprint"]["artifact"]["path"] = (
        "tool_adapters/lookup_policy_adapter_blueprint.py"
    )
    contracts_path.write_text(
        json.dumps(contracts, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    blueprint_path.write_text("# drifted\n", encoding="utf-8")
    blueprint_drift = check_run_receipt(root / "manifest.json.meta.json")
    assert blueprint_drift["status"] == "failed"
    assert blueprint_drift["checks"]["program_tool_adapter_blueprints_valid"] is False
    assert "program_evidence_declaration_mismatch" in blueprint_drift["error_codes"]
    blueprint_path.write_text(blueprint["source_preview"], encoding="utf-8")

    contracts["tool_adapter_policy"]["dspy_tool_binding_allowed"] = True
    contracts_path.write_text(
        json.dumps(contracts, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    adapter_drift = check_run_receipt(root / "manifest.json.meta.json")
    assert adapter_drift["status"] == "failed"
    assert adapter_drift["checks"]["program_tool_contracts_hash_match"] is False
    assert adapter_drift["checks"]["program_tool_contracts_semantic_valid"] is False
    assert "program_evidence_hash_mismatch" in adapter_drift["error_codes"]
    assert "program_evidence_declaration_mismatch" in adapter_drift["error_codes"]

    contracts["tool_adapter_policy"]["dspy_tool_binding_allowed"] = False
    contracts["react_v2_tool_readiness"]["ready_for_react_v2_tool_binding"] = True
    contracts_path.write_text(
        json.dumps(contracts, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    readiness_drift = check_run_receipt(root / "manifest.json.meta.json")
    assert readiness_drift["status"] == "failed"
    assert readiness_drift["checks"]["program_tool_contracts_semantic_valid"] is False
    assert "program_evidence_declaration_mismatch" in readiness_drift["error_codes"]

    contracts["react_v2_tool_readiness"]["ready_for_react_v2_tool_binding"] = False
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


def test_generated_tool_adapter_validates_nested_bounded_schema_and_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_local(tmp_path, monkeypatch)
    intent = _tool_intent()
    intent.capabilities["declarations"][0]["args_schema"] = {
        "type": "object",
        "properties": {
            "question": {"type": "string", "enum": ["q"]},
            "filters": {
                "type": "object",
                "properties": {"scope": {"type": "string", "const": "policy"}},
                "required": ["scope"],
                "additionalProperties": False,
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 3,
            },
        },
        "required": ["question", "filters", "tags"],
        "additionalProperties": False,
    }
    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    root = Path(artifact.root_path)
    contracts = json.loads(
        (root / "program_tool_contracts.json").read_text(encoding="utf-8")
    )
    source = contracts["contracts"][0]["generated_adapter"]["source_preview"]
    namespace: dict[str, object] = {}
    exec(compile(source, "lookup_policy_adapter.py", "exec"), namespace)

    valid_payload = {
        "question": "q",
        "filters": {"scope": "policy"},
        "tags": ["safe"],
    }
    assert namespace["validate_args"](valid_payload) == valid_payload
    with pytest.raises(ValueError, match="schema enum"):
        namespace["validate_args"]({**valid_payload, "question": "other"})
    with pytest.raises(ValueError, match="schema const"):
        namespace["validate_args"]({**valid_payload, "filters": {"scope": "other"}})
    with pytest.raises(TypeError, match="schema type"):
        namespace["validate_args"]({**valid_payload, "tags": [3]})
    with pytest.raises(ValueError, match="fewer items"):
        namespace["validate_args"]({**valid_payload, "tags": []})
    with pytest.raises(ValueError, match="more items"):
        namespace["validate_args"]({**valid_payload, "tags": ["a", "b", "c", "d"]})

    replay = check_run_receipt(root / "manifest.json.meta.json")

    assert replay["status"] == "ok"
    assert replay["checks"]["program_tool_adapter_artifacts_valid"] is True


def test_replay_cross_checks_runtime_trace_tool_intents_against_contracts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_local(tmp_path, monkeypatch)
    intent = _tool_intent()
    intent.examples = [
        {"inputs": {"question": "hello"}, "outputs": {"answer": "hello"}}
    ]
    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    root = Path(artifact.root_path)
    traces_path = root / "program_runtime_traces.json"
    surfaces_path = root / "module_surfaces.json"
    contracts_path = root / "program_tool_contracts.json"
    traces = json.loads(traces_path.read_text(encoding="utf-8"))
    surfaces = json.loads(surfaces_path.read_text(encoding="utf-8"))
    contracts = json.loads(contracts_path.read_text(encoding="utf-8"))

    replay = check_run_receipt(root / "manifest.json.meta.json")
    assert replay["status"] == "ok"
    assert (
        replay["checks"]["program_runtime_trace_tool_intents_match_contracts"] is True
    )

    surfaces["module_surfaces"][0]["primitive"] = "ReActV2"
    surfaces["module_surfaces"][0]["react"] = {
        "declared_tool_refs": ["lookup_policy"],
        "tool_binding_status": "declared_refs_only_not_bound",
        "tool_binding_allowed": False,
    }
    surfaces_path.write_text(json.dumps(surfaces, indent=2, sort_keys=True) + "\n")
    contracts["react_v2_tool_readiness"].update(
        {
            "react_v2_requested": True,
            "react_v2_module_count": 1,
            "react_v2_module_tool_refs": ["lookup_policy"],
            "missing_tool_contracts": [],
            "status": "blocked_until_generated_tool_adapter_policy",
        }
    )
    contracts["react_v2_tool_readiness"]["pure_tool_adapter_preflight"].update(
        {
            "referenced_tool_ids": ["lookup_policy"],
            "all_referenced_tools_have_pure_contracts": True,
            "all_referenced_tool_schemas_bounded": True,
            "all_referenced_adapter_blueprints_hash_bound": True,
            "all_referenced_tools_have_replay_policy_preconditions": True,
            "ready_for_tool_adapter_materialization": True,
            "materialization_status": "ready_for_generated_adapter_materialization",
        }
    )
    contracts_path.write_text(json.dumps(contracts, indent=2, sort_keys=True) + "\n")

    slots = traces["module_calls"][0]["trajectory_slots"]
    slots["tool_refs"] = {
        "declared_tool_refs": ["lookup_policy"],
        "tool_binding_status": "declared_refs_only_not_bound",
        "tool_binding_allowed": False,
        "executable_tools": [],
    }
    slots["tool_call_intents"] = [
        {
            "schema_version": "program-runtime-tool-call-intent-v1",
            "tool_id": "lookup_policy",
            "status": "declared_intent_shape_not_executed",
            "adapter_dry_run_required": True,
            "tool_call_executed": False,
            "dspy_tool_bound": False,
            "result_recorded": False,
            "effects": {
                "tool_called": False,
                "network": False,
                "filesystem": False,
                "subprocess": False,
                "external_authority_mutated": False,
            },
        }
    ]
    call_without_hash = {
        key: value
        for key, value in traces["module_calls"][0].items()
        if key != "trace_hash"
    }
    traces["module_calls"][0]["trace_hash"] = _stable_json_hash(call_without_hash)
    traces["trace_hashes"]["module_calls"] = [traces["module_calls"][0]["trace_hash"]]
    traces_path.write_text(json.dumps(traces, indent=2, sort_keys=True) + "\n")

    valid_intent_shape = check_run_receipt(root / "manifest.json.meta.json")
    assert valid_intent_shape["status"] == "failed"
    assert valid_intent_shape["checks"]["program_runtime_traces_semantic_valid"] is True
    assert (
        valid_intent_shape["checks"][
            "program_runtime_trace_tool_intents_match_contracts"
        ]
        is True
    )
    assert (
        valid_intent_shape["checks"]["program_react_v2_tool_readiness_matches_surfaces"]
        is True
    )

    surfaces["module_surfaces"][0]["react"]["declared_tool_refs"] = []
    surfaces_path.write_text(json.dumps(surfaces, indent=2, sort_keys=True) + "\n")
    surface_mismatch = check_run_receipt(root / "manifest.json.meta.json")
    assert (
        surface_mismatch["checks"]["program_runtime_trace_tool_intents_match_contracts"]
        is False
    )
    assert (
        surface_mismatch["checks"]["program_react_v2_tool_readiness_matches_surfaces"]
        is False
    )
    surfaces["module_surfaces"][0]["react"]["declared_tool_refs"] = ["lookup_policy"]
    surfaces_path.write_text(json.dumps(surfaces, indent=2, sort_keys=True) + "\n")

    traces["module_calls"][0]["trajectory_slots"]["tool_call_intents"][0]["tool_id"] = (
        "missing_policy"
    )
    call_without_hash = {
        key: value
        for key, value in traces["module_calls"][0].items()
        if key != "trace_hash"
    }
    traces["module_calls"][0]["trace_hash"] = _stable_json_hash(call_without_hash)
    traces["trace_hashes"]["module_calls"] = [traces["module_calls"][0]["trace_hash"]]
    traces_path.write_text(json.dumps(traces, indent=2, sort_keys=True) + "\n")

    drift = check_run_receipt(root / "manifest.json.meta.json")

    assert drift["status"] == "failed"
    assert drift["checks"]["program_runtime_traces_semantic_valid"] is True
    assert (
        drift["checks"]["program_runtime_trace_tool_intents_match_contracts"] is False
    )
    assert "program_evidence_declaration_mismatch" in drift["error_codes"]


def test_replay_rejects_missing_tool_adapter_blueprint_artifact(
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
    contracts = json.loads(contracts_path.read_text(encoding="utf-8"))
    contracts["contracts"][0]["generated_adapter_blueprint"].pop("artifact")
    contracts_path.write_text(
        json.dumps(contracts, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    replay = check_run_receipt(root / "manifest.json.meta.json")

    assert replay["status"] == "failed"
    assert replay["checks"]["program_tool_adapter_blueprints_valid"] is False
    assert "program_evidence_declaration_mismatch" in replay["error_codes"]


def test_react_v2_tool_readiness_blocks_unbounded_tool_schema() -> None:
    intent = ProgramIntent(
        name="ReactV2UnboundedToolProgram",
        objective="Use ReActV2 with a declared lookup tool.",
        inputs=["question"],
        outputs=["answer"],
        topology={
            "kind": "pipeline",
            "execution_status": "declared_not_materialized",
            "modules": [
                {
                    "id": "agent",
                    "primitive": "ReActV2",
                    "signature": {
                        "name": "ReactV2Agent",
                        "inputs": ["question"],
                        "outputs": ["answer"],
                    },
                    "tools": [],
                    "tool_refs": ["lookup_policy"],
                }
            ],
            "edges": [
                {"from": "input", "to": "agent"},
                {"from": "agent", "to": "output"},
            ],
        },
        capabilities={
            "declarations": [
                {
                    "id": "lookup_policy",
                    "kind": "tool",
                    "effect_class": "pure",
                    "args_schema": {
                        "type": "object",
                        "properties": {"question": {}},
                        "required": ["question"],
                        "additionalProperties": False,
                    },
                    "return_schema": {
                        "type": "object",
                        "properties": {"answer": {"type": "string"}},
                        "required": ["answer"],
                        "additionalProperties": False,
                    },
                }
            ]
        },
    )

    readiness = build_program_tool_contracts(intent)["react_v2_tool_readiness"]

    assert (
        readiness["pure_tool_adapter_preflight"]["all_referenced_tool_schemas_bounded"]
        is False
    )
    assert any(
        "missing bounded args/return schemas" in item
        for item in readiness["production_readiness_blockers"]
    )


def test_react_v2_tool_readiness_blocks_until_adapter_policy_exists() -> None:
    intent = ProgramIntent(
        name="ReactV2ToolProgram",
        objective="Use ReActV2 with a declared lookup tool.",
        inputs=["question"],
        outputs=["answer"],
        options={"enable_react_v2_materialization": True},
        topology={
            "kind": "pipeline",
            "execution_status": "declared_not_materialized",
            "modules": [
                {
                    "id": "agent",
                    "primitive": "react_v2",
                    "signature": {
                        "name": "ReactV2Agent",
                        "inputs": ["question"],
                        "outputs": ["answer"],
                    },
                    "tools": [],
                    "tool_refs": ["lookup_policy"],
                }
            ],
            "edges": [
                {"from": "input", "to": "agent"},
                {"from": "agent", "to": "output"},
            ],
        },
        capabilities={
            "declarations": [
                {
                    "id": "lookup_policy",
                    "kind": "tool",
                    "effect_class": "pure",
                    "inputs": ["question"],
                    "outputs": ["answer"],
                }
            ]
        },
    )

    readiness = build_program_tool_contracts(intent)["react_v2_tool_readiness"]

    assert readiness["react_v2_requested"] is True
    assert readiness["declared_tool_ids"] == ["lookup_policy"]
    assert readiness["react_v2_module_tool_refs"] == ["lookup_policy"]
    assert readiness["missing_tool_contracts"] == []
    preflight = readiness["pure_tool_adapter_preflight"]
    assert preflight["referenced_tool_ids"] == ["lookup_policy"]
    assert preflight["all_referenced_tools_have_pure_contracts"] is True
    assert preflight["all_referenced_tool_schemas_bounded"] is True
    assert preflight["all_referenced_adapter_blueprints_hash_bound"] is True
    assert preflight["all_referenced_tools_have_replay_policy_preconditions"] is True
    assert preflight["ready_for_tool_adapter_materialization"] is True
    assert preflight["materialization_status"] == (
        "ready_for_generated_adapter_materialization"
    )
    assert readiness["ready_for_react_v2_no_tool_materialization"] is False
    assert readiness["ready_for_react_v2_tool_binding"] is False
    assert readiness["status"] == "blocked_until_generated_tool_adapter_policy"
    assert (
        "program_generated_policy still forbids dspy.Tool materialization"
        in readiness["production_readiness_blockers"]
    )
    assert readiness["effect"]["tool_called"] is False


def test_tool_contracts_do_not_enable_dspy_tool_materialization() -> None:
    policy = build_program_generated_module_policy(
        "import json\nimport dspy\nfrom signature import X\ndspy.Tool(lambda x: x)\n",
        module_surfaces=MODULE_SURFACES,
    )

    assert policy["status"] == "failed"
    assert any(item["code"] == "dspy_call_not_allowed" for item in policy["violations"])

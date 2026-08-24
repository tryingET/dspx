from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
VOICE_ROOT = REPO_ROOT / "examples" / "voice_turn_brains"
CANARY_ROOT = VOICE_ROOT / "canaries" / "dspy-3.3.0"
MODES = ("elaborate", "researched", "deep-research", "socratic", "bloom")


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_artifact(entry: dict[str, Any]) -> Path:
    path = REPO_ROOT / str(entry["path"])
    assert path.is_file()
    assert path.stat().st_size == entry["size"]
    assert _sha256(path) == entry["sha256"]
    return path


def _identity(manifest: dict[str, Any]) -> dict[str, str]:
    assembly = manifest["candidate_assembly"]
    episode = manifest["execution_episode"]
    receipt = manifest["receipt_bundle"]
    return {
        "request_id": assembly["request_id"],
        "assembly_id": assembly["assembly_id"],
        "candidate_id": assembly["candidate_id"],
        "episode_id": episode["episode_id"],
        "receipt_bundle_id": receipt["receipt_bundle_id"],
    }


def test_remaining_originals_index_binds_five_fresh_candidates() -> None:
    aggregate = _load(CANARY_ROOT / "remaining-originals-index.json")
    assert aggregate["schema_version"] == (
        "voice-turn-dspy-3.3-remaining-originals-index-v1"
    )
    assert aggregate["task_id"] == 4794
    assert aggregate["mode_count"] == 5
    assert [item["mode"] for item in aggregate["modes"]] == list(MODES)
    assert aggregate["provider"] == "stub/echo"
    assert aggregate["typed_contract"] == "typed_lm"
    assert aggregate["historical_artifacts_mutated"] is False
    assert aggregate["routing_mutated"] is False
    assert aggregate["optimized_or_gepa_in_scope"] is False
    assert aggregate["semantic_equivalence"] == "not_evaluated"
    assert aggregate["quality"] == "not_evaluated"
    assert aggregate["promotion"] is False
    assert aggregate["activation"] is False
    assert aggregate["network_used"] is False
    assert aggregate["credentials_used"] is False
    assert aggregate["live_model_used"] is False
    assert aggregate["runtime_identity_binding"] == (
        "hash_bound_local_environment_observation_not_external_attestation"
    )

    for item in aggregate["modes"]:
        index_path = _assert_artifact(item["index"])
        index = _load(index_path)
        assert index["mode"] == item["mode"]
        assert (
            index["historical_lineage"]["identity"]["candidate_id"]
            == item["historical_candidate_id"]
        )
        assert (
            index["fresh_candidate"]["identity"]["candidate_id"]
            == item["fresh_candidate_id"]
        )
        assert item["historical_candidate_id"] != item["fresh_candidate_id"]
        assert (
            item["shared_request_id"]
            == index["fresh_candidate"]["identity"]["request_id"]
        )
        assert (
            item["fresh_identity_fields"]
            == index["fresh_candidate"]["identity_freshness"]["fresh_fields"]
        )
        assert (
            item["historical_manifest_sha256"]
            == index["historical_lineage"]["manifest"]["sha256"]
        )
        assert (
            item["fresh_manifest_sha256"]
            == index["fresh_candidate"]["manifest"]["sha256"]
        )
        assert item["receipt_integrity"] is True
        assert item["runtime_replay"] is True
        assert item["runtime_dspy"] == "3.3.0"
        assert item["runtime_identity_binding_kind"] == (
            "hash_bound_local_post_execution_environment_observation"
        )
        assert _assert_artifact(item["runtime_environment_binding"]) == (
            CANARY_ROOT / item["mode"] / "runtime-environment-binding.json"
        )
        assert item["runtime_execution_status"] == "executed"
        assert item["semantic_equivalence"] == "not_evaluated"
        assert item["quality"] == "not_evaluated"


def test_remaining_candidates_have_dspy_33_receipt_bound_surface_closure() -> None:
    for mode in MODES:
        base = CANARY_ROOT / mode
        index = _load(base / "canary-index.json")
        source_root = VOICE_ROOT / "candidates" / mode / "original"
        candidate_root = base / "candidate"
        source_manifest = _load(source_root / "manifest.json")
        candidate_manifest = _load(candidate_root / "manifest.json")
        source_outcomes = _load(source_root / "program_runtime_outcomes.json")
        candidate_outcomes = _load(candidate_root / "program_runtime_outcomes.json")
        behavior = _load(candidate_root / "behavior_results.json")

        assert index["schema_version"] == "voice-turn-dspy-3.3-migration-canary-v1"
        assert index["task_id"] == 4794
        assert index["posture"] == "non_destructive_offline_compatibility_canary"
        assert index["historical_lineage"]["generation_dspy"]["version"] == "3.1.3"
        assert index["fresh_candidate"]["generation_dspy"]["version"] == "3.3.0"
        assert source_outcomes["dspy_runtime"]["version"] == "3.1.3"
        assert candidate_outcomes["dspy_runtime"]["version"] == "3.3.0"
        assert index["source_identity"]["dspy"] == "3.3.0"
        assert index["source_identity"]["dspy_ai"] == "3.3.0"

        source_manifest_path = _assert_artifact(index["historical_lineage"]["manifest"])
        _assert_artifact(index["historical_lineage"]["manifest_receipt"])
        _assert_artifact(index["historical_lineage"]["intent"])
        candidate_manifest_path = _assert_artifact(index["fresh_candidate"]["manifest"])
        candidate_receipt_path = _assert_artifact(
            index["fresh_candidate"]["manifest_receipt"]
        )
        assert _identity(source_manifest) == index["historical_lineage"]["identity"]
        assert _identity(candidate_manifest) == index["fresh_candidate"]["identity"]
        assert index["fresh_candidate"]["historical_manifest_sha256"] == _sha256(
            source_manifest_path
        )
        freshness = index["fresh_candidate"]["identity_freshness"]
        assert freshness["request_id"] == "shared_intent_lineage"
        assert freshness["request_id_matches_historical"] is True
        assert freshness["fresh_fields"] == [
            "assembly_id",
            "candidate_id",
            "episode_id",
            "receipt_bundle_id",
        ]
        assert freshness["fresh_fields_all_distinct"] is True
        assert (
            _identity(source_manifest)["request_id"]
            == _identity(candidate_manifest)["request_id"]
        )
        for key in freshness["fresh_fields"]:
            assert _identity(source_manifest)[key] != _identity(candidate_manifest)[key]

        candidate_receipt = _load(candidate_receipt_path)
        assert candidate_receipt["hash"] == _sha256(candidate_manifest_path)
        surfaces = candidate_manifest["candidate_assembly"]["surfaces"]
        assert len(surfaces) == (28 if mode in {"researched", "deep-research"} else 27)
        for surface in surfaces:
            surface_path_value = surface.get("path")
            surface_hash = surface.get("content_hash")
            assert isinstance(surface_path_value, str)
            assert isinstance(surface_hash, str)
            surface_path = candidate_root / surface_path_value
            assert surface_path.is_file()
            assert _sha256(surface_path) == surface_hash

        topology = candidate_manifest["intent"]["topology"]
        assert topology["kind"] == index["fresh_candidate"]["topology"]["kind"]
        assert [module["id"] for module in topology["modules"]] == index[
            "fresh_candidate"
        ]["topology"]["module_order"]
        assert candidate_manifest["intent"]["inputs"] == [
            "transcription",
            "persona_intent",
        ]
        assert candidate_manifest["intent"]["outputs"] == ["response"]

        generated_python = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(candidate_root.glob("*.py"))
        )
        for forbidden in (
            "allow_pickle=True",
            "dspx_lm_auth",
            "DSPX_LM_AUTH_",
            "dspy.ReAct(",
            "dspy.ReActV2(",
            "dspy.ProgramOfThought(",
        ):
            assert forbidden not in generated_python

        assert behavior["summary"]["status"] == "failed"
        example_statuses = {example["status"] for example in behavior["examples"]}
        assert example_statuses <= {"passed", "failed"}
        assert "failed" in example_statuses
        assert all(
            example["quality_evaluation"]["quality_approved"] is False
            for example in behavior["examples"]
        )
        assert (
            index["fresh_candidate"]["generated_behavior"]["semantic_equivalence"]
            == "not_evaluated"
        )
        assert (
            index["fresh_candidate"]["generated_behavior"]["quality_approved"] is False
        )
        assert index["fresh_candidate"]["provider"] == {
            "credentials_used": False,
            "live_model_used": False,
            "model": "stub/echo",
            "name": "stub",
            "network_used": False,
            "typed_contract": "typed_lm",
        }


def test_remaining_runtime_controls_replay_without_authority_claims() -> None:
    for mode in MODES:
        base = CANARY_ROOT / mode
        index = _load(base / "canary-index.json")
        control = index["same_runtime_control"]
        assert control["provider"] == "stub"
        assert control["model"] == "stub/echo"
        assert control["typed_contract"] == "typed_lm"
        _assert_artifact(control["runtime_inputs"])
        _assert_artifact(control["stub_response"])
        binding_path = _assert_artifact(index["runtime_environment_binding"])
        binding = _load(binding_path)
        assert binding["schema_version"] == (
            "voice-turn-runtime-environment-binding-v1"
        )
        assert binding["binding_kind"] == (
            "hash_bound_local_post_execution_environment_observation"
        )
        assert binding["environment"]["dspy"] == "3.3.0"
        assert binding["environment"]["dspy_ai"] == "3.3.0"
        assert (
            binding["environment"]["dspx_core"] == index["source_identity"]["dspx_core"]
        )
        assert binding["environment"]["platform"] == "linux"
        assert binding["environment"]["python"] == index["source_identity"]["python"]
        assert (
            binding["environment"]["git_commit"]
            == index["source_identity"]["git_commit"]
        )
        assert not any(binding["effect"].values())
        assert index["claims"]["runtime_dspy_3_3_identity"] == (
            "hash_bound_local_environment_observation_not_external_attestation"
        )
        for artifact in index["command_results"].values():
            _assert_artifact(artifact)

        for key in ("historical_artifact_runtime", "fresh_candidate_runtime"):
            runtime = control[key]
            episode_path = _assert_artifact(runtime["episode"])
            receipt_path = _assert_artifact(runtime["receipt"])
            replay_path = _assert_artifact(runtime["replay_output"])
            episode = _load(episode_path)
            receipt = _load(receipt_path)
            replay = _load(replay_path)

            assert receipt["hash"] == _sha256(episode_path)
            assert episode["runtime_episode_id"] == runtime["runtime_episode_id"]
            assert (
                episode["execution_status"] == runtime["execution_status"] == "executed"
            )
            assert episode["provider"]["metadata"]["provider"] == "stub"
            assert episode["provider"]["metadata"]["typed_contract"] == "typed_lm"
            effects = episode["provider"]["effect_evidence"]
            assert effects["attempt_total"] == runtime["attempt_total"] == 4
            assert effects["attempts_truncated"] is False
            assert effects["terminal_effect"] == "completed_success"
            assert all(
                attempt["dispatch_count"] == 1
                and attempt["effect_disposition"] == "completed_success"
                and attempt["provider_kind"] == "stub"
                for attempt in effects["attempts"]
            )
            assert replay["status"] == "execution_reproduced"
            assert replay["runtime_episode_id"] == runtime["runtime_episode_id"]
            assert replay["behavior_quality_approved"] is False
            assert replay["effects"]["network_access_requested"] is False
            assert replay["effects"]["provider_call"] is False
            assert not any(replay["non_authority"].values())

            binding_key = (
                "historical_original"
                if key == "historical_artifact_runtime"
                else "fresh_candidate"
            )
            bound_execution = binding["executions"][binding_key]
            assert _assert_artifact(bound_execution["runtime_episode"]) == episode_path
            assert _assert_artifact(bound_execution["runtime_receipt"]) == receipt_path
            assert (
                _assert_artifact(bound_execution["runtime_replay_output"])
                == replay_path
            )
            _assert_artifact(bound_execution["runtime_replay_result"])
            assert (
                bound_execution["runtime_episode_id"] == runtime["runtime_episode_id"]
            )
            assert bound_execution["execution_status"] == "executed"
            assert bound_execution["replay_status"] == "executed"
            assert bound_execution["replay_runtime_reproduction"] == "passed"
            assert bound_execution["provider"] == "stub"
            assert bound_execution["typed_contract"] == "typed_lm"
            assert (
                bound_execution["receipt_execution_context"]["python_version"]
                == (binding["environment"]["python"])
            )
            assert (
                bound_execution["receipt_execution_context"]["git_commit"]
                == binding["environment"]["git_commit"][:12]
            )

        for entry in control["receipt_checks"].values():
            report = _load(_assert_artifact(entry))
            assert report["status"] == "ok"
            claims = report["replay_claims"]["dimensions"]
            assert claims["receipt_integrity_check"]["status"] == "passed"
            assert claims["semantic_reproduction"]["status"] == "not_evaluated"
        for entry in control["runtime_replay_results"].values():
            report = _load(_assert_artifact(entry))
            assert report["status"] == "executed"
            claims = report["replay_claims"]["dimensions"]
            assert claims["runtime_execution_reproduction"]["status"] == "passed"
            assert claims["semantic_reproduction"]["status"] == "not_evaluated"
            assert not any(report["replay_claims"]["authority"].values())

        comparison = _load(_assert_artifact(index["comparison"]["artifact"]))
        assert comparison["status"] == "compared"
        assert (
            comparison["runtime_evidence_comparison"]["delta"]["status_changed"]
            is False
        )
        assert comparison["interpretation"]["needs_more_evidence"] is True
        assert comparison["non_authority"]["local_comparison_only"] is True
        assert not any(
            value
            for name, value in comparison["non_authority"].items()
            if name != "local_comparison_only"
        )
        assert index["comparison"]["causal_dspy_version_claim"] is False
        assert index["comparison"]["semantic_equivalence_claim"] is False
        assert index["comparison"]["quality_regression_claim"] is False
        assert not any(index["effects"].values())
        assert index["routing"] == {
            "ai_control_brains_updated": False,
            "canary_selected_for_runtime": False,
            "manifest_index_updated": False,
        }
        assert index["claims"]["optimized_or_gepa_compatibility"] == "not_evaluated"
        assert index["claims"]["production_activation"] is False

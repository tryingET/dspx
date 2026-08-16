from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
VOICE_ROOT = REPO_ROOT / "examples" / "voice_turn_brains"
CANARY_ROOT = VOICE_ROOT / "canaries" / "dspy-3.3.0" / "simple"
SOURCE_ROOT = VOICE_ROOT / "candidates" / "simple" / "original"


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_indexed_artifact(entry: dict[str, Any]) -> Path:
    path = REPO_ROOT / str(entry["path"])
    assert path.is_file()
    assert path.stat().st_size == entry["size"]
    assert _sha256(path) == entry["sha256"]
    return path


def _manifest_identity(manifest: dict[str, Any]) -> dict[str, str]:
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


def test_historical_voice_turn_artifacts_remain_byte_identical() -> None:
    inventory = _load(CANARY_ROOT / "historical-inventory.json")
    assert inventory["schema_version"] == "voice-turn-historical-inventory-v1"
    assert inventory["file_count"] == 469
    assert inventory["aggregate_sha256"] == (
        "8a1d1075964cd465547247f6b6ba72af3336b6ac8b9804b14159133b82d64ce1"
    )

    expected_paths = {entry["path"] for entry in inventory["files"]}
    assert not any(path.startswith("canaries/") for path in expected_paths)
    actual_paths = {
        path.relative_to(VOICE_ROOT).as_posix()
        for path in VOICE_ROOT.rglob("*")
        if path.is_file()
        and not path.relative_to(VOICE_ROOT).as_posix().startswith("canaries/")
    }
    assert actual_paths == expected_paths

    aggregate = hashlib.sha256()
    for entry in inventory["files"]:
        path = VOICE_ROOT / entry["path"]
        data = path.read_bytes()
        assert len(data) == entry["size"]
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
        aggregate.update(entry["path"].encode())
        aggregate.update(b"\0")
        aggregate.update(str(len(data)).encode())
        aggregate.update(b"\0")
        aggregate.update(data)
        aggregate.update(b"\0")
    assert aggregate.hexdigest() == inventory["aggregate_sha256"]

    outcomes = sorted(
        (VOICE_ROOT / "candidates").glob("*/*/program_runtime_outcomes.json")
    )
    assert len(outcomes) == 12
    assert {_load(path)["dspy_runtime"]["version"] for path in outcomes} == {"3.1.3"}

    for routing_file in ("manifest-index.json", "ai-control-brains.json"):
        assert "canaries/" not in (VOICE_ROOT / routing_file).read_text(
            encoding="utf-8"
        )


def test_fresh_candidate_has_new_dspy_33_identity_and_bounded_shape() -> None:
    index = _load(CANARY_ROOT / "canary-index.json")
    source_manifest = _load(SOURCE_ROOT / "manifest.json")
    candidate_root = CANARY_ROOT / "candidate"
    candidate_manifest = _load(candidate_root / "manifest.json")
    outcomes = _load(candidate_root / "program_runtime_outcomes.json")
    behavior = _load(candidate_root / "behavior_results.json")

    assert index["schema_version"] == "voice-turn-dspy-3.3-migration-canary-v1"
    assert index["posture"] == "non_destructive_offline_compatibility_canary"
    assert index["source_identity"]["dspy"] == "3.3.0"
    assert index["source_identity"]["dspy_ai"] == "3.3.0"
    assert index["historical_lineage"]["generation_dspy"]["version"] == "3.1.3"
    assert index["fresh_candidate"]["generation_dspy"]["version"] == "3.3.0"
    assert outcomes["dspy_runtime"]["version"] == "3.3.0"

    assert (
        _manifest_identity(source_manifest) == index["historical_lineage"]["identity"]
    )
    assert (
        _manifest_identity(candidate_manifest) == index["fresh_candidate"]["identity"]
    )
    for key in ("assembly_id", "candidate_id", "episode_id", "receipt_bundle_id"):
        assert (
            index["historical_lineage"]["identity"][key]
            != index["fresh_candidate"]["identity"][key]
        )
    assert index["fresh_candidate"]["identity_is_new"] is True

    _assert_indexed_artifact(index["historical_lineage"]["intent"])
    source_manifest_path = _assert_indexed_artifact(
        index["historical_lineage"]["manifest"]
    )
    _assert_indexed_artifact(index["historical_lineage"]["manifest_receipt"])
    candidate_manifest_path = _assert_indexed_artifact(
        index["fresh_candidate"]["manifest"]
    )
    _assert_indexed_artifact(index["fresh_candidate"]["manifest_receipt"])
    assert index["fresh_candidate"]["historical_manifest_sha256"] == _sha256(
        source_manifest_path
    )
    assert candidate_manifest_path == candidate_root / "manifest.json"

    candidate_receipt = _load(candidate_root / "manifest.json.meta.json")
    assert candidate_receipt["hash"] == _sha256(candidate_manifest_path)
    surfaces = candidate_manifest["candidate_assembly"]["surfaces"]
    assert len(surfaces) == 27
    for surface in surfaces:
        path_value = surface.get("path")
        hash_value = surface.get("content_hash")
        assert isinstance(path_value, str)
        assert isinstance(hash_value, str)
        surface_path = candidate_root / path_value
        assert surface_path.is_file()
        assert _sha256(surface_path) == hash_value

    topology = candidate_manifest["intent"]["topology"]
    assert topology["kind"] == "pipeline"
    assert [module["id"] for module in topology["modules"]] == [
        "define_persona",
        "answer_simple",
    ]
    assert [module["primitive"] for module in topology["modules"]] == [
        "Predict",
        "Predict",
    ]
    assert candidate_manifest["intent"]["inputs"] == [
        "transcription",
        "persona_intent",
    ]
    assert candidate_manifest["intent"]["outputs"] == ["response"]

    generated_python = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(candidate_root.glob("*.py"))
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

    provider = index["fresh_candidate"]["provider"]
    assert provider == {
        "credentials_used": False,
        "live_model_used": False,
        "model": "stub/echo",
        "name": "stub",
        "network_used": False,
        "typed_contract": "typed_lm",
    }
    assert behavior["summary"]["status"] == "failed"
    assert {item["status"] for item in behavior["examples"]} == {"failed"}
    assert all(
        item["quality_evaluation"]["quality_approved"] is False
        for item in behavior["examples"]
    )
    assert index["fresh_candidate"]["generated_behavior"] == {
        "behavior_quality": "not_evaluated",
        "fixture_output_kind": "stub_placeholder",
        "quality_approved": False,
        "semantic_equivalence": "not_evaluated",
        "status": "failed",
    }


def test_runtime_receipts_replay_and_comparison_remain_non_authoritative() -> None:
    index = _load(CANARY_ROOT / "canary-index.json")
    control = index["same_runtime_control"]
    assert control["provider"] == "stub"
    assert control["model"] == "stub/echo"
    assert control["typed_contract"] == "typed_lm"
    assert control["fixture_artifacts_match"] is True

    for key in ("historical_artifact_runtime", "fresh_candidate_runtime"):
        runtime = control[key]
        episode_path = _assert_indexed_artifact(runtime["episode"])
        receipt_path = _assert_indexed_artifact(runtime["receipt"])
        replay_path = _assert_indexed_artifact(runtime["replay_output"])
        episode = _load(episode_path)
        receipt = _load(receipt_path)
        replay = _load(replay_path)

        assert receipt["hash"] == _sha256(episode_path)
        assert episode["runtime_episode_id"] == runtime["runtime_episode_id"]
        assert episode["execution_status"] == "executed"
        assert episode["provider"]["metadata"]["typed_contract"] == "typed_lm"
        assert episode["provider"]["metadata"]["provider"] == "stub"
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

    for entry in control["receipt_checks"].values():
        report = _load(_assert_indexed_artifact(entry))
        assert report["status"] == "ok"
        assert (
            report["replay_claims"]["dimensions"]["receipt_integrity_check"]["status"]
            == "passed"
        )
        assert (
            report["replay_claims"]["dimensions"]["semantic_reproduction"]["status"]
            == "not_evaluated"
        )

    for entry in control["runtime_replay_results"].values():
        report = _load(_assert_indexed_artifact(entry))
        assert report["status"] == "executed"
        claims = report["replay_claims"]["dimensions"]
        assert claims["receipt_integrity_check"]["status"] == "passed"
        assert claims["runtime_execution_reproduction"]["status"] == "passed"
        assert claims["semantic_reproduction"]["status"] == "not_evaluated"
        assert report["replay_claims"]["release_claim_allowed"] is False
        assert not any(report["replay_claims"]["authority"].values())

    comparison = _load(_assert_indexed_artifact(index["comparison"]["artifact"]))
    assert comparison["status"] == "compared"
    assert comparison["behavior_comparison"]["delta"]["failure_signals_persisted"] == [
        "mismatch:response"
    ]
    assert comparison["runtime_evidence_comparison"]["delta"]["status_changed"] is False
    assert comparison["interpretation"]["needs_more_evidence"] is True
    assert comparison["non_authority"]["local_comparison_only"] is True
    assert not any(
        value
        for key, value in comparison["non_authority"].items()
        if key != "local_comparison_only"
    )
    assert comparison["effect"]["local_comparison_only"] is True
    assert not any(
        value
        for key, value in comparison["effect"].items()
        if key != "local_comparison_only"
    )

    assert index["comparison"]["causal_dspy_version_claim"] is False
    assert index["comparison"]["semantic_equivalence_claim"] is False
    assert index["comparison"]["quality_regression_claim"] is False
    assert index["routing"] == {
        "ai_control_brains_updated": False,
        "canary_selected_for_runtime": False,
        "manifest_index_updated": False,
    }
    assert not any(index["effects"].values())
    assert index["claims"]["behavior_quality"] == "not_evaluated"
    assert index["claims"]["semantic_equivalence"] == "not_evaluated"
    assert index["claims"]["optimized_or_gepa_compatibility"] == "not_evaluated"
    assert index["claims"]["production_activation"] is False

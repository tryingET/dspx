from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from dspx.cli.dspx import app
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_runtime_episode import run_program_runtime_episode
from dspx.services.program_service import materialize_program_from_intent
from program_activation_packet_shared import (
    _candidate_identity,
    _file_hashes,
    _materialize_program,
    _materialize_review_chain,
    _write_json,
    _setup_env,
    _write_obsidian_adapter_receipt,
    _write_target_aware_candidate_state,
    runner,
)

pytestmark = pytest.mark.slow


def _hash_ref(path: Path) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "schema_version": json.loads(path.read_text(encoding="utf-8")).get(
            "schema_version"
        ),
    }


def _materialize_runtime_program(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    outdir_name: str = "program",
    program_name: str = "ActivationTicketProgram",
) -> Path:
    _setup_env(tmp_path, monkeypatch)
    artifact = materialize_program_from_intent(
        ProgramIntent(
            name=program_name,
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
        ),
        outdir=tmp_path / outdir_name,
    )
    return Path(artifact.root_path)


def _write_runtime_episode(root: Path, tmp_path: Path) -> Path:
    runtime_inputs = tmp_path / "runtime" / "runtime-inputs.json"
    _write_json(
        runtime_inputs,
        {"inputs": {"ticket_text": "Server is down for all users"}},
    )
    runtime_root = tmp_path / "runtime" / "episode"
    run_program_runtime_episode(
        manifest_path=root / "manifest.json",
        inputs_path=runtime_inputs,
        outdir=runtime_root,
        skip_oracle_index=True,
    )
    return runtime_root / "runtime_episode.json"


def _write_candidate_state_with_runtime_episode(
    root: Path,
    runtime_episode_path: Path,
    out: Path,
    *,
    runtime_hash: str | None = None,
) -> Path:
    episode = json.loads(runtime_episode_path.read_text(encoding="utf-8"))
    episode_hashes = episode["artifact_hashes"]
    manifest_hash = hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest()
    supplied_hash = (
        runtime_hash or hashlib.sha256(runtime_episode_path.read_bytes()).hexdigest()
    )
    _write_json(
        out,
        {
            "schema_version": "program-candidate-state-v1",
            "status": "not_promoted_materialized",
            "candidate_identity": _candidate_identity(root),
            "created_from": {"runtime_episode_path": str(runtime_episode_path)},
            "artifact_hashes": {
                "manifest_sha256": manifest_hash,
                "source_manifest_sha256": manifest_hash,
                "runtime_episode_sha256": supplied_hash,
            },
            "evidence_state": {
                "runtime_episode": {
                    "present": True,
                    "schema_version": "program-runtime-episode-v1",
                    "status": episode["status"],
                    "runtime_episode_id": episode["runtime_episode_id"],
                    "contract_mode": episode["contract_mode"],
                    "sha256": supplied_hash,
                    "source_manifest_sha256": episode_hashes["source_manifest_sha256"],
                    "runtime_inputs_sha256": episode_hashes["runtime_inputs_sha256"],
                    "behavior_results_sha256": episode_hashes[
                        "behavior_results_sha256"
                    ],
                    "program_runtime_traces_sha256": episode_hashes[
                        "program_runtime_traces_sha256"
                    ],
                    "oracle_evidence_sha256": episode_hashes["oracle_evidence_sha256"],
                    "evidence_only": True,
                    "activation_authority": False,
                    "promotion_authority": False,
                }
            },
            "non_authority": {
                "agent_kernel_mutation": False,
                "apply_promotion": False,
                "automatic_promotion": False,
                "external_apply": False,
                "governance_authority": False,
                "oracle_authority": False,
                "promotion_authority": False,
                "winner_selection": False,
            },
        },
    )
    return out


def _write_model_jury_results(
    root: Path,
    out: Path,
    *,
    authority_drift: bool = False,
    promotion_authority: bool = False,
    status: str = "executed",
) -> Path:
    identity = _candidate_identity(root)
    if authority_drift:
        identity = {**identity, "candidate_id": "wrong-candidate"}
    manifest_path = root / "manifest.json"
    jury_path = root / "jury.json"
    selection_path = root / "jury_selection.json"
    rubric_path = root / "jury_rubric.json"
    evidence_entries = [
        _hash_ref(path)
        for path in (root / "behavior_results.json", root / "behavior_episode.json")
        if path.exists()
    ]
    _write_json(
        out,
        {
            "schema_version": "program-model-jury-results-v1",
            "status": status,
            "identity": identity,
            "created_from": {
                "manifest_path": str(manifest_path.resolve()),
                "manifest_sha256": hashlib.sha256(
                    manifest_path.read_bytes()
                ).hexdigest(),
                "jury_path": str(jury_path.resolve()),
                "jury_sha256": hashlib.sha256(jury_path.read_bytes()).hexdigest(),
                "jury_selection_path": str(selection_path.resolve()),
                "jury_selection_sha256": hashlib.sha256(
                    selection_path.read_bytes()
                ).hexdigest(),
                "jury_rubric_path": str(rubric_path.resolve()),
                "jury_rubric_sha256": hashlib.sha256(
                    rubric_path.read_bytes()
                ).hexdigest(),
            },
            "jury": {
                "execution_mode": "provider_backed_model",
                "provider_backed_model_calls": True,
                "selected_juror_count": 1,
                "selected_perspectives": ["authority_boundaries"],
            },
            "adjudicator": {
                "repo": "target-repo",
                "promotion_authority": promotion_authority,
            },
            "evidence": {
                "entry_count": len(evidence_entries),
                "entries": evidence_entries,
            },
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
                "unique_improvement_requests": ["collect target evidence"],
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
        },
    )
    return out


def test_program_promote_activation_packet_blocks_without_required_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    before_hashes = _file_hashes(program_root)
    out_path = tmp_path / "activation" / "activation_packet.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert json.loads(out_path.read_text(encoding="utf-8")) == payload
    assert payload["schema_version"] == (
        "generated-cognition-program-production-activation-packet-v1"
    )
    assert payload["transition_type"] == (
        "generated-cognition-program.production_activation"
    )
    assert payload["status"] == "blocked"
    assert payload["owning_domain"] == "softwareco/dspx-generated-program-governance"
    assert payload["activation_target"] == "local-dogfood-only"
    assert "oracle_report" in payload["missing_required_evidence"]
    assert "jury_evidence" in payload["missing_required_evidence"]
    assert "refined_promotion_review" in payload["missing_required_evidence"]
    assert "rollout_owner" in payload["missing_required_evidence"]
    assert "rollback_plan" in payload["missing_required_evidence"]
    assert payload["boundary_checks"] == {
        "mlflow_approval_authority": False,
        "oracle_promotion_authority": False,
        "oracle_publication_activation_authority": False,
        "jury_promotion_authority": False,
        "dspx_activation_authority": False,
        "requires_domain_governing_body": True,
        "requires_rollout_owner_before_rollout": True,
        "requires_rollback_plan_before_rollout": True,
        "requires_canonical_binding_before_rollout": True,
        "requires_obsidian_review_adapter_when_requested": False,
    }
    assert payload["non_authority"]["activation_packet_only"] is True
    assert payload["effect"]["production_activation_applied"] is False
    assert _file_hashes(program_root) == before_hashes
    assert not (program_root / "activation_packet.json").exists()


def test_program_promote_activation_packet_includes_program_run_runtime_episode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_runtime_program(tmp_path, monkeypatch)
    runtime_episode = _write_runtime_episode(program_root, tmp_path)
    out_path = tmp_path / "activation" / "activation_packet.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--runtime-episode",
            str(runtime_episode),
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    runtime_ref = payload["evidence"]["runtime_episode"]
    assert runtime_ref["schema_version"] == "program-runtime-episode-v1"
    assert (
        runtime_ref["sha256"]
        == hashlib.sha256(runtime_episode.read_bytes()).hexdigest()
    )
    assert runtime_ref["status"] == "executed"
    assert runtime_ref["evidence_only"] is True
    assert runtime_ref["activation_authority"] is False
    assert runtime_ref["promotion_authority"] is False
    assert runtime_ref["shared_oracle_mutated"] is False
    assert (
        runtime_ref["source_manifest_sha256"]
        == hashlib.sha256((program_root / "manifest.json").read_bytes()).hexdigest()
    )
    assert payload["status"] == "blocked"
    assert "oracle_report" in payload["missing_required_evidence"]
    assert payload["effect"]["production_activation_applied"] is False
    assert payload["non_authority"]["activation_packet_only"] is True


def test_program_promote_activation_packet_rejects_stale_program_run_manifest_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_runtime_program(tmp_path, monkeypatch)
    runtime_episode = _write_runtime_episode(program_root, tmp_path)
    manifest_path = program_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["candidate_assembly"]["status"] = "materialized_after_runtime_drift"
    _write_json(manifest_path, manifest)

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(manifest_path),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--runtime-episode",
            str(runtime_episode),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
        ],
    )

    assert result.exit_code == 2
    assert "source_manifest_sha256" in result.output


def test_program_promote_activation_packet_rejects_cross_candidate_runtime_episode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_runtime_program(tmp_path, monkeypatch)
    other_root = _materialize_runtime_program(
        tmp_path,
        monkeypatch,
        outdir_name="other-program",
        program_name="OtherActivationTicketProgram",
    )
    runtime_episode = _write_runtime_episode(other_root, tmp_path)

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--runtime-episode",
            str(runtime_episode),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
        ],
    )

    assert result.exit_code == 2
    assert "candidate_manifest_path" in result.output


def test_program_promote_activation_packet_rejects_runtime_episode_trace_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_runtime_program(tmp_path, monkeypatch)
    runtime_episode = _write_runtime_episode(program_root, tmp_path)
    traces_path = runtime_episode.parent / "program_runtime_traces.json"
    traces = json.loads(traces_path.read_text(encoding="utf-8"))
    traces["status"] = "no_runtime_traces_captured"
    _write_json(traces_path, traces)

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--runtime-episode",
            str(runtime_episode),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
        ],
    )

    assert result.exit_code == 2
    assert "program_runtime_traces_sha256" in result.output


def test_program_promote_activation_packet_rejects_runtime_episode_wrong_path_fresh_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_runtime_program(tmp_path, monkeypatch)
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
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--runtime-episode",
            str(runtime_episode),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
        ],
    )

    assert result.exit_code == 2
    assert "behavior_results_path" in result.output


def test_program_promote_activation_packet_rejects_runtime_episode_symlink_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_runtime_program(tmp_path, monkeypatch)
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
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--runtime-episode",
            str(runtime_episode),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
        ],
    )

    assert result.exit_code == 2
    assert "escapes runtime episode root" in result.output


def test_program_promote_activation_packet_rejects_runtime_episode_authority_spoof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_runtime_program(tmp_path, monkeypatch)
    runtime_episode = _write_runtime_episode(program_root, tmp_path)
    payload = json.loads(runtime_episode.read_text(encoding="utf-8"))
    payload["non_authority"]["promotion_authority"] = True
    _write_json(runtime_episode, payload)

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--runtime-episode",
            str(runtime_episode),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
        ],
    )

    assert result.exit_code == 2
    assert "non_authority" in result.output


def test_program_promote_activation_packet_aligns_candidate_state_runtime_episode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_runtime_program(tmp_path, monkeypatch)
    runtime_episode = _write_runtime_episode(program_root, tmp_path)
    candidate_state = _write_candidate_state_with_runtime_episode(
        program_root,
        runtime_episode,
        tmp_path / "state" / "program_candidate_state.json",
    )
    out_path = tmp_path / "activation" / "activation_packet.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--candidate-state",
            str(candidate_state),
            "--runtime-episode",
            str(runtime_episode),
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert (
        payload["evidence"]["candidate_state"]["sha256"]
        == hashlib.sha256(candidate_state.read_bytes()).hexdigest()
    )
    assert (
        payload["evidence"]["runtime_episode"]["sha256"]
        == hashlib.sha256(runtime_episode.read_bytes()).hexdigest()
    )


def test_program_promote_activation_packet_rejects_candidate_state_runtime_omission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_runtime_program(tmp_path, monkeypatch)
    runtime_episode = _write_runtime_episode(program_root, tmp_path)
    candidate_state = _write_candidate_state_with_runtime_episode(
        program_root,
        runtime_episode,
        tmp_path / "state" / "program_candidate_state.json",
    )

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--candidate-state",
            str(candidate_state),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
        ],
    )

    assert result.exit_code == 2
    assert "candidate_state references runtime_episode" in result.output


def test_program_promote_activation_packet_rejects_candidate_state_runtime_hash_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_runtime_program(tmp_path, monkeypatch)
    runtime_episode = _write_runtime_episode(program_root, tmp_path)
    candidate_state = _write_candidate_state_with_runtime_episode(
        program_root,
        runtime_episode,
        tmp_path / "state" / "program_candidate_state.json",
        runtime_hash="0" * 64,
    )

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--candidate-state",
            str(candidate_state),
            "--runtime-episode",
            str(runtime_episode),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
        ],
    )

    assert result.exit_code == 2
    assert "runtime_episode hash does not match" in result.output


def test_program_promote_activation_packet_rejects_stale_candidate_state_manifest_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_runtime_program(tmp_path, monkeypatch)
    runtime_episode = _write_runtime_episode(program_root, tmp_path)
    candidate_state = _write_candidate_state_with_runtime_episode(
        program_root,
        runtime_episode,
        tmp_path / "state" / "program_candidate_state.json",
    )
    payload = json.loads(candidate_state.read_text(encoding="utf-8"))
    payload["artifact_hashes"]["manifest_sha256"] = "0" * 64
    _write_json(candidate_state, payload)

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--candidate-state",
            str(candidate_state),
            "--runtime-episode",
            str(runtime_episode),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
        ],
    )

    assert result.exit_code == 2
    assert "candidate_state manifest_sha256 does not match" in result.output


def test_program_promote_activation_packet_rejects_candidate_state_runtime_path_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_runtime_program(tmp_path, monkeypatch)
    runtime_episode = _write_runtime_episode(program_root, tmp_path)
    candidate_state = _write_candidate_state_with_runtime_episode(
        program_root,
        runtime_episode,
        tmp_path / "state" / "program_candidate_state.json",
    )
    payload = json.loads(candidate_state.read_text(encoding="utf-8"))
    payload["created_from"]["runtime_episode_path"] = str(
        tmp_path / "other" / "runtime_episode.json"
    )
    _write_json(candidate_state, payload)

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--candidate-state",
            str(candidate_state),
            "--runtime-episode",
            str(runtime_episode),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
        ],
    )

    assert result.exit_code == 2
    assert "runtime_episode_path does not match" in result.output


def test_program_promote_activation_packet_rejects_candidate_state_runtime_summary_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_runtime_program(tmp_path, monkeypatch)
    runtime_episode = _write_runtime_episode(program_root, tmp_path)
    candidate_state = _write_candidate_state_with_runtime_episode(
        program_root,
        runtime_episode,
        tmp_path / "state" / "program_candidate_state.json",
    )
    payload = json.loads(candidate_state.read_text(encoding="utf-8"))
    payload["evidence_state"]["runtime_episode"]["runtime_episode_id"] = "stale"
    _write_json(candidate_state, payload)

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--candidate-state",
            str(candidate_state),
            "--runtime-episode",
            str(runtime_episode),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
        ],
    )

    assert result.exit_code == 2
    assert "runtime_episode summary does not match" in result.output


def test_program_promote_activation_packet_requires_obsidian_review_adapter_when_requested(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    out_path = tmp_path / "activation" / "activation_packet.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "obsidian/pdf-transition",
            "--activation-target",
            "obsidian-pdf-transition-generated-program-runtime",
            "--authority-owner",
            "obsidian-pdf-transition-governance",
            "--require-obsidian-review-adapter",
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert (
        "target_aware_candidate_state_missing" in payload["missing_required_evidence"]
    )
    assert (
        "obsidian_review_adapter_receipt_missing"
        in payload["missing_required_evidence"]
    )
    assert payload["target_review_admission"] == {
        "candidate_state": None,
        "obsidian_review_adapter_receipt": None,
        "target_protocol_fidelity_judgment": None,
        "review_adapter_materialization_allowed": False,
        "review_packet_materialized": False,
        "review_only": True,
        "production_activation_authority": False,
        "canonical_mutation_authority": False,
        "canonical_mutation_allowed": False,
        "status": "blocked",
        "blockers": [
            "target_aware_candidate_state_missing",
            "obsidian_review_adapter_receipt_missing",
        ],
    }
    assert "domain_decision_record" in payload["remaining_activation_blockers"]
    assert "canonical_binding_ref" in payload["remaining_activation_blockers"]
    assert payload["effect"]["production_activation_applied"] is False


def test_program_promote_activation_packet_records_obsidian_review_admission_without_activation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    candidate_state_path = _write_target_aware_candidate_state(
        program_root,
        tmp_path / "activation" / "program_candidate_state.json",
    )
    adapter_receipt_path = _write_obsidian_adapter_receipt(
        candidate_state_path,
        tmp_path / "activation" / "adapter-receipt.json",
    )
    out_path = tmp_path / "activation" / "activation_packet.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "obsidian/pdf-transition",
            "--activation-target",
            "obsidian-pdf-transition-generated-program-runtime",
            "--authority-owner",
            "obsidian-pdf-transition-governance",
            "--candidate-state",
            str(candidate_state_path),
            "--obsidian-review-adapter-receipt",
            str(adapter_receipt_path),
            "--require-obsidian-review-adapter",
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert (
        "target_aware_candidate_state_missing"
        not in payload["missing_required_evidence"]
    )
    assert (
        "obsidian_review_adapter_receipt_missing"
        not in payload["missing_required_evidence"]
    )
    assert payload["target_review_admission"]["status"] == "review_admitted"
    assert (
        payload["target_review_admission"]["target_protocol_fidelity_judgment"]
        == "supports_domain_review"
    )
    assert (
        payload["target_review_admission"]["review_adapter_materialization_allowed"]
        is True
    )
    assert payload["target_review_admission"]["review_packet_materialized"] is True
    assert (
        payload["target_review_admission"]["production_activation_authority"] is False
    )
    assert payload["target_review_admission"]["canonical_mutation_authority"] is False
    assert payload["target_review_admission"]["blockers"] == []
    assert (
        "target_aware_candidate_state_missing"
        not in payload["remaining_activation_blockers"]
    )
    assert (
        "obsidian_review_adapter_receipt_missing"
        not in payload["remaining_activation_blockers"]
    )
    assert "domain_decision_record" in payload["remaining_activation_blockers"]
    assert "canonical_binding_ref" in payload["remaining_activation_blockers"]
    assert payload["evidence"]["candidate_state"]["path"] == str(
        candidate_state_path.resolve()
    )
    assert payload["evidence"]["obsidian_review_adapter_receipt"]["path"] == str(
        adapter_receipt_path.resolve()
    )
    assert payload["effect"]["production_activation_applied"] is False


def test_program_promote_activation_packet_rejects_obsidian_adapter_authority_widening(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    candidate_state_path = _write_target_aware_candidate_state(
        program_root,
        tmp_path / "activation" / "program_candidate_state.json",
    )
    adapter_receipt_path = _write_obsidian_adapter_receipt(
        candidate_state_path,
        tmp_path / "activation" / "adapter-receipt.json",
    )
    receipt = json.loads(adapter_receipt_path.read_text(encoding="utf-8"))
    receipt["wiki_mutation_performed"] = True
    adapter_receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "obsidian/pdf-transition",
            "--activation-target",
            "obsidian-pdf-transition-generated-program-runtime",
            "--authority-owner",
            "obsidian-pdf-transition-governance",
            "--candidate-state",
            str(candidate_state_path),
            "--obsidian-review-adapter-receipt",
            str(adapter_receipt_path),
            "--require-obsidian-review-adapter",
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "wiki_mutation_performed false" in result.output


def test_program_promote_activation_packet_rejects_obsidian_adapter_missing_candidate_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    candidate_state_path = _write_target_aware_candidate_state(
        program_root,
        tmp_path / "activation" / "program_candidate_state.json",
    )
    adapter_receipt_path = _write_obsidian_adapter_receipt(
        candidate_state_path,
        tmp_path / "activation" / "adapter-receipt.json",
    )
    receipt = json.loads(adapter_receipt_path.read_text(encoding="utf-8"))
    del receipt["program_candidate_state_hash"]
    adapter_receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "obsidian/pdf-transition",
            "--activation-target",
            "obsidian-pdf-transition-generated-program-runtime",
            "--authority-owner",
            "obsidian-pdf-transition-governance",
            "--candidate-state",
            str(candidate_state_path),
            "--obsidian-review-adapter-receipt",
            str(adapter_receipt_path),
            "--require-obsidian-review-adapter",
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "program_candidate_state_hash is required" in result.output


def test_program_promote_activation_packet_dogfoods_review_chain_without_activation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, jury_path, review_path, decision_path = (
        _materialize_review_chain(tmp_path, monkeypatch)
    )
    before_hashes = _file_hashes(program_root)
    out_path = tmp_path / "activation" / "activation_packet.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-report",
            str(report_path),
            "--jury-results",
            str(jury_path),
            "--review",
            str(review_path),
            "--decision-record",
            str(decision_path),
            "--rollout-owner",
            "softwareco-runtime-operator",
            "--rollback-plan",
            "Disable the generated-program route and restore the previous production program version.",
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert payload["next_required_action"] == "resolve_decision_outcome"
    assert payload["missing_required_evidence"] == ["decision_outcome_not_promote"]
    assert payload["decision"] == {
        "outcome": "request_more_evidence",
        "promotion_state_after_decision": "not_promoted",
        "decided_by": "softwareco-program-governance",
    }
    assert payload["canonical_binding_ref"] is None
    assert payload["evidence"]["oracle_report"]["path"] == str(report_path.resolve())
    assert payload["evidence"]["jury_results"]["path"] == str(jury_path.resolve())
    assert payload["evidence"]["refined_review"]["path"] == str(review_path.resolve())
    assert payload["evidence"]["decision_record"]["path"] == str(
        decision_path.resolve()
    )
    assert payload["effect"] == {
        "activation_packet_written": True,
        "program_files_mutated": False,
        "oracle_index_mutated": False,
        "mlflow_mutated": False,
        "ak_mutated": False,
        "external_authority_mutated": False,
        "production_activation_applied": False,
    }
    assert _file_hashes(program_root) == before_hashes
    assert not (program_root / "activation_packet.json").exists()


def test_program_promote_activation_packet_rejects_stale_jury_result_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, jury_path, review_path, decision_path = (
        _materialize_review_chain(tmp_path, monkeypatch)
    )
    bad_jury = json.loads(jury_path.read_text(encoding="utf-8"))
    bad_jury["created_from"] = {
        **bad_jury["created_from"],
        "behavior_results_sha256": "0" * 64,
    }
    bad_jury_path = tmp_path / "promotion" / "bad_jury_results.json"
    _write_json(bad_jury_path, bad_jury)

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-report",
            str(report_path),
            "--jury-results",
            str(bad_jury_path),
            "--review",
            str(review_path),
            "--decision-record",
            str(decision_path),
            "--rollout-owner",
            "softwareco-runtime-operator",
            "--rollback-plan",
            "Disable the generated-program route and restore the previous production program version.",
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert (
        "jury_results behavior results sha256 does not match current file"
        in result.output
    )


@pytest.mark.parametrize(
    ("effect_patch", "expected_error"),
    [
        ({"program_files_mutated": True}, "jury_results widens effect flags"),
        (
            {"local_jury_evidence_only": False},
            "jury_results must be local jury evidence only",
        ),
    ],
)
def test_program_promote_activation_packet_rejects_spoofed_jury_effect_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    effect_patch: dict[str, object],
    expected_error: str,
) -> None:
    program_root, report_path, jury_path, review_path, decision_path = (
        _materialize_review_chain(tmp_path, monkeypatch)
    )
    before_hashes = _file_hashes(program_root)
    bad_jury = json.loads(jury_path.read_text(encoding="utf-8"))
    bad_jury["effect"] = {**bad_jury["effect"], **effect_patch}
    bad_jury_path = tmp_path / "promotion" / "bad_jury_effect.json"
    _write_json(bad_jury_path, bad_jury)
    out_path = tmp_path / "activation" / "activation_packet.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-report",
            str(report_path),
            "--jury-results",
            str(bad_jury_path),
            "--review",
            str(review_path),
            "--decision-record",
            str(decision_path),
            "--rollout-owner",
            "softwareco-runtime-operator",
            "--rollback-plan",
            "Disable the generated-program route and restore the previous production program version.",
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert expected_error in result.output
    assert not out_path.exists()
    assert _file_hashes(program_root) == before_hashes


@pytest.mark.parametrize(
    ("created_from_key", "expected_error"),
    [
        ("jury_path", "jury_results planned jury path is required"),
        ("jury_selection_path", "jury_results jury selection path is required"),
        ("jury_rubric_path", "jury_results jury rubric path is required"),
    ],
)
def test_program_promote_activation_packet_rejects_unbound_jury_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    created_from_key: str,
    expected_error: str,
) -> None:
    program_root, report_path, jury_path, review_path, decision_path = (
        _materialize_review_chain(tmp_path, monkeypatch)
    )
    before_hashes = _file_hashes(program_root)
    bad_jury = json.loads(jury_path.read_text(encoding="utf-8"))
    bad_jury["created_from"].pop(created_from_key)
    bad_jury_path = tmp_path / "promotion" / "bad_unbound_jury.json"
    _write_json(bad_jury_path, bad_jury)
    out_path = tmp_path / "activation" / "activation_packet.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-report",
            str(report_path),
            "--jury-results",
            str(bad_jury_path),
            "--review",
            str(review_path),
            "--decision-record",
            str(decision_path),
            "--rollout-owner",
            "softwareco-runtime-operator",
            "--rollback-plan",
            "Disable the generated-program route and restore the previous production program version.",
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert expected_error in result.output
    assert not out_path.exists()
    assert _file_hashes(program_root) == before_hashes


def test_program_promote_activation_packet_rejects_output_over_protected_or_input_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    manifest_path = program_root / "manifest.json"
    manifest_before = manifest_path.read_bytes()

    protected_result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(manifest_path),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--out",
            str(manifest_path),
            "--json",
        ],
    )
    assert protected_result.exit_code != 0
    assert (
        "activation packet must not overwrite manifest.json" in protected_result.output
    )
    assert manifest_path.read_bytes() == manifest_before

    root_sidecar_result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(manifest_path),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--out",
            str(program_root / "activation_packet.json"),
            "--json",
        ],
    )
    assert root_sidecar_result.exit_code != 0
    assert (
        "activation packet output must not be written inside a protected artifact root"
        in root_sidecar_result.output
    )
    assert not (program_root / "activation_packet.json").exists()

    model_jury_path = _write_model_jury_results(
        program_root, tmp_path / "promotion" / "provider_jury.json"
    )
    model_jury_before = model_jury_path.read_bytes()
    input_overwrite_result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(manifest_path),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--model-jury-results",
            str(model_jury_path),
            "--out",
            str(model_jury_path),
            "--json",
        ],
    )
    assert input_overwrite_result.exit_code != 0
    assert (
        "activation packet output must not overwrite an input artifact"
        in input_overwrite_result.output
    )
    assert model_jury_path.read_bytes() == model_jury_before
    assert not (program_root / "activation_packet.json").exists()


def test_program_promote_activation_packet_accepts_model_jury_as_jury_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, _jury_path, review_path, _decision_path = (
        _materialize_review_chain(tmp_path, monkeypatch)
    )
    before_hashes = _file_hashes(program_root)
    model_jury_path = _write_model_jury_results(
        program_root,
        tmp_path / "promotion" / "model_jury_results.json",
    )
    out_path = tmp_path / "activation" / "activation_packet.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-report",
            str(report_path),
            "--model-jury-results",
            str(model_jury_path),
            "--review",
            str(review_path),
            "--rollout-owner",
            "softwareco-runtime-operator",
            "--rollback-plan",
            "Disable the generated-program route and restore the previous production program version.",
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "ready_for_domain_adjudication"
    assert payload["next_required_action"] == "record_domain_decision"
    assert payload["missing_required_evidence"] == []
    assert payload["remaining_activation_blockers"] == [
        "domain_decision_record",
        "canonical_binding_ref",
    ]
    assert payload["evidence"]["jury_results"] is None
    assert payload["evidence"]["model_jury_results"]["path"] == str(
        model_jury_path.resolve()
    )
    assert payload["decision"] == {
        "outcome": None,
        "promotion_state_after_decision": None,
        "decided_by": None,
    }
    assert payload["effect"]["production_activation_applied"] is False
    assert payload["effect"]["external_authority_mutated"] is False
    assert payload["non_authority"]["activation_packet_only"] is True
    assert payload["non_authority"]["program_activation_applied"] is False
    assert _file_hashes(program_root) == before_hashes
    assert not (program_root / "activation_packet.json").exists()


def test_program_promote_activation_packet_rejects_stale_model_jury_manifest_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, _jury_path, review_path, _decision_path = (
        _materialize_review_chain(tmp_path, monkeypatch)
    )
    model_jury = json.loads(
        _write_model_jury_results(
            program_root,
            tmp_path / "promotion" / "model_jury_results.json",
        ).read_text(encoding="utf-8")
    )
    model_jury["created_from"] = {
        **model_jury["created_from"],
        "manifest_sha256": "0" * 64,
    }
    model_jury_path = tmp_path / "promotion" / "stale_model_jury_results.json"
    _write_json(model_jury_path, model_jury)
    out_path = tmp_path / "activation" / "activation_packet.json"

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-report",
            str(report_path),
            "--model-jury-results",
            str(model_jury_path),
            "--review",
            str(review_path),
            "--rollout-owner",
            "softwareco-runtime-operator",
            "--rollback-plan",
            "Disable the generated-program route and restore the previous production program version.",
            "--out",
            str(out_path),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "model_jury_results manifest sha256 does not match" in result.output
    assert not out_path.exists()


def test_program_promote_activation_packet_rejects_model_jury_identity_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, _jury_path, review_path, _decision_path = (
        _materialize_review_chain(tmp_path, monkeypatch)
    )
    model_jury_path = _write_model_jury_results(
        program_root,
        tmp_path / "promotion" / "model_jury_results.json",
        authority_drift=True,
    )

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-report",
            str(report_path),
            "--model-jury-results",
            str(model_jury_path),
            "--review",
            str(review_path),
            "--rollout-owner",
            "softwareco-runtime-operator",
            "--rollback-plan",
            "Disable the generated-program route and restore the previous production program version.",
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "model_jury_results identity does not match" in result.output


def test_program_promote_activation_packet_rejects_model_jury_invalid_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, _jury_path, review_path, _decision_path = (
        _materialize_review_chain(tmp_path, monkeypatch)
    )
    model_jury_path = _write_model_jury_results(
        program_root,
        tmp_path / "promotion" / "model_jury_results.json",
        status="not_executed",
    )

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-report",
            str(report_path),
            "--model-jury-results",
            str(model_jury_path),
            "--review",
            str(review_path),
            "--rollout-owner",
            "softwareco-runtime-operator",
            "--rollback-plan",
            "Disable the generated-program route and restore the previous production program version.",
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "status executed or executed_with_failures" in result.output


def test_program_promote_activation_packet_rejects_model_jury_authority_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, _jury_path, review_path, _decision_path = (
        _materialize_review_chain(tmp_path, monkeypatch)
    )
    model_jury_path = _write_model_jury_results(
        program_root,
        tmp_path / "promotion" / "model_jury_results.json",
        promotion_authority=True,
    )

    result = runner.invoke(
        app,
        [
            "program-promote",
            "activation-packet",
            "--manifest",
            str(program_root / "manifest.json"),
            "--owning-domain",
            "softwareco/dspx-generated-program-governance",
            "--activation-target",
            "local-dogfood-only",
            "--authority-owner",
            "softwareco-program-governance",
            "--oracle-report",
            str(report_path),
            "--model-jury-results",
            str(model_jury_path),
            "--review",
            str(review_path),
            "--rollout-owner",
            "softwareco-runtime-operator",
            "--rollback-plan",
            "Disable the generated-program route and restore the previous production program version.",
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "promotion authority" in result.output

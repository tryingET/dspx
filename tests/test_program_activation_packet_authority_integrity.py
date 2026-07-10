from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from dspx.cli.dspx import app
from dspx.services.artifact_boundary import (
    ArtifactEnvelopePolicy,
    validate_artifact_envelope,
    validate_confined_artifact,
)
from program_activation_packet_shared import (
    _candidate_identity,
    _materialize_program,
    _materialize_review_chain,
    _write_json,
    _write_target_aware_candidate_state,
    runner,
)

pytestmark = pytest.mark.slow


def test_artifact_envelope_kernel_fails_closed_on_schema_authority_and_effect() -> None:
    policy = ArtifactEnvelopePolicy(
        schema_version="test-envelope-v1",
        required_false_authority=("promotion_authority",),
        required_false_effect=("external_authority_mutated",),
    )
    valid = {
        "schema_version": "test-envelope-v1",
        "non_authority": {"promotion_authority": False},
        "effect": {"external_authority_mutated": False},
    }
    validate_artifact_envelope(valid, label="test envelope", policy=policy)

    adversarial = (
        ({**valid, "schema_version": "spoofed-v2"}, "schema_version must be"),
        (
            {**valid, "non_authority": {"promotion_authority": True}},
            "widens non-authority flags",
        ),
        (
            {**valid, "effect": {"external_authority_mutated": None}},
            "widens effect flags",
        ),
    )
    for payload, message in adversarial:
        with pytest.raises(ValueError, match=message):
            validate_artifact_envelope(payload, label="test envelope", policy=policy)


def test_confined_artifact_kernel_rejects_stale_hash_and_symlink_escape(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    artifact = root / "evidence.json"
    artifact.write_text("{}\n", encoding="utf-8")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    validated = validate_confined_artifact(
        artifact,
        root=root,
        label="evidence",
        expected_sha256=digest,
        expected_name="evidence.json",
    )
    assert validated.path == artifact.resolve()
    assert validated.sha256 == digest

    with pytest.raises(ValueError, match="sha256 does not match current file"):
        validate_confined_artifact(
            artifact,
            root=root,
            label="evidence",
            expected_sha256="0" * 64,
        )

    outside = tmp_path / "outside.json"
    outside.write_text("{}\n", encoding="utf-8")
    escape = root / "escape.json"
    escape.symlink_to(outside)
    with pytest.raises(ValueError, match="outside the confined artifact root"):
        validate_confined_artifact(
            escape,
            root=root,
            label="evidence",
            expected_sha256=hashlib.sha256(outside.read_bytes()).hexdigest(),
        )


def _artifact_ref(path: Path, *, schema_version: str) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "schema_version": schema_version,
    }


def _write_generation_fitness_results(out: Path) -> Path:
    _write_json(
        out,
        {
            "schema_version": "gen-fitness-results-v1",
            "status": "fitness_passed",
            "rendered_state": "eligible_for_downstream_evidence_review",
            "cases": [],
        },
    )
    return out


def _write_program_evidence_adjudication(
    root: Path,
    out: Path,
    *,
    generation_fitness_results_path: Path,
) -> Path:
    manifest_path = root / "manifest.json"
    _write_json(
        out,
        {
            "schema_version": "program-evidence-adjudication-v1",
            "status": "evidence_adjudicated",
            "identity": _candidate_identity(root),
            "manifest": _artifact_ref(
                manifest_path,
                schema_version="program-candidate-assembly-v1",
            ),
            "evidence_refs": {
                "behavior": None,
                "oracle_report": None,
                "activation_packet": None,
                "generation_traceability": None,
                "generation_fitness_results": _artifact_ref(
                    generation_fitness_results_path,
                    schema_version="gen-fitness-results-v1",
                ),
            },
            "role_judgments": [
                {
                    "perspective": "target_protocol_fidelity",
                    "judgment": "supports_domain_review",
                    "missing_evidence": [],
                    "rationale": "target-fidelity result permits downstream evidence review only",
                    "activation_authority": False,
                    "model_backed": False,
                    "provider_called": False,
                }
            ],
            "aggregate": {
                "recommendation": "revise_or_collect_missing_evidence",
                "ready_for_domain_decision": False,
                "activation_approved": False,
                "judgment_counts": {"supports_domain_review": 1},
                "missing_evidence": [],
                "blocking_perspectives": [],
            },
            "non_authority": {
                "activation_authority": False,
                "promotion_authority": False,
                "oracle_authority": False,
                "governance_authority": False,
                "external_authority": False,
                "external_mutation": False,
            },
            "effect": {
                "candidate_files_mutated": False,
                "canonical_target_mutated": False,
                "ak_mutated": False,
                "governance_mutated": False,
                "oracle_index_mutated": False,
                "shared_oracle_mutated": False,
                "provider_called": False,
            },
        },
    )
    return out


def _write_target_aware_state_with_adjudication_refs(
    root: Path,
    out: Path,
    *,
    generation_fitness_results_path: Path,
    program_evidence_adjudication_path: Path,
) -> Path:
    _write_target_aware_candidate_state(root, out)
    state = json.loads(out.read_text(encoding="utf-8"))
    state["artifact_hashes"] = {
        **state.get("artifact_hashes", {}),
        "generation_fitness_results_sha256": hashlib.sha256(
            generation_fitness_results_path.read_bytes()
        ).hexdigest(),
        "program_evidence_adjudication_sha256": hashlib.sha256(
            program_evidence_adjudication_path.read_bytes()
        ).hexdigest(),
    }
    state.setdefault("truth_summary", {})["target_protocol_adjudication_present"] = True
    _write_json(out, state)
    return out


def test_program_promote_activation_packet_rejects_widened_jury_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, jury_path, review_path, decision_path = (
        _materialize_review_chain(tmp_path, monkeypatch)
    )
    jury = json.loads(jury_path.read_text(encoding="utf-8"))
    jury["non_authority"]["promotion_authority"] = True
    jury_path.write_text(json.dumps(jury, indent=2) + "\n", encoding="utf-8")

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
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "jury_results widens non-authority flags" in result.output
    assert "promotion_authority" in result.output


def test_program_promote_activation_packet_rejects_oracle_report_identity_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, jury_path, review_path, decision_path = (
        _materialize_review_chain(tmp_path, monkeypatch)
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["records"][0]["identity"]["candidate_id"] = "different-candidate"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

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
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert (
        "oracle_report does not contain a record matching candidate identity"
        in result.output
    )


def test_program_promote_activation_packet_rejects_wrong_decision_authority_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, jury_path, review_path, decision_path = (
        _materialize_review_chain(tmp_path, monkeypatch)
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
            "different-authority-owner",
            "--oracle-report",
            str(report_path),
            "--jury-results",
            str(jury_path),
            "--review",
            str(review_path),
            "--decision-record",
            str(decision_path),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert (
        "decision_record decided_by must match activation authority_owner"
        in result.output
    )


def test_program_promote_activation_packet_rejects_blocking_target_judgment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    candidate_state_path = _write_target_aware_candidate_state(
        program_root,
        tmp_path / "activation" / "program_candidate_state.json",
    )
    candidate_state = json.loads(candidate_state_path.read_text(encoding="utf-8"))
    judgment = candidate_state["target_fidelity_state"][
        "target_protocol_fidelity_judgment"
    ]
    judgment["blocking"] = True
    judgment["judgment"] = "needs_more_evidence"
    candidate_state_path.write_text(json.dumps(candidate_state, indent=2) + "\n")

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
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert (
        "target_protocol_fidelity_judgment must record blocking false" in result.output
    )


def test_program_promote_activation_packet_includes_program_evidence_adjudication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    fitness_path = _write_generation_fitness_results(
        tmp_path / "target" / "generation_fitness_results.json"
    )
    adjudication_path = _write_program_evidence_adjudication(
        program_root,
        tmp_path / "target" / "program_evidence_adjudication.json",
        generation_fitness_results_path=fitness_path,
    )
    candidate_state_path = _write_target_aware_state_with_adjudication_refs(
        program_root,
        tmp_path / "activation" / "program_candidate_state.json",
        generation_fitness_results_path=fitness_path,
        program_evidence_adjudication_path=adjudication_path,
    )

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
            "--generation-fitness-results",
            str(fitness_path),
            "--program-evidence-adjudication",
            str(adjudication_path),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert (
        payload["evidence"]["generation_fitness_results"]["sha256"]
        == hashlib.sha256(fitness_path.read_bytes()).hexdigest()
    )
    assert payload["evidence"]["program_evidence_adjudication"]["path"] == str(
        adjudication_path.resolve()
    )
    assert (
        payload["target_review_admission"]["production_activation_authority"] is False
    )
    assert payload["effect"]["production_activation_applied"] is False


def test_program_promote_activation_packet_rejects_stale_program_adjudication_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    fitness_path = _write_generation_fitness_results(
        tmp_path / "target" / "generation_fitness_results.json"
    )
    adjudication_path = _write_program_evidence_adjudication(
        program_root,
        tmp_path / "target" / "program_evidence_adjudication.json",
        generation_fitness_results_path=fitness_path,
    )
    candidate_state_path = _write_target_aware_state_with_adjudication_refs(
        program_root,
        tmp_path / "activation" / "program_candidate_state.json",
        generation_fitness_results_path=fitness_path,
        program_evidence_adjudication_path=adjudication_path,
    )
    adjudication = json.loads(adjudication_path.read_text(encoding="utf-8"))
    adjudication["evidence_refs"]["generation_fitness_results"]["sha256"] = "0" * 64
    _write_json(adjudication_path, adjudication)

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
            "--generation-fitness-results",
            str(fitness_path),
            "--program-evidence-adjudication",
            str(adjudication_path),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert (
        "generation_fitness_results ref sha256 does not match current evidence"
        in result.output
    )


def test_program_promote_activation_packet_rejects_program_adjudication_identity_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    fitness_path = _write_generation_fitness_results(
        tmp_path / "target" / "generation_fitness_results.json"
    )
    adjudication_path = _write_program_evidence_adjudication(
        program_root,
        tmp_path / "target" / "program_evidence_adjudication.json",
        generation_fitness_results_path=fitness_path,
    )
    candidate_state_path = _write_target_aware_state_with_adjudication_refs(
        program_root,
        tmp_path / "activation" / "program_candidate_state.json",
        generation_fitness_results_path=fitness_path,
        program_evidence_adjudication_path=adjudication_path,
    )
    adjudication = json.loads(adjudication_path.read_text(encoding="utf-8"))
    adjudication["identity"]["candidate_id"] = "wrong-candidate"
    _write_json(adjudication_path, adjudication)

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
            "--generation-fitness-results",
            str(fitness_path),
            "--program-evidence-adjudication",
            str(adjudication_path),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "identity does not match current manifest: candidate_id" in result.output


def test_program_promote_activation_packet_rejects_program_adjudication_authority_spoof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    fitness_path = _write_generation_fitness_results(
        tmp_path / "target" / "generation_fitness_results.json"
    )
    adjudication_path = _write_program_evidence_adjudication(
        program_root,
        tmp_path / "target" / "program_evidence_adjudication.json",
        generation_fitness_results_path=fitness_path,
    )
    candidate_state_path = _write_target_aware_state_with_adjudication_refs(
        program_root,
        tmp_path / "activation" / "program_candidate_state.json",
        generation_fitness_results_path=fitness_path,
        program_evidence_adjudication_path=adjudication_path,
    )
    adjudication = json.loads(adjudication_path.read_text(encoding="utf-8"))
    adjudication["non_authority"]["promotion_authority"] = True
    _write_json(adjudication_path, adjudication)

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
            "--generation-fitness-results",
            str(fitness_path),
            "--program-evidence-adjudication",
            str(adjudication_path),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "widens non-authority flags: promotion_authority" in result.output


def test_program_promote_activation_packet_rejects_candidate_state_adjudication_hash_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    fitness_path = _write_generation_fitness_results(
        tmp_path / "target" / "generation_fitness_results.json"
    )
    adjudication_path = _write_program_evidence_adjudication(
        program_root,
        tmp_path / "target" / "program_evidence_adjudication.json",
        generation_fitness_results_path=fitness_path,
    )
    candidate_state_path = _write_target_aware_state_with_adjudication_refs(
        program_root,
        tmp_path / "activation" / "program_candidate_state.json",
        generation_fitness_results_path=fitness_path,
        program_evidence_adjudication_path=adjudication_path,
    )
    state = json.loads(candidate_state_path.read_text(encoding="utf-8"))
    state["artifact_hashes"]["program_evidence_adjudication_sha256"] = "0" * 64
    _write_json(candidate_state_path, state)

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
            "--generation-fitness-results",
            str(fitness_path),
            "--program-evidence-adjudication",
            str(adjudication_path),
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert (
        "candidate_state program_evidence_adjudication hash does not match"
        in result.output
    )


def test_program_promote_activation_packet_rejects_evidence_missing_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root, report_path, jury_path, review_path, decision_path = (
        _materialize_review_chain(tmp_path, monkeypatch)
    )
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review.pop("identity", None)
    review_path.write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")

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
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "refined_review missing identity object" in result.output


def test_program_promote_activation_packet_rejects_behavior_hash_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    behavior = json.loads((program_root / "behavior_results.json").read_text())
    behavior["summary"]["status"] = "tampered"
    (program_root / "behavior_results.json").write_text(
        json.dumps(behavior, indent=2) + "\n",
        encoding="utf-8",
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
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert (
        "behavior_results.json hash does not match manifest declaration"
        in result.output
    )


def test_program_promote_activation_packet_rejects_corrupt_behavior_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program_root = _materialize_program(tmp_path, monkeypatch)
    (program_root / "behavior_results.json").write_text(
        json.dumps({"schema_version": "wrong"}) + "\n",
        encoding="utf-8",
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
            "--out",
            str(tmp_path / "activation" / "activation_packet.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "behavior_results.json schema_version" in result.output

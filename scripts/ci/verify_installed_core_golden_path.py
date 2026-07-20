#!/usr/bin/env python3
# ---
# summary: "Verifies the clean installed-wheel Core journey without trusting CLI success alone."
# read_when:
#   - "Changing the installed Core wheel golden path or its machine-checkable evidence contract."
# ---

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Mapping, cast

from installed_core_proof_contract import (
    EXPECTED_NORMALIZED_INTENT,
    GOLDEN_INTENT,
    verify_install_origin,
    validate_behavior_evidence,
    validate_oracle_evidence,
)

from installed_core_proof_io import (
    MAX_JSON_BYTES as MAX_JSON_BYTES,
    MAX_SQLITE_BYTES,
    InstalledCoreGoldenPathError,
    assert_relative_absent,
    json_artifact,
    open_root,
    read_bounded_bytes,
    read_bounded_json as read_bounded_json,
    root_still_names_descriptor,
    write_result_at,
)


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InstalledCoreGoldenPathError(f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def _expect(value: object, expected: object, label: str) -> None:
    if value != expected:
        raise InstalledCoreGoldenPathError(
            f"{label} drift: expected {expected!r}, observed {value!r}"
        )


def _validate_check_only_replay_claims(value: object) -> None:
    claims = _mapping(value, "replay.replay_claims")
    _expect(
        set(claims),
        {
            "schema_version",
            "mode",
            "dimensions",
            "release_claim_allowed",
            "authority",
        },
        "replay claim fields",
    )
    _expect(
        claims.get("schema_version"),
        "dspx-replay-claim-matrix-v1",
        "replay claim schema",
    )
    _expect(claims.get("mode"), "check_only", "replay claim mode")
    _expect(claims.get("release_claim_allowed"), False, "replay release claim")
    _expect(
        claims.get("authority"),
        {
            "release_authority": False,
            "promotion_authority": False,
            "activation_authority": False,
            "governance_authority": False,
            "external_authority": False,
        },
        "replay claim authority",
    )
    expected_dimensions = {
        "receipt_integrity_check": (
            "passed",
            "current_receipt_and_declared_artifact_bindings",
        ),
        "deterministic_regeneration": (
            "not_run",
            "fresh_producer_output_identity",
        ),
        "runtime_execution_reproduction": (
            "not_run",
            "fresh_receipt_bound_runtime_evidence_identity",
        ),
        "semantic_reproduction": (
            "not_evaluated",
            "independent_semantic_equivalence_evaluation",
        ),
        "quality_evaluation_reproduction": (
            "not_evaluated",
            "receipt_bound_quality_evaluation_identity_not_independent_approval",
        ),
    }
    dimensions = _mapping(claims.get("dimensions"), "replay claim dimensions")
    _expect(set(dimensions), set(expected_dimensions), "replay claim dimension names")
    for name, (status, evidence_level) in expected_dimensions.items():
        dimension = _mapping(dimensions.get(name), f"replay claim {name}")
        _expect(
            set(dimension),
            {"status", "evidence_level"},
            f"replay claim {name} fields",
        )
        _expect(dimension.get("status"), status, f"replay claim {name} status")
        _expect(
            dimension.get("evidence_level"),
            evidence_level,
            f"replay claim {name} evidence level",
        )


def _expect_path(value: object, expected: Path, label: str) -> None:
    _expect(value, str(expected), label)


def _verify_sqlite(
    root_descriptor: int,
    *,
    expected_run_id: str,
) -> None:
    raw = read_bounded_bytes(
        root_descriptor,
        Path("program/oracle/coordinates.db"),
        label="candidate-local Oracle index",
        limit=MAX_SQLITE_BYTES,
    )
    if not raw.startswith(b"SQLite format 3\x00"):
        raise InstalledCoreGoldenPathError(
            "candidate-local Oracle index is not a SQLite database"
        )
    connection = sqlite3.connect(":memory:")
    try:
        connection.deserialize(raw)
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity != ("ok",):
            raise InstalledCoreGoldenPathError(
                "candidate-local Oracle index integrity check failed"
            )
        rows = connection.execute(
            "SELECT run_id, run_kind, provider FROM coordinates ORDER BY run_id"
        ).fetchall()
    except sqlite3.DatabaseError as exc:
        raise InstalledCoreGoldenPathError(
            f"candidate-local Oracle index contract is invalid: {exc}"
        ) from exc
    finally:
        connection.close()
    expected = [(expected_run_id, "program-oracle-evidence", "program-gen")]
    if rows != expected:
        raise InstalledCoreGoldenPathError(
            f"candidate-local Oracle records drift: expected {expected!r}, observed {rows!r}"
        )


def _verify_artifacts(
    root_descriptor: int,
    *,
    journey_root: Path,
) -> dict[str, Any]:
    intent, intent_hash = json_artifact(
        root_descriptor, "intent.json", label="golden-path intent"
    )
    _expect(intent, GOLDEN_INTENT, "golden-path intent")
    loop, _ = json_artifact(
        root_descriptor, "program-loop-result.json", label="program loop result"
    )
    replay, _ = json_artifact(
        root_descriptor, "replay-check.json", label="receipt replay check"
    )
    manifest, manifest_hash = json_artifact(
        root_descriptor, "program/manifest.json", label="program manifest"
    )
    report, report_hash = json_artifact(
        root_descriptor,
        "program/program_oracle_report.json",
        label="program Oracle report",
    )
    state, _ = json_artifact(
        root_descriptor,
        "program/program_candidate_state.json",
        label="program candidate state",
    )
    receipt, _ = json_artifact(
        root_descriptor,
        "program/manifest.json.meta.json",
        label="program generation receipt",
    )
    oracle_evidence, oracle_evidence_hash = json_artifact(
        root_descriptor,
        "program/oracle_evidence.json",
        label="program Oracle evidence",
    )
    behavior_episode, behavior_episode_hash = json_artifact(
        root_descriptor,
        "program/behavior_episode.json",
        label="program behavior episode",
    )
    behavior_results, behavior_results_hash = json_artifact(
        root_descriptor,
        "program/behavior_results.json",
        label="program behavior results",
    )

    program_root = journey_root / "program"
    manifest_path = program_root / "manifest.json"
    receipt_path = program_root / "manifest.json.meta.json"
    report_path = program_root / "program_oracle_report.json"
    state_path = program_root / "program_candidate_state.json"
    index_path = program_root / "oracle/coordinates.db"

    _expect(loop.get("schema_version"), "program-loop-workflow-v2", "loop schema")
    _expect(loop.get("status"), "ok", "loop status")
    candidate = _mapping(loop.get("candidate"), "loop.candidate")
    assembly = _mapping(
        manifest.get("candidate_assembly"), "manifest.candidate_assembly"
    )
    receipt_bundle = _mapping(manifest.get("receipt_bundle"), "manifest.receipt_bundle")
    run_summary = _mapping(receipt.get("run_summary"), "receipt.run_summary")
    replay_inputs = _mapping(receipt.get("replay_inputs"), "receipt.replay_inputs")
    normalized_intent = _mapping(replay_inputs.get("intent"), "receipt replay intent")
    _expect(
        normalized_intent,
        EXPECTED_NORMALIZED_INTENT,
        "complete normalized receipt intent",
    )
    identity = _mapping(oracle_evidence.get("identity"), "oracle_evidence.identity")
    validate_behavior_evidence(
        episode=behavior_episode,
        results=behavior_results,
        results_hash=behavior_results_hash,
    )
    validate_oracle_evidence(
        oracle_evidence,
        expected_identity=identity,
        behavior_results_hash=behavior_results_hash,
    )
    for field in ("assembly_id", "candidate_id"):
        _expect(candidate.get(field), assembly.get(field), f"candidate {field}")
        _expect(identity.get(field), assembly.get(field), f"Oracle identity {field}")
    _expect(
        candidate.get("receipt_bundle_id"),
        receipt_bundle.get("receipt_bundle_id"),
        "candidate receipt bundle",
    )
    _expect(
        run_summary.get("receipt_bundle_id"),
        candidate.get("receipt_bundle_id"),
        "receipt summary bundle",
    )
    _expect(
        run_summary.get("behavior_episode_hash"),
        behavior_episode_hash,
        "receipt behavior episode hash",
    )
    _expect(
        run_summary.get("behavior_results_hash"),
        behavior_results_hash,
        "receipt behavior results hash",
    )
    _expect(
        identity.get("receipt_bundle_id"),
        candidate.get("receipt_bundle_id"),
        "Oracle identity receipt bundle",
    )
    _expect_path(candidate.get("root_path"), program_root, "candidate root")
    _expect_path(candidate.get("manifest_path"), manifest_path, "candidate manifest")
    _expect_path(candidate.get("receipt_path"), receipt_path, "candidate receipt")
    _expect_path(assembly.get("root_path"), program_root, "manifest candidate root")

    steps = _mapping(loop.get("steps"), "loop.steps")
    generation = _mapping(steps.get("program_gen"), "loop.steps.program_gen")
    behavior = _mapping(
        steps.get("behavior_evaluation"), "loop.steps.behavior_evaluation"
    )
    replay_step = _mapping(steps.get("replay_check"), "loop.steps.replay_check")
    oracle_index = _mapping(steps.get("oracle_index"), "loop.steps.oracle_index")
    oracle_result = _mapping(
        oracle_index.get("result"), "loop.steps.oracle_index.result"
    )
    oracle_report = _mapping(steps.get("oracle_report"), "loop.steps.oracle_report")
    candidate_state = _mapping(
        steps.get("candidate_state"), "loop.steps.candidate_state"
    )
    _expect(generation.get("status"), "ok", "program generation status")
    _expect(
        generation.get("materialization_status"),
        "materialized",
        "program materialization status",
    )
    _expect(behavior.get("status"), "passed", "behavior status")
    _expect(behavior.get("passed"), True, "behavior pass marker")
    _expect(replay_step.get("status"), "ok", "embedded replay-check status")
    _expect(oracle_index.get("status"), "ok", "Oracle index status")
    _expect_path(oracle_index.get("index_path"), index_path, "Oracle index path")
    _expect(oracle_result.get("indexed"), 1, "Oracle indexed record count")
    _expect(oracle_result.get("errors"), 0, "Oracle index error count")
    _expect(oracle_result.get("backend"), "mock", "Oracle embedding backend")
    _expect(oracle_report.get("status"), "ok", "Oracle report status")
    _expect_path(oracle_report.get("path"), report_path, "Oracle report path")
    if not candidate_state.get("status"):
        raise InstalledCoreGoldenPathError("candidate state status must be present")
    _expect_path(candidate_state.get("path"), state_path, "candidate state path")

    effect = _mapping(loop.get("effect"), "loop.effect")
    for field in (
        "shared_oracle_mutated",
        "ak_called",
        "external_authority_mutated",
        "governance_mutated",
        "promotion_applied",
        "winner_selected",
    ):
        _expect(effect.get(field), False, f"loop.effect.{field}")
    _expect(
        effect.get("oracle_index_scope"),
        "candidate-local explicit path",
        "Oracle index scope",
    )
    non_authority = _mapping(loop.get("non_authority"), "loop.non_authority")
    _expect(
        non_authority.get("promotion_authority"),
        False,
        "loop promotion authority",
    )

    _expect(replay.get("status"), "ok", "explicit replay-check status")
    _expect_path(replay.get("receipt_path"), receipt_path, "replay receipt path")
    _expect_path(replay.get("output_path"), manifest_path, "replay output path")
    _expect(replay.get("receipt_hash"), manifest_hash, "replay receipt hash")
    _expect(replay.get("actual_output_hash"), manifest_hash, "replay output hash")
    replay_checks = _mapping(replay.get("checks"), "replay.checks")
    if not replay_checks or any(value is not True for value in replay_checks.values()):
        raise InstalledCoreGoldenPathError("explicit replay checks must all pass")
    _expect(replay.get("errors"), [], "replay errors")
    _validate_check_only_replay_claims(replay.get("replay_claims"))

    _expect(receipt.get("receipt_version"), "v2", "receipt version")
    _expect(receipt.get("run_kind"), "program-gen", "receipt run kind")
    _expect(receipt.get("provider"), "stub", "receipt provider")
    _expect_path(receipt.get("output_path"), manifest_path, "receipt output path")
    _expect(receipt.get("hash"), manifest_hash, "receipt manifest hash")

    _expect(
        report.get("schema_version"),
        "program-oracle-evidence-report-v1",
        "report schema",
    )
    _expect(report.get("status"), "ok", "report status")
    _expect(report.get("total_records"), 1, "report record count")
    _expect_path(report.get("index_path"), index_path, "report index path")
    records = report.get("records")
    if not isinstance(records, list) or len(records) != 1:
        raise InstalledCoreGoldenPathError("Oracle report must contain one record")
    record = _mapping(records[0], "report.records[0]")
    _expect(record.get("identity"), identity, "report Oracle identity")
    _expect(
        record.get("run_id"),
        f"program-oracle-evidence:{identity['receipt_bundle_id']}",
        "report run ID",
    )
    _expect(
        record.get("evidence_hash"),
        oracle_evidence_hash,
        "report Oracle evidence hash",
    )
    _expect_path(
        record.get("evidence_path"),
        program_root / "oracle_evidence.json",
        "report Oracle evidence path",
    )
    report_non_authority = _mapping(report.get("non_authority"), "report.non_authority")
    for field in (
        "oracle_ranking",
        "oracle_pruning",
        "oracle_promotion",
        "governance_authority",
        "external_mutation",
    ):
        _expect(
            report_non_authority.get(field),
            False,
            f"report.non_authority.{field}",
        )

    _expect(state.get("schema_version"), "program-candidate-state-v1", "state schema")
    created_from = _mapping(state.get("created_from"), "state.created_from")
    hashes = _mapping(state.get("artifact_hashes"), "state.artifact_hashes")
    _expect_path(created_from.get("manifest_path"), manifest_path, "state manifest")
    _expect_path(created_from.get("oracle_report_path"), report_path, "state report")
    _expect(hashes.get("manifest_sha256"), manifest_hash, "state manifest hash")
    _expect(hashes.get("oracle_report_sha256"), report_hash, "state report hash")
    _expect(
        hashes.get("oracle_evidence_sha256"),
        oracle_evidence_hash,
        "state Oracle evidence hash",
    )
    _expect(
        behavior.get("sha256"),
        behavior_episode_hash,
        "workflow behavior episode hash",
    )
    _expect(
        hashes.get("behavior_episode_sha256"),
        behavior_episode_hash,
        "state behavior episode hash",
    )
    _expect(
        hashes.get("behavior_results_sha256"),
        behavior_results_hash,
        "state behavior results hash",
    )
    truth = _mapping(state.get("truth_summary"), "state.truth_summary")
    for field, expected in (
        ("program_materialized", True),
        ("behavior_evidence_present", True),
        ("oracle_report_present", True),
        ("promotion_applied", False),
        ("ak_called", False),
        ("governance_mutated", False),
        ("external_authority_mutated", False),
        ("winner_selected", False),
        ("oracle_publication_ref_present", False),
    ):
        _expect(truth.get(field), expected, f"state truth {field}")

    expected_run_id = f"program-oracle-evidence:{identity['receipt_bundle_id']}"
    _verify_sqlite(root_descriptor, expected_run_id=expected_run_id)

    return {
        "schema_version": "dspx-installed-core-golden-path-proof-v1",
        "status": "passed",
        "provider": "stub",
        "oracle_embedding_backend": "mock",
        "oracle_semantic_claim": "plumbing_only_not_production_semantics",
        "behavior_status": "passed",
        "receipt_check_status": "ok",
        "replay_claim_matrix_schema": "dspx-replay-claim-matrix-v1",
        "candidate_identity": dict(identity),
        "evidence_hashes": {
            "manifest_sha256": manifest_hash,
            "intent_sha256": intent_hash,
            "behavior_episode_sha256": behavior_episode_hash,
            "behavior_results_sha256": behavior_results_hash,
            "oracle_evidence_sha256": oracle_evidence_hash,
            "oracle_report_sha256": report_hash,
        },
        "oracle_record_count": 1,
        "workflow_declared_effects": {
            "shared_oracle_mutated": False,
            "ak_called": False,
            "governance_mutated": False,
            "external_authority_mutated": False,
            "promotion_applied": False,
            "winner_selected": False,
        },
        "non_authority": {
            "release_readiness": False,
            "live_provider_proof": False,
            "semantic_quality_approval": False,
            "network_isolation_proven": False,
            "absolute_path_external_effects_excluded": False,
            "promotion_authority": False,
            "activation_authority": False,
        },
    }


def verify_artifacts(journey_root: Path) -> dict[str, Any]:
    """Public test helper retaining one root descriptor for the complete read set."""

    root = journey_root.absolute()
    root_descriptor = open_root(root)
    try:
        return _verify_artifacts(root_descriptor, journey_root=root)
    finally:
        os.close(root_descriptor)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--journey-root", type=Path, required=True)
    parser.add_argument("--venv-root", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    args = parser.parse_args()

    journey_root = args.journey_root.absolute()
    install = verify_install_origin(
        venv_root=args.venv_root.absolute(), repo_root=args.repo_root.absolute()
    )
    root_descriptor = open_root(journey_root)
    try:
        proof = _verify_artifacts(root_descriptor, journey_root=journey_root)
        proof["install"] = install
        root_still_names_descriptor(journey_root, root_descriptor)
        assert_relative_absent(
            root_descriptor,
            "ak-called",
            label="PATH-resolved AK canary marker",
        )
        proof["independent_effect_observations"] = {
            "path_resolved_ak_canary_invoked": False,
        }
        write_result_at(
            root_descriptor,
            "installed-core-golden-path-proof.json",
            proof,
        )
    finally:
        os.close(root_descriptor)
    print(json.dumps(proof, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except InstalledCoreGoldenPathError as exc:
        raise SystemExit(
            f"installed Core golden path verification failed: {exc}"
        ) from exc

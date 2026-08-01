# summary: "Validates bounded artifacts and nonclaims for the installed-wheel live semantic journey."
# read_when:
#   - "Changing installed-wheel live semantic artifact bindings, replay claims, or Oracle evidence."

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, cast

from installed_core_live_semantic_oracle import verify_oracle_sqlite
from installed_core_live_semantic_scoring import verify_semantic_case
from installed_core_proof_io import (
    InstalledCoreGoldenPathError,
    assert_relative_absent,
    json_artifact,
    open_root,
    root_still_names_descriptor,
)

CASE_ID = "single-module-authority-boundary"
PROOF_SCHEMA = "dspx-installed-core-live-semantic-proof-v1"
EXPECTED_CASE_SHA256 = (
    "64105f9a7743f0c145af1d6b3d14057177c42fd71349af693f32d20fad715aeb"
)
EXPECTED_AUTH_WHEEL_SHA256 = (
    "67102c73bf20e2e5736ae65fba4aff05c7d8a8f6a5dec302ea71c78bf097491f"
)


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InstalledCoreGoldenPathError(f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def _sequence(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise InstalledCoreGoldenPathError(f"{label} must be an array")
    return value


def _expect(value: object, expected: object, label: str) -> None:
    if value != expected:
        raise InstalledCoreGoldenPathError(
            f"{label} drift: expected {expected!r}, observed {value!r}"
        )


def _sha256_value(value: object) -> str:
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _false_fields(value: object, fields: tuple[str, ...], label: str) -> None:
    payload = _mapping(value, label)
    for field in fields:
        _expect(payload.get(field), False, f"{label}.{field}")


def _artifact_hash(
    root_descriptor: int, relative: str, *, label: str
) -> tuple[dict[str, Any], str]:
    return json_artifact(root_descriptor, relative, label=label)


def verify_journey_artifacts(
    journey_root: Path, *, provider: str, requested_model: str
) -> dict[str, Any]:
    """Verify one already-materialized bounded journey using descriptor-confined reads."""
    root = journey_root.absolute()
    root_descriptor = open_root(root)
    try:
        corpus, _corpus_file_hash = _artifact_hash(
            root_descriptor, "corpus.json", label="single-case corpus"
        )
        _expect(
            corpus.get("schema_version"),
            "dspx-program-semantic-benchmark-corpus-v2",
            "corpus schema",
        )
        cases = _sequence(corpus.get("cases"), "corpus cases")
        _expect(len(cases), 1, "corpus case count")
        case = _mapping(cases[0], "corpus case")
        _expect(case.get("id"), CASE_ID, "corpus case id")
        _expect(
            _sha256_value(case),
            EXPECTED_CASE_SHA256,
            "exact checked-in semantic case hash",
        )

        result, result_hash = _artifact_hash(
            root_descriptor, "benchmark-result.json", label="benchmark result"
        )
        _expect(
            result.get("schema_version"),
            "dspx-program-semantic-benchmark-result-v2",
            "benchmark schema",
        )
        execution = _mapping(result.get("execution"), "benchmark execution")
        _expect(execution.get("mode"), "live", "benchmark mode")
        _expect(execution.get("provider"), provider, "benchmark provider")
        _expect(execution.get("network_allowed"), True, "benchmark network posture")
        _expect(execution.get("deterministic"), False, "benchmark determinism")
        _expect(execution.get("generated_program_path"), True, "generated program path")
        _expect(
            execution.get("oracle_indexed"), False, "benchmark internal Oracle posture"
        )
        corpus_identity = _mapping(result.get("corpus"), "benchmark corpus identity")
        _expect(
            corpus_identity.get("sha256"),
            _sha256_value(corpus),
            "benchmark corpus hash",
        )
        summary = _mapping(result.get("summary"), "benchmark summary")
        _expect(summary.get("cases_total"), 1, "benchmark cases_total")
        _expect(summary.get("cases_passed"), 1, "benchmark cases_passed")
        _expect(summary.get("cases_failed"), 0, "benchmark cases_failed")
        _expect(summary.get("overall_score"), 1.0, "benchmark overall score")
        _expect(summary.get("threshold_pass"), True, "benchmark threshold")
        rows = _sequence(result.get("cases"), "benchmark case rows")
        _expect(len(rows), 1, "benchmark row count")
        row = _mapping(rows[0], "benchmark row")
        _expect(row.get("id"), CASE_ID, "benchmark row id")
        _expect(row.get("status"), "passed", "benchmark row status")
        _expect(row.get("score"), 1.0, "benchmark row score")
        _expect(row.get("error"), None, "benchmark row error")
        _expect(row.get("runtime_replay_status"), "not_required", "case runtime replay")
        _false_fields(
            result.get("authority"),
            (
                "authoritative_decision",
                "promotion_approved",
                "activation_applied",
                "shared_oracle_mutated",
                "external_authority_mutated",
                "governance_mutated",
                "ak_called",
                "winner_selected",
            ),
            "benchmark authority",
        )

        candidate = _mapping(row.get("candidate"), "candidate identity")
        artifacts = _mapping(row.get("artifacts"), "benchmark artifact hashes")
        candidate_root = f"benchmark/{CASE_ID}"
        manifest, manifest_hash = _artifact_hash(
            root_descriptor,
            f"{candidate_root}/manifest.json",
            label="candidate manifest",
        )
        receipt, receipt_hash = _artifact_hash(
            root_descriptor,
            f"{candidate_root}/manifest.json.meta.json",
            label="candidate receipt",
        )
        behavior, behavior_hash = _artifact_hash(
            root_descriptor,
            f"{candidate_root}/behavior_results.json",
            label="behavior results",
        )
        episode, episode_hash = _artifact_hash(
            root_descriptor,
            f"{candidate_root}/behavior_episode.json",
            label="behavior episode",
        )
        oracle_evidence, oracle_evidence_hash = _artifact_hash(
            root_descriptor,
            f"{candidate_root}/oracle_evidence.json",
            label="Oracle evidence",
        )
        workflow, workflow_hash = _artifact_hash(
            root_descriptor,
            f"{candidate_root}/program_loop.json",
            label="program-loop result",
        )
        expected_hashes = {
            "manifest_sha256": manifest_hash,
            "receipt_sha256": receipt_hash,
            "behavior_results_sha256": behavior_hash,
            "behavior_episode_sha256": episode_hash,
            "workflow_sha256": workflow_hash,
        }
        for field, expected in expected_hashes.items():
            _expect(artifacts.get(field), expected, f"benchmark artifacts.{field}")

        assembly = _mapping(
            manifest.get("candidate_assembly"), "manifest candidate assembly"
        )
        receipt_bundle = _mapping(
            manifest.get("receipt_bundle"), "manifest receipt bundle"
        )
        _expect(
            candidate.get("assembly_id"), assembly.get("assembly_id"), "assembly id"
        )
        _expect(
            candidate.get("candidate_id"), assembly.get("candidate_id"), "candidate id"
        )
        _expect(
            candidate.get("receipt_bundle_id"),
            receipt_bundle.get("receipt_bundle_id"),
            "receipt bundle id",
        )
        _expect(receipt.get("run_kind"), "program-gen", "receipt run kind")

        behavior_summary = _mapping(behavior.get("summary"), "behavior summary")
        _expect(behavior_summary.get("status"), "passed", "behavior status")
        _expect(behavior_summary.get("total"), 1, "behavior total")
        _expect(behavior_summary.get("passed"), 1, "behavior passed")
        semantic_score = verify_semantic_case(
            case=case,
            behavior=behavior,
            row=row,
        )
        provider_identity = _mapping(behavior.get("provider"), "behavior provider")
        provider_name = str(provider_identity.get("provider", ""))
        if provider_name != provider and not provider_name.startswith(f"{provider}/"):
            raise InstalledCoreGoldenPathError(
                "behavior provider is not the selected live route"
            )
        _expect(episode.get("status"), "passed", "behavior episode status")
        _false_fields(
            behavior.get("non_authority"),
            (
                "external_authority_mutated",
                "external_mutation",
                "governance_authority",
                "optimization_authority",
                "oracle_promotion",
                "oracle_pruning",
                "oracle_ranking",
                "promotion_authority",
                "winner_selection",
            ),
            "behavior non-authority",
        )
        oracle_behavior = _mapping(
            oracle_evidence.get("behavior"), "Oracle evidence behavior"
        )
        oracle_behavior_summary = _mapping(
            oracle_behavior.get("summary"), "Oracle evidence behavior summary"
        )
        _expect(
            oracle_behavior_summary.get("status"),
            "passed",
            "Oracle evidence behavior status",
        )
        _expect(
            oracle_behavior.get("result_hash"),
            behavior_hash,
            "Oracle evidence behavior hash",
        )

        _expect(workflow.get("status"), "ok", "program-loop status")
        _false_fields(
            workflow.get("effect"),
            (
                "ak_called",
                "external_authority_mutated",
                "governance_mutated",
                "promotion_applied",
                "shared_oracle_mutated",
                "winner_selected",
            ),
            "program-loop effect",
        )

        replay, replay_hash = _artifact_hash(
            root_descriptor, "replay-check.json", label="replay check"
        )
        _expect(replay.get("status"), "ok", "replay status")
        _expect(replay.get("error_codes"), [], "replay errors")
        replay_claims = _mapping(replay.get("replay_claims"), "replay claims")
        dimensions = _mapping(replay_claims.get("dimensions"), "replay dimensions")
        expected_dimensions = {
            "receipt_integrity_check": "passed",
            "deterministic_regeneration": "not_run",
            "runtime_execution_reproduction": "not_run",
            "semantic_reproduction": "not_evaluated",
            "quality_evaluation_reproduction": "not_evaluated",
        }
        for name, status in expected_dimensions.items():
            _expect(
                _mapping(dimensions.get(name), f"replay dimension {name}").get(
                    "status"
                ),
                status,
                f"replay dimension {name}",
            )
        _expect(
            replay_claims.get("release_claim_allowed"), False, "replay release claim"
        )
        _false_fields(
            replay_claims.get("authority"),
            (
                "release_authority",
                "promotion_authority",
                "activation_authority",
                "governance_authority",
                "external_authority",
            ),
            "replay authority",
        )

        oracle_index, oracle_index_hash = _artifact_hash(
            root_descriptor, "oracle-index-result.json", label="Oracle index result"
        )
        _expect(oracle_index.get("scanned"), 1, "Oracle scanned")
        _expect(oracle_index.get("indexed"), 1, "Oracle indexed")
        _expect(oracle_index.get("errors"), 0, "Oracle errors")
        _expect(oracle_index.get("backend"), "mock", "Oracle backend")
        _expect(
            oracle_index.get("semantic_claim"),
            "plumbing_only_not_production_semantics",
            "Oracle semantic claim",
        )
        _expect(
            oracle_index.get("production_semantic_claim_allowed"),
            False,
            "Oracle production claim",
        )
        _expect(
            oracle_index.get("non_authority_confirmed"), True, "Oracle non-authority"
        )
        oracle_report, oracle_report_hash = _artifact_hash(
            root_descriptor, "oracle-report.json", label="Oracle report"
        )
        _expect(
            oracle_report.get("schema_version"),
            "program-oracle-evidence-report-v1",
            "Oracle report schema",
        )
        _expect(oracle_report.get("status"), "ok", "Oracle report status")
        _expect(oracle_report.get("total_records"), 1, "Oracle report records")
        _false_fields(
            oracle_report.get("non_authority"),
            (
                "oracle_ranking",
                "oracle_pruning",
                "oracle_promotion",
                "governance_authority",
                "external_mutation",
            ),
            "Oracle report non-authority",
        )
        verify_oracle_sqlite(
            root_descriptor,
            receipt_bundle_id=str(candidate["receipt_bundle_id"]),
            behavior_results_sha256=behavior_hash,
        )

        runtime, runtime_hash = _artifact_hash(
            root_descriptor, "runtime-environment.json", label="runtime environment"
        )
        _expect(runtime.get("provider"), provider, "runtime provider")
        _expect(
            runtime.get("requested_model"), requested_model, "runtime requested model"
        )
        _expect(
            runtime.get("resolved_model_identity"),
            "not_proven",
            "resolved model posture",
        )
        _expect(runtime.get("pythonpath_unset"), True, "runtime PYTHONPATH posture")
        _expect(runtime.get("auth_store_nonmutation_proven"), False, "auth-store claim")
        _expect(runtime.get("network_isolation_proven"), False, "network claim")
        _expect(
            runtime.get("dspy_lm_auth_wheel_sha256"),
            EXPECTED_AUTH_WHEEL_SHA256,
            "released auth wheel hash",
        )
        _expect(
            runtime.get("dspx_stream_compatibility_retry_enabled"),
            False,
            "DSPx stream compatibility retry posture",
        )
        _expect(
            runtime.get("provider_internal_retry_behavior"),
            "not_proven",
            "provider internal retry posture",
        )
        _expect(
            runtime.get("unbounded_raw_provider_response_retained"),
            False,
            "unbounded provider response retention",
        )
        _expect(
            runtime.get("bounded_benchmark_behavior_output_retained"),
            True,
            "bounded benchmark output retention",
        )
        attempt, attempt_hash = _artifact_hash(
            root_descriptor, "provider-attempt.json", label="provider attempt"
        )
        _expect(
            attempt.get("benchmark_invocation_count"), 1, "benchmark invocation count"
        )
        _expect(attempt.get("disposition"), "passed", "benchmark attempt disposition")
        _expect(
            attempt.get("dspx_stream_compatibility_retry_enabled"),
            False,
            "attempt DSPx compatibility retry",
        )
        _expect(
            attempt.get("provider_internal_retry_behavior"),
            "not_proven",
            "attempt provider internal retry",
        )
        _expect(attempt.get("separate_health_probe_run"), False, "health probe posture")
        _expect(attempt.get("mechanical_retry_run"), False, "mechanical retry posture")
        assert_relative_absent(
            root_descriptor, "ak-called", label="PATH-resolved AK canary marker"
        )
        root_still_names_descriptor(root, root_descriptor)
        return {
            "schema_version": PROOF_SCHEMA,
            "status": "passed",
            "case_id": CASE_ID,
            "provider": provider,
            "requested_model": requested_model,
            "resolved_model_identity": "not_proven",
            "behavior_status": "passed",
            "semantic_score": semantic_score,
            "receipt_check_status": "ok",
            "oracle_embedding_backend": "mock",
            "oracle_semantic_claim": "plumbing_only_not_production_semantics",
            "candidate_identity": dict(candidate),
            "evidence_hashes": {
                "benchmark_result_sha256": result_hash,
                "manifest_sha256": manifest_hash,
                "receipt_sha256": receipt_hash,
                "behavior_results_sha256": behavior_hash,
                "behavior_episode_sha256": episode_hash,
                "oracle_evidence_sha256": oracle_evidence_hash,
                "workflow_sha256": workflow_hash,
                "replay_check_sha256": replay_hash,
                "oracle_index_result_sha256": oracle_index_hash,
                "oracle_report_sha256": oracle_report_hash,
                "runtime_environment_sha256": runtime_hash,
                "provider_attempt_sha256": attempt_hash,
            },
            "replay_claims": expected_dimensions,
            "oracle_record_count": 1,
            "effect": {
                "network_read_possible": True,
                "provider_owned_auth_refresh_possible": True,
                "candidate_local_oracle_mutated": True,
                "shared_oracle_mutated": False,
                "workflow_declared_ak_called": False,
                "ak_path_canary_observation": "not_observed",
                "broad_ak_invocation_absence_proven": False,
                "governance_mutated": False,
                "external_authority_mutated": False,
                "promotion_applied": False,
                "package_published": False,
            },
            "nonclaims": {
                "runtime_execution_reproduction": "not_run",
                "semantic_reproduction": "not_evaluated",
                "quality_evaluation_reproduction": "not_evaluated",
                "production_semantic_oracle_quality": False,
                "network_isolation_proven": False,
                "auth_store_nonmutation_proven": False,
                "exact_resolved_model_identity_proven": False,
                "broad_ak_invocation_absence_proven": False,
                "release_authority": False,
                "package_publication": False,
                "sdist_supported": False,
            },
        }
    finally:
        os.close(root_descriptor)

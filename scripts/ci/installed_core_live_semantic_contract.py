# summary: "Validates bounded three-strata artifacts and nonclaims for the installed-wheel live semantic journey."
# read_when:
#   - "Changing installed-wheel live semantic artifact bindings, replay claims, or Oracle evidence."

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, cast

from installed_core_live_semantic_oracle import verify_oracle_sqlite
from installed_core_live_semantic_scoring import verify_case_artifacts
from installed_core_proof_io import (
    InstalledCoreGoldenPathError,
    assert_relative_absent,
    json_artifact,
    open_root,
    root_still_names_descriptor,
)

CASE_IDS = (
    "single-module-authority-boundary",
    "pipeline-evidence-calibration",
    "pdf-transition-review-runtime-replay",
)
CASE_SHA256 = {
    "single-module-authority-boundary": "64105f9a7743f0c145af1d6b3d14057177c42fd71349af693f32d20fad715aeb",
    "pipeline-evidence-calibration": "56d8a9dc8b41f6e357f41a6f1357ab58ca00c342f54335e88f6f1eb86d1b1493",
    "pdf-transition-review-runtime-replay": "c189e6a0d4a98e781418cf1e05aadafc1c0e90177f62063fcacc12b97c3ad2e7",
}
PROOF_SCHEMA = "dspx-installed-core-live-semantic-proof-v2"
EXPECTED_CORPUS_FILE_SHA256 = (
    "4c877c7992d8b70044645c57e2753ea9f170da027179376cafbc4d6000db0ec9"
)
EXPECTED_EVALUATION_CONTRACT_FILE_SHA256 = (
    "9ff735cd4ba29cfe430c9bce12d697877fa18a91cff78bd98defedcdeed5201a"
)
EXPECTED_AUTH_WHEEL_SHA256 = (
    "ea24c9534fa80c30fc3f3c95f522c36931b67a0b820e275b1de5b2db714931c6"
)


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InstalledCoreGoldenPathError(f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def _sequence(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise InstalledCoreGoldenPathError(f"{label} must be an array")
    return value


def _same_typed_value(value: object, expected: object) -> bool:
    if type(value) is not type(expected):
        return False
    if isinstance(expected, dict):
        if not isinstance(value, dict):
            return False
        observed = cast(dict[object, object], value)
        required = cast(dict[object, object], expected)
        return observed.keys() == required.keys() and all(
            _same_typed_value(observed[key], item) for key, item in required.items()
        )
    if isinstance(expected, list):
        if not isinstance(value, list):
            return False
        return len(value) == len(expected) and all(
            _same_typed_value(left, right)
            for left, right in zip(value, expected, strict=True)
        )
    return value == expected


def _expect(value: object, expected: object, label: str) -> None:
    if not _same_typed_value(value, expected):
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


def _verify_case(
    root_descriptor: int,
    *,
    case: Mapping[str, Any],
    row: Mapping[str, Any],
    provider: str,
    requested_model: str,
) -> tuple[dict[str, Any], dict[str, str], dict[str, str]]:
    return verify_case_artifacts(
        root_descriptor,
        case=case,
        row=row,
        provider=provider,
        requested_model=requested_model,
    )


def verify_journey_artifacts(
    journey_root: Path, *, provider: str, requested_model: str
) -> dict[str, Any]:
    """Verify one already-materialized three-strata journey with confined reads."""

    root = journey_root.absolute()
    root_descriptor = open_root(root)
    try:
        corpus, corpus_file_hash = _artifact_hash(
            root_descriptor, "corpus.json", label="three-strata corpus"
        )
        _expect(corpus_file_hash, EXPECTED_CORPUS_FILE_SHA256, "exact corpus file hash")
        _expect(
            corpus.get("schema_version"),
            "dspx-program-semantic-benchmark-corpus-v2",
            "corpus schema",
        )
        cases = _sequence(corpus.get("cases"), "corpus cases")
        _expect(
            [case.get("id") for case in cases if isinstance(case, Mapping)],
            list(CASE_IDS),
            "corpus case order",
        )
        case_by_id: dict[str, Mapping[str, Any]] = {}
        for raw_case, case_id in zip(cases, CASE_IDS, strict=True):
            case = _mapping(raw_case, f"corpus case {case_id}")
            _expect(
                _sha256_value(case),
                CASE_SHA256[case_id],
                f"{case_id} exact checked-in case hash",
            )
            case_by_id[case_id] = case

        evaluation_contract, evaluation_contract_hash = _artifact_hash(
            root_descriptor,
            "evaluation-contract.json",
            label="precommitted evaluation contract",
        )
        _expect(
            evaluation_contract_hash,
            EXPECTED_EVALUATION_CONTRACT_FILE_SHA256,
            "evaluation contract file hash",
        )
        live_route = _mapping(
            evaluation_contract.get("live_route"), "evaluation contract live route"
        )
        _expect(
            live_route.get("provider"),
            provider,
            "evaluation contract provider",
        )
        _expect(
            live_route.get("requested_model"),
            requested_model,
            "evaluation contract requested model",
        )
        _expect(
            _mapping(evaluation_contract.get("attempt_budget"), "attempt budget").get(
                "case_execution_order"
            ),
            list(CASE_IDS),
            "evaluation contract case order",
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
        for field, expected in {
            "mode": "live",
            "provider": provider,
            "network_allowed": True,
            "deterministic": False,
            "generated_program_path": True,
            "oracle_indexed": False,
        }.items():
            _expect(execution.get(field), expected, f"benchmark execution.{field}")
        _expect(
            _mapping(result.get("corpus"), "benchmark corpus identity").get("sha256"),
            _sha256_value(corpus),
            "benchmark corpus hash",
        )
        _expect(
            result.get("thresholds"),
            {"min_overall_score": 1.0, "min_case_score": 1.0, "max_failed_cases": 0},
            "benchmark thresholds",
        )
        summary = _mapping(result.get("summary"), "benchmark summary")
        for field, expected in {
            "cases_total": 3,
            "cases_passed": 3,
            "cases_failed": 0,
            "overall_score": 1.0,
            "threshold_pass": True,
        }.items():
            _expect(summary.get(field), expected, f"benchmark summary.{field}")
        rows = _sequence(result.get("cases"), "benchmark case rows")
        _expect(
            [row.get("id") for row in rows if isinstance(row, Mapping)],
            list(CASE_IDS),
            "benchmark case order",
        )
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

        case_results: list[dict[str, Any]] = []
        replay_claims_by_case: dict[str, dict[str, str]] = {}
        oracle_records: dict[str, str] = {}
        for raw_row, case_id in zip(rows, CASE_IDS, strict=True):
            case_result, replay_claims, case_oracle_records = _verify_case(
                root_descriptor,
                case=case_by_id[case_id],
                row=_mapping(raw_row, f"benchmark row {case_id}"),
                provider=provider,
                requested_model=requested_model,
            )
            case_results.append(case_result)
            replay_claims_by_case[case_id] = replay_claims
            for receipt_bundle_id, behavior_hash in case_oracle_records.items():
                if receipt_bundle_id in oracle_records:
                    raise InstalledCoreGoldenPathError(
                        "candidate receipt bundle identities must be unique"
                    )
                oracle_records[receipt_bundle_id] = behavior_hash
        candidate_identity_tuples = {
            tuple(
                str(case["candidate_identity"][field])
                for field in ("assembly_id", "candidate_id", "receipt_bundle_id")
            )
            for case in case_results
        }
        _expect(len(candidate_identity_tuples), 3, "candidate identity uniqueness")

        oracle_index, oracle_index_hash = _artifact_hash(
            root_descriptor, "oracle-index-result.json", label="Oracle index result"
        )
        for field, expected in {
            "scanned": 3,
            "indexed": 3,
            "errors": 0,
            "backend": "mock",
            "semantic_claim": "plumbing_only_not_production_semantics",
            "production_semantic_claim_allowed": False,
            "non_authority_confirmed": True,
        }.items():
            _expect(oracle_index.get(field), expected, f"Oracle index.{field}")
        oracle_report, oracle_report_hash = _artifact_hash(
            root_descriptor, "oracle-report.json", label="Oracle report"
        )
        _expect(
            oracle_report.get("schema_version"),
            "program-oracle-evidence-report-v1",
            "Oracle report schema",
        )
        _expect(oracle_report.get("status"), "ok", "Oracle report status")
        _expect(oracle_report.get("total_records"), 3, "Oracle report records")
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
        verify_oracle_sqlite(root_descriptor, expected_records=oracle_records)

        runtime, runtime_hash = _artifact_hash(
            root_descriptor, "runtime-environment.json", label="runtime environment"
        )
        for field, expected in {
            "provider": provider,
            "requested_model": requested_model,
            "resolved_model_identity": "not_proven",
            "pythonpath_unset": True,
            "auth_store_nonmutation_proven": False,
            "network_isolation_proven": False,
            "dspy_lm_auth_wheel_sha256": EXPECTED_AUTH_WHEEL_SHA256,
            "dspx_stream_compatibility_retry_enabled": False,
            "provider_internal_retry_behavior": "not_proven",
            "unbounded_raw_provider_response_retained": False,
            "bounded_benchmark_behavior_output_retained": True,
        }.items():
            _expect(runtime.get(field), expected, f"runtime {field}")
        attempt, attempt_hash = _artifact_hash(
            root_descriptor, "provider-attempt.json", label="provider attempt"
        )
        expected_attempt_fields = {
            "schema_version",
            "benchmark_invocation_count",
            "disposition",
            "dspx_stream_compatibility_retry_enabled",
            "provider_internal_retry_behavior",
            "separate_health_probe_run",
            "mechanical_retry_run",
            "selective_quality_rerun_allowed",
            "case_execution_order",
        }
        _expect(set(attempt), expected_attempt_fields, "provider attempt fields")
        _expect(
            attempt.get("schema_version"),
            "dspx-installed-core-live-attempt-v2",
            "provider attempt schema",
        )
        for field, expected in {
            "benchmark_invocation_count": 1,
            "disposition": "passed",
            "dspx_stream_compatibility_retry_enabled": False,
            "provider_internal_retry_behavior": "not_proven",
            "separate_health_probe_run": False,
            "mechanical_retry_run": False,
            "selective_quality_rerun_allowed": False,
            "case_execution_order": list(CASE_IDS),
        }.items():
            _expect(attempt.get(field), expected, f"provider attempt {field}")
        assert_relative_absent(
            root_descriptor, "ak-called", label="PATH-resolved AK canary marker"
        )
        root_still_names_descriptor(root, root_descriptor)
        return {
            "schema_version": PROOF_SCHEMA,
            "status": "passed",
            "coverage_claim": "declared_strata_only_not_statistically_representative",
            "case_order": list(CASE_IDS),
            "cases": case_results,
            "aggregate_semantic_score": 1.0,
            "provider": provider,
            "requested_model": requested_model,
            "resolved_model_identity": "not_proven",
            "replay_claims_by_case": replay_claims_by_case,
            "oracle_embedding_backend": "mock",
            "oracle_semantic_claim": "plumbing_only_not_production_semantics",
            "oracle_record_count": 3,
            "evidence_hashes": {
                "corpus_sha256": corpus_file_hash,
                "evaluation_contract_sha256": evaluation_contract_hash,
                "benchmark_result_sha256": result_hash,
                "oracle_index_result_sha256": oracle_index_hash,
                "oracle_report_sha256": oracle_report_hash,
                "runtime_environment_sha256": runtime_hash,
                "provider_attempt_sha256": attempt_hash,
            },
            "effect": {
                "corpus_process_invocations": 1,
                "provider_transport_call_count": "not_proven",
                "provider_internal_retry_behavior": "not_proven",
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
                "statistical_representativeness": False,
                "runtime_execution_reproduction": "not_run",
                "semantic_reproduction": "not_evaluated",
                "quality_evaluation_reproduction": "not_evaluated",
                "production_semantic_oracle_quality": False,
                "network_isolation_proven": False,
                "auth_store_nonmutation_proven": False,
                "exact_resolved_model_identity_proven": False,
                "provider_transport_call_cardinality_proven": False,
                "provider_internal_retry_absence_proven": False,
                "broad_ak_invocation_absence_proven": False,
                "release_authority": False,
                "package_publication": False,
                "sdist_supported": False,
            },
        }
    finally:
        os.close(root_descriptor)

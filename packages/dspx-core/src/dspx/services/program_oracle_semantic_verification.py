# summary: "Verifies dependency, source, and artifact provenance for AK-4570 semantic analysis."
# read_when:
#   - "Verifying AK-4570 dependency identity, source identity, or terminal artifacts."

from __future__ import annotations

import stat
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from dspx.redaction import sanitize_diagnostic_text
from dspx.services.program_oracle_semantic_evaluation import (
    ATTEMPT_NAME,
    ATTEMPT_SCHEMA,
    CONTRACT_SNAPSHOT_NAME,
    RESULT_NAME,
    RESULT_SCHEMA,
    VERIFICATION_NAME,
    VERIFICATION_SCHEMA,
    SemanticAnalysisEvaluationError,
    _attempt_ledger_path,
    _mapping,
    _read_json,
    _request,
    _sequence,
    _sha256_bytes,
    _sha256_file,
    _write_private_exclusive,
    load_contract,
    preflight_maintained_lm_auth,
)
from dspx.services.program_oracle_semantic_scoring import score_analysis

LIVE_EVIDENCE_CLASS = "production_adapter_live_behavior"
WIRING_EVIDENCE_CLASS = "test_double_wiring_only"
_SEMANTIC_RESULT_FIELDS = {
    "schema_version",
    "authority",
    "request_sha256",
    "backend_kind",
    "preferred_model",
    "configured_provider",
    "configured_model",
    "executed_provider",
    "executed_model",
    "execution_status",
    "live_call_succeeded",
    "fixture_sha256",
    "analysis",
    "error",
}
SOURCE_PATHS = (
    "benchmarks/semantic/oracle-semantic-analysis-evaluation-v4.json",
    "packages/dspx-core/src/dspx/dspy_lm_auth_lm.py",
    "packages/dspx-core/src/dspx/model_roles.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_backend.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_contract.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_evaluation.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_scoring.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_verification.py",
    "scripts/ci/run_oracle_semantic_analysis_evaluation.py",
)


def _git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = sanitize_diagnostic_text(completed.stderr.strip())
        raise SemanticAnalysisEvaluationError(
            f"source commit preflight failed: {detail or 'git command failed'}"
        )
    return completed.stdout.strip()


def committed_source_identity(repo_root: Path) -> dict[str, Any]:
    root = repo_root.expanduser().resolve()
    commit = _git(root, "rev-parse", "HEAD")
    dirty = subprocess.run(
        ["git", "-C", str(root), "diff", "--quiet", "HEAD"],
        check=False,
    )
    if dirty.returncode not in {0, 1}:
        raise SemanticAnalysisEvaluationError("source commit cleanliness check failed")
    if dirty.returncode == 1:
        raise SemanticAnalysisEvaluationError(
            "all tracked evaluation inputs must match one committed Git snapshot"
        )
    status_lines = [
        line
        for line in _git(
            root, "status", "--porcelain", "--untracked-files=normal"
        ).splitlines()
        if line and line != "?? .ontology/"
    ]
    if status_lines:
        raise SemanticAnalysisEvaluationError(
            "untracked files outside the forbidden runtime-owned .ontology/ "
            "boundary prevent committed-source evaluation"
        )
    hashes: dict[str, str] = {}
    for relative in SOURCE_PATHS:
        tracked = _git(root, "ls-files", "--error-unmatch", relative)
        if tracked != relative:
            raise SemanticAnalysisEvaluationError(
                f"untracked evaluation source: {relative}"
            )
        committed = subprocess.run(
            ["git", "-C", str(root), "show", f"{commit}:{relative}"],
            check=False,
            capture_output=True,
        )
        if committed.returncode != 0:
            raise SemanticAnalysisEvaluationError(
                f"committed evaluation source unavailable: {relative}"
            )
        working_hash = _sha256_file(root / relative)
        committed_hash = _sha256_bytes(committed.stdout)
        if working_hash != committed_hash:
            raise SemanticAnalysisEvaluationError(
                f"evaluation source differs from commit: {relative}"
            )
        hashes[relative] = working_hash
    return {"git_commit": commit, "path_sha256": hashes}


def _require_private_mode(path: Path, expected: int, label: str) -> None:
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError as exc:
        raise SemanticAnalysisEvaluationError(
            f"{label} must be an existing private artifact"
        ) from exc
    if mode != expected:
        raise SemanticAnalysisEvaluationError(f"{label} mode drift")


def _validate_execution_provenance(
    payload: object,
    *,
    evidence_class: str,
    executed_models: list[str],
    mechanics_passed: bool,
) -> bool:
    provenance = _mapping(payload, "execution_provenance")
    if provenance.get("evidence_class") != evidence_class:
        raise SemanticAnalysisEvaluationError("execution provenance class drift")
    if evidence_class == WIRING_EVIDENCE_CLASS:
        if provenance.get("trusted_for_live_behavior") is not False:
            raise SemanticAnalysisEvaluationError(
                "test-double wiring was promoted to live behavior evidence"
            )
        return False
    expected_fixed = {
        "trusted_for_live_behavior": True,
        "adapter_type": "dspx.dspy_lm_auth_lm.DspyLMAuthLM",
        "requested_model": "codex/gpt-5.6-sol",
        "auth_provider": "codex",
        "reasoning_effort": "max",
        "strict": True,
        "history_count_before": 0,
    }
    if any(provenance.get(key) != value for key, value in expected_fixed.items()):
        raise SemanticAnalysisEvaluationError("production adapter provenance drift")
    calls = [
        _mapping(item, "execution_provenance.call")
        for item in _sequence(provenance.get("calls"), "execution_provenance.calls")
    ]
    if mechanics_passed:
        if (
            provenance.get("status") != "completed"
            or provenance.get("history_count_after") != len(executed_models)
            or len(calls) != len(executed_models)
        ):
            raise SemanticAnalysisEvaluationError(
                "production adapter completion evidence drift"
            )
        for index, (call, executed_model) in enumerate(
            zip(calls, executed_models, strict=True)
        ):
            expected_call = {
                "history_index": index,
                "requested_model": "codex/gpt-5.6-sol",
                "auth_provider": "codex",
                "call_error": None,
                "resolved_model": call.get("resolved_model"),
                "uses_codex_route": True,
                "observed_response_model": executed_model,
            }
            if (
                call != expected_call
                or not str(call.get("resolved_model") or "").strip()
            ):
                raise SemanticAnalysisEvaluationError(
                    "production adapter call evidence drift"
                )
    return True


def verify_evaluation(*, repo_root: Path, root: Path) -> dict[str, Any]:
    contract, contract_hash = load_contract(repo_root)
    target = root.expanduser().absolute()
    result_path = target / RESULT_NAME
    attempt_path = target / ATTEMPT_NAME
    _require_private_mode(target, 0o700, "evaluation root")
    for path, label in (
        (result_path, "evaluation result"),
        (attempt_path, "attempt status"),
        (target / CONTRACT_SNAPSHOT_NAME, "contract snapshot"),
    ):
        _require_private_mode(path, 0o600, label)
    result, result_raw = _read_json(result_path, label="evaluation result")
    attempt, _ = _read_json(attempt_path, label="attempt status")
    snapshot, _ = _read_json(target / CONTRACT_SNAPSHOT_NAME, label="contract snapshot")
    if snapshot != contract:
        raise SemanticAnalysisEvaluationError("contract snapshot drift")
    result_hash = _sha256_bytes(result_raw)
    evidence_class = str(result.get("evidence_class") or "")
    source_identity = _mapping(result.get("source_identity"), "source_identity")
    dependency_identity = _mapping(
        result.get("dependency_identity"), "dependency_identity"
    )
    if evidence_class not in {LIVE_EVIDENCE_CLASS, WIRING_EVIDENCE_CLASS}:
        raise SemanticAnalysisEvaluationError("evaluation evidence class drift")
    expected_source_identity = (
        committed_source_identity(repo_root)
        if evidence_class == LIVE_EVIDENCE_CLASS
        else {"status": "wiring_only_not_committed_source_proof"}
    )
    expected_dependency_identity = (
        preflight_maintained_lm_auth()
        if evidence_class == LIVE_EVIDENCE_CLASS
        else {"status": "wiring_only_dependency_not_required"}
    )
    if source_identity != expected_source_identity:
        raise SemanticAnalysisEvaluationError("committed source identity drift")
    if dependency_identity != expected_dependency_identity:
        raise SemanticAnalysisEvaluationError("maintained dependency identity drift")
    if (
        result.get("schema_version") != RESULT_SCHEMA
        or result.get("contract_sha256") != contract_hash
        or result.get("ak_task_id") != 4570
    ):
        raise SemanticAnalysisEvaluationError("evaluation result identity drift")
    rows = _sequence(result.get("cases"), "result.cases")
    contract_cases = [
        _mapping(case, "case") for case in _sequence(contract.get("cases"), "cases")
    ]
    if len(rows) > len(contract_cases):
        raise SemanticAnalysisEvaluationError("result case count widened")
    case_ids = [str(_mapping(row, "result case").get("case_id")) for row in rows]
    recorded_ledger = Path(str(attempt.get("ledger_path"))).expanduser().absolute()
    canonical_ledger = (
        _attempt_ledger_path().expanduser().absolute()
        if evidence_class == LIVE_EVIDENCE_CLASS
        else recorded_ledger
    )
    if (
        attempt.get("schema_version") != ATTEMPT_SCHEMA
        or attempt.get("contract_sha256") != contract_hash
        or attempt.get("ak_task_id") != 4570
        or attempt.get("evaluation_processes") != 1
        or attempt.get("evidence_class") != evidence_class
        or attempt.get("source_identity") != source_identity
        or attempt.get("dependency_identity") != dependency_identity
        or attempt.get("separate_health_probes") != 0
        or attempt.get("dspx_managed_retries") != 0
        or attempt.get("selective_case_rerun") is not False
        or attempt.get("cases_attempted") != case_ids
        or attempt.get("dspx_analyze_invocations") != len(rows)
        or attempt.get("generate_call_count") != "not_directly_observed"
        or attempt.get("result_sha256") != result_hash
        or recorded_ledger != canonical_ledger
    ):
        raise SemanticAnalysisEvaluationError("attempt policy evidence drift")
    _require_private_mode(canonical_ledger, 0o600, "attempt ledger")
    ledger, _ = _read_json(canonical_ledger, label="attempt ledger")
    if ledger != {
        "schema_version": "dspx-oracle-semantic-analysis-evaluation-ledger-v4",
        "ak_task_id": 4570,
        "contract_sha256": contract_hash,
        "root": str(target),
        "status": result.get("status"),
        "source_identity": source_identity,
        "evidence_class": evidence_class,
        "maximum_evaluation_processes": 1,
        "selective_case_rerun_allowed": False,
        "result_sha256": result_hash,
        "attempt_sha256": _sha256_file(attempt_path),
    }:
        raise SemanticAnalysisEvaluationError("attempt ledger drift")

    route = _mapping(contract.get("route"), "route")
    rederived_rows: list[dict[str, Any]] = []
    executed_models: list[str] = []
    for index, raw_row in enumerate(rows):
        row = _mapping(raw_row, f"result.case[{index}]")
        case = contract_cases[index]
        if row.get("case_id") != case.get("id"):
            raise SemanticAnalysisEvaluationError("result case order drift")
        request = _request(case)
        if row.get("request_sha256") != request.request_sha256:
            raise SemanticAnalysisEvaluationError("request hash drift")
        semantic = _mapping(row.get("semantic_result"), "semantic_result")
        if set(semantic) != _SEMANTIC_RESULT_FIELDS:
            raise SemanticAnalysisEvaluationError("semantic result fields drift")
        if semantic.get("request_sha256") != request.request_sha256:
            raise SemanticAnalysisEvaluationError("semantic result request hash drift")
        route_ok = (
            semantic.get("schema_version") == "dspx-program-oracle-semantic-result-v1"
            and semantic.get("authority") == "local_empirical_advisory_only"
            and semantic.get("backend_kind") == "live"
            and semantic.get("preferred_model") == route.get("requested_model")
            and semantic.get("configured_provider") == route.get("requested_provider")
            and semantic.get("configured_model") == route.get("requested_model")
            and semantic.get("executed_provider") is None
            and semantic.get("fixture_sha256") is None
        )
        analysis_raw = semantic.get("analysis")
        analysis = (
            _mapping(analysis_raw, "analysis") if analysis_raw is not None else None
        )
        executed_model = semantic.get("executed_model")
        succeeded = (
            semantic.get("execution_status") == "succeeded"
            and semantic.get("live_call_succeeded") is True
            and analysis is not None
            and isinstance(executed_model, str)
            and bool(executed_model)
            and semantic.get("error") is None
        )
        score = (
            score_analysis(case, analysis)
            if succeeded and route_ok and analysis
            else None
        )
        if row.get("score") != score:
            raise SemanticAnalysisEvaluationError("stored semantic score drift")
        if not succeeded:
            expected_status = "failed_or_indeterminate"
        elif not route_ok:
            expected_status = "identity_failed"
        else:
            expected_status = str(cast(Mapping[str, Any], score).get("status"))
            executed_models.append(cast(str, executed_model))
        if row.get("status") != expected_status:
            raise SemanticAnalysisEvaluationError("stored case status drift")
        rederived_rows.append(
            {"case_id": case.get("id"), "status": expected_status, "score": score}
        )

    complete = len(rows) == len(contract_cases)
    all_passed = complete and all(row["status"] == "passed" for row in rederived_rows)
    consistent_model = bool(executed_models) and len(set(executed_models)) == 1
    macro_score = sum(
        float(cast(Mapping[str, Any], row["score"]).get("score", 0.0))
        if isinstance(row.get("score"), Mapping)
        else 0.0
        for row in rederived_rows
    ) / len(contract_cases)
    mechanics_passed = all_passed and consistent_model and macro_score == 1.0
    production_provenance = _validate_execution_provenance(
        result.get("execution_provenance"),
        evidence_class=evidence_class,
        executed_models=executed_models,
        mechanics_passed=mechanics_passed,
    )
    expected_pass = (
        evidence_class == LIVE_EVIDENCE_CLASS
        and production_provenance
        and mechanics_passed
    )
    expected_status = (
        "passed"
        if expected_pass
        else "wiring_only_passed"
        if evidence_class == WIRING_EVIDENCE_CLASS and mechanics_passed
        else "failed"
    )
    if result.get("mechanics_passed") is not mechanics_passed:
        raise SemanticAnalysisEvaluationError("mechanics result drift")
    if (
        result.get("status") != expected_status
        or attempt.get("status") != expected_status
    ):
        raise SemanticAnalysisEvaluationError("terminal result status drift")
    expected_attempt = {
        "evaluation_processes": 1,
        "separate_health_probes": 0,
        "dspx_managed_retries": 0,
        "selective_case_rerun": False,
        "dspx_analyze_invocations": len(rows),
        "generate_call_count": "not_directly_observed",
    }
    if result.get("attempt") != expected_attempt:
        raise SemanticAnalysisEvaluationError("result attempt projection drift")
    expected_summary = {
        "expected_case_count": len(contract_cases),
        "attempted_case_count": len(rows),
        "passed_case_count": sum(
            1 for row in rederived_rows if row["status"] == "passed"
        ),
        "macro_score": macro_score,
        "executed_model_consistent": consistent_model,
        "observed_executed_model": executed_models[0] if consistent_model else None,
        "executed_provider_identity": "not_proven",
        "provider_transport_call_count": "not_proven",
        "provider_internal_retry_behavior": "not_proven",
    }
    if result.get("summary") != expected_summary:
        raise SemanticAnalysisEvaluationError("result summary drift")
    if result.get("effects") != contract.get("privacy_and_effects"):
        raise SemanticAnalysisEvaluationError("result effect boundary drift")
    claims = _mapping(result.get("claims"), "claims")
    expected_claims = {
        "four_case_semantic_analysis_gate_passed": expected_pass,
        "test_double_wiring_is_live_behavior_evidence": False,
        **_mapping(contract.get("nonclaims"), "nonclaims"),
    }
    if claims != expected_claims:
        raise SemanticAnalysisEvaluationError("semantic-analysis claim drift")
    verification = {
        "schema_version": VERIFICATION_SCHEMA,
        "status": "accepted" if expected_pass else "rejected",
        "contract_sha256": contract_hash,
        "result_sha256": result_hash,
        "attempt_sha256": _sha256_file(attempt_path),
        "ledger_sha256": _sha256_file(canonical_ledger),
        "source_commit_independently_checked": evidence_class == LIVE_EVIDENCE_CLASS,
        "request_hashes_freshly_rederived": True,
        "labels_freshly_deterministically_rescored": True,
        "implementation_independence_claimed": False,
        "evidence_refs_freshly_checked": True,
        "production_adapter_provenance_checked": production_provenance,
        "route_layers_kept_separate": True,
        "attempt_policy_independently_checked": True,
        "failed_history_preserved": result.get("status") == "failed",
        "terminal_history_disposition": (
            "live_passed_no_failure"
            if expected_pass
            else "wiring_only_not_live_history"
            if evidence_class == WIRING_EVIDENCE_CLASS
            else "failed_or_indeterminate_preserved"
        ),
        "four_case_semantic_analysis_gate_passed": expected_pass,
        "shared_store_or_embedding_evidence_used": False,
    }
    _write_private_exclusive(target / VERIFICATION_NAME, verification)
    return verification

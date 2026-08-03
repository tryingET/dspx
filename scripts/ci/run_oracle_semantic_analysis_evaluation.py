#!/usr/bin/env python3
# summary: "Runs or verifies the independently reviewed one-shot AK-4577 semantic evaluation."
# read_when:
#   - "Running the frozen independent-label Oracle semantic-analysis evaluation."

from __future__ import annotations

import argparse
import inspect
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from dspx.dspy_lm_auth_lm import DspyLMAuthLM
from dspx.redaction import sanitize_diagnostic_text
from dspx.services.program_oracle_semantic_backend import (
    LiveLMOracleSemanticBackend,
    _analysis_prompt,
    resolve_program_oracle_semantic_backend,
)
from dspx.services.program_oracle_semantic_evaluation import (
    ATTEMPT_NAME,
    ATTEMPT_SCHEMA,
    CONTRACT_SNAPSHOT_NAME,
    RESULT_NAME,
    RESULT_SCHEMA,
    VERIFICATION_NAME,
    SemanticAnalysisEvaluationError,
    _attempt_ledger_path,
    _consume_attempt_ledger,
    _mapping,
    _read_json,
    _replace_private_atomic,
    _request,
    _sequence,
    _sha256_file,
    _write_private_exclusive,
    load_contract,
    preflight_maintained_lm_auth,
)
from dspx.services.program_oracle_semantic_scoring import score_analysis
from dspx.services.program_oracle_semantic_verification import (
    LIVE_EVIDENCE_CLASS as _LIVE_EVIDENCE_CLASS,
    WIRING_EVIDENCE_CLASS as _WIRING_EVIDENCE_CLASS,
    committed_source_identity as _committed_source_identity,
    verify_evaluation,
)

_CASE_ORDER = (
    "authority-boundary",
    "causal-calibration",
    "review-only-transition",
    "provenance-drift",
)

__all__ = ("VERIFICATION_NAME", "run_evaluation", "verify_evaluation")


def _environment_route(contract: Mapping[str, Any]) -> None:
    route = _mapping(contract.get("route"), "route")
    expected = {
        "DSPX_ORACLE_SEMANTIC_BACKEND": "live",
        "DSPX_ORACLE_SEMANTIC_PROVIDER": str(route["requested_provider"]),
        "DSPX_ORACLE_SEMANTIC_MODEL": str(route["requested_model"]),
        "DSPX_ORACLE_SEMANTIC_REASONING_EFFORT": str(route["reasoning_effort"]),
    }
    observed = {name: os.getenv(name) for name in expected}
    if observed != expected:
        raise SemanticAnalysisEvaluationError(
            "semantic-analysis route environment drift: "
            f"expected {expected!r}, observed {observed!r}"
        )


def _new_root(root: Path) -> Path:
    target = root.expanduser()
    if not target.is_absolute():
        raise SemanticAnalysisEvaluationError("--root must be absolute")
    target = target.absolute()
    if target.exists():
        raise SemanticAnalysisEvaluationError("--root must not already exist")
    target.mkdir(parents=False, mode=0o700)
    os.chmod(target, 0o700)
    return target


def _production_adapter_methods_are_pristine(lm: DspyLMAuthLM) -> bool:
    method_names = ("_build_inner", "forward", "generate", "runtime_metadata")
    expected_suffix = Path("packages/dspx-core/src/dspx/dspy_lm_auth_lm.py")
    for name in method_names:
        if name in lm.__dict__:
            return False
        descriptor = inspect.getattr_static(DspyLMAuthLM, name, None)
        bound = getattr(lm, name, None)
        expected_qualname = f"DspyLMAuthLM.{name}"
        if (
            descriptor is None
            or getattr(descriptor, "__name__", None) != name
            or getattr(descriptor, "__qualname__", None) != expected_qualname
            or getattr(bound, "__func__", None) is not descriptor
        ):
            return False
        source_file = inspect.getsourcefile(descriptor)
        if source_file is None or not Path(source_file).resolve().is_relative_to(
            Path(__file__).resolve().parents[2]
        ):
            return False
        if (
            not Path(source_file)
            .resolve()
            .as_posix()
            .endswith(expected_suffix.as_posix())
        ):
            return False
    return True


def _adapter_preflight(
    backend: LiveLMOracleSemanticBackend, *, evidence_class: str
) -> tuple[DspyLMAuthLM | None, dict[str, Any]]:
    lm = backend.lm
    if evidence_class == _WIRING_EVIDENCE_CLASS:
        return None, {
            "evidence_class": _WIRING_EVIDENCE_CLASS,
            "trusted_for_live_behavior": False,
            "adapter_type": f"{type(lm).__module__}.{type(lm).__qualname__}",
        }
    if evidence_class != _LIVE_EVIDENCE_CLASS:
        raise SemanticAnalysisEvaluationError("unknown evaluation evidence class")
    if type(lm) is not DspyLMAuthLM:
        raise SemanticAnalysisEvaluationError(
            "live behavior requires the exact production DspyLMAuthLM adapter; "
            "fixtures, subclasses, and test doubles are wiring-only"
        )
    if not _production_adapter_methods_are_pristine(lm):
        raise SemanticAnalysisEvaluationError(
            "production adapter methods were rebound or do not originate from "
            "the committed DSPx adapter source"
        )
    if (
        lm.requested_model != "codex/gpt-5.6-sol"
        or lm.auth_provider != "codex"
        or lm.strict is not True
        or lm.kwargs != {"reasoning_effort": "max"}
        or lm.history
    ):
        raise SemanticAnalysisEvaluationError("production adapter preflight drift")
    return lm, {
        "evidence_class": _LIVE_EVIDENCE_CLASS,
        "trusted_for_live_behavior": True,
        "adapter_type": "dspx.dspy_lm_auth_lm.DspyLMAuthLM",
        "requested_model": lm.requested_model,
        "auth_provider": lm.auth_provider,
        "reasoning_effort": lm.kwargs["reasoning_effort"],
        "strict": lm.strict,
        "history_count_before": 0,
    }


def _adapter_call_evidence(
    lm: DspyLMAuthLM, *, previous_history_count: int, executed_model: str
) -> dict[str, Any]:
    if len(lm.history) != previous_history_count + 1:
        raise SemanticAnalysisEvaluationError(
            "production adapter call history cardinality drift"
        )
    call = lm.history[-1]
    metadata = lm.runtime_metadata()
    if (
        call.model != lm.requested_model
        or call.auth_provider != "codex"
        or call.error is not None
        or call.ended_at < call.started_at
        or metadata.get("provider_family") != "dspy-lm-auth"
        or metadata.get("requested_model") != lm.requested_model
        or metadata.get("uses_codex_route") is not True
        or not str(metadata.get("resolved_model") or "").strip()
        or executed_model != str(lm.model)
    ):
        raise SemanticAnalysisEvaluationError(
            "production adapter execution evidence drift"
        )
    return {
        "history_index": previous_history_count,
        "requested_model": call.model,
        "auth_provider": call.auth_provider,
        "call_error": None,
        "resolved_model": str(metadata["resolved_model"]),
        "uses_codex_route": True,
        "observed_response_model": executed_model,
    }


def run_evaluation(
    *,
    repo_root: Path,
    root: Path,
    evidence_class: str = _LIVE_EVIDENCE_CLASS,
) -> dict[str, Any]:
    contract, contract_hash = load_contract(repo_root)
    adjudication = _mapping(
        contract.get("offline_adjudication"), "offline_adjudication"
    )
    successor_review = _mapping(
        adjudication.get("successor_review"), "offline_adjudication.successor_review"
    )
    if successor_review.get("status") != "independent_successor_review_accepted":
        raise SemanticAnalysisEvaluationError(
            "AK-4577 successor review is pending; no evaluation process is authorized"
        )
    if evidence_class != _LIVE_EVIDENCE_CLASS:
        raise SemanticAnalysisEvaluationError(
            "AK-4577 authorizes only the production-adapter live evidence class"
        )
    dependency_identity = preflight_maintained_lm_auth()
    source_identity = _committed_source_identity(repo_root)
    target = _new_root(root)
    try:
        ledger = _consume_attempt_ledger(
            root=target,
            contract_sha256=contract_hash,
            ledger_path=_attempt_ledger_path(),
        )
    except Exception:
        target.rmdir()
        raise
    _write_private_exclusive(target / CONTRACT_SNAPSHOT_NAME, contract)
    attempt: dict[str, Any] = {
        "schema_version": ATTEMPT_SCHEMA,
        "ak_task_id": 4577,
        "status": "started",
        "contract_sha256": contract_hash,
        "evaluation_processes": 1,
        "evidence_class": evidence_class,
        "source_identity": source_identity,
        "dependency_identity": dependency_identity,
        "separate_health_probes": 0,
        "dspx_managed_retries": 0,
        "selective_case_rerun": False,
        "cases_attempted": [],
        "dspx_analyze_invocations": 0,
        "generate_call_count": "not_directly_observed",
        "provider_transport_call_count": "not_proven",
        "provider_internal_retry_behavior": "not_proven",
        "ledger_path": str(ledger),
    }
    _write_private_exclusive(target / ATTEMPT_NAME, attempt)

    case_results: list[dict[str, Any]] = []
    executed_models: list[str] = []
    adapter_calls: list[dict[str, Any]] = []
    adapter_provenance: dict[str, Any] = {
        "evidence_class": evidence_class,
        "trusted_for_live_behavior": False,
        "status": "not_resolved",
    }
    terminal_error: str | None = None
    production_lm: DspyLMAuthLM | None = None
    try:
        _environment_route(contract)
        backend = resolve_program_oracle_semantic_backend()
        if not isinstance(backend, LiveLMOracleSemanticBackend):
            raise SemanticAnalysisEvaluationError(
                "evaluation requires the live LM backend"
            )
        route = _mapping(contract.get("route"), "route")
        if (
            backend.provider_name != route.get("requested_provider")
            or backend.preferred_model != route.get("requested_model")
            or backend.configured_model != route.get("requested_model")
        ):
            raise SemanticAnalysisEvaluationError(
                "configured semantic-analysis route drift"
            )
        production_lm, adapter_provenance = _adapter_preflight(
            backend, evidence_class=evidence_class
        )
        adapter_provenance["status"] = "preflight_passed"

        for raw_case in _sequence(contract.get("cases"), "cases"):
            case = _mapping(raw_case, "case")
            case_id = str(case.get("id"))
            request = _request(case)
            prompt = _analysis_prompt(request)
            if str(case.get("hidden_marker")) in prompt:
                raise SemanticAnalysisEvaluationError(
                    "hidden marker leaked into prompt"
                )
            attempt["cases_attempted"].append(case_id)
            attempt["dspx_analyze_invocations"] = len(attempt["cases_attempted"])
            _replace_private_atomic(target / ATTEMPT_NAME, attempt)
            history_before = len(production_lm.history) if production_lm else 0
            result = backend.analyze(request)
            row: dict[str, Any] = {
                "case_id": case_id,
                "request_sha256": request.request_sha256,
                "semantic_result": result.to_dict(),
                "score": None,
            }
            if (
                result.execution_status != "succeeded"
                or not result.live_call_succeeded
                or result.analysis is None
            ):
                row["status"] = "failed_or_indeterminate"
                case_results.append(row)
                terminal_error = result.error or result.execution_status
                break
            if (
                result.backend_kind != "live"
                or result.preferred_model != route.get("requested_model")
                or result.configured_provider != route.get("requested_provider")
                or result.configured_model != route.get("requested_model")
                or result.executed_provider is not None
                or not result.executed_model
            ):
                row["status"] = "identity_failed"
                case_results.append(row)
                terminal_error = "semantic-analysis identity gate failed"
                break
            executed_models.append(result.executed_model)
            if production_lm is not None:
                adapter_calls.append(
                    _adapter_call_evidence(
                        production_lm,
                        previous_history_count=history_before,
                        executed_model=result.executed_model,
                    )
                )
            score = score_analysis(case, result.analysis.to_dict())
            row["score"] = score
            row["status"] = score["status"]
            case_results.append(row)
            if score["status"] != "passed":
                terminal_error = "semantic-analysis label gate failed"
                break
    except Exception as exc:
        terminal_error = sanitize_diagnostic_text(str(exc))

    complete = len(case_results) == len(_CASE_ORDER)
    all_passed = complete and all(row.get("status") == "passed" for row in case_results)
    consistent_model = bool(executed_models) and len(set(executed_models)) == 1
    macro_score = sum(
        float(cast(Mapping[str, Any], row["score"]).get("score", 0.0))
        if isinstance(row.get("score"), Mapping)
        else 0.0
        for row in case_results
    ) / len(_CASE_ORDER)
    mechanics_passed = all_passed and consistent_model and macro_score == 1.0
    passed = evidence_class == _LIVE_EVIDENCE_CLASS and mechanics_passed
    terminal_status = (
        "passed"
        if passed
        else "wiring_only_passed"
        if evidence_class == _WIRING_EVIDENCE_CLASS and mechanics_passed
        else "failed"
    )
    adapter_provenance["status"] = (
        "completed" if mechanics_passed else "failed_or_indeterminate"
    )
    adapter_provenance["calls"] = adapter_calls
    adapter_provenance["history_count_after"] = (
        len(production_lm.history) if production_lm else 0
    )
    payload = {
        "schema_version": RESULT_SCHEMA,
        "status": terminal_status,
        "ak_task_id": 4577,
        "contract_sha256": contract_hash,
        "evidence_class": evidence_class,
        "source_identity": source_identity,
        "dependency_identity": dependency_identity,
        "execution_provenance": adapter_provenance,
        "cases": case_results,
        "summary": {
            "expected_case_count": len(_CASE_ORDER),
            "attempted_case_count": len(case_results),
            "passed_case_count": sum(
                1 for row in case_results if row.get("status") == "passed"
            ),
            "macro_score": macro_score,
            "executed_model_consistent": consistent_model,
            "observed_executed_model": (
                executed_models[0] if consistent_model else None
            ),
            "executed_provider_identity": "not_proven",
            "provider_transport_call_count": "not_proven",
            "provider_internal_retry_behavior": "not_proven",
        },
        "mechanics_passed": mechanics_passed,
        "attempt": {
            "evaluation_processes": 1,
            "separate_health_probes": 0,
            "dspx_managed_retries": 0,
            "selective_case_rerun": False,
            "dspx_analyze_invocations": len(attempt["cases_attempted"]),
            "generate_call_count": "not_directly_observed",
        },
        "terminal_error": terminal_error,
        "claims": {
            "four_case_semantic_analysis_gate_passed": passed,
            "test_double_wiring_is_live_behavior_evidence": False,
            **_mapping(contract.get("nonclaims"), "nonclaims"),
        },
        "effects": _mapping(contract.get("privacy_and_effects"), "privacy_and_effects"),
    }
    _write_private_exclusive(target / RESULT_NAME, payload)
    result_hash = _sha256_file(target / RESULT_NAME)
    attempt.update(
        {
            "status": terminal_status,
            "result_sha256": result_hash,
            "terminal_error": terminal_error,
        }
    )
    _replace_private_atomic(target / ATTEMPT_NAME, attempt)
    ledger_payload, _ = _read_json(ledger, label="attempt ledger")
    ledger_payload.update(
        {
            "status": terminal_status,
            "source_identity": source_identity,
            "evidence_class": evidence_class,
            "result_sha256": result_hash,
            "attempt_sha256": _sha256_file(target / ATTEMPT_NAME),
        }
    )
    _replace_private_atomic(ledger, ledger_payload)
    return payload


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "verify"):
        command = subparsers.add_parser(name)
        command.add_argument("--root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            result = run_evaluation(repo_root=_repo_root(), root=args.root)
            print(
                json.dumps(
                    {
                        "status": result.get("status"),
                        "artifact_root": str(args.root.expanduser().absolute()),
                        "result_sha256": _sha256_file(
                            args.root.expanduser().absolute() / RESULT_NAME
                        ),
                    },
                    sort_keys=True,
                )
            )
            return 0 if result.get("status") == "passed" else 1
        verification = verify_evaluation(repo_root=_repo_root(), root=args.root)
        print(json.dumps(verification, indent=2, sort_keys=True))
        return 0 if verification.get("status") == "accepted" else 1
    except SemanticAnalysisEvaluationError as exc:
        print(f"error: {sanitize_diagnostic_text(str(exc))}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

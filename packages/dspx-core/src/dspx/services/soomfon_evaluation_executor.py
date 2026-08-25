from __future__ import annotations

import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping

from dspx.services.program_runtime_episode import (
    load_validated_program_runtime_episode_bundle,
)
from dspx.services.soomfon_evaluation_child import (
    _child_main,
    _run_child,
)
from dspx.services.soomfon_evaluation_contract import (
    EXPECTED_MODES,
    build_sanitized_child_environment,
    classify_provider_disposition,
    load_hash_bound_soomfon_contract,
    validate_case_artifact_bindings,
    validate_exact_runtime_identity,
)
from dspx.services.soomfon_evaluation_custody import (
    acquire_suite_lock,
    append_terminal,
    create_attempt_marker,
    default_state_root,
    ensure_private_tree,
    fsync_private_tree,
    marker_sha256,
    reconcile_marker_indeterminate,
    stage_candidate,
)
from dspx.services.soomfon_evaluation_filesystem import (
    write_private_json_exclusive as _write_private_json,
)
from dspx.services.soomfon_evaluation_ledger import (
    private_runtime_tree_sha256_path,
    runtime_evidence_hashes,
)


_SUITE_SCHEMA = "soomfon-dspy33-evaluation-suite-v1"
_CHILD_TIMEOUT_SECONDS = 240


SoomfonEvaluationExecutorError, _repo_root = RuntimeError, Path.cwd


def _evaluate_case(
    *,
    case: Mapping[str, Any],
    staged_manifest: Path,
    raw_root: Path,
    child_environment: Mapping[str, str],
    contract_sha256: str,
    marker_fd: int,
    ledger_fd: int,
    lock_fd: int,
    provider_journal_fd: int,
    execution_task_id: int,
    authorization_sha256: str,
    ak_reconciliation_sha256: str,
    authorization_path: Path,
    repo_root: Path,
    owner_source_root: Path,
) -> tuple[str, dict[str, object]]:
    started = time.monotonic_ns()
    try:
        returncode, latency_ms = _run_child(
            case=case,
            staged_manifest=staged_manifest,
            raw_root=raw_root,
            child_environment=child_environment,
            contract_sha256=contract_sha256,
            marker_fd=marker_fd,
            ledger_fd=ledger_fd,
            lock_fd=lock_fd,
            provider_journal_fd=provider_journal_fd,
            execution_task_id=execution_task_id,
            authorization_sha256=authorization_sha256,
            ak_reconciliation_sha256=ak_reconciliation_sha256,
            authorization_path=authorization_path,
            repo_root=repo_root,
            owner_source_root=owner_source_root,
        )
    except subprocess.TimeoutExpired:
        try:
            fsync_private_tree(raw_root)
        except Exception:
            pass
        return "effect_indeterminate", {
            "reason": "child_timeout",
            "latency_ms": max(0, (time.monotonic_ns() - started) // 1_000_000),
        }
    except Exception as exc:
        return "effect_indeterminate", {
            "reason": "child_supervision_failed",
            "error_type": type(exc).__name__,
            "latency_ms": max(0, (time.monotonic_ns() - started) // 1_000_000),
        }
    try:
        fsync_private_tree(raw_root)
    except Exception as exc:
        return "effect_indeterminate", {
            "reason": "raw_evidence_persistence_failed",
            "error_type": type(exc).__name__,
            "latency_ms": latency_ms,
        }
    if returncode != 0:
        return "effect_indeterminate", {
            "reason": "child_failed",
            "returncode": returncode,
            "latency_ms": latency_ms,
        }
    runtime_path = raw_root / "runtime/runtime_episode.json"
    try:
        baseline_tree_sha256 = private_runtime_tree_sha256_path(runtime_path.parent)
    except Exception as exc:
        return "effect_indeterminate", {
            "reason": "runtime_tree_baseline_invalid",
            "error_type": type(exc).__name__,
            "latency_ms": latency_ms,
        }
    try:
        bundle = load_validated_program_runtime_episode_bundle(
            runtime_episode_path=runtime_path,
            expected_manifest_path=staged_manifest,
            expected_manifest=case["manifest_payload"],
            expected_manifest_sha256=case["manifest_sha256"],
            label="Soomfon evaluation runtime episode",
            error_type=SoomfonEvaluationExecutorError,
        )
    except Exception as exc:
        return "effect_indeterminate", {
            "reason": "runtime_receipt_invalid",
            "error_type": type(exc).__name__,
            "latency_ms": latency_ms,
        }
    durable_evidence = runtime_evidence_hashes(
        ledger_fd, f"{contract_sha256}.{case['mode']}.jsonl"
    )
    if (
        durable_evidence is None
        or durable_evidence.get("runtime_tree_sha256") != baseline_tree_sha256
    ):
        return "effect_indeterminate", {
            "reason": "runtime_durable_evidence_invalid",
            "latency_ms": latency_ms,
        }
    state, provider_details = classify_provider_disposition(bundle.behavior_results)
    if state == "succeeded":
        try:
            from dspx.services.soomfon_evaluation_provider import (
                verify_retained_soomfon_journals,
                verify_soomfon_owner_source,
            )

            verify_soomfon_owner_source(owner_source_root)
            provider = bundle.behavior_results.get("provider")
            if not isinstance(provider, Mapping):
                raise SoomfonEvaluationExecutorError(
                    "validated provider evidence envelope is missing"
                )
            full_provider_evidence = provider.get("effect_evidence")
            if not isinstance(full_provider_evidence, Mapping):
                raise SoomfonEvaluationExecutorError(
                    "validated provider evidence envelope is missing"
                )
            verify_retained_soomfon_journals(
                provider_journal_fd,
                full_provider_evidence,
                mode=str(case["mode"]),
                execution_task_id=execution_task_id,
                contract_sha256=contract_sha256,
                expected_marker_sha256=marker_sha256(marker_fd),
            )
        except Exception:
            state = "effect_indeterminate"
            provider_details = {"reason": "provider_receipt_journal_invalid"}
    if (
        state == "succeeded"
        and bundle.runtime_episode.get("execution_status") != "executed"
    ):
        state = "effect_indeterminate"
        provider_details = {"reason": "runtime_execution_not_successful"}
    examples = bundle.behavior_results.get("examples")
    response: object = None
    if (
        isinstance(examples, list)
        and len(examples) == 1
        and isinstance(examples[0], dict)
    ):
        outputs = examples[0].get("observed_outputs")
        if isinstance(outputs, dict):
            response = outputs.get("response")
    if state == "succeeded" and (not isinstance(response, str) or not response.strip()):
        state = "effect_indeterminate"
        provider_details = {"reason": "response_missing_after_success"}
    details: dict[str, object] = {
        "latency_ms": latency_ms,
        "runtime_episode_sha256": bundle.runtime_episode_sha256,
        "runtime_tree_sha256": durable_evidence["runtime_tree_sha256"],
        "runtime_receipt_sha256": bundle.runtime_receipt_sha256,
        "behavior_results_sha256": bundle.behavior_results_sha256,
        "provider": provider_details,
    }
    if isinstance(response, str):
        details["response_sha256"] = hashlib.sha256(response.encode()).hexdigest()
        details["response_length"] = len(response)
    return state, details


def _persist_attempt_before_effect(
    *,
    ledger_fd: int,
    contract_sha256: str,
    mode: str,
    execution_task_id: int,
    authorization_sha256: str,
    ak_reconciliation_sha256: str,
) -> tuple[int, str]:
    """Return only after the attempted marker and containing ledger are fsynced."""

    return create_attempt_marker(
        ledger_fd=ledger_fd,
        contract_sha256=contract_sha256,
        mode=mode,
        execution_task_id=execution_task_id,
        authorization_sha256=authorization_sha256,
        ak_reconciliation_sha256=ak_reconciliation_sha256,
    )


def execute_soomfon_evaluation_suite(
    *,
    expected_contract_sha256: str,
    execution_authorization_path: Path | None = None,
    expected_authorization_sha256: str | None = None,
    owner_source_root: Path | None = None,
    environment: Mapping[str, str] | None = None,
) -> dict[str, object]:
    repo_root = _repo_root().resolve()
    contract, contract_sha256, contract_path = load_hash_bound_soomfon_contract(
        repo_root=repo_root,
        expected_sha256=expected_contract_sha256,
    )
    from dspx.services.soomfon_evaluation_authorization import (
        validate_execution_authorization,
    )
    from dspx.services.soomfon_evaluation_provider import (
        verify_soomfon_owner_source,
    )

    authorization = validate_execution_authorization(
        path=execution_authorization_path,
        expected_sha256=expected_authorization_sha256,
        repo_root=repo_root,
        contract_sha256=contract_sha256,
    )
    from dspx.services.soomfon_evaluation_dspx_identity import (
        preload_security_critical_dspx_modules,
        verify_executing_dspx_artifact,
    )

    preload_security_critical_dspx_modules()
    verify_executing_dspx_artifact(
        repo_root=repo_root, artifact=authorization.dspx_artifact
    )
    if owner_source_root is None:
        raise SoomfonEvaluationExecutorError("owner source root is required")
    verified_owner_root = owner_source_root.expanduser().resolve(strict=True)
    owner_source_identity = verify_soomfon_owner_source(verified_owner_root)
    runtime_identity = validate_exact_runtime_identity()
    cases = validate_case_artifact_bindings(repo_root=repo_root, contract=contract)
    source_environment = os.environ if environment is None else environment
    state_root = default_state_root()
    child_environment = build_sanitized_child_environment(
        source_environment, private_tmp=state_root / contract_sha256 / "tmp"
    )

    base, base_fd = ensure_private_tree(state_root)
    suite_root, suite_fd = ensure_private_tree(base / contract_sha256)
    ledger_root, ledger_fd = ensure_private_tree(suite_root / "ledger")
    raw_parent, raw_parent_fd = ensure_private_tree(suite_root / "raw")
    stage_parent, stage_parent_fd = ensure_private_tree(suite_root / "stage")
    tmp_root, tmp_fd = ensure_private_tree(suite_root / "tmp")
    provider_parent, provider_parent_fd = ensure_private_tree(
        suite_root / "provider-outcomes"
    )
    for fd in (base_fd, raw_parent_fd, stage_parent_fd, tmp_fd, provider_parent_fd):
        os.close(fd)
    try:
        lock_fd = acquire_suite_lock(suite_fd)
    except Exception:
        os.close(ledger_fd)
        os.close(suite_fd)
        raise
    results: list[dict[str, object]] = []
    try:
        for case in cases:
            mode = str(case["mode"])
            case_started = time.monotonic_ns()
            refreshed_authorization = validate_execution_authorization(
                path=authorization.authorization_path,
                expected_sha256=authorization.authorization_sha256,
                repo_root=repo_root,
                contract_sha256=contract_sha256,
            )
            if refreshed_authorization != authorization:
                raise SoomfonEvaluationExecutorError(
                    "canonical execution authorization changed before marker"
                )
            marker_fd, marker_name = _persist_attempt_before_effect(
                ledger_fd=ledger_fd,
                contract_sha256=contract_sha256,
                mode=mode,
                execution_task_id=authorization.execution_task_id,
                authorization_sha256=authorization.authorization_sha256,
                ak_reconciliation_sha256=authorization.ak_reconciliation_sha256,
            )
            provider_journal_fd = -1
            try:
                try:
                    staged_manifest = stage_candidate(case, stage_parent / mode)
                    raw_root, raw_fd = ensure_private_tree(raw_parent / mode)
                    os.close(raw_fd)
                    _, provider_journal_fd = ensure_private_tree(provider_parent / mode)
                except Exception as exc:
                    state = "effect_indeterminate"
                    details: dict[str, object] = {
                        "reason": "post_marker_staging_failed",
                        "error_type": type(exc).__name__,
                        "latency_ms": max(
                            0, (time.monotonic_ns() - case_started) // 1_000_000
                        ),
                    }
                else:
                    try:
                        state, details = _evaluate_case(
                            case=case,
                            staged_manifest=staged_manifest,
                            raw_root=raw_root,
                            child_environment=child_environment,
                            contract_sha256=contract_sha256,
                            marker_fd=marker_fd,
                            ledger_fd=ledger_fd,
                            lock_fd=lock_fd,
                            provider_journal_fd=provider_journal_fd,
                            execution_task_id=authorization.execution_task_id,
                            authorization_sha256=authorization.authorization_sha256,
                            ak_reconciliation_sha256=authorization.ak_reconciliation_sha256,
                            authorization_path=authorization.authorization_path,
                            repo_root=repo_root,
                            owner_source_root=verified_owner_root,
                        )
                    except BaseException as exc:
                        state = "effect_indeterminate"
                        details = {
                            "reason": "post_marker_executor_interrupted",
                            "error_type": type(exc).__name__,
                            "latency_ms": max(
                                0, (time.monotonic_ns() - case_started) // 1_000_000
                            ),
                        }
                try:
                    append_terminal(
                        marker_fd=marker_fd,
                        ledger_fd=ledger_fd,
                        contract_sha256=contract_sha256,
                        mode=mode,
                        state=state,
                        details=details,
                    )
                except BaseException:
                    state = "effect_indeterminate"
                    details = {
                        "reason": "terminal_persistence_failed",
                        "latency_ms": max(
                            0, (time.monotonic_ns() - case_started) // 1_000_000
                        ),
                    }
                    try:
                        reconcile_marker_indeterminate(
                            ledger_fd=ledger_fd,
                            marker_name=marker_name,
                            reason="terminal_persistence_failed",
                        )
                    except BaseException:
                        pass
                results.append(
                    {
                        "mode": mode,
                        "state": state,
                        "manifest_sha256": case["manifest_sha256"],
                        "ledger_marker": str(ledger_root / marker_name),
                        **details,
                    }
                )
            finally:
                if provider_journal_fd >= 0:
                    os.close(provider_journal_fd)
                os.close(marker_fd)
            if results[-1]["state"] != "succeeded":
                break
        suite_state = (
            "succeeded"
            if len(results) == len(EXPECTED_MODES)
            and all(item["state"] == "succeeded" for item in results)
            else "stopped_non_success"
        )
        payload: dict[str, object] = {
            "schema_version": _SUITE_SCHEMA,
            "contract_path": str(contract_path),
            "contract_sha256": contract_sha256,
            "state": suite_state,
            "runtime_identity": runtime_identity,
            "authorization": {
                "execution_task_id": authorization.execution_task_id,
                "authorization_sha256": authorization.authorization_sha256,
                "ak_reconciliation_sha256": authorization.ak_reconciliation_sha256,
                "maximum_provider_transports": authorization.maximum_provider_transports,
            },
            "owner_source_identity_sha256": hashlib.sha256(
                json.dumps(
                    owner_source_identity,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest(),
            "backend_locality": "external_provider_route_not_local_backend_claim",
            "case_results": results,
            "routing_mutated": False,
            "promotion": False,
            "activation": False,
            "release": False,
            "publication": False,
        }
        _write_private_json(suite_root / "suite-result.json", payload)
        return payload
    finally:
        os.close(ledger_fd)
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
        os.close(suite_fd)


if __name__ == "__main__":
    raise SystemExit(_child_main(sys.argv[1:]))

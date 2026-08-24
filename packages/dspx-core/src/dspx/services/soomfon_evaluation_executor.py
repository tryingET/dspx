from __future__ import annotations

import argparse
import fcntl
import hashlib
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from dspx.services.program_runtime_episode import (
    load_validated_program_runtime_episode_bundle,
    run_program_runtime_episode,
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
    SoomfonRuntimeCustody,
    acquire_suite_lock,
    append_terminal,
    create_attempt_marker,
    default_state_root,
    ensure_private_tree,
    fsync_private_tree,
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
from dspx.services.soomfon_evaluation_runtime import (
    arm_parent_death as _arm_parent_death,
    assert_child_group_quiescent as _assert_child_group_quiescent,
    create_child_runtime_directory,
    terminate_child_group as _terminate_child_group,
    validate_child_working_directory,
)


_SUITE_SCHEMA = "soomfon-dspy33-evaluation-suite-v1"
_CHILD_TIMEOUT_SECONDS = 240


SoomfonEvaluationExecutorError, _repo_root = RuntimeError, Path.cwd


def _run_child(
    *,
    case: Mapping[str, Any],
    staged_manifest: Path,
    raw_root: Path,
    child_environment: Mapping[str, str],
    contract_sha256: str,
    marker_fd: int,
    ledger_fd: int,
    lock_fd: int,
) -> tuple[int, int]:
    inputs_path = raw_root / "inputs.json"
    inputs_sha256 = _write_private_json(
        inputs_path,
        {
            "inputs": {
                "transcription": case["transcription"],
                "persona_intent": case["persona_intent"],
            }
        },
    )
    _child_cwd, child_cwd_fd = ensure_private_tree(raw_root / "empty-cwd")
    if os.listdir(f"/proc/self/fd/{child_cwd_fd}"):
        os.close(child_cwd_fd)
        raise SoomfonEvaluationExecutorError("child working directory is not empty")
    raw_root_fd = os.open(
        raw_root,
        os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
    )
    if set(os.listdir(f"/proc/self/fd/{raw_root_fd}")) != {
        "inputs.json",
        "empty-cwd",
    }:
        os.close(raw_root_fd)
        os.close(child_cwd_fd)
        raise SoomfonEvaluationExecutorError("raw custody root is not empty")
    argv = (
        sys.executable,
        "-I",
        "-P",
        "-m",
        "dspx.services.soomfon_evaluation_executor",
        "--child",
        "--manifest",
        str(staged_manifest),
        "--expected-manifest-sha256",
        str(case["manifest_sha256"]),
        "--expected-receipt-sha256",
        str(case["manifest_receipt_sha256"]),
        "--mode",
        str(case["mode"]),
        "--contract-sha256",
        contract_sha256,
        "--marker-fd",
        str(marker_fd),
        "--ledger-fd",
        str(ledger_fd),
        "--lock-fd",
        str(lock_fd),
        "--raw-root-fd",
        str(raw_root_fd),
        "--cwd-fd",
        str(child_cwd_fd),
        "--parent-pid",
        str(os.getpid()),
        "--inputs",
        str(inputs_path),
        "--expected-inputs-sha256",
        inputs_sha256,
        "--outdir",
        str(raw_root / "runtime"),
    )
    started = time.monotonic_ns()
    previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT})
    process: subprocess.Popen[bytes] | None = None
    mask_restored = False
    try:
        try:
            process = subprocess.Popen(
                argv,
                cwd=f"/proc/self/fd/{child_cwd_fd}",
                env=dict(child_environment),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                pass_fds=(
                    marker_fd,
                    ledger_fd,
                    lock_fd,
                    raw_root_fd,
                    child_cwd_fd,
                ),
                start_new_session=True,
            )
            signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
            mask_restored = True
            returncode = process.wait(timeout=_CHILD_TIMEOUT_SECONDS)
            _assert_child_group_quiescent(process)
            return returncode, max(0, (time.monotonic_ns() - started) // 1_000_000)
        except BaseException:
            if process is not None:
                _terminate_child_group(process)
            raise
    finally:
        if not mask_restored:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
        os.close(raw_root_fd)
        os.close(child_cwd_fd)


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
    *, ledger_fd: int, contract_sha256: str, mode: str
) -> tuple[int, str]:
    """Return only after the attempted marker and containing ledger are fsynced."""

    return create_attempt_marker(
        ledger_fd=ledger_fd,
        contract_sha256=contract_sha256,
        mode=mode,
    )


def execute_soomfon_evaluation_suite(
    *, expected_contract_sha256: str, environment: Mapping[str, str] | None = None
) -> dict[str, object]:
    repo_root = _repo_root()
    contract, contract_sha256, contract_path = load_hash_bound_soomfon_contract(
        repo_root=repo_root,
        expected_sha256=expected_contract_sha256,
    )
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
    for fd in (base_fd, raw_parent_fd, stage_parent_fd, tmp_fd):
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
            marker_fd, marker_name = _persist_attempt_before_effect(
                ledger_fd=ledger_fd,
                contract_sha256=contract_sha256,
                mode=mode,
            )
            try:
                try:
                    staged_manifest = stage_candidate(case, stage_parent / mode)
                    raw_root, raw_fd = ensure_private_tree(raw_parent / mode)
                    os.close(raw_fd)
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
            "backend_locality": "not_verified",
            "case_results": results,
            "routing_mutated": False,
            "promotion": False,
            "activation": False,
        }
        _write_private_json(suite_root / "suite-result.json", payload)
        return payload
    finally:
        os.close(ledger_fd)
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
        os.close(suite_fd)


def _child_main(args: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--child", action="store_true", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--expected-receipt-sha256", required=True)
    parser.add_argument("--mode", choices=EXPECTED_MODES, required=True)
    parser.add_argument("--contract-sha256", required=True)
    parser.add_argument("--marker-fd", type=int, required=True)
    parser.add_argument("--ledger-fd", type=int, required=True)
    parser.add_argument("--lock-fd", type=int, required=True)
    parser.add_argument("--raw-root-fd", type=int, required=True)
    parser.add_argument("--cwd-fd", type=int, required=True)
    parser.add_argument("--parent-pid", type=int, required=True)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--expected-inputs-sha256", required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    parsed = parser.parse_args(args)
    previous_umask = os.umask(0o077)
    runtime_fd = -1
    try:
        try:
            _arm_parent_death(parsed.parent_pid)
            validate_child_working_directory(
                cwd_fd=parsed.cwd_fd,
                raw_root_fd=parsed.raw_root_fd,
            )
            runtime_path, runtime_fd = create_child_runtime_directory(
                raw_root_fd=parsed.raw_root_fd,
                inputs_path=parsed.inputs,
                outdir=parsed.outdir,
            )
            custody = SoomfonRuntimeCustody(
                contract_sha256=parsed.contract_sha256,
                mode=parsed.mode,
                expected_manifest_sha256=parsed.expected_manifest_sha256,
                expected_receipt_sha256=parsed.expected_receipt_sha256,
                staged_manifest_path=parsed.manifest.resolve(),
                inputs_path=parsed.inputs.resolve(),
                expected_inputs_sha256=parsed.expected_inputs_sha256,
                outdir=parsed.outdir.resolve(),
                raw_root_fd=parsed.raw_root_fd,
                runtime_fd=runtime_fd,
                marker_fd=parsed.marker_fd,
                ledger_fd=parsed.ledger_fd,
                lock_fd=parsed.lock_fd,
            )
            run_program_runtime_episode(
                manifest_path=parsed.manifest,
                inputs_path=parsed.inputs,
                outdir=runtime_path,
                contract_mode="none",
                skip_oracle_index=True,
                capture_replay_fixture=False,
                run_oracle_semantic=False,
                soomfon_custody=custody,
            )
        except Exception:
            return 2
        return 0
    finally:
        os.umask(previous_umask)
        if runtime_fd >= 0:
            os.close(runtime_fd)


if __name__ == "__main__":
    raise SystemExit(_child_main(sys.argv[1:]))

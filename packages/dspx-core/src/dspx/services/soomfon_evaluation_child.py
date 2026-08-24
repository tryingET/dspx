"""Descriptor-bound child process supervision for Soomfon evaluation."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from dspx.services.program_runtime_episode import run_program_runtime_episode
from dspx.services.soomfon_evaluation_contract import EXPECTED_MODES
from dspx.services.soomfon_evaluation_custody import (
    SoomfonRuntimeCustody,
    ensure_private_tree,
)
from dspx.services.soomfon_evaluation_filesystem import (
    write_private_json_exclusive as _write_private_json,
)
from dspx.services.soomfon_evaluation_runtime import (
    arm_parent_death as _arm_parent_death,
    assert_child_group_quiescent as _assert_child_group_quiescent,
    create_child_runtime_directory,
    terminate_child_group as _terminate_child_group,
    validate_child_working_directory,
)

_CHILD_TIMEOUT_SECONDS = 240
SoomfonEvaluationExecutorError = RuntimeError


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
    provider_journal_fd: int,
    execution_task_id: int,
    authorization_sha256: str,
    ak_reconciliation_sha256: str,
    authorization_path: Path,
    repo_root: Path,
    owner_source_root: Path,
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
        "-B",
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
        "--provider-journal-fd",
        str(provider_journal_fd),
        "--execution-task-id",
        str(execution_task_id),
        "--authorization-sha256",
        authorization_sha256,
        "--ak-reconciliation-sha256",
        ak_reconciliation_sha256,
        "--authorization-path",
        str(authorization_path),
        "--repo-root",
        str(repo_root),
        "--owner-source-root",
        str(owner_source_root),
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
                env={**child_environment, "PYTHONDONTWRITEBYTECODE": "1"},
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                pass_fds=(
                    marker_fd,
                    ledger_fd,
                    lock_fd,
                    provider_journal_fd,
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


def _revalidate_child_authorization(
    *,
    path: Path,
    expected_sha256: str,
    repo_root: Path,
    contract_sha256: str,
    execution_task_id: int,
    ak_reconciliation_sha256: str,
) -> None:
    """Reconcile AK and loaded DSPx bytes before owner/provider access."""

    from dspx.services.soomfon_evaluation_authorization import (
        validate_execution_authorization,
    )

    validated = validate_execution_authorization(
        path=path,
        expected_sha256=expected_sha256,
        repo_root=repo_root,
        contract_sha256=contract_sha256,
    )
    if (
        validated.execution_task_id != execution_task_id
        or validated.authorization_sha256 != expected_sha256
        or validated.ak_reconciliation_sha256 != ak_reconciliation_sha256
    ):
        raise SoomfonEvaluationExecutorError("child AK authorization identity drifts")
    from dspx.services.soomfon_evaluation_dspx_identity import (
        preload_security_critical_dspx_modules,
        verify_executing_dspx_artifact,
    )

    preload_security_critical_dspx_modules()
    verify_executing_dspx_artifact(
        repo_root=repo_root, artifact=validated.dspx_artifact
    )


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
    parser.add_argument("--provider-journal-fd", type=int, required=True)
    parser.add_argument("--execution-task-id", type=int, required=True)
    parser.add_argument("--authorization-sha256", required=True)
    parser.add_argument("--ak-reconciliation-sha256", required=True)
    parser.add_argument("--authorization-path", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--owner-source-root", type=Path, required=True)
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
            _revalidate_child_authorization(
                path=parsed.authorization_path,
                expected_sha256=parsed.authorization_sha256,
                repo_root=parsed.repo_root,
                contract_sha256=parsed.contract_sha256,
                execution_task_id=parsed.execution_task_id,
                ak_reconciliation_sha256=parsed.ak_reconciliation_sha256,
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
                provider_journal_fd=parsed.provider_journal_fd,
                execution_task_id=parsed.execution_task_id,
                authorization_sha256=parsed.authorization_sha256,
                ak_reconciliation_sha256=parsed.ak_reconciliation_sha256,
                authorization_path=parsed.authorization_path.resolve(),
                repo_root=parsed.repo_root.resolve(),
                owner_source_root=parsed.owner_source_root,
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

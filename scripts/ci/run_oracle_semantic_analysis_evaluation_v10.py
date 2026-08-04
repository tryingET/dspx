#!/usr/bin/env python3
# summary: "Standard-library bootstrap and offline controls for the AK-4643 v10 evaluator."
from __future__ import annotations

# Deliberately standard-library-only above and throughout _consume_attempt. DSPx and
# provider-adjacent imports occur only after the fixed task attempt is durable.
import argparse
import hashlib
import json
import os
import pwd
import stat
import sys
from pathlib import Path
from typing import Any

_TASK_ID = 4643
_ATTEMPT = "attempt"
_EVENT_SCHEMA = "dspx-oracle-semantic-v10-event-v1"
_LEDGER_SCHEMA = "dspx-oracle-semantic-v10-ledger-v1"
_CASE_ORDER = (
    "authority-boundary",
    "causal-calibration",
    "review-only-transition",
    "provenance-drift",
)
_SOURCE_PATHS = (
    "packages/dspx-core/src/dspx/dspy_lm_auth_lm.py",
    "packages/dspx-core/src/dspx/model_roles.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_backend.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_contract.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_scoring.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_artifacts_v10.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_contract_v10.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_evaluation_v10.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_identity_v10.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_verification_v10.py",
    "scripts/ci/run_oracle_semantic_analysis_evaluation_v10.py",
)
_ROUTE = {"provider": "dspy-lm-auth", "model": "codex/gpt-5.6-sol", "reasoning_effort": "max"}  # fmt: skip


def _fixed_state_root() -> Path:
    home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    return (
        home
        / ".local"
        / "state"
        / "dspx"
        / "oracle-semantic-analysis-evaluations"
        / f"AK-{_TASK_ID}"
    )


def _require_private_state(
    state: Path, *, _test_owner_home: Path | None = None
) -> Path:
    target = state.expanduser().absolute()
    home = (_test_owner_home or Path(pwd.getpwuid(os.getuid()).pw_dir)).absolute()
    expected = (
        _fixed_state_root() if _test_owner_home is None else home / f"AK-{_TASK_ID}"
    )
    if target != expected:
        raise RuntimeError("task state root is not the fixed AK-4643 root")
    try:
        relative = target.relative_to(home)
    except ValueError as exc:
        raise RuntimeError("task state escaped the owner home") from exc
    current = home
    for index, part in enumerate(relative.parts):
        current /= part
        info = current.lstat()
        require_private = index >= max(0, len(relative.parts) - 2)
        if (
            not stat.S_ISDIR(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or info.st_uid != os.getuid()
            or (require_private and stat.S_IMODE(info.st_mode) != 0o700)
        ):
            raise RuntimeError("task-state ancestor identity/mode drift")
    return target


def _write(path: Path, payload: dict[str, Any]) -> None:
    parent = path.parent.lstat()
    if (
        not stat.S_ISDIR(parent.st_mode)
        or stat.S_ISLNK(parent.st_mode)
        or parent.st_uid != os.getuid()
        or stat.S_IMODE(parent.st_mode) != 0o700
    ):
        raise RuntimeError("artifact parent identity/mode drift")
    fd = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600
    )
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
        ):
            raise RuntimeError("artifact target identity drift")
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            fd = -1
            json.dump(payload, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if fd >= 0:
            os.close(fd)
    directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _bootstrap_event(attempt: Path, kind: str, **facts: Any) -> None:
    events = attempt / "events"
    names = sorted(path.name for path in events.iterdir())
    if names != [f"{index:06d}.json" for index in range(len(names))]:
        raise RuntimeError("attempt event history drift")
    _write(
        events / f"{len(names):06d}.json",
        {
            "schema_version": _EVENT_SCHEMA,
            "ak_task_id": _TASK_ID,
            "sequence": len(names),
            "kind": kind,
            **facts,
        },
    )


def _read_receipt(path: Path) -> tuple[dict[str, Any], bytes]:
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_nlink != 1
        or stat.S_IMODE(info.st_mode) != 0o600
    ):
        raise RuntimeError("pre-entry receipt identity/mode drift")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        raw = os.read(fd, 1_500_001)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    if len(raw) > 1_500_000 or (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise RuntimeError("pre-entry receipt changed or exceeded its bound")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise TypeError("pre-entry receipt must be an object")
    return payload, raw


def _hex(value: object, length: int = 64) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value)
    )


def _preentry_receipts(
    state_root: Path, *, _test_owner_home: Path | None = None
) -> None:
    state = _require_private_state(state_root, _test_owner_home=_test_owner_home)
    review, review_raw = _read_receipt(state / "candidate-review.json")
    gate, _ = _read_receipt(state / "live-gate.json")
    review_keys = {
        "schema_version",
        "ak_task_id",
        "decision",
        "reviewer",
        "review_ref",
        "contract_sha256",
        "source_hashes",
        "request_hashes",
        "dependency_identity",
        "candidate_commit",
        "candidate_tree",
    }
    dependency_keys = {
        "distribution",
        "version",
        "module_origin",
        "module_sha256",
        "module_tree_sha256",
        "distribution_payload_count",
        "distribution_payload_sha256",
        "direct_url_sha256",
        "record_sha256",
        "editable",
    }
    sources = review.get("source_hashes")
    requests = review.get("request_hashes")
    dependency = review.get("dependency_identity")
    sources_ok = (
        isinstance(sources, dict)
        and set(sources) == set(_SOURCE_PATHS)
        and all(
            isinstance(sources[path], dict)
            and sources[path] == {"path": path, "sha256": sources[path].get("sha256")}
            and _hex(sources[path].get("sha256"))
            for path in _SOURCE_PATHS
        )
    )
    requests_ok = (
        isinstance(requests, dict)
        and set(requests) == set(_CASE_ORDER)
        and all(_hex(requests[case_id]) for case_id in _CASE_ORDER)
    )
    dependency_ok = (
        isinstance(dependency, dict)
        and set(dependency) == dependency_keys
        and dependency.get("distribution") == "tryinget-dspy-lm-auth"
        and dependency.get("version") == "0.1.5"
        and isinstance(dependency.get("module_origin"), str)
        and Path(dependency["module_origin"]).is_absolute()
        and isinstance(dependency.get("distribution_payload_count"), int)
        and not isinstance(dependency.get("distribution_payload_count"), bool)
        and dependency["distribution_payload_count"] > 0
        and isinstance(dependency.get("editable"), bool)
        and all(
            _hex(dependency.get(field))
            for field in (
                "module_sha256",
                "module_tree_sha256",
                "distribution_payload_sha256",
                "direct_url_sha256",
                "record_sha256",
            )
        )
    )
    expected_gate = {
        "schema_version": "dspx-oracle-semantic-v10-live-gate-v1",
        "ak_task_id": _TASK_ID,
        "decision": "AUTHORIZE_EXACTLY_ONE_CORPUS_PROCESS",
        "gate_ref": gate.get("gate_ref"),
        "candidate_review_sha256": hashlib.sha256(review_raw).hexdigest(),
        "contract_sha256": review.get("contract_sha256"),
        "source_hashes": sources,
        "request_hashes": requests,
        "candidate_commit": review.get("candidate_commit"),
        "candidate_tree": review.get("candidate_tree"),
        "route": _ROUTE,
        "dependency_identity": dependency,
        "maximum_corpus_processes": 1,
        "fallback_allowed": False,
        "retry_allowed": False,
    }
    if (
        set(review) != review_keys
        or review.get("schema_version")
        != "dspx-oracle-semantic-v10-candidate-review-v1"
        or review.get("ak_task_id") != _TASK_ID
        or review.get("decision") != "ACCEPT_CANDIDATE_FOR_TASK_GATE"
        or not str(review.get("reviewer") or "").strip()
        or not str(review.get("review_ref") or "").strip()
        or not _hex(review.get("contract_sha256"))
        or not _hex(review.get("candidate_commit"), 40)
        or not _hex(review.get("candidate_tree"), 40)
        or not sources_ok
        or not requests_ok
        or not dependency_ok
        or gate != expected_gate
        or not str(gate.get("gate_ref") or "").strip()
    ):
        raise RuntimeError(
            "pre-entry receipts do not exactly authorize this one process"
        )


def _consume_attempt(state_root: Path, *, _test_owner_home: Path | None = None) -> Path:
    state = _require_private_state(state_root, _test_owner_home=_test_owner_home)
    attempt = state / _ATTEMPT
    try:
        attempt.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise RuntimeError(
            "AK-4643 attempt is already consumed; retry is forbidden"
        ) from exc
    os.chmod(attempt, 0o700)
    events = attempt / "events"
    events.mkdir(mode=0o700)
    os.chmod(events, 0o700)
    _write(
        attempt / "ledger.json",
        {
            "schema_version": _LEDGER_SCHEMA,
            "ak_task_id": _TASK_ID,
            "status": "consumed",
            "maximum_evaluation_processes": 1,
            "retry_allowed": False,
            "root": str(attempt),
        },
    )
    _bootstrap_event(
        attempt, "attempt_consumed", evaluation_processes=1, retry_allowed=False
    )
    directory = os.open(state, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return attempt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("contract-check")
    check.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    review = sub.add_parser("candidate-review")
    review.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    review.add_argument("--reviewer", required=True)
    review.add_argument("--review-ref", required=True)
    review.add_argument("--decision", required=True)
    gate = sub.add_parser("live-gate")
    gate.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    gate.add_argument("--gate-ref", required=True)
    gate.add_argument("--decision", required=True)
    run = sub.add_parser("run")
    run.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    verify = sub.add_parser("verify")
    verify.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    return parser


def _post_entry_failure(attempt: Path, classification: str) -> None:
    kinds: list[str] = []
    active_case: str | None = None
    try:
        for path in sorted((attempt / "events").iterdir()):
            event = json.loads(path.read_text())
            kind = str(event.get("kind"))
            kinds.append(kind)
            if kind == "case_started":
                active_case = str(event.get("case_id") or "")
            elif kind in {"case_scored", "case_error"}:
                active_case = None
        if "terminal" not in kinds:
            if active_case:
                _bootstrap_event(
                    attempt,
                    "case_error",
                    case_id=active_case,
                    classification=classification,
                )
            else:
                _bootstrap_event(
                    attempt, "preflight_error", classification=classification
                )
            _bootstrap_event(
                attempt,
                "terminal",
                disposition=(
                    "effect_indeterminate"
                    if kinds.count("effect_possible") > kinds.count("effect_observed")
                    else "error"
                ),
                result_sha256=None,
            )
    except Exception:  # noqa: BLE001,S110 - consumed marker remains authoritative
        # The immutable consumed marker still forbids retry. A later verifier can
        # classify any open effect interval without trusting this process.
        pass


def _run(
    repo_root: Path, state_root: Path, *, _test_owner_home: Path | None = None
) -> int:
    try:
        _preentry_receipts(state_root, _test_owner_home=_test_owner_home)
        attempt = _consume_attempt(state_root, _test_owner_home=_test_owner_home)
    except Exception as exc:  # noqa: BLE001 - closed CLI boundary
        print(f"error: {type(exc).__name__}", file=sys.stderr)
        return 2
    try:
        from dspx.services.program_oracle_semantic_evaluation_v10 import (
            evaluate_consumed,
        )

        expected = (
            repo_root.expanduser().resolve()
            / "scripts/ci/run_oracle_semantic_analysis_evaluation_v10.py"
        )
        if Path(__file__).resolve() != expected:
            raise RuntimeError("runner source origin drift")
        result = evaluate_consumed(
            repo_root=repo_root,
            state_root=state_root,
            _test_owner_home=_test_owner_home,
        )
        print(
            json.dumps(
                {
                    "artifact_root": str(attempt),
                    "empirical_gate": result["empirical_gate"],
                },
                sort_keys=True,
            )
        )
        return 0 if result["empirical_gate"] == "passed" else 1
    except BaseException as exc:  # noqa: BLE001 - includes interruption after consumption
        _post_entry_failure(attempt, f"post_entry_{type(exc).__name__}")
        print(f"error: post-entry {type(exc).__name__}", file=sys.stderr)
        return 2


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    state_root = _fixed_state_root()
    if args.command == "run":
        return _run(args.repo_root, state_root)
    try:
        if args.command == "contract-check":
            from dspx.services.program_oracle_semantic_contract_v10 import (
                load_candidate,
                request_hashes,
            )

            contract, semantics, digest = load_candidate(args.repo_root)
            print(
                json.dumps(
                    {
                        "status": "accepted_zero_process_candidate",
                        "contract_sha256": digest,
                        "request_hashes": request_hashes(contract, semantics),
                    },
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "candidate-review":
            from dspx.services.program_oracle_semantic_identity_v10 import (
                create_candidate_review,
            )

            payload = create_candidate_review(
                repo_root=args.repo_root,
                state_root=state_root,
                reviewer=args.reviewer,
                review_ref=args.review_ref,
                decision=args.decision,
            )
        elif args.command == "live-gate":
            from dspx.services.program_oracle_semantic_identity_v10 import (
                create_live_gate,
            )

            payload = create_live_gate(
                repo_root=args.repo_root,
                state_root=state_root,
                gate_ref=args.gate_ref,
                decision=args.decision,
            )
        else:
            from dspx.services.program_oracle_semantic_verification_v10 import (
                verify_evaluation,
            )

            payload = verify_evaluation(repo_root=args.repo_root, state_root=state_root)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return (
            0
            if payload.get("artifact_integrity_review", "accepted") == "accepted"
            else 1
        )
    except Exception as exc:  # noqa: BLE001 - closed CLI boundary
        print(f"error: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

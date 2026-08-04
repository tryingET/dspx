#!/usr/bin/env python3
# summary: "Standard-library bootstrap and offline controls for the AK-4643 v10 evaluator."
from __future__ import annotations

# fmt: off

# The run path remains standard-library-only until the fixed attempt is durable and
# the reviewed Git/source/dependency identities have been revalidated.
import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import pwd
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, cast
from urllib.parse import unquote, urlparse

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
    "packages/dspx-core/src/dspx/__init__.py",
    "packages/dspx-core/src/dspx/capabilities.py",
    "packages/dspx-core/src/dspx/claude_cli_lm.py",
    "packages/dspx-core/src/dspx/codex_exec_lm.py",
    "packages/dspx-core/src/dspx/dspy_lm_auth_lm.py",
    "packages/dspx-core/src/dspx/dtos.py",
    "packages/dspx-core/src/dspx/gemini_cli_lm.py",
    "packages/dspx-core/src/dspx/lm_base.py",
    "packages/dspx-core/src/dspx/model_roles.py",
    "packages/dspx-core/src/dspx/multi_provider_lm.py",
    "packages/dspx-core/src/dspx/pi_rpc_client.py",
    "packages/dspx-core/src/dspx/pi_rpc_lm.py",
    "packages/dspx-core/src/dspx/policy.py",
    "packages/dspx-core/src/dspx/redaction.py",
    "packages/dspx-core/src/dspx/services/__init__.py",
    "packages/dspx-core/src/dspx/services/program_oracle_secret_policy.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_backend.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_contract.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_evaluation.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_scoring.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_artifacts_v10.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_contract_v10.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_evaluation_v10.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_identity_v10.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_verification_v10.py",
    "packages/dspx-core/src/dspx/validators.py",
    "scripts/ci/run_oracle_semantic_analysis_evaluation_v10.py",
)
_ROUTE = {"provider": "dspy-lm-auth", "model": "codex/gpt-5.6-sol", "reasoning_effort": "max"}  # fmt: skip


def _fixed_state_root() -> Path:
    return Path(pwd.getpwuid(os.getuid()).pw_dir) / ".local/state/dspx/oracle-semantic-analysis-evaluations" / f"AK-{_TASK_ID}"


def _require_private_state(state: Path, *, _test_owner_home: Path | None = None) -> Path:
    target = state.expanduser().absolute()
    home = (_test_owner_home or Path(pwd.getpwuid(os.getuid()).pw_dir)).absolute()
    expected = _fixed_state_root() if _test_owner_home is None else home / f"AK-{_TASK_ID}"
    if target != expected:
        raise RuntimeError("task state root is not the fixed AK-4643 root")
    current = home
    try:
        parts = target.relative_to(home).parts
    except ValueError as exc:
        raise RuntimeError("task state escaped the owner home") from exc
    for index, part in enumerate(parts):
        current /= part
        info = current.lstat()
        private = index >= max(0, len(parts) - 2)
        if (
            not stat.S_ISDIR(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or info.st_uid != os.getuid()
            or private
            and stat.S_IMODE(info.st_mode) != 0o700
        ):
            raise RuntimeError("task-state ancestor identity/mode drift")
    return target


def _json_bytes(payload: dict[str, Any]) -> bytes:
    raw = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False).encode() + b"\n"
    if len(raw) > 1_500_000:
        raise RuntimeError("artifact exceeds bounded size")
    return raw


def _write(path: Path, payload: dict[str, Any]) -> None:
    parent = path.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode) or stat.S_ISLNK(parent.st_mode) or parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) != 0o700:
        raise RuntimeError("artifact parent identity/mode drift")
    raw = _json_bytes(payload)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
            raise RuntimeError("artifact target identity drift")
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            fd = -1
            stream.write(raw)
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
    _write(events / f"{len(names):06d}.json", {"schema_version": _EVENT_SCHEMA, "ak_task_id": _TASK_ID, "sequence": len(names), "kind": kind, **facts})


def _read(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600:
        raise RuntimeError(f"{label} identity/mode drift")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(fd)
        raw = os.read(fd, 1_500_001)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    if len(raw) > 1_500_000 or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise RuntimeError(f"{label} changed or exceeded its bound")
    def closed_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise RuntimeError(f"{label} contains duplicate JSON keys")
            result[key] = value
        return result
    payload = json.loads(raw, object_pairs_hook=closed_object)
    if not isinstance(payload, dict):
        raise TypeError(f"{label} must be an object")
    return payload, raw


def _hex(value: object, length: int = 64) -> bool:
    return isinstance(value, str) and len(value) == length and all(char in "0123456789abcdef" for char in value)


def _dependency_shape(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != {"dspy", "tryinget-dspy-lm-auth"}:
        return False
    dependencies = cast(dict[str, Any], value)
    expected = {"dspy": ("dspy", "3.1.3"), "tryinget-dspy-lm-auth": ("dspy_lm_auth", "0.1.5")}
    keys = {"distribution", "version", "module", "module_origin", "module_sha256", "module_tree_sha256", "distribution_payload_count", "distribution_payload_sha256", "direct_url_sha256", "record_sha256", "editable"}
    for name, (module, version) in expected.items():
        item = dependencies.get(name)
        if not isinstance(item, dict) or set(item) != keys or re.sub(r"[-_.]+", "-", str(item.get("distribution") or "").lower()) != name or item.get("version") != version or item.get("module") != module or not isinstance(item.get("module_origin"), str) or not Path(item["module_origin"]).is_absolute() or not isinstance(item.get("distribution_payload_count"), int) or item.get("distribution_payload_count", 0) <= 0 or not isinstance(item.get("editable"), bool) or not all(_hex(item.get(field)) for field in ("module_sha256", "module_tree_sha256", "distribution_payload_sha256", "direct_url_sha256", "record_sha256")):
            return False
    return True


def _preentry_receipts(state_root: Path, *, _test_owner_home: Path | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    state = _require_private_state(state_root, _test_owner_home=_test_owner_home)
    review, review_raw = _read(state / "candidate-review.json", "candidate review")
    gate, _ = _read(state / "live-gate.json", "live gate")
    sources, requests, dependency = review.get("source_hashes"), review.get("request_hashes"), review.get("dependency_identity")
    review_keys = {"schema_version", "ak_task_id", "decision", "reviewer", "review_ref", "contract_sha256", "source_hashes", "request_hashes", "dependency_identity", "candidate_commit", "candidate_tree"}
    sources_ok = isinstance(sources, dict) and tuple(sources) == _SOURCE_PATHS and all(sources[path] == {"path": path, "sha256": sources[path].get("sha256")} and _hex(sources[path].get("sha256")) for path in _SOURCE_PATHS)
    requests_ok = isinstance(requests, dict) and tuple(requests) == _CASE_ORDER and all(_hex(requests[case]) for case in _CASE_ORDER)
    expected_gate = {"schema_version": "dspx-oracle-semantic-v10-live-gate-v1", "ak_task_id": _TASK_ID, "decision": "AUTHORIZE_EXACTLY_ONE_CORPUS_PROCESS", "gate_ref": gate.get("gate_ref"), "operator_authorization": "OPERATOR_AUTHORIZED_EXACTLY_ONE_CORPUS_PROCESS", "done_contract_version": 1, "guardrails_version": 1, "candidate_review_sha256": hashlib.sha256(review_raw).hexdigest(), "contract_sha256": review.get("contract_sha256"), "source_hashes": sources, "request_hashes": requests, "candidate_commit": review.get("candidate_commit"), "candidate_tree": review.get("candidate_tree"), "route": _ROUTE, "dependency_identity": dependency, "maximum_corpus_processes": 1, "fallback_allowed": False, "retry_allowed": False}
    if set(review) != review_keys or review.get("schema_version") != "dspx-oracle-semantic-v10-candidate-review-v1" or review.get("ak_task_id") != _TASK_ID or review.get("decision") != "ACCEPT_CANDIDATE_FOR_TASK_GATE" or not str(review.get("reviewer") or "").strip() or not str(review.get("review_ref") or "").strip() or not _hex(review.get("contract_sha256")) or not _hex(review.get("candidate_commit"), 40) or not _hex(review.get("candidate_tree"), 40) or not sources_ok or not requests_ok or not _dependency_shape(dependency) or gate != expected_gate or not re.fullmatch(r"ak:evidence:[0-9]+", str(gate.get("gate_ref") or "")):
        raise RuntimeError("pre-entry receipts do not authorize this one process")
    return review, gate


def _git_env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}


def _git(root: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=False, env=_git_env())
    if result.returncode:
        raise RuntimeError("Git identity check failed")
    return result.stdout


def _dependency(distribution_name: str, module: str, version: str) -> dict[str, Any]:
    distribution = importlib.metadata.distribution(distribution_name)
    spec = importlib.util.find_spec(module)
    if distribution.version != version or spec is None or not spec.origin:
        raise RuntimeError("dependency identity drift")
    observed_name = str(distribution.metadata["Name"])
    if re.sub(r"[-_.]+", "-", observed_name.lower()) != re.sub(r"[-_.]+", "-", distribution_name.lower()):
        raise RuntimeError("dependency distribution-name drift")
    origin = Path(spec.origin).resolve()
    if not origin.is_file() or origin.is_symlink():
        raise RuntimeError("dependency module origin drift")
    direct_raw = (distribution.read_text("direct_url.json") or "").encode()
    record_raw = (distribution.read_text("RECORD") or "").encode()
    direct = json.loads(direct_raw) if direct_raw else {}
    editable = bool(direct.get("dir_info", {}).get("editable"))
    files = list(distribution.files or ())
    located = {Path(str(distribution.locate_file(str(item)))).resolve() for item in files}
    belongs = origin in located
    if editable:
        parsed = urlparse(str(direct.get("url") or ""))
        if parsed.scheme != "file":
            raise RuntimeError("editable dependency source-root drift")
        belongs = origin.is_relative_to(Path(unquote(parsed.path)).resolve())
    if not belongs:
        raise RuntimeError("dependency import is outside distribution")
    module_hashes = {str(path.relative_to(origin.parent)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(origin.parent.rglob("*.py")) if path.is_file() and not path.is_symlink() and "__pycache__" not in path.parts}
    payload_hashes = {str(item): hashlib.sha256(path.read_bytes()).hexdigest() for item in sorted(files, key=str) if (path := Path(str(distribution.locate_file(str(item))))).is_file() and not path.is_symlink()}
    digest = lambda values: hashlib.sha256("\n".join(f"{key} {value}" for key, value in values.items()).encode()).hexdigest()  # noqa: E731
    return {"distribution": observed_name, "version": distribution.version, "module": module, "module_origin": str(origin), "module_sha256": hashlib.sha256(origin.read_bytes()).hexdigest(), "module_tree_sha256": digest(module_hashes), "distribution_payload_count": len(payload_hashes), "distribution_payload_sha256": digest(payload_hashes), "direct_url_sha256": hashlib.sha256(direct_raw).hexdigest(), "record_sha256": hashlib.sha256(record_raw).hexdigest(), "editable": editable}


def _dependency_identity() -> dict[str, Any]:
    return {"dspy": _dependency("dspy", "dspy", "3.1.3"), "tryinget-dspy-lm-auth": _dependency("tryinget-dspy-lm-auth", "dspy_lm_auth", "0.1.5")}


def _postconsume_preimport(repo_root: Path, review: dict[str, Any]) -> None:
    root = repo_root.expanduser().resolve()
    if Path(__file__).resolve() != root / _SOURCE_PATHS[-1]:
        raise RuntimeError("runner source origin drift")
    commit, tree = review["candidate_commit"], review["candidate_tree"]
    if _git(root, "rev-parse", f"{commit}^{{commit}}").decode().strip() != commit or _git(root, "rev-parse", f"{commit}^{{tree}}").decode().strip() != tree or _git(root, "rev-parse", "HEAD").decode().strip() != commit or _git(root, "rev-parse", "HEAD^{tree}").decode().strip() != tree or _git(root, "status", "--porcelain", "--untracked-files=normal"):
        raise RuntimeError("reviewed clean Git identity drift")
    for path in _SOURCE_PATHS:
        digest = review["source_hashes"][path]["sha256"]
        current = (root / path).read_bytes()
        if hashlib.sha256(current).hexdigest() != digest or hashlib.sha256(_git(root, "show", f"{commit}:{path}")).hexdigest() != digest:
            raise RuntimeError(f"reviewed source drift: {path}")
    contract_path = "benchmarks/semantic/oracle-semantic-analysis-evaluation-v10.json"
    contract = (root / contract_path).read_bytes()
    committed_contract = _git(root, "show", f"{commit}:{contract_path}")
    if hashlib.sha256(contract).hexdigest() != review["contract_sha256"] or hashlib.sha256(committed_contract).hexdigest() != review["contract_sha256"] or _dependency_identity() != review["dependency_identity"]:
        raise RuntimeError("contract or dependency identity drift")


def _process_identity(pid: int | None = None) -> dict[str, Any]:
    target = pid or os.getpid()
    boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    raw = Path(f"/proc/{target}/stat").read_text()
    tail = raw[raw.rfind(")") + 2 :].split()
    return {"pid": target, "uid": os.getuid(), "boot_id": boot_id, "proc_start_ticks": int(tail[19])}


def _consume_attempt(state_root: Path, *, _test_owner_home: Path | None = None) -> Path:
    state = _require_private_state(state_root, _test_owner_home=_test_owner_home)
    attempt = state / _ATTEMPT
    try:
        attempt.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise RuntimeError("AK-4643 attempt is already consumed; retry is forbidden") from exc
    os.chmod(attempt, 0o700)
    events = attempt / "events"
    events.mkdir(mode=0o700)
    os.chmod(events, 0o700)
    _write(attempt / "ledger.json", {"schema_version": _LEDGER_SCHEMA, "ak_task_id": _TASK_ID, "status": "consumed", "maximum_evaluation_processes": 1, "retry_allowed": False, "root": str(attempt), "process_identity": _process_identity()})
    _bootstrap_event(attempt, "attempt_consumed", evaluation_processes=1, retry_allowed=False)
    directory = os.open(state, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return attempt


def _recorded_process_inactive(attempt: Path) -> None:
    ledger, _ = _read(attempt / "ledger.json", "ledger")
    recorded = ledger.get("process_identity")
    if not isinstance(recorded, dict):
        raise RuntimeError("recorded process identity missing")
    if recorded.get("uid") != os.getuid():
        raise RuntimeError("recorded process owner drift")
    if Path("/proc/sys/kernel/random/boot_id").read_text().strip() != recorded.get("boot_id"):
        return
    pid = recorded.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        raise RuntimeError("recorded process pid drift")
    try:
        raw = Path(f"/proc/{pid}/stat").read_text()
    except FileNotFoundError:
        return
    tail = raw[raw.rfind(")") + 2 :].split()
    if len(tail) <= 19:
        raise RuntimeError("recorded process status ambiguous")
    if int(tail[19]) != recorded.get("proc_start_ticks") or tail[0] == "Z":
        return
    raise RuntimeError("recorded evaluation process is still active")


def _run(repo_root: Path, state_root: Path, *, _test_owner_home: Path | None = None) -> int:
    try:
        review, _ = _preentry_receipts(state_root, _test_owner_home=_test_owner_home)
        attempt = _consume_attempt(state_root, _test_owner_home=_test_owner_home)
    except Exception as exc:  # noqa: BLE001
        print(f"error: {type(exc).__name__}", file=sys.stderr)
        return 2
    try:
        _postconsume_preimport(repo_root, review)
        from dspx.services.program_oracle_semantic_evaluation_v10 import evaluate_consumed
        result = evaluate_consumed(repo_root=repo_root, state_root=state_root, _test_owner_home=_test_owner_home)
        print(json.dumps({"artifact_root": str(attempt), "empirical_gate": result["empirical_gate"]}, sort_keys=True))
        return 0 if result["empirical_gate"] == "passed" else 1
    except BaseException as exc:  # noqa: BLE001
        print(f"error: post-entry {type(exc).__name__}; finalize-interrupted required", file=sys.stderr)
        return 2


def _finalize_interrupted(repo_root: Path, state_root: Path, *, _test_owner_home: Path | None = None) -> dict[str, Any]:
    state = _require_private_state(state_root, _test_owner_home=_test_owner_home)
    attempt = state / _ATTEMPT
    _recorded_process_inactive(attempt)
    from dspx.services.program_oracle_semantic_evaluation_v10 import finalize_interrupted
    return finalize_interrupted(repo_root=repo_root, state_root=state, _test_owner_home=_test_owner_home)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("contract-check", "candidate-review", "live-gate", "run", "verify", "finalize-interrupted"):
        command = commands.add_parser(name)
        command.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    review = commands.choices["candidate-review"]
    review.add_argument("--reviewer", required=True)
    review.add_argument("--review-ref", required=True)
    review.add_argument("--decision", required=True)
    gate = commands.choices["live-gate"]
    gate.add_argument("--gate-ref", required=True)
    gate.add_argument("--decision", required=True)
    gate.add_argument("--operator-authorization", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    state_root = _fixed_state_root()
    if args.command == "run":
        return _run(args.repo_root, state_root)
    try:
        if args.command == "contract-check":
            from dspx.services.program_oracle_semantic_contract_v10 import load_candidate, request_hashes
            contract, semantics, digest = load_candidate(args.repo_root)
            payload = {"status": "accepted_zero_process_candidate", "contract_sha256": digest, "request_hashes": request_hashes(contract, semantics)}
        elif args.command == "candidate-review":
            from dspx.services.program_oracle_semantic_identity_v10 import create_candidate_review
            payload = create_candidate_review(repo_root=args.repo_root, state_root=state_root, reviewer=args.reviewer, review_ref=args.review_ref, decision=args.decision)
        elif args.command == "live-gate":
            from dspx.services.program_oracle_semantic_identity_v10 import create_live_gate
            payload = create_live_gate(repo_root=args.repo_root, state_root=state_root, gate_ref=args.gate_ref, decision=args.decision, operator_authorization=args.operator_authorization)
        elif args.command == "finalize-interrupted":
            payload = _finalize_interrupted(args.repo_root, state_root)
        else:
            from dspx.services.program_oracle_semantic_verification_v10 import verify_evaluation
            payload = verify_evaluation(repo_root=args.repo_root, state_root=state_root)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload.get("artifact_integrity_review", "accepted") == "accepted" else 1
    except Exception as exc:  # noqa: BLE001
        print(f"error: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

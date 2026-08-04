# summary: "Exact Git, dependency, candidate-review, and live-gate identity for AK-4643."
from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dspx.services.program_oracle_semantic_artifacts_v10 import (
    GATE_SCHEMA,
    REVIEW_SCHEMA,
    ensure_private_directory,
    require_mode,
)
from dspx.services.program_oracle_semantic_contract_v10 import (
    CANDIDATE_RECEIPT,
    EXPECTED_SOURCE_PATHS,
    LIVE_GATE_RECEIPT,
    TASK_ID,
    SemanticV10Error,
    file_sha256,
    load_candidate,
    mapping,
    read_json,
    request_hashes,
    sha256,
    write_exclusive,
)

ROUTE = {
    "provider": "dspy-lm-auth",
    "model": "codex/gpt-5.6-sol",
    "reasoning_effort": "max",
}


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )
    if completed.returncode:
        raise SemanticV10Error("Git identity check failed")
    return completed.stdout.strip()


def committed_identity(
    repo_root: Path,
    commit: str,
    tree: str,
    source_hashes: Mapping[str, Any],
    *,
    require_head: bool = True,
) -> dict[str, Any]:
    root = repo_root.expanduser().resolve()
    if (
        len(commit) != 40
        or len(tree) != 40
        or any(c not in "0123456789abcdef" for c in commit + tree)
    ):
        raise SemanticV10Error(
            "candidate commit/tree must be full lowercase Git identities"
        )
    if (
        _git(root, "rev-parse", f"{commit}^{{commit}}") != commit
        or _git(root, "rev-parse", f"{commit}^{{tree}}") != tree
    ):
        raise SemanticV10Error("reviewed candidate Git identity drift")
    if require_head and (
        _git(root, "rev-parse", "HEAD") != commit
        or _git(root, "rev-parse", "HEAD^{tree}") != tree
    ):
        raise SemanticV10Error("execution HEAD/tree differs from reviewed candidate")
    if require_head and _git(root, "status", "--porcelain", "--untracked-files=normal"):
        raise SemanticV10Error("execution source must be exactly clean")
    for path in EXPECTED_SOURCE_PATHS:
        expected = mapping(source_hashes.get(path), f"source hash {path}").get("sha256")
        blob = subprocess.run(
            ["git", "-C", str(root), "show", f"{commit}:{path}"],
            capture_output=True,
            check=False,
        )
        if (
            blob.returncode
            or sha256(blob.stdout) != expected
            or (require_head and file_sha256(root / path) != expected)
        ):
            raise SemanticV10Error(f"reviewed committed source drift: {path}")
    return {
        "candidate_commit": commit,
        "candidate_tree": tree,
        "source_hashes": dict(source_hashes),
    }


def dependency_identity() -> dict[str, Any]:
    name = "tryinget-dspy-lm-auth"
    try:
        version = importlib.metadata.version(name)
        distribution = importlib.metadata.distribution(name)
        spec = importlib.util.find_spec("dspy_lm_auth")
    except importlib.metadata.PackageNotFoundError as exc:
        raise SemanticV10Error(
            "maintained dspy-lm-auth dependency unavailable"
        ) from exc
    if version != "0.1.5" or spec is None or not spec.origin:
        raise SemanticV10Error("maintained dspy-lm-auth dependency identity drift")
    origin = Path(spec.origin).resolve()
    if not origin.is_file():
        raise SemanticV10Error("maintained dspy-lm-auth module origin drift")
    direct_raw = (distribution.read_text("direct_url.json") or "").encode()
    record_raw = (distribution.read_text("RECORD") or "").encode()
    editable = False
    if direct_raw:
        try:
            direct = json.loads(direct_raw)
            editable = bool(
                mapping(direct.get("dir_info"), "direct_url.dir_info").get("editable")
            )
        except (json.JSONDecodeError, SemanticV10Error) as exc:
            raise SemanticV10Error("dependency direct-url identity drift") from exc
    module_hashes = {
        str(path.relative_to(origin.parent)): file_sha256(path)
        for path in sorted(origin.parent.rglob("*.py"))
        if path.is_file() and "__pycache__" not in path.parts
    }
    module_payload = "\n".join(
        f"{key} {value}" for key, value in module_hashes.items()
    ).encode()
    distribution_hashes: dict[str, str] = {}
    for item in sorted(distribution.files or (), key=str):
        path = Path(str(distribution.locate_file(item)))
        if path.is_file() and not path.is_symlink():
            distribution_hashes[str(item)] = file_sha256(path)
    distribution_payload = "\n".join(
        f"{key} {value}" for key, value in distribution_hashes.items()
    ).encode()
    return {
        "distribution": str(distribution.metadata["Name"]),
        "version": version,
        "module_origin": str(origin),
        "module_sha256": file_sha256(origin),
        "module_tree_sha256": hashlib.sha256(module_payload).hexdigest(),
        "distribution_payload_count": len(distribution_hashes),
        "distribution_payload_sha256": hashlib.sha256(distribution_payload).hexdigest(),
        "direct_url_sha256": hashlib.sha256(direct_raw).hexdigest(),
        "record_sha256": hashlib.sha256(record_raw).hexdigest(),
        "editable": editable,
    }


def _receipt_base(
    repo_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], str, dict[str, str]]:
    contract, semantics, contract_hash = load_candidate(repo_root)
    return contract, semantics, contract_hash, request_hashes(contract, semantics)


def create_candidate_review(
    *,
    repo_root: Path,
    state_root: Path,
    reviewer: str,
    review_ref: str,
    decision: str,
    _test_owner_home: Path | None = None,
) -> dict[str, Any]:
    contract, _, contract_hash, requests = _receipt_base(repo_root)
    root = repo_root.expanduser().resolve()
    commit = _git(root, "rev-parse", "HEAD")
    tree = _git(root, "rev-parse", "HEAD^{tree}")
    source_hashes = mapping(contract["source_bindings"], "source_bindings")
    committed_identity(root, commit, tree, source_hashes)
    dependency = dependency_identity()
    if (
        decision != "ACCEPT_CANDIDATE_FOR_TASK_GATE"
        or not reviewer.strip()
        or not review_ref.strip()
    ):
        raise SemanticV10Error(
            "candidate review must be an explicit attributed acceptance"
        )
    state = ensure_private_directory(
        state_root, create=True, _test_owner_home=_test_owner_home
    )
    payload = {
        "schema_version": REVIEW_SCHEMA,
        "ak_task_id": TASK_ID,
        "decision": decision,
        "reviewer": reviewer,
        "review_ref": review_ref,
        "contract_sha256": contract_hash,
        "source_hashes": source_hashes,
        "request_hashes": requests,
        "dependency_identity": dependency,
        "candidate_commit": commit,
        "candidate_tree": tree,
    }
    write_exclusive(state / CANDIDATE_RECEIPT, payload)
    return payload


def _validate_review(
    review: Mapping[str, Any],
    contract: Mapping[str, Any],
    contract_hash: str,
    requests: Mapping[str, str],
) -> None:
    expected_keys = {
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
    if (
        set(review) != expected_keys
        or review.get("schema_version") != REVIEW_SCHEMA
        or review.get("ak_task_id") != TASK_ID
        or review.get("decision") != "ACCEPT_CANDIDATE_FOR_TASK_GATE"
        or review.get("contract_sha256") != contract_hash
        or review.get("source_hashes") != contract.get("source_bindings")
        or review.get("request_hashes") != dict(requests)
        or not isinstance(review.get("dependency_identity"), Mapping)
        or not str(review.get("reviewer") or "").strip()
        or not str(review.get("review_ref") or "").strip()
    ):
        raise SemanticV10Error("candidate-review receipt drift")


def create_live_gate(
    *,
    repo_root: Path,
    state_root: Path,
    gate_ref: str,
    decision: str,
    _test_owner_home: Path | None = None,
) -> dict[str, Any]:
    state = ensure_private_directory(
        state_root, create=False, _test_owner_home=_test_owner_home
    )
    require_mode(state / CANDIDATE_RECEIPT, 0o600, "candidate review")
    review, review_raw = read_json(state / CANDIDATE_RECEIPT, "candidate review")
    contract, _, contract_hash, requests = _receipt_base(repo_root)
    _validate_review(review, contract, contract_hash, requests)
    committed_identity(
        repo_root,
        str(review["candidate_commit"]),
        str(review["candidate_tree"]),
        mapping(contract["source_bindings"], "source_bindings"),
    )
    dependency = dependency_identity()
    if review.get("dependency_identity") != dependency:
        raise SemanticV10Error("reviewed dependency identity drift")
    if decision != "AUTHORIZE_EXACTLY_ONE_CORPUS_PROCESS" or not gate_ref.strip():
        raise SemanticV10Error(
            "live gate must explicitly authorize exactly one corpus process"
        )
    payload = {
        "schema_version": GATE_SCHEMA,
        "ak_task_id": TASK_ID,
        "decision": decision,
        "gate_ref": gate_ref,
        "candidate_review_sha256": sha256(review_raw),
        "contract_sha256": contract_hash,
        "source_hashes": contract["source_bindings"],
        "request_hashes": requests,
        "candidate_commit": review["candidate_commit"],
        "candidate_tree": review["candidate_tree"],
        "route": ROUTE,
        "dependency_identity": review["dependency_identity"],
        "maximum_corpus_processes": 1,
        "fallback_allowed": False,
        "retry_allowed": False,
    }
    write_exclusive(state / LIVE_GATE_RECEIPT, payload)
    return payload


def validate_receipts(
    *,
    repo_root: Path,
    state_root: Path,
    require_current_commit: bool = True,
    _test_owner_home: Path | None = None,
) -> dict[str, Any]:
    state = ensure_private_directory(
        state_root, create=False, _test_owner_home=_test_owner_home
    )
    require_mode(state / CANDIDATE_RECEIPT, 0o600, "candidate review")
    require_mode(state / LIVE_GATE_RECEIPT, 0o600, "live gate")
    review, review_raw = read_json(state / CANDIDATE_RECEIPT, "candidate review")
    gate, gate_raw = read_json(state / LIVE_GATE_RECEIPT, "live gate")
    contract, semantics, contract_hash = load_candidate(
        repo_root, check_sources=require_current_commit
    )
    requests = request_hashes(contract, semantics)
    _validate_review(review, contract, contract_hash, requests)
    expected_gate = {
        "schema_version": GATE_SCHEMA,
        "ak_task_id": TASK_ID,
        "decision": "AUTHORIZE_EXACTLY_ONE_CORPUS_PROCESS",
        "gate_ref": gate.get("gate_ref"),
        "candidate_review_sha256": sha256(review_raw),
        "contract_sha256": contract_hash,
        "source_hashes": contract["source_bindings"],
        "request_hashes": requests,
        "candidate_commit": review["candidate_commit"],
        "candidate_tree": review["candidate_tree"],
        "route": ROUTE,
        "dependency_identity": review.get("dependency_identity"),
        "maximum_corpus_processes": 1,
        "fallback_allowed": False,
        "retry_allowed": False,
    }
    dependency = review.get("dependency_identity")
    if (
        gate != expected_gate
        or not str(gate.get("gate_ref") or "").strip()
        or not isinstance(dependency, Mapping)
        or (require_current_commit and dependency != dependency_identity())
    ):
        raise SemanticV10Error("live-gate receipt drift")
    identity = committed_identity(
        repo_root,
        str(review["candidate_commit"]),
        str(review["candidate_tree"]),
        mapping(review["source_hashes"], "source_hashes"),
        require_head=require_current_commit,
    )
    return {
        "contract": contract,
        "semantics": semantics,
        "contract_sha256": contract_hash,
        "request_hashes": requests,
        "review": review,
        "review_sha256": sha256(review_raw),
        "gate": gate,
        "gate_sha256": sha256(gate_raw),
        "source_identity": identity,
    }

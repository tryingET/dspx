# summary: "Exact Git, dependency, candidate-review, and live-gate identity for AK-4643."
from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import importlib.util
import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from dspx.services.program_oracle_semantic_artifacts_v10 import (
    GATE_SCHEMA,
    REVIEW_SCHEMA,
    ensure_private_directory,
    require_mode,
)
from dspx.services.program_oracle_semantic_contract_v10 import (
    CANDIDATE_RECEIPT,
    CONTRACT_PATH,
    EXPECTED_SOURCE_PATHS,
    RUNTIME_SOURCE_MODULES,
    SOURCE_MODULE_PATHS,
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


def _git_env() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("GIT_")
    }


def _git_bytes(root: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        check=False,
        env=_git_env(),
    )
    if completed.returncode:
        raise SemanticV10Error("Git identity check failed")
    return completed.stdout


def _git(root: Path, *args: str) -> str:
    try:
        return _git_bytes(root, *args).decode().strip()
    except UnicodeDecodeError as exc:
        raise SemanticV10Error("Git identity output was not UTF-8") from exc


def committed_identity(
    repo_root: Path,
    commit: str,
    tree: str,
    source_hashes: Mapping[str, Any],
    contract_hash: str,
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
        try:
            blob = _git_bytes(root, "show", f"{commit}:{path}")
        except SemanticV10Error as exc:
            raise SemanticV10Error(
                f"reviewed committed source missing: {path}"
            ) from exc
        if sha256(blob) != expected or (
            require_head and file_sha256(root / path) != expected
        ):
            raise SemanticV10Error(f"reviewed committed source drift: {path}")
    contract_blob = _git_bytes(root, "show", f"{commit}:{CONTRACT_PATH}")
    if sha256(contract_blob) != contract_hash or (
        require_head and file_sha256(root / CONTRACT_PATH) != contract_hash
    ):
        raise SemanticV10Error("reviewed committed contract drift")
    return {
        "candidate_commit": commit,
        "candidate_tree": tree,
        "source_hashes": dict(source_hashes),
    }


def _dependency(
    distribution_name: str, module_name: str, version: str
) -> dict[str, Any]:
    try:
        distribution = importlib.metadata.distribution(distribution_name)
        spec = importlib.util.find_spec(module_name)
    except importlib.metadata.PackageNotFoundError as exc:
        raise SemanticV10Error(f"dependency unavailable: {distribution_name}") from exc
    if distribution.version != version or spec is None or not spec.origin:
        raise SemanticV10Error(f"dependency identity drift: {distribution_name}")
    observed_name = str(distribution.metadata["Name"])
    if re.sub(r"[-_.]+", "-", observed_name.lower()) != re.sub(
        r"[-_.]+", "-", distribution_name.lower()
    ):
        raise SemanticV10Error(
            f"dependency distribution-name drift: {distribution_name}"
        )
    origin = Path(spec.origin).resolve()
    if not origin.is_file() or origin.is_symlink():
        raise SemanticV10Error(f"dependency module origin drift: {distribution_name}")
    direct_raw = (distribution.read_text("direct_url.json") or "").encode()
    record_raw = (distribution.read_text("RECORD") or "").encode()
    editable = False
    direct: dict[str, Any] = {}
    if direct_raw:
        try:
            direct = json.loads(direct_raw)
            editable = bool(mapping(direct.get("dir_info"), "dir_info").get("editable"))
        except (json.JSONDecodeError, SemanticV10Error) as exc:
            raise SemanticV10Error("dependency direct-url identity drift") from exc
    files = list(distribution.files or ())
    located = {
        Path(str(distribution.locate_file(str(item)))).resolve() for item in files
    }
    belongs = origin in located
    if editable:
        parsed = urlparse(str(direct.get("url") or ""))
        if parsed.scheme != "file":
            raise SemanticV10Error("editable dependency source-root drift")
        belongs = origin.is_relative_to(Path(unquote(parsed.path)).resolve())
    if not belongs:
        raise SemanticV10Error(
            f"dependency import is outside distribution: {distribution_name}"
        )
    module_hashes = {
        str(path.relative_to(origin.parent)): file_sha256(path)
        for path in sorted(origin.parent.rglob("*.py"))
        if path.is_file() and not path.is_symlink() and "__pycache__" not in path.parts
    }
    distribution_hashes = {
        str(item): file_sha256(path)
        for item in sorted(files, key=lambda value: str(value))
        if (path := Path(str(distribution.locate_file(item)))).is_file()
        and not path.is_symlink()
    }
    digest = lambda values: hashlib.sha256(  # noqa: E731
        "\n".join(f"{key} {value}" for key, value in values.items()).encode()
    ).hexdigest()
    return {
        "distribution": observed_name,
        "version": distribution.version,
        "module": module_name,
        "module_origin": str(origin),
        "module_sha256": file_sha256(origin),
        "module_tree_sha256": digest(module_hashes),
        "distribution_payload_count": len(distribution_hashes),
        "distribution_payload_sha256": digest(distribution_hashes),
        "direct_url_sha256": hashlib.sha256(direct_raw).hexdigest(),
        "record_sha256": hashlib.sha256(record_raw).hexdigest(),
        "editable": editable,
    }


def dependency_identity() -> dict[str, Any]:
    return {
        "dspy": _dependency("dspy", "dspy", "3.1.3"),
        "tryinget-dspy-lm-auth": _dependency(
            "tryinget-dspy-lm-auth", "dspy_lm_auth", "0.1.5"
        ),
    }


def validate_dependency_imports(expected: Mapping[str, Any]) -> None:
    if expected != dependency_identity():
        raise SemanticV10Error("execution dependency payload drift")
    for name in ("dspy", "tryinget-dspy-lm-auth"):
        item = mapping(expected.get(name), f"dependency {name}")
        module = importlib.import_module(str(item.get("module")))
        origin = Path(str(getattr(module, "__file__", ""))).resolve()
        spec_origin = Path(
            str(getattr(getattr(module, "__spec__", None), "origin", ""))
        ).resolve()
        if (
            origin != Path(str(item.get("module_origin"))).resolve()
            or spec_origin != origin
            or file_sha256(origin) != item.get("module_sha256")
        ):
            raise SemanticV10Error(f"dependency import origin drift: {name}")


def expected_loaded_source_identity(
    repo_root: Path, source_hashes: Mapping[str, Any]
) -> dict[str, Any]:
    root = repo_root.expanduser().resolve()
    result: dict[str, Any] = {}
    for name in sorted(RUNTIME_SOURCE_MODULES):
        relative = SOURCE_MODULE_PATHS[name]
        expected = mapping(source_hashes.get(relative), f"source {relative}").get(
            "sha256"
        )
        origin = (root / relative).resolve()
        if file_sha256(origin) != expected:
            raise SemanticV10Error(f"runtime source drift: {name}")
        result[name] = {"path": relative, "origin": str(origin), "sha256": expected}
    return result


def loaded_source_identity(
    repo_root: Path,
    source_hashes: Mapping[str, Any],
    *,
    reject_unexpected: bool = True,
) -> dict[str, Any]:
    expected_identity = expected_loaded_source_identity(repo_root, source_hashes)
    loaded = {
        name
        for name, module in sys.modules.items()
        if (name == "dspx" or name.startswith("dspx."))
        and getattr(module, "__file__", None)
    }
    if not RUNTIME_SOURCE_MODULES.issubset(loaded) or (
        reject_unexpected and loaded != RUNTIME_SOURCE_MODULES
    ):
        raise SemanticV10Error("loaded DSPx module set drift")
    for name, expected in expected_identity.items():
        module = sys.modules[name]
        origin = Path(str(getattr(module, "__file__", ""))).resolve()
        spec_origin = Path(
            str(getattr(getattr(module, "__spec__", None), "origin", ""))
        ).resolve()
        if origin != Path(expected["origin"]) or spec_origin != origin:
            raise SemanticV10Error(f"loaded module origin drift: {name}")
    return expected_identity


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
    committed_identity(root, commit, tree, source_hashes, contract_hash)
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
    operator_authorization: str,
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
        contract_hash,
    )
    dependency = dependency_identity()
    if review.get("dependency_identity") != dependency:
        raise SemanticV10Error("reviewed dependency identity drift")
    if (
        decision != "AUTHORIZE_EXACTLY_ONE_CORPUS_PROCESS"
        or not re.fullmatch(r"ak:evidence:[0-9]+", gate_ref)
        or operator_authorization != "OPERATOR_AUTHORIZED_EXACTLY_ONE_CORPUS_PROCESS"
    ):
        raise SemanticV10Error("live gate lacks typed task/operator authority")
    payload = {
        "schema_version": GATE_SCHEMA,
        "ak_task_id": TASK_ID,
        "decision": decision,
        "gate_ref": gate_ref,
        "operator_authorization": operator_authorization,
        "done_contract_version": 1,
        "guardrails_version": 1,
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
        "operator_authorization": "OPERATOR_AUTHORIZED_EXACTLY_ONE_CORPUS_PROCESS",
        "done_contract_version": 1,
        "guardrails_version": 1,
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
        or not re.fullmatch(r"ak:evidence:[0-9]+", str(gate.get("gate_ref") or ""))
        or not isinstance(dependency, Mapping)
        or (require_current_commit and dependency != dependency_identity())
    ):
        raise SemanticV10Error("live-gate receipt drift")
    identity = committed_identity(
        repo_root,
        str(review["candidate_commit"]),
        str(review["candidate_tree"]),
        mapping(review["source_hashes"], "source_hashes"),
        contract_hash,
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

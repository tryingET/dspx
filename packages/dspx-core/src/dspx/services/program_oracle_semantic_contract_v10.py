# summary: "Validates and materializes the task-fixed AK-4643 semantic v10 contract."
from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from dspx.services.program_oracle_semantic_contract import OracleSemanticRequest
from dspx.services.program_oracle_semantic_scoring import score_analysis

TASK_ID = 4643
CASE_ORDER = (
    "authority-boundary",
    "causal-calibration",
    "review-only-transition",
    "provenance-drift",
)
CONTRACT_PATH = Path("benchmarks/semantic/oracle-semantic-analysis-evaluation-v10.json")
V9_PATH = Path("benchmarks/semantic/oracle-semantic-analysis-evaluation-v9.json")
SEMANTICS_PATH = Path("benchmarks/semantic/oracle-semantic-code-semantics-v1.json")
V9_SHA256 = "d346c4703df46348478ca4d272b766c23eabe6b72ba1ff168bbe911fd3387944"
SEMANTICS_SHA256 = "42ad952318adcde35605c468fc043ae161faf310159203a3c2980a7c51177c41"
DEPENDENCY_POLICY = {
    "distributions": [
        {"distribution": "dspy", "version": "3.1.3", "module": "dspy"},
        {
            "distribution": "tryinget-dspy-lm-auth",
            "version": "0.1.5",
            "module": "dspy_lm_auth",
        },
    ],
    "bind_live_gate_to_observed_identity": True,
}
CANDIDATE_RECEIPT = "candidate-review.json"
LIVE_GATE_RECEIPT = "live-gate.json"
ATTEMPT_DIR = "attempt"
LEDGER_NAME = "ledger.json"
EVENT_DIR = "events"
RESULT_NAME = "evaluation-result.json"
VERIFICATION_NAME = "independent-verification.json"
MAX_ARTIFACT_BYTES = 1_500_000
MAX_EVENT_BYTES = 250_000
INHERITED_KEYS = (
    "claim_scope",
    "thresholds",
    "privacy_and_effects",
    "field_rubric",
    "offline_adjudication",
    "cases",
    "falsifiers",
    "nonclaims",
    "evidence_ref_rubric",
    "confidence_rubric",
    "remediation",
    "semantic_materialization",
    "code_semantics_binding",
)
SOURCE_MODULE_PATHS = {
    "dspx": "packages/dspx-core/src/dspx/__init__.py",
    "dspx.capabilities": "packages/dspx-core/src/dspx/capabilities.py",
    "dspx.claude_cli_lm": "packages/dspx-core/src/dspx/claude_cli_lm.py",
    "dspx.codex_exec_lm": "packages/dspx-core/src/dspx/codex_exec_lm.py",
    "dspx.dspy_lm_auth_lm": "packages/dspx-core/src/dspx/dspy_lm_auth_lm.py",
    "dspx.dtos": "packages/dspx-core/src/dspx/dtos.py",
    "dspx.gemini_cli_lm": "packages/dspx-core/src/dspx/gemini_cli_lm.py",
    "dspx.lm_base": "packages/dspx-core/src/dspx/lm_base.py",
    "dspx.model_roles": "packages/dspx-core/src/dspx/model_roles.py",
    "dspx.multi_provider_lm": "packages/dspx-core/src/dspx/multi_provider_lm.py",
    "dspx.pi_rpc_client": "packages/dspx-core/src/dspx/pi_rpc_client.py",
    "dspx.pi_rpc_lm": "packages/dspx-core/src/dspx/pi_rpc_lm.py",
    "dspx.policy": "packages/dspx-core/src/dspx/policy.py",
    "dspx.redaction": "packages/dspx-core/src/dspx/redaction.py",
    "dspx.services": "packages/dspx-core/src/dspx/services/__init__.py",
    "dspx.services.program_oracle_secret_policy": "packages/dspx-core/src/dspx/services/program_oracle_secret_policy.py",
    "dspx.services.program_oracle_semantic_backend": "packages/dspx-core/src/dspx/services/program_oracle_semantic_backend.py",
    "dspx.services.program_oracle_semantic_contract": "packages/dspx-core/src/dspx/services/program_oracle_semantic_contract.py",
    "dspx.services.program_oracle_semantic_evaluation": "packages/dspx-core/src/dspx/services/program_oracle_semantic_evaluation.py",
    "dspx.services.program_oracle_semantic_scoring": "packages/dspx-core/src/dspx/services/program_oracle_semantic_scoring.py",
    "dspx.services.program_oracle_semantic_artifacts_v10": "packages/dspx-core/src/dspx/services/program_oracle_semantic_artifacts_v10.py",
    "dspx.services.program_oracle_semantic_contract_v10": "packages/dspx-core/src/dspx/services/program_oracle_semantic_contract_v10.py",
    "dspx.services.program_oracle_semantic_evaluation_v10": "packages/dspx-core/src/dspx/services/program_oracle_semantic_evaluation_v10.py",
    "dspx.services.program_oracle_semantic_identity_v10": "packages/dspx-core/src/dspx/services/program_oracle_semantic_identity_v10.py",
    "dspx.services.program_oracle_semantic_verification_v10": "packages/dspx-core/src/dspx/services/program_oracle_semantic_verification_v10.py",
    "dspx.validators": "packages/dspx-core/src/dspx/validators.py",
}
EXPECTED_SOURCE_PATHS = (
    *SOURCE_MODULE_PATHS.values(),
    "scripts/ci/run_oracle_semantic_analysis_evaluation_v10.py",
)
RUNTIME_SOURCE_MODULES = frozenset(SOURCE_MODULE_PATHS) - {
    "dspx.services.program_oracle_semantic_verification_v10"
}


class SemanticV10Error(ValueError):
    """Raised when task-4643 candidate or retained evidence fails closed."""


EVENT_CLASSIFICATIONS = {
    "preflight_error": frozenset(
        {"post_entry_preflight_error", "interrupted_process_terminated"}
    ),
    "attempt_error": frozenset(
        {"post_preflight_error", "interrupted_process_terminated"}
    ),
    "case_error": frozenset(
        {
            "backend_call_incomplete",
            "adapter_cardinality_drift",
            "effect_outcome_unresolved",
            "route_identity_error",
            "response_retention_error",
            "typed_response_error",
            "executed_model_drift",
            "response_schema_error",
            "case_processing_error",
            "interrupted_effect_unresolved",
            "interrupted_case_incomplete",
        }
    ),
}


def validate_route_environment(route: Mapping[str, str]) -> None:
    expected = {
        "DSPX_ORACLE_SEMANTIC_BACKEND": "live",
        "DSPX_ORACLE_SEMANTIC_PROVIDER": route["provider"],
        "DSPX_ORACLE_SEMANTIC_MODEL": route["model"],
        "DSPX_ORACLE_SEMANTIC_REASONING_EFFORT": route["reasoning_effort"],
    }
    if {key: os.getenv(key) for key in expected} != expected:
        raise SemanticV10Error("exact live route environment drift")
    if os.getenv("DSPX_ORACLE_SEMANTIC_FIXTURE_PATH"):
        raise SemanticV10Error("fixture route is forbidden")


def validate_attempt_ledger(ledger: Mapping[str, Any], attempt: Path) -> None:
    process = ledger.get("process_identity")
    valid = (
        ledger
        == {
            "schema_version": "dspx-oracle-semantic-v10-ledger-v1",
            "ak_task_id": TASK_ID,
            "status": "consumed",
            "maximum_evaluation_processes": 1,
            "retry_allowed": False,
            "root": str(attempt),
            "process_identity": process,
        }
        and isinstance(process, Mapping)
        and set(process) == {"pid", "uid", "boot_id", "proc_start_ticks"}
        and isinstance(process.get("pid"), int)
        and process.get("pid", 0) > 0
        and process.get("uid") == os.getuid()
        and isinstance(process.get("boot_id"), str)
        and bool(process.get("boot_id"))
        and isinstance(process.get("proc_start_ticks"), int)
        and process.get("proc_start_ticks", 0) > 0
    )
    if not valid:
        raise SemanticV10Error("attempt ledger drift")


def require_recorded_process_inactive(process: Mapping[str, Any]) -> None:
    if process.get("uid") != os.getuid():
        raise SemanticV10Error("recorded process owner drift")
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    if boot != process.get("boot_id"):
        return
    pid = process.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        raise SemanticV10Error("recorded process pid drift")
    try:
        raw = Path(f"/proc/{pid}/stat").read_text()
    except FileNotFoundError:
        return
    tail = raw[raw.rfind(")") + 2 :].split()
    if len(tail) <= 19:
        raise SemanticV10Error("recorded process status ambiguous")
    if int(tail[19]) != process.get("proc_start_ticks") or tail[0] == "Z":
        return
    raise SemanticV10Error("recorded evaluation process is still active")


def terminal_error_classification(
    events: Sequence[tuple[Mapping[str, Any], str]],
) -> str | None:
    return next(
        (
            str(event.get("classification"))
            for event, _ in reversed(events)
            if event.get("kind") in EVENT_CLASSIFICATIONS
        ),
        None,
    )


def canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    except (TypeError, ValueError) as exc:
        raise SemanticV10Error(f"value is not canonical JSON: {exc}") from exc


def retained_json(value: object) -> bytes:
    try:
        raw = (
            json.dumps(value, indent=2, sort_keys=True, allow_nan=False).encode()
            + b"\n"
        )
    except (TypeError, ValueError) as exc:
        raise SemanticV10Error(f"value is not retained JSON: {exc}") from exc
    if len(raw) > MAX_ARTIFACT_BYTES:
        raise SemanticV10Error("retained artifact exceeds bounded size")
    return raw


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes())


def mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SemanticV10Error(f"{label} must be an object")
    return {str(key): item for key, item in value.items()}


def sequence(value: object, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise SemanticV10Error(f"{label} must be an array")
    return list(value)


def read_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    target = path.expanduser().absolute()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(target, flags)
    except OSError as exc:
        raise SemanticV10Error(f"{label} must be a regular non-symlink file") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise SemanticV10Error(f"{label} must be a regular file")
        with os.fdopen(fd, "rb") as stream:
            fd = -1
            raw = stream.read(MAX_ARTIFACT_BYTES + 1)
            after = os.fstat(stream.fileno())
        if len(raw) > MAX_ARTIFACT_BYTES:
            raise SemanticV10Error(f"{label} exceeds bounded size")
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise SemanticV10Error(f"{label} changed while read")
    finally:
        if fd >= 0:
            os.close(fd)
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SemanticV10Error(f"{label} must be valid UTF-8 JSON") from exc
    return mapping(value, label), raw


def write_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
    target = path.expanduser().absolute()
    raw = retained_json(payload)
    parent = target.parent.lstat()
    if (
        not stat.S_ISDIR(parent.st_mode)
        or stat.S_ISLNK(parent.st_mode)
        or parent.st_uid != os.getuid()
        or stat.S_IMODE(parent.st_mode) != 0o700
    ):
        raise SemanticV10Error("artifact parent must be an owner-only directory")
    fd = os.open(
        target,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
        ):
            raise SemanticV10Error("artifact target identity drift")
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            fd = -1
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if fd >= 0:
            os.close(fd)
    directory = os.open(target.parent, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _hash_binding(value: object, label: str) -> tuple[str, str]:
    binding = mapping(value, label)
    path, digest = binding.get("path"), binding.get("sha256")
    if not isinstance(path, str) or not isinstance(digest, str) or len(digest) != 64:
        raise SemanticV10Error(f"{label} identity drift")
    return path, digest


def materialized_request(
    case: Mapping[str, Any], semantics: Mapping[str, Any]
) -> OracleSemanticRequest:
    # Round-trip only provider_request: hidden labels and markers are unreachable.
    request = mapping(
        json.loads(canonical(case.get("provider_request"))), "case.provider_request"
    )
    quality = mapping(
        request.get("quality_contract"), "provider_request.quality_contract"
    )
    reference = mapping(
        quality.pop("analysis_code_semantics_ref", None), "analysis_code_semantics_ref"
    )
    if reference != {"path": str(SEMANTICS_PATH), "sha256": SEMANTICS_SHA256}:
        raise SemanticV10Error("code-semantics reference drift")
    quality["analysis_code_semantics"] = json.loads(canonical(semantics))
    return OracleSemanticRequest(
        objective=str(request.get("objective") or ""),
        evidence=mapping(request.get("evidence"), "provider_request.evidence"),
        quality_contract=quality,
    )


def request_hashes(
    contract: Mapping[str, Any], semantics: Mapping[str, Any]
) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_case in sequence(contract.get("cases"), "cases"):
        case = mapping(raw_case, "case")
        case_id = str(case.get("id") or "")
        result[case_id] = materialized_request(case, semantics).request_sha256
    return result


def score_v10(case: Mapping[str, Any], analysis: Mapping[str, Any]) -> dict[str, Any]:
    result = score_analysis(case, analysis)
    refs = sequence(analysis.get("evidence_refs"), "analysis.evidence_refs")
    duplicate_refs = len(refs) != len(set(refs))
    result["duplicate_evidence_refs"] = duplicate_refs
    if duplicate_refs:
        result["status"] = "failed"
        result["score"] = 0.0
    return result


def load_candidate(
    repo_root: Path, *, check_sources: bool = True
) -> tuple[dict[str, Any], dict[str, Any], str]:
    root = repo_root.expanduser().resolve()
    contract, raw = read_json(root / CONTRACT_PATH, "v10 contract")
    v9, v9_raw = read_json(root / V9_PATH, "v9 contract")
    semantics, semantics_raw = read_json(root / SEMANTICS_PATH, "code semantics")
    if sha256(v9_raw) != V9_SHA256 or sha256(semantics_raw) != SEMANTICS_SHA256:
        raise SemanticV10Error("frozen predecessor or code-semantics hash drift")
    expected_fields = {
        "schema_version",
        "status",
        "ak_task_id",
        "purpose",
        "predecessor_binding",
        "source_bindings",
        "route",
        "attempt_policy",
        "artifact_policy",
        "dependency_policy",
        *INHERITED_KEYS,
    }
    if set(contract) != expected_fields:
        raise SemanticV10Error("v10 contract fields drift")
    if (
        contract.get("schema_version") != "dspx-oracle-semantic-analysis-evaluation-v10"
        or contract.get("status") != "candidate_requires_external_review_and_live_gate"
        or contract.get("ak_task_id") != TASK_ID
    ):
        raise SemanticV10Error("v10 contract identity drift")
    if mapping(contract.get("predecessor_binding"), "predecessor_binding") != {
        "path": str(V9_PATH),
        "sha256": V9_SHA256,
        "accepted_commit": "d188328c6eb226baf596a8949774056bb86ff895",
    }:
        raise SemanticV10Error("v10 predecessor binding drift")
    for key in INHERITED_KEYS:
        if contract.get(key) != v9.get(key):
            raise SemanticV10Error(f"v9 inherited subtree drift: {key}")
    sources = mapping(contract.get("source_bindings"), "source_bindings")
    if tuple(sources) != EXPECTED_SOURCE_PATHS:
        raise SemanticV10Error("external source allowlist drift")
    for expected_path in EXPECTED_SOURCE_PATHS:
        path, digest = _hash_binding(
            sources[expected_path], f"source_bindings.{expected_path}"
        )
        if path != expected_path or (
            check_sources and file_sha256(root / path) != digest
        ):
            raise SemanticV10Error(f"external source hash drift: {expected_path}")
    expected_route = {
        "required_backend_kind": "live",
        "requested_provider": "dspy-lm-auth",
        "requested_model": "codex/gpt-5.6-sol",
        "reasoning_effort": "max",
        "executed_provider_requirement": "explicit_null_not_proven",
        "executed_model_requirement": "non_empty_observed_response_identity",
        "production_adapter_requirement": "exact_dspx_dspy_lm_auth_lm_type_with_call_history",
        "source_requirement": "candidate_review_commit_and_tree_equal_execution_head_and_tree",
        "live_authorized_by_contract": False,
    }
    if contract.get("route") != expected_route:
        raise SemanticV10Error("route drift")
    policy = mapping(contract.get("attempt_policy"), "attempt_policy")
    if policy != {
        "maximum_evaluation_processes": 1,
        "maximum_generate_calls_per_case": 1,
        "maximum_separate_health_probes": 0,
        "maximum_dspx_managed_retries": 0,
        "selective_case_rerun_allowed": False,
        "case_selector_allowed": False,
        "stop_after_first_failed_error_or_indeterminate_case": True,
        "provider_transport_call_count": "not_proven",
        "provider_internal_retry_behavior": "not_proven",
        "case_order": list(CASE_ORDER),
        "ledger_namespace": "dspx/oracle-semantic-analysis-evaluations/AK-4643",
        "ledger_key": "AK-4643",
        "attempt_directory": ATTEMPT_DIR,
    }:
        raise SemanticV10Error("attempt policy drift")
    if contract.get("artifact_policy") != {
        "task_state_mode": "0700",
        "attempt_root_mode": "0700",
        "regular_file_mode": "0600",
        "history": "append_only_no_replace",
        "candidate_review_receipt": CANDIDATE_RECEIPT,
        "live_gate_receipt": LIVE_GATE_RECEIPT,
        "result": RESULT_NAME,
        "verification": VERIFICATION_NAME,
    }:
        raise SemanticV10Error("artifact policy drift")
    if contract.get("dependency_policy") != DEPENDENCY_POLICY:
        raise SemanticV10Error("dependency policy drift")
    if tuple(request_hashes(contract, semantics)) != CASE_ORDER:
        raise SemanticV10Error("request case order drift")
    return contract, semantics, sha256(raw)

from __future__ import annotations

import copy
import importlib
import inspect
from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

import pytest

from dspx.services.program_oracle_semantic_artifacts_v11 import (
    TaskBinding,
    load_authority_artifacts,
    load_consumed_attempt,
    load_evaluation_result,
    load_independent_verification,
)
from dspx.services.program_oracle_semantic_contract_v11 import (
    CONSUMER_MODULE_HASHES,
    CONTRACT_SHA256,
    PROPOSAL_SHA256,
    SemanticV11Error,
    canonical,
    load_bound_cases,
    sha256,
)
from dspx.services.program_oracle_semantic_evidence_v11 import (
    EXECUTION_EVIDENCE_SCHEMA,
    GATE2_EVIDENCE_IDS,
)
from dspx.services.program_oracle_semantic_gate4_contract_v11 import (
    CANDIDATE_REVIEW_SCHEMA,
    GATE2_BASE_COMMIT,
    GATE2_BASE_TREE,
    GATE2_DONE_CONTRACT,
    GATE2_GUARDRAILS,
    GATE2_SCOPE_SHA256,
    GATE2_TASK_ID,
    GATE3_DONE_CONTRACT,
    GATE3_GUARDRAILS,
    GATE4_DONE_CONTRACT,
    GATE4_GUARDRAILS,
    LIVE_GATE_SCHEMA,
    REMEDIATION_DONE_CONTRACT,
    REMEDIATION_GUARDRAILS,
    REMEDIATION_SCOPE_SHA256,
    REMEDIATION_TASK_ID,
    REQUIRED_LIVE_COMPLETION_KIND,
    TerminalPersistenceError,
    VERIFICATION_SCHEMA,
)
from dspx.services.program_oracle_semantic_gate4_v11 import (
    candidate_source_manifest,
    execute_live_once,
    validate_gate4_authority_documents,
)
from dspx.services.program_oracle_semantic_gate5_authority_v11 import (
    reconstruct_authority_payloads,
)
from dspx.services.program_oracle_semantic_gate5_result_v11 import (
    independently_rederive_result,
)
from dspx.services.program_oracle_semantic_gate5_v11 import (
    _validate_gate5_documents,
    _validate_written_verification,
    verify_retained_once,
)
from dspx.services.program_oracle_semantic_verification_v11 import verify_private_tree
from dspx.services.provider_outcome_receipt_identity import (
    ACCEPTED_OWNER_SOURCE,
    VerifiedOwnerArtifact,
    _fixture_owner_artifact,
)

REPO = Path(__file__).resolve().parents[1]
_PRIVATE_EVIDENCE_STRINGS = (
    "sk-live-private-argv-ak4713",
    "/var/lib/dspx-private-evidence/secret.txt",
    "diagnostic-private-ak4713",
    "account:production-operator-4713",
    "checked-by:private-account-4713",
    "2042-12-31T23:59:58.123456+00:00",
)


def _private(path: Path) -> Path:
    path.mkdir(parents=True, mode=0o700)
    path.chmod(0o700)
    return path


def _machine(surface: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"surface": surface, "ok": True, "payload": payload, "error": None}


def _task(task_id: int, status: str, version: int = 3) -> dict[str, Any]:
    return _machine(
        "task.show",
        {
            "task": {
                "id": task_id,
                "repo": str(REPO),
                "status": status,
                "entity_version": version,
            }
        },
    )


def _contract(
    task_id: int, status: str, done: dict[str, Any], guard: dict[str, Any]
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "repo": str(REPO),
        "status": status,
        "done_contract": {
            "task_id": task_id,
            "contract": copy.deepcopy(done),
            "entity_version": 1,
        },
        "guardrails": {
            "task_id": task_id,
            "guardrails": copy.deepcopy(guard),
            "entity_version": 1,
        },
    }


def _evidence(
    eid: int, task: int, kind: str, details: dict[str, Any]
) -> dict[str, Any]:
    return {
        "id": eid,
        "task_ref": task,
        "check_type": kind,
        "result": "pass",
        "details": details,
        "checked_at": _PRIVATE_EVIDENCE_STRINGS[5],
        "checked_by": _PRIVATE_EVIDENCE_STRINGS[4],
        "diagnostics": _PRIVATE_EVIDENCE_STRINGS[2],
        "account_identifier": _PRIVATE_EVIDENCE_STRINGS[3],
    }


def _execution(
    kind: str, task: int, commit: str, tree: str, source: str
) -> dict[str, Any]:
    command = {
        "check_type": f"{kind}_focused",
        "command": [
            "recorded-command",
            _PRIVATE_EVIDENCE_STRINGS[0],
            _PRIVATE_EVIDENCE_STRINGS[1],
            _PRIVATE_EVIDENCE_STRINGS[3],
        ],
        "diagnostics": _PRIVATE_EVIDENCE_STRINGS[2],
        "result": "pass",
        "result_sha256": sha256(canonical({"kind": kind, "result": "pass"})),
        "receipt_sha256": sha256(canonical({"kind": kind, "receipt": "immutable"})),
    }
    return {
        "schema_version": EXECUTION_EVIDENCE_SCHEMA,
        "artifact_kind": kind,
        "task_id": task,
        "candidate_commit": commit,
        "candidate_tree": tree,
        "candidate_source_manifest_sha256": source,
        "contract_sha256": CONTRACT_SHA256,
        "commands": [command],
        "validation_result_sha256": sha256(canonical({"commands": [command]})),
        "validation_receipt_sha256": sha256(
            canonical({"result": command["result_sha256"]})
        ),
        "provider_operations": 0,
    }


def _minimal_evidence_binding(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "task_ref": row["task_ref"],
        "check_type": row["check_type"],
        "result": row["result"],
        "evidence_sha256": sha256(canonical(row)),
    }


def _minimal_execution_binding(details: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_kind": details["artifact_kind"],
        "task_id": details["task_id"],
        "candidate_commit": details["candidate_commit"],
        "candidate_tree": details["candidate_tree"],
        "candidate_source_manifest_sha256": details["candidate_source_manifest_sha256"],
        "contract_sha256": details["contract_sha256"],
        "commands_sha256": sha256(canonical(details["commands"])),
        "validation_result_sha256": details["validation_result_sha256"],
        "validation_receipt_sha256": details["validation_receipt_sha256"],
    }


def _full_hashes(contract: dict[str, Any]) -> tuple[str, str]:
    return sha256(canonical(contract["done_contract"])), sha256(
        canonical(contract["guardrails"])
    )


def _documents(state: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    ids: dict[str, Any] = {
        "live": 81004,
        "review_task": 81003,
        "remediation_evidence": 82002,
        "review_evidence": 82003,
        "operator_evidence": 82004,
        "live_evidence": 82005,
        "commit": "a" * 40,
        "tree": "b" * 40,
    }
    manifest = candidate_source_manifest(REPO)
    source = sha256(canonical(manifest))
    contracts = {
        "gate2": _contract(
            GATE2_TASK_ID, "done", GATE2_DONE_CONTRACT, GATE2_GUARDRAILS
        ),
        "remediation": _contract(
            REMEDIATION_TASK_ID,
            "done",
            REMEDIATION_DONE_CONTRACT,
            REMEDIATION_GUARDRAILS,
        ),
        "review": _contract(
            ids["review_task"], "done", GATE3_DONE_CONTRACT, GATE3_GUARDRAILS
        ),
        "live": _contract(
            ids["live"], "claimed", GATE4_DONE_CONTRACT, GATE4_GUARDRAILS
        ),
    }
    hashes = {name: _full_hashes(value) for name, value in contracts.items()}
    gate2 = (
        _evidence(
            6729,
            GATE2_TASK_ID,
            "gate2_focused_tests",
            {"command": ["pytest"], "result": "pass"},
        ),
        _evidence(
            6730,
            GATE2_TASK_ID,
            "gate2_static_checks",
            {"command": ["ruff", "ty"], "result": "pass"},
        ),
    )
    gate2_bindings = [_minimal_evidence_binding(row) for row in gate2]
    remediation = _evidence(
        ids["remediation_evidence"],
        REMEDIATION_TASK_ID,
        "oracle_semantic_v11_remediation_validation",
        _execution(
            "remediation_validation",
            REMEDIATION_TASK_ID,
            ids["commit"],
            ids["tree"],
            source,
        ),
    )
    gate3_validation = _execution(
        "gate_3_validation", ids["review_task"], ids["commit"], ids["tree"], source
    )
    review = {
        "schema_version": CANDIDATE_REVIEW_SCHEMA,
        "artifact_kind": "candidate_review",
        "gate_2_task_id": GATE2_TASK_ID,
        "remediation_task_id": REMEDIATION_TASK_ID,
        "gate_3_task_id": ids["review_task"],
        "gate_2_candidate_commit": GATE2_BASE_COMMIT,
        "gate_2_candidate_tree": GATE2_BASE_TREE,
        "gate_2_scope_sha256": GATE2_SCOPE_SHA256,
        "remediation_scope_sha256": REMEDIATION_SCOPE_SHA256,
        "gate_2_task_contract_sha256": hashes["gate2"][0],
        "gate_2_guardrails_sha256": hashes["gate2"][1],
        "remediation_task_contract_sha256": hashes["remediation"][0],
        "remediation_guardrails_sha256": hashes["remediation"][1],
        "gate_3_task_contract_sha256": hashes["review"][0],
        "gate_3_guardrails_sha256": hashes["review"][1],
        "gate_2_evidence_bindings": gate2_bindings,
        "gate_2_evidence_set_sha256": sha256(canonical(list(gate2))),
        "remediation_validation_evidence_binding": _minimal_evidence_binding(
            remediation
        ),
        "gate_3_validation_evidence": _minimal_execution_binding(gate3_validation),
        "decision": "ACCEPT_V11_CANDIDATE_FOR_SEPARATE_LIVE_GATE",
        "contract_sha256": CONTRACT_SHA256,
        "proposal_sha256": PROPOSAL_SHA256,
        "candidate_commit": ids["commit"],
        "candidate_tree": ids["tree"],
        "candidate_source_manifest": manifest,
        "candidate_source_manifest_sha256": source,
        "accepted_consumer_module_sha256": CONSUMER_MODULE_HASHES,
        "provider_operations": 0,
    }
    review_record = _evidence(
        ids["review_evidence"],
        ids["review_task"],
        "oracle_semantic_v11_candidate_review",
        {
            "schema_version": "dspx-oracle-semantic-v11-candidate-review-evidence-v2",
            "artifact_kind": "candidate_review_evidence",
            "candidate_review": review,
            "validation_evidence": gate3_validation,
        },
    )
    root_sha = TaskBinding.create(
        ids["live"], REQUIRED_LIVE_COMPLETION_KIND, state
    ).state_root_identity_sha256
    route = {
        "provider": "dspy-lm-auth",
        "model": "codex/gpt-5.6-sol",
        "reasoning_effort": "max",
        "mode": "sync",
        "cache": False,
        "num_retries": 0,
        "stream": True,
        "store": False,
    }
    operator_details = {
        "schema_version": LIVE_GATE_SCHEMA,
        "artifact_kind": "operator_authorization",
        "live_task_id": ids["live"],
        "state_root_identity_sha256": root_sha,
        "candidate_review_evidence_id": ids["review_evidence"],
        "candidate_review_sha256": sha256(canonical(review)),
        "decision": "AUTHORIZE_EXACTLY_ONE_V11_CORPUS_PROCESS",
        "route": route,
        "maximum_corpus_processes": 1,
        "maximum_effect_capable_delegations_per_request": 1,
        "maximum_health_probes": 0,
        "maximum_dspx_managed_retries": 0,
        "fallback_allowed": False,
    }
    operator = _evidence(
        ids["operator_evidence"],
        ids["live"],
        "oracle_semantic_v11_operator_authorization",
        operator_details,
    )
    gate_details = {
        "schema_version": LIVE_GATE_SCHEMA,
        "artifact_kind": "live_gate",
        "live_task_id": ids["live"],
        "gate_3_task_id": ids["review_task"],
        "state_root_identity_sha256": root_sha,
        "task_entity_version": 7,
        "gate_4_task_contract_sha256": hashes["live"][0],
        "gate_4_guardrails_sha256": hashes["live"][1],
        "candidate_review_evidence_id": ids["review_evidence"],
        "candidate_review_sha256": sha256(canonical(review)),
        "operator_evidence_id": ids["operator_evidence"],
        "operator_evidence_sha256": sha256(canonical(operator)),
        "candidate_commit": ids["commit"],
        "candidate_tree": ids["tree"],
        "candidate_source_manifest_sha256": source,
        "contract_sha256": CONTRACT_SHA256,
        "route": route,
        "maximum_corpus_processes": 1,
        "maximum_effect_capable_delegations_per_request": 1,
        "maximum_health_probes": 0,
        "maximum_dspx_managed_retries": 0,
        "fallback_allowed": False,
    }
    gate = _evidence(
        ids["live_evidence"], ids["live"], "oracle_semantic_v11_live_gate", gate_details
    )
    docs = {
        "gate_2_task_document": _task(GATE2_TASK_ID, "done"),
        "gate_2_contract_document": contracts["gate2"],
        "gate_2_evidence_6729_document": _machine(
            "evidence.show", {"evidence": gate2[0]}
        ),
        "gate_2_evidence_6730_document": _machine(
            "evidence.show", {"evidence": gate2[1]}
        ),
        "remediation_task_document": _task(REMEDIATION_TASK_ID, "done"),
        "remediation_contract_document": contracts["remediation"],
        "review_task_document": _task(ids["review_task"], "done"),
        "review_contract_document": contracts["review"],
        "live_task_document": _task(ids["live"], "claimed", 7),
        "live_contract_document": contracts["live"],
        "remediation_validation_evidence_document": _machine(
            "evidence.show", {"evidence": remediation}
        ),
        "review_evidence_document": _machine(
            "evidence.show", {"evidence": review_record}
        ),
        "operator_evidence_document": _machine("evidence.show", {"evidence": operator}),
        "live_gate_evidence_document": _machine("evidence.show", {"evidence": gate}),
        "live_task_evidence_set_document": _machine(
            "evidence.task",
            {"task_id": ids["live"], "count": 2, "evidence": [operator, gate]},
        ),
    }
    return docs, ids


def _validate(state: Path, docs: dict[str, Any], ids: dict[str, Any]):
    with patch(
        "dspx.services.program_oracle_semantic_gate4_validation_v11._git_identity",
        return_value=(ids["commit"], ids["tree"]),
    ):
        return validate_gate4_authority_documents(
            repo_root=REPO,
            state_root=state,
            live_task_id=ids["live"],
            remediation_validation_evidence_id=ids["remediation_evidence"],
            review_evidence_id=ids["review_evidence"],
            operator_evidence_id=ids["operator_evidence"],
            live_gate_evidence_id=ids["live_evidence"],
            **docs,
        )


@dataclass(frozen=True, slots=True)
class _Event:
    kind: str
    gate_ordinal: int | None = None
    status_class: int | None = None
    error_class: str | None = None
    protocol_event: str | None = None
    response_id_sha256: str | None = None
    observed_model: str | None = None


@dataclass(slots=True)
class _Receipt:
    logical_request_id: str
    semantic_request_sha256: str
    sink: Any


def _artifact() -> VerifiedOwnerArtifact:
    expected = ACCEPTED_OWNER_SOURCE
    fixture = _fixture_owner_artifact(
        source_identity={
            "owner": "tryinget-dspy-lm-auth",
            "version": expected.version,
            "commit": expected.commit,
            "tree": expected.tree,
            "lock_sha256": expected.lock_sha256,
            "module_sha256": {
                name: digest for name, (_, digest) in expected.modules.items()
            },
        },
        dependency_identity={
            name: {
                "version": item.version,
                "locked_wheel_sha256": item.wheel_sha256,
                "payload_count": item.payload_count,
                "payload_sha256": item.payload_sha256,
                "record_sha256": item.record_sha256,
            }
            for name, item in expected.dependencies.items()
        },
        event_type=_Event,
        receipt_type=_Receipt,
    )
    value = object.__new__(VerifiedOwnerArtifact)
    for name in VerifiedOwnerArtifact.__slots__:
        object.__setattr__(
            value, name, True if name == "_accepted" else getattr(fixture, name)
        )
    return value


def _ak_patch(tmp_path: Path, docs: dict[str, Any], ids: dict[str, Any]):
    import dspx.services.program_oracle_semantic_authority_v11 as authority

    executable = tmp_path / "fake-ak-not-executed"
    executable.write_text("#!/bin/sh\nexit 99\n")
    executable.chmod(0o700)
    evidence = {
        6729: docs["gate_2_evidence_6729_document"],
        6730: docs["gate_2_evidence_6730_document"],
        ids["remediation_evidence"]: docs["remediation_validation_evidence_document"],
        ids["review_evidence"]: docs["review_evidence_document"],
        ids["operator_evidence"]: docs["operator_evidence_document"],
        ids["live_evidence"]: docs["live_gate_evidence_document"],
    }
    tasks = {
        GATE2_TASK_ID: (docs["gate_2_task_document"], docs["gate_2_contract_document"]),
        REMEDIATION_TASK_ID: (
            docs["remediation_task_document"],
            docs["remediation_contract_document"],
        ),
        ids["review_task"]: (
            docs["review_task_document"],
            docs["review_contract_document"],
        ),
        ids["live"]: (docs["live_task_document"], docs["live_contract_document"]),
    }

    def run(command: list[str], **_kwargs: Any):
        args = command[1:]
        if args[:2] == ["evidence", "show"]:
            payload = evidence[int(args[2])]
        elif args[:2] == ["evidence", "task"]:
            payload = docs["live_task_evidence_set_document"]
        elif args[:2] == ["task", "show"]:
            payload = tasks[int(args[2])][0]
        else:
            payload = tasks[int(args[3])][1]
        return SimpleNamespace(returncode=0, stderr=b"", stdout=canonical(payload))

    return patch.multiple(
        authority, AK_EXECUTABLE=executable, subprocess=SimpleNamespace(run=run)
    )


@dataclass(slots=True)
class _LivePlan:
    cases: tuple[Any, ...]
    adapter_failure_ordinal: int | None = None
    calls: int = 0


class _LiveInner:
    _uses_codex_route = True
    num_retries = 0

    def __init__(self, plan: _LivePlan) -> None:
        self.plan = plan

    def forward(self, **kwargs: Any) -> object:
        self.plan.calls += 1
        ordinal = self.plan.calls
        if ordinal == self.plan.adapter_failure_ordinal:
            raise RuntimeError("adapter_call-failure")
        receipt = cast(_Receipt, kwargs["outcome_receipt"])
        response = "f" * 64
        for event in (
            _Event("wrapper_request_accepted"),
            _Event("transport_gate_entered", gate_ordinal=1),
            _Event("transport_effect_pending", gate_ordinal=1),
            _Event("transport_entered", gate_ordinal=1),
            _Event("http_response_observed", gate_ordinal=1, status_class=2),
            _Event(
                "parsed_protocol_event_observed",
                protocol_event="response.completed",
                response_id_sha256=response,
            ),
            _Event(
                "provider_response_completed",
                status_class=2,
                response_id_sha256=response,
                observed_model="gpt-5.6-sol",
            ),
        ):
            receipt.sink(event)
        hidden = self.plan.cases[ordinal - 1].case["hidden_labels"]
        analysis = {
            **hidden["expected_codes"],
            "evidence_refs": hidden["expected_evidence_refs"],
            "confidence": 0.8,
        }
        return SimpleNamespace(output_text=json.dumps(analysis), model="gpt-5.6-sol")


def _patch_live_runtime(
    monkeypatch: pytest.MonkeyPatch,
    artifact: VerifiedOwnerArtifact,
    *,
    adapter_failure_ordinal: int | None = None,
    owner_drift_after_first: bool = False,
) -> tuple[Any, _LivePlan]:
    import dspx.services.program_oracle_semantic_adapter_v11 as adapter_module
    import dspx.services.program_oracle_semantic_gate4_v11 as gate4
    import dspx.services.program_oracle_semantic_identity_v11 as identity

    cases = load_bound_cases(REPO)
    plan = _LivePlan(cases, adapter_failure_ordinal)
    owner_calls = {"count": 0}

    def revalidate() -> None:
        owner_calls["count"] += 1
        if owner_drift_after_first and owner_calls["count"] > 1:
            raise RuntimeError("owner-drift-after-case-1")

    owner = SimpleNamespace(
        artifact=artifact, revalidate=revalidate, lm_type=_LiveInner
    )
    monkeypatch.setattr(gate4, "_assert_preledger_import_posture", lambda: None)
    monkeypatch.setattr(gate4, "verify_loaded_runtime_modules", lambda *_a, **_k: None)
    monkeypatch.setattr(
        gate4,
        "_owner_api",
        lambda: (
            _Event,
            _Receipt,
            "https://chatgpt.com/backend-api/codex",
            _LiveInner,
        ),
    )
    monkeypatch.setattr(identity, "verify_exact_owner", lambda *_a, **_k: owner)

    def build_inner(instance: Any) -> _LiveInner:
        instance._uses_codex_route = True
        return _LiveInner(plan)

    monkeypatch.setattr(
        adapter_module.ReceiptSafeDspyLMAuthLM, "_build_inner", build_inner
    )
    monkeypatch.setattr(
        "dspx.services.program_oracle_semantic_owner_bridge_v11._check_capability", None
    )
    return owner, plan


def _execute_with_documents(
    tmp_path: Path,
    state: Path,
    docs: dict[str, Any],
    ids: dict[str, Any],
) -> dict[str, Any]:
    with (
        _ak_patch(tmp_path, docs, ids),
        patch(
            "dspx.services.program_oracle_semantic_gate4_validation_v11._git_identity",
            return_value=(ids["commit"], ids["tree"]),
        ),
    ):
        return cast(
            dict[str, Any],
            execute_live_once(
                repo_root=REPO,
                state_root=state,
                owner_source_root=tmp_path / "owner",
                live_task_id=ids["live"],
                remediation_validation_evidence_id=ids["remediation_evidence"],
                review_evidence_id=ids["review_evidence"],
                operator_evidence_id=ids["operator_evidence"],
                live_gate_evidence_id=ids["live_evidence"],
            ),
        )


def _gate5_attempt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str):
    state = _private(tmp_path / name)
    docs, ids = _documents(state)
    import dspx.services.program_oracle_semantic_gate4_v11 as gate4
    import dspx.services.program_oracle_semantic_gate5_v11 as gate5
    import dspx.services.program_oracle_semantic_gate5_persistence_v11 as gate5_persistence

    monkeypatch.setattr(gate4, "_assert_preledger_import_posture", lambda: None)
    with (
        _ak_patch(tmp_path, docs, ids),
        patch(
            "dspx.services.program_oracle_semantic_gate4_validation_v11._git_identity",
            return_value=(ids["commit"], ids["tree"]),
        ),
        patch.object(
            gate4,
            "verify_loaded_runtime_modules",
            side_effect=RuntimeError("gate5-fixture-runtime-origin-failure"),
        ),
        pytest.raises(RuntimeError, match="gate5-fixture-runtime-origin"),
    ):
        execute_live_once(
            repo_root=REPO,
            state_root=state,
            owner_source_root=tmp_path / "owner",
            live_task_id=ids["live"],
            remediation_validation_evidence_id=ids["remediation_evidence"],
            review_evidence_id=ids["review_evidence"],
            operator_evidence_id=ids["operator_evidence"],
            live_gate_evidence_id=ids["live_evidence"],
        )
    attempt = load_consumed_attempt(state, ids["live"])
    review, _, live_gate, _ = load_authority_artifacts(attempt)
    ids.update(gate5_task=81005, gate5_evidence=82006)
    gate5_authorization = _evidence(
        ids["gate5_evidence"],
        ids["gate5_task"],
        "oracle_semantic_v11_gate5_authorization",
        {
            "schema_version": VERIFICATION_SCHEMA,
            "artifact_kind": "gate5_authorization",
            "gate5_task_id": ids["gate5_task"],
            "gate5_task_entity_version": 1,
            "gate5_task_contract_sha256": "1" * 64,
            "gate5_guardrails_sha256": "2" * 64,
            "live_task_id": ids["live"],
            "gate_3_task_id": ids["review_task"],
            "state_root_identity_sha256": (attempt.binding.state_root_identity_sha256),
            "ledger_sha256": attempt.ledger_sha256,
            "result_sha256": "3" * 64,
            "candidate_review_sha256": attempt.ledger["candidate_review_sha256"],
            "live_gate_sha256": attempt.ledger["live_gate_sha256"],
            "decision": "AUTHORIZE_ONE_PROVIDER_FREE_INDEPENDENT_VERIFICATION",
            "different_process_required": True,
            "provider_operations": 0,
            "terminal_modification_allowed": False,
        },
    )
    ids["gate5_preflight_document"] = _machine(
        "evidence.show", {"evidence": gate5_authorization}
    )
    monkeypatch.setattr(gate5, "current_process_identity_sha256", lambda: "9" * 64)
    monkeypatch.setattr(
        gate5_persistence, "current_process_identity_sha256", lambda: "9" * 64
    )
    monkeypatch.setattr(
        gate5, "_source_manifest", lambda _root: review["candidate_source_manifest"]
    )
    monkeypatch.setattr(
        gate5, "_git_identity", lambda _root: (ids["commit"], ids["tree"])
    )

    def gate5_ak(*args: str) -> dict[str, Any]:
        if args[:3] == ("evidence", "show", str(ids["gate5_evidence"])):
            return cast(dict[str, Any], ids["gate5_preflight_document"])
        return {}

    monkeypatch.setattr(gate5, "_run_ak", gate5_ak)
    monkeypatch.setattr(
        gate5,
        "reconstruct_authority_payloads",
        lambda **_kwargs: (
            review,
            live_gate,
            attempt.ledger["authority_snapshot_sha256"],
        ),
    )
    monkeypatch.setattr(
        gate5,
        "_validate_gate5_documents",
        lambda **_kwargs: SimpleNamespace(
            task_contract_sha256="1" * 64,
            guardrails_sha256="2" * 64,
            evidence_sha256="3" * 64,
        ),
    )
    monkeypatch.setattr(gate5, "_verify_loaded_origins", lambda *_args: None)
    monkeypatch.setattr(gate5, "_verify_owner", lambda _root: _artifact())
    ids["documents"] = docs
    return state, attempt, ids, gate5


def _verify_gate5(state: Path, ids: dict[str, Any]) -> dict[str, Any]:
    return verify_retained_once(
        repo_root=REPO,
        state_root=state,
        live_task_id=ids["live"],
        gate5_task_id=ids["gate5_task"],
        gate5_evidence_id=ids["gate5_evidence"],
        owner_source_root=state / "unused-owner",
    )


@pytest.mark.parametrize(
    "evidence_key",
    ["remediation_evidence", "review_evidence", "operator_evidence", "live_evidence"],
)
@pytest.mark.parametrize("task_key", ["gate2", "remediation", "review", "live"])
def test_gate4_rejects_cross_category_task_evidence_alias(
    tmp_path, evidence_key, task_key
):
    state = _private(tmp_path / f"gate4-cross-alias-{evidence_key}-{task_key}")
    docs, ids = _documents(state)
    task_ids = {
        "gate2": GATE2_TASK_ID,
        "remediation": REMEDIATION_TASK_ID,
        "review": ids["review_task"],
        "live": ids["live"],
    }
    ids[evidence_key] = task_ids[task_key]
    with pytest.raises(SemanticV11Error, match="task/evidence selectors"):
        _validate(state, docs, ids)


def test_public_one_shots_accept_no_documents_reports_or_bearers(tmp_path):
    state = _private(tmp_path / "state")
    docs, ids = _documents(state)
    report = _validate(state, docs, ids)
    assert report["authority_granted"] is False
    assert [
        item["id"] for item in report["candidate_review"]["gate_2_evidence_bindings"]
    ] == list(GATE2_EVIDENCE_IDS)
    assert set(inspect.signature(execute_live_once).parameters) == {
        "repo_root",
        "state_root",
        "owner_source_root",
        "live_task_id",
        "remediation_validation_evidence_id",
        "review_evidence_id",
        "operator_evidence_id",
        "live_gate_evidence_id",
    }
    assert set(inspect.signature(verify_retained_once).parameters) == {
        "repo_root",
        "state_root",
        "live_task_id",
        "gate5_task_id",
        "gate5_evidence_id",
        "owner_source_root",
    }
    forbidden = {
        "canonical_documents",
        "require_canonical_documents",
        "_mint_gate4_live_admission",
        "_mint_live_attempt_custody",
        "_mint_case_invocation_custody",
        "_mint_gate5_write_custody",
        "_write_independent_verification",
        "Gate4LiveAdmission",
        "LiveAttemptCustody",
        "CaseInvocationCustody",
        "Gate5VerificationCustody",
    }
    modules = [
        importlib.import_module(f"dspx.services.{path.stem}")
        for path in (REPO / "packages/dspx-core/src/dspx/services").glob(
            "program_oracle_semantic_*_v11.py"
        )
    ]
    assert not {
        name for module in modules for name in forbidden if hasattr(module, name)
    }
    with pytest.raises(TypeError):
        cast(Any, execute_live_once)(
            repo_root=REPO,
            state_root=state,
            owner_source_root=tmp_path,
            live_task_id=ids["live"],
            remediation_validation_evidence_id=ids["remediation_evidence"],
            review_evidence_id=ids["review_evidence"],
            operator_evidence_id=ids["operator_evidence"],
            live_gate_evidence_id=ids["live_evidence"],
            documents=docs,
        )
    assert list(state.iterdir()) == []
    poisoned = copy.deepcopy(docs)
    rows = poisoned["live_task_evidence_set_document"]["payload"]
    rows["evidence"].append(copy.deepcopy(rows["evidence"][0]))
    rows["count"] = 3
    with pytest.raises(SemanticV11Error, match="pair cardinality"):
        _validate(state, poisoned, ids)


def _later_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
    ordinal: int,
):
    state = _private(tmp_path / f"{phase}-{ordinal}")
    docs, ids = _documents(state)
    artifact = _artifact()
    _patch_live_runtime(
        monkeypatch,
        artifact,
        adapter_failure_ordinal=ordinal if phase == "adapter" else None,
    )
    import dspx.services.program_oracle_semantic_evaluation_v11 as evaluation
    import dspx.services.program_oracle_semantic_result_artifact_v11 as result

    if phase == "mark":
        original_entry = result.validate_generate_entry

        def fail_entry(snapshot: Any, entered: Any):
            if snapshot.case.case_ordinal == ordinal:
                raise RuntimeError("mark_generate_entered-failure")
            return original_entry(snapshot, entered)

        monkeypatch.setattr(result, "validate_generate_entry", fail_entry)
    elif phase == "fragment":
        original_write_check = result.validate_case_fragment_write

        def fail_fragment_write(snapshot: Any, fragment: Any):
            if snapshot.case.case_ordinal == ordinal:
                raise RuntimeError("fragment-write-failure")
            return original_write_check(snapshot, fragment)

        monkeypatch.setattr(result, "validate_case_fragment_write", fail_fragment_write)
    elif phase == "seal":
        original_seal = result.validate_case_fragment_seal

        def fail_seal(snapshot: Any, fragment: Any):
            if snapshot.case.case_ordinal == ordinal:
                raise RuntimeError("seal-failure")
            return original_seal(snapshot, fragment)

        monkeypatch.setattr(result, "validate_case_fragment_seal", fail_seal)
    elif phase == "projection":
        original_projection = evaluation.projection_disposition

        def fail_projection(fragment: Any):
            if fragment["case_ordinal"] == ordinal:
                raise RuntimeError("projection-failure")
            return original_projection(fragment)

        monkeypatch.setattr(evaluation, "projection_disposition", fail_projection)
    expected = {
        "mark": "mark_generate_entered-failure",
        "adapter": "adapter_call-failure",
        "fragment": "fragment-write-failure",
        "seal": "seal-failure",
        "projection": "projection-failure",
    }[phase]
    with pytest.raises(RuntimeError, match=expected):
        _execute_with_documents(tmp_path, state, docs, ids)
    attempt = load_consumed_attempt(state, ids["live"])
    result_payload, _ = load_evaluation_result(attempt)
    assert [
        case["provider_outcome"]["empirical_disposition"]
        for case in result_payload["cases"][:-1]
    ] == ["passed"] * (ordinal - 1)
    assert (
        result_payload["cases"][-1]["provider_outcome"]["empirical_disposition"]
        == "error"
    )
    assert result_payload["empirical_gate"] == "error"
    expected_generates = ordinal - 1 if phase == "mark" else ordinal
    assert (
        result_payload["operation_counts"]["dspx_generate_calls"] == expected_generates
    )
    assert (
        independently_rederive_result(
            repo_root=REPO, attempt=attempt, artifact=artifact
        )
        == result_payload
    )
    verify_private_tree(attempt)
    names = sorted(
        path.name for path in (attempt.attempt_root / "result-fragments").iterdir()
    )
    expected_names = [f"{index:02d}-case.json" for index in range(1, ordinal + 1)]
    if phase in {"fragment", "seal", "projection"}:
        expected_names.append(f"{ordinal:02d}-terminal.json")
    assert names == sorted(expected_names)
    return state, attempt, result_payload, docs, ids, artifact


@pytest.mark.parametrize("phase", ["fragment", "seal"])
@pytest.mark.parametrize("ordinal", [2, 3, 4])
def test_actual_fragment_and_seal_failures_terminalize_from_snapshots(
    tmp_path, monkeypatch, phase, ordinal
):
    _later_failure(tmp_path, monkeypatch, phase, ordinal)


@pytest.mark.parametrize("ordinal", [2, 3, 4])
def test_generate_entry_failures_terminalize_from_snapshots(
    tmp_path, monkeypatch, ordinal
):
    _later_failure(tmp_path, monkeypatch, "mark", ordinal)


@pytest.mark.parametrize("phase", ["adapter", "projection"])
def test_adapter_and_projection_failures_terminalize_from_snapshots(
    tmp_path, monkeypatch, phase
):
    _later_failure(tmp_path, monkeypatch, phase, 2)


def test_owner_drift_after_case_one_terminalizes_without_fresh_revalidation(
    tmp_path, monkeypatch
):
    state = _private(tmp_path / "owner-drift")
    docs, ids = _documents(state)
    artifact = _artifact()
    _patch_live_runtime(monkeypatch, artifact, owner_drift_after_first=True)
    with pytest.raises(RuntimeError, match="owner-drift-after-case-1"):
        _execute_with_documents(tmp_path, state, docs, ids)
    attempt = load_consumed_attempt(state, ids["live"])
    result_payload, _ = load_evaluation_result(attempt)
    assert [
        item["provider_outcome"]["empirical_disposition"]
        for item in result_payload["cases"]
    ] == ["passed", "error"]
    assert result_payload["operation_counts"]["dspx_generate_calls"] == 2
    assert (
        independently_rederive_result(
            repo_root=REPO, attempt=attempt, artifact=artifact
        )
        == result_payload
    )


def test_final_aggregate_application_failure_uses_snapshot_fallback(
    tmp_path, monkeypatch
):
    state = _private(tmp_path / "aggregate-fallback")
    docs, ids = _documents(state)
    artifact = _artifact()
    _patch_live_runtime(monkeypatch, artifact)
    import dspx.services.program_oracle_semantic_result_artifact_v11 as result

    original = result.derive_evaluation_result
    calls = {"count": 0}

    def fail_once(*args: Any, **kwargs: Any):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("aggregate-application-failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(result, "derive_evaluation_result", fail_once)
    payload = _execute_with_documents(tmp_path, state, docs, ids)
    assert payload["empirical_gate"] == "error"
    assert payload["operation_counts"]["dspx_generate_calls"] == 4
    attempt = load_consumed_attempt(state, ids["live"])
    retained, _ = load_evaluation_result(attempt)
    assert retained == payload
    assert (attempt.attempt_root / "result-fragments/04-terminal.json").is_file()
    assert (
        independently_rederive_result(
            repo_root=REPO, attempt=attempt, artifact=artifact
        )
        == retained
    )


def test_no_replace_persistence_failure_reports_truth_without_terminal(
    tmp_path, monkeypatch
):
    state = _private(tmp_path / "persistence")
    docs, ids = _documents(state)
    artifact = _artifact()
    _patch_live_runtime(monkeypatch, artifact)
    import dspx.services.program_oracle_semantic_gate4_v11 as gate4

    original = gate4._state_io._persist_no_replace

    def fail_second_fragment(path: Path, payload: Any):
        if path.name == "02-case.json":
            raise OSError("injected no-replace persistence failure")
        return original(path, payload)

    monkeypatch.setattr(gate4._state_io, "_persist_no_replace", fail_second_fragment)
    with pytest.raises(TerminalPersistenceError) as captured:
        _execute_with_documents(tmp_path, state, docs, ids)
    assert captured.value.external_effect_possible is True
    assert captured.value.empirical_disposition == "effect_indeterminate"
    assert captured.value.terminal_retained is False
    attempt = load_consumed_attempt(state, ids["live"])
    assert not (attempt.attempt_root / "evaluation-result.json").exists()
    assert sorted(
        path.name for path in (attempt.attempt_root / "result-fragments").iterdir()
    ) == ["01-case.json"]


def test_canonical_evidence_secrets_hash_but_never_cross_retention(
    tmp_path, monkeypatch
):
    state, attempt, ids, _ = _gate5_attempt(tmp_path, monkeypatch, "privacy")
    documents = ids["documents"]
    evidence = documents["remediation_validation_evidence_document"]["payload"][
        "evidence"
    ]
    evidence_raw = canonical(evidence)
    evidence_sha = sha256(evidence_raw)
    review, review_raw, live_gate, _ = load_authority_artifacts(attempt)
    assert (
        review["remediation_validation_evidence_binding"]["evidence_sha256"]
        == evidence_sha
    )
    for private_value in _PRIVATE_EVIDENCE_STRINGS:
        encoded = private_value.encode()
        assert encoded in evidence_raw
        changed = json.loads(evidence_raw.replace(encoded, b"changed-private-value"))
        assert sha256(canonical(changed)) != evidence_sha
    assert set(review["gate_2_evidence_bindings"][0]) == {
        "id",
        "task_ref",
        "check_type",
        "result",
        "evidence_sha256",
    }
    gate3_raw = documents["review_evidence_document"]["payload"]["evidence"]["details"][
        "validation_evidence"
    ]
    assert review["gate_3_validation_evidence"]["commands_sha256"] == sha256(
        canonical(gate3_raw["commands"])
    )
    assert set(review["gate_3_validation_evidence"]) == {
        "artifact_kind",
        "task_id",
        "candidate_commit",
        "candidate_tree",
        "candidate_source_manifest_sha256",
        "contract_sha256",
        "commands_sha256",
        "validation_result_sha256",
        "validation_receipt_sha256",
    }
    reconstructed_review, reconstructed_gate, snapshot_sha = (
        reconstruct_authority_payloads(
            repo_root=REPO,
            state_root_identity_sha256=(attempt.binding.state_root_identity_sha256),
            ledger=attempt.ledger,
            commit=ids["commit"],
            tree=ids["tree"],
            source_manifest=review["candidate_source_manifest"],
            documents=documents,
        )
    )
    assert reconstructed_review == review
    assert reconstructed_gate == live_gate
    assert snapshot_sha == attempt.ledger["authority_snapshot_sha256"]
    accepted = _verify_gate5(state, ids)
    assert accepted["artifact_integrity_review"] == "accepted"
    retained_paths = [
        path for path in attempt.attempt_root.rglob("*") if path.is_file()
    ]
    retained_paths.extend(state.glob(".dspx-*.started.json"))
    retained_bytes = b"\n".join(path.read_bytes() for path in retained_paths)
    for private_value in _PRIVATE_EVIDENCE_STRINGS:
        assert private_value.encode() not in retained_bytes
    assert review_raw == canonical(review)


def test_candidate_review_path_grammar_rejects_nested_raw_or_bad_hash(
    tmp_path, monkeypatch
):
    _, attempt, _, _ = _gate5_attempt(tmp_path, monkeypatch, "review-grammar")
    path = attempt.attempt_root / "candidate-review.json"
    original = path.read_bytes()
    for variant in ("raw-argv", "bad-execution-hash", "absolute-source"):
        review = json.loads(original)
        if variant == "raw-argv":
            review["gate_2_evidence_bindings"][0]["argv"] = ["raw"]
        elif variant == "bad-execution-hash":
            review["gate_3_validation_evidence"]["commands_sha256"] = "not-a-hash"
        else:
            review["candidate_source_manifest"]["/mnt/private/source.py"] = "a" * 64
        path.write_bytes(canonical(review))
        with pytest.raises(SemanticV11Error, match="path-specific"):
            verify_private_tree(attempt)
        path.write_bytes(original)
    verify_private_tree(attempt)


@pytest.mark.parametrize(
    "task_key", ["gate2", "remediation", "review", "live", "gate5"]
)
def test_gate5_rejects_cross_category_task_evidence_alias(
    tmp_path, monkeypatch, task_key
):
    _state, attempt, ids, _ = _gate5_attempt(
        tmp_path, monkeypatch, f"gate5-cross-alias-{task_key}"
    )
    task_ids = {
        "gate2": GATE2_TASK_ID,
        "remediation": REMEDIATION_TASK_ID,
        "review": ids["review_task"],
        "live": ids["live"],
        "gate5": ids["gate5_task"],
    }
    ids["gate5_evidence"] = task_ids[task_key]
    with pytest.raises(SemanticV11Error, match="task/evidence/process separation"):
        _validate_gate5_documents(
            repo_root=REPO,
            attempt=attempt,
            result_sha256="3" * 64,
            gate5_task_id=ids["gate5_task"],
            gate5_evidence_id=ids["gate5_evidence"],
            task_document={},
            contract_document={},
            evidence_document={},
            evidence_set_document={},
        )


def test_gate5_wrong_root_preflight_does_not_consume_then_correct_enters(
    tmp_path, monkeypatch
):
    state, attempt, ids, _ = _gate5_attempt(tmp_path, monkeypatch, "wrong-root")
    evidence = ids["gate5_preflight_document"]["payload"]["evidence"]
    details = evidence["details"]
    correct = details["state_root_identity_sha256"]
    other_root = _private(tmp_path / "other-private-root")
    details["state_root_identity_sha256"] = TaskBinding.create(
        ids["live"], REQUIRED_LIVE_COMPLETION_KIND, other_root
    ).state_root_identity_sha256
    with pytest.raises(SemanticV11Error) as captured:
        _verify_gate5(state, ids)
    assert getattr(captured.value, "started_marker_consumed") is False
    assert getattr(captured.value, "retry_allowed") is True
    assert getattr(captured.value, "artifact_integrity_review") == "not_evaluated"
    assert not list(state.glob(".dspx-*.started.json"))
    assert not (attempt.attempt_root / "independent-verification.json").exists()
    details["state_root_identity_sha256"] = correct
    accepted = _verify_gate5(state, ids)
    assert accepted["artifact_integrity_review"] == "accepted"
    assert len(list(state.glob(".dspx-*.started.json"))) == 1


@pytest.mark.parametrize(
    "variant",
    ["unbound", "malformed", "missing-actor", "extra-details", "bad-hash"],
)
def test_gate5_unbound_or_malformed_preflight_never_consumes(
    tmp_path, monkeypatch, variant
):
    state, attempt, ids, _ = _gate5_attempt(tmp_path, monkeypatch, variant)
    evidence = ids["gate5_preflight_document"]["payload"]["evidence"]
    if variant == "unbound":
        evidence["task_ref"] = ids["gate5_task"] + 1
    elif variant == "malformed":
        evidence["details"] = "malformed-private-details"
    elif variant == "missing-actor":
        evidence.pop("checked_by")
    elif variant == "extra-details":
        evidence["details"]["diagnostic"] = "private-diagnostic"
    else:
        evidence["details"]["ledger_sha256"] = "not-a-hash"
    with pytest.raises(SemanticV11Error) as captured:
        _verify_gate5(state, ids)
    assert getattr(captured.value, "started_marker_consumed") is False
    assert getattr(captured.value, "retry_allowed") is True
    assert getattr(captured.value, "artifact_integrity_review") == "not_evaluated"
    assert not list(state.glob(".dspx-*.started.json"))
    assert not (attempt.attempt_root / "independent-verification.json").exists()


def test_gate5_marker_write_failure_allows_first_real_entry(tmp_path, monkeypatch):
    state, attempt, ids, _ = _gate5_attempt(tmp_path, monkeypatch, "marker-fail")
    import dspx.services.program_oracle_semantic_gate5_persistence_v11 as persistence

    original = persistence._state_io._persist_no_replace

    def fail_marker(path: Path, payload: Any):
        if path.name.endswith(".started.json"):
            raise OSError("injected started-marker write failure")
        return original(path, payload)

    monkeypatch.setattr(persistence._state_io, "_persist_no_replace", fail_marker)
    with pytest.raises(SemanticV11Error) as captured:
        _verify_gate5(state, ids)
    assert getattr(captured.value, "started_marker_consumed") is False
    assert getattr(captured.value, "retry_allowed") is True
    assert getattr(captured.value, "artifact_integrity_review") == "not_evaluated"
    assert not list(state.glob(".dspx-*.started.json"))
    assert not (attempt.attempt_root / "independent-verification.json").exists()
    monkeypatch.setattr(persistence._state_io, "_persist_no_replace", original)
    accepted = _verify_gate5(state, ids)
    assert accepted["artifact_integrity_review"] == "accepted"


def test_gate5_first_failure_persists_one_bounded_rejection_after_start(
    tmp_path, monkeypatch
):
    state, attempt, ids, gate5 = _gate5_attempt(tmp_path, monkeypatch, "first")
    original = gate5.load_consumed_attempt

    def fail_after_start(*_args: Any):
        assert len(list(state.glob(".dspx-*.started.json"))) == 1
        raise SemanticV11Error("injected first retained-read rejection")

    monkeypatch.setattr(gate5, "load_consumed_attempt", fail_after_start)
    rejected = _verify_gate5(state, ids)
    monkeypatch.setattr(gate5, "load_consumed_attempt", original)
    retained, _ = load_independent_verification(attempt)
    assert retained == rejected
    assert rejected["artifact_integrity_review"] == "rejected"
    assert rejected["rejection_reason_code"] == "consumed_attempt_rejected"
    assert rejected["empirical_gate"] == "error"
    assert rejected["provider_invoked"] is False
    assert rejected["authority_granted"] is False
    marker = next(state.glob(".dspx-*.started.json"))
    marker_payload = json.loads(marker.read_bytes())
    assert marker.parent == state and not marker.is_relative_to(attempt.attempt_root)
    assert str(state).encode() not in marker.read_bytes()
    assert marker_payload["gate5_task_id"] == ids["gate5_task"]
    assert marker_payload["gate5_evidence_id"] == ids["gate5_evidence"]
    assert marker_payload["live_task_id"] == ids["live"]
    assert (
        marker_payload["state_root_identity_sha256"]
        == attempt.binding.state_root_identity_sha256
    )
    assert marker_payload["root_binding_id"] == attempt.binding.root_binding_id
    assert marker_payload["process_identity_sha256"] == "9" * 64
    verify_private_tree(attempt, include_verification=True)


def test_gate5_unknown_user_repo_persists_rejection_after_start(tmp_path, monkeypatch):
    state, attempt, ids, gate5 = _gate5_attempt(tmp_path, monkeypatch, "bad-repo")
    from dspx.services.program_oracle_semantic_gate5_runtime_v11 import source_manifest

    monkeypatch.setattr(gate5, "_source_manifest", source_manifest)
    rejected = gate5.verify_retained_once(
        repo_root=Path("~__dspx_missing_user_for_gate5__/repo"),
        state_root=state,
        live_task_id=ids["live"],
        gate5_task_id=ids["gate5_task"],
        gate5_evidence_id=ids["gate5_evidence"],
        owner_source_root=state / "unused-owner",
    )
    assert rejected["artifact_integrity_review"] == "rejected"
    assert rejected["rejection_reason_code"] == "candidate_source_rejected"
    assert rejected["provider_invoked"] is False
    assert len(list(state.glob(".dspx-*.started.json"))) == 1
    assert load_independent_verification(attempt)[0] == rejected
    verify_private_tree(attempt, include_verification=True)


def test_gate5_crash_marker_blocks_actual_second_process(tmp_path, monkeypatch):
    state, attempt, ids, gate5 = _gate5_attempt(tmp_path, monkeypatch, "crash")
    code = f"""
import os
from pathlib import Path
from dspx.services.program_oracle_semantic_gate5_persistence_v11 import _consume_gate5_started
_consume_gate5_started(state_root=Path({str(state)!r}), live_task_id={ids["live"]}, gate5_task_id={ids["gate5_task"]}, gate5_evidence_id={ids["gate5_evidence"]}, expected_state_root_identity_sha256={attempt.binding.state_root_identity_sha256!r})
os._exit(73)
"""
    env = {
        **os.environ,
        "PYTHONPATH": str(REPO / "packages/dspx-core/src"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    crashed = subprocess.run([sys.executable, "-c", code], env=env, check=False)
    assert crashed.returncode == 73
    assert not (attempt.attempt_root / "independent-verification.json").exists()
    monkeypatch.setattr(
        gate5, "load_consumed_attempt", lambda *_: pytest.fail("retained read repeated")
    )
    with pytest.raises(SemanticV11Error, match="retry authority is false"):
        _verify_gate5(state, ids)


def test_gate5_duplicate_invocation_is_blocked_before_retained_reads(
    tmp_path, monkeypatch
):
    state, attempt, ids, gate5 = _gate5_attempt(tmp_path, monkeypatch, "duplicate")
    accepted = _verify_gate5(state, ids)
    assert accepted["artifact_integrity_review"] == "accepted", accepted.get(
        "rejection_reason_code"
    )
    assert "rejection_reason_code" not in accepted
    before = (attempt.attempt_root / "independent-verification.json").read_bytes()
    monkeypatch.setattr(
        gate5,
        "load_consumed_attempt",
        lambda *_: pytest.fail("duplicate retained read"),
    )
    with pytest.raises(SemanticV11Error, match="retry authority is false"):
        _verify_gate5(state, ids)
    assert (
        attempt.attempt_root / "independent-verification.json"
    ).read_bytes() == before


def test_gate5_tampered_tree_persists_rejected_artifact(tmp_path, monkeypatch):
    state, attempt, ids, _ = _gate5_attempt(tmp_path, monkeypatch, "tampered")
    extra = attempt.attempt_root / "unexpected.json"
    extra.write_bytes(canonical({"unexpected": True}))
    extra.chmod(0o600)
    rejected = _verify_gate5(state, ids)
    assert rejected["artifact_integrity_review"] == "rejected"
    assert rejected["rejection_reason_code"] == "retained_tree_rejected"
    assert rejected["empirical_gate"] == "error"
    assert load_independent_verification(attempt)[0] == rejected


def test_gate5_unsafe_attempt_root_leaves_started_marker_consumed(
    tmp_path, monkeypatch
):
    state, attempt, ids, _ = _gate5_attempt(tmp_path, monkeypatch, "unsafe-root")
    attempt.attempt_root.chmod(0o755)
    try:
        with pytest.raises(SemanticV11Error) as captured:
            _verify_gate5(state, ids)
        assert getattr(captured.value, "reason_code") == "unsafe_attempt_root"
        assert getattr(captured.value, "retry_allowed") is False
        assert getattr(captured.value, "started_marker_consumed") is True
        assert len(list(state.glob(".dspx-*.started.json"))) == 1
        assert not (attempt.attempt_root / "independent-verification.json").exists()
    finally:
        attempt.attempt_root.chmod(0o700)


def test_gate5_rejection_write_failure_is_truthful_and_nonretryable(
    tmp_path, monkeypatch
):
    state, attempt, ids, gate5 = _gate5_attempt(tmp_path, monkeypatch, "write-fail")
    monkeypatch.setattr(
        gate5,
        "load_consumed_attempt",
        lambda *_: (_ for _ in ()).throw(SemanticV11Error("first rejection")),
    )
    original = gate5._state_io._persist_no_replace

    def fail_rejection(path: Path, payload: Any):
        if path.name == "independent-verification.json":
            raise OSError("injected rejection persistence failure")
        return original(path, payload)

    monkeypatch.setattr(gate5._state_io, "_persist_no_replace", fail_rejection)
    with pytest.raises(SemanticV11Error) as captured:
        _verify_gate5(state, ids)
    error = captured.value
    assert getattr(error, "retry_allowed") is False
    assert getattr(error, "started_marker_consumed") is True
    assert getattr(error, "verification_retained") is False
    assert not (attempt.attempt_root / "independent-verification.json").exists()
    assert len(list(state.glob(".dspx-*.started.json"))) == 1


def test_gate5_postwrite_verification_rejects_reread_drift(monkeypatch):
    monkeypatch.setattr(
        "dspx.services.program_oracle_semantic_gate5_v11.load_independent_verification",
        lambda *_: ({"written": "drift"}, canonical({"written": "drift"})),
    )
    with pytest.raises(SemanticV11Error, match="written verification payload"):
        _validate_written_verification(cast(Any, object()), {"written": "expected"})


@pytest.mark.parametrize(
    "field,replacement",
    {
        "candidate_commit": "c" * 40,
        "candidate_tree": "d" * 40,
        "candidate_source_manifest_sha256": "e" * 64,
        "contract_sha256": "f" * 64,
    }.items(),
)
def test_gate5_rejects_self_consistent_ledger_result_identity_rewrites(
    tmp_path, monkeypatch, field, replacement
):
    state = _private(tmp_path / field)
    docs, ids = _documents(state)
    import dspx.services.program_oracle_semantic_gate4_v11 as gate4

    monkeypatch.setattr(gate4, "_assert_preledger_import_posture", lambda: None)
    with (
        _ak_patch(tmp_path, docs, ids),
        patch(
            "dspx.services.program_oracle_semantic_gate4_validation_v11._git_identity",
            return_value=(ids["commit"], ids["tree"]),
        ),
        patch.object(
            gate4,
            "verify_loaded_runtime_modules",
            side_effect=RuntimeError("runtime-origin-failure"),
        ),
        pytest.raises(RuntimeError, match="runtime-origin"),
    ):
        execute_live_once(
            repo_root=REPO,
            state_root=state,
            owner_source_root=tmp_path,
            live_task_id=ids["live"],
            remediation_validation_evidence_id=ids["remediation_evidence"],
            review_evidence_id=ids["review_evidence"],
            operator_evidence_id=ids["operator_evidence"],
            live_gate_evidence_id=ids["live_evidence"],
        )
    attempt = load_consumed_attempt(state, ids["live"])
    result, _ = load_evaluation_result(attempt)
    assert result["cases"] == []
    ledger_path = attempt.attempt_root / "ledger.json"
    result_path = attempt.attempt_root / "evaluation-result.json"
    ledger = attempt.ledger
    ledger[field] = replacement
    ledger_raw = canonical(ledger)
    ledger_path.write_bytes(ledger_raw)
    result[field] = replacement
    result["ledger_sha256"] = sha256(ledger_raw)
    result_path.write_bytes(canonical(result))
    rewritten = load_consumed_attempt(state, ids["live"])
    assert rewritten.ledger[field] == replacement
    assert ids["commit"] == "a" * 40 and ids["tree"] == "b" * 40
    with pytest.raises(SemanticV11Error, match="authority/ledger"):
        reconstruct_authority_payloads(
            repo_root=REPO,
            state_root_identity_sha256=rewritten.binding.state_root_identity_sha256,
            ledger=rewritten.ledger,
            commit=ids["commit"],
            tree=ids["tree"],
            source_manifest=candidate_source_manifest(REPO),
            documents=docs,
        )

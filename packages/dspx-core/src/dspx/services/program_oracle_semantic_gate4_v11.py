# summary: "Monolithic canonical-read, consume, execute, and retain Gate-4 one-shot."
from __future__ import annotations

import importlib
import os
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from urllib.parse import urlsplit

import dspx.services.program_oracle_semantic_state_v11 as _state_io
from dspx.services.program_oracle_semantic_authority_v11 import (
    machine_payload,
    run_ak,
)
from dspx.services.program_oracle_semantic_gate4_contract_v11 import (
    CANDIDATE_REVIEW_NAME,
    CANDIDATE_REVIEW_SCHEMA,
    EXPECTED_ENDPOINT_ORIGIN_SHA256,
    GATE2_TASK_ID,
    LEDGER_NAME,
    LEDGER_SCHEMA,
    LIVE_GATE_NAME,
    LIVE_GATE_SCHEMA,
    PRELEDGER_ALLOWED_DSPX_MODULES,
    PRELEDGER_FORBIDDEN_PREFIXES,
    PROVIDER_OUTCOMES_NAME,
    REMEDIATION_TASK_ID,
    REQUIRED_POSTLEDGER_RUNTIME_MODULES,
    RESULT_FRAGMENTS_NAME,
    RESULT_SCHEMA,
    RESULT_NAME,
    REVIEWED_RUNTIME_MODULES,
    SemanticV11Error,
    TerminalPersistenceError,
    canonical,
    mapping,
    sha256,
)
from dspx.services.program_oracle_semantic_gate4_validation_v11 import (
    _derive_gate4_documents,
    candidate_source_manifest,
    candidate_source_manifest_sha256,
    validate_gate4_authority_documents,
)
from dspx.services.program_oracle_semantic_state_v11 import (
    ConsumedAttempt,
    TaskBinding,
    _binding_marker,
    _collision_path,
    _prepare_attempt_directories,
    _validate_artifact,
    _validate_ledger,
    current_process_identity_sha256,
    state_root_identity_sha256,
)

__all__ = [
    "candidate_source_manifest",
    "candidate_source_manifest_sha256",
    "execute_live_once",
    "validate_gate4_authority_documents",
    "verify_loaded_runtime_modules",
]

_ENDPOINT_ORIGIN_DOMAIN = b"dspx-oracle-semantic-v11-endpoint-origin-v1\0"


def _assert_preledger_import_posture() -> None:
    loaded_dspx = {
        name for name in sys.modules if name == "dspx" or name.startswith("dspx.")
    }
    if loaded_dspx != PRELEDGER_ALLOWED_DSPX_MODULES:
        raise SemanticV11Error("pre-ledger DSPx import allowlist drift")
    forbidden = {
        name
        for name in sys.modules
        if any(
            name == prefix or name.startswith(prefix + ".")
            for prefix in PRELEDGER_FORBIDDEN_PREFIXES
        )
    }
    if forbidden:
        raise SemanticV11Error("backend/evaluation/adapter/DSPy imported before ledger")


def _module_source(module: ModuleType) -> Path:
    value = getattr(module, "__file__", None)
    if (
        not isinstance(value, str)
        or value.endswith((".pyc", ".pyo"))
        or getattr(module, "__cached__", None) is not None
    ):
        raise SemanticV11Error("reviewed runtime module origin drift")
    try:
        return Path(value).resolve(strict=True)
    except OSError as exc:
        raise SemanticV11Error("reviewed runtime module origin drift") from exc


def verify_loaded_runtime_modules(
    repo_root: Path,
    reviewed_manifest: Mapping[str, str],
    *,
    require_all: bool,
) -> None:
    root = repo_root.expanduser().resolve(strict=True)
    package_roots = {
        "dspx": root / "packages/dspx-core/src/dspx",
        "dspx.services": root / "packages/dspx-core/src/dspx/services",
    }
    for package_name, expected_root in package_roots.items():
        package = sys.modules.get(package_name)
        search = getattr(package, "__path__", None) if package is not None else None
        if search is None or {Path(item).resolve(strict=True) for item in search} != {
            expected_root.resolve(strict=True)
        }:
            raise SemanticV11Error("reviewed runtime package search path drift")
    loaded_dspx = {
        name for name in sys.modules if name == "dspx" or name.startswith("dspx.")
    }
    if loaded_dspx - set(REVIEWED_RUNTIME_MODULES):
        raise SemanticV11Error("unreviewed DSPx runtime module loaded")
    for name, relative in REVIEWED_RUNTIME_MODULES.items():
        expected_path = (root / relative).resolve(strict=True)
        expected_hash = reviewed_manifest.get(relative)
        if expected_hash is None or sha256(expected_path.read_bytes()) != expected_hash:
            raise SemanticV11Error("reviewed runtime source hash drift")
        module = sys.modules.get(name)
        if module is None:
            if require_all and name in REQUIRED_POSTLEDGER_RUNTIME_MODULES:
                raise SemanticV11Error(
                    "required reviewed runtime module was not loaded"
                )
            continue
        if (
            not isinstance(module, ModuleType)
            or _module_source(module) != expected_path
        ):
            raise SemanticV11Error("reviewed runtime module origin/hash drift")


def _runtime_modules() -> SimpleNamespace:
    """Import computation-only helpers after the live ledger is durable."""

    names = {
        "adapter": "program_oracle_semantic_adapter_v11",
        "backend": "program_oracle_semantic_backend",
        "contract": "program_oracle_semantic_contract_v11",
        "evaluation": "program_oracle_semantic_evaluation_v11",
        "identity": "program_oracle_semantic_identity_v11",
        "journal": "provider_outcome_receipt_journal",
        "result": "program_oracle_semantic_result_artifact_v11",
        "semantic": "program_oracle_semantic_result_v11",
    }
    return SimpleNamespace(
        **{
            key: importlib.import_module(f"dspx.services.{suffix}")
            for key, suffix in names.items()
        }
    )


def _owner_api() -> tuple[type[Any], type[Any], str, type[Any]]:
    package = importlib.import_module("dspy_lm_auth")
    lm_module = importlib.import_module("dspy_lm_auth.lm")
    event_type = getattr(package, "OutcomeReceiptEvent", None)
    receipt_type = getattr(package, "ProviderOutcomeReceipt", None)
    endpoint = getattr(lm_module, "DEFAULT_CODEX_API_BASE", None)
    lm_type = getattr(lm_module, "LM", None)
    if (
        not isinstance(event_type, type)
        or not isinstance(receipt_type, type)
        or not isinstance(lm_type, type)
        or not isinstance(endpoint, str)
    ):
        raise SemanticV11Error("loaded owner API shape drift")
    return event_type, receipt_type, endpoint, lm_type


def _validate_endpoint(endpoint: str) -> None:
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise SemanticV11Error("owner endpoint origin drift")
    digest = sha256(
        _ENDPOINT_ORIGIN_DOMAIN
        + canonical({"scheme": parsed.scheme, "hostname": parsed.hostname})
    )
    if digest != EXPECTED_ENDPOINT_ORIGIN_SHA256:
        raise SemanticV11Error("owner endpoint origin identity drift")


def _persistence_error(
    *,
    external_effect_possible: bool,
    empirical_disposition: str,
) -> TerminalPersistenceError:
    return TerminalPersistenceError(
        external_effect_possible=external_effect_possible,
        empirical_disposition=empirical_disposition,
    )


def execute_live_once(
    *,
    repo_root: Path,
    state_root: Path,
    owner_source_root: Path,
    live_task_id: int,
    remediation_validation_evidence_id: int,
    review_evidence_id: int,
    operator_evidence_id: int,
    live_gate_evidence_id: int,
) -> dict[str, object]:
    """Trusted one-shot Gate 4; no document, report, or bearer input is accepted.

    Arbitrary code execution, monkeypatching, tracing, or reflection inside this
    interpreter is outside the capability boundary, consistent with the accepted
    same-UID sink boundary. Supported public and caller-data paths fail closed.
    """

    _assert_preledger_import_posture()
    review_document = run_ak("evidence", "show", str(review_evidence_id), "--machine")
    review_payload = machine_payload(review_document, "evidence.show")
    review_task_id = mapping(review_payload.get("evidence"), "review evidence").get(
        "task_ref"
    )
    if isinstance(review_task_id, bool) or not isinstance(review_task_id, int):
        raise SemanticV11Error("Gate-3 task selector rejected")
    documents = {
        "gate_2_task_document": run_ak("task", "show", str(GATE2_TASK_ID), "--machine"),
        "gate_2_contract_document": run_ak(
            "task", "contract", "show", str(GATE2_TASK_ID), "-F", "json"
        ),
        "gate_2_evidence_6729_document": run_ak(
            "evidence", "show", "6729", "--machine"
        ),
        "gate_2_evidence_6730_document": run_ak(
            "evidence", "show", "6730", "--machine"
        ),
        "remediation_task_document": run_ak(
            "task", "show", str(REMEDIATION_TASK_ID), "--machine"
        ),
        "remediation_contract_document": run_ak(
            "task", "contract", "show", str(REMEDIATION_TASK_ID), "-F", "json"
        ),
        "review_task_document": run_ak(
            "task", "show", str(review_task_id), "--machine"
        ),
        "review_contract_document": run_ak(
            "task", "contract", "show", str(review_task_id), "-F", "json"
        ),
        "live_task_document": run_ak("task", "show", str(live_task_id), "--machine"),
        "live_contract_document": run_ak(
            "task", "contract", "show", str(live_task_id), "-F", "json"
        ),
        "remediation_validation_evidence_document": run_ak(
            "evidence",
            "show",
            str(remediation_validation_evidence_id),
            "--machine",
        ),
        "review_evidence_document": review_document,
        "operator_evidence_document": run_ak(
            "evidence", "show", str(operator_evidence_id), "--machine"
        ),
        "live_gate_evidence_document": run_ak(
            "evidence", "show", str(live_gate_evidence_id), "--machine"
        ),
        "live_task_evidence_set_document": run_ak(
            "evidence", "task", str(live_task_id), "--machine"
        ),
    }
    facts, review, gate = _derive_gate4_documents(
        repo_root=repo_root,
        state_root=state_root,
        live_task_id=live_task_id,
        remediation_validation_evidence_id=remediation_validation_evidence_id,
        review_evidence_id=review_evidence_id,
        operator_evidence_id=operator_evidence_id,
        live_gate_evidence_id=live_gate_evidence_id,
        **documents,
    )
    process_digest = current_process_identity_sha256()
    root_digest = state_root_identity_sha256(state_root)
    if facts["state_root_identity_sha256"] != root_digest:
        raise SemanticV11Error("validated state-root binding drift")
    binding = TaskBinding(live_task_id, root_digest)
    ledger: dict[str, Any] = {
        "schema_version": LEDGER_SCHEMA,
        "artifact_kind": "consumed_attempt",
        **binding.payload(),
        "root_binding_sha256": "0" * 64,
        "status": "consumed",
        "maximum_evaluation_processes": 1,
        "retry_allowed": False,
        "process_identity_sha256": process_digest,
        "process_admitted": True,
        **{
            key: value
            for key, value in facts.items()
            if key not in {"live_task_id", "state_root_identity_sha256"}
        },
        "live_authorized": True,
    }
    _validate_artifact(review, CANDIDATE_REVIEW_SCHEMA, "candidate_review")
    _validate_artifact(gate, LIVE_GATE_SCHEMA, "live_gate")
    if (
        sha256(canonical(review)) != ledger["candidate_review_sha256"]
        or sha256(canonical(gate)) != ledger["live_gate_sha256"]
    ):
        raise SemanticV11Error("live authority artifact digest drift")
    _validate_ledger(binding, ledger)
    attempt_root = _prepare_attempt_directories(state_root, binding)
    marker_raw = _state_io._persist_no_replace(
        _collision_path(state_root.expanduser(), binding),
        _binding_marker(binding, ledger),
    )
    ledger["root_binding_sha256"] = sha256(marker_raw)
    _validate_ledger(binding, ledger)
    _state_io._persist_no_replace(attempt_root / CANDIDATE_REVIEW_NAME, review)
    _state_io._persist_no_replace(attempt_root / LIVE_GATE_NAME, gate)
    ledger_raw = _state_io._persist_no_replace(attempt_root / LEDGER_NAME, ledger)
    attempt = ConsumedAttempt(binding, attempt_root, ledger_raw)
    authority_digest = sha256(canonical(facts))
    pid = os.getpid()

    def guard() -> None:
        if (
            os.getpid() != pid
            or current_process_identity_sha256() != process_digest
            or state_root_identity_sha256(state_root) != root_digest
            or sha256(canonical(facts)) != authority_digest
            or attempt.ledger.get("live_authorized") is not True
        ):
            raise SemanticV11Error("integrated Gate-4 one-shot drift")

    def persist(
        path: Path,
        payload: Mapping[str, Any],
        *,
        effect_possible: bool,
        disposition: str,
    ) -> None:
        guard()
        try:
            _state_io._persist_no_replace(path, payload)
        except BaseException as exc:
            raise _persistence_error(
                external_effect_possible=effect_possible,
                empirical_disposition=disposition,
            ) from exc

    def setup_fragment(stage: str) -> dict[str, Any]:
        return {
            "schema_version": RESULT_SCHEMA,
            "artifact_kind": "setup_result_fragment",
            "live_task_id": live_task_id,
            "setup_stage": stage,
            "external_effect_possible": False,
            "empirical_disposition": "error",
            "reason": f"post_entry_{stage}_failed_before_provider_effect",
            "dspx_generate_entered": False,
            "invocation_admitted": False,
            "effect_capable_delegations": 0,
            "fixture_only": False,
            "v11_authorized": True,
            "live_execution_authorized": True,
        }

    def setup_result() -> dict[str, Any]:
        current = attempt.ledger
        return {
            "schema_version": RESULT_SCHEMA,
            "artifact_kind": "evaluation_result",
            "live_task_id": live_task_id,
            "task_binding": binding.payload(),
            "ledger_sha256": attempt.ledger_sha256,
            "root_binding_sha256": current["root_binding_sha256"],
            "candidate_commit": current["candidate_commit"],
            "candidate_tree": current["candidate_tree"],
            "candidate_source_manifest_sha256": current[
                "candidate_source_manifest_sha256"
            ],
            "contract_sha256": current["contract_sha256"],
            "candidate_review_sha256": current["candidate_review_sha256"],
            "live_gate_sha256": current["live_gate_sha256"],
            "authority_snapshot_sha256": current["authority_snapshot_sha256"],
            "provider_owner_source_identity_sha256": None,
            "dependency_identity_sha256": None,
            "artifact_integrity_review": "not_evaluated",
            "empirical_gate": "error",
            "cases": [],
            "operation_counts": {
                "corpus_processes": 1,
                "reached_requests": 0,
                "admitted_invocations": 0,
                "dspx_generate_calls": 0,
                "effect_capable_delegations": 0,
                "receipt_journals": 0,
                "separate_health_probes": 0,
                "dspx_managed_retries": 0,
                "fallback_routes": 0,
                "provider_transport_calls": "not_proven",
            },
            "observed_model": None,
            "fixture_only": False,
            "v11_authorized": True,
            "live_execution_authorized": True,
        }

    def terminalize_setup(original: BaseException, stage: str) -> None:
        try:
            persist(
                attempt_root / RESULT_FRAGMENTS_NAME / "00-setup.json",
                setup_fragment(stage),
                effect_possible=False,
                disposition="error",
            )
            persist(
                attempt_root / RESULT_NAME,
                setup_result(),
                effect_possible=False,
                disposition="error",
            )
        except TerminalPersistenceError:
            raise
        except BaseException as fallback:
            raise original.with_traceback(original.__traceback__) from fallback
        raise original

    try:
        runtime = _runtime_modules()
    except BaseException as original:
        terminalize_setup(original, "runtime_import")
    try:
        guard()
        reviewed_manifest = candidate_source_manifest(repo_root)
        verify_loaded_runtime_modules(repo_root, reviewed_manifest, require_all=True)
    except BaseException as original:
        terminalize_setup(original, "runtime_origin")
    try:
        event_type, receipt_type, endpoint, lm_type = _owner_api()
    except BaseException as original:
        terminalize_setup(original, "owner_api")
    try:
        owner = runtime.identity.verify_exact_owner(
            owner_source_root, event_type, receipt_type, lm_type
        )
    except BaseException as original:
        terminalize_setup(original, "owner_verification")
    try:
        cases = runtime.contract.load_bound_cases(repo_root)
    except BaseException as original:
        terminalize_setup(original, "case_load")
    try:
        requests = tuple(
            (
                case,
                runtime.evaluation.normalized_semantic_request(
                    case.materialized_request()
                ),
            )
            for case in cases
        )
    except BaseException as original:
        terminalize_setup(original, "request_normalization")
    try:
        reservations = tuple(
            runtime.identity.expected_reservation(
                attempt,
                case=case,
                semantic_request=semantic,
                artifact=owner.artifact,
            )
            for case, semantic in requests
        )
        snapshots = tuple(
            runtime.result.CaseSnapshot(
                attempt=attempt,
                case=case,
                semantic_request=semantic,
                reservation=reservation,
                artifact=owner.artifact,
            )
            for (case, semantic), reservation in zip(
                requests, reservations, strict=True
            )
        )
    except BaseException as original:
        terminalize_setup(original, "reservation")
    try:
        _validate_endpoint(endpoint)
    except BaseException as original:
        terminalize_setup(original, "endpoint")
    try:
        lm = runtime.adapter.ReceiptSafeDspyLMAuthLM()
    except BaseException as original:
        terminalize_setup(original, "adapter_construction")

    @dataclass(slots=True)
    class CaseState:
        snapshot: Any
        generate_entered: bool = False
        fragment: dict[str, Any] | None = None
        sealed: bool = False
        marker_written: bool = False
        failure_stage: str = "adapter_call"

    states = tuple(CaseState(snapshot) for snapshot in snapshots)

    def fragment_effect(payload: Mapping[str, Any]) -> tuple[bool, str]:
        provider = payload.get("provider_outcome")
        if not isinstance(provider, Mapping):
            return True, "effect_indeterminate"
        possible = provider.get("external_effect_possible") is True
        disposition = provider.get("empirical_disposition")
        return possible, (
            str(disposition)
            if disposition in {"effect_indeterminate", "error", "failed", "passed"}
            else "effect_indeterminate"
        )

    def persist_fragment(
        state: CaseState,
        payload: Mapping[str, Any],
        *,
        application_check: bool = True,
    ) -> None:
        if application_check:
            runtime.result.validate_case_fragment_write(state.snapshot, payload)
        else:
            # The primary application check failed; this local exact-shape check
            # uses only the immutable snapshot before attempting fallback bytes.
            if (
                payload.get("schema_version") != RESULT_SCHEMA
                or payload.get("artifact_kind") != "case_result_fragment"
                or payload.get("live_task_id") != live_task_id
                or payload.get("case_id") != state.snapshot.case.case_id
                or payload.get("case_ordinal") != state.snapshot.case.case_ordinal
                or payload.get("semantic_request_sha256")
                != state.snapshot.reservation.semantic_request_sha256
            ):
                raise SemanticV11Error("fallback fragment snapshot drift")
        possible, _ = fragment_effect(payload)
        persist(
            attempt_root
            / RESULT_FRAGMENTS_NAME
            / f"{state.snapshot.case.case_ordinal:02d}-case.json",
            payload,
            effect_possible=possible,
            disposition="effect_indeterminate" if possible else "error",
        )

    def persist_marker(state: CaseState, stage: str) -> None:
        if state.fragment is None or state.marker_written:
            raise SemanticV11Error("case terminal marker state drift")
        marker = runtime.result.build_case_terminal_marker(
            state.snapshot, state.fragment, stage
        )
        persist(
            attempt_root
            / RESULT_FRAGMENTS_NAME
            / f"{state.snapshot.case.case_ordinal:02d}-terminal.json",
            marker,
            effect_possible=True,
            disposition="effect_indeterminate",
        )
        state.marker_written = True

    def persist_aggregate(*, fallback_state: CaseState | None = None) -> dict[str, Any]:
        try:
            payload = runtime.result.derive_evaluation_result(attempt, snapshots)
        except BaseException as original:
            if (
                fallback_state is None
                or fallback_state.fragment is None
                or fallback_state.marker_written
            ):
                raise
            persist_marker(fallback_state, "result_fragment")
            try:
                payload = runtime.result.derive_evaluation_result(attempt, snapshots)
            except BaseException as fallback:
                raise original.with_traceback(original.__traceback__) from fallback
        effect = any(
            case["provider_outcome"]["external_effect_possible"] is True
            for case in payload["cases"]
        )
        persist(
            attempt_root / RESULT_NAME,
            payload,
            effect_possible=effect,
            disposition="effect_indeterminate" if effect else "error",
        )
        return payload

    def terminalize_case(original: BaseException, stage: str, state: CaseState) -> None:
        try:
            if not state.generate_entered:
                state.fragment = runtime.result.build_pre_generate_failure(
                    state.snapshot, stage
                )
                persist_fragment(state, state.fragment, application_check=False)
                state.sealed = True
            elif state.fragment is None:
                state.fragment = runtime.result.build_case_call_failure(state.snapshot)
                persist_fragment(state, state.fragment, application_check=False)
                state.sealed = True
            if stage in {"post_return_projection", "result_fragment"}:
                persist_marker(state, stage)
            persist_aggregate(fallback_state=state)
        except TerminalPersistenceError:
            raise
        except BaseException as fallback:
            raise original.with_traceback(original.__traceback__) from fallback
        raise original

    def invoke_case(state: CaseState) -> dict[str, Any]:
        snapshot = state.snapshot
        case = snapshot.case
        semantic = snapshot.semantic_request
        request = case.materialized_request()
        expected = runtime.evaluation.normalized_semantic_request(request)
        if (
            semantic != expected
            or runtime.contract.semantic_request_sha256(expected)
            != snapshot.reservation.semantic_request_sha256
        ):
            raise SemanticV11Error("prepared semantic request drift")
        owner.revalidate()
        root = (
            attempt_root
            / PROVIDER_OUTCOMES_NAME
            / f"{case.case_ordinal:02d}-{case.case_id}"
        )
        started = time.time()
        failed = True
        try:
            journal = runtime.journal.ReceiptJournal.create(
                root, snapshot.reservation, snapshot.artifact
            )
            receipt = journal.provider_receipt()
            base = importlib.import_module(
                "dspx.services.program_oracle_semantic_owner_bridge_v11"
            )
            if base._check_capability is not None:
                base._check_capability("network.mutate")
            inner = lm._build_inner()
            if (
                type(inner) is not owner.lm_type
                or lm._uses_codex_route is not True
                or getattr(inner, "_uses_codex_route", None) is not True
                or getattr(inner, "num_retries", None) != 0
            ):
                raise SemanticV11Error("v11 owner route/retry configuration drift")
            response = inner.forward(
                prompt=runtime.backend._analysis_prompt(request),
                messages=None,
                outcome_receipt=receipt,
                response_format=dict(
                    runtime.backend._analysis_response_format(request)
                ),
                cache=False,
                num_retries=0,
            )
            text = runtime.adapter.ReceiptSafeDspyLMAuthLM._receipt_text(response)
            if len(text.encode("utf-8")) > lm.MAX_RESPONSE_TEXT_BYTES:
                raise SemanticV11Error("provider response exceeds bounded size")
            model = runtime.adapter.ReceiptSafeDspyLMAuthLM._receipt_model(response)
            state.failure_stage = "result_fragment"
            report = runtime.semantic.validate_semantic_response(case, text)
            fragment = runtime.result.build_case_result_fragment(
                snapshot,
                semantic=report.semantic_payload(),
                observed_model=model,
            )
            persist_fragment(state, fragment)
            state.fragment = fragment
            runtime.result.validate_case_fragment_seal(snapshot, fragment)
            state.sealed = True
            failed = False
            return fragment
        finally:
            call_type = (
                getattr(base, "DspyLmAuthCall", None) if "base" in locals() else None
            )
            if isinstance(call_type, type):
                lm.history.append(
                    call_type(
                        model=lm.requested_model,
                        auth_provider=lm.auth_provider,
                        started_at=started,
                        ended_at=time.time(),
                        text="",
                        usage=None,
                        transport=None,
                        error="receipt_mode_error" if failed else None,
                    )
                )

    entered_ordinals: set[int] = set()
    last_state: CaseState | None = None
    for state in states:
        last_state = state
        try:
            runtime.result.validate_generate_entry(
                state.snapshot, frozenset(entered_ordinals)
            )
            state.generate_entered = True
            entered_ordinals.add(state.snapshot.case.case_ordinal)
        except BaseException as original:
            terminalize_case(original, "mark_generate_entered", state)
        try:
            fragment = invoke_case(state)
        except TerminalPersistenceError:
            raise
        except BaseException as original:
            terminalize_case(original, state.failure_stage, state)
        try:
            disposition = runtime.evaluation.projection_disposition(fragment)
        except BaseException as original:
            terminalize_case(original, "post_return_projection", state)
        if disposition != "passed":
            break
    return persist_aggregate(fallback_state=last_state)

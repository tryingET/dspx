# summary: "Closed task, evidence, route, source, and schema contract for semantic v11."
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any


class SemanticV11Error(ValueError):
    """Fixed-message fail-closed v11 candidate error."""


class TerminalPersistenceError(SemanticV11Error):
    """Truthful disposition when the no-replace persistence primitive fails."""

    external_effect_possible: bool
    empirical_disposition: str
    terminal_retained: bool

    def __init__(
        self,
        *,
        external_effect_possible: bool,
        empirical_disposition: str,
    ) -> None:
        super().__init__("terminal persistence failed; no terminal is claimed")
        self.external_effect_possible = external_effect_possible
        self.empirical_disposition = empirical_disposition
        self.terminal_retained = False


def canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise SemanticV11Error("value is not canonical JSON") from exc


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def assert_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise SemanticV11Error(f"{label} must be lowercase SHA-256")
    return value


def mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SemanticV11Error(f"{label} must be an object")
    return {str(key): item for key, item in value.items()}


CONTRACT_SHA256 = "23eea0a89ab4e62cb19e18f9165399c5b91dce39e9997aec6070412ac310b624"
PROPOSAL_SHA256 = "931ba8f5d71f1514bd3b4952bc28f471be1e6205889813f7801ca9261385a6d9"
CASE_ORDER = (
    "authority-boundary",
    "causal-calibration",
    "review-only-transition",
    "provenance-drift",
)
SEMANTIC_REQUEST_DOMAIN = b"dspx-oracle-semantic-request-v1\0"
SEMANTIC_KEYS = frozenset(
    {"input", "instructions", "model", "reasoning", "store", "stream", "text"}
)
OPTIONAL_UNSET_KEYS = frozenset(
    {"max_output_tokens", "temperature", "top_p", "truncation"}
)


def semantic_request_projection(request: Mapping[str, Any]) -> dict[str, Any]:
    keys = set(request)
    if not SEMANTIC_KEYS.issubset(keys):
        raise SemanticV11Error("semantic request is missing a required key")
    unknown = keys - SEMANTIC_KEYS - OPTIONAL_UNSET_KEYS
    if unknown or any(
        request.get(key) is not None for key in OPTIONAL_UNSET_KEYS & keys
    ):
        raise SemanticV11Error("semantic request contains unsupported fields")
    return {key: request[key] for key in sorted(SEMANTIC_KEYS)}


def semantic_request_sha256(request: Mapping[str, Any]) -> str:
    return sha256(
        SEMANTIC_REQUEST_DOMAIN + canonical(semantic_request_projection(request))
    )


CONSUMER_MODULE_HASHES = {
    "provider_outcome_receipt_contract.py": "08310ff976c47bb2a5a3003131ab4ce4b45787f1380418a96b109de6f1664d30",
    "provider_outcome_receipt_identity.py": "9f8a40b1b22f5fc377fb44ceb21919d2c37b48e23c04802bf340cd3fa35fc5a2",
    "provider_outcome_receipt_journal.py": "6e2df68d71f081192ac460ecab9acbc0c44445cc5014409279595a87a0a340a5",
    "provider_outcome_receipt_reducer.py": "33efcd28db0443c30069bdcb2a77ae6c9772dde25c34b2b411892302d5e48a4c",
}

GATE2_TASK_ID = 4691
REMEDIATION_TASK_ID = 4713
REJECTED_V10_TASK_ID = 4643

GATE2_COMPLETION_KIND = "oracle_semantic_v11_candidate_materialization"
REMEDIATION_COMPLETION_KIND = "oracle_semantic_v11_gate3_remediation"
REQUIRED_REVIEW_COMPLETION_KIND = "oracle_semantic_v11_candidate_review"
REQUIRED_LIVE_COMPLETION_KIND = "oracle_semantic_v11_live_execution"
REQUIRED_GATE5_COMPLETION_KIND = "oracle_semantic_v11_independent_verification"

CANDIDATE_REVIEW_SCHEMA = "dspx-oracle-semantic-v11-candidate-review-v1"
LIVE_GATE_SCHEMA = "dspx-oracle-semantic-v11-live-gate-v1"
RESULT_SCHEMA = "dspx-oracle-semantic-v11-result-v1"
VERIFICATION_SCHEMA = "dspx-oracle-semantic-v11-verification-v1"
LEDGER_SCHEMA = "dspx-oracle-semantic-v11-ledger-v1"

CANDIDATE_REVIEW_NAME = "candidate-review.json"
LIVE_GATE_NAME = "live-gate.json"
RESULT_NAME = "evaluation-result.json"
VERIFICATION_NAME = "independent-verification.json"
GATE5_STARTED_SCHEMA = "dspx-oracle-semantic-v11-gate5-started-v1"
GATE5_REJECTION_REASON_CODES = frozenset(
    {
        "consumed_attempt_rejected",
        "retained_result_rejected",
        "retained_authority_rejected",
        "candidate_source_rejected",
        "candidate_git_identity_rejected",
        "canonical_authority_read_rejected",
        "authority_reconstruction_rejected",
        "gate5_authorization_rejected",
        "runtime_origin_rejected",
        "owner_identity_rejected",
        "result_reconstruction_rejected",
        "result_comparison_rejected",
        "retained_tree_rejected",
        "accepted_payload_derivation_rejected",
    }
)
LEDGER_NAME = "ledger.json"
RESULT_FRAGMENTS_NAME = "result-fragments"
PROVIDER_OUTCOMES_NAME = "provider-outcomes"

GATE2_BASE_COMMIT = "ee27a2f241be2aa498031ab44bbd427c31c1b875"
GATE2_BASE_TREE = "6e7d394c97051ce6db7ba940429df586259c35f5"
GATE2_SCOPE_SHA256 = "974e0f60dae8c200b39282b241a3dd7f02ac93c004dacd85e4b2951670174b9c"
REMEDIATION_SCOPE_SHA256 = (
    "0c85d6986947682438db8d7fe07a160a8618a5c2ceae481794c596d5c5491ffe"
)

GATE2_DONE_CONTRACT = {
    "completion_kind": GATE2_COMPLETION_KIND,
    "required_outcomes": [
        "materialize the exact authority-false receipt-bound v11 candidate or pause_empirical_line",
        "preserve every inherited contract byte and every accepted consumer byte",
        "create no live task, live authority, provider operation, or empirical result",
    ],
    "required_validation": [
        "focused provider-free v11 and adapter tests",
        "scoped Ruff and both package and test typechecks",
        "current provider-free repository gate without waiver",
    ],
    "required_evidence_classes": [
        "exact candidate source and contract hashes",
        "hostile receipt, privacy, ordering, and fixture-ceiling tests",
        "provider-free validation results",
    ],
    "review_questions": [
        "Does every fixture and pure projection remain authority-false?",
        "Are all later gates distinct and dormant?",
    ],
}
GATE2_GUARDRAILS = {
    "invariants": [
        "unchanged v10 semantic subtrees and accepted provider-outcome consumer bytes",
        "no provider, network, authentication, shared-store, or live owner-state operation",
        "effect_indeterminate precedence and bounded privacy",
    ],
    "anti_goals": [
        "no caller-minted live authority or passing empirical result",
        "no retry, fallback, health probe, selective rerun, release, publication, or activation",
    ],
    "constraints": [
        "provider-free fake transports and disposable private roots only",
        "all retained and projected fixture outputs are authority-false",
    ],
    "rollback_boundaries": [
        "pause_empirical_line rather than weaken receipt, authority, or privacy contracts"
    ],
}

REMEDIATION_DONE_CONTRACT = {
    "completion_kind": REMEDIATION_COMPLETION_KIND,
    "required_outcomes": [
        "remediate all eleven AK-4708 Gate-3 blockers in v11-only code",
        "retain exact candidate-review, live-gate, result, and verification grammar",
        "leave benchmark, proposal, predecessors, and accepted consumer bytes unchanged",
    ],
    "required_validation": [
        "hostile regression coverage for every rejected finding",
        "focused v11, adapter, and accepted consumer tests",
        "scoped Ruff and package and test typechecks",
    ],
    "required_evidence_classes": [
        "changed-path inventory and finding-to-code/test map",
        "provider-free command results",
        "explicit residual blocker report",
    ],
    "review_questions": [
        "Can any caller, fixture, pure report, or importable token grant live authority?",
        "Can one task/evidence binding execute against more than one private root?",
        "Does Gate 5 independently rederive every retained fact in a different process?",
    ],
}
REMEDIATION_GUARDRAILS = {
    "invariants": [
        "opaque state-root binding and durable global collision per authority binding",
        "canonical full task, guardrail, and distinct evidence bindings for Gates 2 through 5",
        "ledger consumption before backend or evaluation imports",
        "strict poison, inflight, callback, reservation, operation-count, and privacy reduction",
    ],
    "anti_goals": [
        "no bearer authority, fixture-derived live result, synthesized passing metric, or gate synthesis",
        "no unbound retained schema identity or second Gate-4 entry",
        "no provider, network, authentication, shared-store, or credential operation during remediation",
    ],
    "constraints": [
        "one public one-shot live entry and one distinct one-shot Gate-5 entry",
        "fixture lanes remain authority-false and are rejected by live writers",
        "generic ReceiptProjection remains authority-false and accepted consumer bytes remain exact",
    ],
    "rollback_boundaries": [
        "stop rather than weaken effect_indeterminate precedence, authority separation, fixture ceilings, or privacy"
    ],
}

GATE3_DONE_CONTRACT = {
    "completion_kind": REQUIRED_REVIEW_COMPLETION_KIND,
    "required_outcomes": [
        "accept or reject the exact remediated v11 candidate without live execution",
        "bind Gate-2 and remediation tasks, scopes, full contracts, guardrails, and validation evidence",
        "bind exact source, Git, contract, owner, consumer, dependency, request, privacy, and nonclaim facts",
    ],
    "required_validation": [
        "provider-free exact candidate and hostile review",
        "passing current provider-free repository gate",
        "no state-root creation, ledger consumption, provider import, or provider operation",
    ],
    "required_evidence_classes": [
        "Gate-2 validation evidence",
        "remediation validation evidence",
        "canonical candidate-review evidence",
    ],
    "review_questions": [
        "Is the candidate exact and are all eleven prior blockers mechanically closed?",
        "Is separate operator and Gate-4 authority still required?",
    ],
}
GATE3_GUARDRAILS = {
    "invariants": [
        "read-only provider-free review of one exact committed clean candidate",
        "Gate 3 is distinct from Gate 2, remediation, Gate 4, and Gate 5",
        "acceptance grants no provider operation and mints no live authority",
    ],
    "anti_goals": [
        "no self-attested validation strings, caller-authored metrics, or gate synthesis",
        "no ledger, artifact root, provider, auth, network, or shared-store effect",
    ],
    "constraints": [
        "decision is exactly ACCEPT_V11_CANDIDATE_FOR_SEPARATE_LIVE_GATE or REJECT",
        "all source and evidence identities are exact and no-replace",
    ],
    "rollback_boundaries": ["any drift requires a fresh review task and evidence"],
}

GATE4_DONE_CONTRACT = {
    "completion_kind": REQUIRED_LIVE_COMPLETION_KIND,
    "required_outcomes": [
        "consume one opaque-root-bound ledger before backend or evaluation import",
        "admit at most one fixed-order corpus process and terminalize every reached case",
        "write one no-replace evaluation-result.json without performing Gate 5",
    ],
    "required_validation": [
        "rebind exact reviewed source, route, root, tasks, evidence, and operation budget",
        "derive counts from admitted invocation custody and exact receipt chains",
        "defer independent provider-free verification to a distinct Gate-5 process",
    ],
    "required_evidence_classes": [
        "canonical Gate-3 candidate review",
        "distinct explicit operator authorization",
        "canonical live-gate evidence and receipt-bound terminal result",
    ],
    "review_questions": [
        "Did root, source, route, counts, receipts, stop policy, and privacy remain exact?",
        "Was there exactly one admitted Gate-4 process and no retry path?",
    ],
}
GATE4_GUARDRAILS = {
    "invariants": [
        "one exact Gate-3-reviewed candidate and one opaque owner-private state-root identity",
        "one durable global collision marker and one task-bound consumed ledger",
        "one client-visible effect-capable delegation at most per reached request",
        "strict effect_indeterminate precedence for ambiguous effect-capable custody",
    ],
    "anti_goals": [
        "no retry, fallback, health probe, selector, selective rerun, fixture, or second process",
        "no release, publication, activation, shared-store, or generic semantic claim",
    ],
    "constraints": [
        "dspy-lm-auth codex/gpt-5.6-sol max sync cache-false retry-zero stream-true store-false",
        "stop after the first failed, error, or effect-indeterminate case",
        "retain no raw output, prompt, header, credential, URL, path, exception, traceback, or arbitrary diagnostic",
    ],
    "rollback_boundaries": [
        "the root collision, consumed ledger, receipt journals, and result fragments are immutable and non-retryable"
    ],
}

GATE5_DONE_CONTRACT = {
    "completion_kind": REQUIRED_GATE5_COMPLETION_KIND,
    "required_outcomes": [
        "validate canonical Gate-5 evidence against the supplied private-root identity before consuming one no-replace started marker",
        "independently rederive exact source, reservation, journal, result, privacy, and count facts",
        "write one no-replace accepted or rejected independent-verification.json without changing terminal bytes",
        "truthfully accept or reject artifact integrity without relabeling the empirical gate",
    ],
    "required_validation": [
        "run in a process distinct from the Gate-4 process",
        "perform zero provider, network, authentication, shared-store, retry, or result-derivation calls",
        "compare every reservation and route field including fixed endpoint-origin digest",
    ],
    "required_evidence_classes": [
        "canonical distinct Gate-5 authorization evidence",
        "independently reconstructed retained-tree evidence",
        "provider-free verification result",
    ],
    "review_questions": [
        "Did Gate 5 independently reconstruct rather than trust or call Gate-4 derivation?",
        "Were fixture and same-process attempts rejected?",
    ],
}
GATE5_GUARDRAILS = {
    "invariants": [
        "Gate 5 task and evidence are distinct from Gates 2, 3, 4 and remediation",
        "Gate 5 process identity differs from the consumed Gate-4 process identity",
        "terminal bytes, journals, ledger, candidate review, live gate, and result remain unchanged",
    ],
    "anti_goals": [
        "no post-marker retry, provider/backend invocation, event repair, result synthesis, promotion, or empirical relabeling",
        "no fixture result or authority-false projection accepted as live evidence",
    ],
    "constraints": [
        "provider-free rederivation only after root-bound canonical preflight and durable one-shot consumption, followed by one no-replace verification write",
        "preflight or absent-marker persistence failure permits correction; marker existence makes every later failure nonretryable",
        "supported integrity rejection retains one bounded authority-false rejection without inventing producer facts",
        "unknown files, schemas, fields, aliases, and ambiguous ordering fail closed",
    ],
    "rollback_boundaries": [
        "a started, failed, rejected, or indeterminate verification grants no retry or another Gate-4 entry"
    ],
}

EXACT_ROUTE = {
    "provider": "dspy-lm-auth",
    "model": "codex/gpt-5.6-sol",
    "reasoning_effort": "max",
    "mode": "sync",
    "cache": False,
    "num_retries": 0,
    "stream": True,
    "store": False,
}
REQUESTED_ROUTE = "dspy-lm-auth:codex:gpt-5.6-sol:max"
RESOLVED_ROUTE = "openai:gpt-5.6-sol:responses"
EXPECTED_ENDPOINT_ORIGIN_SHA256 = (
    "7d4b206e8a080358f16d8048e0705d8e17c9df9b8968ab150ff73ed1643294c8"
)

# Every mutable candidate byte reviewed by Gate 3. Immutable predecessors are included
# where live imports depend on them, but this task never mutates those files.
CANDIDATE_SOURCE_PATHS = (
    "benchmarks/semantic/oracle-semantic-analysis-evaluation-v11.json",
    "docs/project/oracle-semantic-analysis-v11-contract-proposal.md",
    "governance/task-scopes/AK-4691.snapshot.json",
    "governance/task-scopes/AK-4713.snapshot.json",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_owner_bridge_v11.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_adapter_v11.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_artifacts_v11.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_authority_v11.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_contract_v11.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_evaluation_v11.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_evidence_v11.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_gate4_contract_v11.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_gate4_v11.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_gate4_validation_v11.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_gate5_v11.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_gate5_authority_v11.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_gate5_journal_v11.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_gate5_persistence_v11.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_gate5_result_v11.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_gate5_runtime_v11.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_gate5_semantics_v11.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_identity_v11.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_journal_v11.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_result_artifact_v11.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_result_v11.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_review_grammar_v11.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_state_v11.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_verification_v11.py",
    "scripts/ci/run_oracle_semantic_analysis_evaluation_v11.py",
    "tests/test_dspy_lm_auth_lm.py",
    "tests/test_program_oracle_semantic_evaluation_v11.py",
)

# Local modules whose loaded origins and bytes are rebound after ledger consumption.
REVIEWED_RUNTIME_MODULES = {
    "dspx": "packages/dspx-core/src/dspx/__init__.py",
    "dspx.services": "packages/dspx-core/src/dspx/services/__init__.py",
    "dspx.model_roles": "packages/dspx-core/src/dspx/model_roles.py",
    "dspx.provider_registry": "packages/dspx-core/src/dspx/provider_registry.py",
    "dspx.dspy_typed_lm": "packages/dspx-core/src/dspx/dspy_typed_lm.py",
    "dspx.openai_compatible_provider": "packages/dspx-core/src/dspx/openai_compatible_provider.py",
    "dspx.provider_contract": "packages/dspx-core/src/dspx/provider_contract.py",
    "dspx.stub_provider": "packages/dspx-core/src/dspx/stub_provider.py",
    "dspx.capabilities": "packages/dspx-core/src/dspx/capabilities.py",
    "dspx.policy": "packages/dspx-core/src/dspx/policy.py",
    "dspx.redaction": "packages/dspx-core/src/dspx/redaction.py",
    "dspx.validators": "packages/dspx-core/src/dspx/validators.py",
    "dspx.services.program_oracle_secret_policy": "packages/dspx-core/src/dspx/services/program_oracle_secret_policy.py",
    "dspx.services.program_oracle_semantic_contract": "packages/dspx-core/src/dspx/services/program_oracle_semantic_contract.py",
    "dspx.services.program_oracle_semantic_contract_v10": "packages/dspx-core/src/dspx/services/program_oracle_semantic_contract_v10.py",
    "dspx.services.program_oracle_semantic_evaluation": "packages/dspx-core/src/dspx/services/program_oracle_semantic_evaluation.py",
    "dspx.services.program_oracle_semantic_scoring": "packages/dspx-core/src/dspx/services/program_oracle_semantic_scoring.py",
    "dspx.services.program_oracle_semantic_owner_bridge_v11": "packages/dspx-core/src/dspx/services/program_oracle_semantic_owner_bridge_v11.py",
    "dspx.services.program_oracle_semantic_adapter_v11": "packages/dspx-core/src/dspx/services/program_oracle_semantic_adapter_v11.py",
    "dspx.services.program_oracle_semantic_artifacts_v11": "packages/dspx-core/src/dspx/services/program_oracle_semantic_artifacts_v11.py",
    "dspx.services.program_oracle_semantic_authority_v11": "packages/dspx-core/src/dspx/services/program_oracle_semantic_authority_v11.py",
    "dspx.services.program_oracle_semantic_contract_v11": "packages/dspx-core/src/dspx/services/program_oracle_semantic_contract_v11.py",
    "dspx.services.program_oracle_semantic_evaluation_v11": "packages/dspx-core/src/dspx/services/program_oracle_semantic_evaluation_v11.py",
    "dspx.services.program_oracle_semantic_evidence_v11": "packages/dspx-core/src/dspx/services/program_oracle_semantic_evidence_v11.py",
    "dspx.services.program_oracle_semantic_gate4_contract_v11": "packages/dspx-core/src/dspx/services/program_oracle_semantic_gate4_contract_v11.py",
    "dspx.services.program_oracle_semantic_gate4_v11": "packages/dspx-core/src/dspx/services/program_oracle_semantic_gate4_v11.py",
    "dspx.services.program_oracle_semantic_gate4_validation_v11": "packages/dspx-core/src/dspx/services/program_oracle_semantic_gate4_validation_v11.py",
    "dspx.services.program_oracle_semantic_identity_v11": "packages/dspx-core/src/dspx/services/program_oracle_semantic_identity_v11.py",
    "dspx.services.program_oracle_semantic_journal_v11": "packages/dspx-core/src/dspx/services/program_oracle_semantic_journal_v11.py",
    "dspx.services.program_oracle_semantic_result_artifact_v11": "packages/dspx-core/src/dspx/services/program_oracle_semantic_result_artifact_v11.py",
    "dspx.services.program_oracle_semantic_result_v11": "packages/dspx-core/src/dspx/services/program_oracle_semantic_result_v11.py",
    "dspx.services.program_oracle_semantic_review_grammar_v11": "packages/dspx-core/src/dspx/services/program_oracle_semantic_review_grammar_v11.py",
    "dspx.services.program_oracle_semantic_state_v11": "packages/dspx-core/src/dspx/services/program_oracle_semantic_state_v11.py",
    "dspx.services.program_oracle_semantic_gate5_v11": "packages/dspx-core/src/dspx/services/program_oracle_semantic_gate5_v11.py",
    "dspx.services.program_oracle_semantic_gate5_authority_v11": "packages/dspx-core/src/dspx/services/program_oracle_semantic_gate5_authority_v11.py",
    "dspx.services.program_oracle_semantic_gate5_journal_v11": "packages/dspx-core/src/dspx/services/program_oracle_semantic_gate5_journal_v11.py",
    "dspx.services.program_oracle_semantic_gate5_persistence_v11": "packages/dspx-core/src/dspx/services/program_oracle_semantic_gate5_persistence_v11.py",
    "dspx.services.program_oracle_semantic_gate5_result_v11": "packages/dspx-core/src/dspx/services/program_oracle_semantic_gate5_result_v11.py",
    "dspx.services.program_oracle_semantic_gate5_runtime_v11": "packages/dspx-core/src/dspx/services/program_oracle_semantic_gate5_runtime_v11.py",
    "dspx.services.program_oracle_semantic_gate5_semantics_v11": "packages/dspx-core/src/dspx/services/program_oracle_semantic_gate5_semantics_v11.py",
    "dspx.services.program_oracle_semantic_verification_v11": "packages/dspx-core/src/dspx/services/program_oracle_semantic_verification_v11.py",
    "dspx.services.program_oracle_semantic_backend": "packages/dspx-core/src/dspx/services/program_oracle_semantic_backend.py",
    "dspx.services.provider_outcome_receipt_contract": "packages/dspx-core/src/dspx/services/provider_outcome_receipt_contract.py",
    "dspx.services.provider_outcome_receipt_identity": "packages/dspx-core/src/dspx/services/provider_outcome_receipt_identity.py",
    "dspx.services.provider_outcome_receipt_journal": "packages/dspx-core/src/dspx/services/provider_outcome_receipt_journal.py",
    "dspx.services.provider_outcome_receipt_reducer": "packages/dspx-core/src/dspx/services/provider_outcome_receipt_reducer.py",
}
RUNTIME_SUPPORT_SOURCE_PATHS = tuple(
    sorted(set(REVIEWED_RUNTIME_MODULES.values()) - set(CANDIDATE_SOURCE_PATHS))
)

PRELEDGER_ALLOWED_DSPX_MODULES = frozenset(
    {
        "dspx",
        "dspx.services",
        "dspx.services.program_oracle_semantic_gate4_contract_v11",
        "dspx.services.program_oracle_semantic_state_v11",
        "dspx.services.program_oracle_semantic_authority_v11",
        "dspx.services.program_oracle_semantic_evidence_v11",
        "dspx.services.program_oracle_semantic_gate4_validation_v11",
        "dspx.services.program_oracle_semantic_gate4_v11",
    }
)

PRELEDGER_FORBIDDEN_PREFIXES = (
    "dspy",
    "dspy_lm_auth",
    "litellm",
    "httpx",
    "httpcore",
    "dspx.services.program_oracle_semantic_owner_bridge_v11",
    "dspx.services.program_oracle_semantic_backend",
    "dspx.services.program_oracle_semantic_evaluation",
    "dspx.services.program_oracle_semantic_adapter",
    "dspx.services.program_oracle_semantic_identity",
    "dspx.services.program_oracle_semantic_result",
    "dspx.services.program_oracle_semantic_runner",
    "dspx.services.provider_outcome_receipt",
)

REQUIRED_POSTLEDGER_RUNTIME_MODULES = frozenset(
    {
        "dspx",
        "dspx.services",
        "dspx.services.program_oracle_semantic_owner_bridge_v11",
        "dspx.services.program_oracle_secret_policy",
        "dspx.services.program_oracle_semantic_backend",
        "dspx.services.program_oracle_semantic_contract",
        "dspx.services.program_oracle_semantic_contract_v10",
        "dspx.services.program_oracle_semantic_scoring",
        "dspx.services.program_oracle_semantic_adapter_v11",
        "dspx.services.program_oracle_semantic_state_v11",
        "dspx.services.program_oracle_semantic_authority_v11",
        "dspx.services.program_oracle_semantic_contract_v11",
        "dspx.services.program_oracle_semantic_evaluation_v11",
        "dspx.services.program_oracle_semantic_journal_v11",
        "dspx.services.program_oracle_semantic_gate4_validation_v11",
        "dspx.services.program_oracle_semantic_evidence_v11",
        "dspx.services.program_oracle_semantic_gate4_contract_v11",
        "dspx.services.program_oracle_semantic_gate4_v11",
        "dspx.services.program_oracle_semantic_identity_v11",
        "dspx.services.program_oracle_semantic_result_artifact_v11",
        "dspx.services.program_oracle_semantic_result_v11",
        "dspx.services.program_oracle_semantic_state_v11",
        "dspx.services.provider_outcome_receipt_contract",
        "dspx.services.provider_outcome_receipt_identity",
        "dspx.services.provider_outcome_receipt_journal",
        "dspx.services.provider_outcome_receipt_reducer",
    }
)

# summary: "Closed Gate-3/Gate-4 task, route, and candidate-source contract for v11."
from __future__ import annotations

REQUIRED_LIVE_COMPLETION_KIND = "oracle_semantic_v11_live_execution"
REQUIRED_REVIEW_COMPLETION_KIND = "oracle_semantic_v11_candidate_review"

GATE4_DONE_CONTRACT = {
    "completion_kind": REQUIRED_LIVE_COMPLETION_KIND,
    "required_outcomes": [
        "exact reviewed v11 candidate consumed at most one corpus process",
        "every reached case terminalized under the receipt-bound stop policy",
    ],
    "required_validation": [
        "write no-replace evaluation-result.json",
        "defer provider-free independent verification to Gate 5",
    ],
    "required_evidence_classes": [
        "canonical Gate-3 acceptance",
        "explicit operator authorization",
        "receipt-bound terminal result",
    ],
    "review_questions": [
        "Did source, route, operation counts, receipts, and stop policy remain exact?"
    ],
}
GATE4_GUARDRAILS = {
    "invariants": [
        "exact Gate-3-reviewed candidate, contract, owner, consumer, and dependency identities",
        "one task-bound ledger and at most one fixed-order corpus process",
    ],
    "anti_goals": [
        "no retry, fallback, health probe, selective rerun, or second process",
        "no release, publication, activation, shared-store, or generic semantic claim",
    ],
    "constraints": [
        "dspy-lm-auth codex/gpt-5.6-sol max sync cache-false retry-zero stream-true store-false",
        "stop after the first failed, error, or effect-indeterminate case",
    ],
    "rollback_boundaries": [
        "the consumed ledger and every retained terminal are immutable and non-retryable"
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
EXPECTED_ENDPOINT_ORIGIN_SHA256 = (
    "7d4b206e8a080358f16d8048e0705d8e17c9df9b8968ab150ff73ed1643294c8"
)
CANDIDATE_SOURCE_PATHS = (
    "benchmarks/semantic/oracle-semantic-analysis-evaluation-v11.json",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_adapter_v11.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_artifacts_v11.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_contract_v11.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_evaluation_v11.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_gate4_contract_v11.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_gate4_v11.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_identity_v11.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_result_artifact_v11.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_result_v11.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_runner_v11.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_verification_v11.py",
    "scripts/ci/run_oracle_semantic_analysis_evaluation_v11.py",
    "tests/test_dspy_lm_auth_lm.py",
    "tests/test_program_oracle_semantic_evaluation_v11.py",
)

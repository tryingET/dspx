# summary: "Refuses artifact verification for the zero-process AK-4574 v7 candidate."
# read_when:
#   - "Validating that pending v7 cannot consume or promote evaluation artifacts."

from __future__ import annotations

from pathlib import Path
from typing import Any

from dspx.services.program_oracle_semantic_evaluation import (
    SemanticAnalysisEvaluationError,
    _mapping,
    load_contract,
)

LIVE_EVIDENCE_CLASS = "production_adapter_live_behavior"
WIRING_EVIDENCE_CLASS = "test_double_wiring_only"
SOURCE_PATHS = (
    "benchmarks/semantic/oracle-semantic-analysis-evaluation-v7.json",
    "packages/dspx-core/src/dspx/dspy_lm_auth_lm.py",
    "packages/dspx-core/src/dspx/model_roles.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_backend.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_contract.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_evaluation.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_scoring.py",
    "packages/dspx-core/src/dspx/services/program_oracle_semantic_verification.py",
    "scripts/ci/run_oracle_semantic_analysis_evaluation.py",
)


def verify_evaluation(*, repo_root: Path, root: Path) -> dict[str, Any]:
    """Refuse v7 artifact verification before inspecting the supplied root."""

    del root
    contract, _ = load_contract(repo_root)
    route = _mapping(contract.get("route"), "route")
    if route.get("live_authorized") is False:
        raise SemanticAnalysisEvaluationError(
            "AK-4574 v7 authorizes no evaluation artifact verification"
        )
    raise SemanticAnalysisEvaluationError(
        "semantic-analysis contract did not declare a supported verification route"
    )

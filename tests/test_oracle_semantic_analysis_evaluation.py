# summary: "Preserves v8 semantic evidence while proving the removed live provider cannot be retried after the typed cutover."
# read_when:
#   - "Changing historical Oracle semantic evidence or typed-provider cutover boundaries."

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dspx.provider_registry import UnsupportedProviderError, create
from dspx.services.program_oracle_semantic_contract_v10 import SemanticV10Error
from dspx.services.program_oracle_semantic_evaluation_v10 import _production_backend

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_v8_and_v10_contract_artifacts_remain_historical_evidence() -> None:
    for version in (8, 10):
        path = (
            REPO_ROOT
            / f"benchmarks/semantic/oracle-semantic-analysis-evaluation-v{version}.json"
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(payload, dict)
        assert path.is_file()


def test_removed_semantic_provider_cannot_be_constructed_or_fallback() -> None:
    with pytest.raises(UnsupportedProviderError):
        create("dspy-lm-auth")


def test_terminal_v10_backend_is_not_retried_after_typed_cutover() -> None:
    with pytest.raises(SemanticV10Error, match="effect_indeterminate.*not retried"):
        _production_backend()

# summary: "Exact semantic request construction and integrated live case execution."
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dspx.services.program_oracle_semantic_backend import (
    _analysis_prompt,
    _analysis_response_format,
)
from dspx.services.program_oracle_semantic_contract_v11 import SemanticV11Error
from dspx.services.program_oracle_semantic_result_v11 import validate_semantic_response

DEFAULT_CODEX_INSTRUCTIONS = "You are a helpful assistant."
RESOLVED_MODEL = "openai/gpt-5.6-sol"


def normalized_semantic_request(request: Any) -> dict[str, Any]:
    """Build the exact seven-key owner Responses projection before effect."""

    response_format = _analysis_response_format(request)
    return {
        "input": [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": _analysis_prompt(request)}],
            }
        ],
        "instructions": DEFAULT_CODEX_INSTRUCTIONS,
        "model": RESOLVED_MODEL,
        "reasoning": {"effort": "max", "summary": "auto"},
        "store": False,
        "stream": True,
        "text": {"format": response_format},
    }


def validate_fixture_response(invocation_case: Any, raw: str) -> dict[str, Any]:
    """Provider-free scoring diagnostic whose output is explicitly authority-false."""

    report = validate_semantic_response(invocation_case, raw)
    return report.payload()


def projection_disposition(fragment: Mapping[str, Any]) -> str:
    provider = fragment.get("provider_outcome")
    if not isinstance(provider, Mapping):
        raise SemanticV11Error("case provider projection missing")
    disposition = provider.get("empirical_disposition")
    if disposition not in {"effect_indeterminate", "error", "failed", "passed"}:
        raise SemanticV11Error("case provider projection disposition drift")
    return str(disposition)

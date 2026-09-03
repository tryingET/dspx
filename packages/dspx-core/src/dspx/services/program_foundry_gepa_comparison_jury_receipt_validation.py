# summary: "Drift checks for retained foundry comparison-jury results and receipts against their bound lineage."
# read_when:
#   - "Changing how comparison-jury results or receipts are checked for drift before reuse or receipt writing."

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from dspx.services.program_foundry_gepa_comparison_jury_attempt import (
    load_json_snapshot,
    validate_attempt,
)
from dspx.services.program_foundry_gepa_comparison_jury_result import (
    validate_task_local_jury_result,
)
from dspx.services.program_foundry_gepa_comparison_jury_runtime import (
    ProgramFoundryGepaComparisonJuryError,
    receipt_payload,
)
from dspx.services.program_model_jury_validation import (
    validate_program_model_jury_results_contract,
)


def _validate_jury_result(
    *,
    result_path: Path,
    validated: Mapping[str, Any],
    request: Mapping[str, Any],
    attempt_sha256: str,
) -> tuple[dict[str, Any], str]:
    result, digest = load_json_snapshot(result_path, label="comparison jury results")
    validate_program_model_jury_results_contract(
        result,
        label="foundry GEPA comparison jury results",
        error_type=ProgramFoundryGepaComparisonJuryError,
        valid_manifest_refs={
            Path(str(validated["candidate_manifest_path"])): str(
                validated["candidate_manifest_sha256"]
            )
        },
    )
    evidence = result.get("evidence")
    entries = evidence.get("entries") if isinstance(evidence, Mapping) else None
    comparison_path = str(validated["comparison_path"])
    comparison_hash = str(validated["comparison_sha256"])
    comparison_entries = [
        entry
        for entry in entries or []
        if isinstance(entry, Mapping) and entry.get("path") == comparison_path
    ]
    if (
        len(comparison_entries) != 1
        or comparison_entries[0].get("sha256") != comparison_hash
    ):
        raise ProgramFoundryGepaComparisonJuryError(
            "comparison jury results do not bind the receipt comparison exactly once"
        )
    validate_task_local_jury_result(
        result=result,
        result_path=result_path,
        validated=validated,
        request=request,
        attempt_sha256=attempt_sha256,
    )
    return result, digest


def _validate_existing_receipt(
    *,
    validated: Mapping[str, Any],
    request: Mapping[str, Any],
    input_sha256: Mapping[Path, str],
    paths: Mapping[str, Path],
) -> dict[str, Any]:
    _, attempt_sha256 = validate_attempt(
        path=paths["attempt"],
        validated=validated,
        request=request,
        input_sha256=input_sha256,
    )
    result, result_sha256 = _validate_jury_result(
        result_path=paths["result"],
        validated=validated,
        request=request,
        attempt_sha256=attempt_sha256,
    )
    expected = receipt_payload(
        validated=validated,
        request=request,
        attempt_sha256=attempt_sha256,
        result=result,
        result_sha256=result_sha256,
        paths=paths,
    )
    receipt, _ = load_json_snapshot(paths["receipt"], label="comparison jury receipt")
    if receipt != expected:
        raise ProgramFoundryGepaComparisonJuryError(
            "comparison jury receipt or bound artifacts drifted"
        )
    return {**receipt, "reused": True}


__all__ = [
    "_validate_existing_receipt",
    "_validate_jury_result",
]

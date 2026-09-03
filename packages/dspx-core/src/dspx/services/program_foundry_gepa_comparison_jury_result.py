"""Retained result validation for the task-local foundry provider families."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dspx.services.program_foundry_gepa_comparison_jury_provider import (
    validate_foundry_jury_provider_metadata,
)
from dspx.services.program_foundry_gepa_comparison_jury_provider_evidence import (
    validate_foundry_jury_provider_evidence,
)
from dspx.services.program_foundry_gepa_comparison_jury_runtime import (
    ProgramFoundryGepaComparisonJuryError,
    task_local_family,
)
from dspx.services.program_foundry_gepa_proposal_io import read_regular_bytes


def _load_selection(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            read_regular_bytes(path, label="jury selection").decode("utf-8")
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProgramFoundryGepaComparisonJuryError(
            "jury selection must be valid JSON"
        ) from exc
    if not isinstance(value, dict):
        raise ProgramFoundryGepaComparisonJuryError(
            "jury selection must contain an object"
        )
    return value


def validate_task_local_jury_result(
    *,
    result: Mapping[str, Any],
    result_path: Path,
    validated: Mapping[str, Any],
    request: Mapping[str, Any],
    attempt_sha256: str,
) -> None:
    family = task_local_family(request)
    if family is None:
        return
    jury = result.get("jury")
    outcome_evidence = (
        jury.get("provider_outcome_evidence") if isinstance(jury, Mapping) else None
    )
    provider_config = jury.get("provider_config") if isinstance(jury, Mapping) else None
    juror_results = result.get("juror_results")
    if (
        not isinstance(outcome_evidence, Mapping)
        or not isinstance(provider_config, Mapping)
        or not isinstance(juror_results, list)
    ):
        raise ProgramFoundryGepaComparisonJuryError(
            "task-local jury result requires provider outcome evidence"
        )
    selection = _load_selection(
        Path(str(validated["candidate_manifest_path"])).parent / "jury_selection.json"
    )
    raw_selected = selection.get("selected_jurors")
    if not isinstance(raw_selected, list):
        raise ProgramFoundryGepaComparisonJuryError(
            "task-local jury selection identities are invalid"
        )
    selected = [item for item in raw_selected if isinstance(item, Mapping)]
    max_jurors = request["max_jurors"]
    if isinstance(max_jurors, int):
        selected = selected[:max_jurors]
    expected_jurors = [
        (
            str(item.get("id") or item.get("perspective") or ""),
            item.get("perspective"),
        )
        for item in selected
    ]
    expected_model = str(request[family.model_key])
    raw_effort = request.get("reasoning_effort")
    reasoning_effort = str(raw_effort) if raw_effort is not None else None
    if len(expected_jurors) != len(juror_results) or any(
        not isinstance(item, Mapping)
        or item.get("juror_id") != expected_id
        or item.get("perspective") != expected_perspective
        or item.get("provider") != family.provider_name
        or item.get("model") != expected_model
        for item, (expected_id, expected_perspective) in zip(
            juror_results, expected_jurors, strict=True
        )
    ):
        raise ProgramFoundryGepaComparisonJuryError(
            "task-local jury result juror identities are invalid"
        )
    juror_ids = [item[0] for item in expected_jurors]
    try:
        validate_foundry_jury_provider_metadata(
            provider_config,
            execution_task_id=int(request["execution_task_id"]),
            execution_claimant=str(request["execution_claimant"]),
            model=expected_model,
            reasoning_effort=reasoning_effort,
            family=family,
        )
        validated_outcome = validate_foundry_jury_provider_evidence(
            outcome_evidence,
            journal_parent=result_path.parent / "provider-outcomes",
            owner_source_root=Path(str(request["owner_source_root"])),
            execution_task_id=int(request["execution_task_id"]),
            contract_sha256=attempt_sha256,
            expected_juror_ids=juror_ids,
            expected_model=expected_model,
            family=family,
        )
        call_records = validated_outcome["call_records"]
        call_total = validated_outcome["logical_call_total"]
        if not isinstance(call_records, list) or not isinstance(call_total, int):
            raise ProgramFoundryGepaComparisonJuryError(
                "task-local provider call evidence is invalid"
            )
        for index, juror_result in enumerate(juror_results):
            if not isinstance(juror_result, Mapping):
                raise ProgramFoundryGepaComparisonJuryError(
                    "task-local juror result is invalid"
                )
            if index >= call_total:
                if juror_result.get("status") != "failed":
                    raise ProgramFoundryGepaComparisonJuryError(
                        "juror without provider journal must be failed"
                    )
                continue
            record = call_records[index]
            if (
                not isinstance(record, Mapping)
                or record.get("producer_terminal") != "provider_response_completed"
            ) and juror_result.get("status") != "failed":
                raise ProgramFoundryGepaComparisonJuryError(
                    "non-completed provider journal cannot back a judged juror"
                )
    except ValueError as exc:
        raise ProgramFoundryGepaComparisonJuryError(str(exc)) from exc


__all__ = ["validate_task_local_jury_result"]

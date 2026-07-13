# summary: "Revalidates canonical successful foundry GEPA execution receipts for downstream consumers."
# read_when:
#   - "Changing downstream GEPA execution-chain validation or canonical receipt consumption."

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dspx.services.program_foundry_gepa_execution import (
    ProgramFoundryGepaExecutionError,
    read_foundry_gepa_json_at,
    validate_existing_foundry_gepa_execution_state,
)
from dspx.services.program_foundry_gepa_execution_contract import (
    mapping,
    sha256_bytes,
    validate_execution_proposal,
)
from dspx.services.program_foundry_gepa_proposal_io import (
    assert_path_descriptor_identity,
    read_root_relative_bytes,
)


def validate_successful_program_foundry_gepa_execution_receipt(
    execution_receipt_path: Path,
    *,
    root_descriptor: int,
) -> dict[str, Any]:
    """Revalidate a canonical successful execution chain without invoking GEPA."""

    receipt_path = execution_receipt_path.expanduser().absolute()
    experiment_root = receipt_path.parent
    root = experiment_root.parent
    assert_path_descriptor_identity(root, root_descriptor, label="foundry root")
    if receipt_path != experiment_root / "execution-receipt.json" or (
        experiment_root.name != "gepa-experiment"
    ):
        raise ProgramFoundryGepaExecutionError(
            "execution receipt must be the canonical foundry GEPA receipt"
        )
    proposal_path = root / "gepa_experiment_proposal.json"
    proposal_bytes = read_root_relative_bytes(
        root_descriptor,
        "gepa_experiment_proposal.json",
        label="foundry GEPA proposal",
    )
    try:
        proposal = json.loads(proposal_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProgramFoundryGepaExecutionError(
            "foundry GEPA proposal must be valid JSON"
        ) from exc
    if not isinstance(proposal, dict):
        raise ProgramFoundryGepaExecutionError(
            "foundry GEPA proposal must contain one JSON object"
        )
    proposal_sha256 = sha256_bytes(proposal_bytes)
    validated = validate_execution_proposal(
        proposal_path=proposal_path,
        proposal_sha256=proposal_sha256,
        payload=proposal,
        root=root,
    )
    directory = os.open(
        "gepa-experiment",
        os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=root_descriptor,
    )
    assert_path_descriptor_identity(
        experiment_root,
        directory,
        label="foundry GEPA experiment directory",
    )
    attempt, _ = read_foundry_gepa_json_at(
        directory, "attempt.json", label="GEPA attempt"
    )
    declaration = mapping(attempt.get("review_declaration"))
    operator_label = str(declaration.get("operator_label") or "")
    try:
        receipt = validate_existing_foundry_gepa_execution_state(
            directory,
            validated=validated,
            operator_label=operator_label,
            strict_receipt=True,
        )
        _, execution_receipt_sha256 = read_foundry_gepa_json_at(
            directory,
            "execution-receipt.json",
            label="GEPA execution receipt",
        )
    finally:
        os.close(directory)
    if receipt.get("status") != "ok":
        raise ProgramFoundryGepaExecutionError(
            "foundry GEPA execution receipt must be terminal and successful"
        )
    return {
        **validated,
        "root": root,
        "experiment_root": experiment_root,
        "execution_receipt": receipt,
        "execution_receipt_path": receipt_path,
        "execution_receipt_sha256": execution_receipt_sha256,
        "proposal_path": proposal_path,
    }

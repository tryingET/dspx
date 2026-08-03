#!/usr/bin/env python3
# summary: "Validates the adjudicated AK-4574 semantic contract and refuses evaluation effects."
# read_when:
#   - "Validating the frozen field rubric or confirming that v7 authorizes no evaluation process."

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from dspx.redaction import sanitize_diagnostic_text
from dspx.services.program_oracle_semantic_evaluation import (
    SemanticAnalysisEvaluationError,
    load_contract,
)
from dspx.services.program_oracle_semantic_verification import verify_evaluation

_CASE_ORDER = (
    "authority-boundary",
    "causal-calibration",
    "review-only-transition",
    "provenance-drift",
)

__all__ = ("run_evaluation", "verify_evaluation")


def run_evaluation(
    *,
    repo_root: Path,
    root: Path,
    evidence_class: str = "production_adapter_live_behavior",
) -> dict[str, Any]:
    """Refuse every v7 evaluation class before resolving an effectful surface."""

    del root, evidence_class
    load_contract(repo_root)
    raise SemanticAnalysisEvaluationError(
        "AK-4574 v7 authorizes no evaluation process; a separately tasked "
        "successor is required"
    )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    for name in ("run", "verify"):
        command = subparsers.add_parser(name)
        command.add_argument("--root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            contract, contract_hash = load_contract(_repo_root())
            print(
                json.dumps(
                    {
                        "schema_version": contract.get("schema_version"),
                        "status": contract.get("status"),
                        "contract_sha256": contract_hash,
                        "live_authorized": contract.get("route", {}).get(
                            "live_authorized"
                        ),
                        "maximum_evaluation_processes": contract.get(
                            "attempt_policy", {}
                        ).get("maximum_evaluation_processes"),
                    },
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "run":
            run_evaluation(repo_root=_repo_root(), root=args.root)
            return 1
        verify_evaluation(repo_root=_repo_root(), root=args.root)
        return 1
    except SemanticAnalysisEvaluationError as exc:
        print(f"error: {sanitize_diagnostic_text(str(exc))}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

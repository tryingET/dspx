#!/usr/bin/env python3
# summary: "Provider-free preflight plus explicitly gated dormant v11 entrypoints."
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dspx.services.program_oracle_semantic_artifacts_v11 import (
    REQUIRED_LIVE_COMPLETION_KIND,
    TaskBinding,
)
from dspx.services.program_oracle_semantic_verification_v11 import candidate_manifest


def _required_path(
    parser: argparse.ArgumentParser, value: Path | None, name: str
) -> Path:
    if value is None:
        parser.error(f"{name} is required for this operation")
    return value


def _required_int(parser: argparse.ArgumentParser, value: int | None, name: str) -> int:
    if value is None:
        parser.error(f"{name} is required for this operation")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate or explicitly enter the Oracle semantic v11 lifecycle"
    )
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--task-binding-check", type=int)
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument(
        "--execute-live",
        action="store_true",
        help="authenticate canonical AK Gate-4 authority, consume, then run once",
    )
    operation.add_argument(
        "--verify-retained",
        action="store_true",
        help="provider-free Gate-5 re-derivation of an already terminal attempt",
    )
    parser.add_argument("--state-root", type=Path)
    parser.add_argument("--owner-source-root", type=Path)
    parser.add_argument("--live-task-id", type=int)
    parser.add_argument("--review-evidence-id", type=int)
    parser.add_argument("--gate-evidence-id", type=int)
    args = parser.parse_args()

    if args.execute_live:
        state_root = _required_path(parser, args.state_root, "--state-root")
        owner_root = _required_path(
            parser, args.owner_source_root, "--owner-source-root"
        )
        task_id = _required_int(parser, args.live_task_id, "--live-task-id")
        review_id = _required_int(
            parser, args.review_evidence_id, "--review-evidence-id"
        )
        gate_id = _required_int(parser, args.gate_evidence_id, "--gate-evidence-id")
        from dspx.services.program_oracle_semantic_gate4_v11 import (
            authenticate_gate4_authority,
        )
        from dspx.services.program_oracle_semantic_runner_v11 import run_corpus

        authority = authenticate_gate4_authority(
            repo_root=args.repo,
            live_task_id=task_id,
            review_evidence_id=review_id,
            gate_evidence_id=gate_id,
        )
        payload = run_corpus(
            repo_root=args.repo,
            state_root=state_root,
            owner_source_root=owner_root,
            authority=authority,
        )
    elif args.verify_retained:
        state_root = _required_path(parser, args.state_root, "--state-root")
        owner_root = _required_path(
            parser, args.owner_source_root, "--owner-source-root"
        )
        task_id = _required_int(parser, args.live_task_id, "--live-task-id")
        from dspy_lm_auth import (  # ty: ignore[unresolved-import]
            OutcomeReceiptEvent,
            ProviderOutcomeReceipt,
        )
        from dspy_lm_auth.lm import LM as OwnerLM  # ty: ignore[unresolved-import]

        from dspx.services.program_oracle_semantic_identity_v11 import (
            verify_exact_owner,
        )
        from dspx.services.program_oracle_semantic_verification_v11 import (
            write_independent_verification,
        )

        owner = verify_exact_owner(
            owner_root,
            OutcomeReceiptEvent,
            ProviderOutcomeReceipt,
            OwnerLM,
        )
        payload = write_independent_verification(
            repo_root=args.repo,
            state_root=state_root,
            live_task_id=task_id,
            artifact=owner.artifact,
        )
    else:
        payload = candidate_manifest(args.repo)
        if args.task_binding_check is not None:
            payload["task_binding"] = TaskBinding.create(
                args.task_binding_check, REQUIRED_LIVE_COMPLETION_KIND
            ).payload()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

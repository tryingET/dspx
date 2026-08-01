#!/usr/bin/env python3
# ---
# summary: "Provides the standalone non-publishing Core owner authorization CLI."
# ---

from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import secrets
from typing import Any, cast

from core_release_authorization_consumer import (
    NonceLedger,
    SnapshotInputs,
    consume_shadow,
    derive_live_snapshot,
    payload_from_snapshot,
)
from core_release_evidence_io import CoreReleaseEvidenceError
from core_release_owner_authorization import (
    canonical_payload,
    load_json as load_owner_json,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _add_snapshot_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--trust-checkpoint", type=Path, required=True)
    parser.add_argument("--owner-checkpoint", type=Path, required=True)
    parser.add_argument("--evidence-bundle", type=Path, required=True)
    parser.add_argument("--statement", type=Path, required=True)
    parser.add_argument("--sigstore-bundle", type=Path, required=True)
    parser.add_argument("--subject", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--receipt-statement", type=Path, required=True)
    parser.add_argument("--receipt-sigstore-bundle", type=Path, required=True)
    parser.add_argument("--trusted-root", type=Path, required=True)


def _inputs_from_args(args: argparse.Namespace) -> SnapshotInputs:
    return SnapshotInputs(
        repo_root=args.repo_root,
        trust_checkpoint=args.trust_checkpoint,
        owner_checkpoint=args.owner_checkpoint,
        evidence_bundle=args.evidence_bundle,
        statement_path=args.statement,
        sigstore_bundle=args.sigstore_bundle,
        subject_path=args.subject,
        receipt_path=args.receipt,
        receipt_statement_path=args.receipt_statement,
        receipt_sigstore_bundle=args.receipt_sigstore_bundle,
        trusted_root_path=args.trusted_root,
    )


def _snapshot(inputs: SnapshotInputs, *, now: datetime) -> dict[str, Any]:
    return derive_live_snapshot(
        repo_root=inputs.repo_root,
        trust_checkpoint=inputs.trust_checkpoint,
        owner_checkpoint=inputs.owner_checkpoint,
        evidence_bundle=inputs.evidence_bundle,
        statement_path=inputs.statement_path,
        sigstore_bundle=inputs.sigstore_bundle,
        subject_path=inputs.subject_path,
        receipt_path=inputs.receipt_path,
        receipt_statement_path=inputs.receipt_statement_path,
        receipt_sigstore_bundle=inputs.receipt_sigstore_bundle,
        trusted_root_path=inputs.trusted_root_path,
        now=now,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--payload", type=Path, required=True)
    _add_snapshot_arguments(prepare)
    consume = commands.add_parser("consume-shadow")
    consume.add_argument("--payload", type=Path, required=True)
    consume.add_argument("--signature", type=Path, required=True)
    consume.add_argument("--ledger", type=Path, required=True)
    _add_snapshot_arguments(consume)
    args = parser.parse_args()
    inputs = _inputs_from_args(args)
    if args.command == "prepare":
        snapshot = _snapshot(inputs, now=_utc_now())
        issued_at = _utc_now()
        payload = payload_from_snapshot(
            snapshot,
            nonce=secrets.token_hex(32),
            issued_at=issued_at,
            expires_at=issued_at + timedelta(minutes=10),
        )
        owner_policy = cast(Mapping[str, Any], snapshot["owner_policy"])
        raw = canonical_payload(payload, policy=owner_policy, now=_utc_now())
        args.payload.parent.mkdir(parents=True, exist_ok=True)
        try:
            with args.payload.open("xb") as output:
                output.write(raw)
        except FileExistsError as exc:
            raise CoreReleaseEvidenceError(
                "approval payload output already exists"
            ) from exc
        args.payload.chmod(0o600)
        result = {
            "status": "prepared_for_interactive_owner_signature",
            "payload": str(args.payload),
            "payload_sha256": hashlib.sha256(raw).hexdigest(),
            "release_authority": False,
            "package_publication": False,
        }
    else:
        payload = load_owner_json(args.payload, "approval payload")
        result = consume_shadow(
            payload=payload,
            signature_path=args.signature,
            ledger=NonceLedger(args.ledger),
            inputs=inputs,
        )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CoreReleaseEvidenceError as exc:
        raise SystemExit(f"Core release authorization consumer failed: {exc}") from exc

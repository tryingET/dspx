#!/usr/bin/env python3
# ---
# summary: "Runs a non-publishing fail-closed shadow consumer for exact Core owner authorization."
# ---

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, cast

from core_release_custody import validate_receipt, verify_current_availability
from core_release_evidence_io import (
    CoreReleaseEvidenceError,
    sha256,
    stable_regular_bytes,
)
from core_release_authorization_ledger import NonceLedger
from core_release_authorization_snapshot import SnapshotInputs, stage_run_inputs
from core_release_owner_authorization import (
    OWNER_SELECTOR_REF_PATTERN,
    PAYLOAD_SCHEMA,
    authenticate_owner_approval,
    canonical_payload,
)
from core_release_owner_policy_live import resolve_live_current_owner_policy
from core_release_policy import load_json, loads_json, mapping
from core_release_policy_live import resolve_live_current_policy
from core_release_signing import enforce_denylist, validate_statement_against_bundle
from core_release_signing_identity import verify_sigstore_bundle

REPOSITORY = "tryingET/dspx"
RECEIPT_SCHEMA = "dspx-core-release-authorization-shadow-receipt-v1"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise CoreReleaseEvidenceError(f"{label} timestamp drift")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise CoreReleaseEvidenceError(f"{label} timestamp drift") from exc
    if parsed.tzinfo != timezone.utc:
        raise CoreReleaseEvidenceError(f"{label} timestamp drift")
    return parsed


def _derive_snapshot(inputs: SnapshotInputs, *, now: datetime) -> dict[str, Any]:
    return _derive_staged_snapshot(
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
        ak_command=inputs.ak_command,
        gh_command=inputs.gh_command,
    )


def _git_show_json(
    repo_root: Path, commit: str, path: str, label: str
) -> Mapping[str, Any]:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "show", f"{commit}:{path}"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise CoreReleaseEvidenceError(f"{label} Git blob is unavailable")
    return loads_json(result.stdout, label)


def _selected_policy(
    repo_root: Path, selector: Mapping[str, Any], label: str
) -> Mapping[str, Any]:
    selected = mapping(selector.get("policy"), f"{label} selected policy")
    commit = selected.get("commit")
    path = selected.get("path")
    if not isinstance(commit, str) or not isinstance(path, str):
        raise CoreReleaseEvidenceError(f"{label} selected policy locator drift")
    return _git_show_json(repo_root, commit, path, label)


def _query_observation(run_id: int, *, gh_command: str = "gh") -> dict[str, Any]:
    result = subprocess.run(
        [
            gh_command,
            "api",
            "--paginate",
            f"repos/{REPOSITORY}/actions/runs/{run_id}/artifacts?per_page=100",
            "--slurp",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise CoreReleaseEvidenceError("fresh GitHub artifact observation failed")
    try:
        pages = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise CoreReleaseEvidenceError(
            "fresh GitHub observation is invalid JSON"
        ) from exc
    if not isinstance(pages, list):
        raise CoreReleaseEvidenceError("fresh GitHub observation pagination drift")
    artifacts: list[object] = []
    for page in pages:
        if not isinstance(page, Mapping) or not isinstance(page.get("artifacts"), list):
            raise CoreReleaseEvidenceError("fresh GitHub observation page drift")
        artifacts.extend(cast(list[object], page["artifacts"]))
    return {
        "schema_version": "dspx-github-artifact-observation-v1",
        "query_status": "success",
        "run_id": run_id,
        "complete": True,
        "artifacts": artifacts,
    }


def _receipt_artifact(
    observation: Mapping[str, Any], evidence_id: int
) -> Mapping[str, Any]:
    artifacts = observation.get("artifacts")
    if not isinstance(artifacts, list):
        raise CoreReleaseEvidenceError("fresh receipt artifacts drift")
    expected_name = f"dspx-core-custody-receipt-{evidence_id}"
    matches = [
        item
        for item in artifacts
        if isinstance(item, Mapping) and item.get("name") == expected_name
    ]
    if len(matches) != 1:
        raise CoreReleaseEvidenceError("fresh receipt artifact identity drift")
    return cast(Mapping[str, Any], matches[0])


def _derive_staged_snapshot(
    *,
    repo_root: Path,
    trust_checkpoint: Path,
    owner_checkpoint: Path,
    evidence_bundle: Path,
    statement_path: Path,
    sigstore_bundle: Path,
    subject_path: Path,
    receipt_path: Path,
    receipt_statement_path: Path,
    receipt_sigstore_bundle: Path,
    trusted_root_path: Path,
    now: datetime,
    ak_command: str = "ak",
    gh_command: str = "gh",
) -> dict[str, Any]:
    trust_resolution = resolve_live_current_policy(
        repo_root=repo_root, checkpoint_path=trust_checkpoint, ak_command=ak_command
    )
    owner_resolution = resolve_live_current_owner_policy(
        repo_root=repo_root,
        checkpoint_path=owner_checkpoint,
        ak_command=ak_command,
        now=now,
    )
    trust_ref = cast(str, trust_resolution["selector_ref"])
    owner_ref = cast(str, owner_resolution["selector_ref"])
    trust_match = __import__("core_release_policy").SELECTOR_REF_PATTERN.fullmatch(
        trust_ref
    )
    if trust_match is None:
        raise CoreReleaseEvidenceError("current trust selector reference drift")
    trust_selector = _git_show_json(
        repo_root,
        trust_match.group("commit"),
        trust_match.group("path"),
        "current trust selector",
    )
    trust_policy = _selected_policy(repo_root, trust_selector, "current trust policy")
    owner_selector = cast(Mapping[str, Any], owner_resolution["selector"])
    owner_policy = _selected_policy(repo_root, owner_selector, "current owner policy")

    statement_raw = stable_regular_bytes(
        statement_path, label="signed statement", limit=16 * 1024 * 1024
    )
    statement = load_json(statement_path, "signed statement")
    validate_statement_against_bundle(
        statement=statement,
        policy=trust_policy,
        bundle_path=evidence_bundle,
        repo_root=repo_root,
    )
    enforce_denylist(
        statement=statement, statement_raw=statement_raw, policy=trust_policy
    )
    _verify_with_policy(
        statement_path=statement_path,
        bundle_path=sigstore_bundle,
        subject_path=subject_path,
        policy=trust_policy,
        trusted_root_path=trusted_root_path,
    )

    receipt = validate_receipt(load_json(receipt_path, "custody receipt"))
    _verify_with_policy(
        statement_path=receipt_statement_path,
        bundle_path=receipt_sigstore_bundle,
        subject_path=receipt_path,
        policy=trust_policy,
        trusted_root_path=trusted_root_path,
    )
    predicate = mapping(statement["predicate"], "statement predicate")
    workflow = mapping(predicate["workflow"], "statement workflow")
    run_id = cast(int, workflow["run_id"])
    observation = _query_observation(run_id, gh_command=gh_command)
    evidence_artifact = mapping(
        receipt["evidence_artifact"], "receipt evidence artifact"
    )
    receipt_artifact = _receipt_artifact(
        observation, cast(int, evidence_artifact["id"])
    )
    availability = verify_current_availability(
        receipt=receipt,
        receipt_artifact_id=cast(int, receipt_artifact["id"]),
        receipt_provider_digest=cast(str, receipt_artifact["digest"]),
        observation=observation,
        now=now,
    )
    if availability != {"status": "current", "release_use_custody": True}:
        raise CoreReleaseEvidenceError("fresh paired custody is not current")
    if receipt["signed_statement_sha256"] != sha256(statement_raw):
        raise CoreReleaseEvidenceError("receipt signed statement binding drift")
    subject = mapping(cast(list[object], statement["subject"])[0], "statement subject")
    wheel_digest = mapping(subject["digest"], "statement subject digest")["sha256"]
    auxiliary = {
        item["role"]: item
        for item in cast(list[Mapping[str, Any]], predicate["auxiliary_evidence"])
    }
    package = mapping(predicate["package"], "statement package")
    source = mapping(predicate["source"], "statement source")
    owner_auth = mapping(owner_policy["authentication"], "owner authentication")
    receipt_policy = mapping(receipt["policy"], "receipt policy")
    receipt_workflow = mapping(receipt["workflow"], "receipt workflow")
    evidence_raw = stable_regular_bytes(
        evidence_bundle, label="evidence bundle", limit=1024 * 1024 * 1024
    )
    sigstore_raw = stable_regular_bytes(
        sigstore_bundle, label="evidence Sigstore bundle", limit=16 * 1024 * 1024
    )
    if (
        receipt["evidence_bundle_sha256"] != sha256(evidence_raw)
        or receipt["bundle_manifest_sha256"] != auxiliary["bundle_manifest"]["sha256"]
        or receipt["sigstore_bundle_sha256"] != sha256(sigstore_raw)
        or receipt["source_commit_sha"] != source["commit_sha"]
        or receipt_policy.get("version") != trust_policy["policy_version"]
        or receipt_policy.get("selector") != trust_ref
        or receipt_workflow.get("run_id") != run_id
        or receipt_workflow.get("run_attempt") != workflow["run_attempt"]
    ):
        raise CoreReleaseEvidenceError("receipt current evidence binding drift")
    return {
        "trust_policy_version": trust_policy["policy_version"],
        "trust_selector_ref": trust_ref,
        "owner_policy_version": owner_policy["owner_policy_version"],
        "owner_selector_ref": owner_ref,
        "owner_key_fingerprint": owner_auth["fingerprint_sha256"],
        "owner_decision_id": owner_resolution["decision_id"],
        "wheel_sha256": wheel_digest,
        "bundle_manifest_sha256": auxiliary["bundle_manifest"]["sha256"],
        "signed_statement_sha256": sha256(statement_raw),
        "source_commit_sha": source["commit_sha"],
        "package_version": package["version"],
        "workflow_run_id": run_id,
        "workflow_run_attempt": workflow["run_attempt"],
        "evidence_artifact_id": evidence_artifact["id"],
        "evidence_provider_digest": evidence_artifact["provider_digest"],
        "receipt_artifact_id": receipt_artifact["id"],
        "receipt_provider_digest": receipt_artifact["digest"],
        "evidence_expires_at": receipt["expires_at"],
        "receipt_expires_at": receipt_artifact["expires_at"],
        "owner_policy": dict(owner_policy),
    }


def derive_live_snapshot(
    *,
    repo_root: Path,
    trust_checkpoint: Path,
    owner_checkpoint: Path,
    evidence_bundle: Path,
    statement_path: Path,
    sigstore_bundle: Path,
    subject_path: Path,
    receipt_path: Path,
    receipt_statement_path: Path,
    receipt_sigstore_bundle: Path,
    trusted_root_path: Path,
    now: datetime,
    ak_command: str = "ak",
    gh_command: str = "gh",
) -> dict[str, Any]:
    inputs = SnapshotInputs(
        repo_root=repo_root,
        trust_checkpoint=trust_checkpoint,
        owner_checkpoint=owner_checkpoint,
        evidence_bundle=evidence_bundle,
        statement_path=statement_path,
        sigstore_bundle=sigstore_bundle,
        subject_path=subject_path,
        receipt_path=receipt_path,
        receipt_statement_path=receipt_statement_path,
        receipt_sigstore_bundle=receipt_sigstore_bundle,
        trusted_root_path=trusted_root_path,
        ak_command=ak_command,
        gh_command=gh_command,
    )
    with stage_run_inputs(inputs) as staged:
        return _derive_snapshot(staged.inputs, now=now)


def _verify_with_policy(
    *,
    statement_path: Path,
    bundle_path: Path,
    subject_path: Path,
    policy: Mapping[str, Any],
    trusted_root_path: Path,
) -> None:
    import tempfile

    with tempfile.TemporaryDirectory(prefix="dspx-current-trust-") as directory:
        policy_path = Path(directory) / "policy.json"
        policy_path.write_text(
            json.dumps(dict(policy), sort_keys=True) + "\n", encoding="utf-8"
        )
        policy_path.chmod(0o600)
        verify_sigstore_bundle(
            statement_path=statement_path,
            bundle_path=bundle_path,
            subject_path=subject_path,
            policy_path=policy_path,
            trusted_root_path=trusted_root_path,
        )


def payload_from_snapshot(
    snapshot: Mapping[str, Any],
    *,
    nonce: str,
    issued_at: datetime,
    expires_at: datetime,
) -> dict[str, Any]:
    return {
        "schema_version": PAYLOAD_SCHEMA,
        "repository": {"name": REPOSITORY, "id": 1_318_473_695},
        "policy_version": snapshot["trust_policy_version"],
        "policy_selector_ref": snapshot["trust_selector_ref"],
        "owner_policy_version": snapshot["owner_policy_version"],
        "owner_policy_selector_ref": snapshot["owner_selector_ref"],
        "owner_key_fingerprint": snapshot["owner_key_fingerprint"],
        "wheel_sha256": snapshot["wheel_sha256"],
        "bundle_manifest_sha256": snapshot["bundle_manifest_sha256"],
        "signed_statement_sha256": snapshot["signed_statement_sha256"],
        "source_commit_sha": snapshot["source_commit_sha"],
        "package_version": snapshot["package_version"],
        "workflow_run_id": snapshot["workflow_run_id"],
        "workflow_run_attempt": snapshot["workflow_run_attempt"],
        "purpose": "authorize-dspx-core-wheel-release",
        "nonce": nonce,
        "issued_at": issued_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": expires_at.astimezone(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "authority_ref": f"ak-decision:{snapshot['owner_decision_id']}",
    }


def consume_shadow(
    *,
    payload: Mapping[str, Any],
    signature_path: Path,
    ledger: NonceLedger,
    inputs: SnapshotInputs,
) -> dict[str, Any]:
    owner_ref = payload.get("owner_policy_selector_ref")
    fingerprint = payload.get("owner_key_fingerprint")
    nonce = payload.get("nonce")
    if (
        not isinstance(owner_ref, str)
        or OWNER_SELECTOR_REF_PATTERN.fullmatch(owner_ref) is None
        or not isinstance(fingerprint, str)
        or not fingerprint.startswith("SHA256:")
        or not isinstance(nonce, str)
        or len(nonce) != 64
        or any(character not in "0123456789abcdef" for character in nonce)
    ):
        raise CoreReleaseEvidenceError("authorization reservation identity drift")
    preliminary_raw = (
        json.dumps(dict(payload), sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    payload_digest = hashlib.sha256(preliminary_raw).hexdigest()
    with stage_run_inputs(inputs, signature_path=signature_path) as staged:
        if staged.signature_path is None:
            raise CoreReleaseEvidenceError("owner approval signature staging failed")
        ledger.reserve(
            owner_selector_ref=owner_ref,
            fingerprint=fingerprint,
            nonce=nonce,
            payload_sha256=payload_digest,
            now=_utc_now(),
        )
        first = _derive_snapshot(staged.inputs, now=_utc_now())
        expected = payload_from_snapshot(
            first,
            nonce=nonce,
            issued_at=_utc_timestamp(payload.get("issued_at"), "approval issued_at"),
            expires_at=_utc_timestamp(payload.get("expires_at"), "approval expires_at"),
        )
        if dict(payload) != expected:
            raise CoreReleaseEvidenceError(
                "approval payload does not match independently derived evidence"
            )
        owner_policy = cast(Mapping[str, Any], first["owner_policy"])
        authentication = authenticate_owner_approval(
            policy=owner_policy,
            payload=payload,
            signature_path=staged.signature_path,
            consumed_nonces=set(),
            now=_utc_now(),
        )
        second = _derive_snapshot(staged.inputs, now=_utc_now())
        if dict(first) != dict(second):
            raise CoreReleaseEvidenceError(
                "authorization currentness changed after nonce reservation"
            )
        final_now = _utc_now()
        for field in ("evidence_expires_at", "receipt_expires_at"):
            if final_now >= _utc_timestamp(second.get(field), field):
                raise CoreReleaseEvidenceError(
                    "authorization custody expired before finalization"
                )
        final_raw = canonical_payload(payload, policy=owner_policy, now=final_now)
        if hashlib.sha256(final_raw).hexdigest() != payload_digest:
            raise CoreReleaseEvidenceError("authorization canonical payload changed")
        receipt = {
            "schema_version": RECEIPT_SCHEMA,
            "status": "shadow_verified_not_authorized",
            "payload_sha256": payload_digest,
            "owner_selector_ref": owner_ref,
            "trust_selector_ref": first["trust_selector_ref"],
            "nonce": nonce,
            "security_key_counter": authentication["security_key_counter"],
            "evidence_artifact_id": first["evidence_artifact_id"],
            "receipt_artifact_id": first["receipt_artifact_id"],
            "linearization_point": "durable_nonce_receipt_commit",
            "finalized_at": final_now.astimezone(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "release_authority": False,
            "package_publication": False,
            "sdist_supported": False,
        }
        ledger.finalize(
            owner_selector_ref=owner_ref,
            fingerprint=fingerprint,
            nonce=nonce,
            payload_sha256=payload_digest,
            receipt=receipt,
        )
        return receipt

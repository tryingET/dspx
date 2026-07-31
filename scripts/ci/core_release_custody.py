#!/usr/bin/env python3
# ---
# summary: "Validates public Core evidence, custody receipts, and GitHub artifact observations."
# read_when:
#   - "Changing Core CI evidence disclosure, retention, receipts, or provider-effect handling."
# ---

from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
from typing import Any, cast
import zipfile

from core_release_bundle_contract import validate_bundle
from core_release_custody_provider import (
    classify_upload_observation,
    verify_artifact_pair_availability,
)
from core_release_evidence_io import (
    MAX_ARTIFACT_BYTES,
    MAX_JSON_BYTES,
    CoreReleaseEvidenceError,
    stable_regular_bytes,
    write_json,
)
from core_release_public_scan import secret_matches, scan_nested_release_archive

RECEIPT_SCHEMA = "dspx-core-ci-custody-receipt-v1"
REPOSITORY = "tryingET/dspx"
REPOSITORY_ID = 1_318_473_695
OWNER_ID = 260_287_438
WORKFLOW_PATH = ".github/workflows/core-release-evidence.yml"
ENVIRONMENT = "core-release-evidence"
RETENTION_DAYS = {"trusted_run_14d": 14, "release_candidate_90d": 90}
PROVIDER_TIMESTAMP_TOLERANCE = timedelta(seconds=60)
_ALLOWED_FIXED_MEMBERS = {
    "bundle-manifest.json",
    "dspx-core-installed-environment-sbom.cdx.json",
    "dspx-core-release-evidence.json",
    "dspx-core-wheel-sbom.cdx.json",
    "installed-core-golden-path-proof.json",
    "local-build-provenance.json",
}
_RECEIPT_FIELDS = {
    "schema_version",
    "evidence_artifact",
    "evidence_bundle_sha256",
    "bundle_manifest_sha256",
    "signed_statement_sha256",
    "sigstore_bundle_sha256",
    "repository",
    "workflow",
    "source_commit_sha",
    "policy",
    "retention",
    "observed_at",
    "expires_at",
    "claims",
}


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CoreReleaseEvidenceError(f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise CoreReleaseEvidenceError(
            f"{label} fields drift: expected {sorted(fields)!r}, observed {sorted(value)!r}"
        )


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise CoreReleaseEvidenceError(f"{label} must be a positive integer")
    return value


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise CoreReleaseEvidenceError(f"{label} must be a UTC RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise CoreReleaseEvidenceError(f"{label} is invalid") from exc
    if parsed.tzinfo != timezone.utc:
        raise CoreReleaseEvidenceError(f"{label} must be UTC")
    return parsed


def _load_json(path: Path, label: str) -> Mapping[str, Any]:
    raw = stable_regular_bytes(path, label=label, limit=MAX_JSON_BYTES)

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise CoreReleaseEvidenceError(f"{label} has duplicate key {key!r}")
            result[key] = value
        return result

    try:
        return _mapping(json.loads(raw, object_pairs_hook=reject_duplicates), label)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoreReleaseEvidenceError(f"{label} is not valid JSON") from exc


def validate_public_bundle(path: Path) -> dict[str, Any]:
    manifest = validate_bundle(path)
    raw = stable_regular_bytes(
        path, label="Core release bundle", limit=2 * MAX_ARTIFACT_BYTES
    )
    try:
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            names = archive.namelist()
            declared = {
                cast(str, _mapping(entry, "manifest file entry").get("filename"))
                for entry in cast(list[object], manifest.get("files"))
            }
            allowed = _ALLOWED_FIXED_MEMBERS | {
                name for name in declared if name.endswith((".whl", ".tar.gz"))
            }
            if set(names) != allowed or set(names) != declared | {
                "bundle-manifest.json"
            }:
                raise CoreReleaseEvidenceError("public bundle member allowlist drift")
            payloads = {name: archive.read(name) for name in names}
            findings: dict[str, list[str]] = {}
            for name, member_raw in payloads.items():
                matches = secret_matches(member_raw)
                nested = scan_nested_release_archive(name, member_raw)
                if matches or nested:
                    findings[name] = matches + [
                        f"nested-member:{member}" for member in nested
                    ]
            if findings:
                raise CoreReleaseEvidenceError(
                    f"public bundle contains secret-shaped content: {sorted(findings)!r}"
                )
    except zipfile.BadZipFile as exc:
        raise CoreReleaseEvidenceError("public bundle is not a valid ZIP") from exc
    return {
        "schema_version": "dspx-core-public-bundle-preflight-v1",
        "status": "passed",
        "bundle_sha256": _sha256(raw),
        "manifest_sha256": _sha256(payloads["bundle-manifest.json"]),
        "member_count": len(allowed),
        "public_non_secret_evidence": True,
        "package_publication": False,
        "release_authority": False,
    }


def validate_public_upload_files(paths: list[Path]) -> dict[str, Any]:
    expected = {
        "evidence.zip",
        "signed-statement.json",
        "statement.sigstore.json",
    }
    by_name = {path.name: path for path in paths}
    if set(by_name) != expected or len(paths) != len(expected):
        raise CoreReleaseEvidenceError("public upload file allowlist drift")
    bundle = validate_public_bundle(by_name["evidence.zip"])
    digests: dict[str, str] = {}
    for name, path in by_name.items():
        limit = 2 * MAX_ARTIFACT_BYTES if name == "evidence.zip" else MAX_JSON_BYTES
        raw = stable_regular_bytes(path, label=f"public upload {name}", limit=limit)
        if secret_matches(raw):
            raise CoreReleaseEvidenceError(
                f"public upload {name} contains secret-shaped content"
            )
        digests[name] = _sha256(raw)
    return {
        "schema_version": "dspx-core-public-upload-preflight-v1",
        "status": "passed",
        "files": digests,
        "bundle_manifest_sha256": bundle["manifest_sha256"],
        "public_non_secret_evidence": True,
        "package_publication": False,
        "release_authority": False,
    }


def build_receipt(metadata: Mapping[str, Any]) -> dict[str, Any]:
    retention_class = metadata.get("retention_class")
    if retention_class not in RETENTION_DAYS:
        raise CoreReleaseEvidenceError("unsupported custody retention class")
    requested_days = RETENTION_DAYS[cast(str, retention_class)]
    provider_cap = _positive_int(
        metadata.get("provider_retention_cap_days"), "provider retention cap"
    )
    if provider_cap < requested_days:
        raise CoreReleaseEvidenceError(
            "provider retention cap is below requested class"
        )
    observed_at = _timestamp(metadata.get("observed_at"), "observed_at")
    expires_at = _timestamp(metadata.get("expires_at"), "expires_at")
    if expires_at + PROVIDER_TIMESTAMP_TOLERANCE < observed_at + timedelta(
        days=requested_days
    ):
        raise CoreReleaseEvidenceError(
            "provider expiry is earlier than requested retention"
        )
    artifact = {
        "id": _positive_int(metadata.get("artifact_id"), "artifact ID"),
        "url": metadata.get("artifact_url"),
        "provider_digest": metadata.get("artifact_digest"),
        "name": metadata.get("artifact_name"),
        "visibility": "public",
    }
    if not isinstance(artifact["url"], str) or not artifact["url"].startswith(
        f"https://github.com/{REPOSITORY}/actions/runs/"
    ):
        raise CoreReleaseEvidenceError("artifact URL is outside the trusted repository")
    if not isinstance(artifact["provider_digest"], str) or not re.fullmatch(
        r"sha256:[0-9a-f]{64}", cast(str, artifact["provider_digest"])
    ):
        raise CoreReleaseEvidenceError("artifact provider digest is invalid")
    if not isinstance(artifact["name"], str) or not cast(
        str, artifact["name"]
    ).startswith("dspx-core-evidence-"):
        raise CoreReleaseEvidenceError("artifact name is untrusted")
    for field in (
        "evidence_bundle_sha256",
        "bundle_manifest_sha256",
        "signed_statement_sha256",
        "sigstore_bundle_sha256",
        "workflow_file_sha256",
    ):
        if not _is_sha256(metadata.get(field)):
            raise CoreReleaseEvidenceError(f"{field} must be SHA-256")
    source_sha = metadata.get("source_commit_sha")
    if (
        not isinstance(source_sha, str)
        or re.fullmatch(r"[0-9a-f]{40}", source_sha) is None
    ):
        raise CoreReleaseEvidenceError("source commit SHA is invalid")
    workflow = {
        "path": WORKFLOW_PATH,
        "ref": "refs/heads/main",
        "file_sha256": metadata["workflow_file_sha256"],
        "event": "workflow_dispatch",
        "environment": ENVIRONMENT,
        "run_id": _positive_int(metadata.get("run_id"), "workflow run ID"),
        "run_attempt": _positive_int(
            metadata.get("run_attempt"), "workflow run attempt"
        ),
    }
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "evidence_artifact": artifact,
        "evidence_bundle_sha256": metadata["evidence_bundle_sha256"],
        "bundle_manifest_sha256": metadata["bundle_manifest_sha256"],
        "signed_statement_sha256": metadata["signed_statement_sha256"],
        "sigstore_bundle_sha256": metadata["sigstore_bundle_sha256"],
        "repository": {"name": REPOSITORY, "id": REPOSITORY_ID, "owner_id": OWNER_ID},
        "workflow": workflow,
        "source_commit_sha": source_sha,
        "policy": {
            "version": _positive_int(metadata.get("policy_version"), "policy version"),
            "selector": metadata.get("policy_selector"),
        },
        "retention": {
            "class": retention_class,
            "requested_days": requested_days,
            "provider_cap_days": provider_cap,
        },
        "observed_at": metadata["observed_at"],
        "expires_at": metadata["expires_at"],
        "claims": {
            "evidence_publication_only": True,
            "package_release_authority": False,
            "package_publication": False,
            "current_availability_requires_fresh_observation": True,
        },
    }
    validate_receipt(receipt)
    return receipt


def validate_receipt(value: object) -> dict[str, Any]:
    receipt = _mapping(value, "custody receipt")
    _exact(receipt, _RECEIPT_FIELDS, "custody receipt")
    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        raise CoreReleaseEvidenceError("custody receipt schema drift")
    repository = _mapping(receipt.get("repository"), "receipt repository")
    if repository != {"name": REPOSITORY, "id": REPOSITORY_ID, "owner_id": OWNER_ID}:
        raise CoreReleaseEvidenceError("custody receipt repository drift")
    workflow = _mapping(receipt.get("workflow"), "receipt workflow")
    expected_workflow_fields = {
        "path",
        "ref",
        "file_sha256",
        "event",
        "environment",
        "run_id",
        "run_attempt",
    }
    if set(workflow) != expected_workflow_fields:
        raise CoreReleaseEvidenceError("custody receipt workflow fields drift")
    if (
        workflow.get("path") != WORKFLOW_PATH
        or workflow.get("ref") != "refs/heads/main"
    ):
        raise CoreReleaseEvidenceError("custody receipt workflow identity drift")
    if (
        workflow.get("event") != "workflow_dispatch"
        or workflow.get("environment") != ENVIRONMENT
    ):
        raise CoreReleaseEvidenceError("custody receipt workflow context drift")
    _positive_int(workflow.get("run_id"), "workflow run ID")
    _positive_int(workflow.get("run_attempt"), "workflow run attempt")
    if not _is_sha256(workflow.get("file_sha256")):
        raise CoreReleaseEvidenceError("custody receipt workflow digest drift")
    source_sha = receipt.get("source_commit_sha")
    if (
        not isinstance(source_sha, str)
        or re.fullmatch(r"[0-9a-f]{40}", source_sha) is None
    ):
        raise CoreReleaseEvidenceError("custody receipt source commit drift")
    policy = _mapping(receipt.get("policy"), "receipt policy")
    if set(policy) != {"version", "selector"}:
        raise CoreReleaseEvidenceError("custody receipt policy fields drift")
    _positive_int(policy.get("version"), "policy version")
    if not isinstance(policy.get("selector"), str) or not cast(
        str, policy["selector"]
    ).startswith("dspx-core-policy-selector-v1:git:"):
        raise CoreReleaseEvidenceError("custody receipt policy selector drift")
    artifact = _mapping(receipt.get("evidence_artifact"), "receipt evidence artifact")
    if set(artifact) != {"id", "url", "provider_digest", "name", "visibility"}:
        raise CoreReleaseEvidenceError("custody receipt artifact fields drift")
    _positive_int(artifact.get("id"), "artifact ID")
    if artifact.get("visibility") != "public":
        raise CoreReleaseEvidenceError("custody receipt must declare public visibility")
    if not isinstance(artifact.get("name"), str) or not cast(
        str, artifact["name"]
    ).startswith("dspx-core-evidence-"):
        raise CoreReleaseEvidenceError("custody receipt artifact name drift")
    if not isinstance(artifact.get("url"), str) or not cast(
        str, artifact["url"]
    ).startswith(f"https://github.com/{REPOSITORY}/actions/runs/"):
        raise CoreReleaseEvidenceError("custody receipt artifact URL drift")
    if not isinstance(artifact.get("provider_digest"), str) or not re.fullmatch(
        r"sha256:[0-9a-f]{64}", cast(str, artifact["provider_digest"])
    ):
        raise CoreReleaseEvidenceError("custody receipt provider digest drift")
    retention = _mapping(receipt.get("retention"), "receipt retention")
    retention_class = retention.get("class")
    if (
        retention_class not in RETENTION_DAYS
        or retention.get("requested_days") != RETENTION_DAYS[cast(str, retention_class)]
    ):
        raise CoreReleaseEvidenceError("custody receipt retention drift")
    if _positive_int(
        retention.get("provider_cap_days"), "provider retention cap"
    ) < cast(int, retention.get("requested_days")):
        raise CoreReleaseEvidenceError("custody receipt provider cap is insufficient")
    observed = _timestamp(receipt.get("observed_at"), "observed_at")
    expires = _timestamp(receipt.get("expires_at"), "expires_at")
    if expires + PROVIDER_TIMESTAMP_TOLERANCE < observed + timedelta(
        days=cast(int, retention["requested_days"])
    ):
        raise CoreReleaseEvidenceError("custody receipt expiry is too early")
    claims = _mapping(receipt.get("claims"), "receipt claims")
    if claims != {
        "evidence_publication_only": True,
        "package_release_authority": False,
        "package_publication": False,
        "current_availability_requires_fresh_observation": True,
    }:
        raise CoreReleaseEvidenceError("custody receipt authority claims drift")
    for field in (
        "evidence_bundle_sha256",
        "bundle_manifest_sha256",
        "signed_statement_sha256",
        "sigstore_bundle_sha256",
    ):
        if not _is_sha256(receipt.get(field)):
            raise CoreReleaseEvidenceError(f"custody receipt {field} drift")
    return dict(receipt)


def verify_current_availability(
    *,
    receipt: object,
    receipt_artifact_id: int,
    receipt_provider_digest: str,
    observation: object,
    now: datetime,
) -> dict[str, Any]:
    valid = validate_receipt(receipt)
    if now >= _timestamp(valid["expires_at"], "expires_at"):
        return {"status": "expired", "release_use_custody": False}
    return verify_artifact_pair_availability(
        evidence_artifact=_mapping(
            valid["evidence_artifact"], "receipt evidence artifact"
        ),
        receipt_artifact_id=receipt_artifact_id,
        receipt_provider_digest=receipt_provider_digest,
        observation=observation,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    bundle = commands.add_parser("preflight-bundle")
    bundle.add_argument("--bundle", type=Path, required=True)
    upload = commands.add_parser("preflight-upload")
    upload.add_argument("--file", action="append", type=Path, required=True)
    receipt = commands.add_parser("build-receipt")
    receipt.add_argument("--metadata", type=Path, required=True)
    receipt.add_argument("--out", type=Path, required=True)
    validate = commands.add_parser("validate-receipt")
    validate.add_argument("--receipt", type=Path, required=True)
    observe = commands.add_parser("observe-upload")
    observe.add_argument("--observation", type=Path, required=True)
    observe.add_argument(
        "--operation-outcome", choices=("success", "failure"), required=True
    )
    observe.add_argument("--name", required=True)
    observe.add_argument("--run-id", type=int, required=True)
    availability = commands.add_parser("verify-availability")
    availability.add_argument("--receipt", type=Path, required=True)
    availability.add_argument("--receipt-artifact-id", type=int, required=True)
    availability.add_argument("--receipt-provider-digest", required=True)
    availability.add_argument("--observation", type=Path, required=True)
    availability.add_argument("--now", required=True)
    args = parser.parse_args()
    if args.command == "preflight-bundle":
        payload = validate_public_bundle(args.bundle)
    elif args.command == "preflight-upload":
        payload = validate_public_upload_files(args.file)
    elif args.command == "build-receipt":
        payload = build_receipt(_load_json(args.metadata, "custody metadata"))
        write_json(args.out, payload)
    elif args.command == "validate-receipt":
        payload = validate_receipt(_load_json(args.receipt, "custody receipt"))
    elif args.command == "verify-availability":
        payload = verify_current_availability(
            receipt=_load_json(args.receipt, "custody receipt"),
            receipt_artifact_id=args.receipt_artifact_id,
            receipt_provider_digest=args.receipt_provider_digest,
            observation=_load_json(args.observation, "provider observation"),
            now=_timestamp(args.now, "current observation time"),
        )
        if payload["status"] != "current":
            print(json.dumps(payload, sort_keys=True))
            return 5
    else:
        payload = classify_upload_observation(
            operation_outcome=args.operation_outcome,
            observation=_load_json(args.observation, "provider observation"),
            expected_name=args.name,
            run_id=args.run_id,
        )
        if payload["status"] != "observed_success":
            print(json.dumps(payload, sort_keys=True))
            return 3 if payload["status"] == "effect_indeterminate" else 4
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CoreReleaseEvidenceError as exc:
        raise SystemExit(f"Core release custody failed: {exc}") from exc

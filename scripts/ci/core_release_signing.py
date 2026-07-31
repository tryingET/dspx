#!/usr/bin/env python3
# ---
# summary: "Builds and verifies wheel-only Core statements under the selected signer policy."
# read_when:
#   - "Changing Core signing statements, policy preflight, or release authorization checks."
# ---

from __future__ import annotations

import argparse
from collections.abc import Mapping
from io import BytesIO
import json
from pathlib import Path
import re
import subprocess
from typing import Any, cast
import zipfile

from core_release_bundle_contract import validate_bundle
from core_release_evidence_io import (
    MAX_ARTIFACT_BYTES,
    MAX_JSON_BYTES,
    CoreReleaseEvidenceError,
    stable_regular_bytes,
    write_json,
)
from core_release_policy import (
    AUXILIARY_ROLES,
    ROSTER_VERSION,
    is_sha256,
    load_json,
    loads_json,
    mapping,
    selector_ref,
    sha256,
    validate_policy,
    validate_roster,
    validate_selector,
)
from core_release_policy_live import resolve_live_current_policy
from core_release_signing_identity import verify_sigstore_bundle

STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
PREDICATE_TYPE = "https://dspx.ai/attestations/core-release-evidence/v1"
PREDICATE_SCHEMA = "dspx-core-signed-release-evidence-predicate-v1"
RECEIPT_PREDICATE_TYPE = "https://dspx.ai/attestations/core-ci-custody-receipt/v1"
_ROLE_MAP = {
    "installed-proof": "installed_wheel_proof",
    "release-evidence": "release_evidence_v3",
    "core-sbom": "exact_wheel_sbom",
    "core-installed-environment-sbom": "resolved_environment_sbom",
    "core-sdist": "unsigned_unsupported_distribution_evidence",
}


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _git_bytes(repo_root: Path, commit: str, path: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "show", f"{commit}:{path}"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise CoreReleaseEvidenceError(f"cannot read {path} from source commit")
    return result.stdout


def _bundle_payloads(path: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    manifest = validate_bundle(path)
    raw = stable_regular_bytes(
        path, label="Core release bundle", limit=2 * MAX_ARTIFACT_BYTES
    )
    try:
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            payloads = {name: archive.read(name) for name in archive.namelist()}
    except zipfile.BadZipFile as exc:
        raise CoreReleaseEvidenceError("Core release bundle is malformed") from exc
    return manifest, payloads


def _by_role(manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    files = manifest.get("files")
    if not isinstance(files, list):
        raise CoreReleaseEvidenceError("Core release manifest files are invalid")
    result: dict[str, Mapping[str, Any]] = {}
    for index, raw in enumerate(files):
        entry = mapping(raw, f"manifest file {index}")
        role = entry.get("role")
        if not isinstance(role, str) or role in result:
            raise CoreReleaseEvidenceError("Core release manifest roles are ambiguous")
        result[role] = entry
    return result


def _evidence_entry(*, role: str, name: str, raw: bytes) -> dict[str, str]:
    return {"role": role, "name": name, "sha256": sha256(raw)}


def build_statement(
    *,
    bundle_path: Path,
    policy: object,
    repo_root: Path,
    run_id: int,
    run_attempt: int,
    workflow_commit_sha: str,
) -> dict[str, Any]:
    valid_policy = validate_policy(policy)
    manifest, payloads = _bundle_payloads(bundle_path)
    entries = _by_role(manifest)
    source = mapping(manifest.get("source"), "bundle source")
    source_commit = source.get("git_commit")
    if (
        source.get("tree_state") != "clean"
        or source.get("commit_binding_status") != "commit_bound_clean_tree"
        or not isinstance(source_commit, str)
        or re.fullmatch(r"[0-9a-f]{40}", source_commit) is None
    ):
        raise CoreReleaseEvidenceError("signing requires a clean commit-bound bundle")
    if workflow_commit_sha != source_commit:
        raise CoreReleaseEvidenceError("reusable or cross-commit workflow is forbidden")
    workflow_raw = _git_bytes(
        repo_root, source_commit, ".github/workflows/core-release-evidence.yml"
    )
    wheel = entries.get("core-wheel")
    if wheel is None:
        raise CoreReleaseEvidenceError("Core wheel is missing from the bundle")
    wheel_name = wheel.get("filename")
    wheel_digest = wheel.get("sha256")
    if not isinstance(wheel_name, str) or not is_sha256(wheel_digest):
        raise CoreReleaseEvidenceError("Core wheel identity is invalid")
    auxiliary: list[dict[str, str]] = []
    for bundle_role, statement_role in _ROLE_MAP.items():
        entry = entries.get(bundle_role)
        if entry is None:
            raise CoreReleaseEvidenceError(f"bundle role {bundle_role} is missing")
        name = entry.get("filename")
        if not isinstance(name, str) or name not in payloads:
            raise CoreReleaseEvidenceError(f"bundle role {bundle_role} filename drift")
        auxiliary.append(
            _evidence_entry(role=statement_role, name=name, raw=payloads[name])
        )
    release_raw = payloads[cast(str, entries["release-evidence"]["filename"])]
    release = loads_json(release_raw, "release evidence")
    release_source = mapping(release.get("source"), "release evidence source")
    if dict(release_source) != dict(source):
        raise CoreReleaseEvidenceError("bundle source identity drift")
    source_state = {
        "git_commit": source_commit,
        "tree_state": "clean",
        "commit_binding_status": "commit_bound_clean_tree",
    }
    auxiliary.extend(
        [
            _evidence_entry(
                role="source_state",
                name="source-state.json",
                raw=_json_bytes(source_state),
            ),
            _evidence_entry(
                role="bundle_manifest",
                name="bundle-manifest.json",
                raw=payloads["bundle-manifest.json"],
            ),
        ]
    )
    auxiliary.sort(key=lambda item: AUXILIARY_ROLES.index(item["role"]))
    package = mapping(manifest.get("package"), "bundle package")
    statement = {
        "_type": STATEMENT_TYPE,
        "subject": [{"name": wheel_name, "digest": {"sha256": wheel_digest}}],
        "predicateType": PREDICATE_TYPE,
        "predicate": {
            "schema_version": PREDICATE_SCHEMA,
            "package": dict(package),
            "source": {"commit_sha": source_commit, "tree_state": "clean"},
            "workflow": {
                "path": ".github/workflows/core-release-evidence.yml",
                "ref": "refs/heads/main",
                "workflow_commit_sha": workflow_commit_sha,
                "workflow_file_sha256": sha256(workflow_raw),
                "event": "workflow_dispatch",
                "environment": "core-release-evidence",
                "run_id": run_id,
                "run_attempt": run_attempt,
            },
            "policy": {
                "version": valid_policy["policy_version"],
                "roster_version": ROSTER_VERSION,
            },
            "auxiliary_evidence": auxiliary,
            "claims": {
                "workload_signature_required": True,
                "evidence_authenticity": False,
                "release_authority": False,
                "package_publication": False,
                "sdist_supported": False,
            },
        },
    }
    validate_statement(statement, policy=valid_policy)
    return statement


def validate_statement(value: object, *, policy: object) -> dict[str, Any]:
    valid_policy = validate_policy(policy)
    statement = mapping(value, "signed statement")
    if set(statement) != {"_type", "subject", "predicateType", "predicate"}:
        raise CoreReleaseEvidenceError("signed statement fields drift")
    if (
        statement.get("_type") != STATEMENT_TYPE
        or statement.get("predicateType") != PREDICATE_TYPE
    ):
        raise CoreReleaseEvidenceError("signed statement type drift")
    subjects = statement.get("subject")
    if not isinstance(subjects, list) or len(subjects) != 1:
        raise CoreReleaseEvidenceError("signed statement must have exactly one subject")
    subject = mapping(subjects[0], "signed statement subject")
    if (
        set(subject) != {"name", "digest"}
        or not isinstance(subject.get("name"), str)
        or not cast(str, subject["name"]).startswith("dspx_core-")
        or not cast(str, subject["name"]).endswith(".whl")
    ):
        raise CoreReleaseEvidenceError("signed subject must be the Core wheel")
    digest = mapping(subject.get("digest"), "signed subject digest")
    if set(digest) != {"sha256"} or not is_sha256(digest.get("sha256")):
        raise CoreReleaseEvidenceError("signed subject digest drift")
    predicate = mapping(statement.get("predicate"), "signed statement predicate")
    package = mapping(predicate.get("package"), "statement package")
    if package.get("name") != "dspx-core" or not isinstance(
        package.get("version"), str
    ):
        raise CoreReleaseEvidenceError("signed statement package drift")
    expected_fields = {
        "schema_version",
        "package",
        "source",
        "workflow",
        "policy",
        "auxiliary_evidence",
        "claims",
    }
    if (
        set(predicate) != expected_fields
        or predicate.get("schema_version") != PREDICATE_SCHEMA
    ):
        raise CoreReleaseEvidenceError("signed statement predicate drift")
    source = mapping(predicate.get("source"), "statement source")
    if (
        source.get("tree_state") != "clean"
        or not isinstance(source.get("commit_sha"), str)
        or re.fullmatch(r"[0-9a-f]{40}", cast(str, source["commit_sha"])) is None
    ):
        raise CoreReleaseEvidenceError("signed statement source drift")
    workflow = mapping(predicate.get("workflow"), "statement workflow")
    if (
        workflow.get("path") != ".github/workflows/core-release-evidence.yml"
        or workflow.get("ref") != "refs/heads/main"
        or workflow.get("event") != "workflow_dispatch"
        or workflow.get("environment") != "core-release-evidence"
    ):
        raise CoreReleaseEvidenceError("signed statement workflow drift")
    if workflow.get("workflow_commit_sha") != source.get("commit_sha") or not is_sha256(
        workflow.get("workflow_file_sha256")
    ):
        raise CoreReleaseEvidenceError("signed statement workflow binding drift")
    for key in ("run_id", "run_attempt"):
        if (
            not isinstance(workflow.get(key), int)
            or isinstance(workflow.get(key), bool)
            or workflow[key] <= 0
        ):
            raise CoreReleaseEvidenceError(f"signed statement {key} drift")
    selected = mapping(predicate.get("policy"), "statement policy")
    if selected != {
        "version": valid_policy["policy_version"],
        "roster_version": ROSTER_VERSION,
    }:
        raise CoreReleaseEvidenceError("signed statement policy drift")
    auxiliary = predicate.get("auxiliary_evidence")
    if not isinstance(auxiliary, list) or [
        mapping(item, "auxiliary evidence").get("role") for item in auxiliary
    ] != list(AUXILIARY_ROLES):
        raise CoreReleaseEvidenceError("signed statement auxiliary roles drift")
    for item in auxiliary:
        evidence = mapping(item, "auxiliary evidence")
        if set(evidence) != {"role", "name", "sha256"} or not is_sha256(
            evidence.get("sha256")
        ):
            raise CoreReleaseEvidenceError("signed statement auxiliary evidence drift")
    if any(
        item["role"] == "unsigned_unsupported_distribution_evidence"
        and not cast(str, item["name"]).endswith(".tar.gz")
        for item in auxiliary
    ):
        raise CoreReleaseEvidenceError("sdist auxiliary role drift")
    if predicate.get("claims") != {
        "workload_signature_required": True,
        "evidence_authenticity": False,
        "release_authority": False,
        "package_publication": False,
        "sdist_supported": False,
    }:
        raise CoreReleaseEvidenceError("signed statement authority claims drift")
    return dict(statement)


def validate_statement_against_bundle(
    *, statement: object, policy: object, bundle_path: Path, repo_root: Path
) -> dict[str, Any]:
    valid = validate_statement(statement, policy=policy)
    predicate = mapping(valid["predicate"], "signed statement predicate")
    workflow = mapping(predicate["workflow"], "signed statement workflow")
    rebuilt = build_statement(
        bundle_path=bundle_path,
        policy=policy,
        repo_root=repo_root,
        run_id=cast(int, workflow["run_id"]),
        run_attempt=cast(int, workflow["run_attempt"]),
        workflow_commit_sha=cast(str, workflow["workflow_commit_sha"]),
    )
    if rebuilt != valid:
        raise CoreReleaseEvidenceError("signed statement evidence binding drift")
    return valid


def extract_wheel(*, bundle_path: Path, out_path: Path) -> dict[str, str]:
    manifest, payloads = _bundle_payloads(bundle_path)
    wheel = _by_role(manifest).get("core-wheel")
    if wheel is None or not isinstance(wheel.get("filename"), str):
        raise CoreReleaseEvidenceError("Core wheel is absent")
    name = cast(str, wheel["filename"])
    if out_path.exists() or out_path.is_symlink():
        raise CoreReleaseEvidenceError("wheel output already exists")
    out_path.write_bytes(payloads[name])
    out_path.chmod(0o600)
    return {"filename": name, "sha256": sha256(payloads[name])}


def build_receipt_statement(receipt_path: Path) -> dict[str, Any]:
    raw = stable_regular_bytes(
        receipt_path, label="custody receipt", limit=MAX_JSON_BYTES
    )
    receipt = load_json(receipt_path, "custody receipt")
    return {
        "_type": STATEMENT_TYPE,
        "subject": [
            {"name": "custody-receipt.json", "digest": {"sha256": sha256(raw)}}
        ],
        "predicateType": RECEIPT_PREDICATE_TYPE,
        "predicate": dict(receipt),
    }


def enforce_denylist(
    *, statement: object, statement_raw: bytes, policy: object
) -> None:
    valid = validate_statement(statement, policy=policy)
    predicate = mapping(valid["predicate"], "statement predicate")
    workflow = mapping(predicate["workflow"], "statement workflow")
    source = mapping(predicate["source"], "statement source")
    auxiliary = {entry["role"]: entry for entry in predicate["auxiliary_evidence"]}
    deny = mapping(mapping(policy, "policy")["deny"], "policy denylist")
    checks = (
        (workflow["run_id"], deny["workflow_run_ids"]),
        (source["commit_sha"], deny["source_commit_shas"]),
        (sha256(statement_raw), deny["signed_statement_sha256"]),
        (auxiliary["bundle_manifest"]["sha256"], deny["bundle_manifest_sha256"]),
    )
    if any(value in denied for value, denied in checks):
        raise CoreReleaseEvidenceError("signed evidence is denied by current policy")


def _positive(value: str, label: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise CoreReleaseEvidenceError(f"{label} must be positive")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    preflight = commands.add_parser("preflight-policy")
    preflight.add_argument("--policy", type=Path, required=True)
    preflight.add_argument("--selector", type=Path, required=True)
    preflight.add_argument("--roster", type=Path, required=True)
    preflight.add_argument("--require-bindings", action="store_true")
    build = commands.add_parser("build-statement")
    build.add_argument("--bundle", type=Path, required=True)
    build.add_argument("--policy", type=Path, required=True)
    build.add_argument("--repo-root", type=Path, default=Path("."))
    build.add_argument("--run-id", required=True)
    build.add_argument("--run-attempt", required=True)
    build.add_argument("--workflow-commit", required=True)
    build.add_argument("--out", type=Path, required=True)
    extract = commands.add_parser("extract-wheel")
    extract.add_argument("--bundle", type=Path, required=True)
    extract.add_argument("--out", type=Path, required=True)
    verify = commands.add_parser("verify-bundle")
    verify.add_argument("--statement", type=Path, required=True)
    verify.add_argument("--sigstore-bundle", type=Path, required=True)
    verify.add_argument("--subject", type=Path, required=True)
    verify.add_argument("--evidence-bundle", type=Path, required=True)
    verify.add_argument("--policy", type=Path, required=True)
    verify.add_argument("--selector", type=Path, required=True)
    verify.add_argument("--trusted-root", type=Path, required=True)
    verify.add_argument("--creation-policy-only", action="store_true")
    receipt = commands.add_parser("build-receipt-statement")
    receipt.add_argument("--receipt", type=Path, required=True)
    receipt.add_argument("--out", type=Path, required=True)
    reference = commands.add_parser("selector-ref")
    reference.add_argument("--selector", type=Path, required=True)
    current = commands.add_parser("resolve-current")
    current.add_argument("--checkpoint", type=Path, required=True)
    current.add_argument("--repo-root", type=Path, default=Path("."))
    args = parser.parse_args()
    if args.command == "preflight-policy":
        payload = {
            "policy": validate_policy(load_json(args.policy, "trust policy")),
            "selector": validate_selector(
                load_json(args.selector, "policy selector"), repo_root=Path(".")
            ),
            "roster": validate_roster(
                load_json(args.roster, "release-owner roster"),
                require_bindings=args.require_bindings,
            ),
        }
    elif args.command == "build-statement":
        payload = build_statement(
            bundle_path=args.bundle,
            policy=load_json(args.policy, "trust policy"),
            repo_root=args.repo_root,
            run_id=_positive(args.run_id, "run ID"),
            run_attempt=_positive(args.run_attempt, "run attempt"),
            workflow_commit_sha=args.workflow_commit,
        )
        write_json(args.out, payload)
    elif args.command == "extract-wheel":
        payload = extract_wheel(bundle_path=args.bundle, out_path=args.out)
    elif args.command == "verify-bundle":
        policy = load_json(args.policy, "trust policy")
        validate_selector(
            load_json(args.selector, "policy selector"), repo_root=Path(".")
        )
        statement_raw = stable_regular_bytes(
            args.statement, label="signed statement", limit=MAX_JSON_BYTES
        )
        statement = load_json(args.statement, "signed statement")
        validate_statement_against_bundle(
            statement=statement,
            policy=policy,
            bundle_path=args.evidence_bundle,
            repo_root=Path("."),
        )
        enforce_denylist(
            statement=statement, statement_raw=statement_raw, policy=policy
        )
        payload = verify_sigstore_bundle(
            statement_path=args.statement,
            bundle_path=args.sigstore_bundle,
            subject_path=args.subject,
            policy_path=args.policy,
            trusted_root_path=args.trusted_root,
        )
        payload["current_policy"] = (
            "creation_policy_only"
            if args.creation_policy_only
            else "current_policy_resolution_required"
        )
    elif args.command == "build-receipt-statement":
        payload = build_receipt_statement(args.receipt)
        write_json(args.out, payload)
    elif args.command == "selector-ref":
        print(selector_ref(repo_root=Path("."), selector_path=args.selector))
        return 0
    else:
        payload = resolve_live_current_policy(
            repo_root=args.repo_root, checkpoint_path=args.checkpoint
        )
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CoreReleaseEvidenceError, ValueError) as exc:
        raise SystemExit(f"Core release signing failed: {exc}") from exc

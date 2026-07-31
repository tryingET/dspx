#!/usr/bin/env python3
# ---
# summary: "Verifies Sigstore bundle cryptography and exact Fulcio workload identity."
# read_when:
#   - "Changing Core keyless signer identity, trust roots, or certificate matching."
# ---

from __future__ import annotations

import argparse
import base64
from collections.abc import Mapping
import json
from pathlib import Path
import subprocess
from typing import Any, cast

from cryptography import x509
from cryptography.x509.oid import ObjectIdentifier

from core_release_evidence_io import (
    MAX_JSON_BYTES,
    CoreReleaseEvidenceError,
    stable_regular_bytes,
)
from core_release_policy import (
    load_json,
    loads_json,
    mapping,
    sha256,
    validate_policy,
)


def _certificate_bytes(bundle: Mapping[str, Any]) -> bytes:
    material = mapping(
        bundle.get("verificationMaterial"), "Sigstore verification material"
    )
    certificate = material.get("certificate")
    if isinstance(certificate, Mapping):
        raw = certificate.get("rawBytes")
    else:
        chain = mapping(
            material.get("x509CertificateChain"), "Sigstore certificate chain"
        )
        certificates = chain.get("certificates")
        if not isinstance(certificates, list) or not certificates:
            raise CoreReleaseEvidenceError("Sigstore bundle has no signing certificate")
        raw = mapping(certificates[0], "Sigstore signing certificate").get("rawBytes")
    if not isinstance(raw, str):
        raise CoreReleaseEvidenceError("Sigstore signing certificate bytes are missing")
    try:
        return base64.b64decode(raw, validate=True)
    except ValueError as exc:
        raise CoreReleaseEvidenceError(
            "Sigstore signing certificate is invalid base64"
        ) from exc


def _der_text(raw: bytes, oid: str) -> str:
    if len(raw) < 2 or raw[0] not in {0x0C, 0x16}:
        raise CoreReleaseEvidenceError(f"certificate extension {oid} is not text")
    first = raw[1]
    if first < 0x80:
        length = first
        offset = 2
    else:
        width = first & 0x7F
        if width == 0 or width > 4 or len(raw) < 2 + width:
            raise CoreReleaseEvidenceError(
                f"certificate extension {oid} has invalid DER"
            )
        length = int.from_bytes(raw[2 : 2 + width], "big")
        offset = 2 + width
    if offset + length != len(raw):
        raise CoreReleaseEvidenceError(f"certificate extension {oid} has trailing DER")
    try:
        return raw[offset:].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CoreReleaseEvidenceError(
            f"certificate extension {oid} is not UTF-8"
        ) from exc


def certificate_facts(bundle: object) -> dict[str, str]:
    value = mapping(bundle, "Sigstore bundle")
    if value.get("mediaType") != "application/vnd.dev.sigstore.bundle.v0.3+json":
        raise CoreReleaseEvidenceError("Sigstore bundle media type drift")
    try:
        certificate = x509.load_der_x509_certificate(_certificate_bytes(value))
    except ValueError as exc:
        raise CoreReleaseEvidenceError(
            "Sigstore signing certificate is malformed"
        ) from exc
    try:
        san = certificate.extensions.get_extension_for_oid(
            ObjectIdentifier("2.5.29.17")
        ).value
    except x509.ExtensionNotFound as exc:
        raise CoreReleaseEvidenceError(
            "Sigstore certificate URI SAN is missing"
        ) from exc
    uris = san.get_values_for_type(x509.UniformResourceIdentifier)
    if len(uris) != 1:
        raise CoreReleaseEvidenceError("Sigstore certificate URI SAN is ambiguous")
    facts = {"2.5.29.17": uris[0]}
    for index in range(8, 25):
        oid = f"1.3.6.1.4.1.57264.1.{index}"
        try:
            extension = certificate.extensions.get_extension_for_oid(
                ObjectIdentifier(oid)
            ).value
        except x509.ExtensionNotFound as exc:
            raise CoreReleaseEvidenceError(
                f"certificate extension {oid} is missing"
            ) from exc
        if not isinstance(extension, x509.UnrecognizedExtension):
            raise CoreReleaseEvidenceError(f"certificate extension {oid} type drift")
        facts[oid] = _der_text(extension.value, oid)
    return facts


def _statement_context(statement: Mapping[str, Any]) -> dict[str, str]:
    predicate = mapping(statement.get("predicate"), "signed statement predicate")
    workflow = mapping(predicate.get("workflow"), "signed statement workflow")
    source = predicate.get("source")
    if isinstance(source, Mapping):
        source_commit = source.get("commit_sha")
        workflow_commit = workflow.get("workflow_commit_sha")
    else:
        source_commit = predicate.get("source_commit_sha")
        workflow_commit = source_commit
    run_id = workflow.get("run_id")
    run_attempt = workflow.get("run_attempt")
    if (
        not isinstance(source_commit, str)
        or not isinstance(workflow_commit, str)
        or not isinstance(run_id, int)
        or not isinstance(run_attempt, int)
    ):
        raise CoreReleaseEvidenceError("signed statement run identity drift")
    return {
        "$source_commit_sha": source_commit,
        "$workflow_commit_sha": workflow_commit,
        "$run_invocation_uri": (
            f"https://github.com/tryingET/dspx/actions/runs/{run_id}/attempts/{run_attempt}"
        ),
    }


def validate_certificate_identity(
    *, facts: Mapping[str, str], policy: object, statement: object
) -> dict[str, Any]:
    valid_policy = validate_policy(policy)
    signed_statement = mapping(statement, "signed statement")
    dynamic = _statement_context(signed_statement)
    expected = mapping(
        mapping(valid_policy["workload"], "policy workload")["certificate_extensions"],
        "policy certificate extensions",
    )
    if set(facts) != set(expected):
        raise CoreReleaseEvidenceError("certificate identity field coverage drift")
    for oid, configured in expected.items():
        required = dynamic.get(cast(str, configured), configured)
        if facts.get(oid) != required:
            raise CoreReleaseEvidenceError(f"certificate identity mismatch for {oid}")
    if facts["1.3.6.1.4.1.57264.1.9"] != facts["1.3.6.1.4.1.57264.1.18"]:
        raise CoreReleaseEvidenceError("Build Signer and Build Config URI differ")
    if facts["1.3.6.1.4.1.57264.1.10"] != facts["1.3.6.1.4.1.57264.1.19"]:
        raise CoreReleaseEvidenceError("Build Signer and Build Config digest differ")
    return {"status": "exact_identity_verified", "facts": dict(facts)}


def verify_sigstore_bundle(
    *,
    statement_path: Path,
    bundle_path: Path,
    subject_path: Path,
    policy_path: Path,
    trusted_root_path: Path,
    cosign_command: str = "cosign",
) -> dict[str, Any]:
    policy = validate_policy(load_json(policy_path, "trust policy"))
    statement_raw = stable_regular_bytes(
        statement_path, label="signed statement", limit=MAX_JSON_BYTES
    )
    statement = loads_json(statement_raw, "signed statement")
    bundle = load_json(bundle_path, "Sigstore bundle")
    root_raw = stable_regular_bytes(
        trusted_root_path, label="Sigstore trusted root", limit=MAX_JSON_BYTES
    )
    expected_root = mapping(policy["sigstore"], "policy Sigstore")[
        "trusted_root_sha256"
    ]
    if sha256(root_raw) != expected_root:
        raise CoreReleaseEvidenceError("Sigstore trusted root digest drift")
    envelope = mapping(bundle.get("dsseEnvelope"), "Sigstore DSSE envelope")
    payload = envelope.get("payload")
    if not isinstance(payload, str):
        raise CoreReleaseEvidenceError("Sigstore DSSE payload is missing")
    try:
        authenticated_statement_raw = base64.b64decode(payload, validate=True)
        bundled_statement = loads_json(
            authenticated_statement_raw, "Sigstore bundled statement"
        )
    except ValueError as exc:
        raise CoreReleaseEvidenceError("Sigstore DSSE payload is malformed") from exc
    if authenticated_statement_raw != statement_raw or dict(bundled_statement) != dict(
        statement
    ):
        raise CoreReleaseEvidenceError("Sigstore bundled statement byte drift")
    workload = mapping(policy["workload"], "policy workload")
    predicate_type = statement.get("predicateType")
    allowed_types = {
        mapping(policy["statement"], "policy statement")["predicate_type"],
        "https://dspx.ai/attestations/core-ci-custody-receipt/v1",
    }
    if predicate_type not in allowed_types:
        raise CoreReleaseEvidenceError("signed statement predicate type is unsupported")
    if predicate_type == "https://dspx.ai/attestations/core-ci-custody-receipt/v1":
        from core_release_custody import validate_receipt

        validate_receipt(statement.get("predicate"))
    command = [
        cosign_command,
        "verify-blob-attestation",
        "--bundle",
        str(bundle_path),
        "--new-bundle-format",
        "--trusted-root",
        str(trusted_root_path),
        "--offline",
        "--certificate-identity",
        cast(
            str, mapping(workload["certificate_extensions"], "extensions")["2.5.29.17"]
        ),
        "--certificate-oidc-issuer",
        cast(str, workload["issuer"]),
        "--type",
        cast(str, predicate_type),
        str(subject_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise CoreReleaseEvidenceError(
            f"cosign cryptographic verification failed: {result.stderr.strip()}"
        )
    identity = validate_certificate_identity(
        facts=certificate_facts(bundle), policy=policy, statement=statement
    )
    return {
        "schema_version": "dspx-core-sigstore-verification-v1",
        "status": "verified",
        "cryptographic_verifier": "cosign-v2.6.4-offline-pinned-root",
        "identity": identity,
        "release_authority": False,
        "package_publication": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--statement", type=Path, required=True)
    parser.add_argument("--sigstore-bundle", type=Path, required=True)
    parser.add_argument("--subject", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--trusted-root", type=Path, required=True)
    args = parser.parse_args()
    payload = verify_sigstore_bundle(
        statement_path=args.statement,
        bundle_path=args.sigstore_bundle,
        subject_path=args.subject,
        policy_path=args.policy,
        trusted_root_path=args.trusted_root,
    )
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CoreReleaseEvidenceError as exc:
        raise SystemExit(f"Core release identity verification failed: {exc}") from exc

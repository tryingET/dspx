# ---
# summary: "Validates the complete installed Core proof before release-evidence consumption."
# read_when:
#   - "Changing installed-proof v2 fields, invariants, or release-envelope handoff validation."
# ---

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from core_release_evidence_io import CoreReleaseEvidenceError, is_sha256


_PROOF_FIELDS = {
    "schema_version",
    "status",
    "provider",
    "oracle_embedding_backend",
    "oracle_semantic_claim",
    "behavior_status",
    "receipt_check_status",
    "replay_claim_matrix_schema",
    "candidate_identity",
    "evidence_hashes",
    "oracle_record_count",
    "workflow_declared_effects",
    "non_authority",
    "artifact_under_test",
    "install",
    "independent_effect_observations",
}
_ARTIFACT_FIELDS = {
    "filename",
    "sha256",
    "distribution_name",
    "distribution_version",
    "direct_url_bound",
    "installed_payload_record_verified",
    "installed_payload_file_count",
}
_IDENTITY_FIELDS = {
    "assembly_id",
    "candidate_id",
    "episode_id",
    "receipt_bundle_id",
    "request_id",
}
_EVIDENCE_HASH_FIELDS = {
    "manifest_sha256",
    "intent_sha256",
    "behavior_episode_sha256",
    "behavior_results_sha256",
    "oracle_evidence_sha256",
    "oracle_report_sha256",
}
_WORKFLOW_EFFECTS = {
    "shared_oracle_mutated": False,
    "ak_called": False,
    "governance_mutated": False,
    "external_authority_mutated": False,
    "promotion_applied": False,
    "winner_selected": False,
}
_NON_AUTHORITY = {
    "release_readiness": False,
    "live_provider_proof": False,
    "semantic_quality_approval": False,
    "network_isolation_proven": False,
    "absolute_path_external_effects_excluded": False,
    "promotion_authority": False,
    "activation_authority": False,
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


def _typed_equal(value: object, expected: object) -> bool:
    if isinstance(expected, Mapping):
        if not isinstance(value, Mapping) or set(value) != set(expected):
            return False
        actual_mapping = cast(Mapping[Any, Any], value)
        expected_mapping = cast(Mapping[Any, Any], expected)
        return all(
            _typed_equal(actual_mapping.get(key), wanted)
            for key, wanted in expected_mapping.items()
        )
    if isinstance(expected, list):
        return (
            isinstance(value, list)
            and len(value) == len(expected)
            and all(
                _typed_equal(actual, wanted) for actual, wanted in zip(value, expected)
            )
        )
    return type(value) is type(expected) and value == expected


def _expect(value: object, expected: object, label: str) -> None:
    if not _typed_equal(value, expected):
        raise CoreReleaseEvidenceError(
            f"{label} drift: expected {expected!r}, observed {value!r}"
        )


def validate_installed_proof(
    value: object,
    *,
    expected_name: str,
    expected_version: str,
    expected_wheel_filename: str,
    expected_wheel_sha256: str,
) -> Mapping[str, Any]:
    proof = _mapping(value, "installed Core proof")
    _exact(proof, _PROOF_FIELDS, "installed Core proof")
    for field, expected in (
        ("schema_version", "dspx-installed-core-golden-path-proof-v2"),
        ("status", "passed"),
        ("provider", "stub"),
        ("oracle_embedding_backend", "mock"),
        ("oracle_semantic_claim", "plumbing_only_not_production_semantics"),
        ("behavior_status", "passed"),
        ("receipt_check_status", "ok"),
        ("replay_claim_matrix_schema", "dspx-replay-claim-matrix-v1"),
        ("oracle_record_count", 1),
    ):
        _expect(proof.get(field), expected, f"installed proof {field}")

    identity = _mapping(proof.get("candidate_identity"), "installed proof identity")
    _exact(identity, _IDENTITY_FIELDS, "installed proof identity")
    if any(
        not isinstance(identity[field], str) or not identity[field]
        for field in identity
    ):
        raise CoreReleaseEvidenceError(
            "installed proof identity values must be non-empty"
        )

    hashes = _mapping(proof.get("evidence_hashes"), "installed proof evidence hashes")
    _exact(hashes, _EVIDENCE_HASH_FIELDS, "installed proof evidence hashes")
    if any(not is_sha256(hashes[field]) for field in hashes):
        raise CoreReleaseEvidenceError("installed proof evidence hash is invalid")

    effects = _mapping(
        proof.get("workflow_declared_effects"), "installed proof effects"
    )
    _expect(dict(effects), _WORKFLOW_EFFECTS, "installed proof effects")
    non_authority = _mapping(
        proof.get("non_authority"), "installed proof non-authority"
    )
    _expect(dict(non_authority), _NON_AUTHORITY, "installed proof non-authority")

    artifact = _mapping(proof.get("artifact_under_test"), "installed proof artifact")
    _exact(artifact, _ARTIFACT_FIELDS, "installed proof artifact")
    for field, expected in (
        ("filename", expected_wheel_filename),
        ("sha256", expected_wheel_sha256),
        ("distribution_name", expected_name),
        ("distribution_version", expected_version),
        ("direct_url_bound", True),
        ("installed_payload_record_verified", True),
    ):
        _expect(artifact.get(field), expected, f"installed proof artifact {field}")
    file_count = artifact.get("installed_payload_file_count")
    if (
        not isinstance(file_count, int)
        or isinstance(file_count, bool)
        or file_count <= 0
    ):
        raise CoreReleaseEvidenceError("installed proof payload file count is invalid")

    install = _mapping(proof.get("install"), "installed proof install")
    _exact(install, {"module_path", "distribution_version"}, "installed proof install")
    if not isinstance(install.get("module_path"), str) or not install["module_path"]:
        raise CoreReleaseEvidenceError("installed proof module path is invalid")
    _expect(
        install.get("distribution_version"), expected_version, "installed proof version"
    )

    observations = _mapping(
        proof.get("independent_effect_observations"), "installed proof observations"
    )
    _expect(
        dict(observations),
        {"path_resolved_ak_canary_invoked": False},
        "installed proof observations",
    )
    return artifact

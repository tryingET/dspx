from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping, NoReturn

PROGRAM_EVIDENCE_ADJUDICATION_SCHEMA = "program-evidence-adjudication-v1"
_ALLOWED_JUDGMENTS = {
    "supports_domain_review",
    "supports_domain_review_with_caveat",
    "needs_more_evidence",
    "withhold",
}
_BLOCKING_JUDGMENTS = {"needs_more_evidence", "withhold"}
_EFFECT_FALSE_KEYS = (
    "candidate_files_mutated",
    "canonical_target_mutated",
    "ak_mutated",
    "governance_mutated",
    "oracle_index_mutated",
    "shared_oracle_mutated",
    "provider_called",
)
_NON_AUTHORITY_FALSE_KEYS = (
    "activation_authority",
    "promotion_authority",
    "oracle_authority",
    "governance_authority",
    "external_authority",
    "external_mutation",
)


def _safe_mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _safe_list(value: object) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _first_text(*values: object) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _raise(error_type: type[Exception], message: str) -> NoReturn:
    raise error_type(message)


def _identity_mismatches(
    expected_identity: Mapping[str, Any], artifact_identity: Mapping[str, Any]
) -> list[str]:
    mismatched: list[str] = []
    for key, expected_value in expected_identity.items():
        artifact_value = artifact_identity.get(key)
        if expected_value in {None, ""}:
            continue
        if artifact_value in {None, ""} or str(artifact_value) != str(expected_value):
            mismatched.append(str(key))
    return mismatched


def _validate_hash_bound_ref(
    ref: object,
    *,
    label: str,
    expected_schema: str | set[str],
    expected_hashes: set[str],
    error_type: type[Exception],
    require_present: bool = True,
) -> None:
    ref_map = _safe_mapping(ref)
    if not ref_map:
        if require_present:
            _raise(error_type, f"{label} ref is required")
        return
    path_text = _first_text(ref_map.get("path"))
    expected_sha256 = _first_text(ref_map.get("sha256"))
    schema = _first_text(ref_map.get("schema_version"))
    allowed_schemas = (
        expected_schema if isinstance(expected_schema, set) else {expected_schema}
    )
    if not path_text:
        _raise(error_type, f"{label} ref path is required")
    if not expected_sha256:
        _raise(error_type, f"{label} ref sha256 is required")
    if schema not in allowed_schemas:
        _raise(
            error_type,
            f"{label} ref schema_version must be one of "
            + ", ".join(sorted(allowed_schemas)),
        )
    assert path_text is not None
    assert expected_sha256 is not None
    if expected_sha256 not in expected_hashes:
        _raise(error_type, f"{label} ref sha256 does not match current evidence")
    path = Path(path_text).expanduser().resolve()
    try:
        actual_sha256 = _sha256_file(path)
    except FileNotFoundError:
        _raise(error_type, f"{label} ref path does not exist: {path}")
    if actual_sha256 != expected_sha256:
        _raise(error_type, f"{label} ref sha256 is stale: {path}")


def validate_program_evidence_adjudication_contract(
    payload: Mapping[str, Any] | None,
    *,
    expected_identity: Mapping[str, Any],
    current_manifest_path: Path,
    current_manifest_hash: str,
    behavior_results_hash: str | None = None,
    behavior_episode_hash: str | None = None,
    oracle_report_hash: str | None = None,
    activation_packet_hash: str | None = None,
    generation_fitness_results_hash: str | None = None,
    label: str = "program evidence adjudication",
    error_type: type[Exception] = ValueError,
) -> None:
    """Validate a consumed program-evidence-adjudication-v1 sidecar.

    The sidecar is local adjudication evidence only. Consumers must re-bind it to
    the current manifest and evidence files before it can affect candidate truth
    state or target-fidelity summaries.
    """

    if payload is None:
        return
    if payload.get("schema_version") != PROGRAM_EVIDENCE_ADJUDICATION_SCHEMA:
        _raise(
            error_type,
            f"{label} schema_version must be {PROGRAM_EVIDENCE_ADJUDICATION_SCHEMA}",
        )
    if payload.get("status") != "evidence_adjudicated":
        _raise(error_type, f"{label} status must be evidence_adjudicated")

    identity = _safe_mapping(payload.get("identity"))
    if not identity:
        _raise(error_type, f"{label} identity is required")
    mismatches = _identity_mismatches(expected_identity, identity)
    if mismatches:
        _raise(
            error_type,
            f"{label} identity does not match current manifest: "
            + ", ".join(mismatches),
        )

    manifest_ref = _safe_mapping(payload.get("manifest"))
    manifest_path = _first_text(manifest_ref.get("path"))
    manifest_sha256 = _first_text(manifest_ref.get("sha256"))
    if not manifest_path or not manifest_sha256:
        _raise(error_type, f"{label} manifest path and sha256 are required")
    if (
        Path(manifest_path).expanduser().resolve()
        != current_manifest_path.expanduser().resolve()
    ):
        _raise(error_type, f"{label} manifest path does not match current manifest")
    if manifest_sha256 != current_manifest_hash:
        _raise(error_type, f"{label} manifest sha256 does not match current manifest")
    if _sha256_file(current_manifest_path.expanduser().resolve()) != manifest_sha256:
        _raise(error_type, f"{label} manifest sha256 is stale")

    non_authority = _safe_mapping(payload.get("non_authority"))
    invalid_non_authority = [
        key for key in _NON_AUTHORITY_FALSE_KEYS if non_authority.get(key) is not False
    ]
    if invalid_non_authority:
        _raise(
            error_type,
            f"{label} widens non-authority flags: " + ", ".join(invalid_non_authority),
        )
    effect = _safe_mapping(payload.get("effect"))
    invalid_effect = [key for key in _EFFECT_FALSE_KEYS if effect.get(key) is not False]
    if invalid_effect:
        _raise(
            error_type,
            f"{label} widens effect flags: " + ", ".join(invalid_effect),
        )

    evidence_refs = _safe_mapping(payload.get("evidence_refs"))
    behavior_ref = _safe_mapping(evidence_refs.get("behavior"))
    current_behavior_hashes = {
        item for item in (behavior_results_hash, behavior_episode_hash) if item
    }
    if behavior_ref:
        _validate_hash_bound_ref(
            behavior_ref,
            label=f"{label} behavior",
            expected_schema={
                "program-behavior-results-v1",
                "program-behavior-episode-v1",
            },
            expected_hashes=current_behavior_hashes,
            error_type=error_type,
        )
    for ref_key, expected_schema, expected_hash in (
        ("oracle_report", "program-oracle-evidence-report-v1", oracle_report_hash),
        (
            "activation_packet",
            "generated-cognition-program-production-activation-packet-v1",
            activation_packet_hash,
        ),
        (
            "generation_fitness_results",
            "gen-fitness-results-v1",
            generation_fitness_results_hash,
        ),
    ):
        ref = _safe_mapping(evidence_refs.get(ref_key))
        if ref:
            if not expected_hash:
                _raise(
                    error_type,
                    f"{label} {ref_key} ref was supplied but current evidence was not supplied",
                )
            assert expected_hash is not None
            _validate_hash_bound_ref(
                ref,
                label=f"{label} {ref_key}",
                expected_schema=expected_schema,
                expected_hashes={expected_hash},
                error_type=error_type,
            )

    role_judgments = [
        _safe_mapping(item) for item in _safe_list(payload.get("role_judgments"))
    ]
    if not role_judgments:
        _raise(error_type, f"{label} role_judgments must be non-empty")
    judgment_counts: dict[str, int] = {}
    blocking_perspectives: list[str] = []
    target_protocol_seen = False
    target_protocol_support = False
    for index, role in enumerate(role_judgments):
        perspective = _first_text(role.get("perspective"))
        judgment = _first_text(role.get("judgment"))
        if not perspective:
            _raise(
                error_type, f"{label} role_judgments[{index}].perspective is required"
            )
        if judgment is None or judgment not in _ALLOWED_JUDGMENTS:
            _raise(
                error_type, f"{label} role_judgments[{index}].judgment is unsupported"
            )
        if role.get("activation_authority") is not False:
            _raise(
                error_type,
                f"{label} role_judgments[{index}] claims activation authority",
            )
        if role.get("provider_called") is not False:
            _raise(error_type, f"{label} role_judgments[{index}] claims provider call")
        if role.get("model_backed") is not False:
            _raise(
                error_type,
                f"{label} role_judgments[{index}] claims model-backed judgment",
            )
        judgment_counts[judgment] = judgment_counts.get(judgment, 0) + 1
        if judgment in _BLOCKING_JUDGMENTS:
            blocking_perspectives.append(perspective)
        if perspective == "target_protocol_fidelity":
            target_protocol_seen = True
            target_protocol_support = judgment == "supports_domain_review"
            if target_protocol_support:
                if not generation_fitness_results_hash:
                    _raise(
                        error_type,
                        f"{label} target_protocol_fidelity support requires current generation fitness results",
                    )
                if not _safe_mapping(evidence_refs.get("generation_fitness_results")):
                    _raise(
                        error_type,
                        f"{label} target_protocol_fidelity support requires generation_fitness_results ref",
                    )

    aggregate = _safe_mapping(payload.get("aggregate"))
    if aggregate.get("activation_approved") is not False:
        _raise(error_type, f"{label} aggregate must keep activation_approved false")
    aggregate_counts = _safe_mapping(aggregate.get("judgment_counts"))
    normalized_counts = {
        str(key): int(value) for key, value in aggregate_counts.items()
    }
    if normalized_counts != judgment_counts:
        _raise(
            error_type, f"{label} aggregate judgment_counts do not match role judgments"
        )
    if sorted(
        str(item) for item in _safe_list(aggregate.get("blocking_perspectives"))
    ) != sorted(blocking_perspectives):
        _raise(
            error_type,
            f"{label} aggregate blocking_perspectives do not match role judgments",
        )
    expected_ready = bool(behavior_ref) and not blocking_perspectives
    if aggregate.get("ready_for_domain_decision") is not expected_ready:
        _raise(
            error_type, f"{label} aggregate ready_for_domain_decision is inconsistent"
        )
    if (
        target_protocol_seen
        and target_protocol_support
        and generation_fitness_results_hash
    ):
        _validate_hash_bound_ref(
            evidence_refs.get("generation_fitness_results"),
            label=f"{label} generation_fitness_results",
            expected_schema="gen-fitness-results-v1",
            expected_hashes={generation_fitness_results_hash},
            error_type=error_type,
        )

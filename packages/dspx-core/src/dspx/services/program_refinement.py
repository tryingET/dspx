# summary: "Loads hash-bound candidate behavior and Oracle reports, then builds bounded non-authoritative program refinement proposals."
# read_when:
#   - "Changing refinement proposal validation, behavior failure signals, Oracle identity matching, or bounded intent patches."
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from dspx.security import confine_path, identity_matches_exact, identity_mismatch_keys
from dspx.services.artifact_boundary import prepare_sidecar_output_path

PROGRAM_REFINEMENT_PROPOSAL_SCHEMA = "program-refinement-proposal-v1"
PROGRAM_MANIFEST_SCHEMA = "program-candidate-assembly-v1"
PROGRAM_BEHAVIOR_RESULTS_SCHEMA = "program-behavior-results-v1"
PROGRAM_ORACLE_REPORT_SCHEMA = "program-oracle-evidence-report-v1"

_REQUIRED_FALSE_REPORT_NON_AUTHORITY_FLAGS = (
    "oracle_ranking",
    "oracle_pruning",
    "oracle_promotion",
    "governance_authority",
    "external_mutation",
)

_PROPOSAL_NON_AUTHORITY = {
    "proposal_only": True,
    "applies_changes": False,
    "generates_candidate": False,
    "oracle_ranking": False,
    "oracle_pruning": False,
    "oracle_promotion": False,
    "promotion_authority": False,
    "governance_authority": False,
    "external_mutation": False,
}

_REQUIRED_FALSE_PROPOSAL_NON_AUTHORITY_FLAGS = tuple(
    key for key, value in _PROPOSAL_NON_AUTHORITY.items() if value is False
)

_BASE_LIMITATIONS = [
    "Behavior evidence is local and source-indexed; it is not a quality claim.",
    "No jury execution, broad eval_behavior.py orchestration, or authority apply was run.",
    "This proposal is not a promotion or ranking decision.",
]


class ProgramRefinementError(ValueError):
    """Raised when a refinement proposal input is malformed or mismatched."""


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.expanduser().read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProgramRefinementError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ProgramRefinementError(f"{label} must be valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ProgramRefinementError(f"{label} must contain a JSON object: {path}")
    return payload


def _safe_mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _safe_list(value: object) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve_payload_path(raw_path: object, *, base: Path | None = None) -> Path | None:
    text = str(raw_path or "").strip()
    if not text:
        return None
    path = Path(text).expanduser()
    if not path.is_absolute() and base is not None:
        path = base / path
    return path.resolve()


def _json_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def load_program_manifest(path: Path) -> dict[str, Any]:
    """Load and validate the narrow program-gen manifest shape."""

    manifest = _load_json_object(path, label="program manifest")
    if manifest.get("schema_version") != PROGRAM_MANIFEST_SCHEMA:
        raise ProgramRefinementError(
            "program manifest schema_version must be " + PROGRAM_MANIFEST_SCHEMA
        )
    identity = _identity_from_manifest(manifest)
    if not any(identity.values()):
        raise ProgramRefinementError(
            "program manifest does not expose request/candidate/assembly/episode/receipt identity"
        )
    return manifest


def _identity_from_manifest(manifest: Mapping[str, Any]) -> dict[str, str | None]:
    request = _safe_mapping(manifest.get("request"))
    candidate_assembly = _safe_mapping(manifest.get("candidate_assembly"))
    execution_episode = _safe_mapping(manifest.get("execution_episode"))
    receipt_bundle = _safe_mapping(manifest.get("receipt_bundle"))
    return {
        "request_id": _first_text(
            request.get("request_id"),
            candidate_assembly.get("request_id"),
            execution_episode.get("request_id"),
            receipt_bundle.get("request_id"),
        ),
        "candidate_id": _first_text(
            candidate_assembly.get("candidate_id"),
            execution_episode.get("candidate_id"),
            receipt_bundle.get("candidate_id"),
        ),
        "assembly_id": _first_text(
            candidate_assembly.get("assembly_id"),
            execution_episode.get("assembly_id"),
            receipt_bundle.get("assembly_id"),
        ),
        "episode_id": _first_text(
            execution_episode.get("episode_id"),
            receipt_bundle.get("episode_id"),
        ),
        "receipt_bundle_id": _first_text(receipt_bundle.get("receipt_bundle_id")),
    }


def _first_text(*values: object) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _manifest_root(manifest_path: Path) -> Path:
    return manifest_path.expanduser().resolve().parent


def _declared_behavior_path(
    manifest: Mapping[str, Any], manifest_path: Path
) -> Path | None:
    execution_episode = _safe_mapping(manifest.get("execution_episode"))
    behavior_results = _safe_mapping(execution_episode.get("behavior_results"))
    behavior_path = _first_text(behavior_results.get("path"))
    if behavior_path is None:
        candidate_assembly = _safe_mapping(manifest.get("candidate_assembly"))
        for surface in _safe_list(candidate_assembly.get("surfaces")):
            if not isinstance(surface, Mapping):
                continue
            if surface.get("kind") == "behavior_results":
                behavior_path = _first_text(surface.get("path"))
                break
    if behavior_path is None:
        request = _safe_mapping(manifest.get("request"))
        if request.get("behavior_results_hash"):
            behavior_path = "behavior_results.json"
    if behavior_path is None:
        return None
    path = Path(behavior_path)
    if path.is_absolute():
        raise ProgramRefinementError(
            "program behavior results path must be candidate-relative"
        )
    try:
        return confine_path(_manifest_root(manifest_path), path, strict=True)
    except ValueError as exc:
        raise ProgramRefinementError(
            "program behavior results path escapes candidate root"
        ) from exc


def _declared_behavior_hashes(manifest: Mapping[str, Any]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    request = _safe_mapping(manifest.get("request"))
    request_hash = _first_text(request.get("behavior_results_hash"))
    if request_hash:
        hashes["request.behavior_results_hash"] = request_hash

    execution_episode = _safe_mapping(manifest.get("execution_episode"))
    behavior_results = _safe_mapping(execution_episode.get("behavior_results"))
    episode_hash = _first_text(behavior_results.get("content_hash"))
    if episode_hash:
        hashes["execution_episode.behavior_results.content_hash"] = episode_hash

    receipt_bundle = _safe_mapping(manifest.get("receipt_bundle"))
    evidence = _safe_mapping(receipt_bundle.get("evidence"))
    evidence_hash = _first_text(evidence.get("behavior_results_hash"))
    if evidence_hash:
        hashes["receipt_bundle.evidence.behavior_results_hash"] = evidence_hash

    candidate_assembly = _safe_mapping(manifest.get("candidate_assembly"))
    for surface in _safe_list(candidate_assembly.get("surfaces")):
        if not isinstance(surface, Mapping):
            continue
        if surface.get("kind") == "behavior_results":
            surface_hash = _first_text(surface.get("content_hash"))
            if surface_hash:
                hashes["candidate_assembly.surfaces.behavior_results.content_hash"] = (
                    surface_hash
                )
    return hashes


def load_program_behavior_results(
    manifest: Mapping[str, Any], manifest_path: Path
) -> tuple[dict[str, Any] | None, Path | None, str | None]:
    """Load declared behavior_results.json, if present, and verify manifest hashes."""

    behavior_path = _declared_behavior_path(manifest, manifest_path)
    if behavior_path is None or not behavior_path.exists():
        return None, behavior_path, None

    behavior = _load_json_object(behavior_path, label="program behavior results")
    if behavior.get("schema_version") != PROGRAM_BEHAVIOR_RESULTS_SCHEMA:
        raise ProgramRefinementError(
            "program behavior results schema_version must be "
            + PROGRAM_BEHAVIOR_RESULTS_SCHEMA
        )
    actual_hash = _sha256_file(behavior_path)
    declared_hashes = _declared_behavior_hashes(manifest)
    if not declared_hashes:
        raise ProgramRefinementError(
            "program behavior results must have a manifest-declared content hash"
        )
    mismatches = [
        name
        for name, declared_hash in declared_hashes.items()
        if declared_hash != actual_hash
    ]
    if mismatches:
        raise ProgramRefinementError(
            "program behavior results hash does not match manifest declaration(s): "
            + ", ".join(sorted(mismatches))
        )
    return behavior, behavior_path, actual_hash


def load_program_oracle_report(path: Path) -> dict[str, Any]:
    """Load a Wave 6 program Oracle evidence report."""

    report = _load_json_object(path, label="program Oracle evidence report")
    if report.get("schema_version") != PROGRAM_ORACLE_REPORT_SCHEMA:
        raise ProgramRefinementError(
            "program Oracle evidence report schema_version must be "
            + PROGRAM_ORACLE_REPORT_SCHEMA
        )
    return report


def validate_program_oracle_report_non_authority(report: Mapping[str, Any]) -> None:
    """Fail unless the report is explicitly interpretation-only and non-authoritative."""

    non_authority = _safe_mapping(report.get("non_authority"))
    if non_authority.get("oracle_interpretation_only") is not True:
        raise ProgramRefinementError(
            "program Oracle evidence report must be interpretation-only"
        )
    invalid = [
        key
        for key in _REQUIRED_FALSE_REPORT_NON_AUTHORITY_FLAGS
        if non_authority.get(key) is not False
    ]
    if invalid:
        raise ProgramRefinementError(
            "program Oracle evidence report widens non-authority flags: "
            + ", ".join(invalid)
        )


def _raise_refinement_contract_error(error_type: type[Exception], message: str) -> None:
    if issubclass(error_type, ValueError):
        raise error_type(message)
    raise ProgramRefinementError(message)


def _hash_bound_created_from_ref(
    *,
    proposal: Mapping[str, Any],
    path_key: str,
    hash_key: str,
    label: str,
    error_type: type[Exception],
    required: bool,
) -> Path | None:
    created_from = _safe_mapping(proposal.get("created_from"))
    path = _resolve_payload_path(created_from.get(path_key))
    if path is None:
        if required:
            _raise_refinement_contract_error(
                error_type,
                f"program refinement proposal is missing {label} path",
            )
        return None
    expected_hash = _first_text(created_from.get(hash_key))
    if expected_hash is None:
        _raise_refinement_contract_error(
            error_type,
            f"program refinement proposal is missing {label} hash",
        )
    try:
        actual_hash = _sha256_file(path)
    except FileNotFoundError:
        _raise_refinement_contract_error(
            error_type,
            f"program refinement proposal {label} path not found: {path}",
        )
    if actual_hash != expected_hash:
        _raise_refinement_contract_error(
            error_type,
            f"program refinement proposal {label} hash does not match current file",
        )
    return path


def _validate_proposal_bound_ref(
    *,
    actual_path: Path | None,
    valid_refs: Mapping[Path, str] | None,
    label: str,
    error_type: type[Exception],
) -> None:
    if valid_refs is None or actual_path is None:
        return
    normalized_refs = {
        path.expanduser().resolve(): value for path, value in valid_refs.items()
    }
    expected_hash = normalized_refs.get(actual_path)
    if expected_hash is None:
        _raise_refinement_contract_error(
            error_type,
            f"program refinement proposal {label} path does not match expected input",
        )
    actual_hash = _sha256_file(actual_path)
    if actual_hash != expected_hash:
        _raise_refinement_contract_error(
            error_type,
            f"program refinement proposal {label} hash does not match expected input",
        )


def validate_program_refinement_proposal_contract(
    proposal: Mapping[str, Any],
    *,
    expected_identity: Mapping[str, Any] | None = None,
    valid_manifest_refs: Mapping[Path, str] | None = None,
    valid_oracle_report_refs: Mapping[Path, str] | None = None,
    valid_behavior_results_refs: Mapping[Path, str] | None = None,
    allowed_statuses: set[str] | frozenset[str] | None = None,
    require_next_candidate_patch: bool = False,
    label: str = "program refinement proposal",
    error_type: type[Exception] = ProgramRefinementError,
) -> None:
    """Validate a refinement-proposal sidecar at the consumer boundary."""

    if proposal.get("schema_version") != PROGRAM_REFINEMENT_PROPOSAL_SCHEMA:
        _raise_refinement_contract_error(
            error_type,
            f"{label} schema_version must be {PROGRAM_REFINEMENT_PROPOSAL_SCHEMA}",
        )
    status = str(proposal.get("status") or "").strip()
    if allowed_statuses is not None and status not in allowed_statuses:
        _raise_refinement_contract_error(
            error_type,
            f"{label} status must be one of: " + ", ".join(sorted(allowed_statuses)),
        )
    if expected_identity is not None:
        actual_identity = _safe_mapping(proposal.get("identity"))
        if not identity_matches_exact(actual_identity, expected_identity):
            mismatches = identity_mismatch_keys(actual_identity, expected_identity)
            detail = ": " + ", ".join(sorted(mismatches)) if mismatches else ""
            _raise_refinement_contract_error(
                error_type,
                f"{label} identity does not match expected identity" + detail,
            )
    non_authority = _safe_mapping(proposal.get("non_authority"))
    if non_authority.get("proposal_only") is not True:
        _raise_refinement_contract_error(error_type, f"{label} must be proposal-only")
    invalid = [
        key
        for key in _REQUIRED_FALSE_PROPOSAL_NON_AUTHORITY_FLAGS
        if non_authority.get(key) is not False
    ]
    if invalid:
        _raise_refinement_contract_error(
            error_type,
            f"{label} widens non-authority flags: " + ", ".join(invalid),
        )
    manifest_path = _hash_bound_created_from_ref(
        proposal=proposal,
        path_key="manifest_path",
        hash_key="manifest_sha256",
        label="manifest",
        error_type=error_type,
        required=True,
    )
    _validate_proposal_bound_ref(
        actual_path=manifest_path,
        valid_refs=valid_manifest_refs,
        label="manifest",
        error_type=error_type,
    )
    oracle_report_path = _hash_bound_created_from_ref(
        proposal=proposal,
        path_key="oracle_report_path",
        hash_key="oracle_report_sha256",
        label="Oracle report",
        error_type=error_type,
        required=True,
    )
    _validate_proposal_bound_ref(
        actual_path=oracle_report_path,
        valid_refs=valid_oracle_report_refs,
        label="Oracle report",
        error_type=error_type,
    )
    behavior_path = _hash_bound_created_from_ref(
        proposal=proposal,
        path_key="behavior_results_path",
        hash_key="behavior_results_sha256",
        label="behavior results",
        error_type=error_type,
        required=False,
    )
    _validate_proposal_bound_ref(
        actual_path=behavior_path,
        valid_refs=valid_behavior_results_refs,
        label="behavior results",
        error_type=error_type,
    )
    if require_next_candidate_patch:
        patch = _safe_mapping(
            _safe_mapping(proposal.get("bounded_refinement")).get(
                "next_candidate_intent_patch"
            )
        )
        if not _string_list(patch.get("constraints")):
            _raise_refinement_contract_error(
                error_type,
                f"{label} must include bounded next-candidate constraints",
            )


def _matching_oracle_record(
    report: Mapping[str, Any], identity: Mapping[str, str | None]
) -> tuple[dict[str, Any] | None, bool]:
    records = [
        item for item in _safe_list(report.get("records")) if isinstance(item, Mapping)
    ]
    if not records:
        return None, False
    for raw_record in records:
        record_identity = _safe_mapping(raw_record.get("identity"))
        if identity_matches_exact(record_identity, identity):
            return dict(raw_record), True
    return None, False


def _validate_report_identity_match(
    report: Mapping[str, Any], identity: Mapping[str, str | None]
) -> tuple[dict[str, Any] | None, bool]:
    record, matched = _matching_oracle_record(report, identity)
    records = [
        item for item in _safe_list(report.get("records")) if isinstance(item, Mapping)
    ]
    if str(report.get("status") or "") == "ok" and records and not matched:
        raise ProgramRefinementError(
            "program Oracle evidence report does not contain a record matching manifest identity"
        )
    return record, matched


def _behavior_summary(behavior: Mapping[str, Any] | None) -> dict[str, Any]:
    if behavior is None:
        return {}
    return _safe_mapping(behavior.get("summary"))


def _behavior_examples(behavior: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if behavior is None:
        return []
    return [
        dict(item)
        for item in _safe_list(behavior.get("examples"))
        if isinstance(item, Mapping)
    ]


def _output_fields(
    manifest: Mapping[str, Any], behavior: Mapping[str, Any] | None
) -> list[str]:
    fields = _string_list(_safe_mapping(manifest.get("intent")).get("outputs"))
    if fields:
        return fields
    if behavior is not None:
        return _string_list(behavior.get("output_fields"))
    return []


def _failure_signals_from_behavior(
    behavior: Mapping[str, Any] | None, *, output_fields: list[str]
) -> list[str]:
    signals: list[str] = []
    for record in _behavior_examples(behavior):
        status = str(record.get("status") or "unknown")
        expected = _safe_mapping(record.get("expected_outputs"))
        observed = _safe_mapping(record.get("observed_outputs"))
        if status == "error":
            error = _safe_mapping(record.get("error"))
            error_type = str(error.get("type") or "unknown")
            signals.append(f"error:{error_type}")
        if status.startswith("degraded"):
            signals.append(status)
        for field in output_fields:
            if (
                field in expected
                and field in observed
                and str(expected[field]) != str(observed[field])
            ):
                signals.append(f"mismatch:{field}")
            if field not in observed and status != "error":
                signals.append(f"missing_observed:{field}")
        for note in _string_list(record.get("notes")):
            if "output mismatch" in note:
                for field in output_fields:
                    if field in note:
                        signals.append(f"mismatch:{field}")
    unique: list[str] = []
    for signal in signals:
        if signal not in unique:
            unique.append(signal)
    return unique


def _failure_signals(
    *,
    behavior: Mapping[str, Any] | None,
    oracle_record: Mapping[str, Any] | None,
    output_fields: list[str],
) -> list[str]:
    signals = _failure_signals_from_behavior(behavior, output_fields=output_fields)
    if oracle_record is not None:
        for signal in _string_list(oracle_record.get("failure_signals")):
            if signal not in signals:
                signals.append(signal)
    return signals


def _proposal_id(
    identity: Mapping[str, str | None],
    behavior_hash: str | None,
    report: Mapping[str, Any],
) -> str:
    seed = json.dumps(
        {
            "identity": identity,
            "behavior_hash": behavior_hash,
            "report_status": report.get("status"),
            "total_records": report.get("total_records"),
        },
        sort_keys=True,
    ).encode("utf-8")
    return "prog-refine-prop-" + hashlib.sha256(seed).hexdigest()[:12]


def _manifest_behavior_evidence_summary(manifest: Mapping[str, Any]) -> dict[str, Any]:
    execution_episode = _safe_mapping(manifest.get("execution_episode"))
    return _safe_mapping(execution_episode.get("behavior_evidence_summary"))


def _evidence_sources(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    execution_episode = _safe_mapping(manifest.get("execution_episode"))
    return [
        dict(source)
        for source in _safe_list(execution_episode.get("evaluation_sources"))
        if isinstance(source, Mapping)
    ]


def _behavior_source_kinds(manifest: Mapping[str, Any]) -> list[str]:
    kinds = {
        str(source.get("source_kind"))
        for source in _evidence_sources(manifest)
        if str(source.get("source_kind") or "").strip()
    }
    return sorted(kinds)


def _status_for_evidence(
    behavior: Mapping[str, Any] | None, evidence_summary: Mapping[str, Any]
) -> str:
    if behavior is None and int(evidence_summary.get("total") or 0) <= 0:
        return "insufficient_behavior_evidence"
    summary = _behavior_summary(behavior) if behavior is not None else evidence_summary
    behavior_status = str(summary.get("status") or "unknown")
    if behavior_status in {"passed", "no_examples"}:
        return (
            "no_refinement_needed"
            if behavior_status == "passed"
            else "insufficient_behavior_evidence"
        )
    return "proposed"


def _limitations_for_sources(source_kinds: list[str]) -> list[str]:
    limitations = list(_BASE_LIMITATIONS)
    if not source_kinds:
        limitations.insert(0, "No local behavior evidence source was available.")
    elif source_kinds == ["inline_examples"] or source_kinds == ["examples_path"]:
        limitations.insert(0, "Evidence is example-backed via eval_examples.py.")
        limitations.insert(1, "No dataset split behavior evidence was present.")
    elif "dataset_split" in source_kinds:
        limitations.insert(
            0,
            "Dataset split evidence is split-local; no broad graph or eval_behavior.py orchestration was run.",
        )
    return limitations


def _target_surface_for_status(
    status: str, signals: list[str]
) -> tuple[str | None, str | None]:
    if status == "failed" or any(signal.startswith("mismatch:") for signal in signals):
        fields = [
            signal.split(":", 1)[1]
            for signal in signals
            if signal.startswith("mismatch:")
        ]
        field_text = ", ".join(fields) if fields else "declared outputs"
        return "module", f"Observed local behavior output mismatch for {field_text}."
    if any(signal.startswith("missing_observed:") for signal in signals):
        fields = [
            signal.split(":", 1)[1]
            for signal in signals
            if signal.startswith("missing_observed:")
        ]
        return (
            "program",
            "Observed local behavior output observability gap for "
            + ", ".join(fields)
            + ".",
        )
    if status == "error" or any(signal.startswith("error:") for signal in signals):
        return "program", "Observed local behavior runtime or execution error."
    if status == "degraded" or status.startswith("degraded"):
        return (
            "program",
            "Observed degraded local behavior; investigate IO binding and observability.",
        )
    return None, None


def _bounded_refinement(
    *, behavior_status: str | None, proposal_status: str, signals: list[str]
) -> dict[str, Any]:
    if proposal_status == "insufficient_behavior_evidence":
        return {
            "refinement_kind": "proposal_only",
            "target_surfaces": [],
            "proposed_changes": [],
            "next_candidate_intent_patch": {
                "bounded_next_questions": [
                    "Add declared examples before proposing a semantic correction.",
                    "Keep the input/output contract unchanged unless new evidence shows it is invalid.",
                ]
            },
        }
    if proposal_status == "no_refinement_needed":
        return {
            "refinement_kind": "proposal_only",
            "target_surfaces": [],
            "proposed_changes": [],
            "next_candidate_intent_patch": {
                "bounded_next_questions": [
                    "Add more examples or a dataset slice before requesting another candidate.",
                    "Preserve declared inputs and outputs.",
                ]
            },
        }

    status = behavior_status or "unknown"
    surface, reason = _target_surface_for_status(status, signals)
    if surface is None or reason is None:
        surface = "program"
        reason = "Observed local behavior needs bounded inspection before another candidate is generated."

    if any(signal.startswith("mismatch:") for signal in signals):
        mismatch_fields = [
            signal.split(":", 1)[1]
            for signal in signals
            if signal.startswith("mismatch:")
        ]
        focus = ", ".join(mismatch_fields) if mismatch_fields else "declared outputs"
        change_type = "tighten_output_mapping"
        rationale = f"The current local behavior failed exact_match for {focus}."
        constraints = [
            "Preserve declared inputs and outputs.",
            f"Focus on correcting observed {focus} mismatch.",
        ]
    elif status == "error" or any(signal.startswith("error:") for signal in signals):
        change_type = "debug_execution_surface"
        rationale = "The current local behavior produced an execution error; debug runtime/materialized harness behavior before semantic changes."
        constraints = [
            "Preserve declared inputs and outputs.",
            "Focus on making the generated program executable over the observed evidence source.",
        ]
    elif (
        status == "degraded"
        or status.startswith("degraded")
        or any(signal.startswith("missing_observed:") for signal in signals)
    ):
        change_type = "improve_output_observability"
        rationale = "The current local behavior did not expose comparable declared outputs; inspect IO binding before semantic correction."
        constraints = [
            "Preserve declared inputs and outputs.",
            "Focus on exposing declared outputs for example-backed comparison.",
        ]
    else:
        change_type = "bounded_behavior_inspection"
        rationale = "The current local behavior did not pass; inspect the smallest surface consistent with observed signals."
        constraints = ["Preserve declared inputs and outputs."]

    return {
        "refinement_kind": "proposal_only",
        "target_surfaces": [{"surface": surface, "reason": reason}],
        "proposed_changes": [
            {
                "change_type": change_type,
                "surface": surface,
                "rationale": rationale,
                "evidence_refs": ["behavior_results.json", "oracle_report"],
            }
        ],
        "next_candidate_intent_patch": {"constraints": constraints},
    }


def build_program_refinement_proposal(
    *,
    manifest_path: Path,
    oracle_report_path: Path,
) -> dict[str, Any]:
    """Build a deterministic proposal artifact without mutating program files."""

    manifest_path = manifest_path.expanduser().resolve()
    oracle_report_path = oracle_report_path.expanduser().resolve()
    manifest = load_program_manifest(manifest_path)
    report = load_program_oracle_report(oracle_report_path)
    validate_program_oracle_report_non_authority(report)
    identity = _identity_from_manifest(manifest)
    oracle_record, oracle_matched = _validate_report_identity_match(report, identity)
    behavior, behavior_path, behavior_hash = load_program_behavior_results(
        manifest,
        manifest_path,
    )
    episode_summary = _manifest_behavior_evidence_summary(manifest)
    source_kinds = _behavior_source_kinds(manifest)
    summary = _behavior_summary(behavior) if behavior is not None else episode_summary
    behavior_status = str(summary.get("status") or "insufficient_behavior_evidence")
    output_fields = _output_fields(manifest, behavior)
    signals = _failure_signals(
        behavior=behavior,
        oracle_record=oracle_record,
        output_fields=output_fields,
    )
    proposal_status = _status_for_evidence(behavior, episode_summary)
    example_count = (
        int(_behavior_summary(behavior).get("total") or 0)
        if behavior is not None
        else 0
    )
    status_counts = _safe_mapping(summary.get("status_counts"))
    evidence_source_count = int(episode_summary.get("source_count") or 0)
    total_evaluation_count = int(episode_summary.get("total") or 0)

    proposal = {
        "schema_version": PROGRAM_REFINEMENT_PROPOSAL_SCHEMA,
        "status": proposal_status,
        "proposal_id": _proposal_id(identity, behavior_hash, report),
        "created_from": {
            "manifest_path": str(manifest_path),
            "manifest_sha256": _sha256_file(manifest_path),
            "oracle_report_path": str(oracle_report_path),
            "oracle_report_sha256": _sha256_file(oracle_report_path),
            "behavior_results_path": str(behavior_path)
            if behavior_path is not None and behavior_path.exists()
            else None,
            "behavior_results_sha256": behavior_hash,
        },
        "identity": identity,
        "evidence_summary": {
            "behavior_status": behavior_status,
            "example_count": example_count,
            "evidence_source_count": evidence_source_count,
            "total_evaluation_count": total_evaluation_count,
            "behavior_source_kinds": source_kinds,
            "status_counts": status_counts,
            "failure_signals": signals,
            "oracle_report_status": report.get("status"),
            "oracle_report_total_records": int(report.get("total_records") or 0),
            "oracle_report_record_matched": oracle_matched,
            "oracle_report_evidence_source_count": int(
                report.get("evidence_source_count") or 0
            ),
            "oracle_report_total_evaluation_count": int(
                report.get("total_evaluation_count") or 0
            ),
        },
        "bounded_refinement": _bounded_refinement(
            behavior_status=behavior_status,
            proposal_status=proposal_status,
            signals=signals,
        ),
        "limitations": _limitations_for_sources(source_kinds),
        "non_authority": dict(_PROPOSAL_NON_AUTHORITY),
    }
    return proposal


def write_program_refinement_proposal(
    proposal: Mapping[str, Any],
    out_path: Path,
) -> dict[str, Any]:
    """Write the proposal artifact and return the same JSON-compatible payload."""

    payload = dict(proposal)
    out_path = prepare_sidecar_output_path(
        out_path,
        payload=payload,
        artifact_label="program refinement proposal",
        payload_artifact_root_policy="forbid",
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(_json_text(payload), encoding="utf-8")
    return payload

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from dspx.services.program_refinement import (
    ProgramRefinementError,
    load_program_manifest,
)

PROGRAM_META_ADJUDICATION_PLAN_SCHEMA = "program-meta-adjudication-plan-v1"
PROGRAM_TARGET_PROFILE_SCHEMA = "program-target-profile-v1"
PROGRAM_JURY_REQUIREMENTS_SCHEMA = "program-jury-requirements-v1"
PROGRAM_META_JURY_SELECTION_SCHEMA = "program-meta-jury-selection-v1"
PROGRAM_JURY_VERIFICATION_SCHEMA = "program-jury-verification-v1"

_EXPECTED_SIDECAR_SCHEMAS = {
    "behavior_results": "program-behavior-results-v1",
    "behavior_episode": "program-behavior-episode-v1",
    "oracle_report": "program-oracle-evidence-report-v1",
    "oracle_publication_receipt": "program-oracle-shared-publication-receipt-v1",
    "jury_results": "program-jury-results-v1",
    "review": "program-promotion-review-refined-v1",
    "decision_record": "program-promotion-decision-record-v1",
    "activation_packet": "generated-cognition-program-production-activation-packet-v1",
}

_DEFAULT_SIDECAR_FILES = {
    "behavior_results": "behavior_results.json",
    "behavior_episode": "behavior_episode.json",
    "oracle_report": "program_oracle_report.json",
    "oracle_publication_receipt": "program_oracle_publication_receipt.json",
    "jury_results": "jury_results.json",
    "review": "promotion_review_refined.json",
    "decision_record": "promotion_decision_record.json",
    "activation_packet": "activation_packet.json",
}

_NON_AUTHORITY = {
    "activation_authority": False,
    "promotion_authority": False,
    "oracle_authority": False,
    "governance_authority": False,
    "external_authority": False,
    "external_mutation": False,
}

_EFFECT = {
    "candidate_files_mutated": False,
    "canonical_target_mutated": False,
    "ak_mutated": False,
    "governance_mutated": False,
    "oracle_index_mutated": False,
    "shared_oracle_mutated": False,
    "provider_called": False,
}


class ProgramMetaAdjudicationError(ValueError):
    """Raised when meta-adjudication planning inputs are invalid."""


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


def _first_text(*values: object) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _slug(value: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or "unspecified"


def _json_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.expanduser().read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProgramMetaAdjudicationError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ProgramMetaAdjudicationError(
            f"{label} must be valid JSON: {path}"
        ) from exc
    if not isinstance(payload, dict):
        raise ProgramMetaAdjudicationError(
            f"{label} must contain a JSON object: {path}"
        )
    return payload


def _manifest_root(manifest_path: Path) -> Path:
    return manifest_path.expanduser().resolve().parent


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
            execution_episode.get("episode_id"), receipt_bundle.get("episode_id")
        ),
        "receipt_bundle_id": _first_text(receipt_bundle.get("receipt_bundle_id")),
    }


def _sidecar_path(manifest_path: Path, *, key: str, explicit_path: Path | None) -> Path:
    if explicit_path is not None:
        return explicit_path.expanduser().resolve()
    return _manifest_root(manifest_path) / _DEFAULT_SIDECAR_FILES[key]


def _sidecar_status(
    manifest_path: Path, *, key: str, explicit_path: Path | None = None
) -> dict[str, Any]:
    path = _sidecar_path(manifest_path, key=key, explicit_path=explicit_path)
    required_schema = _EXPECTED_SIDECAR_SCHEMAS[key]
    status: dict[str, Any] = {
        "key": key,
        "path": str(path),
        "present": path.exists(),
        "required_schema": required_schema,
    }
    if not path.exists():
        if explicit_path is not None:
            status["status"] = "missing_explicit_path"
        else:
            status["status"] = "missing"
        return status
    payload = _load_json_object(path, label=f"{key} sidecar")
    schema = payload.get("schema_version")
    status.update(
        {
            "status": "present" if schema == required_schema else "schema_mismatch",
            "schema_version": schema,
            "sha256": _sha256_file(path),
        }
    )
    if schema != required_schema:
        status["warning"] = f"expected schema_version {required_schema}"
    return status


def _manifest_text(manifest: Mapping[str, Any]) -> str:
    intent = _safe_mapping(manifest.get("intent"))
    request = _safe_mapping(manifest.get("request"))
    parts: list[str] = []
    for value in (
        intent.get("name"),
        intent.get("objective"),
        intent.get("task_type"),
        intent.get("metric"),
        request.get("goal"),
        request.get("intent_source"),
    ):
        if value:
            parts.append(str(value))
    for key in ("inputs", "outputs", "constraints"):
        parts.extend(_string_list(intent.get(key)))
    parts.append(json.dumps(intent.get("promotion", {}), sort_keys=True))
    parts.append(json.dumps(intent.get("options", {}), sort_keys=True))
    return "\n".join(parts).lower()


def _target_profile(
    manifest: Mapping[str, Any], *, manifest_path: Path | None = None
) -> dict[str, Any]:
    intent = _safe_mapping(manifest.get("intent"))
    request = _safe_mapping(manifest.get("request"))
    text = _manifest_text(manifest)
    risks: list[dict[str, str]] = [
        {
            "risk_id": "behavior_quality",
            "reason": "every generated program needs behavior and regression evidence",
        },
        {
            "risk_id": "authority_boundary",
            "reason": "DSPx evidence must not be mistaken for production activation authority",
        },
    ]
    if any(
        token in text for token in ("source", "zotero", "citation", "marker", "rag")
    ):
        risks.append(
            {
                "risk_id": "source_grounding",
                "reason": "target mentions source/citation/Zotero/Marker/RAG grounding",
            }
        )
    if any(token in text for token in ("obsidian", "wiki", "atlas", "canonical")):
        risks.append(
            {
                "risk_id": "canonical_mutation_boundary",
                "reason": "target mentions Obsidian/Wiki/Atlas/canonical artifact boundaries",
            }
        )
    if any(token in text for token in ("review", "proposal", "queue", "human")):
        risks.append(
            {
                "risk_id": "review_queue_boundary",
                "reason": "target mentions review/proposal/human queue semantics",
            }
        )
    if any(
        token in text for token in ("deploy", "activation", "production", "rollout")
    ):
        risks.append(
            {
                "risk_id": "rollout_rollback",
                "reason": "target mentions deployment/activation/production rollout",
            }
        )
    profile: dict[str, Any] = {
        "schema_version": PROGRAM_TARGET_PROFILE_SCHEMA,
        "status": "derived_from_manifest",
        "authority": "target_profile_evidence_only_non_authoritative",
        "intent_name": _first_text(intent.get("name")),
        "objective": _first_text(intent.get("objective"), request.get("goal")),
        "task_type": _first_text(intent.get("task_type")),
        "metric": _first_text(intent.get("metric")),
        "inputs": _string_list(intent.get("inputs")),
        "outputs": _string_list(intent.get("outputs")),
        "declared_constraints": _string_list(intent.get("constraints")),
        "intent_source": _first_text(request.get("intent_source")),
        "risks": risks,
        "non_authority": dict(_NON_AUTHORITY),
        "effect": dict(_EFFECT),
    }
    if manifest_path is not None:
        resolved_manifest = manifest_path.expanduser().resolve()
        profile["identity"] = _identity_from_manifest(manifest)
        profile["manifest"] = {
            "path": str(resolved_manifest),
            "sha256": _sha256_file(resolved_manifest),
            "schema_version": manifest.get("schema_version"),
        }
    return profile


def _jury_requirements(profile: Mapping[str, Any]) -> dict[str, Any]:
    risk_ids = {
        str(risk.get("risk_id"))
        for risk in _safe_list(profile.get("risks"))
        if isinstance(risk, Mapping)
    }
    perspectives = [
        {
            "perspective": "behavior_evidence",
            "reason": "verify generated behavior evidence is complete and not overclaimed",
        },
        {
            "perspective": "target_domain",
            "reason": "verify target-specific semantics and acceptance risks",
        },
        {
            "perspective": "authority_boundary",
            "reason": "verify DSPx/Oracle/jury results remain evidence only",
        },
    ]
    if "source_grounding" in risk_ids:
        perspectives.append(
            {
                "perspective": "source_grounding",
                "reason": "verify provenance and source refs are preserved",
            }
        )
    if "canonical_mutation_boundary" in risk_ids:
        perspectives.append(
            {
                "perspective": "canonical_mutation_safety",
                "reason": "verify no canonical target surface is mutated by evidence generation",
            }
        )
    if "review_queue_boundary" in risk_ids:
        perspectives.append(
            {
                "perspective": "review_surface",
                "reason": "verify generated artifacts remain review/proposal-only",
            }
        )
    perspectives.append(
        {
            "perspective": "rollout_rollback",
            "reason": "verify activation requests include owner, binding, and rollback evidence",
        }
    )
    return {
        "schema_version": PROGRAM_JURY_REQUIREMENTS_SCHEMA,
        "status": "planned_not_executed",
        "authority": "jury_requirements_evidence_only_non_authoritative",
        "minimum_jurors": min(3, len(perspectives)),
        "required_perspectives": perspectives,
        "selection_constraints": {
            "prefer_diverse_perspectives": True,
            "require_authority_boundary_reviewer": True,
            "require_provider_identity_when_model_backed": True,
            "require_conflict_overlap_check": True,
        },
        "non_authority": dict(_NON_AUTHORITY),
        "effect": dict(_EFFECT),
    }


def _missing_evidence(sidecars: Mapping[str, Mapping[str, Any]]) -> list[str]:
    missing: list[str] = []
    if not sidecars["behavior_results"].get("present") and not sidecars[
        "behavior_episode"
    ].get("present"):
        missing.append("behavior_evidence")
    for key, label in (
        ("oracle_report", "oracle_report"),
        ("jury_results", "program_jury_results"),
        ("review", "refined_promotion_review"),
        ("decision_record", "domain_or_adjudicator_decision_record"),
        ("activation_packet", "activation_evidence_packet"),
    ):
        if not sidecars[key].get("present"):
            missing.append(label)
    missing.extend(
        [
            "target_discovery_review",
            "jury_panel_verification",
            "program_adjudicator_formation",
            "program_adjudicator_verification",
            "adjudication_behavior_trace_publication",
        ]
    )
    return missing


def _next_commands(
    manifest_path: Path, sidecars: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    manifest_arg = str(manifest_path.expanduser().resolve())
    root = _manifest_root(manifest_path)
    commands: list[dict[str, Any]] = []
    if not sidecars["jury_results"].get("present"):
        commands.append(
            {
                "step": "run_deterministic_jury_baseline",
                "implemented": True,
                "command": (
                    "dspx program-promote jury "
                    f"--manifest {manifest_arg} --out {root / 'jury_results.json'} --json"
                ),
            }
        )
    if not sidecars["oracle_report"].get("present"):
        commands.append(
            {
                "step": "produce_oracle_report",
                "implemented": True,
                "command": (
                    "dspx program-loop --intent <intent.yaml> "
                    "--outdir <fresh-candidate-dir> --json"
                ),
                "note": "program-loop writes candidate-local Oracle evidence/report; keep shared publication explicit",
            }
        )
    commands.append(
        {
            "step": "write_target_profile",
            "implemented": True,
            "command": (
                "dspx program-promote target-profile "
                f"--manifest {manifest_arg} --out {root / 'target_profile.json'} --json"
            ),
        }
    )
    commands.append(
        {
            "step": "write_jury_requirements",
            "implemented": True,
            "command": (
                "dspx program-promote jury-requirements "
                f"--manifest {manifest_arg} --out {root / 'jury_requirements.json'} --json"
            ),
        }
    )
    commands.append(
        {
            "step": "select_meta_jury_panel",
            "implemented": True,
            "command": (
                "dspx program-promote jury-panel "
                f"--jury-requirements {root / 'jury_requirements.json'} "
                f"--out {root / 'meta_jury_selection.json'} --json"
            ),
        }
    )
    commands.append(
        {
            "step": "verify_meta_jury_panel",
            "implemented": True,
            "command": (
                "dspx program-promote verify-jury-panel "
                f"--jury-selection {root / 'meta_jury_selection.json'} "
                f"--out {root / 'jury_verification.json'} --json"
            ),
        }
    )
    commands.append(
        {
            "step": "phase4_form_and_verify_program_adjudicator",
            "implemented": False,
            "command": "future: dspx program-promote adjudicator-formation --jury-verification <jury_verification.json>",
        }
    )
    commands.append(
        {
            "step": "phase4_publish_adjudication_trace",
            "implemented": False,
            "command": "future: dspx oracle program-evidence publish --include-adjudication-trace <trace.json>",
        }
    )
    return commands


def build_program_target_profile(*, manifest_path: Path) -> dict[str, Any]:
    """Build a first-class target profile sidecar without model calls."""

    try:
        manifest = load_program_manifest(manifest_path)
    except ProgramRefinementError as exc:
        raise ProgramMetaAdjudicationError(str(exc)) from exc
    return _target_profile(manifest, manifest_path=manifest_path)


def write_program_target_profile(
    profile: Mapping[str, Any], out_path: Path
) -> dict[str, Any]:
    if profile.get("schema_version") != PROGRAM_TARGET_PROFILE_SCHEMA:
        raise ProgramMetaAdjudicationError(
            "target profile schema_version must be " + PROGRAM_TARGET_PROFILE_SCHEMA
        )
    out = out_path.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(profile)
    out.write_text(_json_text(payload), encoding="utf-8")
    return payload


def build_program_jury_requirements(
    *, manifest_path: Path | None = None, target_profile_path: Path | None = None
) -> dict[str, Any]:
    """Build first-class jury requirements from a target profile or manifest."""

    if target_profile_path is not None:
        profile = _load_json_object(target_profile_path, label="target profile")
        if profile.get("schema_version") != PROGRAM_TARGET_PROFILE_SCHEMA:
            raise ProgramMetaAdjudicationError(
                "target profile schema_version must be " + PROGRAM_TARGET_PROFILE_SCHEMA
            )
        requirements = _jury_requirements(profile)
        requirements["target_profile"] = {
            "path": str(target_profile_path.expanduser().resolve()),
            "sha256": _sha256_file(target_profile_path.expanduser().resolve()),
            "schema_version": profile.get("schema_version"),
        }
        if isinstance(profile.get("identity"), Mapping):
            requirements["identity"] = dict(profile["identity"])
        return requirements
    if manifest_path is None:
        raise ProgramMetaAdjudicationError(
            "either manifest_path or target_profile_path is required"
        )
    profile = build_program_target_profile(manifest_path=manifest_path)
    return _jury_requirements(profile)


def write_program_jury_requirements(
    requirements: Mapping[str, Any], out_path: Path
) -> dict[str, Any]:
    if requirements.get("schema_version") != PROGRAM_JURY_REQUIREMENTS_SCHEMA:
        raise ProgramMetaAdjudicationError(
            "jury requirements schema_version must be "
            + PROGRAM_JURY_REQUIREMENTS_SCHEMA
        )
    out = out_path.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(requirements)
    out.write_text(_json_text(payload), encoding="utf-8")
    return payload


def build_program_meta_jury_selection(
    *,
    manifest_path: Path | None = None,
    target_profile_path: Path | None = None,
    jury_requirements_path: Path | None = None,
) -> dict[str, Any]:
    """Build a deterministic meta-jury selection sidecar without model calls."""

    requirements: dict[str, Any]
    requirements_ref: dict[str, Any] | None = None
    if jury_requirements_path is not None:
        requirements = _load_json_object(
            jury_requirements_path, label="jury requirements"
        )
        if requirements.get("schema_version") != PROGRAM_JURY_REQUIREMENTS_SCHEMA:
            raise ProgramMetaAdjudicationError(
                "jury requirements schema_version must be "
                + PROGRAM_JURY_REQUIREMENTS_SCHEMA
            )
        requirements_ref = {
            "path": str(jury_requirements_path.expanduser().resolve()),
            "sha256": _sha256_file(jury_requirements_path.expanduser().resolve()),
            "schema_version": requirements.get("schema_version"),
        }
    else:
        requirements = build_program_jury_requirements(
            manifest_path=manifest_path, target_profile_path=target_profile_path
        )

    required_perspectives = [
        dict(item)
        for item in _safe_list(requirements.get("required_perspectives"))
        if isinstance(item, Mapping) and _first_text(item.get("perspective"))
    ]
    selected_jurors: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in required_perspectives:
        perspective = str(item["perspective"])
        if perspective in seen:
            continue
        seen.add(perspective)
        selected_jurors.append(
            {
                "juror_id": f"meta_juror_{_slug(perspective)}",
                "perspective": perspective,
                "kind": "deterministic_role_juror",
                "model_backed": False,
                "provider": None,
                "model": None,
                "qualification": item.get("reason"),
                "selection_reason": "selected to cover required target-risk perspective",
                "authority": "advisory_evidence_only",
            }
        )

    selected_perspectives = [str(juror["perspective"]) for juror in selected_jurors]
    missing_perspectives = [
        str(item["perspective"])
        for item in required_perspectives
        if str(item["perspective"]) not in selected_perspectives
    ]
    minimum_jurors = int(requirements.get("minimum_jurors") or 0)
    status = (
        "selected"
        if len(selected_jurors) >= minimum_jurors and not missing_perspectives
        else "selection_incomplete"
    )
    selection: dict[str, Any] = {
        "schema_version": PROGRAM_META_JURY_SELECTION_SCHEMA,
        "status": status,
        "authority": "meta_jury_selection_evidence_only_non_authoritative",
        "minimum_jurors": minimum_jurors,
        "selected_jurors": selected_jurors,
        "coverage": {
            "required_perspectives": [
                str(item["perspective"]) for item in required_perspectives
            ],
            "selected_perspectives": selected_perspectives,
            "missing_perspectives": missing_perspectives,
        },
        "selection_constraints": _safe_mapping(
            requirements.get("selection_constraints")
        ),
        "selection_method": "deterministic_required_perspective_coverage_v1",
        "notes": [
            "This sidecar selects deterministic role-jurors only.",
            "No model/provider was called and no production authority was granted.",
            "Model-backed juror nomination remains a future explicit phase.",
        ],
        "non_authority": dict(_NON_AUTHORITY),
        "effect": dict(_EFFECT),
    }
    if requirements_ref is not None:
        selection["jury_requirements"] = requirements_ref
    if isinstance(requirements.get("identity"), Mapping):
        selection["identity"] = dict(requirements["identity"])
    return selection


def write_program_meta_jury_selection(
    selection: Mapping[str, Any], out_path: Path
) -> dict[str, Any]:
    if selection.get("schema_version") != PROGRAM_META_JURY_SELECTION_SCHEMA:
        raise ProgramMetaAdjudicationError(
            "meta jury selection schema_version must be "
            + PROGRAM_META_JURY_SELECTION_SCHEMA
        )
    out = out_path.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(selection)
    out.write_text(_json_text(payload), encoding="utf-8")
    return payload


def build_program_jury_verification(*, jury_selection_path: Path) -> dict[str, Any]:
    """Verify a deterministic meta-jury selection without judging the program."""

    selection = _load_json_object(jury_selection_path, label="meta jury selection")
    if selection.get("schema_version") != PROGRAM_META_JURY_SELECTION_SCHEMA:
        raise ProgramMetaAdjudicationError(
            "meta jury selection schema_version must be "
            + PROGRAM_META_JURY_SELECTION_SCHEMA
        )
    jurors = [
        dict(item)
        for item in _safe_list(selection.get("selected_jurors"))
        if isinstance(item, Mapping)
    ]
    perspectives = [str(juror.get("perspective") or "") for juror in jurors]
    perspective_set = {perspective for perspective in perspectives if perspective}
    constraints = _safe_mapping(selection.get("selection_constraints"))
    coverage = _safe_mapping(selection.get("coverage"))
    required_perspectives = set(_string_list(coverage.get("required_perspectives")))
    missing_perspectives = sorted(required_perspectives - perspective_set)
    minimum_jurors = int(selection.get("minimum_jurors") or 0)
    duplicate_perspectives = sorted(
        perspective
        for perspective in perspective_set
        if perspectives.count(perspective) > 1
    )
    missing_provider_identity = [
        str(juror.get("juror_id") or "unknown")
        for juror in jurors
        if juror.get("model_backed") is True
        and (not juror.get("provider") or not juror.get("model"))
    ]
    checks = [
        {
            "check": "minimum_jurors_satisfied",
            "ok": len(jurors) >= minimum_jurors,
            "detail": f"selected={len(jurors)} minimum={minimum_jurors}",
        },
        {
            "check": "required_perspective_coverage_complete",
            "ok": not missing_perspectives,
            "detail": ",".join(missing_perspectives) or "complete",
        },
        {
            "check": "authority_boundary_present",
            "ok": (
                not constraints.get("require_authority_boundary_reviewer")
                or "authority_boundary" in perspective_set
            ),
            "detail": "authority_boundary perspective required by selection constraints",
        },
        {
            "check": "no_duplicate_perspectives",
            "ok": not duplicate_perspectives,
            "detail": ",".join(duplicate_perspectives) or "none",
        },
        {
            "check": "model_backed_jurors_have_provider_identity",
            "ok": not missing_provider_identity,
            "detail": ",".join(missing_provider_identity)
            or "not_applicable_or_complete",
        },
        {
            "check": "selection_has_no_authority_effect",
            "ok": _safe_mapping(selection.get("non_authority")).get(
                "activation_authority"
            )
            is False
            and _safe_mapping(selection.get("effect")).get("provider_called") is False,
            "detail": "selection must be evidence-only and local in this phase",
        },
    ]
    failed_checks = [str(check["check"]) for check in checks if not check["ok"]]
    verified = not failed_checks
    return {
        "schema_version": PROGRAM_JURY_VERIFICATION_SCHEMA,
        "status": "verified" if verified else "revise_jury_selection",
        "authority": "jury_verification_evidence_only_non_authoritative",
        "dspx_adjudicator": {
            "id": "dspx_meta_adjudicator_v1",
            "mode": "deterministic_contract_check",
            "scope": "judge_jury_fitness_not_program_promotion_or_activation",
            "model_backed": False,
        },
        "jury_selection": {
            "path": str(jury_selection_path.expanduser().resolve()),
            "sha256": _sha256_file(jury_selection_path.expanduser().resolve()),
            "schema_version": selection.get("schema_version"),
        },
        "checks": checks,
        "failed_checks": failed_checks,
        "approved_for_program_adjudicator_formation": verified,
        "next_required_action": (
            "form_program_adjudicator" if verified else "revise_jury_selection"
        ),
        "non_authority": dict(_NON_AUTHORITY),
        "effect": dict(_EFFECT),
    }


def write_program_jury_verification(
    verification: Mapping[str, Any], out_path: Path
) -> dict[str, Any]:
    if verification.get("schema_version") != PROGRAM_JURY_VERIFICATION_SCHEMA:
        raise ProgramMetaAdjudicationError(
            "jury verification schema_version must be "
            + PROGRAM_JURY_VERIFICATION_SCHEMA
        )
    out = out_path.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(verification)
    out.write_text(_json_text(payload), encoding="utf-8")
    return payload


def build_program_meta_adjudication_plan(
    *,
    manifest_path: Path,
    behavior_results_path: Path | None = None,
    behavior_episode_path: Path | None = None,
    oracle_report_path: Path | None = None,
    oracle_publication_receipt_path: Path | None = None,
    jury_results_path: Path | None = None,
    review_path: Path | None = None,
    decision_record_path: Path | None = None,
    activation_packet_path: Path | None = None,
) -> dict[str, Any]:
    """Build a local meta-adjudication plan without model calls or authority effects."""

    try:
        manifest = load_program_manifest(manifest_path)
    except ProgramRefinementError as exc:
        raise ProgramMetaAdjudicationError(str(exc)) from exc

    sidecars = {
        "behavior_results": _sidecar_status(
            manifest_path, key="behavior_results", explicit_path=behavior_results_path
        ),
        "behavior_episode": _sidecar_status(
            manifest_path, key="behavior_episode", explicit_path=behavior_episode_path
        ),
        "oracle_report": _sidecar_status(
            manifest_path, key="oracle_report", explicit_path=oracle_report_path
        ),
        "oracle_publication_receipt": _sidecar_status(
            manifest_path,
            key="oracle_publication_receipt",
            explicit_path=oracle_publication_receipt_path,
        ),
        "jury_results": _sidecar_status(
            manifest_path, key="jury_results", explicit_path=jury_results_path
        ),
        "review": _sidecar_status(
            manifest_path, key="review", explicit_path=review_path
        ),
        "decision_record": _sidecar_status(
            manifest_path, key="decision_record", explicit_path=decision_record_path
        ),
        "activation_packet": _sidecar_status(
            manifest_path, key="activation_packet", explicit_path=activation_packet_path
        ),
    }
    profile = _target_profile(manifest, manifest_path=manifest_path)
    requirements = _jury_requirements(profile)
    missing = _missing_evidence(sidecars)
    return {
        "schema_version": PROGRAM_META_ADJUDICATION_PLAN_SCHEMA,
        "status": "planned_not_executed",
        "lifecycle_state": "meta_adjudication_plan_ready",
        "authority": "local_meta_adjudication_plan_evidence_only_non_authoritative",
        "identity": _identity_from_manifest(manifest),
        "manifest": {
            "path": str(manifest_path.expanduser().resolve()),
            "sha256": _sha256_file(manifest_path.expanduser().resolve()),
            "schema_version": manifest.get("schema_version"),
        },
        "target_profile": profile,
        "jury_requirements": requirements,
        "sidecars": sidecars,
        "missing_evidence": missing,
        "next_commands": _next_commands(manifest_path, sidecars),
        "oracle_postgres_behavior_memory": {
            "intended_label": "adjudication_behavior_trace",
            "publication_allowed_by_this_plan": False,
            "requires_explicit_publication_preflight": True,
            "activation_authority": False,
        },
        "gepa_improvement_lane": {
            "eligible_after_trace_publication": True,
            "optimized_artifact_kind": "versioned_judging_policy_or_prompt",
            "activation_authority": False,
            "requires_curated_train_validation_examples": True,
        },
        "non_authority": dict(_NON_AUTHORITY),
        "effect": dict(_EFFECT),
    }


def write_program_meta_adjudication_plan(
    plan: Mapping[str, Any], out_path: Path
) -> dict[str, Any]:
    if plan.get("schema_version") != PROGRAM_META_ADJUDICATION_PLAN_SCHEMA:
        raise ProgramMetaAdjudicationError(
            "meta-adjudication plan schema_version must be "
            + PROGRAM_META_ADJUDICATION_PLAN_SCHEMA
        )
    out = out_path.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(plan)
    out.write_text(_json_text(payload), encoding="utf-8")
    return payload

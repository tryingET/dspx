from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from dspx.cache import sha256_text
from dspx.services.program_artifact_names import PROTECTED_PROGRAM_ARTIFACT_NAMES
from dspx.services.program_architecture import (
    PROGRAM_ARCHITECTURE_CANDIDATES_SCHEMA,
    ProgramArchitectureError,
    _json_text,
    _non_authority,
    build_program_architecture_candidates,
)
from dspx.services.program_intent import ProgramIntent, load_program_intent
from dspx.services.program_service import materialize_program_from_intent
from dspx.services.run_replay_service import check_run_receipt

PROGRAM_ARCHITECTURE_TOURNAMENT_SCHEMA = "program-architecture-tournament-v1"
PROGRAM_ARCHITECTURE_TOURNAMENT_EVIDENCE_MATRIX_SCHEMA = (
    "program-architecture-tournament-evidence-matrix-v1"
)
_FORBIDDEN_OUTPUT_NAMES = set(PROTECTED_PROGRAM_ARTIFACT_NAMES)


_PLAN_REQUIRED_FALSE_EFFECT_FLAGS = (
    "candidate_materialized",
    "provider_called",
    "oracle_index_mutated",
    "ak_called",
    "governance_mutated",
    "external_authority_mutated",
)
_PLAN_OPTIONAL_FALSE_EFFECT_FLAGS = ("winner_selected", "promotion_applied")
_PLAN_REQUIRED_FALSE_NON_AUTHORITY_FLAGS = (
    "winner_selection",
    "ranking_authority",
    "promotion_authority",
    "activation_authority",
    "oracle_authority",
    "governance_authority",
    "external_mutation",
    "canonical_mutation",
)
_PLAN_OPTIONAL_FALSE_NON_AUTHORITY_FLAGS = (
    "oracle_ranking",
    "oracle_pruning",
    "oracle_promotion",
)


class ProgramArchitectureTournamentError(ProgramArchitectureError):
    """Raised when local architecture tournament execution is unsafe."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))
    except Exception as exc:
        raise ProgramArchitectureTournamentError(
            f"failed to read JSON: {path}"
        ) from exc
    if not isinstance(payload, dict):
        raise ProgramArchitectureTournamentError(
            "architecture tournament input must be a JSON object"
        )
    return payload


def _content_hash(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _optional_json(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    return _load_json(path)


def _mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _safe_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip()) if value.strip() else 0
        except ValueError:
            return 0
    return 0


def _validate_output_path(path: Path, *, label: str) -> Path:
    target = path.expanduser().resolve()
    if target.name in _FORBIDDEN_OUTPUT_NAMES:
        raise ProgramArchitectureTournamentError(
            f"refusing to write {label} to generated candidate artifact path: {target.name}"
        )
    if target.exists() and target.is_dir():
        raise ProgramArchitectureTournamentError(
            f"{label} output path is a directory: {target}"
        )
    return target


def _safe_output_path(path: Path, *, label: str) -> Path:
    target = _validate_output_path(path, label=label)
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _safe_outdir(path: Path) -> Path:
    target = path.expanduser().resolve()
    if target.exists() and not target.is_dir():
        raise ProgramArchitectureTournamentError(
            f"tournament outdir is a file: {target}"
        )
    target.mkdir(parents=True, exist_ok=True)
    return target


def _safe_candidate_id(value: object) -> str:
    candidate_id = str(value or "").strip()
    if not candidate_id:
        raise ProgramArchitectureTournamentError(
            "architecture candidate_id must not be blank"
        )
    if candidate_id in {".", ".."} or "/" in candidate_id or "\\" in candidate_id:
        raise ProgramArchitectureTournamentError(
            f"architecture candidate_id is path-hostile: {candidate_id!r}"
        )
    return candidate_id


def _candidate_dir(root: Path, candidate_id: str) -> Path:
    target = (root / "candidates" / candidate_id).resolve()
    candidates_root = (root / "candidates").resolve()
    if candidates_root not in [target, *target.parents]:
        raise ProgramArchitectureTournamentError(
            f"candidate output path escapes tournament root: {candidate_id!r}"
        )
    if target.exists():
        raise ProgramArchitectureTournamentError(
            f"candidate output already exists: {target}"
        )
    return target


def _missing_required_flags(
    value: object, required_flags: tuple[str, ...]
) -> list[str]:
    mapping = _mapping(value)
    return [key for key in required_flags if key not in mapping]


def _widened_plan_effect_flags(value: object) -> list[str]:
    effect = _mapping(value)
    return [
        key
        for key in (
            *_PLAN_REQUIRED_FALSE_EFFECT_FLAGS,
            *_PLAN_OPTIONAL_FALSE_EFFECT_FLAGS,
        )
        if key in effect and effect.get(key) is not False
    ]


def _widened_plan_non_authority_flags(value: object) -> list[str]:
    non_authority = _mapping(value)
    return [
        key
        for key in (
            *_PLAN_REQUIRED_FALSE_NON_AUTHORITY_FLAGS,
            *_PLAN_OPTIONAL_FALSE_NON_AUTHORITY_FLAGS,
        )
        if key in non_authority and non_authority.get(key) is not False
    ]


def _candidate_source_comparable_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    comparable = dict(payload)
    comparable.pop("name", None)
    comparable.pop("topology", None)
    options = dict(comparable.get("options") or {})
    options.pop("module_inference", None)
    options.pop("prompt_module_inference", None)
    if options:
        comparable["options"] = options
    else:
        comparable.pop("options", None)
    return comparable


def _validate_candidate_intent_payload(
    *,
    candidate: Mapping[str, Any],
    index: int,
    intent_identity: Mapping[str, Any],
    source_intent_payload: Mapping[str, Any],
) -> None:
    if candidate.get("status") != "materializable":
        return
    candidate_id = _safe_candidate_id(candidate.get("candidate_id"))
    intent_payload = candidate.get("intent_payload")
    if not isinstance(intent_payload, Mapping):
        raise ProgramArchitectureTournamentError(
            f"architecture plan candidate {index} materializable candidate lacks intent_payload"
        )
    try:
        ProgramIntent.model_validate(dict(intent_payload))
    except Exception as exc:
        raise ProgramArchitectureTournamentError(
            f"architecture plan candidate {index} intent_payload is invalid: {exc}"
        ) from exc
    for key in ["schema_version", "objective", "inputs", "outputs"]:
        if key in intent_identity and intent_payload.get(key) != intent_identity.get(
            key
        ):
            raise ProgramArchitectureTournamentError(
                f"architecture plan candidate {index} intent_payload does not match intent_identity.{key}"
            )
    if source_intent_payload and _candidate_source_comparable_payload(
        intent_payload
    ) != _candidate_source_comparable_payload(source_intent_payload):
        raise ProgramArchitectureTournamentError(
            f"architecture plan candidate {index} intent_payload source fields drift from source_intent_payload"
        )
    candidate_topology = dict(candidate.get("topology") or {})
    payload_topology = dict(intent_payload.get("topology") or {})
    if candidate_topology != payload_topology:
        raise ProgramArchitectureTournamentError(
            f"architecture plan candidate {candidate_id} topology does not match intent_payload topology"
        )
    topology_source = str(candidate.get("topology_source") or "")
    if topology_source == "baseline_default" and payload_topology:
        raise ProgramArchitectureTournamentError(
            f"architecture plan candidate {candidate_id} baseline topology source cannot carry intent_payload topology"
        )
    if (
        topology_source in {"declared", "prompt_inferred"}
        and payload_topology.get("kind") != "pipeline"
    ):
        raise ProgramArchitectureTournamentError(
            f"architecture plan candidate {candidate_id} topology source requires pipeline intent_payload topology"
        )
    intent_hash = str(candidate.get("intent_hash") or "").strip()
    if not intent_hash:
        raise ProgramArchitectureTournamentError(
            f"architecture plan candidate {index} missing intent_hash"
        )
    actual_hash = sha256_text(_json_text(dict(intent_payload)))
    if intent_hash != actual_hash:
        raise ProgramArchitectureTournamentError(
            f"architecture plan candidate {index} intent_hash mismatch"
        )


def _validate_architecture_plan(plan: Mapping[str, Any]) -> None:
    if plan.get("schema_version") != PROGRAM_ARCHITECTURE_CANDIDATES_SCHEMA:
        raise ProgramArchitectureTournamentError(
            "architecture plan schema_version must be program-architecture-candidates-v1"
        )
    candidates = plan.get("candidates")
    if not isinstance(candidates, list):
        raise ProgramArchitectureTournamentError(
            "architecture plan candidates must be a list"
        )
    candidate_count = plan.get("candidate_count")
    if candidate_count is not None and candidate_count != len(candidates):
        raise ProgramArchitectureTournamentError(
            "architecture plan candidate_count does not match candidates length"
        )
    intent_identity = _mapping(plan.get("intent_identity"))
    source_intent_payload = _mapping(plan.get("source_intent_payload"))
    if not source_intent_payload:
        raise ProgramArchitectureTournamentError(
            "architecture plan source_intent_payload is required for candidate lineage validation"
        )
    missing_identity = [
        key
        for key in ["schema_version", "objective", "inputs", "outputs", "intent_hash"]
        if key not in intent_identity
    ]
    if missing_identity:
        raise ProgramArchitectureTournamentError(
            "architecture plan intent_identity missing required fields: "
            + ", ".join(missing_identity)
        )
    source_hash = sha256_text(
        json.dumps(dict(source_intent_payload), ensure_ascii=False, sort_keys=True)
    )
    if intent_identity.get("intent_hash") != source_hash:
        raise ProgramArchitectureTournamentError(
            "architecture plan source_intent_payload hash does not match intent_identity.intent_hash"
        )
    missing_effect = _missing_required_flags(
        plan.get("effect"), _PLAN_REQUIRED_FALSE_EFFECT_FLAGS
    )
    if missing_effect:
        raise ProgramArchitectureTournamentError(
            "architecture plan effect missing authority flags: "
            + ", ".join(missing_effect)
        )
    widened_effect = _widened_plan_effect_flags(plan.get("effect"))
    if widened_effect:
        raise ProgramArchitectureTournamentError(
            "architecture plan effect widens authority: " + ", ".join(widened_effect)
        )
    missing_non_authority = _missing_required_flags(
        plan.get("non_authority"), _PLAN_REQUIRED_FALSE_NON_AUTHORITY_FLAGS
    )
    if missing_non_authority:
        raise ProgramArchitectureTournamentError(
            "architecture plan non_authority missing authority flags: "
            + ", ".join(missing_non_authority)
        )
    widened_non_authority = _widened_plan_non_authority_flags(plan.get("non_authority"))
    if widened_non_authority:
        raise ProgramArchitectureTournamentError(
            "architecture plan non_authority widens authority: "
            + ", ".join(widened_non_authority)
        )
    seen_candidate_ids: set[str] = set()
    for index, candidate_value in enumerate(candidates):
        if not isinstance(candidate_value, Mapping):
            raise ProgramArchitectureTournamentError(
                f"architecture plan candidate {index} must be an object"
            )
        candidate = _mapping(candidate_value)
        candidate_id = _safe_candidate_id(candidate.get("candidate_id"))
        if candidate_id in seen_candidate_ids:
            raise ProgramArchitectureTournamentError(
                f"duplicate architecture candidate_id: {candidate_id}"
            )
        seen_candidate_ids.add(candidate_id)
        missing_candidate_effect = _missing_required_flags(
            candidate.get("effect"), _PLAN_REQUIRED_FALSE_EFFECT_FLAGS
        )
        if missing_candidate_effect:
            raise ProgramArchitectureTournamentError(
                f"architecture plan candidate {index} effect missing authority flags: "
                + ", ".join(missing_candidate_effect)
            )
        widened_candidate_effect = _widened_plan_effect_flags(candidate.get("effect"))
        if widened_candidate_effect:
            raise ProgramArchitectureTournamentError(
                f"architecture plan candidate {index} effect widens authority: "
                + ", ".join(widened_candidate_effect)
            )
        missing_candidate_non_authority = _missing_required_flags(
            candidate.get("non_authority"), _PLAN_REQUIRED_FALSE_NON_AUTHORITY_FLAGS
        )
        if missing_candidate_non_authority:
            raise ProgramArchitectureTournamentError(
                f"architecture plan candidate {index} non_authority missing authority flags: "
                + ", ".join(missing_candidate_non_authority)
            )
        widened_candidate_non_authority = _widened_plan_non_authority_flags(
            candidate.get("non_authority")
        )
        if widened_candidate_non_authority:
            raise ProgramArchitectureTournamentError(
                f"architecture plan candidate {index} non_authority widens authority: "
                + ", ".join(widened_candidate_non_authority)
            )
        _validate_candidate_intent_payload(
            candidate=candidate,
            index=index,
            intent_identity=intent_identity,
            source_intent_payload=source_intent_payload,
        )


def _validated_selected_candidate_ids(
    *, architecture_plan: Mapping[str, Any], candidate_ids: list[str] | None
) -> set[str]:
    selected_ids = {
        _safe_candidate_id(item) for item in candidate_ids or [] if str(item).strip()
    }
    if not selected_ids:
        return set()
    plan_candidate_ids = {
        _safe_candidate_id(candidate.get("candidate_id"))
        for candidate in architecture_plan.get("candidates", [])
        if isinstance(candidate, Mapping)
    }
    unknown = sorted(selected_ids - plan_candidate_ids)
    if unknown:
        raise ProgramArchitectureTournamentError(
            "unknown architecture candidate id(s): " + ", ".join(unknown)
        )
    return selected_ids


def _candidate_allowed(candidate_id: str, candidate_ids: set[str]) -> bool:
    return not candidate_ids or candidate_id in candidate_ids


def _preflight_tournament_outputs(
    *, root: Path, architecture_plan: Mapping[str, Any], selected_ids: set[str]
) -> None:
    intent_dir = root / "candidate_intents"
    if intent_dir.exists() and not intent_dir.is_dir():
        raise ProgramArchitectureTournamentError(
            f"candidate intents output path is not a directory: {intent_dir}"
        )
    candidates_dir = root / "candidates"
    if candidates_dir.exists() and not candidates_dir.is_dir():
        raise ProgramArchitectureTournamentError(
            f"candidate outputs path is not a directory: {candidates_dir}"
        )
    candidates = architecture_plan.get("candidates", [])
    for raw_candidate in candidates:
        if not isinstance(raw_candidate, Mapping):
            continue
        candidate_id = _safe_candidate_id(raw_candidate.get("candidate_id"))
        if not _candidate_allowed(candidate_id, selected_ids):
            continue
        if raw_candidate.get("status") != "materializable":
            continue
        _candidate_dir(root, candidate_id)
        intent_path = root / "candidate_intents" / f"{candidate_id}.json"
        if intent_path.exists():
            raise ProgramArchitectureTournamentError(
                f"candidate intent output already exists: {intent_path}"
            )


def _artifact_ref(path: Path) -> dict[str, Any]:
    return {
        "path": path.name,
        "exists": path.exists(),
        "content_hash": _content_hash(path),
    }


def _candidate_evidence_row(record: Mapping[str, Any]) -> dict[str, Any]:
    if record.get("status") == "skipped":
        return {
            "candidate_id": record.get("candidate_id"),
            "status": "skipped",
            "reason": record.get("reason"),
            "non_authority": {
                "winner_selection": False,
                "promotion_authority": False,
                "oracle_ranking": False,
            },
        }
    root = Path(str(record.get("root_path") or ""))
    execution_episode = _optional_json(root / "execution_episode.json")
    behavior_results = _optional_json(root / "behavior_results.json")
    oracle_evidence = _optional_json(root / "oracle_evidence.json")
    behavior_summary = _mapping(execution_episode.get("behavior_evidence_summary"))
    behavioral_eval = _mapping(execution_episode.get("behavioral_evaluation"))
    behavior_sources = execution_episode.get("evaluation_sources")
    source_kinds: list[str] = []
    if isinstance(behavior_sources, list):
        for source in behavior_sources:
            if isinstance(source, Mapping):
                source_kind = str(source.get("source_kind") or source.get("kind") or "")
                if source_kind:
                    source_kinds.append(source_kind)
    oracle_facets = _mapping(oracle_evidence.get("oracle_facets"))
    oracle_text = oracle_evidence.get("oracle_text")
    summary = _mapping(behavioral_eval.get("summary")) or _mapping(
        behavior_results.get("summary")
    )
    status_counts = _mapping(summary.get("status_counts")) or _mapping(
        behavior_summary.get("status_counts")
    )
    topology = _mapping(record.get("topology_execution"))
    checks = _mapping(execution_episode.get("checks"))
    return {
        "candidate_id": record.get("candidate_id"),
        "label": record.get("label"),
        "family": record.get("family"),
        "plan_recommendation": record.get("plan_recommendation"),
        "materialization_status": record.get("status"),
        "replay_status": _mapping(record.get("replay_check")).get("status"),
        "assembly_id": record.get("assembly_id"),
        "candidate_runtime_id": record.get("candidate_runtime_id"),
        "topology": {
            "status": topology.get("status"),
            "materialized": topology.get("materialized"),
            "renderer": topology.get("current_renderer"),
            "kind": topology.get("materialized_topology_kind")
            or topology.get("declared_topology_kind")
            or topology.get("inferred_topology_kind"),
        },
        "checks": {
            "smoke": _mapping(checks.get("smoke")).get("status"),
            "examples_binding": _mapping(checks.get("examples_binding")).get("status"),
            "dataset_binding": _mapping(checks.get("dataset_binding")).get("status"),
            "jury_binding": _mapping(checks.get("jury_binding")).get("status"),
            "promotion_binding": _mapping(checks.get("promotion_binding")).get(
                "status"
            ),
        },
        "artifacts": {
            "manifest": {
                "path": Path(str(record.get("manifest_path") or "manifest.json")).name,
                "content_hash": record.get("manifest_hash"),
            },
            "receipt": {
                "path": Path(
                    str(record.get("receipt_path") or "manifest.json.meta.json")
                ).name,
                "content_hash": record.get("receipt_hash"),
            },
            "execution_episode": _artifact_ref(root / "execution_episode.json"),
            "behavior_results": _artifact_ref(root / "behavior_results.json"),
            "behavior_episode": _artifact_ref(root / "behavior_episode.json"),
            "oracle_evidence": _artifact_ref(root / "oracle_evidence.json"),
            "oracle_report": _artifact_ref(root / "program_oracle_report.json"),
            "oracle_index": _artifact_ref(root / "oracle" / "coordinates.db"),
            "module_surfaces": _artifact_ref(root / "module_surfaces.json"),
            "capability_registry": _artifact_ref(
                root / "program_capability_registry.json"
            ),
            "generated_module_policy": _artifact_ref(
                root / "generated_module_policy.json"
            ),
        },
        "behavior_summary": {
            "status": behavior_summary.get("status") or summary.get("status"),
            "total": _safe_int(behavior_summary.get("total") or summary.get("total")),
            "passed": _safe_int(
                behavior_summary.get("passed") or summary.get("passed")
            ),
            "failed": _safe_int(
                behavior_summary.get("failed") or summary.get("failed")
            ),
            "error": _safe_int(behavior_summary.get("error") or summary.get("error")),
            "degraded": _safe_int(
                behavior_summary.get("degraded") or summary.get("degraded")
            ),
            "status_counts": status_counts,
        },
        "behavior_sources": {
            "source_count": _safe_int(behavior_summary.get("source_count"))
            or len(source_kinds),
            "executed_source_count": _safe_int(
                behavior_summary.get("executed_source_count")
            ),
            "source_kinds": source_kinds,
            "dataset_split_count": sum(
                1 for item in source_kinds if item == "dataset_split"
            ),
        },
        "oracle_readability": {
            "status": _mapping(execution_episode.get("oracle_readability")).get(
                "status"
            ),
            "failure_mode_count": _safe_int(oracle_facets.get("failure_mode_count")),
            "has_failures": bool(oracle_facets.get("has_failures")),
            "oracle_text_hash": sha256_text(str(oracle_text))
            if isinstance(oracle_text, str) and oracle_text
            else None,
            "candidate_local_report_status": _mapping(
                _mapping(record.get("candidate_local_oracle")).get("report_summary")
            ).get("status"),
            "candidate_local_report_records": _mapping(
                _mapping(record.get("candidate_local_oracle")).get("report_summary")
            ).get("total_records"),
        },
        "non_authority": {
            "winner_selection": False,
            "promotion_authority": False,
            "oracle_ranking": False,
        },
    }


def _build_evidence_matrix(records: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [_candidate_evidence_row(record) for record in records]
    source_kind_counts: dict[str, int] = {}
    for row in rows:
        behavior_sources = _mapping(row.get("behavior_sources"))
        for source_kind in behavior_sources.get("source_kinds", []) or []:
            key = str(source_kind)
            source_kind_counts[key] = source_kind_counts.get(key, 0) + 1
    return {
        "schema_version": PROGRAM_ARCHITECTURE_TOURNAMENT_EVIDENCE_MATRIX_SCHEMA,
        "status": "captured",
        "row_count": len(rows),
        "source_kind_counts": dict(sorted(source_kind_counts.items())),
        "rows": rows,
        "non_authority": {
            "evidence_summary_only": True,
            "raw_examples_included": False,
            "raw_outputs_included": False,
            "winner_selection": False,
            "promotion_authority": False,
            "oracle_ranking": False,
        },
    }


def _run_candidate_local_oracle(root: Path) -> dict[str, Any]:
    from dspx.services.program_oracle_index import index_program_oracle_evidence_path
    from dspx.services.program_oracle_report import build_program_oracle_evidence_report

    index_path = root / "oracle" / "coordinates.db"
    report_path = root / "program_oracle_report.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_result = index_program_oracle_evidence_path(
        root,
        index_path=index_path,
        limit=1000,
    )
    report = build_program_oracle_evidence_report(index_path=index_path, limit=1000)
    report_text = _json_text(report)
    report_path.write_text(report_text, encoding="utf-8")
    return {
        "status": "ok"
        if report.get("status") in {"ok", "no_program_oracle_evidence"}
        and not index_result.get("errors")
        else "degraded",
        "index_path": str(index_path),
        "index_hash": _content_hash(index_path),
        "report_path": str(report_path),
        "report_hash": sha256_text(report_text),
        "index_result": {
            "scanned": index_result.get("scanned"),
            "indexed": index_result.get("indexed"),
            "skipped": index_result.get("skipped"),
            "errors": index_result.get("errors"),
            "backend": index_result.get("backend"),
            "dimension": index_result.get("dimension"),
            "non_authority_confirmed": index_result.get("non_authority_confirmed"),
        },
        "report_summary": {
            "schema_version": report.get("schema_version"),
            "status": report.get("status"),
            "total_records": report.get("total_records"),
            "behavior_status_counts": report.get("behavior_status_counts"),
            "behavior_source_kind_counts": report.get("behavior_source_kind_counts"),
            "evidence_source_count": report.get("evidence_source_count"),
            "total_evaluation_count": report.get("total_evaluation_count"),
        },
        "non_authority": _mapping(report.get("non_authority")),
    }


def _candidate_record_from_artifact(
    *,
    plan_candidate: Mapping[str, Any],
    candidate_id: str,
    root: Path,
    intent_path: Path,
    candidate_local_oracle: bool = False,
) -> dict[str, Any]:
    manifest_path = root / "manifest.json"
    receipt_path = root / "manifest.json.meta.json"
    replay = check_run_receipt(receipt_path)
    manifest = _load_json(manifest_path)
    generated_files = list(manifest.get("generated_files") or [])
    receipt_bundle = dict(manifest.get("receipt_bundle") or {})
    candidate_assembly = dict(manifest.get("candidate_assembly") or {})
    oracle_payload = (
        _run_candidate_local_oracle(root) if candidate_local_oracle else None
    )
    record = {
        "candidate_id": candidate_id,
        "label": plan_candidate.get("label"),
        "family": plan_candidate.get("family"),
        "plan_recommendation": plan_candidate.get("recommendation"),
        "intent_path": str(intent_path),
        "intent_hash": _content_hash(intent_path),
        "root_path": str(root),
        "manifest_path": str(manifest_path),
        "manifest_hash": _content_hash(manifest_path),
        "receipt_path": str(receipt_path),
        "receipt_hash": _content_hash(receipt_path),
        "assembly_id": candidate_assembly.get("assembly_id"),
        "candidate_runtime_id": candidate_assembly.get("candidate_id"),
        "receipt_bundle_id": receipt_bundle.get("receipt_bundle_id"),
        "generated_file_count": len(generated_files),
        "module_surfaces_hash": _content_hash(root / "module_surfaces.json"),
        "capability_registry_hash": _content_hash(
            root / "program_capability_registry.json"
        ),
        "generated_module_policy_hash": _content_hash(
            root / "generated_module_policy.json"
        ),
        "topology_execution": manifest.get("topology_execution"),
        "replay_check": replay,
        "status": "replay_ok" if replay.get("status") == "ok" else "replay_failed",
    }
    if oracle_payload is not None:
        record["candidate_local_oracle"] = oracle_payload
    return record


def _skipped_record(*, candidate: Mapping[str, Any], reason: str) -> dict[str, Any]:
    candidate_id = _safe_candidate_id(candidate.get("candidate_id"))
    return {
        "candidate_id": candidate_id,
        "label": candidate.get("label"),
        "family": candidate.get("family"),
        "plan_recommendation": candidate.get("recommendation"),
        "status": "skipped",
        "reason": reason,
        "materialized": False,
        "replay_check": None,
    }


def _build_interpretation(records: list[dict[str, Any]]) -> dict[str, Any]:
    materialized = [record for record in records if record.get("status") != "skipped"]
    replay_ok = [
        record for record in materialized if record.get("status") == "replay_ok"
    ]
    needs_attention = [
        {
            "candidate_id": record.get("candidate_id"),
            "status": record.get("status"),
            "reason": record.get("reason"),
        }
        for record in records
        if record.get("status") not in {"replay_ok", "skipped"}
    ]
    return {
        "summary": "Architecture candidates were materialized and receipt-checked locally. No winner was selected.",
        "materialized_candidate_count": len(materialized),
        "replay_ok_count": len(replay_ok),
        "skipped_candidate_count": len(records) - len(materialized),
        "needs_attention": needs_attention,
    }


def preflight_program_architecture_tournament(
    *,
    architecture_plan: Mapping[str, Any],
    outdir: Path,
    candidate_ids: list[str] | None = None,
) -> set[str]:
    """Validate tournament inputs and output collisions without writing files."""

    _validate_architecture_plan(architecture_plan)
    selected_ids = _validated_selected_candidate_ids(
        architecture_plan=architecture_plan, candidate_ids=candidate_ids
    )
    root = outdir.expanduser().resolve()
    _preflight_tournament_outputs(
        root=root, architecture_plan=architecture_plan, selected_ids=selected_ids
    )
    return selected_ids


def run_program_architecture_tournament(
    *,
    architecture_plan: Mapping[str, Any],
    outdir: Path,
    candidate_ids: list[str] | None = None,
    source_plan_path: Path | None = None,
    candidate_local_oracle: bool = False,
) -> dict[str, Any]:
    """Materialize and replay-check materializable architecture candidates locally."""

    selected_ids = preflight_program_architecture_tournament(
        architecture_plan=architecture_plan,
        outdir=outdir,
        candidate_ids=candidate_ids,
    )
    root = _safe_outdir(outdir)
    intent_dir = root / "candidate_intents"
    intent_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    candidates = architecture_plan["candidates"]
    for raw_candidate in candidates:
        if not isinstance(raw_candidate, Mapping):
            raise ProgramArchitectureTournamentError(
                "architecture candidates must be objects"
            )
        candidate_id = _safe_candidate_id(raw_candidate.get("candidate_id"))
        if not _candidate_allowed(candidate_id, selected_ids):
            records.append(
                _skipped_record(candidate=raw_candidate, reason="filtered_out")
            )
            continue
        if raw_candidate.get("status") != "materializable":
            records.append(
                _skipped_record(
                    candidate=raw_candidate,
                    reason="candidate status is not materializable",
                )
            )
            continue
        intent_payload = raw_candidate.get("intent_payload")
        if not isinstance(intent_payload, Mapping):
            raise ProgramArchitectureTournamentError(
                f"materializable candidate lacks intent_payload: {candidate_id}"
            )
        target_dir = _candidate_dir(root, candidate_id)
        intent_path = intent_dir / f"{candidate_id}.json"
        intent_text = _json_text(dict(intent_payload))
        intent_path.write_text(intent_text, encoding="utf-8")
        artifact = materialize_program_from_intent(
            ProgramIntent.model_validate(dict(intent_payload)),
            outdir=target_dir,
        )
        records.append(
            _candidate_record_from_artifact(
                plan_candidate=raw_candidate,
                candidate_id=candidate_id,
                root=Path(artifact.root_path),
                intent_path=intent_path,
                candidate_local_oracle=candidate_local_oracle,
            )
        )
    evidence_matrix = _build_evidence_matrix(records)
    interpretation = _build_interpretation(records)
    materialized_count = interpretation["materialized_candidate_count"]
    replay_ok_count = interpretation["replay_ok_count"]
    if materialized_count == 0:
        status = "no_materializable_candidates"
    elif replay_ok_count == materialized_count:
        status = "materialized_and_replay_checked"
    else:
        status = "materialized_with_replay_failures"
    plan_hash = None
    plan_path_text = None
    if source_plan_path is not None:
        plan_path = source_plan_path.expanduser().resolve()
        plan_path_text = str(plan_path)
        plan_hash = _content_hash(plan_path)
    return {
        "schema_version": PROGRAM_ARCHITECTURE_TOURNAMENT_SCHEMA,
        "status": status,
        "created_from": {
            "architecture_plan_path": plan_path_text,
            "architecture_plan_hash": plan_hash,
            "architecture_plan_schema_version": architecture_plan.get("schema_version"),
            "architecture_plan_recommended_candidate_id": architecture_plan.get(
                "recommended_candidate_id"
            ),
        },
        "candidate_count": len(records),
        "materialized_candidate_count": materialized_count,
        "candidates": records,
        "evidence_matrix": evidence_matrix,
        "interpretation": interpretation,
        "effect": {
            "architecture_plan_built": False,
            "candidate_intents_materialized": True,
            "candidate_programs_materialized": materialized_count > 0,
            "receipts_replay_checked": materialized_count > 0,
            "tournament_sidecar_written": False,
            "oracle_index_mutated": bool(
                candidate_local_oracle and materialized_count > 0
            ),
            "oracle_index_scope": "candidate_local_explicit_paths"
            if candidate_local_oracle and materialized_count > 0
            else "none",
            "shared_oracle_mutated": False,
            "ak_called": False,
            "governance_mutated": False,
            "external_authority_mutated": False,
            "winner_selected": False,
            "promotion_applied": False,
        },
        "non_authority": {
            **_non_authority(),
            "local_architecture_tournament_only": True,
            "receipt_check_only": True,
        },
    }


def run_program_architecture_tournament_from_plan_path(
    architecture_plan_path: Path,
    *,
    outdir: Path,
    candidate_ids: list[str] | None = None,
    candidate_local_oracle: bool = False,
) -> dict[str, Any]:
    plan_path = architecture_plan_path.expanduser().resolve()
    plan = _load_json(plan_path)
    return run_program_architecture_tournament(
        architecture_plan=plan,
        outdir=outdir,
        candidate_ids=candidate_ids,
        source_plan_path=plan_path,
        candidate_local_oracle=candidate_local_oracle,
    )


def run_program_architecture_tournament_from_intent_path(
    intent_path: Path,
    *,
    outdir: Path,
    candidate_ids: list[str] | None = None,
    candidate_local_oracle: bool = False,
) -> dict[str, Any]:
    intent = load_program_intent(intent_path)
    plan = build_program_architecture_candidates(intent)
    return run_program_architecture_tournament(
        architecture_plan=plan,
        outdir=outdir,
        candidate_ids=candidate_ids,
        source_plan_path=None,
        candidate_local_oracle=candidate_local_oracle,
    )


def validate_program_architecture_tournament_output_path(
    out: Path, *, outdir: Path | None = None
) -> Path:
    """Validate the tournament sidecar output path before materialization."""

    target = _validate_output_path(out, label="architecture tournament")
    if outdir is not None:
        root = outdir.expanduser().resolve()
        if target == root or target in root.parents:
            raise ProgramArchitectureTournamentError(
                "architecture tournament sidecar path collides with tournament outdir: "
                f"{target}"
            )
        reserved_roots = [root / "candidate_intents", root / "candidates"]
        for reserved in reserved_roots:
            if target == reserved or reserved in target.parents:
                raise ProgramArchitectureTournamentError(
                    "architecture tournament sidecar path collides with internal tournament artifacts: "
                    f"{target}"
                )
    return target


def write_program_architecture_tournament_result(
    result: Mapping[str, Any], out: Path
) -> dict[str, Any]:
    target = _safe_output_path(out, label="architecture tournament")
    payload_without_artifact = dict(result)
    payload_without_artifact.pop("artifact", None)
    payload_without_artifact["effect"] = {
        **dict(payload_without_artifact.get("effect") or {}),
        "tournament_sidecar_written": True,
    }
    payload_hash = sha256_text(_json_text(payload_without_artifact))
    updated = dict(payload_without_artifact)
    updated["artifact"] = {
        "path": str(target),
        "payload_hash_excluding_artifact": payload_hash,
        "schema_version": PROGRAM_ARCHITECTURE_TOURNAMENT_SCHEMA,
    }
    target.write_text(_json_text(updated), encoding="utf-8")
    return updated

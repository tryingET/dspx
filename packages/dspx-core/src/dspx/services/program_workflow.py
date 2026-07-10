from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from dspx.coordinates import CoordinateStore
from dspx.services.program_candidate_state import (
    build_program_candidate_state,
    write_program_candidate_state,
)
from dspx.services.program_artifact_names import PROTECTED_PROGRAM_ARTIFACT_NAMES
from dspx.services.program_oracle_index import index_program_oracle_evidence_path
from dspx.services.program_oracle_publication import (
    validate_program_oracle_publication_preflight_contract,
    validate_program_oracle_publication_receipt_contract,
    publish_program_oracle_preflight,
    write_program_oracle_publication_receipt,
)
from dspx.services.program_oracle_publication_preflight import (
    build_program_oracle_publication_preflight,
    write_program_oracle_publication_preflight,
)
from dspx.services.program_intent import default_outdir, load_program_intent
from dspx.services.program_oracle_report import build_program_oracle_evidence_report
from dspx.services.program_service import run_generate_from_intent_path
from dspx.services.run_replay_service import check_run_receipt

PROGRAM_LOOP_SCHEMA = "program-loop-workflow-v2"

_FORBIDDEN_OUTPUT_NAMES = {
    *PROTECTED_PROGRAM_ARTIFACT_NAMES,
    "promotion_review_refined.json",
    "promotion_decision_record.json",
    "promotion_plan.json",
    "jury_results.json",
}


def _json_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _default_index_path(root: Path) -> Path:
    return root / "oracle" / "coordinates.db"


def _safe_rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return str(path)


def _required_text(value: object, *, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required when --publish-to-shared is set")
    return text


def _validate_sidecar_output_path(path: Path, *, label: str) -> Path:
    target = path.expanduser().resolve()
    if target.name in _FORBIDDEN_OUTPUT_NAMES:
        raise ValueError(f"{label} must not overwrite {target.name}")
    if target.exists() and target.is_dir():
        raise ValueError(f"{label} output path is a directory: {target}")
    return target


def _resolve_loop_output_paths(
    *,
    root: Path,
    oracle_report_out: Path | None,
    state_out: Path | None,
    workflow_out: Path | None,
    publication_preflight_out: Path | None,
    publication_receipt_out: Path | None,
) -> dict[str, Path]:
    return {
        "oracle_report_out": oracle_report_out.expanduser().resolve()
        if oracle_report_out
        else root / "program_oracle_report.json",
        "state_out": state_out.expanduser().resolve()
        if state_out
        else root / "program_candidate_state.json",
        "workflow_out": workflow_out.expanduser().resolve()
        if workflow_out
        else root / "program_loop.json",
        "publication_preflight_out": publication_preflight_out.expanduser().resolve()
        if publication_preflight_out
        else root / "program_oracle_publication_preflight.json",
        "publication_receipt_out": publication_receipt_out.expanduser().resolve()
        if publication_receipt_out
        else root / "program_oracle_publication_receipt.json",
    }


def _active_loop_sidecars(
    *, paths: Mapping[str, Path], skip_oracle_index: bool, publish_to_shared: str | None
) -> list[tuple[str, Path]]:
    active = [
        ("state_out", paths["state_out"]),
        ("workflow_out", paths["workflow_out"]),
    ]
    if not skip_oracle_index:
        active.append(("index_path", paths["index_path"]))
        active.append(("oracle_report_out", paths["oracle_report_out"]))
    if publish_to_shared is not None:
        active.extend(
            [
                ("publication_preflight_out", paths["publication_preflight_out"]),
                ("publication_receipt_out", paths["publication_receipt_out"]),
            ]
        )
    return active


def _preflight_loop_sidecar_outputs(
    *,
    root: Path,
    paths: Mapping[str, Path],
    skip_oracle_index: bool,
    publish_to_shared: str | None,
) -> None:
    generated_directories = [root]
    if not skip_oracle_index:
        generated_directories.append(root / "oracle")
    seen: dict[Path, str] = {}
    for label, path in _active_loop_sidecars(
        paths=paths,
        skip_oracle_index=skip_oracle_index,
        publish_to_shared=publish_to_shared,
    ):
        target = _validate_sidecar_output_path(path, label=label)
        for generated_directory in generated_directories:
            planned_dir = generated_directory.expanduser().resolve()
            if target == planned_dir or target in planned_dir.parents:
                raise ValueError(
                    f"{label} output path collides with generated program output directory: {target}"
                )
        for seen_target, seen_label in seen.items():
            if target == seen_target:
                raise ValueError(
                    f"{label} duplicates sidecar output path already used by {seen_label}: {target}"
                )
            if target in seen_target.parents or seen_target in target.parents:
                raise ValueError(
                    f"{label} conflicts with sidecar output path already used by {seen_label}: {target} vs {seen_target}"
                )
        seen[target] = label


def _workflow_behavior_evaluation(
    state_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Project canonical candidate-state behavior into workflow status evidence.

    Candidate state owns current-file/hash validation. The workflow prefers the
    aggregate behavior episode so dataset-only and multi-source failures cannot be
    hidden by a missing or passing inline-example result.
    """

    evidence_state = dict(state_payload.get("evidence_state") or {})
    behavior_episode = dict(evidence_state.get("behavior_episode") or {})
    behavior_results = dict(evidence_state.get("behavior") or {})
    created_from = dict(state_payload.get("created_from") or {})
    if behavior_episode.get("present") is True:
        source_kind = "behavior_episode"
        summary = behavior_episode
        path = created_from.get("behavior_episode_path")
    elif behavior_results.get("present") is True:
        source_kind = "behavior_results"
        summary = behavior_results
        path = created_from.get("behavior_results_path")
    else:
        source_kind = "none"
        summary = {
            "present": False,
            "status": "not_evaluated",
            "status_counts": {},
            "sha256": None,
        }
        path = None
    status = str(summary.get("status") or "unknown")
    return {
        "status": status,
        "passed": status == "passed",
        "source_kind": source_kind,
        "path": str(path) if path is not None else None,
        "sha256": summary.get("sha256"),
        "summary": summary,
    }


def write_program_loop_result(
    result: Mapping[str, Any], out_path: Path
) -> dict[str, Any]:
    """Write a local one-intent program loop workflow summary sidecar."""

    target = out_path.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(result)
    effect = dict(payload.get("effect") or {})
    effect["workflow_summary_written"] = True
    payload["effect"] = effect
    target.write_text(_json_text(payload), encoding="utf-8")
    return payload


def run_program_loop_from_intent_path(
    intent_path: Path,
    *,
    outdir: Path | None = None,
    index_path: Path | None = None,
    oracle_report_out: Path | None = None,
    state_out: Path | None = None,
    workflow_out: Path | None = None,
    skip_oracle_index: bool = False,
    publish_to_shared: str | None = None,
    publisher_id: str | None = None,
    publisher_role: str | None = None,
    publisher_assertion: str | None = None,
    redaction_status: str | None = None,
    retention_class: str | None = None,
    authority_ref: str | None = None,
    publisher_secret_refs: list[str] | None = None,
    publication_preflight_out: Path | None = None,
    publication_receipt_out: Path | None = None,
    shared_publication_store: CoordinateStore | None = None,
) -> dict[str, Any]:
    """Run the coherent local one-intent DSPx program loop.

    The loop intentionally composes already explicit local product surfaces:
    program materialization, receipt replay check, Oracle-readable evidence indexing,
    non-authoritative Oracle reporting, and local candidate-state summarization.
    It does not call AK, apply promotion, select winners, deploy, or mutate governance.
    """

    intent = load_program_intent(intent_path)
    root = (
        (outdir if outdir is not None else default_outdir(intent))
        .expanduser()
        .resolve()
    )
    resolved_index_path = (
        index_path.expanduser().resolve() if index_path else _default_index_path(root)
    )
    output_paths = _resolve_loop_output_paths(
        root=root,
        oracle_report_out=oracle_report_out,
        state_out=state_out,
        workflow_out=workflow_out,
        publication_preflight_out=publication_preflight_out,
        publication_receipt_out=publication_receipt_out,
    )
    output_paths["index_path"] = resolved_index_path
    _preflight_loop_sidecar_outputs(
        root=root,
        paths=output_paths,
        skip_oracle_index=skip_oracle_index,
        publish_to_shared=publish_to_shared,
    )
    if publish_to_shared is not None:
        _required_text(publish_to_shared, field="publish_to_shared")
        _required_text(publisher_id, field="publisher_id")
        _required_text(publisher_role, field="publisher_role")
        _required_text(publisher_assertion, field="publisher_assertion")
        _required_text(redaction_status, field="redaction_status")
        _required_text(retention_class, field="retention_class")
    resolved_oracle_report_out = output_paths["oracle_report_out"]
    resolved_state_out = output_paths["state_out"]
    resolved_workflow_out = output_paths["workflow_out"]
    resolved_publication_preflight_out = output_paths["publication_preflight_out"]
    resolved_publication_receipt_out = output_paths["publication_receipt_out"]

    artifact = run_generate_from_intent_path(intent_path, outdir=outdir)
    root = Path(artifact.root_path).expanduser().resolve()
    manifest_path = root / "manifest.json"
    receipt_path = Path(artifact.receipt_path or (root / "manifest.json.meta.json"))
    if not receipt_path.is_absolute():
        receipt_path = root / receipt_path
    receipt_path = receipt_path.expanduser().resolve()

    replay = check_run_receipt(receipt_path)

    oracle_index_result: dict[str, Any] | None = None
    oracle_report: dict[str, Any] | None = None
    if not skip_oracle_index:
        resolved_index_path.parent.mkdir(parents=True, exist_ok=True)
        oracle_index_result = index_program_oracle_evidence_path(
            root,
            index_path=resolved_index_path,
            limit=1000,
        )
        oracle_report = build_program_oracle_evidence_report(
            index_path=resolved_index_path,
            limit=1000,
        )
        resolved_oracle_report_out.parent.mkdir(parents=True, exist_ok=True)
        resolved_oracle_report_out.write_text(
            _json_text(oracle_report), encoding="utf-8"
        )

    publication_preflight_payload: dict[str, Any] | None = None
    publication_receipt_payload: dict[str, Any] | None = None
    if publish_to_shared is not None:
        publication_preflight = build_program_oracle_publication_preflight(
            manifest_path=manifest_path,
            target="shared-postgres",
            publication_label=_required_text(
                publish_to_shared,
                field="publish_to_shared",
            ),
            publisher_id=_required_text(publisher_id, field="publisher_id"),
            publisher_role=_required_text(publisher_role, field="publisher_role"),
            publisher_assertion=_required_text(
                publisher_assertion,
                field="publisher_assertion",
            ),
            redaction_status=_required_text(
                redaction_status,
                field="redaction_status",
            ),
            retention_class=_required_text(
                retention_class,
                field="retention_class",
            ),
            authority_ref=authority_ref,
            publisher_secret_refs=publisher_secret_refs,
        )
        publication_preflight_payload = write_program_oracle_publication_preflight(
            publication_preflight,
            resolved_publication_preflight_out,
        )
        publication_receipt = publish_program_oracle_preflight(
            preflight_path=resolved_publication_preflight_out,
            store=shared_publication_store,
        )
        publication_receipt_payload = write_program_oracle_publication_receipt(
            publication_receipt,
            resolved_publication_receipt_out,
        )
        manifest_hash = _sha256_file(manifest_path)
        validate_program_oracle_publication_preflight_contract(
            publication_preflight_payload,
            expected_manifest_path=manifest_path,
            expected_manifest_hash=manifest_hash,
            preflight_path=resolved_publication_preflight_out,
        )
        preflight_identity = publication_preflight_payload.get("identity")
        validate_program_oracle_publication_receipt_contract(
            publication_receipt_payload,
            expected_identities=(
                preflight_identity if isinstance(preflight_identity, Mapping) else {},
            ),
            preflight=publication_preflight_payload,
            preflight_sha256=_sha256_file(resolved_publication_preflight_out),
        )

    state = build_program_candidate_state(
        manifest_path=manifest_path,
        out_path=resolved_state_out,
        oracle_report_path=resolved_oracle_report_out
        if oracle_report is not None
        else None,
        oracle_publication_preflight_path=resolved_publication_preflight_out
        if publication_preflight_payload is not None
        else None,
        oracle_publication_receipt_path=resolved_publication_receipt_out
        if publication_receipt_payload is not None
        else None,
    )
    state_payload = write_program_candidate_state(state, resolved_state_out)

    behavior_evaluation = _workflow_behavior_evaluation(state_payload)
    behavior_status = str(behavior_evaluation["status"])
    behavior_passed = behavior_evaluation["passed"] is True

    generated_sidecars = [resolved_state_out]
    if oracle_report is not None:
        generated_sidecars.append(resolved_oracle_report_out)
    if publication_preflight_payload is not None:
        generated_sidecars.append(resolved_publication_preflight_out)
    if publication_receipt_payload is not None:
        generated_sidecars.append(resolved_publication_receipt_out)

    result: dict[str, Any] = {
        "schema_version": PROGRAM_LOOP_SCHEMA,
        "status": "ok"
        if replay.get("status") == "ok"
        and behavior_passed
        and state_payload.get("status")
        and (skip_oracle_index or (oracle_index_result or {}).get("errors") == 0)
        else "behavior_failed"
        if behavior_status == "failed"
        else "behavior_error"
        if behavior_status == "error"
        else "degraded",
        "intent_path": str(intent_path.expanduser().resolve()),
        "candidate": {
            "root_path": str(root),
            "manifest_path": str(manifest_path),
            "receipt_path": str(receipt_path),
            "assembly_id": artifact.metadata.get("assembly_id"),
            "candidate_id": artifact.metadata.get("candidate_id"),
            "receipt_bundle_id": artifact.metadata.get("receipt_bundle_id"),
        },
        "steps": {
            "program_gen": {
                "status": "ok",
                "materialization_status": "materialized",
                "manifest_path": _safe_rel(manifest_path, root),
                "generated_file_count": len(artifact.files),
            },
            "behavior_evaluation": behavior_evaluation,
            "replay_check": {
                "status": replay.get("status"),
                "receipt_path": str(receipt_path),
                "checks": replay.get("checks") or {},
            },
            "oracle_index": {
                "status": "skipped" if skip_oracle_index else "ok",
                "index_path": str(resolved_index_path),
                "result": oracle_index_result,
                "scope": "candidate_local_index_by_default",
            },
            "oracle_report": {
                "status": "skipped"
                if oracle_report is None
                else oracle_report.get("status"),
                "path": str(resolved_oracle_report_out)
                if oracle_report is not None
                else None,
                "summary": (oracle_report or {})
                .get("interpretation", {})
                .get("summary"),
            },
            "candidate_state": {
                "status": state_payload.get("status"),
                "path": str(resolved_state_out),
                "required_next_steps": (state_payload.get("truth_summary") or {}).get(
                    "required_next_steps"
                )
                or [],
            },
            "oracle_publication": {
                "status": "skipped"
                if publication_receipt_payload is None
                else publication_receipt_payload.get("status"),
                "preflight_path": str(resolved_publication_preflight_out)
                if publication_preflight_payload is not None
                else None,
                "receipt_path": str(resolved_publication_receipt_out)
                if publication_receipt_payload is not None
                else None,
                "publication_id": (publication_receipt_payload or {}).get(
                    "publication_id"
                ),
                "publication_label": (publication_receipt_payload or {})
                .get("publication", {})
                .get("publication_label"),
                "evidence_only": publication_receipt_payload is not None,
                "scope": "explicit_shared_publication_opt_in"
                if publication_receipt_payload is not None
                else "none",
            },
        },
        "next_actions": [
            "Inspect program_candidate_state.json for local truth and missing evidence.",
            "Use program-refine propose/review only when the Oracle report suggests a bounded evidence-backed refinement.",
            "Use program-promote activation-packet only after explicit governing authority, canonical binding, rollout owner, and rollback plan exist.",
        ],
        "generated_sidecars": [str(path) for path in generated_sidecars],
        "workflow_path": str(resolved_workflow_out),
        "effect": {
            "program_candidate_materialized": True,
            "replay_checked": True,
            "oracle_index_mutated": not skip_oracle_index,
            "oracle_index_scope": "candidate-local explicit path"
            if not skip_oracle_index
            else "none",
            "oracle_report_written": oracle_report is not None,
            "candidate_state_written": True,
            "oracle_publication_preflight_written": publication_preflight_payload
            is not None,
            "oracle_publication_receipt_written": publication_receipt_payload
            is not None,
            "shared_oracle_mutated": publication_receipt_payload is not None,
            "shared_oracle_publication_scope": "explicit opt-in"
            if publication_receipt_payload is not None
            else "none",
            "workflow_summary_written": False,
            "ak_called": False,
            "external_authority_mutated": False,
            "governance_mutated": False,
            "promotion_applied": False,
            "winner_selected": False,
        },
        "non_authority": {
            "workflow_summary_only": True,
            "oracle_interpretation_only": True,
            "apply_promotion": False,
            "external_apply": False,
            "agent_kernel_mutation": False,
            "governance_authority": False,
            "promotion_authority": False,
            "winner_selection": False,
            "automatic_promotion": False,
        },
    }
    return write_program_loop_result(result, resolved_workflow_out)

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from dspx.services.program_candidate_state import (
    build_program_candidate_state,
    write_program_candidate_state,
)
from dspx.services.program_oracle_index import index_program_oracle_evidence_path
from dspx.services.program_oracle_report import build_program_oracle_evidence_report
from dspx.services.program_service import run_generate_from_intent_path
from dspx.services.run_replay_service import check_run_receipt

PROGRAM_LOOP_SCHEMA = "program-loop-workflow-v1"


def _json_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _default_index_path(root: Path) -> Path:
    return root / "oracle" / "coordinates.db"


def _safe_rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return str(path)


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
) -> dict[str, Any]:
    """Run the coherent local one-intent DSPx program loop.

    The loop intentionally composes already explicit local product surfaces:
    program materialization, receipt replay check, Oracle-readable evidence indexing,
    non-authoritative Oracle reporting, and local candidate-state summarization.
    It does not call AK, apply promotion, select winners, deploy, or mutate governance.
    """

    artifact = run_generate_from_intent_path(intent_path, outdir=outdir)
    root = Path(artifact.root_path).expanduser().resolve()
    manifest_path = root / "manifest.json"
    receipt_path = Path(artifact.receipt_path or (root / "manifest.json.meta.json"))
    if not receipt_path.is_absolute():
        receipt_path = root / receipt_path
    receipt_path = receipt_path.expanduser().resolve()

    replay = check_run_receipt(receipt_path)

    resolved_index_path = (
        index_path.expanduser().resolve() if index_path else _default_index_path(root)
    )
    resolved_oracle_report_out = (
        oracle_report_out.expanduser().resolve()
        if oracle_report_out
        else root / "program_oracle_report.json"
    )
    resolved_state_out = (
        state_out.expanduser().resolve()
        if state_out
        else root / "program_candidate_state.json"
    )
    resolved_workflow_out = (
        workflow_out.expanduser().resolve()
        if workflow_out
        else root / "program_loop.json"
    )

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

    state = build_program_candidate_state(
        manifest_path=manifest_path,
        out_path=resolved_state_out,
        oracle_report_path=resolved_oracle_report_out
        if oracle_report is not None
        else None,
    )
    state_payload = write_program_candidate_state(state, resolved_state_out)

    generated_sidecars = [resolved_state_out]
    if oracle_report is not None:
        generated_sidecars.append(resolved_oracle_report_out)

    result: dict[str, Any] = {
        "schema_version": PROGRAM_LOOP_SCHEMA,
        "status": "ok"
        if replay.get("status") == "ok"
        and state_payload.get("status")
        and (skip_oracle_index or (oracle_index_result or {}).get("errors") == 0)
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
                "manifest_path": _safe_rel(manifest_path, root),
                "generated_file_count": len(artifact.files),
            },
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

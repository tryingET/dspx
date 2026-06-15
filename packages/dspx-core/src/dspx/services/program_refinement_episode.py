from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from dspx.services.artifact_boundary import prepare_sidecar_output_path
from dspx.services.program_candidate_state import (
    build_program_candidate_state,
    write_program_candidate_state,
)
from dspx.services.program_promotion_decision import (
    build_program_promotion_decision_record,
    write_program_promotion_decision_record,
)
from dspx.services.program_promotion_refinement import (
    build_program_promotion_refinement,
    write_program_promotion_refinement,
)
from dspx.services.program_refinement import (
    build_program_refinement_proposal,
    load_program_manifest,
    write_program_refinement_proposal,
)
from dspx.services.program_refinement_workflow import (
    materialize_and_compare_refinement_candidate,
)

PROGRAM_REFINEMENT_EPISODE_SCHEMA = "program-refinement-episode-v1"


class ProgramRefinementEpisodeError(ValueError):
    """Raised when a guided local refinement episode cannot safely run."""


def _json_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _safe_mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _safe_rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return str(path)


def _default_paths(sidecar_outdir: Path) -> dict[str, Path]:
    return {
        "proposal_out": sidecar_outdir / "refinement_proposal.json",
        "review_out": sidecar_outdir / "promotion_review_refined.json",
        "decision_out": sidecar_outdir / "promotion_decision_record.json",
        "comparison_out": sidecar_outdir / "program_candidate_comparison.json",
        "state_out": sidecar_outdir / "program_candidate_state.refinement.json",
        "workflow_out": sidecar_outdir / "program_refinement_episode.json",
        "second_candidate_outdir": sidecar_outdir / "second_candidate",
    }


def _resolved_output_paths(
    *,
    sidecar_outdir: Path,
    proposal_out: Path | None,
    review_out: Path | None,
    decision_out: Path | None,
    comparison_out: Path | None,
    state_out: Path | None,
    workflow_out: Path | None,
    second_candidate_outdir: Path | None,
) -> dict[str, Path]:
    sidecar_outdir = sidecar_outdir.expanduser().resolve()
    defaults = _default_paths(sidecar_outdir)
    return {
        "sidecar_outdir": sidecar_outdir,
        "proposal_out": proposal_out.expanduser().resolve()
        if proposal_out is not None
        else defaults["proposal_out"],
        "review_out": review_out.expanduser().resolve()
        if review_out is not None
        else defaults["review_out"],
        "decision_out": decision_out.expanduser().resolve()
        if decision_out is not None
        else defaults["decision_out"],
        "comparison_out": comparison_out.expanduser().resolve()
        if comparison_out is not None
        else defaults["comparison_out"],
        "state_out": state_out.expanduser().resolve()
        if state_out is not None
        else defaults["state_out"],
        "workflow_out": workflow_out.expanduser().resolve()
        if workflow_out is not None
        else defaults["workflow_out"],
        "second_candidate_outdir": second_candidate_outdir.expanduser().resolve()
        if second_candidate_outdir is not None
        else defaults["second_candidate_outdir"],
    }


def _assert_not_inside_source_root(
    path: Path, *, source_root: Path, label: str
) -> None:
    try:
        target = path.expanduser().resolve()
        root = source_root.expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise ProgramRefinementEpisodeError(f"{label} path cannot be resolved") from exc
    if target == root or root in target.parents:
        raise ProgramRefinementEpisodeError(
            f"{label} must not be inside the source generated program root: {target}"
        )


def _preflight_distinct_outputs(
    *,
    source_root: Path,
    paths: Mapping[str, Path],
    generate_second_candidate: bool,
) -> None:
    labels = [
        "proposal_out",
        "review_out",
        "decision_out",
        "state_out",
        "workflow_out",
    ]
    if generate_second_candidate:
        labels.append("comparison_out")
    seen: dict[Path, str] = {}
    for label in labels:
        target = paths[label].expanduser().resolve()
        _assert_not_inside_source_root(target, source_root=source_root, label=label)
        if target.exists() and target.is_dir():
            raise ProgramRefinementEpisodeError(
                f"{label} output path is a directory: {target}"
            )
        for seen_target, seen_label in seen.items():
            if target == seen_target:
                raise ProgramRefinementEpisodeError(
                    f"{label} duplicates sidecar output path already used by {seen_label}: {target}"
                )
            if target in seen_target.parents or seen_target in target.parents:
                raise ProgramRefinementEpisodeError(
                    f"{label} conflicts with sidecar output path already used by {seen_label}: {target} vs {seen_target}"
                )
        seen[target] = label
    if generate_second_candidate:
        candidate_root = paths["second_candidate_outdir"].expanduser().resolve()
        _assert_not_inside_source_root(
            candidate_root,
            source_root=source_root,
            label="second_candidate_outdir",
        )
        for sidecar_path, sidecar_label in seen.items():
            if (
                sidecar_path == candidate_root
                or candidate_root in sidecar_path.parents
                or sidecar_path in candidate_root.parents
            ):
                raise ProgramRefinementEpisodeError(
                    "second_candidate_outdir conflicts with sidecar output path "
                    f"{sidecar_label}: {candidate_root} vs {sidecar_path}"
                )


def write_program_refinement_episode_result(
    result: Mapping[str, Any],
    out_path: Path,
) -> dict[str, Any]:
    """Write the guided refinement episode summary sidecar."""

    payload = dict(result)
    validation_payload = dict(payload)
    validation_payload.pop("workflow_path", None)
    try:
        target = prepare_sidecar_output_path(
            out_path,
            payload=validation_payload,
            artifact_label="program refinement episode",
        )
    except ValueError as exc:
        raise ProgramRefinementEpisodeError(str(exc)) from exc
    target.parent.mkdir(parents=True, exist_ok=True)
    effect = _safe_mapping(payload.get("effect"))
    effect["workflow_summary_written"] = True
    payload["effect"] = effect
    target.write_text(_json_text(payload), encoding="utf-8")
    return payload


def run_program_refinement_episode(
    *,
    manifest_path: Path,
    oracle_report_path: Path,
    sidecar_outdir: Path,
    decision_outcome: str,
    decided_by: str,
    rationale: str,
    generate_second_candidate: bool = True,
    proposal_out: Path | None = None,
    review_out: Path | None = None,
    decision_out: Path | None = None,
    comparison_out: Path | None = None,
    state_out: Path | None = None,
    workflow_out: Path | None = None,
    second_candidate_outdir: Path | None = None,
) -> dict[str, Any]:
    """Run one local guided refinement episode over an existing candidate.

    The episode composes already explicit non-authoritative product seams: proposal,
    refined review, local decision record, optional request-more-evidence second
    candidate generation plus comparison, and refreshed local candidate state. It
    never calls AK, mutates governance, selects a winner, or applies promotion.
    """

    manifest_path = manifest_path.expanduser().resolve()
    oracle_report_path = oracle_report_path.expanduser().resolve()
    manifest = load_program_manifest(manifest_path)
    source_root = manifest_path.parent
    paths = _resolved_output_paths(
        sidecar_outdir=sidecar_outdir,
        proposal_out=proposal_out,
        review_out=review_out,
        decision_out=decision_out,
        comparison_out=comparison_out,
        state_out=state_out,
        workflow_out=workflow_out,
        second_candidate_outdir=second_candidate_outdir,
    )
    normalized_outcome = str(decision_outcome or "").strip()
    if generate_second_candidate and normalized_outcome != "request_more_evidence":
        raise ProgramRefinementEpisodeError(
            "second-candidate generation requires decision outcome request_more_evidence"
        )
    _preflight_distinct_outputs(
        source_root=source_root,
        paths=paths,
        generate_second_candidate=generate_second_candidate,
    )

    try:
        proposal = build_program_refinement_proposal(
            manifest_path=manifest_path,
            oracle_report_path=oracle_report_path,
        )
        proposal_payload = write_program_refinement_proposal(
            proposal,
            paths["proposal_out"],
        )

        review = build_program_promotion_refinement(
            manifest_path=manifest_path,
            oracle_report_path=oracle_report_path,
            refinement_proposal_path=paths["proposal_out"],
        )
        review_payload = write_program_promotion_refinement(
            review,
            paths["review_out"],
        )

        decision = build_program_promotion_decision_record(
            refined_review_path=paths["review_out"],
            outcome=normalized_outcome,
            decided_by=decided_by,
            rationale=rationale,
        )
        decision_payload = write_program_promotion_decision_record(
            decision,
            paths["decision_out"],
        )

        refinement_workflow: dict[str, Any] | None = None
        candidate_manifest_path: Path | None = None
        comparison_payload: dict[str, Any] | None = None
        if generate_second_candidate:
            refinement_workflow = materialize_and_compare_refinement_candidate(
                manifest_path=manifest_path,
                refinement_proposal_path=paths["proposal_out"],
                decision_record_path=paths["decision_out"],
                outdir=paths["second_candidate_outdir"],
                comparison_out_path=paths["comparison_out"],
            )
            candidate_manifest_path = (
                Path(
                    str(
                        _safe_mapping(
                            _safe_mapping(refinement_workflow.get("generation")).get(
                                "candidate"
                            )
                        ).get("manifest_path")
                        or ""
                    )
                )
                .expanduser()
                .resolve()
            )
            comparison_payload = _safe_mapping(
                refinement_workflow.get("comparison_sidecar")
            )

        state = build_program_candidate_state(
            manifest_path=manifest_path,
            out_path=paths["state_out"],
            oracle_report_path=oracle_report_path,
            refinement_proposal_path=paths["proposal_out"],
            review_path=paths["review_out"],
            decision_record_path=paths["decision_out"],
            comparison_path=paths["comparison_out"]
            if generate_second_candidate
            else None,
        )
        state_payload = write_program_candidate_state(state, paths["state_out"])
    except Exception as exc:
        if isinstance(exc, ProgramRefinementEpisodeError):
            raise
        raise ProgramRefinementEpisodeError(str(exc)) from exc

    comparison_status = (comparison_payload or {}).get("status")
    status = "decision_recorded"
    if generate_second_candidate:
        status = (
            "second_candidate_compared"
            if comparison_status == "compared"
            else "second_candidate_materialized_with_insufficient_behavior_evidence"
        )

    result = {
        "schema_version": PROGRAM_REFINEMENT_EPISODE_SCHEMA,
        "status": status,
        "created_from": {
            "manifest_path": str(manifest_path),
            "manifest_schema_version": manifest.get("schema_version"),
            "oracle_report_path": str(oracle_report_path),
        },
        "source_candidate": {
            "root_path": str(source_root),
            "manifest_path": str(manifest_path),
            "identity": _safe_mapping(state_payload.get("candidate_identity")),
        },
        "steps": {
            "refinement_proposal": {
                "status": proposal_payload.get("status"),
                "path": str(paths["proposal_out"]),
                "proposal_id": proposal_payload.get("proposal_id"),
            },
            "promotion_review_refined": {
                "status": review_payload.get("status"),
                "path": str(paths["review_out"]),
                "ready_for_adjudicator_review": _safe_mapping(
                    review_payload.get("review_readiness")
                ).get("ready_for_adjudicator_review"),
            },
            "decision_record": {
                "status": decision_payload.get("status"),
                "path": str(paths["decision_out"]),
                "outcome": decision_payload.get("outcome"),
                "promotion_state_after_decision": decision_payload.get(
                    "promotion_state_after_decision"
                ),
            },
            "second_candidate": {
                "status": "skipped"
                if not generate_second_candidate
                else _safe_mapping(refinement_workflow or {}).get("status"),
                "root_path": str(paths["second_candidate_outdir"])
                if generate_second_candidate
                else None,
                "manifest_path": str(candidate_manifest_path)
                if candidate_manifest_path is not None
                else None,
                "comparison_path": str(paths["comparison_out"])
                if generate_second_candidate
                else None,
                "comparison_status": comparison_status
                if generate_second_candidate
                else None,
            },
            "candidate_state": {
                "status": state_payload.get("status"),
                "path": str(paths["state_out"]),
                "required_next_steps": _safe_mapping(
                    state_payload.get("truth_summary")
                ).get("required_next_steps")
                or [],
            },
        },
        "generated_sidecars": [
            str(paths["proposal_out"]),
            str(paths["review_out"]),
            str(paths["decision_out"]),
            *([str(paths["comparison_out"])] if generate_second_candidate else []),
            str(paths["state_out"]),
        ],
        "workflow_path": str(paths["workflow_out"]),
        "next_actions": [
            "Inspect the refreshed candidate state and comparison sidecar before deciding whether more work is justified.",
            "Treat the decision record and comparison as local evidence only; they do not approve, rank, or activate a candidate.",
            "Use external authority/export/activation commands only after an owning authority, exact binding, duplicate checks, apply receipt, and rollback plan exist.",
        ],
        "effect": {
            "refinement_proposal_written": True,
            "promotion_review_refined_written": True,
            "decision_record_written": True,
            "local_second_candidate_generated": generate_second_candidate,
            "local_comparison_written": generate_second_candidate,
            "candidate_state_written": True,
            "workflow_summary_written": False,
            "source_program_files_mutated": False,
            "sidecar_inputs_mutated": False,
            "oracle_index_mutated": False,
            "ak_called": False,
            "external_authority_mutated": False,
            "governance_mutated": False,
            "promotion_applied": False,
            "winner_selected": False,
        },
        "non_authority": {
            "workflow_summary_only": True,
            "local_refinement_episode_only": True,
            "oracle_interpretation_only": True,
            "apply_promotion": False,
            "external_apply": False,
            "agent_kernel_mutation": False,
            "governance_authority": False,
            "promotion_authority": False,
            "oracle_authority": False,
            "winner_selection": False,
            "automatic_promotion": False,
        },
        "notes": [
            "This guided episode composes local non-authoritative refinement sidecars over existing candidate evidence.",
            "Second-candidate generation is allowed only for an explicit request_more_evidence decision outcome.",
            "The workflow does not call AK, mutate governance or external authority, select a winner, or apply promotion.",
        ],
        "paths_relative_to_sidecar_outdir": {
            key: _safe_rel(value, paths["sidecar_outdir"])
            for key, value in paths.items()
            if key != "sidecar_outdir"
        },
    }
    return write_program_refinement_episode_result(result, paths["workflow_out"])

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
from dspx.services.program_promotion_plan import (
    SUPPORTED_LOCAL_TARGETS,
    build_program_promotion_plan,
    write_program_promotion_plan,
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
    materialize_and_compare_gepa_refinement_candidate,
    materialize_and_compare_refinement_candidate,
)

PROGRAM_REFINEMENT_EPISODE_SCHEMA = "program-refinement-episode-v1"

_PROMOTION_PLAN_FORBIDDEN_OUTPUT_NAMES = frozenset(
    {
        "manifest.json",
        "manifest.json.meta.json",
        "program.py",
        "module.py",
        "signature.py",
        "eval_examples.py",
        "eval_behavior.py",
        "behavior_results.json",
        "behavior_episode.json",
        "oracle_evidence.json",
        "execution_episode.json",
    }
)


class ProgramRefinementEpisodeError(ValueError):
    """Raised when a guided local refinement episode cannot safely run."""


def _json_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _safe_mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _first_text(*values: object) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


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
        "promotion_plan_out": sidecar_outdir / "promotion_plan.json",
        "second_candidate_outdir": sidecar_outdir / "second_candidate",
        "gepa_candidate_outdir": sidecar_outdir / "gepa_candidate",
        "gepa_candidate_result_out": sidecar_outdir / "gepa_candidate_result.json",
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
    promotion_plan_out: Path | None,
    second_candidate_outdir: Path | None,
    gepa_candidate_outdir: Path | None,
    gepa_candidate_result_out: Path | None,
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
        "promotion_plan_out": promotion_plan_out.expanduser().resolve()
        if promotion_plan_out is not None
        else defaults["promotion_plan_out"],
        "second_candidate_outdir": second_candidate_outdir.expanduser().resolve()
        if second_candidate_outdir is not None
        else defaults["second_candidate_outdir"],
        "gepa_candidate_outdir": gepa_candidate_outdir.expanduser().resolve()
        if gepa_candidate_outdir is not None
        else defaults["gepa_candidate_outdir"],
        "gepa_candidate_result_out": gepa_candidate_result_out.expanduser().resolve()
        if gepa_candidate_result_out is not None
        else defaults["gepa_candidate_result_out"],
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
    generate_gepa_candidate: bool,
    generate_promotion_plan: bool,
    protected_inputs: Mapping[str, Path] | None = None,
) -> None:
    labels = [
        "proposal_out",
        "review_out",
        "decision_out",
        "state_out",
        "workflow_out",
    ]
    if generate_second_candidate or generate_gepa_candidate:
        labels.append("comparison_out")
    if generate_gepa_candidate:
        labels.append("gepa_candidate_result_out")
    if generate_promotion_plan:
        labels.append("promotion_plan_out")
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
        for input_label, input_path in (protected_inputs or {}).items():
            protected = input_path.expanduser().resolve()
            if (
                target == protected
                or target in protected.parents
                or protected in target.parents
            ):
                raise ProgramRefinementEpisodeError(
                    f"{label} output path must not overlap protected input {input_label}: {target} vs {protected}"
                )
        seen[target] = label
    candidate_roots: list[tuple[str, Path]] = []
    if generate_second_candidate:
        candidate_roots.append(
            ("second_candidate_outdir", paths["second_candidate_outdir"])
        )
    if generate_gepa_candidate:
        candidate_roots.append(
            ("gepa_candidate_outdir", paths["gepa_candidate_outdir"])
        )
    for candidate_label, candidate_path in candidate_roots:
        candidate_root = candidate_path.expanduser().resolve()
        _assert_not_inside_source_root(
            candidate_root,
            source_root=source_root,
            label=candidate_label,
        )
        for sidecar_path, sidecar_label in seen.items():
            if (
                sidecar_path == candidate_root
                or candidate_root in sidecar_path.parents
                or sidecar_path in candidate_root.parents
            ):
                raise ProgramRefinementEpisodeError(
                    f"{candidate_label} conflicts with sidecar output path "
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
    generate_promotion_plan: bool = False,
    promotion_plan_target: str | None = None,
    promotion_plan_authority_owner: str | None = None,
    promotion_plan_out: Path | None = None,
    gepa_result_path: Path | None = None,
    gepa_candidate_outdir: Path | None = None,
    gepa_candidate_result_out: Path | None = None,
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
        promotion_plan_out=promotion_plan_out,
        second_candidate_outdir=second_candidate_outdir,
        gepa_candidate_outdir=gepa_candidate_outdir,
        gepa_candidate_result_out=gepa_candidate_result_out,
    )
    normalized_outcome = str(decision_outcome or "").strip()
    normalized_plan_target = str(promotion_plan_target or "").strip()
    normalized_plan_owner = str(promotion_plan_authority_owner or "").strip()
    generate_gepa_candidate = gepa_result_path is not None
    generate_proposal_second_candidate = (
        generate_second_candidate and not generate_gepa_candidate
    )
    gepa_result_resolved = (
        gepa_result_path.expanduser().resolve()
        if gepa_result_path is not None
        else None
    )
    if generate_gepa_candidate and second_candidate_outdir is not None:
        raise ProgramRefinementEpisodeError(
            "second_candidate_outdir cannot be combined with --gepa-result; "
            "use gepa_candidate_outdir for the GEPA-backed candidate"
        )
    if (
        promotion_plan_target or promotion_plan_authority_owner or promotion_plan_out
    ) and not generate_promotion_plan:
        raise ProgramRefinementEpisodeError(
            "promotion plan options require --promotion-plan"
        )
    if (
        generate_proposal_second_candidate or generate_gepa_candidate
    ) and normalized_outcome != "request_more_evidence":
        raise ProgramRefinementEpisodeError(
            "local candidate generation requires decision outcome request_more_evidence"
        )
    if generate_promotion_plan:
        if not (generate_proposal_second_candidate or generate_gepa_candidate):
            raise ProgramRefinementEpisodeError(
                "promotion plan generation requires a second-candidate comparison"
            )
        if not normalized_plan_target:
            raise ProgramRefinementEpisodeError(
                "promotion plan generation requires promotion_plan_target"
            )
        if normalized_plan_target not in SUPPORTED_LOCAL_TARGETS:
            allowed = ", ".join(sorted(SUPPORTED_LOCAL_TARGETS))
            raise ProgramRefinementEpisodeError(
                "unsupported promotion_plan_target "
                f"{normalized_plan_target!r}; allowed targets: {allowed}"
            )
        if not normalized_plan_owner:
            raise ProgramRefinementEpisodeError(
                "promotion plan generation requires promotion_plan_authority_owner"
            )
        if paths["promotion_plan_out"].name in _PROMOTION_PLAN_FORBIDDEN_OUTPUT_NAMES:
            raise ProgramRefinementEpisodeError(
                "promotion_plan_out must not use a generated program/control artifact name: "
                f"{paths['promotion_plan_out'].name}"
            )
    _preflight_distinct_outputs(
        source_root=source_root,
        paths=paths,
        generate_second_candidate=generate_proposal_second_candidate,
        generate_gepa_candidate=generate_gepa_candidate,
        generate_promotion_plan=generate_promotion_plan,
        protected_inputs={"gepa_result": gepa_result_resolved}
        if gepa_result_resolved is not None
        else None,
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
        gepa_workflow: dict[str, Any] | None = None
        candidate_manifest_path: Path | None = None
        comparison_payload: dict[str, Any] | None = None
        promotion_plan_payload: dict[str, Any] | None = None
        if generate_proposal_second_candidate:
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
        elif generate_gepa_candidate:
            if gepa_result_resolved is None:
                raise ProgramRefinementEpisodeError("gepa_result_path is required")
            gepa_workflow = materialize_and_compare_gepa_refinement_candidate(
                manifest_path=manifest_path,
                gepa_result_path=gepa_result_resolved,
                outdir=paths["gepa_candidate_outdir"],
                comparison_out_path=paths["comparison_out"],
                gepa_candidate_result_out=paths["gepa_candidate_result_out"],
            )
            candidate_manifest_path = (
                Path(
                    str(
                        _safe_mapping(
                            _safe_mapping(gepa_workflow.get("generation")).get(
                                "candidate"
                            )
                        ).get("manifest_path")
                        or ""
                    )
                )
                .expanduser()
                .resolve()
            )
            comparison_payload = _safe_mapping(gepa_workflow.get("comparison_sidecar"))
        if generate_promotion_plan and candidate_manifest_path is not None:
            promotion_plan = build_program_promotion_plan(
                manifest_path=candidate_manifest_path,
                decision_record_path=paths["decision_out"],
                comparison_path=paths["comparison_out"],
                target=normalized_plan_target,
                authority_owner=normalized_plan_owner,
                review_path=paths["review_out"],
                source_manifest_path=manifest_path,
            )
            promotion_plan_payload = write_program_promotion_plan(
                promotion_plan,
                paths["promotion_plan_out"],
            )

        state_manifest_path = (
            candidate_manifest_path
            if (generate_promotion_plan or generate_gepa_candidate)
            and candidate_manifest_path is not None
            else manifest_path
        )
        state = build_program_candidate_state(
            manifest_path=state_manifest_path,
            out_path=paths["state_out"],
            source_manifest_path=manifest_path
            if state_manifest_path != manifest_path
            else None,
            oracle_report_path=oracle_report_path
            if state_manifest_path == manifest_path
            else None,
            refinement_proposal_path=paths["proposal_out"],
            review_path=paths["review_out"],
            decision_record_path=paths["decision_out"],
            comparison_path=paths["comparison_out"]
            if (generate_proposal_second_candidate or generate_gepa_candidate)
            else None,
            promotion_plan_path=paths["promotion_plan_out"]
            if generate_promotion_plan
            else None,
            gepa_refinement_path=gepa_result_resolved
            if generate_gepa_candidate
            else None,
        )
        state_payload = write_program_candidate_state(state, paths["state_out"])
    except Exception as exc:
        if isinstance(exc, ProgramRefinementEpisodeError):
            raise
        raise ProgramRefinementEpisodeError(str(exc)) from exc

    comparison_status = (comparison_payload or {}).get("status")
    status = "decision_recorded"
    if generate_promotion_plan:
        status = "local_promotion_plan_written"
    elif generate_gepa_candidate:
        status = (
            "gepa_candidate_compared"
            if comparison_status == "compared"
            else "gepa_candidate_materialized_with_insufficient_behavior_evidence"
        )
    elif generate_proposal_second_candidate:
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
            "identity": _identity_from_manifest(manifest),
        },
        "state_candidate": {
            "root_path": str(state_manifest_path.parent),
            "manifest_path": str(state_manifest_path),
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
                if not generate_proposal_second_candidate
                else _safe_mapping(refinement_workflow or {}).get("status"),
                "root_path": str(paths["second_candidate_outdir"])
                if generate_proposal_second_candidate
                else None,
                "manifest_path": str(candidate_manifest_path)
                if generate_proposal_second_candidate
                and candidate_manifest_path is not None
                else None,
                "comparison_path": str(paths["comparison_out"])
                if generate_proposal_second_candidate
                else None,
                "comparison_status": comparison_status
                if generate_proposal_second_candidate
                else None,
            },
            "gepa_candidate": {
                "status": "skipped"
                if not generate_gepa_candidate
                else _safe_mapping(gepa_workflow or {}).get("status"),
                "gepa_result_path": str(gepa_result_resolved)
                if generate_gepa_candidate
                else None,
                "root_path": str(paths["gepa_candidate_outdir"])
                if generate_gepa_candidate
                else None,
                "manifest_path": str(candidate_manifest_path)
                if generate_gepa_candidate and candidate_manifest_path is not None
                else None,
                "comparison_path": str(paths["comparison_out"])
                if generate_gepa_candidate
                else None,
                "comparison_status": comparison_status
                if generate_gepa_candidate
                else None,
                "candidate_result_path": str(paths["gepa_candidate_result_out"])
                if generate_gepa_candidate
                else None,
            },
            "promotion_plan": {
                "status": "skipped"
                if not generate_promotion_plan
                else (promotion_plan_payload or {}).get("status"),
                "path": str(paths["promotion_plan_out"])
                if generate_promotion_plan
                else None,
                "target": _safe_mapping(
                    (promotion_plan_payload or {}).get("target")
                ).get("kind")
                if generate_promotion_plan
                else None,
                "allowed_for_apply": _safe_mapping(
                    (promotion_plan_payload or {}).get("eligibility")
                ).get("allowed_for_apply")
                if generate_promotion_plan
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
            *(
                [str(paths["comparison_out"])]
                if (generate_proposal_second_candidate or generate_gepa_candidate)
                else []
            ),
            *(
                [str(paths["gepa_candidate_result_out"])]
                if generate_gepa_candidate
                else []
            ),
            *([str(paths["promotion_plan_out"])] if generate_promotion_plan else []),
            str(paths["state_out"]),
        ],
        "workflow_path": str(paths["workflow_out"]),
        "next_actions": [
            "Inspect the refreshed candidate state, comparison sidecar, and optional local promotion plan before deciding whether more work is justified.",
            "Treat the decision record, comparison, and promotion plan as local evidence only; they do not approve, rank, select, or activate a candidate.",
            "Use external authority/export/activation commands only after an owning authority, exact binding, duplicate checks, apply receipt, and rollback plan exist.",
        ],
        "effect": {
            "refinement_proposal_written": True,
            "promotion_review_refined_written": True,
            "decision_record_written": True,
            "local_second_candidate_generated": generate_proposal_second_candidate,
            "local_gepa_candidate_generated": generate_gepa_candidate,
            "local_comparison_written": generate_proposal_second_candidate
            or generate_gepa_candidate,
            "gepa_optimizer_output_mutated": False,
            "local_promotion_plan_written": generate_promotion_plan,
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
            "local_promotion_plan_only": generate_promotion_plan,
            "gepa_candidate_evidence_only": generate_gepa_candidate,
            "gepa_approval": False,
            "oracle_authority": False,
            "winner_selection": False,
            "automatic_promotion": False,
        },
        "notes": [
            "This guided episode composes local non-authoritative refinement sidecars over existing candidate evidence.",
            "Local candidate generation is allowed only for an explicit request_more_evidence decision outcome.",
            "A supplied GEPA result materializes one local GEPA-backed candidate and comparison; it is evidence, not approval.",
            "Optional promotion planning is local-only and keeps allowed_for_apply false.",
            "The workflow does not call AK, mutate governance or external authority, select a winner, or apply promotion.",
        ],
        "paths_relative_to_sidecar_outdir": {
            key: _safe_rel(value, paths["sidecar_outdir"])
            for key, value in paths.items()
            if key != "sidecar_outdir"
        },
    }
    return write_program_refinement_episode_result(result, paths["workflow_out"])

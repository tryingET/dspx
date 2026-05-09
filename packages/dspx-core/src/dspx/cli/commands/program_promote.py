from __future__ import annotations

import json
from pathlib import Path

import typer

app = typer.Typer(no_args_is_help=True)


@app.command("review")
def review(
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        help="Path to program-gen manifest.json",
    ),
    oracle_report: Path = typer.Option(
        ...,
        "--oracle-report",
        help="Path to explicit Oracle program-evidence report JSON",
    ),
    refinement_proposal: Path = typer.Option(
        ...,
        "--refinement-proposal",
        help="Path to explicit program refinement proposal JSON",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the refined local promotion-review packet should be written",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print review packet JSON"),
) -> None:
    """Build a refined local promotion-review packet without promotion authority."""
    from dspx.services.program_promotion_refinement import (
        ProgramPromotionRefinementError,
        build_program_promotion_refinement,
        write_program_promotion_refinement,
    )

    try:
        packet = build_program_promotion_refinement(
            manifest_path=manifest,
            oracle_report_path=oracle_report,
            refinement_proposal_path=refinement_proposal,
        )
        payload = write_program_promotion_refinement(packet, out)
    except ProgramPromotionRefinementError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(
            f"Error: program promotion review refinement failed: {exc}", err=True
        )
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(out.expanduser().resolve()))


@app.command("jury")
def jury(
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        help="Path to program-gen manifest.json",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the local jury results sidecar should be written",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print jury results JSON"),
) -> None:
    """Run local deterministic jury execution without promotion authority."""
    from dspx.services.program_jury_execution import (
        ProgramJuryExecutionError,
        build_program_jury_execution_result,
        write_program_jury_execution_result,
    )

    try:
        result = build_program_jury_execution_result(manifest_path=manifest)
        payload = write_program_jury_execution_result(result, out)
    except ProgramJuryExecutionError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"Error: program jury execution failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(out.expanduser().resolve()))


@app.command("plan")
def plan(
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        help="Path to candidate program-candidate-assembly-v1 manifest.json",
    ),
    decision_record: Path = typer.Option(
        ...,
        "--decision-record",
        help="Path to local program-promotion-decision-record-v1 JSON",
    ),
    comparison: Path = typer.Option(
        ...,
        "--comparison",
        help="Path to program-refinement-candidate-comparison-v1 JSON",
    ),
    target: str = typer.Option(
        ...,
        "--target",
        help="Local non-mutating target kind for the plan",
    ),
    authority_owner: str = typer.Option(
        ...,
        "--authority-owner",
        help="Explicit local operator/adjudication authority owner identifier",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the local promotion/adjudication plan should be written",
    ),
    review: Path | None = typer.Option(
        None,
        "--review",
        help="Optional program-promotion-review-refined-v1 JSON",
    ),
    source_manifest: Path | None = typer.Option(
        None,
        "--source-manifest",
        help="Optional source manifest used to verify comparison source identity",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print plan JSON"),
) -> None:
    """Build a local promotion/adjudication plan without applying promotion."""
    from dspx.services.program_promotion_plan import (
        ProgramPromotionPlanError,
        build_program_promotion_plan,
        write_program_promotion_plan,
    )

    try:
        plan_payload = build_program_promotion_plan(
            manifest_path=manifest,
            decision_record_path=decision_record,
            comparison_path=comparison,
            target=target,
            authority_owner=authority_owner,
            review_path=review,
            source_manifest_path=source_manifest,
        )
        payload = write_program_promotion_plan(plan_payload, out)
    except ProgramPromotionPlanError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"Error: program promotion planning failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(out.expanduser().resolve()))


@app.command("activation-packet")
def activation_packet(
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        help="Path to candidate program-candidate-assembly-v1 manifest.json",
    ),
    owning_domain: str = typer.Option(
        ...,
        "--owning-domain",
        help="Explicit governing domain accountable for this activation target",
    ),
    activation_target: str = typer.Option(
        ...,
        "--activation-target",
        help="Concrete production/material activation target being requested",
    ),
    authority_owner: str = typer.Option(
        ...,
        "--authority-owner",
        help="Domain governing body or delegated adjudicator identifier",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the activation evidence packet should be written",
    ),
    oracle_report: Path | None = typer.Option(
        None,
        "--oracle-report",
        help="Optional program-oracle-evidence-report-v1 JSON",
    ),
    jury_results: Path | None = typer.Option(
        None,
        "--jury-results",
        help="Optional program-jury-results-v1 JSON",
    ),
    review: Path | None = typer.Option(
        None,
        "--review",
        help="Optional program-promotion-review-refined-v1 JSON",
    ),
    decision_record: Path | None = typer.Option(
        None,
        "--decision-record",
        help="Optional program-promotion-decision-record-v1 JSON",
    ),
    promotion_plan: Path | None = typer.Option(
        None,
        "--promotion-plan",
        help="Optional program-promotion-plan-v1 JSON",
    ),
    oracle_publication_receipt: Path | None = typer.Option(
        None,
        "--oracle-publication-receipt",
        help="Optional program-oracle-shared-publication-receipt-v1 JSON evidence ref",
    ),
    canonical_binding_ref: str | None = typer.Option(
        None,
        "--canonical-binding-ref",
        help="Optional AK/current-authority binding ref; does not create that binding",
    ),
    rollout_owner: str | None = typer.Option(
        None,
        "--rollout-owner",
        help="Optional owner responsible for rollout execution",
    ),
    rollback_plan: str | None = typer.Option(
        None,
        "--rollback-plan",
        help="Optional rollback/deactivation plan summary",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print packet JSON"),
) -> None:
    """Write a non-authoritative production-activation evidence packet."""
    from dspx.services.program_activation_packet import (
        ProgramActivationPacketError,
        build_generated_program_activation_packet,
        write_generated_program_activation_packet,
    )

    try:
        packet = build_generated_program_activation_packet(
            manifest_path=manifest,
            owning_domain=owning_domain,
            activation_target=activation_target,
            authority_owner=authority_owner,
            oracle_report_path=oracle_report,
            jury_results_path=jury_results,
            review_path=review,
            decision_record_path=decision_record,
            promotion_plan_path=promotion_plan,
            oracle_publication_receipt_path=oracle_publication_receipt,
            canonical_binding_ref=canonical_binding_ref,
            rollout_owner=rollout_owner,
            rollback_plan=rollback_plan,
        )
        payload = write_generated_program_activation_packet(packet, out)
    except ProgramActivationPacketError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(
            f"Error: program activation packet generation failed: {exc}", err=True
        )
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(out.expanduser().resolve()))


@app.command("meta-adjudication-plan")
def meta_adjudication_plan(
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        help="Path to candidate program-candidate-assembly-v1 manifest.json",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the local meta-adjudication plan should be written",
    ),
    behavior_results: Path | None = typer.Option(
        None,
        "--behavior-results",
        help="Optional program-behavior-results-v1 JSON",
    ),
    behavior_episode: Path | None = typer.Option(
        None,
        "--behavior-episode",
        help="Optional program-behavior-episode-v1 JSON",
    ),
    oracle_report: Path | None = typer.Option(
        None,
        "--oracle-report",
        help="Optional program-oracle-evidence-report-v1 JSON",
    ),
    oracle_publication_receipt: Path | None = typer.Option(
        None,
        "--oracle-publication-receipt",
        help="Optional program-oracle-shared-publication-receipt-v1 JSON evidence ref",
    ),
    jury_results: Path | None = typer.Option(
        None,
        "--jury-results",
        help="Optional program-jury-results-v1 JSON",
    ),
    review: Path | None = typer.Option(
        None,
        "--review",
        help="Optional program-promotion-review-refined-v1 JSON",
    ),
    decision_record: Path | None = typer.Option(
        None,
        "--decision-record",
        help="Optional program-promotion-decision-record-v1 JSON",
    ),
    activation_packet: Path | None = typer.Option(
        None,
        "--activation-packet",
        help="Optional generated-cognition-program activation packet JSON",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print plan JSON"),
) -> None:
    """Plan target-sensitive jury/adjudicator orchestration without authority effects."""
    from dspx.services.program_meta_adjudication import (
        ProgramMetaAdjudicationError,
        build_program_meta_adjudication_plan,
        write_program_meta_adjudication_plan,
    )

    try:
        plan_payload = build_program_meta_adjudication_plan(
            manifest_path=manifest,
            behavior_results_path=behavior_results,
            behavior_episode_path=behavior_episode,
            oracle_report_path=oracle_report,
            oracle_publication_receipt_path=oracle_publication_receipt,
            jury_results_path=jury_results,
            review_path=review,
            decision_record_path=decision_record,
            activation_packet_path=activation_packet,
        )
        payload = write_program_meta_adjudication_plan(plan_payload, out)
    except ProgramMetaAdjudicationError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"Error: meta-adjudication planning failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(out.expanduser().resolve()))


@app.command("status")
def status(
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        help="Path to candidate program-candidate-assembly-v1 manifest.json",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the local candidate truth-state sidecar should be written",
    ),
    source_manifest: Path | None = typer.Option(
        None,
        "--source-manifest",
        help="Optional source manifest when the candidate state includes refinement lineage",
    ),
    oracle_report: Path | None = typer.Option(
        None,
        "--oracle-report",
        help="Optional program-oracle-evidence-report-v1 JSON",
    ),
    refinement_proposal: Path | None = typer.Option(
        None,
        "--refinement-proposal",
        help="Optional program-refinement-proposal-v1 JSON",
    ),
    review: Path | None = typer.Option(
        None,
        "--review",
        help="Optional program-promotion-review-refined-v1 JSON",
    ),
    decision_record: Path | None = typer.Option(
        None,
        "--decision-record",
        help="Optional program-promotion-decision-record-v1 JSON",
    ),
    jury_results: Path | None = typer.Option(
        None,
        "--jury-results",
        help="Optional program-jury-results-v1 JSON",
    ),
    comparison: Path | None = typer.Option(
        None,
        "--comparison",
        help="Optional program-refinement-candidate-comparison-v1 JSON",
    ),
    promotion_plan: Path | None = typer.Option(
        None,
        "--promotion-plan",
        help="Optional program-promotion-plan-v1 JSON",
    ),
    export_preflight: Path | None = typer.Option(
        None,
        "--export-preflight",
        help="Optional program-external-authority-export-preflight-v1 JSON",
    ),
    oracle_publication_receipt: Path | None = typer.Option(
        None,
        "--oracle-publication-receipt",
        help="Optional program-oracle-shared-publication-receipt-v1 JSON evidence ref",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print state JSON"),
) -> None:
    """Summarize the local truth state for one program candidate."""
    from dspx.services.program_candidate_state import (
        ProgramCandidateStateError,
        build_program_candidate_state,
        write_program_candidate_state,
    )

    try:
        state = build_program_candidate_state(
            manifest_path=manifest,
            out_path=out,
            source_manifest_path=source_manifest,
            oracle_report_path=oracle_report,
            refinement_proposal_path=refinement_proposal,
            review_path=review,
            decision_record_path=decision_record,
            jury_results_path=jury_results,
            comparison_path=comparison,
            promotion_plan_path=promotion_plan,
            export_preflight_path=export_preflight,
            oracle_publication_receipt_path=oracle_publication_receipt,
        )
        payload = write_program_candidate_state(state, out)
    except ProgramCandidateStateError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(
            f"Error: program candidate state summarization failed: {exc}", err=True
        )
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(out.expanduser().resolve()))


@app.command("decide")
def decide(
    review: Path = typer.Option(
        ...,
        "--review",
        help="Path to program-promotion-review-refined-v1 JSON",
    ),
    outcome: str = typer.Option(
        ...,
        "--outcome",
        help="Decision outcome: withhold, reject, request_more_evidence, or promote",
    ),
    decided_by: str = typer.Option(
        ...,
        "--decided-by",
        help="Explicit local operator/adjudicator identifier",
    ),
    rationale: str = typer.Option(
        ...,
        "--rationale",
        help="Non-empty rationale for the local decision record",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the local decision sidecar should be written",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print decision record JSON"),
) -> None:
    """Record a local adjudicator decision sidecar without promotion authority."""
    from dspx.services.program_promotion_decision import (
        ProgramPromotionDecisionError,
        build_program_promotion_decision_record,
        write_program_promotion_decision_record,
    )

    try:
        record = build_program_promotion_decision_record(
            refined_review_path=review,
            outcome=outcome,
            decided_by=decided_by,
            rationale=rationale,
        )
        payload = write_program_promotion_decision_record(record, out)
    except ProgramPromotionDecisionError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(
            f"Error: program promotion decision recording failed: {exc}", err=True
        )
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(out.expanduser().resolve()))

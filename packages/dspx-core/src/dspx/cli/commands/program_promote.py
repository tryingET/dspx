# summary: "Defines local program promotion-review, jury, adjudication, decision, and activation-evidence commands."
# read_when:
#   - "Changing generated-program review evidence, adjudicator workflows, candidate state, or activation readiness."

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
    model_jury_results: Path | None = typer.Option(
        None,
        "--model-jury-results",
        help="Optional provider-backed program-model-jury-results-v1 JSON",
    ),
    runtime_episode: Path | None = typer.Option(
        None,
        "--runtime-episode",
        help="Optional program-runtime-episode-v1 JSON from program-run; evidence only, not promotion authority",
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
            model_jury_results_path=model_jury_results,
            runtime_episode_path=runtime_episode,
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


@app.command("model-jury")
def model_jury(
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        help="Path to program-gen manifest.json",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the provider-backed model jury results sidecar should be written",
    ),
    evidence: list[Path] = typer.Option(
        [],
        "--evidence",
        help="Additional runtime/extraction evidence file or directory to include (repeatable)",
    ),
    provider: str | None = typer.Option(
        None,
        "--provider",
        help="Provider for juror model calls (defaults to explicit DSPX_PROVIDER; supported: stub)",
    ),
    adjudicator_id: str = typer.Option(
        "target_repo_product_manager_agent",
        "--adjudicator-id",
        help="Downstream adjudicator id to bind in the sidecar",
    ),
    adjudicator_kind: str = typer.Option(
        "target_repo_product_manager_agent",
        "--adjudicator-kind",
        help="Downstream adjudicator kind for product/domain review routing",
    ),
    adjudicator_repo: str | None = typer.Option(
        None,
        "--adjudicator-repo",
        help="Owning target repo for the downstream adjudicator, when known",
    ),
    max_jurors: int | None = typer.Option(
        None,
        "--max-jurors",
        help="Optional bounded number of selected jurors to execute",
    ),
    json_out: bool = typer.Option(
        False, "--json", help="Print model jury results JSON"
    ),
) -> None:
    """Run provider-backed model jury deliberation without promotion authority."""
    from dspx.cli.utils import ensure_env
    from dspx.services.program_model_jury_execution import (
        ProgramModelJuryExecutionError,
        build_program_model_jury_execution_result,
        preflight_program_model_jury_output_path,
        write_program_model_jury_execution_result,
    )

    try:
        preflight_program_model_jury_output_path(
            manifest_path=manifest, out_path=out, evidence_paths=evidence
        )
        ensure_env(provider)
        result = build_program_model_jury_execution_result(
            manifest_path=manifest,
            evidence_paths=evidence,
            provider=provider,
            adjudicator_id=adjudicator_id,
            adjudicator_kind=adjudicator_kind,
            adjudicator_repo=adjudicator_repo,
            max_jurors=max_jurors,
        )
        payload = write_program_model_jury_execution_result(result, out)
    except ProgramModelJuryExecutionError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(
            f"Error: provider-backed model jury execution failed: {exc}", err=True
        )
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


@app.command("canonical-binding-verification")
def canonical_binding_verification(
    canonical_binding_ref: str = typer.Option(
        ...,
        "--canonical-binding-ref",
        help="AK/current-authority binding ref, e.g. ak://decision/40#accepted",
    ),
    decision_record: Path = typer.Option(
        ...,
        "--decision-record",
        help="Path to program-promotion-decision-record-v1 JSON",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the canonical binding verification sidecar should be written",
    ),
    ak_bin: Path = typer.Option(
        Path("ak"),
        "--ak-bin",
        help="AK binary to use for read-only decision verification",
    ),
    ak_db: Path | None = typer.Option(
        None,
        "--ak-db",
        help="Optional AK database path",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print verification JSON"),
) -> None:
    """Verify an AK/current-authority binding ref without applying rollout."""
    from dspx.services.program_activation_packet import (
        ProgramActivationPacketError,
        build_canonical_binding_verification,
        write_canonical_binding_verification,
    )

    try:
        verification = build_canonical_binding_verification(
            canonical_binding_ref=canonical_binding_ref,
            decision_record_path=decision_record,
            ak_bin=ak_bin,
            ak_db=ak_db,
        )
        payload = write_canonical_binding_verification(verification, out)
    except ProgramActivationPacketError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"Error: canonical binding verification failed: {exc}", err=True)
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
        help="Optional program-jury-results-v2 JSON",
    ),
    model_jury_results: Path | None = typer.Option(
        None,
        "--model-jury-results",
        help="Optional provider-backed program-model-jury-results-v1 JSON",
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
    oracle_publication_preflight: Path | None = typer.Option(
        None,
        "--oracle-publication-preflight",
        help="Optional program-oracle-shared-publication-preflight-v1 JSON readiness evidence",
    ),
    oracle_publication_receipt: Path | None = typer.Option(
        None,
        "--oracle-publication-receipt",
        help="Optional program-oracle-shared-publication-receipt-v1 JSON evidence ref",
    ),
    candidate_state: Path | None = typer.Option(
        None,
        "--candidate-state",
        help="Optional program-candidate-state-v1 JSON status/admission evidence",
    ),
    generation_fitness_results: Path | None = typer.Option(
        None,
        "--generation-fitness-results",
        help="Optional gen-fitness-results-v1 JSON used to bind target-protocol adjudication evidence",
    ),
    program_evidence_adjudication: Path | None = typer.Option(
        None,
        "--program-evidence-adjudication",
        help="Optional program-evidence-adjudication-v1 JSON; local evidence only, not activation authority",
    ),
    export_preflight: Path | None = typer.Option(
        None,
        "--export-preflight",
        help="Optional program-external-authority-export-preflight-v1 JSON evidence; preflight only, not apply",
    ),
    obsidian_review_adapter_receipt: Path | None = typer.Option(
        None,
        "--obsidian-review-adapter-receipt",
        help="Optional dspy-pdf-transition review-adapter receipt JSON",
    ),
    canonical_binding_verification: Path | None = typer.Option(
        None,
        "--canonical-binding-verification",
        help="Optional program-canonical-binding-verification-v1 JSON",
    ),
    runtime_episode: Path | None = typer.Option(
        None,
        "--runtime-episode",
        help="Optional program-runtime-episode-v1 JSON from program-run; evidence only, not activation authority",
    ),
    require_obsidian_review_adapter: bool = typer.Option(
        False,
        "--require-obsidian-review-adapter",
        help="Require target-aware Obsidian review-adapter evidence before rollout readiness",
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
            model_jury_results_path=model_jury_results,
            review_path=review,
            decision_record_path=decision_record,
            promotion_plan_path=promotion_plan,
            oracle_publication_preflight_path=oracle_publication_preflight,
            oracle_publication_receipt_path=oracle_publication_receipt,
            candidate_state_path=candidate_state,
            generation_fitness_results_path=generation_fitness_results,
            program_evidence_adjudication_path=program_evidence_adjudication,
            external_authority_export_preflight_path=export_preflight,
            obsidian_review_adapter_receipt_path=obsidian_review_adapter_receipt,
            canonical_binding_verification_path=canonical_binding_verification,
            runtime_episode_path=runtime_episode,
            require_obsidian_review_adapter=require_obsidian_review_adapter,
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


@app.command("target-profile")
def target_profile(
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        help="Path to candidate program-candidate-assembly-v1 manifest.json",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the program-target-profile-v1 sidecar should be written",
    ),
    generation_target_contract: Path | None = typer.Option(
        None,
        "--generation-target-contract",
        help="Optional gen-target-contract-v1 JSON sidecar",
    ),
    generation_fitness_suite: Path | None = typer.Option(
        None,
        "--generation-fitness-suite",
        help="Optional gen-fitness-suite-v1 JSON sidecar",
    ),
    generation_gate_preflight: Path | None = typer.Option(
        None,
        "--generation-gate-preflight",
        help="Optional gen-generation-gate-preflight-v1 JSON sidecar",
    ),
    generation_traceability: Path | None = typer.Option(
        None,
        "--generation-traceability",
        help="Optional gen-traceability-v1 JSON sidecar",
    ),
    generation_fitness_results: Path | None = typer.Option(
        None,
        "--generation-fitness-results",
        help="Optional gen-fitness-results-v1 JSON sidecar",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print target profile JSON"),
) -> None:
    """Write a deterministic target profile sidecar without model calls."""
    from dspx.services.program_meta_adjudication import (
        ProgramMetaAdjudicationError,
        build_program_target_profile,
        write_program_target_profile,
    )

    try:
        profile = build_program_target_profile(
            manifest_path=manifest,
            generation_target_contract_path=generation_target_contract,
            generation_fitness_suite_path=generation_fitness_suite,
            generation_gate_preflight_path=generation_gate_preflight,
            generation_traceability_path=generation_traceability,
            generation_fitness_results_path=generation_fitness_results,
        )
        payload = write_program_target_profile(profile, out)
    except ProgramMetaAdjudicationError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"Error: target profile generation failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(out.expanduser().resolve()))


@app.command("jury-requirements")
def jury_requirements(
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the program-jury-requirements-v1 sidecar should be written",
    ),
    manifest: Path | None = typer.Option(
        None,
        "--manifest",
        help="Path to candidate manifest.json when deriving requirements directly",
    ),
    target_profile: Path | None = typer.Option(
        None,
        "--target-profile",
        help="Optional program-target-profile-v1 JSON sidecar to consume",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print jury requirements JSON"),
) -> None:
    """Write deterministic jury requirements from a target profile or manifest."""
    from dspx.services.program_meta_adjudication import (
        ProgramMetaAdjudicationError,
        build_program_jury_requirements,
        write_program_jury_requirements,
    )

    try:
        requirements = build_program_jury_requirements(
            manifest_path=manifest,
            target_profile_path=target_profile,
        )
        payload = write_program_jury_requirements(requirements, out)
    except ProgramMetaAdjudicationError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"Error: jury requirements generation failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(out.expanduser().resolve()))


@app.command("jury-panel")
def jury_panel(
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the program-meta-jury-selection-v1 sidecar should be written",
    ),
    jury_requirements: Path | None = typer.Option(
        None,
        "--jury-requirements",
        help="Optional program-jury-requirements-v1 JSON sidecar to consume",
    ),
    target_profile: Path | None = typer.Option(
        None,
        "--target-profile",
        help="Optional program-target-profile-v1 JSON sidecar to derive requirements",
    ),
    manifest: Path | None = typer.Option(
        None,
        "--manifest",
        help="Optional candidate manifest.json to derive requirements directly",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print jury panel JSON"),
) -> None:
    """Select a deterministic target-sensitive meta-jury panel."""
    from dspx.services.program_meta_adjudication import (
        ProgramMetaAdjudicationError,
        build_program_meta_jury_selection,
        write_program_meta_jury_selection,
    )

    try:
        selection = build_program_meta_jury_selection(
            manifest_path=manifest,
            target_profile_path=target_profile,
            jury_requirements_path=jury_requirements,
        )
        payload = write_program_meta_jury_selection(selection, out)
    except ProgramMetaAdjudicationError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"Error: jury panel selection failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(out.expanduser().resolve()))


@app.command("verify-jury-panel")
def verify_jury_panel(
    jury_selection: Path = typer.Option(
        ...,
        "--jury-selection",
        help="Path to program-meta-jury-selection-v1 JSON",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the program-jury-verification-v1 sidecar should be written",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print jury verification JSON"),
) -> None:
    """Verify a selected meta-jury panel without judging the program."""
    from dspx.services.program_meta_adjudication import (
        ProgramMetaAdjudicationError,
        build_program_jury_verification,
        write_program_jury_verification,
    )

    try:
        verification = build_program_jury_verification(
            jury_selection_path=jury_selection,
        )
        payload = write_program_jury_verification(verification, out)
    except ProgramMetaAdjudicationError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"Error: jury panel verification failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(out.expanduser().resolve()))


@app.command("adjudicator-formation")
def adjudicator_formation(
    jury_verification: Path = typer.Option(
        ...,
        "--jury-verification",
        help="Path to program-jury-verification-v1 JSON",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the program-adjudicator-formation-v1 sidecar should be written",
    ),
    jury_selection: Path | None = typer.Option(
        None,
        "--jury-selection",
        help="Optional program-meta-jury-selection-v1 JSON if not referenced by verification",
    ),
    json_out: bool = typer.Option(
        False, "--json", help="Print adjudicator formation JSON"
    ),
) -> None:
    """Form a deterministic program adjudicator from a verified jury panel."""
    from dspx.services.program_meta_adjudication import (
        ProgramMetaAdjudicationError,
        build_program_adjudicator_formation,
        write_program_adjudicator_formation,
    )

    try:
        formation = build_program_adjudicator_formation(
            jury_verification_path=jury_verification,
            jury_selection_path=jury_selection,
        )
        payload = write_program_adjudicator_formation(formation, out)
    except ProgramMetaAdjudicationError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"Error: program adjudicator formation failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(out.expanduser().resolve()))


@app.command("verify-program-adjudicator")
def verify_program_adjudicator(
    adjudicator_formation: Path = typer.Option(
        ...,
        "--adjudicator-formation",
        help="Path to program-adjudicator-formation-v1 JSON",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the program-adjudicator-verification-v1 sidecar should be written",
    ),
    json_out: bool = typer.Option(
        False, "--json", help="Print adjudicator verification JSON"
    ),
) -> None:
    """Verify a program adjudicator contract without judging program evidence."""
    from dspx.services.program_meta_adjudication import (
        ProgramMetaAdjudicationError,
        build_program_adjudicator_verification,
        write_program_adjudicator_verification,
    )

    try:
        verification = build_program_adjudicator_verification(
            adjudicator_formation_path=adjudicator_formation,
        )
        payload = write_program_adjudicator_verification(verification, out)
    except ProgramMetaAdjudicationError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"Error: program adjudicator verification failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(out.expanduser().resolve()))


@app.command("adjudicator-delegation")
def adjudicator_delegation(
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        help="Path to candidate manifest.json",
    ),
    adjudicator_verification: Path = typer.Option(
        ...,
        "--adjudicator-verification",
        help="Path to program-adjudicator-verification-v1 JSON",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the program-adjudicator-delegation-v1 sidecar should be written",
    ),
    json_out: bool = typer.Option(
        False, "--json", help="Print adjudicator delegation JSON"
    ),
) -> None:
    """Let DSPx/meta approve the generated-program adjudicator to decide locally."""
    from dspx.services.program_meta_adjudication import (
        ProgramMetaAdjudicationError,
        build_program_adjudicator_delegation,
        write_program_adjudicator_delegation,
    )

    try:
        delegation = build_program_adjudicator_delegation(
            manifest_path=manifest,
            adjudicator_verification_path=adjudicator_verification,
        )
        payload = write_program_adjudicator_delegation(delegation, out)
    except ProgramMetaAdjudicationError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"Error: program adjudicator delegation failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(out.expanduser().resolve()))


@app.command("evidence-adjudication")
def evidence_adjudication(
    adjudicator_verification: Path = typer.Option(
        ...,
        "--adjudicator-verification",
        help="Path to program-adjudicator-verification-v1 JSON",
    ),
    manifest: Path = typer.Option(
        ...,
        "--manifest",
        help="Path to candidate manifest.json",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the program-evidence-adjudication-v1 sidecar should be written",
    ),
    behavior_results: Path | None = typer.Option(
        None,
        "--behavior-results",
        help="Optional program-behavior-results-v1 JSON",
    ),
    behavior_episode: Path | None = typer.Option(
        None,
        "--behavior-episode",
        help="Optional program-behavior-episode-v1 JSON fallback",
    ),
    runtime_episode: Path | None = typer.Option(
        None,
        "--runtime-episode",
        help="Optional program-runtime-episode-v1 JSON from program-run; evidence only, not adjudication authority",
    ),
    oracle_report: Path | None = typer.Option(
        None,
        "--oracle-report",
        help="Optional program-oracle-evidence-report-v1 JSON",
    ),
    activation_packet: Path | None = typer.Option(
        None,
        "--activation-packet",
        help="Optional generated-cognition-program activation packet JSON",
    ),
    generation_traceability: Path | None = typer.Option(
        None,
        "--generation-traceability",
        help="Optional gen-traceability-v1 JSON sidecar",
    ),
    generation_fitness_results: Path | None = typer.Option(
        None,
        "--generation-fitness-results",
        help="Optional gen-fitness-results-v1 JSON sidecar",
    ),
    json_out: bool = typer.Option(
        False, "--json", help="Print evidence adjudication JSON"
    ),
) -> None:
    """Adjudicate program evidence with a verified deterministic program adjudicator."""
    from dspx.services.program_meta_adjudication import (
        ProgramMetaAdjudicationError,
        build_program_evidence_adjudication,
        write_program_evidence_adjudication,
    )

    try:
        adjudication = build_program_evidence_adjudication(
            adjudicator_verification_path=adjudicator_verification,
            manifest_path=manifest,
            behavior_results_path=behavior_results,
            behavior_episode_path=behavior_episode,
            runtime_episode_path=runtime_episode,
            oracle_report_path=oracle_report,
            activation_packet_path=activation_packet,
            generation_traceability_path=generation_traceability,
            generation_fitness_results_path=generation_fitness_results,
        )
        payload = write_program_evidence_adjudication(adjudication, out)
    except ProgramMetaAdjudicationError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"Error: program evidence adjudication failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(out.expanduser().resolve()))


@app.command("adjudication-behavior-trace")
def adjudication_behavior_trace(
    evidence_adjudication: Path = typer.Option(
        ...,
        "--evidence-adjudication",
        help="Path to program-evidence-adjudication-v1 JSON",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the program-adjudication-behavior-trace-v1 sidecar should be written",
    ),
    adjudicator_delegation: Path | None = typer.Option(
        None,
        "--adjudicator-delegation",
        help="Optional program-adjudicator-delegation-v1 JSON",
    ),
    decision_record: Path | None = typer.Option(
        None,
        "--decision-record",
        help="Optional generated-program adjudicator decision record JSON",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print behavior trace JSON"),
) -> None:
    """Write a local adjudication behavior trace for later explicit publication."""
    from dspx.services.program_meta_adjudication import (
        ProgramMetaAdjudicationError,
        build_program_adjudication_behavior_trace,
        write_program_adjudication_behavior_trace,
    )

    try:
        trace = build_program_adjudication_behavior_trace(
            evidence_adjudication_path=evidence_adjudication,
            adjudicator_delegation_path=adjudicator_delegation,
            decision_record_path=decision_record,
        )
        payload = write_program_adjudication_behavior_trace(trace, out)
    except ProgramMetaAdjudicationError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(f"Error: adjudication behavior trace failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(out.expanduser().resolve()))


@app.command("adjudication-gepa-example")
def adjudication_gepa_example(
    trace: Path = typer.Option(
        ...,
        "--trace",
        help="Path to program-adjudication-behavior-trace-v1 JSON",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the program-adjudication-gepa-example-v1 sidecar should be written",
    ),
    outcome_label: str | None = typer.Option(
        None,
        "--outcome-label",
        help="Optional later human/domain outcome label; omit to keep example pending",
    ),
    feedback: str | None = typer.Option(
        None,
        "--feedback",
        help="Optional feedback for GEPA metric training/validation",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print GEPA example JSON"),
) -> None:
    """Create a non-authoritative GEPA example from an adjudication trace."""
    from dspx.services.program_meta_adjudication import (
        ProgramMetaAdjudicationError,
        build_program_adjudication_gepa_example,
        write_program_adjudication_gepa_example,
    )

    try:
        example = build_program_adjudication_gepa_example(
            trace_path=trace,
            outcome_label=outcome_label,
            feedback=feedback,
        )
        payload = write_program_adjudication_gepa_example(example, out)
    except ProgramMetaAdjudicationError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(
            f"Error: adjudication GEPA example generation failed: {exc}", err=True
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
    runtime_episode: Path | None = typer.Option(
        None,
        "--runtime-episode",
        help="Optional program-runtime-episode-v1 JSON from program-run; evidence only, not adjudication authority",
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
        help="Optional program-jury-results-v2 JSON",
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
    generation_target_contract: Path | None = typer.Option(
        None,
        "--generation-target-contract",
        help="Optional gen-target-contract-v1 JSON sidecar",
    ),
    generation_fitness_suite: Path | None = typer.Option(
        None,
        "--generation-fitness-suite",
        help="Optional gen-fitness-suite-v1 JSON sidecar",
    ),
    generation_gate_preflight: Path | None = typer.Option(
        None,
        "--generation-gate-preflight",
        help="Optional gen-generation-gate-preflight-v1 JSON sidecar",
    ),
    generation_traceability: Path | None = typer.Option(
        None,
        "--generation-traceability",
        help="Optional gen-traceability-v1 JSON sidecar",
    ),
    generation_fitness_results: Path | None = typer.Option(
        None,
        "--generation-fitness-results",
        help="Optional gen-fitness-results-v1 JSON sidecar",
    ),
    program_adjudicator_delegation: Path | None = typer.Option(
        None,
        "--program-adjudicator-delegation",
        help="Optional program-adjudicator-delegation-v1 JSON",
    ),
    program_evidence_adjudication: Path | None = typer.Option(
        None,
        "--program-evidence-adjudication",
        help="Optional program-evidence-adjudication-v1 JSON",
    ),
    adjudication_behavior_trace: Path | None = typer.Option(
        None,
        "--adjudication-behavior-trace",
        help="Optional program-adjudication-behavior-trace-v1 JSON",
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
            runtime_episode_path=runtime_episode,
            oracle_report_path=oracle_report,
            oracle_publication_receipt_path=oracle_publication_receipt,
            jury_results_path=jury_results,
            review_path=review,
            decision_record_path=decision_record,
            activation_packet_path=activation_packet,
            generation_target_contract_path=generation_target_contract,
            generation_fitness_suite_path=generation_fitness_suite,
            generation_gate_preflight_path=generation_gate_preflight,
            generation_traceability_path=generation_traceability,
            generation_fitness_results_path=generation_fitness_results,
            program_adjudicator_delegation_path=program_adjudicator_delegation,
            program_evidence_adjudication_path=program_evidence_adjudication,
            adjudication_behavior_trace_path=adjudication_behavior_trace,
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
        help="Optional program-jury-results-v2 JSON",
    ),
    model_jury_results: Path | None = typer.Option(
        None,
        "--model-jury-results",
        help="Optional provider-backed program-model-jury-results-v1 JSON",
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
    meta_adjudication_plan: Path | None = typer.Option(
        None,
        "--meta-adjudication-plan",
        help="Optional program-meta-adjudication-plan-v1 JSON",
    ),
    activation_packet: Path | None = typer.Option(
        None,
        "--activation-packet",
        help="Optional generated-cognition-program-production-activation-packet-v1 JSON",
    ),
    oracle_publication_preflight: Path | None = typer.Option(
        None,
        "--oracle-publication-preflight",
        help="Optional program-oracle-shared-publication-preflight-v1 JSON readiness evidence",
    ),
    oracle_publication_receipt: Path | None = typer.Option(
        None,
        "--oracle-publication-receipt",
        help="Optional program-oracle-shared-publication-receipt-v1 JSON evidence ref",
    ),
    generation_gate_preflight: Path | None = typer.Option(
        None,
        "--generation-gate-preflight",
        help="Optional gen-generation-gate-preflight-v1 JSON sidecar",
    ),
    generation_fitness_results: Path | None = typer.Option(
        None,
        "--generation-fitness-results",
        help="Optional gen-fitness-results-v1 JSON sidecar",
    ),
    program_evidence_adjudication: Path | None = typer.Option(
        None,
        "--program-evidence-adjudication",
        help="Optional program-evidence-adjudication-v1 JSON sidecar",
    ),
    gepa_refinement: Path | None = typer.Option(
        None,
        "--gepa-refinement",
        help="Optional program-refinement-gepa-result-v1 JSON sidecar",
    ),
    runtime_episode: Path | None = typer.Option(
        None,
        "--runtime-episode",
        help="Optional program-runtime-episode-v1 JSON from program-run",
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
            model_jury_results_path=model_jury_results,
            comparison_path=comparison,
            promotion_plan_path=promotion_plan,
            export_preflight_path=export_preflight,
            meta_adjudication_plan_path=meta_adjudication_plan,
            activation_packet_path=activation_packet,
            oracle_publication_preflight_path=oracle_publication_preflight,
            oracle_publication_receipt_path=oracle_publication_receipt,
            generation_gate_preflight_path=generation_gate_preflight,
            generation_fitness_results_path=generation_fitness_results,
            program_evidence_adjudication_path=program_evidence_adjudication,
            gepa_refinement_path=gepa_refinement,
            runtime_episode_path=runtime_episode,
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


@app.command("generated-adjudicator-decision")
def generated_adjudicator_decision(
    evidence_adjudication: Path = typer.Option(
        ...,
        "--evidence-adjudication",
        help="Path to program-evidence-adjudication-v1 JSON",
    ),
    adjudicator_delegation: Path = typer.Option(
        ...,
        "--adjudicator-delegation",
        help="Path to program-adjudicator-delegation-v1 JSON",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the local generated-program adjudicator decision sidecar should be written",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print decision record JSON"),
) -> None:
    """Record the generated-program adjudicator decision after DSPx/meta delegation."""
    from dspx.services.program_promotion_decision import (
        ProgramPromotionDecisionError,
        build_generated_program_adjudicator_decision_record,
        write_program_promotion_decision_record,
    )

    try:
        record = build_generated_program_adjudicator_decision_record(
            evidence_adjudication_path=evidence_adjudication,
            adjudicator_delegation_path=adjudicator_delegation,
        )
        payload = write_program_promotion_decision_record(record, out)
    except ProgramPromotionDecisionError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(
            f"Error: generated-program adjudicator decision recording failed: {exc}",
            err=True,
        )
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(out.expanduser().resolve()))


@app.command("dspx-adjudicator-decision")
def dspx_adjudicator_decision(
    evidence_adjudication: Path = typer.Option(
        ...,
        "--evidence-adjudication",
        help="Path to program-evidence-adjudication-v1 JSON",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the local DSPx adjudicator decision sidecar should be written",
    ),
    decided_by: str = typer.Option(
        "dspx_program_adjudicator_v1",
        "--decided-by",
        help="DSPx adjudicator identifier for the local decision record",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print decision record JSON"),
) -> None:
    """Record a local DSPx adjudicator decision without promotion authority."""
    from dspx.services.program_promotion_decision import (
        ProgramPromotionDecisionError,
        build_dspx_adjudicator_decision_record,
        write_program_promotion_decision_record,
    )

    try:
        record = build_dspx_adjudicator_decision_record(
            evidence_adjudication_path=evidence_adjudication,
            decided_by=decided_by,
        )
        payload = write_program_promotion_decision_record(record, out)
    except ProgramPromotionDecisionError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(
            f"Error: DSPx adjudicator decision recording failed: {exc}", err=True
        )
        raise typer.Exit(code=2) from exc

    if json_out:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        typer.echo(str(out.expanduser().resolve()))


@app.command("decide-comparison")
def decide_comparison(
    comparison: Path = typer.Option(
        ...,
        "--comparison",
        help="Path to program-refinement-candidate-comparison-v1 JSON",
    ),
    outcome: str = typer.Option(
        ...,
        "--outcome",
        help="Comparison decision outcome: withhold, reject, or request_more_evidence",
    ),
    decided_by: str = typer.Option(
        ...,
        "--decided-by",
        help="Explicit local operator/adjudicator identifier",
    ),
    rationale: str = typer.Option(
        ...,
        "--rationale",
        help="Non-empty rationale for the local comparison decision record",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Path where the local comparison decision sidecar should be written",
    ),
    json_out: bool = typer.Option(False, "--json", help="Print decision record JSON"),
) -> None:
    """Record a local decision from comparison evidence without promotion authority."""
    from dspx.services.program_promotion_decision import (
        ProgramPromotionDecisionError,
        build_program_comparison_decision_record,
        write_program_promotion_decision_record,
    )

    try:
        record = build_program_comparison_decision_record(
            comparison_path=comparison,
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
            f"Error: program comparison decision recording failed: {exc}", err=True
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

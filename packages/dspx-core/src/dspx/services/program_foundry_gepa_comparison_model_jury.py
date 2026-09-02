"""Foundry-only model-jury execution over one receipt-bound provider runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from dspx.services import program_model_jury_execution as generic_jury
from dspx.services.program_model_jury_judgment import parse_model_judgment
from dspx.services.program_model_jury_provider_runtime import (
    ProgramModelJuryExecutionError,
    ProgramModelJuryProcessSlot,
    ProgramModelJuryProviderRuntimeBinding,
    run_program_model_jurors,
    validate_model_jury_process_slot,
)


def _run_closed_juror(
    *,
    juror: Mapping[str, Any],
    rubric: Mapping[str, Any],
    candidate_identity: Mapping[str, Any],
    evidence_json: str,
    adjudicator: Mapping[str, Any],
) -> dict[str, Any]:
    """Parse the raw model field before the generic parser can add defaults."""

    import dspy

    class FoundryProgramModelJurorSignature(dspy.Signature):
        """Judge bounded program evidence without promotion authority."""

        juror_json: str = dspy.InputField(
            desc="Selected juror id, perspective, model/provider metadata, and reason."
        )
        rubric_json: str = dspy.InputField(
            desc="Criteria and adversarial questions assigned to this juror."
        )
        candidate_identity_json: str = dspy.InputField(
            desc="Generated program candidate identity and schema facts."
        )
        evidence_json: str = dspy.InputField(
            desc="Behavior/runtime/extraction evidence to judge. Treat as evidence only."
        )
        adjudicator_json: str = dspy.InputField(
            desc="Downstream adjudicator context for recommendation routing only."
        )
        judgment_json: str = dspy.OutputField(
            desc=(
                "Return exactly one JSON object with exactly six keys and no extras: "
                "outcome (one of supports_review_evidence, withhold, reject, "
                "request_more_evidence); rationale (string); evidence_strengths, "
                "concerns, and improvement_requests (arrays of strings); confidence "
                "(one of low, medium, high, unknown). Do not claim promotion, "
                "activation, domain acceptance, external authority, or canonical mutation."
            )
        )

    pred = dspy.Predict(FoundryProgramModelJurorSignature)(
        juror_json=generic_jury._json_text(dict(juror)).strip(),
        rubric_json=generic_jury._json_text(dict(rubric)).strip(),
        candidate_identity_json=generic_jury._json_text(
            dict(candidate_identity)
        ).strip(),
        evidence_json=evidence_json,
        adjudicator_json=generic_jury._json_text(dict(adjudicator)).strip(),
    )
    raw = getattr(pred, "judgment_json", None)
    juror_id = str(juror.get("id") or juror.get("perspective") or "unknown")
    return parse_model_judgment(raw, juror_id=juror_id)


def build_foundry_program_model_jury_result(
    slot: ProgramModelJuryProcessSlot,
    *,
    manifest_path: Path,
    evidence_paths: Sequence[Path],
    provider: str,
    adjudicator_id: str,
    adjudicator_kind: str,
    adjudicator_repo: str | None,
    max_jurors: int | None,
    expected_input_sha256: Mapping[Path, str],
    provider_runtime_binding: ProgramModelJuryProviderRuntimeBinding,
) -> dict[str, Any]:
    """Run the task-local foundry jury without widening the generic public API."""

    validate_model_jury_process_slot(slot)
    manifest_path = manifest_path.expanduser().resolve()
    manifest, manifest_sha256 = generic_jury._load_manifest(manifest_path)
    jury, selection, rubric, jury_paths = generic_jury._load_jury_artifacts(
        manifest_path, manifest
    )
    selected = [
        item
        for item in generic_jury._safe_list(selection.get("selected_jurors"))
        if isinstance(item, Mapping)
    ]
    if max_jurors is not None:
        selected = selected[: max(0, int(max_jurors))]
    if not selected:
        raise ProgramModelJuryExecutionError(
            "jury selection contains no selected jurors"
        )
    rubrics = {
        str(item.get("juror_id")): dict(item)
        for item in generic_jury._safe_list(rubric.get("juror_rubrics"))
        if isinstance(item, Mapping)
    }
    extra_entries = generic_jury._load_extra_evidence(evidence_paths)
    if not extra_entries:
        raise ProgramModelJuryExecutionError(
            "model jury requires at least one receipt-bound evidence path"
        )
    observed_input_hashes = {
        manifest_path: manifest_sha256,
        Path(jury_paths["jury_path"]): jury_paths["jury_sha256"],
        Path(jury_paths["jury_selection_path"]): jury_paths["jury_selection_sha256"],
        Path(jury_paths["jury_rubric_path"]): jury_paths["jury_rubric_sha256"],
        **{Path(str(entry["path"])): str(entry["sha256"]) for entry in extra_entries},
    }
    expected = {
        path.expanduser().resolve(): str(digest)
        for path, digest in expected_input_sha256.items()
    }
    if observed_input_hashes != expected:
        raise ProgramModelJuryExecutionError(
            "model jury input snapshots do not match the expected receipt-bound bytes"
        )

    identity = generic_jury._identity_from_manifest(manifest)
    candidate_identity = {
        "schema_version": manifest.get("schema_version"),
        "identity": identity,
        "candidate_assembly": generic_jury._safe_mapping(
            manifest.get("candidate_assembly")
        ),
    }
    adjudicator = {
        "id": adjudicator_id,
        "kind": adjudicator_kind,
        "repo": adjudicator_repo,
        "authority": "downstream_domain_review_recommendation_only",
        "promotion_authority": False,
    }
    evidence_json = generic_jury._bounded_evidence_for_prompt(extra_entries)
    provider_config, juror_results, provider_outcome_evidence = (
        run_program_model_jurors(
            selected=selected,
            rubrics=rubrics,
            candidate_identity=candidate_identity,
            evidence_json=evidence_json,
            adjudicator=adjudicator,
            provider=provider,
            configure_provider=generic_jury._configure_provider,
            run_juror=_run_closed_juror,
            sanitize_diagnostic=generic_jury._sanitize_model_jury_diagnostic,
            provider_runtime_binding=provider_runtime_binding,
        )
    )
    aggregate = generic_jury._aggregate(juror_results)
    return {
        "schema_version": generic_jury.PROGRAM_MODEL_JURY_RESULTS_SCHEMA,
        "status": "executed_with_failures"
        if aggregate["judgment_counts"]["failed"]
        else "executed",
        "identity": identity,
        "created_from": {
            "manifest_path": str(manifest_path),
            "manifest_sha256": manifest_sha256,
            "manifest_schema_version": manifest.get("schema_version"),
            **jury_paths,
            "evidence_paths": [
                str(path.expanduser().resolve()) for path in evidence_paths
            ],
        },
        "jury": {
            "planned_jury_schema_version": jury.get("schema_version"),
            "selection_schema_version": selection.get("schema_version"),
            "rubric_schema_version": rubric.get("schema_version"),
            "selected_juror_count": len(selected),
            "selected_perspectives": [
                str(item.get("perspective")) for item in selected
            ],
            "execution_mode": "provider_backed_model",
            "provider_backed_model_calls": True,
            "provider_config": provider_config,
            "provider_outcome_evidence": provider_outcome_evidence,
        },
        "adjudicator": adjudicator,
        "evidence": {
            "default_behavior": {
                "present": False,
                "entry_count": 0,
                "kinds": [],
            },
            "extra_evidence_count": len(extra_entries),
            "entry_count": len(extra_entries),
            "entries": [
                {
                    key: entry.get(key)
                    for key in (
                        "kind",
                        "path",
                        "sha256",
                        "schema_version",
                        "summary",
                    )
                }
                for entry in extra_entries
            ],
            "prompt_sha256": generic_jury._sha256_text(evidence_json),
        },
        "juror_results": juror_results,
        "aggregate": aggregate,
        "interpretation": {
            "summary": "Model-backed jury results are review evidence only and may request extraction refinement.",
            "ready_for_promotion_decision": False,
            "next_step": "Route aggregate critique to the declared target-repo adjudicator or run an explicit refinement pass.",
            "limits": [
                "This command calls provider-backed juror models but does not mutate generated program outputs.",
                "It does not improve files in place; improvement_requests are explicit follow-up evidence.",
                "It does not promote, activate, rank winners, export authority, mutate AK, or mutate governance.",
            ],
        },
        "effect": dict(generic_jury._EFFECT),
        "non_authority": dict(generic_jury._NON_AUTHORITY),
    }


def build_comparison_model_jury_result(
    slot: ProgramModelJuryProcessSlot,
    *,
    manifest_path: Path,
    evidence_paths: Sequence[Path],
    provider: str,
    adjudicator_id: str,
    adjudicator_kind: str,
    adjudicator_repo: str | None,
    max_jurors: int | None,
    expected_input_sha256: Mapping[Path, str],
    provider_runtime_binding: ProgramModelJuryProviderRuntimeBinding | None,
) -> dict[str, Any]:
    """Route generic execution or the sealed foundry-only backend path."""

    validate_model_jury_process_slot(slot)
    if provider_runtime_binding is None:
        return generic_jury.build_program_model_jury_execution_result(
            manifest_path=manifest_path,
            evidence_paths=evidence_paths,
            provider=provider,
            adjudicator_id=adjudicator_id,
            adjudicator_kind=adjudicator_kind,
            adjudicator_repo=adjudicator_repo,
            max_jurors=max_jurors,
            expected_input_sha256=expected_input_sha256,
            include_default_behavior=False,
        )
    return build_foundry_program_model_jury_result(
        slot,
        manifest_path=manifest_path,
        evidence_paths=evidence_paths,
        provider=provider,
        adjudicator_id=adjudicator_id,
        adjudicator_kind=adjudicator_kind,
        adjudicator_repo=adjudicator_repo,
        max_jurors=max_jurors,
        expected_input_sha256=expected_input_sha256,
        provider_runtime_binding=provider_runtime_binding,
    )


__all__ = [
    "build_comparison_model_jury_result",
    "build_foundry_program_model_jury_result",
]

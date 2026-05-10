from __future__ import annotations

from typing import Any, Mapping
import keyword
import re

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _sanitize_ident(name: str, fallback: str = "IntentProgram") -> str:
    value = re.sub(r"\W+", "_", str(name or "").strip()) or fallback
    if value[0].isdigit():
        value = f"_{value}"
    if keyword.iskeyword(value):
        value = f"{value}_"
    return value


def string_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def jury_options(intent: Any) -> dict[str, Any]:
    if intent.jury:
        return dict(intent.jury)
    raw_options_jury = (
        intent.options.get("jury") if isinstance(intent.options, Mapping) else None
    )
    return dict(raw_options_jury) if isinstance(raw_options_jury, Mapping) else {}


def normalize_jurors(raw_jurors: Any) -> list[dict[str, Any]]:
    jurors: list[dict[str, Any]] = []
    if not isinstance(raw_jurors, list):
        return jurors
    for index, raw in enumerate(raw_jurors):
        if isinstance(raw, str):
            model = raw.strip()
            if not model:
                continue
            jurors.append(
                {
                    "id": _sanitize_ident(model, fallback=f"juror_{index + 1}"),
                    "model": model,
                    "perspective": "unspecified",
                    "source": "explicit_user",
                }
            )
            continue
        if not isinstance(raw, Mapping):
            continue
        item = dict(raw)
        model = str(item.get("model") or item.get("name") or "").strip()
        perspective = str(
            item.get("perspective") or item.get("role") or "unspecified"
        ).strip()
        juror_id = str(
            item.get("id")
            or _sanitize_ident(model or perspective, fallback=f"juror_{index + 1}")
        ).strip()
        juror = {
            "id": juror_id,
            "model": model or None,
            "perspective": perspective or "unspecified",
            "source": str(item.get("source") or "explicit_user"),
        }
        if item.get("provider") is not None:
            juror["provider"] = str(item["provider"])
        if item.get("weight") is not None:
            juror["weight"] = item["weight"]
        if item.get("reason") is not None:
            juror["reason"] = str(item["reason"])
        jurors.append(juror)
    return jurors


def intent_text_for_jury(intent: Any) -> str:
    parts = [intent.name, intent.objective, intent.task_type, intent.metric or ""]
    parts.extend(intent.constraints or [])
    parts.extend(intent.inputs or [])
    parts.extend(intent.outputs or [])
    return " ".join(str(part) for part in parts).lower()


def inferred_juror(perspective: str, reason: str) -> dict[str, Any]:
    return {
        "id": f"inferred_{_sanitize_ident(perspective).lower()}",
        "model": None,
        "perspective": perspective,
        "source": "inferred_from_intent",
        "reason": reason,
    }


def explicit_perspective_juror(perspective: str) -> dict[str, Any]:
    return {
        "id": f"explicit_{_sanitize_ident(perspective).lower()}",
        "model": None,
        "perspective": perspective,
        "source": "explicit_perspective",
        "reason": "declared in jury.perspectives without a bound juror model",
    }


def infer_program_jury_pool(intent: Any) -> list[dict[str, Any]]:
    """Infer a program-specific jury pool from deterministic intent features."""

    text = intent_text_for_jury(intent)
    jurors = [
        inferred_juror("correctness", "baseline behavior correctness coverage"),
        inferred_juror("robustness", "baseline edge-case and failure-mode coverage"),
        inferred_juror(
            "instruction_following",
            "baseline objective and instruction adherence coverage",
        ),
    ]
    if intent.examples:
        jurors.append(
            inferred_juror(
                "example_generalization",
                "examples are present, so held-out/generalization behavior matters",
            )
        )
    if intent.metric:
        metric = intent.metric.lower()
        if "exact" in metric:
            jurors.append(
                inferred_juror(
                    "answer_equivalence",
                    "exact-match metrics need strict answer-equivalence critique",
                )
            )
        if "accuracy" in metric or "class" in metric:
            jurors.append(
                inferred_juror(
                    "label_boundary",
                    "classification/accuracy metrics need boundary-case critique",
                )
            )
    if any(name in intent.outputs for name in ("confidence", "score", "probability")):
        jurors.append(
            inferred_juror(
                "calibration", "confidence-like outputs require calibration critique"
            )
        )
    if any(token in text for token in ("context", "cite", "citation", "source", "rag")):
        jurors.append(
            inferred_juror(
                "grounding", "context/source/citation cues require grounding critique"
            )
        )
    if intent.constraints:
        jurors.append(
            inferred_juror(
                "constraint_adherence",
                "declared constraints require adversarial checking",
            )
        )
    return jurors


def merge_jury_pool(
    explicit_jurors: list[dict[str, Any]], inferred_jurors: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen_perspectives: set[str] = set()
    for juror in [*explicit_jurors, *inferred_jurors]:
        perspective = str(juror.get("perspective") or "unspecified")
        if perspective in seen_perspectives:
            continue
        merged.append(dict(juror))
        seen_perspectives.add(perspective)
    return merged


def jury_plan_defaults(intent: Any) -> dict[str, Any]:
    options = jury_options(intent)
    explicit_jurors = normalize_jurors(options.get("jurors"))
    explicit_perspectives = string_list(options.get("perspectives"))
    explicit_juror_perspectives = {
        str(juror.get("perspective") or "")
        for juror in explicit_jurors
        if str(juror.get("perspective") or "").strip()
    }
    explicit_perspective_jurors = [
        explicit_perspective_juror(perspective)
        for perspective in explicit_perspectives
        if perspective not in explicit_juror_perspectives
    ]
    inferred_jurors = infer_program_jury_pool(intent)
    jurors = merge_jury_pool(
        [*explicit_jurors, *explicit_perspective_jurors], inferred_jurors
    )
    juror_perspectives = [
        str(juror["perspective"])
        for juror in jurors
        if juror.get("perspective") and juror.get("perspective") != "unspecified"
    ]
    perspectives = explicit_perspectives or sorted(set(juror_perspectives))
    selection_constraints = options.get("selection_constraints")
    if not isinstance(selection_constraints, Mapping):
        selection_constraints = {
            "prefer_diverse_models": True,
            "prefer_diverse_perspectives": True,
        }
    return {
        "schema_version": "program-jury-v1",
        "mode": "jury",
        "status": "planned_not_executed",
        "selection_model": str(
            options.get("selection_model") or "perspective_balanced_explicit_pool"
        ),
        "minimum_jurors": int(options.get("minimum_jurors") or 3),
        "jurors": jurors,
        "pool": {
            "scope": "program",
            "explicit_juror_count": len(explicit_jurors),
            "explicit_perspective_count": len(explicit_perspectives),
            "explicit_perspective_juror_count": len(explicit_perspective_jurors),
            "inferred_juror_count": len(inferred_jurors),
            "merged_juror_count": len(jurors),
            "inference_basis": [
                "intent.name",
                "intent.objective",
                "intent.task_type",
                "intent.metric",
                "intent.inputs",
                "intent.outputs",
                "intent.constraints",
                "intent.examples",
            ],
        },
        "perspectives": perspectives,
        "selection_constraints": dict(selection_constraints),
        "aggregation": str(options.get("aggregation") or "deliberation_summary"),
        "authority": "advisory_evidence_only",
        "notes": [
            "ProgramPlan records the intended evaluation shape only.",
            "No juror model is called during deterministic materialization.",
            "Jury evidence cannot rank, prune, promote, or grant Oracle authority.",
        ],
    }


def build_jury_selection(jury_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Build deterministic juror selection metadata without calling any model."""

    jurors = [
        dict(item)
        for item in jury_payload.get("jurors", [])
        if isinstance(item, Mapping)
    ]
    minimum_jurors = int(jury_payload.get("minimum_jurors") or 3)
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    seen_perspectives: set[str] = set()
    for juror in jurors:
        perspective = str(juror.get("perspective") or "unspecified")
        juror_id = str(juror.get("id") or "")
        if juror_id in selected_ids or perspective in seen_perspectives:
            continue
        selected.append(dict(juror))
        selected_ids.add(juror_id)
        seen_perspectives.add(perspective)
        if len(selected) >= minimum_jurors:
            break
    if len(selected) < minimum_jurors:
        for juror in jurors:
            juror_id = str(juror.get("id") or "")
            if juror_id in selected_ids:
                continue
            selected.append(dict(juror))
            selected_ids.add(juror_id)
            if len(selected) >= minimum_jurors:
                break
    status = "selected" if len(selected) >= minimum_jurors else "selection_incomplete"
    selection_constraints = jury_payload.get("selection_constraints")
    if not isinstance(selection_constraints, Mapping):
        selection_constraints = {}
    return {
        "schema_version": "program-jury-selection-v1",
        "jury_schema_version": jury_payload.get("schema_version", "program-jury-v1"),
        "selection_model": jury_payload.get("selection_model"),
        "selection_constraints": dict(selection_constraints),
        "minimum_jurors": minimum_jurors,
        "eligible_juror_count": len(jurors),
        "selected_juror_count": len(selected),
        "selected_jurors": selected,
        "selected_perspectives": [
            str(juror.get("perspective") or "unspecified") for juror in selected
        ],
        "status": status,
        "authority": "selection_contract_only_non_authoritative",
        "notes": [
            "Selection is deterministic metadata for future jury execution binding.",
            "No juror model is called during deterministic materialization.",
            "Selected jurors cannot rank, prune, promote, or grant Oracle authority.",
        ],
    }


PERSPECTIVE_RUBRICS: dict[str, dict[str, list[str]]] = {
    "correctness": {
        "criteria": ["answer_correctness", "objective_satisfaction"],
        "adversarial_questions": [
            "Where could the produced answer be simply wrong?",
            "Does the output satisfy every declared output field?",
        ],
    },
    "robustness": {
        "criteria": ["edge_case_resilience", "failure_mode_visibility"],
        "adversarial_questions": [
            "Which edge case would break this program first?",
            "Are failure modes explicit enough to debug?",
        ],
    },
    "instruction_following": {
        "criteria": ["objective_adherence", "format_and_field_adherence"],
        "adversarial_questions": [
            "Does the output drift from the stated objective?",
            "Does the output honor the requested field contract?",
        ],
    },
    "answer_equivalence": {
        "criteria": ["strict_equivalence", "acceptable_variant_handling"],
        "adversarial_questions": [
            "Would semantically equivalent answers be scored incorrectly?",
            "Would near-miss answers pass when they should not?",
        ],
    },
    "label_boundary": {
        "criteria": ["class_boundary_clarity", "ambiguous_case_handling"],
        "adversarial_questions": [
            "Which inputs sit on the boundary between labels?",
            "Are ambiguous cases handled consistently?",
        ],
    },
    "example_generalization": {
        "criteria": ["overfit_resistance", "held_out_behavior"],
        "adversarial_questions": [
            "Does the program merely mimic examples?",
            "What held-out example would expose weak generalization?",
        ],
    },
    "calibration": {
        "criteria": ["confidence_alignment", "uncertainty_expression"],
        "adversarial_questions": [
            "Is confidence overstated for uncertain answers?",
            "Does the program know when evidence is insufficient?",
        ],
    },
    "grounding": {
        "criteria": ["source_faithfulness", "citation_discipline"],
        "adversarial_questions": [
            "Which claim is unsupported by the supplied context?",
            "Are citations or source references faithful?",
        ],
    },
    "source_grounding": {
        "criteria": ["source_refs_preserved", "source_identity_not_invented"],
        "adversarial_questions": [
            "Does every transition artifact preserve source references?",
            "Does the program invent Zotero, Marker, or source-package authority?",
        ],
    },
    "authority_boundaries": {
        "criteria": ["canonical_mutation_forbidden", "review_authority_explicit"],
        "adversarial_questions": [
            "Could this output be mistaken for an accepted Wiki or Atlas mutation?",
            "Are review-only boundaries and required human decisions explicit?",
        ],
    },
    "transition_artifact_quality": {
        "criteria": ["artifact_family_clarity", "proposal_reviewability"],
        "adversarial_questions": [
            "Are transition, proposal, review, and canonical artifact families distinct?",
            "Would a reviewer have enough provenance and uncertainty to act?",
        ],
    },
    "language_fidelity": {
        "criteria": ["source_language_preserved", "review_text_language_consistent"],
        "adversarial_questions": [
            "Does the generated draft switch languages without an explicit request?",
            "Are headings, labels, and review-facing note text in the source language?",
        ],
    },
    "zotero_footnote_linkage": {
        "criteria": ["zotero_refs_preferred", "source_provenance_footnotes_only"],
        "adversarial_questions": [
            "Does provenance prefer Zotero item/attachment refs when available?",
            "Did source/provenance material leak into a separate heading block instead of footnotes?",
        ],
    },
    "zotero_identity_derivation": {
        "criteria": [
            "zotero_uris_derived_from_manifest_keys",
            "package_folder_not_renamed_to_zotero_key",
        ],
        "adversarial_questions": [
            "If explicit Zotero URIs are absent, did the draft derive review links from item_key and attachment_record_id without inventing source identity?",
            "Did the output preserve doc_id/hash-keyed package paths instead of treating Zotero keys or citekeys as package folders?",
        ],
    },
    "wiki_link_key_concepts": {
        "criteria": ["durable_concepts_wikilinked", "ordinary_words_not_overlinked"],
        "adversarial_questions": [
            "Are reusable concepts, methods, and sibling candidates emitted as Obsidian wikilinks?",
            "Is the draft overlinking generic words or underlinking durable concepts?",
        ],
    },
    "constraint_adherence": {
        "criteria": ["constraint_satisfaction", "forbidden_behavior_detection"],
        "adversarial_questions": [
            "Which declared constraint is easiest to violate?",
            "Does the program expose or hide constraint failures?",
        ],
    },
    "clarity": {
        "criteria": ["readability", "user_actionability"],
        "adversarial_questions": [
            "Would a user understand the answer without extra context?",
            "Is the response concise enough for the use case?",
        ],
    },
}


def rubric_for_perspective(perspective: str) -> dict[str, list[str]]:
    return PERSPECTIVE_RUBRICS.get(
        perspective,
        {
            "criteria": [f"{perspective}_review"],
            "adversarial_questions": [
                f"What would a {perspective} reviewer challenge first?"
            ],
        },
    )


def build_jury_rubric(intent: Any, jury_selection: Mapping[str, Any]) -> dict[str, Any]:
    """Build deterministic perspective rubrics for selected jurors without model calls."""

    juror_rubrics: list[dict[str, Any]] = []
    for juror in jury_selection.get("selected_jurors", []):
        if not isinstance(juror, Mapping):
            continue
        perspective = str(juror.get("perspective") or "unspecified")
        rubric = rubric_for_perspective(perspective)
        juror_rubrics.append(
            {
                "juror_id": juror.get("id"),
                "perspective": perspective,
                "criteria": list(rubric["criteria"]),
                "adversarial_questions": list(rubric["adversarial_questions"]),
            }
        )
    return {
        "schema_version": "program-jury-rubric-v1",
        "intent_name": intent.name,
        "objective": intent.objective,
        "selection_status": jury_selection.get("status"),
        "selected_juror_count": jury_selection.get("selected_juror_count", 0),
        "juror_rubrics": juror_rubrics,
        "constraints_under_review": list(intent.constraints),
        "authority": "rubric_contract_only_non_authoritative",
        "notes": [
            "Rubrics are deterministic prompts for future jury execution binding.",
            "No juror model is called during deterministic materialization.",
            "Rubric results cannot rank, prune, promote, or grant Oracle authority.",
        ],
    }

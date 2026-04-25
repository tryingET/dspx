from __future__ import annotations

from typing import Any, Mapping

PROMOTION_ADJUDICATOR_DEFAULT_IDS = {
    "human_operator": "local_operator",
    "ai_agent": "local_ai_agent",
    "ai_council": "local_ai_council",
    "hybrid": "ai_council_recommends_human_approves",
    "policy_gate": "local_policy_gate",
}


def promotion_adjudicator(intent: Any) -> dict[str, Any]:
    promotion = dict(intent.promotion or {})
    raw_adjudicator = promotion.get("adjudicator")
    adjudicator = dict(raw_adjudicator) if isinstance(raw_adjudicator, Mapping) else {}
    kind = str(
        adjudicator.get("kind") or promotion.get("adjudicator_kind") or "human_operator"
    )
    if kind not in PROMOTION_ADJUDICATOR_DEFAULT_IDS:
        allowed = sorted(PROMOTION_ADJUDICATOR_DEFAULT_IDS)
        raise ValueError(
            "program promotion adjudicator.kind must name a decision actor/process; "
            f"allowed values: {allowed}"
        )
    adjudicator_id = PROMOTION_ADJUDICATOR_DEFAULT_IDS[kind]
    if adjudicator.get("id"):
        adjudicator_id = str(adjudicator["id"])
    payload: dict[str, Any] = {
        "kind": kind,
        "id": adjudicator_id,
        "authority": str(adjudicator.get("authority") or "required_for_promotion"),
        "status": "pending",
    }
    for key, value in adjudicator.items():
        if (
            key not in {"kind", "id", "authority", "status", "adapter"}
            and value is not None
        ):
            payload[key] = value
    return payload


def external_authority_ref(raw: Any, *, source: str) -> dict[str, Any] | None:
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        return {"ref": text, "status": "not_exported", "source": source}
    if not isinstance(raw, Mapping):
        return None
    ref = {str(key): value for key, value in raw.items() if value is not None}
    if not ref:
        return None
    ref.setdefault("status", "not_exported")
    ref.setdefault("source", source)
    return ref


def promotion_external_authority(intent: Any) -> dict[str, Any]:
    """Preserve opaque external authority refs without owning adapter semantics."""

    promotion = dict(intent.promotion or {})
    refs: list[dict[str, Any]] = []
    raw_external_authority = promotion.get("external_authority")
    if isinstance(raw_external_authority, Mapping):
        raw_refs = raw_external_authority.get("refs") or []
        if isinstance(raw_refs, list):
            for raw_ref in raw_refs:
                ref = external_authority_ref(
                    raw_ref, source="promotion.external_authority.refs"
                )
                if ref is not None:
                    refs.append(ref)
    raw_external_refs = promotion.get("external_refs")
    if isinstance(raw_external_refs, list):
        for raw_ref in raw_external_refs:
            ref = external_authority_ref(raw_ref, source="promotion.external_refs")
            if ref is not None:
                refs.append(ref)
    return {
        "status": "not_exported",
        "refs": refs,
        "notes": [
            "External authority references are preserved as opaque metadata.",
            "DSPx core does not validate, call, or mutate external authority systems.",
        ],
    }


def promotion_policy(intent: Any) -> dict[str, Any]:
    promotion = dict(intent.promotion or {})
    raw_policy = promotion.get("policy")
    policy = dict(raw_policy) if isinstance(raw_policy, Mapping) else {}
    if bool(policy.get("automatic_promotion", False)):
        raise ValueError(
            "program-gen promotion policy cannot enable automatic_promotion"
        )
    return {
        "requires_behavioral_evaluation": bool(
            policy.get("requires_behavioral_evaluation", True)
        ),
        "requires_jury_execution": bool(policy.get("requires_jury_execution", True)),
        "requires_adjudicator_decision": bool(
            policy.get("requires_adjudicator_decision", True)
        ),
        "automatic_promotion": False,
    }


def build_promotion_review(
    intent: Any,
    *,
    has_examples: bool,
    jury_selection: Mapping[str, Any],
    jury_rubric: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a local non-authoritative promotion/review shell."""

    adjudicator = promotion_adjudicator(intent)
    policy = promotion_policy(intent)
    external_authority = promotion_external_authority(intent)
    evidence_requirements = [
        {
            "name": "candidate_materialized",
            "status": "satisfied_by_current_materialization",
            "artifact_refs": ["program.py", "manifest.json"],
        },
        {
            "name": "smoke_validation",
            "status": "satisfied_by_current_materialization",
            "artifact_refs": ["eval_smoke.py"],
        },
        {
            "name": "jury_artifact_binding",
            "status": "satisfied_by_current_materialization",
            "artifact_refs": ["jury.json", "jury_selection.json", "jury_rubric.json"],
        },
        {
            "name": "examples_binding",
            "status": "satisfied_by_current_materialization"
            if has_examples
            else "not_applicable",
            "artifact_refs": ["examples.json", "eval_examples.py"]
            if has_examples
            else [],
        },
        {
            "name": "behavioral_evaluation_episode",
            "status": "pending"
            if policy["requires_behavioral_evaluation"]
            else "not_required_by_policy",
            "artifact_refs": [],
        },
        {
            "name": "model_jury_execution_episode",
            "status": "pending"
            if policy["requires_jury_execution"]
            else "not_required_by_policy",
            "artifact_refs": [],
        },
        {
            "name": "promotion_adjudicator_decision",
            "status": "pending"
            if policy["requires_adjudicator_decision"]
            else "not_required_by_policy",
            "artifact_refs": [],
            "adjudicator_ref": adjudicator["id"],
        },
    ]
    blocking_conditions = []
    if policy["requires_behavioral_evaluation"]:
        blocking_conditions.append("no_behavioral_evaluation_episode")
    if policy["requires_jury_execution"]:
        blocking_conditions.append("no_model_jury_execution_episode")
    if policy["requires_adjudicator_decision"]:
        blocking_conditions.append("no_promotion_adjudicator_decision")
    return {
        "schema_version": "program-promotion-review-v1",
        "intent_name": intent.name,
        "objective": intent.objective,
        "promotion_state": "not_promoted",
        "candidate_status": "exploratory",
        "review_required": True,
        "adjudicator": adjudicator,
        "decision_authority": adjudicator["authority"],
        "promotion_policy": policy,
        "external_authority": external_authority,
        "decision": {
            "status": "pending",
            "outcome": None,
            "decided_by": None,
            "decided_at": None,
            "evidence_refs": [],
        },
        "evidence_requirements": evidence_requirements,
        "blocking_conditions": blocking_conditions,
        "available_local_evidence": {
            "plan": "plan.json",
            "jury": "jury.json",
            "jury_selection_status": jury_selection.get("status"),
            "jury_rubric_status": "available"
            if jury_rubric.get("juror_rubrics")
            else "unavailable",
            "smoke_harness": "eval_smoke.py",
            "jury_harness": "eval_jury.py",
            "examples_binding": has_examples,
        },
        "non_authority": {
            "program_gen_materialization": "evidence_only",
            "jury_artifacts": "planned_contracts_only",
            "oracle_role": "behavioral_interpreter_only",
            "automatic_promotion": False,
            "ranking_pruning_promotion": False,
            "external_authority_export": False,
        },
        "notes": [
            "This shell records what would be needed before local promotion review.",
            "It does not promote the generated program or activate any policy.",
            "The promotion adjudicator may be human, one AI agent, an AI council, a hybrid, or a policy gate.",
            "Jury artifacts are planning/binding evidence until a later model jury episode runs.",
        ],
    }


def build_promotion_adjudication_request(
    promotion_review: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a deterministic decision packet for the configured adjudicator."""

    adjudicator = dict(promotion_review.get("adjudicator") or {})
    external_authority = dict(promotion_review.get("external_authority") or {})
    blocking_conditions = list(promotion_review.get("blocking_conditions") or [])
    decision_record_template = {
        "schema_version": "program-promotion-decision-v1",
        "status": "pending",
        "outcome": None,
        "decided_by": None,
        "adjudicator_ref": adjudicator.get("id"),
        "adjudicator_kind": adjudicator.get("kind"),
        "rationale": None,
        "evidence_refs": [],
    }
    return {
        "schema_version": "program-promotion-adjudication-request-v1",
        "status": "not_ready_blocked"
        if blocking_conditions
        else "ready_for_adjudicator",
        "adjudicator": adjudicator,
        "external_authority": external_authority,
        "decision_question": (
            "Should this exact program candidate be promoted, withheld, rejected, "
            "or returned for more evidence?"
        ),
        "allowed_outcomes": [
            "promote",
            "withhold",
            "reject",
            "request_more_evidence",
        ],
        "candidate_refs": {
            "manifest": "manifest.json",
            "program": "program.py",
            "intent": "intent.json",
            "plan": "plan.json",
        },
        "evidence_packet": [
            {"kind": "plan", "path": "plan.json"},
            {"kind": "jury_pool", "path": "jury.json"},
            {"kind": "jury_selection", "path": "jury_selection.json"},
            {"kind": "jury_rubric", "path": "jury_rubric.json"},
            {"kind": "promotion_review", "path": "promotion_review.json"},
            {"kind": "smoke_harness", "path": "eval_smoke.py"},
            {"kind": "jury_binding_harness", "path": "eval_jury.py"},
        ],
        "missing_required_evidence": blocking_conditions,
        "decision_record_template": decision_record_template,
        "authority": "adjudication_request_only_non_authoritative",
        "notes": [
            "This packet prepares an explicit adjudicator decision; it is not a decision.",
            "Promotion remains blocked until required evidence and an adjudicator decision exist.",
            "No human, AI agent, council, policy gate, or Oracle is invoked during materialization.",
        ],
    }

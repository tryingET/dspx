"""Pure v1 terminal reconstruction and finite historical journal validation."""

from __future__ import annotations

from pathlib import PurePosixPath
import json
from program_foundry_closure_core import NONAUTH  # ty: ignore[unresolved-import]
from program_foundry_closure_journal import journals  # ty: ignore[unresolved-import]
from program_foundry_closure_io import (  # ty: ignore[unresolved-import]
    Snapshot,
    canonical,
    closed,
    digest,
    equal,
    integer,
    path_parts,
    require,
    sha,
    sibling,
)

COUNT_KEYS = {
    "supports_review_evidence",
    "reject",
    "request_more_evidence",
    "withhold",
    "failed",
}


def aggregate(results: list) -> tuple[str, dict]:
    counts = dict.fromkeys(sorted(COUNT_KEYS), 0)
    improvements = set()
    judged = 0
    for result in results:
        require(result["status"] in {"judged", "failed"}, "juror_status")
        if result["status"] == "failed":
            counts["failed"] += 1
            continue
        judged += 1
        judgment = closed(
            result["judgment"],
            {
                "outcome",
                "confidence",
                "rationale",
                "concerns",
                "evidence_strengths",
                "improvement_requests",
            },
        )
        outcome = judgment["outcome"]
        require(outcome in COUNT_KEYS - {"failed"}, "unknown_judgment")
        require(
            judgment["confidence"] in {"low", "medium", "high"}, "judgment_confidence"
        )
        require(
            isinstance(judgment["rationale"], str) and judgment["rationale"],
            "judgment_rationale",
        )
        for key in ("concerns", "evidence_strengths", "improvement_requests"):
            require(
                isinstance(judgment[key], list)
                and len(judgment[key]) <= 32
                and all(isinstance(x, str) for x in judgment[key]),
                "judgment_list",
            )
        counts[outcome] += 1
        improvements.update(judgment["improvement_requests"])
    require(judged > 0, "all_jurors_failed")
    recommendation = "supports_review_evidence_only"
    for key, value in (
        ("failed", "withhold_until_failed_jurors_rerun"),
        ("reject", "reject_or_redesign"),
        ("request_more_evidence", "request_more_evidence"),
        ("withhold", "withhold_for_owner_review"),
    ):
        if counts[key]:
            recommendation = value
            break
    return ("executed_with_failures" if counts["failed"] else "executed"), {
        "judgment_counts": counts,
        "recommendation": recommendation,
        "blocking_concerns_present": bool(
            counts["failed"] or counts["reject"] or counts["request_more_evidence"]
        ),
        "unique_improvement_requests": sorted(improvements),
    }


def verify_jury(s: Snapshot, state: dict, report: dict) -> None:
    jury, jpath = state["jury"], state["jpath"]
    eroot = str(PurePosixPath(jpath).parent)
    cp, comparison_path = state["candidate_path"], state["comparison_path"]
    request = jury["execution_request"]
    common = {
        "provider",
        "adjudicator_id",
        "adjudicator_kind",
        "adjudicator_repo",
        "max_jurors",
        "owner_source_root",
        "execution_task_id",
        "execution_claimant",
        "model",
    }
    closed(
        request,
        common
        | (
            {"local_vllm_base_url"}
            if request["provider"] == "foundry-dspy-lm-auth-local-vllm"
            else set()
        )
        | ({"execution_repo_root"} if "execution_repo_root" in request else set())
        | (
            {"provider_evidence_kind"} if "provider_evidence_kind" in request else set()
        ),
    )
    integer(request["execution_task_id"], 2**53 - 1, 1)
    if "execution_repo_root" in request:
        path_parts(request["execution_repo_root"], absolute=True)
    if "provider_evidence_kind" in request:
        require(
            request["provider_evidence_kind"]
            in {"live", "authored_fixture_replay", "stub_echo"},
            "invalid_evidence_label",
        )
    inputs = [
        cp,
        sibling(cp, "jury.json"),
        sibling(cp, "jury_selection.json"),
        sibling(cp, "jury_rubric.json"),
        comparison_path,
    ]
    snapshots = [{"path": p, "sha256": s.hash(p)} for p in sorted(inputs)]
    attempt_path = eroot + "/comparison-jury-attempt.json"
    attempt = s.json(attempt_path)
    body = {
        "schema_version": "dspx-program-foundry-gepa-comparison-jury-attempt-v1",
        "status": "provider_effect_possible",
        "proposal_id": state["proposal"]["proposal_id"],
        "consumption_receipt_path": state["consumption_path"],
        "consumption_receipt_sha256": s.hash(state["consumption_path"]),
        "execution_request": request,
        "jury_input_snapshots": snapshots,
        "no_replay_after_marker": True,
        "effect_disposition": "indeterminate_until_comparison_jury_receipt",
        "non_authority": NONAUTH,
    }
    equal(
        attempt,
        {**body, "attempt_id": digest(canonical(body))},
        "jury_attempt_reconstruction",
    )
    result_path = eroot + "/comparison-jury-results.json"
    result = s.json(result_path)
    closed(
        result,
        {
            "schema_version",
            "status",
            "adjudicator",
            "aggregate",
            "created_from",
            "effect",
            "evidence",
            "identity",
            "interpretation",
            "juror_results",
            "jury",
            "non_authority",
        },
    )
    equal(result["schema_version"], "program-model-jury-results-v1")
    selected = s.json(sibling(cp, "jury_selection.json"))["selected_jurors"]
    if request["max_jurors"] is not None:
        maximum = integer(request["max_jurors"], 32, 1)
        selected = selected[:maximum]
    rows = result["juror_results"]
    require(isinstance(rows, list) and 0 < len(rows) <= 32, "juror_count")
    equal(len(rows), len(selected))
    require(len({x["id"] for x in selected}) == len(selected), "duplicate_juror")
    for row, chosen in zip(rows, selected, strict=True):
        closed(
            row,
            {"juror_id", "perspective", "provider", "model", "status", "execution_mode"}
            | ({"judgment"} if row["status"] == "judged" else {"error"}),
        )
        equal(row["execution_mode"], "provider_backed_model")
        if row["status"] != "judged":
            error = closed(row["error"], {"type", "message"})
            require(
                all(isinstance(x, str) and len(x) <= 4096 for x in error.values()),
                "juror_error_shape",
            )
        equal(row["juror_id"], chosen["id"])
        equal(row["perspective"], chosen["perspective"])
        equal(row["provider"], request["provider"])
        equal(row["model"], request["model"])
    status, agg = aggregate(rows)
    equal(result["status"], status)
    equal(result["aggregate"], agg, "jury_aggregate_reconstruction")
    equal(result["identity"], state["comparison"]["candidate_identity"])
    created = {
        "manifest_path": cp,
        "manifest_schema_version": "program-candidate-assembly-v1",
        "manifest_sha256": s.hash(cp),
        "evidence_paths": [comparison_path],
    }
    for role in ("jury", "jury_selection", "jury_rubric"):
        path = sibling(cp, role + ".json")
        created.update({role + "_path": path, role + "_sha256": s.hash(path)})
    equal(result["created_from"], created)
    equal(
        result["jury"],
        {
            "execution_mode": "provider_backed_model",
            "planned_jury_schema_version": "program-jury-v1",
            "provider_backed_model_calls": True,
            "rubric_schema_version": "program-jury-rubric-v1",
            "selected_juror_count": len(rows),
            "selected_perspectives": [x["perspective"] for x in selected],
            "selection_schema_version": "program-jury-selection-v1",
            "provider_config": result["jury"]["provider_config"],
            "provider_outcome_evidence": result["jury"]["provider_outcome_evidence"],
        },
    )
    equal(
        result["adjudicator"],
        {
            "id": request["adjudicator_id"],
            "kind": request["adjudicator_kind"],
            "repo": request["adjudicator_repo"],
            "authority": "downstream_domain_review_recommendation_only",
            "promotion_authority": False,
        },
    )
    equal(
        result["effect"],
        {
            "ak_mutated": False,
            "external_authority_mutated": False,
            "governance_mutated": False,
            "model_jury_evidence_only": True,
            "new_candidate_generated": False,
            "oracle_index_mutated": False,
            "program_files_mutated": False,
            "promotion_review_mutated": False,
        },
    )
    equal(
        result["non_authority"],
        {
            "canonical_mutation": False,
            "domain_acceptance": False,
            "external_authority_apply": False,
            "promotion_approval": False,
            "ranking_or_winner_selection": False,
        },
    )
    require(
        result["interpretation"]["ready_for_promotion_decision"] is False,
        "jury_promotion_claim",
    )
    evidence = result["evidence"]
    prompt = json.dumps(
        [
            {
                "kind": "explicit_evidence",
                "path": comparison_path,
                "sha256": s.hash(comparison_path),
                "schema_version": "program-refinement-candidate-comparison-v1",
                "summary": None,
                "payload": state["comparison"],
            }
        ],
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    if len(prompt) > 48000:
        prompt = (
            prompt[:48000]
            + f"\n... truncated for model jury prompt ({len(prompt)} chars total)"
        )
    equal(evidence["prompt_sha256"], digest(prompt.encode()), "jury_prompt_hash")
    equal(
        evidence,
        {
            "default_behavior": {"entry_count": 0, "kinds": [], "present": False},
            "entries": [
                {
                    "kind": "explicit_evidence",
                    "path": comparison_path,
                    "schema_version": "program-refinement-candidate-comparison-v1",
                    "sha256": s.hash(comparison_path),
                    "summary": None,
                }
            ],
            "entry_count": 1,
            "extra_evidence_count": 1,
            "prompt_sha256": sha(evidence["prompt_sha256"]),
        },
    )
    journals(s, request, result, s.hash(attempt_path), eroot)
    bindings = {}
    for name, path in {
        "consumption_receipt": state["consumption_path"],
        "execution_receipt": state["execution_path"],
        "source_manifest": state["source_path"],
        "candidate_manifest": cp,
        "comparison": comparison_path,
        "attempt": attempt_path,
        "jury_results": result_path,
    }.items():
        bindings.update({name + "_path": path, name + "_sha256": s.hash(path)})
    equal(
        jury,
        {
            "schema_version": "dspx-program-foundry-gepa-comparison-jury-v1",
            "status": "ok",
            "jury_status": status,
            "proposal_id": state["proposal"]["proposal_id"],
            "execution_request": request,
            "bindings": bindings,
            "aggregate": agg,
            "effect": {
                "program_specific_jury_executed": True,
                "provider_calls_may_have_occurred": True,
                "comparison_mutated": False,
                "candidate_mutated": False,
                "winner_selected": False,
                "promotion_applied": False,
                "activation_applied": False,
                "external_authority_mutated": False,
                "ak_called": True,
                "ak_mutated": False,
            },
            "non_authority": {"local_jury_evidence_only": True, **NONAUTH},
        },
        "jury_receipt_reconstruction",
    )
    verify_adjudication(s, jury, jpath, result_path)
    report["origins"]["jury"] = "historical_owner_journal"


def verify_adjudication(s: Snapshot, jury: dict, jpath: str, result_path: str) -> None:
    _, adjudication = s.expected("adjudication")
    agg = jury["aggregate"]
    counts = agg["judgment_counts"]
    disposition, local_state = "require_review", "held_for_local_review"
    reason = {
        "withhold_until_failed_jurors_rerun": "juror_execution_failed_no_replay",
        "request_more_evidence": "jury_requests_more_evidence",
        "withhold_for_owner_review": "jury_withholds_for_review",
    }.get(
        agg["recommendation"],
        "jury_outcome_not_eligible_for_automatic_local_transition",
    )
    if counts["supports_review_evidence"] == sum(counts.values()):
        disposition, local_state, reason = (
            "promote_locally",
            "eligible_local_candidate",
            "all_jurors_support_review_evidence",
        )
    elif counts["reject"] == sum(counts.values()):
        disposition, local_state, reason = (
            "reject_locally",
            "rejected_local_candidate",
            "one_or_more_jurors_reject",
        )
    bindings = {
        k: v
        for k, v in jury["bindings"].items()
        if not k.startswith(("attempt_", "execution_receipt_"))
    }
    bindings.update(
        comparison_jury_receipt_path=jpath, comparison_jury_receipt_sha256=s.hash(jpath)
    )
    equal(
        adjudication,
        {
            "schema_version": "dspx-program-foundry-gepa-comparison-adjudication-v1",
            "status": "recorded",
            "disposition": disposition,
            "local_candidate_state": local_state,
            "proposal_id": jury["proposal_id"],
            "policy": {
                "id": "foundry-gepa-comparison-jury-disposition-v1",
                "input_mode": "validated_comparison_jury_receipt_only",
                "deterministic": True,
                "models_rerun": False,
                "unknown_or_mixed_outcomes_fail_to_review": True,
            },
            "bindings": bindings,
            "jury_snapshot": {"jury_status": jury["jury_status"], "aggregate": agg},
            "reason_codes": [reason],
            "effect": {
                "bounded_local_disposition_recorded": True,
                "candidate_files_mutated": False,
                "comparison_mutated": False,
                "models_rerun": False,
                "gepa_reexecuted": False,
                "winner_applied": False,
                "production_activation_applied": False,
                "external_authority_mutated": False,
                "governance_mutated": False,
                "ak_called": False,
            },
            "non_authority": {
                "bounded_local_disposition_only": True,
                "external_winner_selection": False,
                "production_promotion_authority": False,
                "activation_authority": False,
                "governance_authority": False,
                "external_authority_apply": False,
            },
        },
        "adjudication_reconstruction",
    )

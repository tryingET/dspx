from __future__ import annotations

import ast
import json
import os
import shutil
from pathlib import Path
from typing import Any, Optional

from dspx.cache import cache_dir, make_key
from dspx.dtos import ModuleSpec
from dspx.generated_code_guard import smoke_module_code

from .contracts import (
    CandidateRecord,
    CandidateWorkspace,
    EvaluationRecord,
    PromotionDecision,
    StrategyRecord,
    SynthesisBundle,
    SynthesisRequest,
    build_module_candidate_record,
    build_module_evaluation_record,
    build_module_promotion_decision,
    build_module_promotion_shell,
    build_module_selection_policy,
    build_module_strategy_record,
    build_module_synthesis_request,
)


def synthesis_workspace_dir() -> Path:
    """Return the workspace root used for materialized synthesis candidates."""

    override = os.getenv("DSPX_SYNTHESIS_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return cache_dir() / "synthesis"


def _module_filename(request: SynthesisRequest) -> str:
    return f"{request.spec.name}.py"


def _sanitize_ident(name: str, fallback: str = "Module") -> str:
    import re

    value = re.sub(r"\W+", "_", name.strip()) or fallback
    if value[0].isdigit():
        value = f"_{value}"
    return value


def _module_class_name(request: SynthesisRequest) -> str:
    return _sanitize_ident(request.spec.name or "Module")


def _signature_class_name(request: SynthesisRequest) -> str:
    return f"Sig_{_module_class_name(request)}"


def _expected_io(request: SynthesisRequest) -> tuple[list[str], list[str]]:
    inputs = [field.name for field in request.spec.inputs] or ["context"]
    outputs = [field.name for field in request.spec.outputs] or ["output"]
    return inputs, outputs


def _promoted_target_path(
    request: SynthesisRequest,
    workspace_root: Path,
    *,
    target_path: Optional[Path] = None,
) -> Path:
    if target_path is not None:
        return target_path.expanduser().resolve()
    return (workspace_root / "promoted" / _module_filename(request)).resolve()


def materialize_module_candidate_workspace(
    request: SynthesisRequest,
    candidate: CandidateRecord,
    *,
    code: str,
    strategy: StrategyRecord,
    workspace_root: Optional[Path] = None,
) -> CandidateWorkspace:
    """Write the rendered candidate into a stable scratch workspace."""

    root = (
        workspace_root.expanduser().resolve()
        if workspace_root is not None
        else (synthesis_workspace_dir() / request.request_id).resolve()
    )
    scratch = root / "scratch" / candidate.candidate_id
    scratch.mkdir(parents=True, exist_ok=True)

    artifact_path = scratch / _module_filename(request)
    artifact_path.write_text(code, encoding="utf-8")

    manifest_path = scratch / "candidate.json"
    workspace_payload = {
        "request_id": request.request_id,
        "candidate_id": candidate.candidate_id,
        "root_path": str(root),
        "scratch_path": str(scratch),
    }
    workspace = CandidateWorkspace(
        workspace_id=f"ws-{make_key(workspace_payload)[:12]}",
        request_id=request.request_id,
        candidate_id=candidate.candidate_id,
        root_path=str(root),
        scratch_path=str(scratch),
        artifact_path=str(artifact_path),
        manifest_path=str(manifest_path),
        metadata={
            "workspace_kind": "scratch",
            "artifact_name": artifact_path.name,
            "strategy_id": strategy.strategy_id,
            "strategy_version": strategy.strategy_version,
        },
    )

    manifest = {
        "request": request.model_dump(mode="json"),
        "strategy": strategy.model_dump(mode="json"),
        "candidate": candidate.model_dump(mode="json"),
        "workspace": workspace.model_dump(mode="json"),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return workspace


def _attach_workspace_metadata(
    candidate: CandidateRecord,
    workspace: CandidateWorkspace,
    strategy: StrategyRecord,
) -> CandidateRecord:
    artifact_metadata = dict(candidate.artifact.metadata)
    artifact_metadata.update(
        {
            "workspace_id": workspace.workspace_id,
            "artifact_path": workspace.artifact_path,
            "strategy_id": strategy.strategy_id,
            "strategy_version": strategy.strategy_version,
        }
    )
    candidate_metadata = dict(candidate.metadata)
    candidate_metadata.update(
        {
            "workspace_id": workspace.workspace_id,
            "workspace_root": workspace.root_path,
            "manifest_path": workspace.manifest_path,
            "selection_ready": False,
        }
    )
    lineage = dict(candidate.lineage)
    lineage.update({"workspace_id": workspace.workspace_id})
    return candidate.model_copy(
        update={
            "artifact": candidate.artifact.model_copy(
                update={"metadata": artifact_metadata}
            ),
            "metadata": candidate_metadata,
            "lineage": lineage,
        }
    )


def _normalize_candidate_sources(
    *,
    code: Optional[str],
    candidate_sources: Optional[list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    if candidate_sources:
        normalized: list[dict[str, Any]] = []
        for ordinal, source in enumerate(candidate_sources):
            candidate_code = source.get("code") if isinstance(source, dict) else None
            if not isinstance(candidate_code, str):
                raise ValueError(
                    f"candidate_sources[{ordinal}] is missing a string 'code' field"
                )
            normalized.append(
                {
                    "code": candidate_code,
                    "artifact_metadata": (
                        dict(source.get("artifact_metadata") or {})
                        if isinstance(source, dict)
                        else {}
                    ),
                    "candidate_metadata": (
                        dict(source.get("candidate_metadata") or {})
                        if isinstance(source, dict)
                        else {}
                    ),
                    "lineage": (
                        dict(source.get("lineage") or {})
                        if isinstance(source, dict)
                        else {}
                    ),
                }
            )
        return normalized

    if code is None:
        raise ValueError("Module synthesis bundle requires code or candidate_sources")

    return [
        {
            "code": code,
            "artifact_metadata": {},
            "candidate_metadata": {},
            "lineage": {},
        }
    ]


def materialize_module_synthesis_bundle(
    spec: ModuleSpec,
    *,
    code: Optional[str] = None,
    candidate_sources: Optional[list[dict[str, Any]]] = None,
    use_signature: bool = False,
    strategy_id: Optional[str] = None,
    strategy_version: str = "v0",
    workspace_root: Optional[Path] = None,
    promotion_target: Optional[Path] = None,
    strategy_metadata: Optional[dict[str, Any]] = None,
) -> SynthesisBundle:
    """Build a synthesis bundle and materialize its scratch workspace shell."""

    sources = _normalize_candidate_sources(
        code=code, candidate_sources=candidate_sources
    )
    request = build_module_synthesis_request(
        spec,
        use_signature=use_signature,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        candidate_budget=len(sources),
    )
    strategy = build_module_strategy_record(
        request,
        metadata={
            "fan_out_count": len(sources),
            **dict(strategy_metadata or {}),
        },
    )
    workspace_base = (
        workspace_root.expanduser().resolve()
        if workspace_root is not None
        else (synthesis_workspace_dir() / request.request_id).resolve()
    )

    candidates: list[CandidateRecord] = []
    workspaces: list[CandidateWorkspace] = []
    evaluations: list[EvaluationRecord] = []
    for ordinal, source in enumerate(sources):
        candidate = build_module_candidate_record(
            request,
            code=source["code"],
            ordinal=ordinal,
            artifact_metadata=source.get("artifact_metadata"),
            candidate_metadata=source.get("candidate_metadata"),
            lineage=source.get("lineage"),
        )
        workspace = materialize_module_candidate_workspace(
            request,
            candidate,
            code=source["code"],
            strategy=strategy,
            workspace_root=workspace_base,
        )
        candidate = _attach_workspace_metadata(candidate, workspace, strategy)
        evaluation = build_module_evaluation_record(
            candidate,
            phase="AK-256" if len(sources) > 1 else "AK-251",
            workspace=workspace,
        )
        candidates.append(candidate)
        workspaces.append(workspace)
        evaluations.append(evaluation)

    policy = build_module_selection_policy(candidate_limit=len(sources))
    shell_target = _promoted_target_path(
        request,
        workspace_base,
        target_path=promotion_target,
    )
    promotion_shell = build_module_promotion_shell(
        request,
        target_path=str(shell_target),
    )
    promotion_decision = build_module_promotion_decision(
        request,
        policy,
        evaluations=evaluations,
        promotion_shell=promotion_shell,
    )
    return SynthesisBundle(
        request=request,
        strategy=strategy,
        candidates=candidates,
        candidate_workspaces=workspaces,
        evaluations=evaluations,
        selection_policy=policy,
        promotion_shell=promotion_shell,
        promotion_decision=promotion_decision,
    )


def _workspace_for_candidate(
    bundle: SynthesisBundle,
    candidate_id: str,
) -> CandidateWorkspace:
    for workspace in bundle.candidate_workspaces:
        if workspace.candidate_id == candidate_id:
            return workspace
    raise ValueError(f"No workspace found for candidate {candidate_id}")


def _candidate_by_id(bundle: SynthesisBundle, candidate_id: str) -> CandidateRecord:
    for candidate in bundle.candidates:
        if candidate.candidate_id == candidate_id:
            return candidate
    raise ValueError(f"Unknown candidate_id: {candidate_id}")


def _evaluation_for_candidate(
    bundle: SynthesisBundle,
    candidate_id: str,
) -> EvaluationRecord:
    for evaluation in bundle.evaluations:
        if evaluation.candidate_id == candidate_id:
            return evaluation
    raise ValueError(f"No evaluation found for candidate {candidate_id}")


def _is_named_base(node: ast.expr, expected: str) -> bool:
    return (isinstance(node, ast.Attribute) and node.attr == expected) or (
        isinstance(node, ast.Name) and node.id == expected
    )


def _module_static_checks(
    request: SynthesisRequest,
    code: str,
) -> tuple[bool, dict[str, bool], list[str]]:
    checks: dict[str, bool] = {
        "python-parse": False,
        "module-shape": False,
        "signature-wiring": False,
    }
    errors: list[str] = []

    try:
        tree = ast.parse(code)
        checks["python-parse"] = True
    except SyntaxError as exc:
        errors.append(f"syntax_error:{exc.msg}")
        return False, checks, errors

    module_classes: set[str] = set()
    signature_classes: set[str] = set()
    helpers: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            if any(_is_named_base(base, "Module") for base in node.bases):
                module_classes.add(node.name)
            if any(_is_named_base(base, "Signature") for base in node.bases):
                signature_classes.add(node.name)
        elif isinstance(node, ast.FunctionDef):
            helpers.add(node.name)

    required_helpers = {
        "build_student",
        "io_spec",
        "output_weights",
        "normalize_output",
    }
    expected_module = _module_class_name(request)
    checks["module-shape"] = (
        expected_module in module_classes and required_helpers.issubset(helpers)
    )
    if not checks["module-shape"]:
        errors.append(f"module_shape_missing:{expected_module}")

    if request.spec.use_signature:
        expected_signature = _signature_class_name(request)
        checks["signature-wiring"] = (
            expected_signature in signature_classes
            and f"self.predict = dspy.Predict({expected_signature})" in code
        )
        if not checks["signature-wiring"]:
            errors.append(f"signature_wiring_missing:{expected_signature}")
    else:
        inputs, outputs = _expected_io(request)
        io_sig = ", ".join(inputs) + " -> " + ", ".join(outputs)
        checks["signature-wiring"] = f"self.predict = dspy.Predict({io_sig!r})" in code
        if not checks["signature-wiring"]:
            errors.append("signature_wiring_missing:predict_prompt")

    try:
        compile(tree, "<generated_module>", "exec")
    except Exception as exc:
        checks["python-parse"] = False
        errors.append(f"compile_error:{exc}")

    return all(checks.values()), checks, errors


def _module_smoke_checks(
    request: SynthesisRequest,
    code: str,
) -> tuple[bool, dict[str, bool], list[str]]:
    inputs, outputs = _expected_io(request)
    return smoke_module_code(
        code,
        payload={
            "expected_module": _module_class_name(request),
            "expected_signature": (
                _signature_class_name(request) if request.spec.use_signature else None
            ),
            "use_signature": bool(request.spec.use_signature),
            "inputs": inputs,
            "outputs": outputs,
        },
    )


def _selection_bonus(candidate: CandidateRecord) -> float:
    raw = candidate.metadata.get("selection_bonus")
    if isinstance(raw, bool):
        return float(raw)
    if isinstance(raw, (int, float)):
        return float(raw)
    try:
        return float(str(raw)) if raw is not None else 0.0
    except Exception:
        return 0.0


def _ranking_entry(
    *,
    candidate: CandidateRecord,
    evaluation: EvaluationRecord,
    passed: bool,
) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "ordinal": candidate.ordinal,
        "status": evaluation.status,
        "score": evaluation.score,
        "evaluation_id": evaluation.evaluation_id,
        "variant_id": candidate.metadata.get("variant_id"),
        "variant_origin": candidate.lineage.get("variant_origin"),
        "variant_label": candidate.metadata.get("variant_label"),
        "selection_basis": candidate.metadata.get("selection_basis"),
        "passed": passed,
    }


def _evaluation_summary(
    *,
    passed: bool,
    errors: list[str],
    promoted: bool = False,
    ranked: bool = False,
) -> str:
    if passed:
        if promoted:
            return (
                "Runtime static + smoke validation passed; ranked selection chose this "
                "candidate and promoted it through the explicit shell."
            )
        if ranked:
            return (
                "Runtime static + smoke validation passed; ranked selection kept this "
                "candidate eligible for explicit promotion."
            )
        return "Runtime static + smoke validation passed; selected candidate is ready for explicit promotion."
    return "Runtime static/smoke validation failed: " + "; ".join(errors[:5])


def evaluate_module_synthesis_bundle(bundle: SynthesisBundle) -> SynthesisBundle:
    """Run static/smoke validation and ranked selection over a module bundle."""

    if not bundle.candidates:
        raise ValueError("Module synthesis bundle is missing candidates")
    if not bundle.candidate_workspaces:
        raise ValueError("Module synthesis bundle is missing candidate workspaces")
    if not bundle.evaluations:
        raise ValueError("Module synthesis bundle is missing evaluations")

    updated_candidates: list[CandidateRecord] = []
    updated_evaluations: list[EvaluationRecord] = []
    ranking_inputs: list[dict[str, Any]] = []

    multi_candidate = len(bundle.candidates) > 1
    phase = "AK-256" if multi_candidate else "AK-251"

    for candidate in bundle.candidates:
        workspace = _workspace_for_candidate(bundle, candidate.candidate_id)
        code = Path(workspace.artifact_path).read_text(encoding="utf-8")

        static_ok, static_checks, static_errors = _module_static_checks(
            bundle.request, code
        )
        smoke_ok, smoke_checks, smoke_errors = _module_smoke_checks(
            bundle.request, code
        )
        passed = static_ok and smoke_ok
        errors = [*static_errors, *smoke_errors]
        bonus = _selection_bonus(candidate)
        total_score = (100.0 if passed else 0.0) + bonus

        evaluation = _evaluation_for_candidate(bundle, candidate.candidate_id)
        evaluation_evidence = dict(evaluation.evidence)
        evaluation_evidence.update(
            {
                "phase": phase,
                "static": static_checks,
                "smoke": smoke_checks,
                "errors": errors,
                "workspace_id": workspace.workspace_id,
                "artifact_path": workspace.artifact_path,
                "checked_candidate_id": candidate.candidate_id,
                "selection_bonus": bonus,
                "selection_basis": candidate.metadata.get("selection_basis"),
                "variant_id": candidate.metadata.get("variant_id"),
                "variant_origin": candidate.lineage.get("variant_origin"),
                "variant_label": candidate.metadata.get("variant_label"),
                "ranking_components": {
                    "runtime_validation_gate": 100.0 if passed else 0.0,
                    "selection_bonus": bonus,
                    "ordinal_tiebreaker": -float(candidate.ordinal),
                },
                "total_score": total_score,
            }
        )
        updated_evaluation = evaluation.model_copy(
            update={
                "status": "passed" if passed else "failed",
                "score": total_score,
                "summary": _evaluation_summary(
                    passed=passed,
                    errors=errors,
                    ranked=multi_candidate,
                ),
                "checks": [
                    "python-parse",
                    "module-shape",
                    "signature-wiring",
                    "module-smoke",
                    "policy-score",
                ],
                "evidence": evaluation_evidence,
            }
        )

        candidate_metadata = dict(candidate.metadata)
        candidate_metadata.update(
            {
                "selection_ready": passed,
                "evaluation_id": updated_evaluation.evaluation_id,
                "validation_passed": static_ok,
                "smoke_passed": smoke_ok,
                "runtime_phase": phase,
                "ranking_score": total_score,
            }
        )
        updated_candidate = candidate.model_copy(
            update={
                "status": "rendered" if passed else "rejected",
                "metadata": candidate_metadata,
            }
        )

        updated_candidates.append(updated_candidate)
        updated_evaluations.append(updated_evaluation)
        ranking_inputs.append(
            {
                "candidate": updated_candidate,
                "evaluation": updated_evaluation,
                "passed": passed,
                "score": total_score,
            }
        )

    ranked_candidates = sorted(
        ranking_inputs,
        key=lambda item: (
            1 if item["passed"] else 0,
            float(item["score"]),
            -int(item["candidate"].ordinal),
        ),
        reverse=True,
    )
    selected_entry = next((item for item in ranked_candidates if item["passed"]), None)
    selected_candidate_id = (
        selected_entry["candidate"].candidate_id if selected_entry is not None else None
    )
    rank_map = {
        item["candidate"].candidate_id: index
        for index, item in enumerate(ranked_candidates, start=1)
    }
    ranked_payload = []
    for index, item in enumerate(ranked_candidates, start=1):
        payload = _ranking_entry(
            candidate=item["candidate"],
            evaluation=item["evaluation"],
            passed=bool(item["passed"]),
        )
        payload["rank"] = index
        ranked_payload.append(payload)

    final_candidates: list[CandidateRecord] = []
    for candidate in updated_candidates:
        metadata = dict(candidate.metadata)
        metadata.update(
            {
                "rank": rank_map[candidate.candidate_id],
                "winning_candidate_id": selected_candidate_id,
            }
        )
        status = candidate.status
        if candidate.candidate_id == selected_candidate_id:
            status = "selected"
        final_candidates.append(
            candidate.model_copy(update={"status": status, "metadata": metadata})
        )

    updated_shell = bundle.promotion_shell
    if updated_shell is not None:
        shell_metadata = dict(updated_shell.metadata)
        shell_metadata.update(
            {
                "ranked_candidates": ranked_payload,
                "policy_id": bundle.selection_policy.policy_id,
                "policy_version": bundle.selection_policy.policy_version,
                "selection_pending": selected_candidate_id is None,
            }
        )
        if selected_candidate_id is not None:
            selected_workspace = _workspace_for_candidate(bundle, selected_candidate_id)
            selected_evaluation = next(
                item["evaluation"]
                for item in ranked_candidates
                if item["candidate"].candidate_id == selected_candidate_id
            )
            shell_metadata.update(
                {
                    "evaluation_id": selected_evaluation.evaluation_id,
                    "evaluation_status": selected_evaluation.status,
                    "source_artifact_path": selected_workspace.artifact_path,
                    "workspace_id": selected_workspace.workspace_id,
                    "selected_rank": 1,
                    "selection_score": selected_evaluation.score,
                }
            )
            updated_shell = updated_shell.model_copy(
                update={
                    "selected_candidate_id": selected_candidate_id,
                    "staging_path": selected_workspace.artifact_path,
                    "status": "ready",
                    "metadata": shell_metadata,
                }
            )
        else:
            shell_metadata["evaluation_status"] = "failed"
            updated_shell = updated_shell.model_copy(
                update={
                    "selected_candidate_id": None,
                    "status": "withheld",
                    "metadata": shell_metadata,
                }
            )

    pass_count = sum(1 for item in updated_evaluations if item.status == "passed")
    selected_score = (
        selected_entry["evaluation"].score if selected_entry is not None else None
    )
    decision_metadata = dict(bundle.promotion_decision.metadata)
    decision_metadata.update(
        {
            "evaluation_status": "passed"
            if selected_candidate_id is not None
            else "failed",
            "validation_pass_count": pass_count,
            "validation_total": len(updated_evaluations),
            "selected_candidate_id": selected_candidate_id,
            "selected_rank": 1 if selected_candidate_id is not None else None,
            "selected_score": selected_score,
            "ranked_candidates": ranked_payload,
            "selection_phase": phase,
        }
    )
    updated_decision = bundle.promotion_decision.model_copy(
        update={
            "candidate_id": selected_candidate_id,
            "outcome": "withheld" if selected_candidate_id is not None else "rejected",
            "rationale": (
                f"Ranked {len(final_candidates)} candidates under "
                f"{bundle.selection_policy.policy_id}; selected {selected_candidate_id} "
                f"after {pass_count}/{len(updated_evaluations)} passed runtime validation."
                if selected_candidate_id is not None
                else (
                    f"No candidate passed runtime validation under "
                    f"{bundle.selection_policy.policy_id}; promotion remains rejected."
                )
            ),
            "evaluation_ids": [item.evaluation_id for item in updated_evaluations],
            "metadata": decision_metadata,
        }
    )

    return bundle.model_copy(
        update={
            "candidates": final_candidates,
            "evaluations": updated_evaluations,
            "promotion_shell": updated_shell,
            "promotion_decision": updated_decision,
        }
    )


def module_synthesis_run_summary(bundle: SynthesisBundle) -> dict[str, Any]:
    """Return receipt-friendly summary fields for the current module synthesis run."""

    selected_candidate_id = (
        bundle.promotion_shell.selected_candidate_id
        if bundle.promotion_shell is not None
        else bundle.promotion_decision.candidate_id
    )
    selected_evaluation = None
    if selected_candidate_id is not None:
        selected_evaluation = next(
            (
                item
                for item in bundle.evaluations
                if item.candidate_id == selected_candidate_id
            ),
            None,
        )
    validation_pass_count = sum(
        1 for item in bundle.evaluations if item.status == "passed"
    )
    smoke_pass_count = sum(
        1
        for item in bundle.evaluations
        if bool((item.evidence.get("smoke") or {}).get("module-smoke"))
    )
    ranked_candidates = bundle.promotion_decision.metadata.get("ranked_candidates")
    ranked_candidate_ids = (
        [
            item.get("candidate_id")
            for item in ranked_candidates
            if isinstance(item, dict) and item.get("candidate_id")
        ]
        if isinstance(ranked_candidates, list)
        else []
    )
    selected_rank = None
    if isinstance(ranked_candidates, list):
        for item in ranked_candidates:
            if (
                isinstance(item, dict)
                and item.get("candidate_id") == selected_candidate_id
                and isinstance(item.get("rank"), int)
            ):
                selected_rank = item["rank"]
                break

    return {
        "run_kind": "module-gen",
        "backend": "synthesis_runtime",
        "strategy_id": bundle.request.strategy_id,
        "strategy_version": bundle.request.strategy_version,
        "candidate_count": len(bundle.candidates),
        "selected_candidate_id": selected_candidate_id,
        "selected_candidate_rank": selected_rank,
        "ranked_candidate_ids": ranked_candidate_ids,
        "ranking_policy_id": bundle.selection_policy.policy_id,
        "ranking_policy_version": bundle.selection_policy.policy_version,
        "validation_pass_count": validation_pass_count,
        "validation_total": len(bundle.evaluations),
        "validation_pass_rate": (
            validation_pass_count / len(bundle.evaluations)
            if bundle.evaluations
            else 0.0
        ),
        "smoke_pass_count": smoke_pass_count,
        "smoke_total": len(bundle.evaluations),
        "smoke_pass_rate": (
            smoke_pass_count / len(bundle.evaluations) if bundle.evaluations else 0.0
        ),
        "evaluation_status": (
            selected_evaluation.status
            if selected_evaluation is not None
            else ("failed" if bundle.evaluations else "missing")
        ),
        "promotion_status": (
            bundle.promotion_shell.status
            if bundle.promotion_shell is not None
            else bundle.promotion_decision.outcome
        ),
        "promotion_outcome": bundle.promotion_decision.outcome,
    }


def execute_module_synthesis_bundle(
    spec: ModuleSpec,
    *,
    code: Optional[str] = None,
    candidate_sources: Optional[list[dict[str, Any]]] = None,
    use_signature: bool = False,
    strategy_id: Optional[str] = None,
    strategy_version: str = "v0",
    workspace_root: Optional[Path] = None,
    promotion_target: Optional[Path] = None,
    strategy_metadata: Optional[dict[str, Any]] = None,
) -> SynthesisBundle:
    """Materialize, validate, and optionally promote a module synthesis bundle."""

    bundle = materialize_module_synthesis_bundle(
        spec,
        code=code,
        candidate_sources=candidate_sources,
        use_signature=use_signature,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        workspace_root=workspace_root,
        promotion_target=promotion_target,
        strategy_metadata=strategy_metadata,
    )
    evaluated = evaluate_module_synthesis_bundle(bundle)
    if promotion_target is None:
        return evaluated

    selected_candidate_id = (
        evaluated.promotion_shell.selected_candidate_id
        if evaluated.promotion_shell is not None
        else evaluated.promotion_decision.candidate_id
    )
    if selected_candidate_id is None:
        return evaluated

    selected_evaluation = _evaluation_for_candidate(evaluated, selected_candidate_id)
    if selected_evaluation.status != "passed":
        return evaluated

    promoted = promote_selected_module_candidate(
        evaluated,
        target_path=promotion_target,
    )
    updated_evaluations = [
        evaluation.model_copy(
            update={
                "summary": _evaluation_summary(
                    passed=True,
                    errors=[],
                    promoted=(evaluation.candidate_id == selected_candidate_id),
                    ranked=len(promoted.candidates) > 1,
                )
            }
        )
        if evaluation.candidate_id == selected_candidate_id
        else evaluation
        for evaluation in promoted.evaluations
    ]
    return promoted.model_copy(update={"evaluations": updated_evaluations})


def _updated_decision(
    decision: PromotionDecision,
    *,
    candidate_id: str,
    promoted_path: Path,
) -> PromotionDecision:
    metadata = dict(decision.metadata)
    metadata["promoted_path"] = str(promoted_path)
    metadata["selected_candidate_id"] = candidate_id
    return decision.model_copy(
        update={
            "candidate_id": candidate_id,
            "outcome": "promoted",
            "rationale": "Promoted via explicit module synthesis shell.",
            "metadata": metadata,
        }
    )


def promote_selected_module_candidate(
    bundle: SynthesisBundle,
    *,
    candidate_id: Optional[str] = None,
    target_path: Optional[Path] = None,
) -> SynthesisBundle:
    """Promote the explicitly selected candidate through the promotion shell."""

    shell = bundle.promotion_shell
    selected_candidate_id = (
        shell.selected_candidate_id if shell is not None else None
    ) or bundle.promotion_decision.candidate_id
    if selected_candidate_id is None:
        raise ValueError("No selected candidate available for promotion")
    if candidate_id is not None and candidate_id != selected_candidate_id:
        raise ValueError("candidate_id does not match the selected candidate")

    chosen_candidate_id = selected_candidate_id
    candidate = _candidate_by_id(bundle, chosen_candidate_id)
    if candidate.status not in {"selected", "promoted"}:
        raise ValueError("Selected candidate is not promotion-ready")
    evaluation = _evaluation_for_candidate(bundle, chosen_candidate_id)
    if evaluation.status != "passed":
        raise ValueError("Selected candidate has not passed evaluation")

    workspace = _workspace_for_candidate(bundle, chosen_candidate_id)
    source_path = Path(workspace.artifact_path)
    if not source_path.exists():
        raise FileNotFoundError(source_path)

    destination = (
        target_path.expanduser().resolve()
        if target_path is not None
        else Path(
            (
                shell.target_path
                if shell and shell.target_path
                else workspace.artifact_path
            )
        )
        .expanduser()
        .resolve()
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination)

    updated_candidate_metadata = dict(candidate.metadata)
    updated_candidate_metadata["promoted_path"] = str(destination)
    updated_candidate = candidate.model_copy(
        update={
            "status": "promoted",
            "metadata": updated_candidate_metadata,
        }
    )

    updated_workspace_metadata = dict(workspace.metadata)
    updated_workspace_metadata["promoted_path"] = str(destination)
    updated_workspace = workspace.model_copy(
        update={
            "status": "promoted",
            "metadata": updated_workspace_metadata,
        }
    )

    updated_shell = None
    if shell is not None:
        shell_metadata = dict(shell.metadata)
        shell_metadata["promoted_from"] = str(source_path)
        updated_shell = shell.model_copy(
            update={
                "selected_candidate_id": chosen_candidate_id,
                "staging_path": str(source_path),
                "target_path": str(destination),
                "status": "promoted",
                "metadata": shell_metadata,
            }
        )

    return bundle.model_copy(
        update={
            "candidates": [
                updated_candidate if item.candidate_id == chosen_candidate_id else item
                for item in bundle.candidates
            ],
            "candidate_workspaces": [
                updated_workspace if item.candidate_id == chosen_candidate_id else item
                for item in bundle.candidate_workspaces
            ],
            "promotion_shell": updated_shell,
            "promotion_decision": _updated_decision(
                bundle.promotion_decision,
                candidate_id=chosen_candidate_id,
                promoted_path=destination,
            ),
        }
    )

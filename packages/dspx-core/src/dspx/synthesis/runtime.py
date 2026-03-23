from __future__ import annotations

import ast
import json
import os
import shutil
from pathlib import Path
from typing import Any, Optional

from dspx.cache import cache_dir, make_key
from dspx.dtos import ModuleSpec

from .contracts import (
    CandidateRecord,
    CandidateWorkspace,
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


def materialize_module_synthesis_bundle(
    spec: ModuleSpec,
    *,
    code: str,
    use_signature: bool = False,
    strategy_id: str = "module.single_candidate.template",
    strategy_version: str = "v0",
    workspace_root: Optional[Path] = None,
    promotion_target: Optional[Path] = None,
    strategy_metadata: Optional[dict[str, Any]] = None,
) -> SynthesisBundle:
    """Build a synthesis bundle and materialize its scratch workspace shell."""

    request = build_module_synthesis_request(
        spec,
        use_signature=use_signature,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
    )
    strategy = build_module_strategy_record(request, metadata=strategy_metadata)
    workspace_base = (
        workspace_root.expanduser().resolve()
        if workspace_root is not None
        else (synthesis_workspace_dir() / request.request_id).resolve()
    )
    candidate = build_module_candidate_record(request, code=code)
    workspace = materialize_module_candidate_workspace(
        request,
        candidate,
        code=code,
        strategy=strategy,
        workspace_root=workspace_base,
    )
    candidate = _attach_workspace_metadata(candidate, workspace, strategy)
    evaluation = build_module_evaluation_record(candidate, workspace=workspace)
    policy = build_module_selection_policy()
    shell_target = _promoted_target_path(
        request,
        workspace_base,
        target_path=promotion_target,
    )
    promotion_shell = build_module_promotion_shell(
        request,
        candidate,
        workspace,
        target_path=str(shell_target),
    )
    promotion_decision = build_module_promotion_decision(
        request,
        candidate,
        evaluation,
        policy,
        promotion_shell=promotion_shell,
    )
    return SynthesisBundle(
        request=request,
        strategy=strategy,
        candidates=[candidate],
        candidate_workspaces=[workspace],
        evaluations=[evaluation],
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
    checks: dict[str, bool] = {"module-smoke": False}
    errors: list[str] = []
    namespace: dict[str, Any] = {}

    try:
        exec(code, namespace, namespace)
    except Exception as exc:
        errors.append(f"exec_error:{exc}")
        return False, checks, errors

    try:
        import dspy
    except Exception as exc:  # pragma: no cover - environment issue
        errors.append(f"dspy_import_error:{exc}")
        return False, checks, errors

    expected_module = _module_class_name(request)
    module_cls = namespace.get(expected_module)
    if not isinstance(module_cls, type):
        errors.append(f"class_not_found:{expected_module}")
        return False, checks, errors

    try:
        if not issubclass(module_cls, dspy.Module):
            errors.append("class_not_dspy_module")
    except Exception:
        errors.append("class_not_dspy_module")

    if request.spec.use_signature:
        expected_signature = _signature_class_name(request)
        signature_cls = namespace.get(expected_signature)
        if not isinstance(signature_cls, type):
            errors.append(f"signature_not_found:{expected_signature}")
        else:
            try:
                if not issubclass(signature_cls, dspy.Signature):
                    errors.append("signature_not_dspy_signature")
            except Exception:
                errors.append("signature_not_dspy_signature")

    build_student = namespace.get("build_student")
    if not callable(build_student):
        errors.append("build_student_missing")
    else:
        try:
            student = build_student(use_cot=False)
            if not isinstance(student, dspy.Module):
                errors.append("build_student_not_module")
            if getattr(student, "predict", None) is None:
                errors.append("predict_missing")
        except Exception as exc:
            errors.append(f"build_student_error:{exc}")

    inputs, outputs = _expected_io(request)
    io_spec = namespace.get("io_spec")
    if not callable(io_spec):
        errors.append("io_spec_missing")
    else:
        try:
            if io_spec() != {"inputs": inputs, "outputs": outputs}:
                errors.append("io_spec_mismatch")
        except Exception as exc:
            errors.append(f"io_spec_error:{exc}")

    output_weights = namespace.get("output_weights")
    if not callable(output_weights):
        errors.append("output_weights_missing")
    else:
        try:
            weights = output_weights()
            if not isinstance(weights, dict) or set(weights.keys()) != set(outputs):
                errors.append("output_weights_mismatch")
        except Exception as exc:
            errors.append(f"output_weights_error:{exc}")

    normalize_output = namespace.get("normalize_output")
    if not callable(normalize_output):
        errors.append("normalize_output_missing")
    else:
        try:
            normalized = normalize_output(
                "key",
                "gold",
                "pred",
                pred_name="pred",
                pred_trace=None,
            )
            if not (
                isinstance(normalized, tuple)
                and len(normalized) == 2
                and normalized == ("gold", "pred")
            ):
                errors.append("normalize_output_mismatch")
        except Exception as exc:
            errors.append(f"normalize_output_error:{exc}")

    checks["module-smoke"] = len(errors) == 0
    return checks["module-smoke"], checks, errors


def _evaluation_summary(
    *,
    passed: bool,
    errors: list[str],
    promoted: bool = False,
) -> str:
    if passed:
        if promoted:
            return "Runtime static + smoke validation passed; selected candidate promoted through the explicit shell."
        return "Runtime static + smoke validation passed; selected candidate is ready for explicit promotion."
    return "Runtime static/smoke validation failed: " + "; ".join(errors[:5])


def evaluate_module_synthesis_bundle(bundle: SynthesisBundle) -> SynthesisBundle:
    """Run the AK-251 static + smoke validation pass over a module bundle."""

    if not bundle.candidates:
        raise ValueError("Module synthesis bundle is missing candidates")
    if not bundle.candidate_workspaces:
        raise ValueError("Module synthesis bundle is missing candidate workspaces")
    if not bundle.evaluations:
        raise ValueError("Module synthesis bundle is missing evaluations")

    candidate = bundle.candidates[0]
    workspace = _workspace_for_candidate(bundle, candidate.candidate_id)
    code = Path(workspace.artifact_path).read_text(encoding="utf-8")

    static_ok, static_checks, static_errors = _module_static_checks(
        bundle.request, code
    )
    smoke_ok, smoke_checks, smoke_errors = _module_smoke_checks(bundle.request, code)
    passed = static_ok and smoke_ok
    errors = [*static_errors, *smoke_errors]
    check_results = {
        "python-parse": bool(static_checks.get("python-parse")),
        "module-shape": bool(static_checks.get("module-shape")),
        "signature-wiring": bool(static_checks.get("signature-wiring")),
        "module-smoke": bool(smoke_checks.get("module-smoke")),
    }

    evaluation = bundle.evaluations[0]
    evaluation_evidence = dict(evaluation.evidence)
    evaluation_evidence.update(
        {
            "phase": "AK-251",
            "static": static_checks,
            "smoke": smoke_checks,
            "errors": errors,
            "workspace_id": workspace.workspace_id,
            "artifact_path": workspace.artifact_path,
            "checked_candidate_id": candidate.candidate_id,
        }
    )
    updated_evaluation = evaluation.model_copy(
        update={
            "status": "passed" if passed else "failed",
            "score": 100.0 if passed else 0.0,
            "summary": _evaluation_summary(passed=passed, errors=errors),
            "checks": list(check_results.keys()),
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
            "runtime_phase": "AK-251",
        }
    )
    updated_candidate = candidate.model_copy(
        update={
            "status": "selected" if passed else "rejected",
            "metadata": candidate_metadata,
        }
    )

    updated_shell = bundle.promotion_shell
    if updated_shell is not None:
        shell_metadata = dict(updated_shell.metadata)
        shell_metadata.update(
            {
                "evaluation_id": updated_evaluation.evaluation_id,
                "evaluation_status": updated_evaluation.status,
            }
        )
        updated_shell = updated_shell.model_copy(
            update={
                "status": "ready" if passed else "withheld",
                "metadata": shell_metadata,
            }
        )

    decision_metadata = dict(bundle.promotion_decision.metadata)
    decision_metadata.update(
        {
            "evaluation_status": updated_evaluation.status,
            "validation_passed": static_ok,
            "smoke_passed": smoke_ok,
        }
    )
    updated_decision = bundle.promotion_decision.model_copy(
        update={
            "candidate_id": updated_candidate.candidate_id,
            "outcome": "withheld" if passed else "rejected",
            "rationale": _evaluation_summary(passed=passed, errors=errors),
            "evaluation_ids": [updated_evaluation.evaluation_id],
            "metadata": decision_metadata,
        }
    )

    return bundle.model_copy(
        update={
            "candidates": [updated_candidate],
            "evaluations": [updated_evaluation],
            "promotion_shell": updated_shell,
            "promotion_decision": updated_decision,
        }
    )


def module_synthesis_run_summary(bundle: SynthesisBundle) -> dict[str, Any]:
    """Return receipt-friendly summary fields for the current module synthesis run."""

    evaluation = bundle.evaluations[0] if bundle.evaluations else None
    evaluation_evidence = dict(evaluation.evidence) if evaluation is not None else {}
    smoke_checks = evaluation_evidence.get("smoke")
    smoke_passed = (
        bool(smoke_checks.get("module-smoke"))
        if isinstance(smoke_checks, dict)
        else bool(evaluation and evaluation.status == "passed")
    )
    selected_candidate_id = (
        bundle.promotion_shell.selected_candidate_id
        if bundle.promotion_shell is not None
        else bundle.promotion_decision.candidate_id
    )
    return {
        "run_kind": "module-gen",
        "backend": "synthesis_runtime",
        "strategy_id": bundle.request.strategy_id,
        "strategy_version": bundle.request.strategy_version,
        "candidate_count": len(bundle.candidates),
        "selected_candidate_id": selected_candidate_id,
        "validation_pass_count": 1
        if evaluation and evaluation.status == "passed"
        else 0,
        "validation_total": 1,
        "validation_pass_rate": 1.0
        if evaluation and evaluation.status == "passed"
        else 0.0,
        "smoke_pass_count": 1 if smoke_passed else 0,
        "smoke_total": 1,
        "smoke_pass_rate": 1.0 if smoke_passed else 0.0,
        "evaluation_status": evaluation.status if evaluation is not None else "missing",
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
    code: str,
    use_signature: bool = False,
    strategy_id: str = "module.single_candidate.template",
    strategy_version: str = "v0",
    workspace_root: Optional[Path] = None,
    promotion_target: Optional[Path] = None,
    strategy_metadata: Optional[dict[str, Any]] = None,
) -> SynthesisBundle:
    """Materialize, validate, and optionally promote a module synthesis bundle."""

    bundle = materialize_module_synthesis_bundle(
        spec,
        code=code,
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
    if not evaluated.evaluations or evaluated.evaluations[0].status != "passed":
        return evaluated
    promoted = promote_selected_module_candidate(
        evaluated,
        target_path=promotion_target,
    )
    updated_evaluation = promoted.evaluations[0].model_copy(
        update={
            "summary": _evaluation_summary(
                passed=True,
                errors=[],
                promoted=True,
            )
        }
    )
    return promoted.model_copy(update={"evaluations": [updated_evaluation]})


def _updated_decision(
    decision: PromotionDecision,
    *,
    candidate_id: str,
    promoted_path: Path,
) -> PromotionDecision:
    metadata = dict(decision.metadata)
    metadata["promoted_path"] = str(promoted_path)
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
    chosen_candidate_id = (
        candidate_id
        or (shell.selected_candidate_id if shell is not None else None)
        or bundle.promotion_decision.candidate_id
    )
    if chosen_candidate_id is None:
        raise ValueError("No selected candidate available for promotion")

    candidate = _candidate_by_id(bundle, chosen_candidate_id)
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
                "staging_path": str(destination),
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

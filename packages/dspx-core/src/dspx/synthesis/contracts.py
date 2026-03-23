from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from dspx.cache import make_key, sha256_text
from dspx.dtos import ModuleSpec


class ModuleFieldIR(BaseModel):
    """Structured field description for module synthesis IR."""

    model_config = ConfigDict(frozen=True)

    name: str
    role: Literal["input", "output"]
    ordinal: int = Field(default=0, ge=0)
    description: Optional[str] = None


class ModuleSpecIR(BaseModel):
    """Structured intermediate representation for module generation."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["module"] = "module"
    name: str
    description: Optional[str] = None
    inputs: List[ModuleFieldIR] = Field(default_factory=list)
    outputs: List[ModuleFieldIR] = Field(default_factory=list)
    use_signature: bool = False
    template_version: Optional[str] = None
    options: Dict[str, Any] = Field(default_factory=dict)


class SynthesisRequest(BaseModel):
    """Top-level synthesis intent for a single artifact generation attempt."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    artifact_kind: Literal["module"] = "module"
    source_command: str = "module-gen"
    goal: str
    strategy_id: str = "module.single_candidate.template"
    strategy_version: str = "v0"
    spec: ModuleSpecIR
    constraints: Dict[str, Any] = Field(default_factory=dict)
    options: Dict[str, Any] = Field(default_factory=dict)


class StrategyRecord(BaseModel):
    """Persisted strategy metadata for a synthesis request."""

    model_config = ConfigDict(frozen=True)

    strategy_id: str
    strategy_version: str
    source_command: str = "module-gen"
    persistence: Literal["metadata", "workspace_manifest"] = "workspace_manifest"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CandidateArtifact(BaseModel):
    """Artifact-level materialization details for a synthesis candidate."""

    model_config = ConfigDict(frozen=True)

    language: Literal["python"] = "python"
    content_hash: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CandidateRecord(BaseModel):
    """A rendered candidate plus lineage metadata."""

    model_config = ConfigDict(frozen=True)

    candidate_id: str
    request_id: str
    ordinal: int = Field(default=0, ge=0)
    status: Literal[
        "draft",
        "rendered",
        "selected",
        "promoted",
        "rejected",
    ] = "rendered"
    strategy_id: str
    strategy_version: str
    spec: ModuleSpecIR
    artifact: CandidateArtifact
    lineage: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CandidateWorkspace(BaseModel):
    """Scratch-space boundary for an individual synthesis candidate."""

    model_config = ConfigDict(frozen=True)

    workspace_id: str
    request_id: str
    candidate_id: str
    root_path: str
    scratch_path: str
    artifact_path: str
    manifest_path: str
    status: Literal["materialized", "promoted", "cleaned"] = "materialized"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EvaluationRecord(BaseModel):
    """Evaluation outcome shell for a synthesis candidate."""

    model_config = ConfigDict(frozen=True)

    evaluation_id: str
    candidate_id: str
    evaluator: str
    status: Literal["pending", "passed", "failed", "skipped"] = "pending"
    score: Optional[float] = None
    summary: Optional[str] = None
    checks: List[str] = Field(default_factory=list)
    evidence: Dict[str, Any] = Field(default_factory=dict)


class SelectionPolicy(BaseModel):
    """Named selection policy contract for choosing a candidate."""

    model_config = ConfigDict(frozen=True)

    policy_id: str
    policy_version: str = "v0"
    mode: Literal["single_best", "manual_review", "multi_candidate_ranked"] = (
        "single_best"
    )
    pass_requirements: List[str] = Field(default_factory=list)
    tie_breakers: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PromotionShell(BaseModel):
    """Explicit promotion boundary for a selected candidate."""

    model_config = ConfigDict(frozen=True)

    shell_id: str
    request_id: str
    selected_candidate_id: Optional[str] = None
    staging_path: str
    target_path: Optional[str] = None
    status: Literal["pending", "ready", "promoted", "withheld"] = "pending"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PromotionDecision(BaseModel):
    """Promotion boundary decision for a selected synthesis candidate."""

    model_config = ConfigDict(frozen=True)

    decision_id: str
    request_id: str
    candidate_id: Optional[str] = None
    policy_id: str
    policy_version: str
    outcome: Literal["pending", "promoted", "withheld", "rejected"] = "withheld"
    rationale: str
    evaluation_ids: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SynthesisBundle(BaseModel):
    """Contract bundle for a synthesis attempt."""

    model_config = ConfigDict(frozen=True)

    request: SynthesisRequest
    strategy: Optional[StrategyRecord] = None
    candidates: List[CandidateRecord] = Field(default_factory=list)
    candidate_workspaces: List[CandidateWorkspace] = Field(default_factory=list)
    evaluations: List[EvaluationRecord] = Field(default_factory=list)
    selection_policy: SelectionPolicy
    promotion_shell: Optional[PromotionShell] = None
    promotion_decision: PromotionDecision


def _stable_id(prefix: str, payload: Dict[str, Any]) -> str:
    return f"{prefix}-{make_key(payload)[:12]}"


def module_spec_to_ir(spec: ModuleSpec, *, use_signature: bool = False) -> ModuleSpecIR:
    """Convert the legacy module spec into a structured synthesis IR."""

    options = dict(spec.options or {})
    template_version = options.get("template_version")
    if template_version is not None and not isinstance(template_version, str):
        template_version = str(template_version)

    return ModuleSpecIR(
        name=spec.name,
        description=spec.description,
        inputs=[
            ModuleFieldIR(name=name, role="input", ordinal=index)
            for index, name in enumerate(spec.inputs or [])
        ],
        outputs=[
            ModuleFieldIR(name=name, role="output", ordinal=index)
            for index, name in enumerate(spec.outputs or [])
        ],
        use_signature=bool(use_signature),
        template_version=template_version,
        options=options,
    )


def build_module_synthesis_request(
    spec: ModuleSpec,
    *,
    use_signature: bool = False,
    strategy_id: str = "module.single_candidate.template",
    strategy_version: str = "v0",
) -> SynthesisRequest:
    """Build the V9-compatible request envelope for module synthesis."""

    ir = module_spec_to_ir(spec, use_signature=use_signature)
    request_payload = {
        "artifact_kind": "module",
        "source_command": "module-gen",
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "spec": ir.model_dump(mode="json"),
    }
    goal = spec.description or f"Generate module scaffold for {spec.name}"
    return SynthesisRequest(
        request_id=_stable_id("sreq", request_payload),
        goal=goal,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        spec=ir,
        constraints={
            "preserve_cli_surface": True,
            "artifact_language": "python",
            "candidate_budget": 1,
        },
        options={
            "use_signature": bool(use_signature),
            "template_version": ir.template_version,
        },
    )


def build_module_strategy_record(
    request: SynthesisRequest,
    *,
    metadata: Optional[Dict[str, Any]] = None,
) -> StrategyRecord:
    """Build persisted strategy metadata for the current module synthesis path."""

    merged_metadata = {
        "artifact_kind": request.artifact_kind,
        "goal": request.goal,
        "candidate_budget": request.constraints.get("candidate_budget"),
        "template_version": request.spec.template_version,
        "use_signature": request.spec.use_signature,
        "render_backend": "template",
        "workspace_mode": "scratch",
    }
    if metadata:
        merged_metadata.update(metadata)
    return StrategyRecord(
        strategy_id=request.strategy_id,
        strategy_version=request.strategy_version,
        source_command=request.source_command,
        persistence="workspace_manifest",
        metadata=merged_metadata,
    )


def build_module_candidate_record(
    request: SynthesisRequest,
    *,
    code: str,
    ordinal: int = 0,
) -> CandidateRecord:
    """Build a rendered candidate record for the current one-candidate module path."""

    artifact = CandidateArtifact(
        content_hash=sha256_text(code),
        metadata={
            "line_count": len(code.splitlines()),
            "render_backend": "template",
            "template_version": request.spec.template_version,
            "uses_signature": request.spec.use_signature,
        },
    )
    candidate_payload = {
        "request_id": request.request_id,
        "ordinal": ordinal,
        "content_hash": artifact.content_hash,
    }
    return CandidateRecord(
        candidate_id=_stable_id("cand", candidate_payload),
        request_id=request.request_id,
        ordinal=ordinal,
        strategy_id=request.strategy_id,
        strategy_version=request.strategy_version,
        spec=request.spec,
        artifact=artifact,
        lineage={"request_id": request.request_id},
        metadata={"selection_ready": False},
    )


def build_module_evaluation_record(
    candidate: CandidateRecord,
    *,
    phase: str = "AK-250",
    workspace: Optional[CandidateWorkspace] = None,
) -> EvaluationRecord:
    """Build the placeholder evaluation contract for the MVP candidate path."""

    evaluation_payload = {
        "candidate_id": candidate.candidate_id,
        "evaluator": "module.static.validation",
    }
    evidence: Dict[str, Any] = {"phase": phase}
    if workspace is not None:
        evidence["workspace_id"] = workspace.workspace_id
        evidence["artifact_path"] = workspace.artifact_path
    return EvaluationRecord(
        evaluation_id=_stable_id("eval", evaluation_payload),
        candidate_id=candidate.candidate_id,
        evaluator="module.static.validation",
        status="pending",
        summary=(
            "Runtime shell only: static/smoke execution lands in follow-on module "
            "synthesis routing slices."
        ),
        checks=[
            "python-parse",
            "module-shape",
            "signature-wiring",
        ],
        evidence=evidence,
    )


def build_module_selection_policy() -> SelectionPolicy:
    """Build the named selection policy contract for the initial module path."""

    return SelectionPolicy(
        policy_id="module.v7.single-candidate-pass-through",
        policy_version="v0",
        mode="single_best",
        pass_requirements=[
            "render succeeds",
            "all required evaluations pass",
            "promotion invoked for the selected candidate only",
        ],
        tie_breakers=[
            "highest score",
            "lowest ordinal",
        ],
        metadata={
            "candidate_limit": 1,
            "promote_without_evaluations": False,
            "promotion_boundary": "explicit_shell",
        },
    )


def build_module_promotion_shell(
    request: SynthesisRequest,
    candidate: CandidateRecord,
    workspace: CandidateWorkspace,
    *,
    target_path: Optional[str] = None,
) -> PromotionShell:
    """Build the explicit promotion shell for the selected module candidate."""

    shell_target = target_path or str(workspace.artifact_path)
    shell_payload = {
        "request_id": request.request_id,
        "candidate_id": candidate.candidate_id,
        "target_path": shell_target,
    }
    return PromotionShell(
        shell_id=_stable_id("shell", shell_payload),
        request_id=request.request_id,
        selected_candidate_id=candidate.candidate_id,
        staging_path=shell_target,
        target_path=shell_target,
        status="pending",
        metadata={
            "requires_selected_candidate": True,
            "source_artifact_path": workspace.artifact_path,
            "workspace_id": workspace.workspace_id,
        },
    )


def build_module_promotion_decision(
    request: SynthesisRequest,
    candidate: CandidateRecord,
    evaluation: EvaluationRecord,
    policy: SelectionPolicy,
    *,
    promotion_shell: Optional[PromotionShell] = None,
) -> PromotionDecision:
    """Build the explicit promotion boundary decision for the current candidate."""

    decision_payload = {
        "request_id": request.request_id,
        "candidate_id": candidate.candidate_id,
        "policy_id": policy.policy_id,
        "evaluation_id": evaluation.evaluation_id,
    }
    metadata: Dict[str, Any] = {
        "selected_candidate_id": candidate.candidate_id,
        "target": "module artifact",
    }
    if promotion_shell is not None:
        metadata.update(
            {
                "promotion_shell_id": promotion_shell.shell_id,
                "promotion_target_path": promotion_shell.target_path,
            }
        )
    return PromotionDecision(
        decision_id=_stable_id("promote", decision_payload),
        request_id=request.request_id,
        candidate_id=candidate.candidate_id,
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        outcome="withheld",
        rationale=(
            "AK-250 establishes scratch workspaces and an explicit promotion shell, "
            "but promotion stays withheld until the runtime selects and invokes the "
            "chosen candidate."
        ),
        evaluation_ids=[evaluation.evaluation_id],
        metadata=metadata,
    )


def build_module_synthesis_bundle(
    spec: ModuleSpec,
    *,
    code: str,
    use_signature: bool = False,
    strategy_id: str = "module.single_candidate.template",
    strategy_version: str = "v0",
) -> SynthesisBundle:
    """Build the contract bundle for the current module synthesis attempt."""

    request = build_module_synthesis_request(
        spec,
        use_signature=use_signature,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
    )
    strategy = build_module_strategy_record(request)
    candidate = build_module_candidate_record(request, code=code)
    evaluation = build_module_evaluation_record(candidate)
    policy = build_module_selection_policy()
    decision = build_module_promotion_decision(request, candidate, evaluation, policy)
    return SynthesisBundle(
        request=request,
        strategy=strategy,
        candidates=[candidate],
        evaluations=[evaluation],
        selection_policy=policy,
        promotion_decision=decision,
    )

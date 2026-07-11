# summary: "Defines module-synthesis IR, candidate/runtime/promotion models, stable identities, and contract builders."
# read_when:
#   - "Changing synthesis bundle schemas, lineage fields, selection policy, or promotion contract construction."

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


class CandidateAssembly(BaseModel):
    """Concrete runtime assembly for a candidate that can be executed or replayed."""

    model_config = ConfigDict(frozen=True)

    assembly_id: str
    request_id: str
    candidate_id: str
    artifact_kind: Literal["module"] = "module"
    surface_kinds: List[str] = Field(default_factory=lambda: ["module"])
    workspace_id: Optional[str] = None
    artifact_path: Optional[str] = None
    content_hash: str
    status: Literal["materialized", "selected", "promoted", "rejected"] = "materialized"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ExecutionEpisode(BaseModel):
    """Bounded runtime episode for executing a candidate assembly."""

    model_config = ConfigDict(frozen=True)

    episode_id: str
    request_id: str
    candidate_id: str
    assembly_id: str
    evaluator: str
    phase: str
    status: Literal["pending", "passed", "failed", "promoted", "rejected"] = "pending"
    score: Optional[float] = None
    summary: Optional[str] = None
    runtime_conditions: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ReceiptBundle(BaseModel):
    """Replay-oriented evidence bundle emitted for an execution episode."""

    model_config = ConfigDict(frozen=True)

    receipt_bundle_id: str
    request_id: str
    candidate_id: str
    assembly_id: str
    episode_id: str
    status: Literal["pending", "captured", "promoted", "rejected"] = "pending"
    evidence: Dict[str, Any] = Field(default_factory=dict)
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
    candidate_assemblies: List[CandidateAssembly] = Field(default_factory=list)
    execution_episodes: List[ExecutionEpisode] = Field(default_factory=list)
    receipt_bundles: List[ReceiptBundle] = Field(default_factory=list)
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
    strategy_id: Optional[str] = None,
    strategy_version: str = "v0",
    candidate_budget: int = 1,
) -> SynthesisRequest:
    """Build the V9-compatible request envelope for module synthesis."""

    ir = module_spec_to_ir(spec, use_signature=use_signature)
    candidate_budget = max(1, int(candidate_budget))
    resolved_strategy_id = strategy_id or (
        "module.multi_candidate.template"
        if candidate_budget > 1
        else "module.single_candidate.template"
    )
    request_payload = {
        "artifact_kind": "module",
        "source_command": "module-gen",
        "strategy_id": resolved_strategy_id,
        "strategy_version": strategy_version,
        "candidate_budget": candidate_budget,
        "spec": ir.model_dump(mode="json"),
    }
    goal = spec.description or f"Generate module scaffold for {spec.name}"
    return SynthesisRequest(
        request_id=_stable_id("sreq", request_payload),
        goal=goal,
        strategy_id=resolved_strategy_id,
        strategy_version=strategy_version,
        spec=ir,
        constraints={
            "preserve_cli_surface": True,
            "artifact_language": "python",
            "candidate_budget": candidate_budget,
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
        "runtime_spine_version": "v1",
        "fan_out_mode": (
            "ranked_candidates"
            if int(request.constraints.get("candidate_budget") or 1) > 1
            else "single_candidate"
        ),
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
    artifact_metadata: Optional[Dict[str, Any]] = None,
    candidate_metadata: Optional[Dict[str, Any]] = None,
    lineage: Optional[Dict[str, Any]] = None,
) -> CandidateRecord:
    """Build a rendered candidate record for the module synthesis path."""

    merged_artifact_metadata: Dict[str, Any] = {
        "line_count": len(code.splitlines()),
        "render_backend": "template",
        "template_version": request.spec.template_version,
        "uses_signature": request.spec.use_signature,
        "runtime_spine_version": "v1",
    }
    if artifact_metadata:
        merged_artifact_metadata.update(artifact_metadata)

    artifact = CandidateArtifact(
        content_hash=sha256_text(code),
        metadata=merged_artifact_metadata,
    )
    candidate_payload = {
        "request_id": request.request_id,
        "ordinal": ordinal,
        "content_hash": artifact.content_hash,
    }
    merged_lineage = {"request_id": request.request_id}
    if lineage:
        merged_lineage.update(lineage)
    merged_candidate_metadata = {
        "selection_ready": False,
        "runtime_spine_version": "v1",
    }
    if candidate_metadata:
        merged_candidate_metadata.update(candidate_metadata)

    return CandidateRecord(
        candidate_id=_stable_id("cand", candidate_payload),
        request_id=request.request_id,
        ordinal=ordinal,
        strategy_id=request.strategy_id,
        strategy_version=request.strategy_version,
        spec=request.spec,
        artifact=artifact,
        lineage=merged_lineage,
        metadata=merged_candidate_metadata,
    )


def build_module_candidate_assembly(
    request: SynthesisRequest,
    candidate: CandidateRecord,
    *,
    workspace: Optional[CandidateWorkspace] = None,
    strategy: Optional[StrategyRecord] = None,
) -> CandidateAssembly:
    """Build the first explicit runtime assembly for a module candidate."""

    assembly_payload = {
        "request_id": request.request_id,
        "candidate_id": candidate.candidate_id,
        "workspace_id": workspace.workspace_id if workspace is not None else None,
        "content_hash": candidate.artifact.content_hash,
    }
    metadata: Dict[str, Any] = {
        "source_command": request.source_command,
        "strategy_id": candidate.strategy_id,
        "strategy_version": candidate.strategy_version,
        "module_name": request.spec.name,
        "use_signature": request.spec.use_signature,
        "runtime_spine_version": "v1",
    }
    if strategy is not None:
        metadata["workspace_mode"] = strategy.metadata.get("workspace_mode")
    if workspace is not None:
        metadata["manifest_path"] = workspace.manifest_path
    return CandidateAssembly(
        assembly_id=_stable_id("assembly", assembly_payload),
        request_id=request.request_id,
        candidate_id=candidate.candidate_id,
        workspace_id=workspace.workspace_id if workspace is not None else None,
        artifact_path=workspace.artifact_path if workspace is not None else None,
        content_hash=candidate.artifact.content_hash,
        metadata=metadata,
    )


def build_module_execution_episode(
    request: SynthesisRequest,
    candidate: CandidateRecord,
    assembly: CandidateAssembly,
    *,
    phase: str = "AK-251",
    workspace: Optional[CandidateWorkspace] = None,
    selection_policy: Optional[SelectionPolicy] = None,
) -> ExecutionEpisode:
    """Build the first bounded execution episode shell for a candidate assembly."""

    episode_payload = {
        "assembly_id": assembly.assembly_id,
        "phase": phase,
        "evaluator": "module.runtime.validation",
    }
    runtime_conditions: Dict[str, Any] = {
        "source_command": request.source_command,
        "strategy_id": request.strategy_id,
        "strategy_version": request.strategy_version,
        "candidate_budget": request.constraints.get("candidate_budget"),
        "use_signature": request.spec.use_signature,
        "inputs": [field.name for field in request.spec.inputs],
        "outputs": [field.name for field in request.spec.outputs],
        "runtime_spine_version": "v1",
    }
    if workspace is not None:
        runtime_conditions["workspace_id"] = workspace.workspace_id
        runtime_conditions["artifact_path"] = workspace.artifact_path
    if selection_policy is not None:
        runtime_conditions["selection_policy_id"] = selection_policy.policy_id
        runtime_conditions["selection_policy_version"] = selection_policy.policy_version
    return ExecutionEpisode(
        episode_id=_stable_id("episode", episode_payload),
        request_id=request.request_id,
        candidate_id=candidate.candidate_id,
        assembly_id=assembly.assembly_id,
        evaluator="module.runtime.validation",
        phase=phase,
        summary="Pending runtime validation for the candidate assembly.",
        runtime_conditions=runtime_conditions,
        metadata={
            "module_name": request.spec.name,
            "runtime_spine_version": "v1",
        },
    )


def build_module_receipt_bundle(
    request: SynthesisRequest,
    candidate: CandidateRecord,
    assembly: CandidateAssembly,
    execution_episode: ExecutionEpisode,
    *,
    workspace: Optional[CandidateWorkspace] = None,
    strategy: Optional[StrategyRecord] = None,
) -> ReceiptBundle:
    """Build the replay-oriented receipt bundle shell for an execution episode."""

    receipt_payload = {
        "episode_id": execution_episode.episode_id,
        "candidate_id": candidate.candidate_id,
        "content_hash": candidate.artifact.content_hash,
    }
    evidence: Dict[str, Any] = {
        "phase": execution_episode.phase,
        "content_hash": candidate.artifact.content_hash,
    }
    metadata: Dict[str, Any] = {
        "strategy_id": candidate.strategy_id,
        "strategy_version": candidate.strategy_version,
        "runtime_spine_version": "v1",
    }
    if workspace is not None:
        evidence["artifact_path"] = workspace.artifact_path
        metadata["workspace_id"] = workspace.workspace_id
        metadata["manifest_path"] = workspace.manifest_path
    if strategy is not None:
        metadata["workspace_mode"] = strategy.metadata.get("workspace_mode")
    return ReceiptBundle(
        receipt_bundle_id=_stable_id("receipt", receipt_payload),
        request_id=request.request_id,
        candidate_id=candidate.candidate_id,
        assembly_id=assembly.assembly_id,
        episode_id=execution_episode.episode_id,
        evidence=evidence,
        metadata=metadata,
    )


def build_module_evaluation_record(
    candidate: CandidateRecord,
    *,
    phase: str = "AK-251",
    workspace: Optional[CandidateWorkspace] = None,
    assembly: Optional[CandidateAssembly] = None,
    execution_episode: Optional[ExecutionEpisode] = None,
    receipt_bundle: Optional[ReceiptBundle] = None,
) -> EvaluationRecord:
    """Build the evaluation contract shell for a module candidate."""

    evaluation_payload = {
        "candidate_id": candidate.candidate_id,
        "evaluator": "module.runtime.validation",
    }
    evidence: Dict[str, Any] = {
        "phase": phase,
        "runtime_spine_version": "v1",
    }
    if workspace is not None:
        evidence["workspace_id"] = workspace.workspace_id
        evidence["artifact_path"] = workspace.artifact_path
    if assembly is not None:
        evidence["assembly_id"] = assembly.assembly_id
    if execution_episode is not None:
        evidence["execution_episode_id"] = execution_episode.episode_id
    if receipt_bundle is not None:
        evidence["receipt_bundle_id"] = receipt_bundle.receipt_bundle_id
    return EvaluationRecord(
        evaluation_id=_stable_id("eval", evaluation_payload),
        candidate_id=candidate.candidate_id,
        evaluator="module.runtime.validation",
        status="pending",
        summary=(
            "Pending runtime static/smoke validation and ranked selection before "
            "the candidate can be promoted."
        ),
        checks=[
            "python-parse",
            "module-shape",
            "signature-wiring",
            "module-smoke",
            "policy-score",
        ],
        evidence=evidence,
    )


def build_module_selection_policy(*, candidate_limit: int = 1) -> SelectionPolicy:
    """Build the named selection policy contract for the current module path."""

    candidate_limit = max(1, int(candidate_limit))
    multi_candidate = candidate_limit > 1
    return SelectionPolicy(
        policy_id=(
            "module.v7.multi-candidate-ranked"
            if multi_candidate
            else "module.v7.single-candidate-pass-through"
        ),
        policy_version="v0",
        mode="multi_candidate_ranked" if multi_candidate else "single_best",
        pass_requirements=[
            "render succeeds",
            "all required evaluations pass",
            "promotion invoked for the selected candidate only",
        ],
        tie_breakers=[
            "highest score",
            "preferred variant",
            "lowest ordinal",
        ],
        metadata={
            "candidate_limit": candidate_limit,
            "promote_without_evaluations": False,
            "promotion_boundary": "explicit_shell",
            "runtime_spine_version": "v1",
            "ranking_dimensions": [
                "runtime_validation_gate",
                "selection_bonus",
                "ordinal",
            ],
        },
    )


def build_module_promotion_shell(
    request: SynthesisRequest,
    *,
    target_path: Optional[str] = None,
    selected_candidate_id: Optional[str] = None,
    source_artifact_path: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> PromotionShell:
    """Build the explicit promotion shell for the selected module candidate."""

    shell_target = target_path or f"{request.spec.name}.py"
    shell_payload = {
        "request_id": request.request_id,
        "target_path": shell_target,
        "selected_candidate_id": selected_candidate_id,
    }
    metadata: Dict[str, Any] = {
        "requires_selected_candidate": True,
        "selection_pending": selected_candidate_id is None,
        "runtime_spine_version": "v1",
    }
    if source_artifact_path is not None:
        metadata["source_artifact_path"] = source_artifact_path
    if workspace_id is not None:
        metadata["workspace_id"] = workspace_id
    return PromotionShell(
        shell_id=_stable_id("shell", shell_payload),
        request_id=request.request_id,
        selected_candidate_id=selected_candidate_id,
        staging_path=source_artifact_path or shell_target,
        target_path=shell_target,
        status="pending",
        metadata=metadata,
    )


def build_module_promotion_decision(
    request: SynthesisRequest,
    policy: SelectionPolicy,
    *,
    candidate_id: Optional[str] = None,
    evaluations: Optional[List[EvaluationRecord]] = None,
    promotion_shell: Optional[PromotionShell] = None,
) -> PromotionDecision:
    """Build the explicit promotion boundary decision for the current bundle."""

    evaluation_ids = [item.evaluation_id for item in evaluations or []]
    decision_payload = {
        "request_id": request.request_id,
        "candidate_id": candidate_id,
        "policy_id": policy.policy_id,
        "evaluation_ids": evaluation_ids,
    }
    metadata: Dict[str, Any] = {
        "selected_candidate_id": candidate_id,
        "target": "module artifact",
        "runtime_spine_version": "v1",
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
        candidate_id=candidate_id,
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        outcome="withheld",
        rationale=(
            "Promotion stays withheld until the runtime validates, ranks, and "
            "explicitly invokes the chosen candidate through the promotion shell."
        ),
        evaluation_ids=evaluation_ids,
        metadata=metadata,
    )


def build_module_synthesis_bundle(
    spec: ModuleSpec,
    *,
    code: str,
    use_signature: bool = False,
    strategy_id: Optional[str] = None,
    strategy_version: str = "v0",
) -> SynthesisBundle:
    """Build the contract bundle for the current module synthesis attempt."""

    request = build_module_synthesis_request(
        spec,
        use_signature=use_signature,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        candidate_budget=1,
    )
    strategy = build_module_strategy_record(request)
    candidate = build_module_candidate_record(request, code=code)
    evaluation = build_module_evaluation_record(candidate)
    policy = build_module_selection_policy(candidate_limit=1)
    decision = build_module_promotion_decision(
        request,
        policy,
        candidate_id=candidate.candidate_id,
        evaluations=[evaluation],
    )
    return SynthesisBundle(
        request=request,
        strategy=strategy,
        candidates=[candidate],
        evaluations=[evaluation],
        selection_policy=policy,
        promotion_decision=decision,
    )

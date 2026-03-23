from __future__ import annotations

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
            "selection_ready": True,
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

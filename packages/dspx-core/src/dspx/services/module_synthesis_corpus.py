"""Deterministic module-synthesis regression corpus helpers."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, cast

from dspx.cache import sha256_text
from dspx.dtos import ModuleArtifact, ModuleSpec
from dspx.services.module_synthesis_quality import ModuleSynthesisQualityGate

from .module_service import run_generate


MODULE_SYNTHESIS_CORPUS_GATE = ModuleSynthesisQualityGate()


@dataclass(frozen=True)
class ModuleSynthesisCorpusRun:
    case_name: str
    spec: ModuleSpec
    use_signature: bool
    promote: bool
    artifact: ModuleArtifact
    ranked_variant_ids: tuple[str, ...]
    selected_candidate_id: str | None
    selected_variant_id: str | None
    selection_integrity: bool
    receipt_coverage: bool
    promotion_receipt_coverage: bool
    promotion_target: Path | None = None


@contextmanager
def _override_env(overrides: dict[str, str]) -> Iterator[None]:
    original = {key: os.environ.get(key) for key in overrides}
    try:
        for key, value in overrides.items():
            os.environ[key] = value
        yield
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def load_module_synthesis_cases(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"module synthesis corpus must be a JSON list: {path}")

    out: list[dict[str, Any]] = []
    for idx, row in enumerate(data):
        if not isinstance(row, dict):
            raise ValueError(
                "module synthesis corpus entry at index "
                f"{idx} must be an object: {path}"
            )
        out.append(cast(dict[str, Any], row))

    if not out:
        raise ValueError(f"module synthesis corpus is empty: {path}")
    return out


def _ranked_candidates(synthesis: dict[str, Any]) -> list[dict[str, Any]]:
    decision = synthesis.get("promotion_decision")
    if not isinstance(decision, dict):
        return []
    metadata = decision.get("metadata")
    if not isinstance(metadata, dict):
        return []
    ranked = metadata.get("ranked_candidates")
    if not isinstance(ranked, list):
        return []
    return [item for item in ranked if isinstance(item, dict)]


def _selected_candidate_workspace_code(
    synthesis: dict[str, Any],
    candidate_id: str | None,
) -> str | None:
    if not candidate_id:
        return None

    workspaces = synthesis.get("candidate_workspaces")
    if not isinstance(workspaces, list):
        return None

    for workspace in workspaces:
        if not isinstance(workspace, dict):
            continue
        if workspace.get("candidate_id") != candidate_id:
            continue
        artifact_path = workspace.get("artifact_path")
        if not isinstance(artifact_path, str) or artifact_path == "":
            return None
        path = Path(artifact_path)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")
    return None


def _receipt_coverage(metadata: dict[str, Any], synthesis: dict[str, Any]) -> bool:
    run_summary = metadata.get("run_summary")
    selection_policy = synthesis.get("selection_policy")
    promotion_shell = synthesis.get("promotion_shell")

    return (
        isinstance(run_summary, dict)
        and run_summary.get("backend") == "synthesis_runtime"
        and isinstance(synthesis.get("request"), dict)
        and isinstance(synthesis.get("strategy"), dict)
        and isinstance(synthesis.get("candidates"), list)
        and isinstance(synthesis.get("candidate_workspaces"), list)
        and isinstance(synthesis.get("evaluations"), list)
        and isinstance(selection_policy, dict)
        and selection_policy.get("policy_id") == "module.v7.multi-candidate-ranked"
        and isinstance(promotion_shell, dict)
        and isinstance(synthesis.get("promotion_decision"), dict)
        and isinstance(metadata.get("ranked_candidate_ids"), list)
        and isinstance(metadata.get("selected_candidate_rank"), int)
    )


def _promotion_receipt_coverage(
    *,
    promote: bool,
    metadata: dict[str, Any],
    synthesis: dict[str, Any],
    promotion_target: Path | None,
) -> bool:
    if not promote:
        return True

    promotion_shell = synthesis.get("promotion_shell")
    promotion_decision = synthesis.get("promotion_decision")
    if not isinstance(promotion_shell, dict) or not isinstance(
        promotion_decision, dict
    ):
        return False

    return (
        promotion_target is not None
        and promotion_target.exists()
        and metadata.get("promotion_status") == "promoted"
        and metadata.get("promotion_outcome") == "promoted"
        and promotion_shell.get("status") == "promoted"
        and promotion_decision.get("outcome") == "promoted"
    )


def run_module_synthesis_corpus_case(
    case: dict[str, Any],
    *,
    workspace_root: Path,
) -> ModuleSynthesisCorpusRun:
    case_name = str(case.get("name") or "module-synthesis-case")
    spec_raw = case.get("spec")
    if not isinstance(spec_raw, dict):
        raise ValueError(
            f"module synthesis case '{case_name}' is missing a spec object"
        )

    spec = ModuleSpec.model_validate(spec_raw)
    use_signature = bool(case.get("use_signature", False))
    promote = bool(case.get("promote", False))

    case_root = workspace_root / case_name
    synthesis_dir = case_root / "synthesis"
    promotion_target = case_root / "promoted" / f"{spec.name}.py" if promote else None

    with _override_env(
        {
            "DSPX_CACHE_ENABLE": "0",
            "DSPX_SYNTHESIS_DIR": str(synthesis_dir),
            "MLFLOW_ENABLE": "0",
        }
    ):
        artifact = run_generate(
            spec,
            use_signature=use_signature,
            promotion_target=promotion_target,
        )

    metadata = dict(artifact.metadata)
    synthesis = metadata.get("synthesis")
    if not isinstance(synthesis, dict):
        raise ValueError(
            f"module synthesis case '{case_name}' did not emit synthesis metadata"
        )

    ranked_candidates = _ranked_candidates(synthesis)
    ranked_variant_ids = tuple(
        str(item.get("variant_id"))
        for item in ranked_candidates
        if item.get("variant_id") is not None
    )
    selected_candidate_id = cast(str | None, metadata.get("selected_candidate_id"))
    selected_variant_id = next(
        (
            cast(str, item.get("variant_id"))
            for item in ranked_candidates
            if item.get("candidate_id") == selected_candidate_id
            and isinstance(item.get("variant_id"), str)
        ),
        None,
    )
    selected_workspace_code = _selected_candidate_workspace_code(
        synthesis,
        selected_candidate_id,
    )

    selection_integrity = (
        bool(selected_candidate_id)
        and bool(ranked_candidates)
        and ranked_candidates[0].get("candidate_id") == selected_candidate_id
        and selected_workspace_code == artifact.code
        and sha256_text(artifact.code) == sha256_text(selected_workspace_code or "")
    )

    return ModuleSynthesisCorpusRun(
        case_name=case_name,
        spec=spec,
        use_signature=use_signature,
        promote=promote,
        artifact=artifact,
        ranked_variant_ids=ranked_variant_ids,
        selected_candidate_id=selected_candidate_id,
        selected_variant_id=selected_variant_id,
        selection_integrity=selection_integrity,
        receipt_coverage=_receipt_coverage(metadata, synthesis),
        promotion_receipt_coverage=_promotion_receipt_coverage(
            promote=promote,
            metadata=metadata,
            synthesis=synthesis,
            promotion_target=promotion_target,
        ),
        promotion_target=promotion_target,
    )


def build_module_synthesis_quality_events(
    cases: list[dict[str, Any]],
    *,
    workspace_root: Path,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for case in cases:
        run = run_module_synthesis_corpus_case(case, workspace_root=workspace_root)
        metadata = dict(run.artifact.metadata)
        events.append(
            {
                "run_kind": "module-gen",
                "case_name": run.case_name,
                "use_signature": run.use_signature,
                "promotion_requested": run.promote,
                "candidate_count": int(metadata.get("candidate_count") or 0),
                "selected_candidate_id": run.selected_candidate_id,
                "selected_candidate_rank": int(
                    metadata.get("selected_candidate_rank") or 0
                ),
                "selected_variant_id": run.selected_variant_id,
                "ranked_variant_ids": list(run.ranked_variant_ids),
                "validation_pass_count": int(
                    metadata.get("validation_pass_count") or 0
                ),
                "validation_total": int(metadata.get("validation_total") or 0),
                "smoke_pass_count": int(metadata.get("smoke_pass_count") or 0),
                "smoke_total": int(metadata.get("smoke_total") or 0),
                "selection_integrity": run.selection_integrity,
                "receipt_coverage": run.receipt_coverage,
                "promotion_receipt_coverage": run.promotion_receipt_coverage,
                "output_hash": sha256_text(run.artifact.code),
            }
        )
    return events


def write_module_quality_events_jsonl(
    events: list[dict[str, Any]],
    out_path: Path,
) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(event, ensure_ascii=False, sort_keys=True) for event in events]
    text = "\n".join(lines)
    if text:
        text += "\n"
    out_path.write_text(text, encoding="utf-8")
    return out_path

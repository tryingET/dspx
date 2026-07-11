# summary: "Runs deterministic module-synthesis corpus cases and emits quality-event evidence."
# read_when:
#   - "Changing module-synthesis regression cases, selection checks, or corpus quality output."

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
from dspx.services.module_synthesis_quality import (
    MODULE_SYNTHESIS_CORPUS_GATE as _MODULE_SYNTHESIS_CORPUS_GATE,
    build_module_quality_event_from_metadata,
)

from .module_service import run_generate


MODULE_SYNTHESIS_CORPUS_GATE = _MODULE_SYNTHESIS_CORPUS_GATE


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
    receipt_invariant_issues: tuple[str, ...] = ()


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

    event = build_module_quality_event_from_metadata(
        metadata,
        use_signature=use_signature,
        promotion_requested=promote,
        case_name=case_name,
        output_hash=sha256_text(artifact.code),
    )
    selection_integrity = (
        bool(selected_candidate_id)
        and event.payload["selection_integrity"] is True
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
        receipt_coverage=bool(event.payload["receipt_coverage"]),
        promotion_receipt_coverage=bool(event.payload["promotion_receipt_coverage"]),
        promotion_target=promotion_target,
        receipt_invariant_issues=event.receipt_invariants.issues,
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
        event = build_module_quality_event_from_metadata(
            metadata,
            use_signature=run.use_signature,
            promotion_requested=run.promote,
            case_name=run.case_name,
            output_hash=sha256_text(run.artifact.code),
        )
        payload = dict(event.payload)
        payload["selection_integrity"] = run.selection_integrity
        payload["receipt_invariant_issues"] = list(run.receipt_invariant_issues)
        events.append(payload)
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

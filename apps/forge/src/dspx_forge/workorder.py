from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import secrets
from typing import Optional

from dspx_forge.fingerprints import stable_sha256, workorder_id_from_title
from dspx_forge.io import write_yaml
from dspx_forge.io import read_yaml
from dspx_forge.models import (
    AcceptanceTest,
    Constraint,
    Intent,
    Outputs,
    RedactionReport,
    Requirement,
    ResourceRef,
    Routing,
    WorkOrder,
    WorkOrderDoc,
)
from dspx_forge.sanitize import sanitize_text
from dspx_forge.system_definition import render_system_definition_card


@dataclass(frozen=True)
class WorkOrderPaths:
    root: Path
    workorder_yaml: Path
    system_definition_card: Path


def _display_path(path: Path) -> str:
    return path.resolve().as_posix()


def _now_run_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"run_{ts}_{secrets.token_hex(2)}"


def _default_constraints() -> list[Constraint]:
    return [
        Constraint(id="c_offline", text="Offline/deterministic by default"),
        Constraint(id="c_no_secrets", text="No secrets in logs/issues/artifacts"),
        Constraint(id="c_policy", text="No network mutations without explicit allow"),
    ]


def build_workorder(
    raw_input: str,
    *,
    title: Optional[str] = None,
    intent: Optional[Intent] = None,
    routing: Optional[Routing] = None,
    offline_default: bool = True,
) -> WorkOrderDoc:
    sres = sanitize_text(raw_input)
    sanitized = (sres.sanitized or "").strip()
    resolved_title = (title or "").strip() or (
        sanitized.splitlines()[0].strip() if sanitized else "Work"
    )

    it = intent.model_copy() if intent is not None else Intent()
    it.offline_default = bool(offline_default)
    rt = routing.model_copy() if routing is not None else Routing()

    # Minimal deterministic canonicalization: treat the prompt as the single top-level requirement.
    requirements = []
    if sanitized:
        requirements.append(
            Requirement(id="r1", text=sanitized, rationale=None, priority="must")
        )
    acceptance = [
        AcceptanceTest(
            id="a1",
            given="a WorkOrder is created from sanitized input",
            when="forge plan is generated",
            then="the plan includes stable fingerprints and dry-run defaults",
        )
    ]

    fingerprint_input = {
        "sanitized_input": sanitized,
        "intent": it.model_dump(),
        "routing": {
            "mode": rt.mode,
            "strategy": rt.strategy,
            "primary_project": rt.primary_project,
            "secondary_projects": list(rt.secondary_projects or []),
        },
        "constraints": [c.model_dump() for c in _default_constraints()],
        "resources": [{"id": "res_repo", "kind": "repo", "ref": "."}],
    }
    fingerprint = stable_sha256(fingerprint_input)

    wo_id = workorder_id_from_title(resolved_title, fingerprint)
    wo = WorkOrder(
        fingerprint=fingerprint,
        id=wo_id,
        run_id=_now_run_id(),
        title=resolved_title,
        raw_input=raw_input,
        sanitized_input=sanitized,
        redaction_report=RedactionReport(
            detected=bool(sres.detected),
            notes=list(sres.notes),
        ),
        intent=it,
        routing=rt,
        constraints=_default_constraints(),
        requirements=requirements,
        acceptance_tests=acceptance,
        resources=[ResourceRef(id="res_repo", kind="repo", ref=".")],
        outputs=Outputs(out_dir=f"generated/forge/{wo_id}"),
    )
    return WorkOrderDoc(work_order=wo)


def write_workorder(out_root: Path, doc: WorkOrderDoc) -> WorkOrderPaths:
    wo = doc.work_order
    root = (out_root / wo.id).resolve()
    root.mkdir(parents=True, exist_ok=True)
    workorder_yaml = root / "workorder.yaml"
    system_definition_card = root / "system_definition_card.md"

    wo.outputs.out_dir = _display_path(root)
    write_yaml(workorder_yaml, doc.model_dump())
    system_definition_card.write_text(
        render_system_definition_card(wo), encoding="utf-8"
    )
    return WorkOrderPaths(
        root=root,
        workorder_yaml=workorder_yaml,
        system_definition_card=system_definition_card,
    )


def load_workorder(path: Path) -> WorkOrderDoc:
    data = read_yaml(path)
    return WorkOrderDoc.model_validate(data)

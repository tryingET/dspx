from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
import os

from dspx_forge.io import write_json
from dspx_forge.models import PlanDoc, WorkOrderDoc


def _configured_gitlab() -> bool:
    base = os.getenv("DSPX_GITLAB_BASE_URL")
    token = os.getenv("DSPX_GITLAB_TOKEN")
    mpj = os.getenv("DSPX_GITLAB_PROJECT_MAP_JSON")
    mpf = os.getenv("DSPX_GITLAB_PROJECT_MAP_FILE")
    return bool(base and token and (mpj or mpf))


def _permitted(cap: str) -> bool:
    try:
        from dspx.policy import check_capability

        check_capability(cap)
        return True
    except Exception:
        return False


def build_plan(doc: WorkOrderDoc) -> PlanDoc:
    wo = doc.work_order
    caps_needed = [
        "filesystem.write",
        "network.read",
        "network.mutate",
        "forge.issues.read",
        "forge.issues.write",
    ]
    status: Dict[str, Any] = {}
    configured_gitlab = _configured_gitlab()
    for cap in caps_needed:
        implemented = True
        configured = True
        if cap in {"network.read", "network.mutate"}:
            configured = bool(os.getenv("DSPX_GITLAB_BASE_URL"))
        if cap in {"forge.issues.read", "forge.issues.write"}:
            configured = configured_gitlab
        permitted = _permitted(cap)
        status[cap] = {
            "implemented": implemented,
            "configured": configured,
            "permitted": permitted,
        }
    gaps = [
        c
        for c, st in status.items()
        if not (st["implemented"] and st["configured"] and st["permitted"])
    ]
    out = PlanDoc(
        workorder_id=wo.id,
        workorder_fingerprint=wo.fingerprint,
        capabilities={
            "needed": caps_needed,
            "status": status,
            "gaps": gaps,
        },
        steps=[
            {"id": "s1", "kind": "emit_issue_specs", "requires": ["filesystem.write"]},
            {"id": "s2", "kind": "overlap_review", "requires": ["network.read"]},
            {"id": "s3", "kind": "gitlab_apply", "requires": ["network.mutate"]},
        ],
    )
    return out


def write_plan(out_dir: Path, plan: PlanDoc) -> Path:
    path = out_dir / "plan.json"
    write_json(path, plan.model_dump())
    return path

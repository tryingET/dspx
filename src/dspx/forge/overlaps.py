from __future__ import annotations

from pathlib import Path
from typing import Any

from dspx.forge.io import write_json
from dspx.forge.models import WorkOrderDoc
from dspx.forge.fingerprints import slugify


def compute_overlaps(doc: WorkOrderDoc) -> dict[str, Any]:
    wo = doc.work_order

    candidates: list[dict[str, Any]] = []
    notes: list[str] = []

    # Keep deterministic/offline by default.
    try:
        from dspx.forge.gitlab_client import GitLabClient, load_gitlab_config_from_env

        cfg = load_gitlab_config_from_env()
        gl = GitLabClient(cfg)
        local_id = "iss_" + slugify(wo.title, max_len=24)
        label = f"dspx-iss:{local_id}"
        project_key = wo.routing.primary_project or "core"
        project_id = gl.project_id(project_key)
        matches = gl.list_issues(project_id, labels=[label])
        if matches:
            candidates.append(
                {
                    "project_key": project_key,
                    "local_id": local_id,
                    "label": label,
                    "matches": [
                        {
                            "iid": m.get("iid"),
                            "web_url": m.get("web_url"),
                            "title": m.get("title"),
                        }
                        for m in matches
                        if isinstance(m, dict)
                    ],
                    "reasons": ["label_match:dspx-iss"],
                }
            )
        else:
            notes.append("no_matches")
    except Exception as e:
        # No config or policy denies network.read: keep offline result.
        notes.append(f"offline:{type(e).__name__}")

    return {
        "schema_version": 0,
        "workorder_id": wo.id,
        "workorder_fingerprint": wo.fingerprint,
        "candidates": candidates,
        "decisions": [],
        "notes": notes or ["overlaps:v0_placeholder"],
    }


def write_overlaps(out_dir: Path, overlaps: dict[str, Any]) -> Path:
    path = out_dir / "overlaps.json"
    write_json(path, overlaps)
    return path

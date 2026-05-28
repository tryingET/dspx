from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, Optional, cast

from dspx_forge.fingerprints import slugify, stable_sha256
from dspx_forge.io import read_json, write_json, write_yaml
from dspx_forge.issue_text import build_managed_block, upsert_managed_block
from dspx_forge.models import (
    IssueSpec,
    IssueSpecDoc,
    ManifestDoc,
    WorkOrderDoc,
)
from dspx_forge.gitlab_client import GitLabClient, load_gitlab_config_from_env

try:
    from dspx.security import confine_relative_path
except Exception:  # pragma: no cover - standalone forge fallback

    def confine_relative_path(root: Path, *parts: str | Path) -> Path:  # type: ignore[misc]
        resolved_root = root.resolve()
        safe_parts: list[str] = []
        for raw_part in parts:
            raw_text = str(raw_part)
            if raw_text in {"", "."}:
                raise ValueError(
                    f"unsafe path component segment is not allowed: {raw_part}"
                )
            part = Path(raw_part)
            if part.is_absolute():
                raise ValueError(f"absolute path component is not allowed: {raw_part}")
            if not part.parts:
                raise ValueError(
                    f"unsafe path component segment is not allowed: {raw_part}"
                )
            for segment in part.parts:
                if segment in {"", ".", ".."}:
                    raise ValueError(
                        f"unsafe path component segment is not allowed: {raw_part}"
                    )
                safe_parts.append(segment)
        resolved = (resolved_root / Path(*safe_parts)).resolve()
        resolved.relative_to(resolved_root)
        return resolved


@dataclass(frozen=True)
class ForgePaths:
    root: Path
    issues_dir: Path
    manifest_json: Path
    overlaps_json: Path


def _fqid(project_key: str, local_id: str) -> str:
    return f"{project_key}/{local_id}"


def default_paths(workorder_yaml: Path) -> ForgePaths:
    root = workorder_yaml.parent
    return ForgePaths(
        root=root,
        issues_dir=root / "issues",
        manifest_json=root / "manifest.json",
        overlaps_json=root / "overlaps.json",
    )


def _workorder_fingerprint_digest(doc: WorkOrderDoc) -> str:
    return doc.work_order.fingerprint.split(":", 1)[-1]


def _workorder_label(doc: WorkOrderDoc) -> str:
    return f"dspx-wo:{_workorder_fingerprint_digest(doc)[:8]}"


def _issue_local_id(doc: WorkOrderDoc) -> str:
    wo = doc.work_order
    digest = _workorder_fingerprint_digest(doc)[:8]
    return f"iss_{slugify(wo.title, max_len=24)}_{digest}"


def _stable_system_definition_card_ref(doc: WorkOrderDoc) -> str:
    return f"workorder://{doc.work_order.id}/system_definition_card.md"


def build_issue_spec(
    doc: WorkOrderDoc, *, project_key: Optional[str] = None
) -> IssueSpecDoc:
    wo = doc.work_order
    pk = project_key or wo.routing.primary_project or "core"
    local_id = _issue_local_id(doc)

    system_card_ref = _stable_system_definition_card_ref(doc)
    managed = build_managed_block(
        workorder_id=wo.id,
        fingerprint=wo.fingerprint,
        system_definition_card_path=system_card_ref,
    )
    description = (
        "\n\n".join(
            [
                managed,
                "",
                "Notes for humans (Forge will not overwrite this section):",
                f"- Prompt (sanitized): {wo.sanitized_input[:200].replace(chr(10), ' ')}",
            ]
        ).strip()
        + "\n"
    )

    labels = sorted(
        list(
            {
                "dspx-forge",
                _workorder_label(doc),
                f"dspx-iss:{local_id}",
            }
        )
    )
    # stable fingerprint excludes fingerprint itself
    fp_input: dict[str, Any] = {
        "schema_version": 0,
        "local_id": local_id,
        "project_key": pk,
        "title": wo.title,
        "managed_block": managed,
        "labels": labels,
        "depends_on": [],
    }
    fp = stable_sha256(fp_input)
    spec = IssueSpec(
        local_id=local_id,
        project_key=pk,
        title=wo.title,
        description_md=description,
        labels=labels,
        depends_on=[],
        fingerprint=fp,
    )
    return IssueSpecDoc(issue_spec=spec)


def write_issue_specs(paths: ForgePaths, specs: list[IssueSpecDoc]) -> list[Path]:
    out: list[Path] = []
    for doc in specs:
        iss = doc.issue_spec
        p = confine_relative_path(
            paths.issues_dir, iss.project_key, f"{iss.local_id}.yaml"
        )
        write_yaml(p, doc.model_dump())
        out.append(p)
    return out


def _manifest_base(doc: WorkOrderDoc) -> ManifestDoc:
    wo = doc.work_order
    return ManifestDoc(
        workorder_id=wo.id,
        workorder_fingerprint=wo.fingerprint,
        created_at=datetime.now(timezone.utc).isoformat(),
        run_id=wo.run_id,
        gitlab={},
        issue_map={},
        decisions={"overlaps": [], "routing_overrides": []},
    )


def load_or_init_manifest(paths: ForgePaths, doc: WorkOrderDoc) -> ManifestDoc:
    if paths.manifest_json.exists():
        return ManifestDoc.model_validate(read_json(paths.manifest_json))
    m = _manifest_base(doc)
    write_json(paths.manifest_json, m.model_dump())
    return m


def _gitlab_enabled() -> bool:
    return bool(
        (os.getenv("DSPX_GITLAB_BASE_URL") or "").strip()
        and (os.getenv("DSPX_GITLAB_TOKEN") or "").strip()
    )


def _issue_matches_workorder_fingerprint(
    issue: dict[str, Any], expected_fingerprint: str
) -> bool:
    description = str(issue.get("description") or "")
    return f"<!-- DSPX_FINGERPRINT: {expected_fingerprint} -->" in description


def _resolve_existing_issue(
    gl: GitLabClient,
    *,
    project_id: int,
    spec: IssueSpecDoc,
    doc: WorkOrderDoc,
) -> dict[str, Any] | None:
    issue_label = f"dspx-iss:{spec.issue_spec.local_id}"
    matches = gl.list_issues(project_id, labels=[issue_label])
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise RuntimeError(f"multiple GitLab issues match label {issue_label}")

    workorder_label = _workorder_label(doc)
    matches = gl.list_issues(project_id, labels=[workorder_label])
    if not matches:
        return None
    if len(matches) == 1:
        raw_mid = matches[0].get("iid")
        if raw_mid is None:
            raise RuntimeError("GitLab returned issue without iid")
        mid = int(cast(Any, raw_mid))
        existing = gl.get_issue(project_id, mid)
        if _issue_matches_workorder_fingerprint(existing, doc.work_order.fingerprint):
            return existing
        return None

    resolved: list[dict[str, Any]] = []
    for match in matches:
        raw_mid = match.get("iid")
        if raw_mid is None:
            continue
        mid = int(cast(Any, raw_mid))
        existing = gl.get_issue(project_id, mid)
        if _issue_matches_workorder_fingerprint(existing, doc.work_order.fingerprint):
            resolved.append(existing)
    if len(resolved) == 1:
        return resolved[0]
    if len(resolved) > 1:
        raise RuntimeError(
            f"multiple GitLab issues match workorder fingerprint {doc.work_order.fingerprint}"
        )
    return None


def apply_issue_specs(
    workorder_yaml: Path,
    doc: WorkOrderDoc,
    specs: list[IssueSpecDoc],
    *,
    dry_run: bool = True,
) -> tuple[ManifestDoc, list[dict[str, Any]]]:
    paths = default_paths(workorder_yaml)
    manifest = load_or_init_manifest(paths, doc)

    results: list[dict[str, Any]] = []
    if dry_run:
        for sdoc in specs:
            iss = sdoc.issue_spec
            fq = _fqid(iss.project_key, iss.local_id)
            manifest.issue_map[fq] = {
                "iid": None,
                "web_url": None,
                "fingerprint": iss.fingerprint,
            }
            results.append(
                {
                    "project_key": iss.project_key,
                    "local_id": iss.local_id,
                    "dry_run": True,
                }
            )
        write_json(paths.manifest_json, manifest.model_dump())
        return manifest, results

    if not _gitlab_enabled():
        raise RuntimeError(
            "GitLab not configured (set DSPX_GITLAB_BASE_URL and DSPX_GITLAB_TOKEN; run `dspx forge plan` to see config gaps)"
        )

    cfg = load_gitlab_config_from_env()
    gl = GitLabClient(cfg)
    manifest.gitlab = {
        "base_url": cfg.base_url,
        "projects": {k: {"project_id": v} for k, v in cfg.project_map.items()},
    }
    # MUST write manifest before any POST/PUT so apply is resumable and auditable.
    write_json(paths.manifest_json, manifest.model_dump())

    for sdoc in specs:
        iss = sdoc.issue_spec
        project_id = gl.project_id(iss.project_key)
        fq = _fqid(iss.project_key, iss.local_id)

        # Ensure issue exists; use manifest fast path if available.
        iid = None
        if fq in manifest.issue_map and isinstance(manifest.issue_map.get(fq), dict):
            iid = (manifest.issue_map[fq] or {}).get("iid")
        item: dict[str, Any] = {
            "project_key": iss.project_key,
            "local_id": iss.local_id,
        }

        labels = sorted(list(dict.fromkeys(cfg.default_labels + (iss.labels or []))))
        if iid:
            iid_int = int(cast(Any, iid))
            existing = gl.get_issue(project_id, iid_int)
            desc_existing = str(existing.get("description") or "")
            desc_new = upsert_managed_block(
                desc_existing, iss.description_md.split("\n\n", 1)[0]
            )
            updated = gl.update_issue(
                project_id,
                iid_int,
                title=iss.title,
                description=desc_new,
                labels=labels,
            )
            manifest.issue_map[fq] = {
                "iid": updated.get("iid"),
                "web_url": updated.get("web_url"),
                "fingerprint": iss.fingerprint,
            }
            item.update({"action": "update", "iid": updated.get("iid")})
        else:
            existing = _resolve_existing_issue(
                gl,
                project_id=project_id,
                spec=sdoc,
                doc=doc,
            )
            if existing is not None:
                raw_mid = existing.get("iid")
                if raw_mid is None:
                    raise RuntimeError("GitLab returned issue without iid")
                mid = int(cast(Any, raw_mid))
                desc_existing = str(existing.get("description") or "")
                desc_new = upsert_managed_block(
                    desc_existing, iss.description_md.split("\n\n", 1)[0]
                )
                updated = gl.update_issue(
                    project_id,
                    mid,
                    title=iss.title,
                    description=desc_new,
                    labels=labels,
                )
                manifest.issue_map[fq] = {
                    "iid": updated.get("iid"),
                    "web_url": updated.get("web_url"),
                    "fingerprint": iss.fingerprint,
                }
                item.update({"action": "update", "iid": updated.get("iid")})
            else:
                created = gl.create_issue(
                    project_id,
                    title=iss.title,
                    description=iss.description_md,
                    labels=labels,
                )
                manifest.issue_map[fq] = {
                    "iid": created.get("iid"),
                    "web_url": created.get("web_url"),
                    "fingerprint": iss.fingerprint,
                }
                item.update({"action": "create", "iid": created.get("iid")})

        results.append(item)
        write_json(paths.manifest_json, manifest.model_dump())

    return manifest, results


def close_marked_duplicates(
    workorder_yaml: Path,
    doc: WorkOrderDoc,
    *,
    dry_run: bool = True,
) -> tuple[ManifestDoc, list[dict[str, Any]]]:
    """Close duplicates based on user-marked decisions in overlaps.json.

    Safety: operates only on decisions explicitly present in overlaps.json.
    """
    paths = default_paths(workorder_yaml)
    manifest = load_or_init_manifest(paths, doc)

    overlaps: dict[str, Any] = {}
    if paths.overlaps_json.exists():
        overlaps = read_json(paths.overlaps_json)
    decisions = overlaps.get("decisions")
    if not isinstance(decisions, list):
        decisions = []

    to_close: list[dict[str, Any]] = []
    for d in decisions:
        if not isinstance(d, dict):
            continue
        if str(d.get("action") or "").strip().lower() not in {
            "close_duplicate",
            "close-duplicate",
        }:
            continue
        pk = (
            str(d.get("project_key") or "").strip()
            or doc.work_order.routing.primary_project
            or "core"
        )
        iid = d.get("iid")
        if iid is None:
            continue
        try:
            iid_int = int(cast(Any, iid))
        except Exception:
            continue
        to_close.append({"project_key": pk, "iid": iid_int, "reason": d.get("reason")})

    if dry_run or not to_close:
        results = [
            {"project_key": it["project_key"], "iid": it["iid"], "dry_run": True}
            for it in to_close
        ]
        write_json(paths.manifest_json, manifest.model_dump())
        return manifest, results

    if not _gitlab_enabled():
        raise RuntimeError("GitLab not configured; cannot close duplicates")

    cfg = load_gitlab_config_from_env()
    gl = GitLabClient(cfg)
    manifest.gitlab = {
        "base_url": cfg.base_url,
        "projects": {k: {"project_id": v} for k, v in cfg.project_map.items()},
    }
    write_json(paths.manifest_json, manifest.model_dump())

    results: list[dict[str, Any]] = []
    manifest.decisions.setdefault("closed_duplicates", [])
    for it in to_close:
        project_id = gl.project_id(str(it["project_key"]))
        iid = int(it["iid"])
        gl.close_issue(project_id, iid)
        results.append(
            {"project_key": it["project_key"], "iid": iid, "action": "close"}
        )
        manifest.decisions["closed_duplicates"].append(
            {"project_key": it["project_key"], "iid": iid}
        )
        write_json(paths.manifest_json, manifest.model_dump())

    return manifest, results

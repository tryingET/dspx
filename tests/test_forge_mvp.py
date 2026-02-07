from __future__ import annotations

from pathlib import Path

import pytest

from dspx_forge.issues import apply_issue_specs, build_issue_spec, default_paths
from dspx_forge.issue_text import build_managed_block, upsert_managed_block
from dspx_forge.workorder import build_workorder, write_workorder


pytestmark = pytest.mark.forge


def test_forge_workorder_fingerprint_stable() -> None:
    prompt = "Build thing\nDo it safely"
    d1 = build_workorder(prompt)
    d2 = build_workorder(prompt)
    assert d1.work_order.fingerprint == d2.work_order.fingerprint


def test_forge_workorder_id_stable() -> None:
    prompt = "Build thing\nDo it safely"
    d1 = build_workorder(prompt)
    d2 = build_workorder(prompt)
    assert d1.work_order.id == d2.work_order.id


def test_forge_issue_spec_fingerprint_stable() -> None:
    prompt = "Build thing\nDo it safely"
    wo = build_workorder(prompt)
    i1 = build_issue_spec(wo)
    i2 = build_issue_spec(wo)
    assert i1.issue_spec.fingerprint == i2.issue_spec.fingerprint


def test_forge_managed_block_upsert_preserves_human_edits() -> None:
    new_block = build_managed_block(
        workorder_id="wo_x",
        fingerprint="sha256:abc",
        system_definition_card_path="generated/forge/wo_x/system_definition_card.md",
    )
    existing = "\n\n".join(
        [
            new_block,
            "",
            "Notes for humans (Forge will not overwrite this section):",
            "- keep this line",
        ]
    )
    updated_block = build_managed_block(
        workorder_id="wo_x",
        fingerprint="sha256:def",
        system_definition_card_path="generated/forge/wo_x/system_definition_card.md",
    )
    merged = upsert_managed_block(existing, updated_block)
    assert "sha256:def" in merged
    assert "- keep this line" in merged


def test_forge_issues_apply_dry_run_writes_manifest(tmp_path: Path) -> None:
    wo = build_workorder("Build thing\nDo it safely")
    paths = write_workorder(tmp_path / "generated" / "forge", wo)
    spec = build_issue_spec(wo)
    manifest, results = apply_issue_specs(
        paths.workorder_yaml, wo, [spec], dry_run=True
    )
    assert results and results[0]["dry_run"] is True
    p = default_paths(paths.workorder_yaml).manifest_json
    assert p.exists()
    assert manifest.workorder_id == wo.work_order.id

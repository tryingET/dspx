from __future__ import annotations

import json
from pathlib import Path

import pytest

from dspx_forge.issues import (
    apply_issue_specs,
    build_issue_spec,
    close_marked_duplicates,
    default_paths,
    write_issue_specs,
)
from dspx_forge.overlaps import compute_overlaps
from dspx_forge.issue_text import build_managed_block, upsert_managed_block
from dspx_forge.plan import build_plan
from dspx_forge.workorder import build_workorder, load_workorder, write_workorder


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


def test_forge_overlaps_uses_digestful_issue_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wo = build_workorder("Build thing\nDo it safely")
    spec = build_issue_spec(wo)
    issue_label = [
        label for label in spec.issue_spec.labels if label.startswith("dspx-iss:")
    ][0]

    monkeypatch.setenv("DSPX_GITLAB_BASE_URL", "https://gitlab.example.com")
    monkeypatch.setenv("DSPX_GITLAB_TOKEN", "tok")

    import dspx_forge.gitlab_client as gitlab_mod
    from dspx_forge.gitlab_client import GitLabConfig

    cfg = GitLabConfig(
        base_url="https://gitlab.example.com",
        token="tok",
        project_map={"core": 101},
        allowed_project_keys=None,
        allowed_hosts={"gitlab.example.com"},
        default_labels=[],
    )
    monkeypatch.setattr(gitlab_mod, "load_gitlab_config_from_env", lambda: cfg)
    seen_labels: list[list[str]] = []

    class FakeGitLabClient:
        def __init__(self, _cfg):
            pass

        def project_id(self, project_key: str) -> int:
            return 101

        def list_issues(self, project_id: int, *, labels: list[str]):
            seen_labels.append(labels)
            return []

    monkeypatch.setattr(gitlab_mod, "GitLabClient", FakeGitLabClient)

    compute_overlaps(wo)

    assert seen_labels == [[issue_label]]


def test_forge_issue_local_id_differs_for_same_title_different_workorders() -> None:
    wo1 = build_workorder("Build thing\nFirst body")
    wo2 = build_workorder("Build thing\nSecond body")

    i1 = build_issue_spec(wo1)
    i2 = build_issue_spec(wo2)

    assert wo1.work_order.title == wo2.work_order.title == "Build thing"
    assert wo1.work_order.fingerprint != wo2.work_order.fingerprint
    assert i1.issue_spec.local_id != i2.issue_spec.local_id
    assert set(i1.issue_spec.labels) != set(i2.issue_spec.labels)


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


def test_forge_issue_spec_write_confines_project_key(tmp_path: Path) -> None:
    wo = build_workorder("Build thing\nDo it safely")
    paths = write_workorder(tmp_path / "generated" / "forge", wo)
    spec = build_issue_spec(wo, project_key="../../escape")

    with pytest.raises(ValueError, match="unsafe path component|Path escapes"):
        write_issue_specs(default_paths(paths.workorder_yaml), [spec])

    assert not (tmp_path / "escape" / f"{spec.issue_spec.local_id}.yaml").exists()


def test_forge_workorder_redacts_colon_style_secrets() -> None:
    wo = build_workorder(
        "Build thing\npassword: hunter2\ntoken: abc123\napi_key: sk-test"
    )

    assert wo.work_order.redaction_report.detected is True
    assert "hunter2" not in wo.work_order.sanitized_input
    assert "abc123" not in wo.work_order.sanitized_input
    assert "sk-test" not in wo.work_order.sanitized_input


def test_forge_workorder_redacts_common_provider_tokens() -> None:
    wo = build_workorder(
        "Build thing\nGitHub token ghp_abcdefghijklmnopqrstuvwxyz123456\nOpenAI sk-proj-abcdefghijklmnopqrstuvwxyz123456"
    )

    assert wo.work_order.redaction_report.detected is True
    assert "ghp_" not in wo.work_order.sanitized_input
    assert "sk-proj-" not in wo.work_order.sanitized_input


def test_forge_custom_out_root_persists_into_workorder_and_issue_specs(
    tmp_path: Path,
) -> None:
    wo = build_workorder("Build thing\nDo it safely")
    paths = write_workorder(tmp_path / "alt-root", wo)

    loaded = load_workorder(paths.workorder_yaml)
    assert loaded.work_order.outputs.out_dir == str(paths.root)

    spec = build_issue_spec(loaded)
    assert (
        f"workorder://{loaded.work_order.id}/system_definition_card.md"
        in spec.issue_spec.description_md
    )


def test_forge_issue_spec_uses_stable_workorder_reference_across_cwd_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.chdir(repo_root)

    wo = build_workorder("Build thing\nDo it safely")
    paths = write_workorder(repo_root / "generated" / "forge", wo)

    loaded = load_workorder(paths.workorder_yaml)
    assert loaded.work_order.outputs.out_dir == str(paths.root)

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    spec = build_issue_spec(loaded)
    assert (
        f"workorder://{loaded.work_order.id}/system_definition_card.md"
        in spec.issue_spec.description_md
    )


def test_forge_issue_spec_fingerprint_stable_across_output_roots(
    tmp_path: Path,
) -> None:
    prompt = "Build thing\nDo it safely"
    first = write_workorder(tmp_path / "first-root", build_workorder(prompt))
    second = write_workorder(tmp_path / "second-root", build_workorder(prompt))

    loaded_first = load_workorder(first.workorder_yaml)
    loaded_second = load_workorder(second.workorder_yaml)

    spec_first = build_issue_spec(loaded_first)
    spec_second = build_issue_spec(loaded_second)

    assert loaded_first.work_order.fingerprint == loaded_second.work_order.fingerprint
    assert spec_first.issue_spec.fingerprint == spec_second.issue_spec.fingerprint


def test_forge_plan_marks_invalid_gitlab_map_as_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DSPX_GITLAB_BASE_URL", "https://gitlab.example.com")
    monkeypatch.setenv("DSPX_GITLAB_TOKEN", "tok")
    monkeypatch.setenv("DSPX_GITLAB_PROJECT_MAP_JSON", "not-json")

    plan = build_plan(build_workorder("Build thing\nDo it safely"))

    assert plan.capabilities["status"]["forge.issues.read"]["configured"] is False
    assert plan.capabilities["status"]["forge.issues.write"]["configured"] is False


def test_forge_close_duplicates_refuses_unmanaged_issue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_GITLAB_BASE_URL", "https://gitlab.example.com")
    monkeypatch.setenv("DSPX_GITLAB_TOKEN", "tok")

    wo = build_workorder("Build thing\nDo it safely")
    paths = write_workorder(tmp_path / "generated" / "forge", wo)
    forge_paths = default_paths(paths.workorder_yaml)
    forge_paths.overlaps_json.write_text(
        json.dumps(
            {
                "decisions": [
                    {"action": "close_duplicate", "project_key": "core", "iid": 1}
                ]
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    import dspx_forge.issues as issues_mod
    from dspx_forge.gitlab_client import GitLabConfig

    cfg = GitLabConfig(
        base_url="https://gitlab.example.com",
        token="tok",
        project_map={"core": 101},
        allowed_project_keys=None,
        allowed_hosts={"gitlab.example.com"},
        default_labels=[],
    )
    monkeypatch.setattr(issues_mod, "load_gitlab_config_from_env", lambda: cfg)
    closed: list[int] = []

    class FakeGitLabClient:
        def __init__(self, _cfg):
            pass

        def project_id(self, project_key: str) -> int:
            return 101

        def get_issue(self, project_id: int, iid: int):
            return {"iid": iid, "description": "human issue", "labels": []}

        def close_issue(self, project_id: int, iid: int):
            closed.append(iid)
            return {"iid": iid}

    monkeypatch.setattr(issues_mod, "GitLabClient", FakeGitLabClient)

    with pytest.raises(RuntimeError, match="refusing to close issue"):
        close_marked_duplicates(paths.workorder_yaml, wo, dry_run=False)

    assert closed == []


def test_forge_apply_refuses_stale_manifest_iid_without_managed_labels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_GITLAB_BASE_URL", "https://gitlab.example.com")
    monkeypatch.setenv("DSPX_GITLAB_TOKEN", "tok")

    wo = build_workorder("Build thing\nDo it safely")
    spec = build_issue_spec(wo)
    paths = write_workorder(tmp_path / "generated" / "forge", wo)
    forge_paths = default_paths(paths.workorder_yaml)
    forge_paths.manifest_json.write_text(
        json.dumps(
            {
                "schema_version": 0,
                "workorder_id": wo.work_order.id,
                "workorder_fingerprint": wo.work_order.fingerprint,
                "created_at": "2026-01-01T00:00:00+00:00",
                "run_id": wo.work_order.run_id,
                "gitlab": {},
                "issue_map": {f"core/{spec.issue_spec.local_id}": {"iid": 99}},
                "decisions": {"overlaps": [], "routing_overrides": []},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    import dspx_forge.issues as issues_mod
    from dspx_forge.gitlab_client import GitLabConfig

    cfg = GitLabConfig(
        base_url="https://gitlab.example.com",
        token="tok",
        project_map={"core": 101},
        allowed_project_keys=None,
        allowed_hosts={"gitlab.example.com"},
        default_labels=[],
    )
    monkeypatch.setattr(issues_mod, "load_gitlab_config_from_env", lambda: cfg)
    updated: list[int] = []

    class FakeGitLabClient:
        def __init__(self, _cfg):
            pass

        def project_id(self, project_key: str) -> int:
            return 101

        def get_issue(self, project_id: int, iid: int):
            return {"iid": iid, "description": "unrelated human issue", "labels": []}

        def update_issue(self, project_id: int, iid: int, **_kwargs):
            updated.append(iid)
            return {"iid": iid}

    monkeypatch.setattr(issues_mod, "GitLabClient", FakeGitLabClient)

    with pytest.raises(RuntimeError, match="refusing to update"):
        issues_mod.apply_issue_specs(paths.workorder_yaml, wo, [spec], dry_run=False)

    assert updated == []


def test_forge_apply_same_title_different_workorder_creates_new_issue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_GITLAB_BASE_URL", "https://gitlab.example.com")
    monkeypatch.setenv("DSPX_GITLAB_TOKEN", "tok")

    wo1 = build_workorder("Build thing\nFirst body")
    wo2 = build_workorder("Build thing\nSecond body")
    spec2 = build_issue_spec(wo2)
    paths = write_workorder(tmp_path / "generated" / "forge", wo2)

    import dspx_forge.issues as issues_mod
    from dspx_forge.gitlab_client import GitLabConfig

    cfg = GitLabConfig(
        base_url="https://gitlab.example.com",
        token="tok",
        project_map={"core": 101},
        allowed_project_keys=None,
        allowed_hosts={"gitlab.example.com"},
        default_labels=[],
    )
    monkeypatch.setattr(issues_mod, "load_gitlab_config_from_env", lambda: cfg)

    legacy_local_id = build_issue_spec(wo1).issue_spec.local_id.rsplit("_", 1)[0]
    calls: list[tuple[str, object]] = []

    class FakeGitLabClient:
        def __init__(self, _cfg):
            pass

        def project_id(self, project_key: str) -> int:
            return 101

        def list_issues(self, project_id: int, *, labels: list[str]):
            calls.append(("list", tuple(labels)))
            # Simulate an older same-title issue under a legacy title-only label.
            if labels == [f"dspx-iss:{legacy_local_id}"]:
                return [{"iid": 7}]
            return []

        def get_issue(self, project_id: int, iid: int):
            calls.append(("get", iid))
            return {
                "iid": iid,
                "description": (
                    "<!-- DSPX_MANAGED_START -->\n"
                    f"<!-- DSPX_FINGERPRINT: {wo1.work_order.fingerprint} -->\n"
                    "<!-- DSPX_MANAGED_END -->\n"
                ),
            }

        def update_issue(self, *args, **kwargs):
            calls.append(("update", kwargs.get("title")))
            return {"iid": 7, "web_url": "https://gitlab.example.com/core/-/issues/7"}

        def create_issue(
            self, project_id: int, *, title: str, description: str, labels: list[str]
        ):
            calls.append(("create", title))
            return {"iid": 8, "web_url": "https://gitlab.example.com/core/-/issues/8"}

    monkeypatch.setattr(issues_mod, "GitLabClient", FakeGitLabClient)

    manifest, results = issues_mod.apply_issue_specs(
        paths.workorder_yaml, wo2, [spec2], dry_run=False
    )

    assert results and results[0]["action"] == "create"
    assert ("create", "Build thing") in calls
    assert not any(call[0] == "update" for call in calls)
    assert manifest.issue_map[f"core/{spec2.issue_spec.local_id}"]["iid"] == 8

from __future__ import annotations

from pathlib import Path

import pytest

from dspx_forge.issues import build_issue_spec
from dspx_forge.workorder import build_workorder, write_workorder


pytestmark = pytest.mark.forge


def test_forge_apply_writes_manifest_before_network(
    tmp_path: Path, monkeypatch
) -> None:
    # Enable "gitlab mode" in apply_issue_specs, but keep network stubbed.
    monkeypatch.setenv("DSPX_GITLAB_BASE_URL", "https://gitlab.example.com")
    monkeypatch.setenv("DSPX_GITLAB_TOKEN", "redacted-token")

    wo = build_workorder("Build thing\nDo it safely")
    paths = write_workorder(tmp_path / "generated" / "forge", wo)
    spec = build_issue_spec(wo)

    import dspx_forge.issues as issues_mod
    from dspx_forge.gitlab_client import GitLabConfig

    cfg = GitLabConfig(
        base_url="https://gitlab.example.com",
        token="redacted-token",
        project_map={"core": 101},
        allowed_project_keys=None,
        allowed_hosts={"gitlab.example.com"},
        default_labels=[],
    )

    monkeypatch.setattr(issues_mod, "load_gitlab_config_from_env", lambda: cfg)

    class FakeGitLabClient:
        def __init__(self, _cfg):
            pass

        def project_id(self, project_key: str) -> int:
            assert project_key == "core"
            return 101

        def list_issues(self, project_id: int, *, labels: list[str]):
            p = issues_mod.default_paths(paths.workorder_yaml).manifest_json
            assert p.exists()
            data = issues_mod.read_json(p)
            assert (
                data.get("gitlab", {}).get("base_url") == "https://gitlab.example.com"
            )
            return []

        def create_issue(
            self, project_id: int, *, title: str, description: str, labels: list[str]
        ):
            return {"iid": 42, "web_url": "https://gitlab.example.com/core/-/issues/42"}

    monkeypatch.setattr(issues_mod, "GitLabClient", FakeGitLabClient)

    manifest, results = issues_mod.apply_issue_specs(
        paths.workorder_yaml, wo, [spec], dry_run=False
    )
    assert results and results[0].get("action") == "create"
    assert manifest.gitlab.get("base_url") == "https://gitlab.example.com"

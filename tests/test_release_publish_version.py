"""Consumer version, compatibility and registry documentation stay coordinated."""

from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def test_paired_versions_match_changelog_lock_and_registry_links():
    projects = {
        name: tomllib.loads((ROOT / path / "pyproject.toml").read_text())["project"]
        for name, path in (
            ("dspx-core", "packages/dspx-core"),
            ("dspx-forge", "apps/forge"),
        )
    }
    version = projects["dspx-core"]["version"]
    assert projects["dspx-forge"]["version"] == version
    headings = re.findall(
        r"^## (\d+\.\d+\.\d+) —", (ROOT / "CHANGELOG.md").read_text(), re.M
    )
    assert headings[0] == version
    major, minor, _ = map(int, version.split("."))
    assert (
        f"dspx-core>={version},<{major}.{minor + 1}.0"
        in projects["dspx-forge"]["dependencies"]
    )
    locked = tomllib.loads((ROOT / "uv.lock").read_text())["package"]
    for name, project in projects.items():
        assert [p["version"] for p in locked if p["name"] == name] == [version]
        assert (
            f"https://github.com/tryingET/dspx/blob/{name}-v{version}/LICENSE"
            in project["readme"]["text"]
        )
        assert project["requires-python"] == ">=3.13,<3.15"
        assert project["license"] == "LicenseRef-Apache-2.0-with-AI-Rider"

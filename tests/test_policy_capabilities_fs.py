from __future__ import annotations

from pathlib import Path
import pytest

from dspx.security import PathEscapeError
from dspx.tools.registry import ensure_default_tools, get_tool


def test_filesystem_read_capability_blocks_data_preview(
    tmp_path: Path, monkeypatch
) -> None:
    # Create a small CSV
    p = tmp_path / "d.csv"
    p.write_text("id,name\n1,Alice\n", encoding="utf-8")

    ensure_default_tools()
    tool = get_tool("data_preview")
    # Deny filesystem.read
    monkeypatch.setenv("DSPX_POLICY_DISALLOWED_CAPS", "filesystem.read")
    with pytest.raises(PermissionError):
        _ = tool(str(p))


def test_filesystem_read_tools_are_confined_to_declared_root(
    tmp_path: Path, monkeypatch
) -> None:
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    inside_csv = allowed / "data.csv"
    outside_csv = outside / "data.csv"
    inside_csv.write_text("id,name\n1,Alice\n", encoding="utf-8")
    outside_csv.write_text("id,name\n2,Bob\n", encoding="utf-8")

    monkeypatch.setenv("DSPX_FILESYSTEM_ROOT", str(allowed))
    ensure_default_tools()
    data_preview = get_tool("data_preview")
    repo_summary = get_tool("repo_summary")

    assert data_preview(str(inside_csv))["type"] == "csv"
    with pytest.raises(PathEscapeError):
        data_preview(str(outside_csv))
    with pytest.raises(PathEscapeError):
        repo_summary(str(outside))

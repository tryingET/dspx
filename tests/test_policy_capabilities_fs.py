from __future__ import annotations

from pathlib import Path
import pytest

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

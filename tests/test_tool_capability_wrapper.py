from __future__ import annotations

import pytest

from dspx.tools.registry import register_tool, get_tool


def test_wrapper_enforces_declared_capabilities(monkeypatch) -> None:
    # Allow only filesystem.read; deny filesystem.write
    monkeypatch.setenv("DSPX_POLICY_ALLOWED_CAPS", "filesystem.read")

    called = {"ok": False}

    def _write_tool(*, path: str = "") -> str:
        called["ok"] = True
        return f"wrote:{path}"

    # Declare capability on the original function before registration
    setattr(_write_tool, "_dspx_capabilities", ["filesystem.write"])
    register_tool("x.write", _write_tool)
    fn = get_tool("x.write")

    with pytest.raises(PermissionError):
        _ = fn(path="/tmp/x.txt")
    assert called["ok"] is False

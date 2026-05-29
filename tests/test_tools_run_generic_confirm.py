from __future__ import annotations

from pathlib import Path
from typing import Optional, Mapping, Any
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.tools.registry import register_tool


runner = CliRunner()


def _register_write_tool(name: str = "tw.write") -> str:
    def _write_tool(
        *,
        params: Optional[Mapping[str, Any]] = None,
        body: Optional[Mapping[str, Any]] = None,
    ) -> str:
        # simulate writing a file (no real IO)
        p = (params or {}).get("path", "")
        return f"wrote:{p}"

    # Declare capability prior to registration so wrapper can enforce/inspect
    setattr(_write_tool, "_dspx_capabilities", ["filesystem.write"])
    register_tool(name, _write_tool)
    return name


def test_tools_run_requires_confirmation_for_filesystem_write(monkeypatch) -> None:
    monkeypatch.delenv("DSPX_POLICY_BYPASS", raising=False)
    name = _register_write_tool("tw1.write")
    res = runner.invoke(
        app, ["tools", "run", name, "--params", "path=/tmp/x"], input="n\n"
    )
    assert res.exit_code == 2
    assert "confirmation required" in (res.stdout.lower() + res.stderr.lower())


def test_tools_run_skips_confirmation_with_yes_for_filesystem_write() -> None:
    name = _register_write_tool("tw2.write")
    res = runner.invoke(
        app, ["tools", "run", name, "--params", "path=/tmp/y", "--yes"], input="\n"
    )
    assert res.exit_code == 0
    assert "wrote:/tmp/y" in res.stdout


def test_tools_run_dry_run_for_filesystem_write() -> None:
    name = _register_write_tool("tw3.write")
    res = runner.invoke(
        app, ["tools", "run", name, "--params", "path=/tmp/z", "--dry-run"], input="\n"
    )
    assert res.exit_code == 0
    s = res.stdout.strip().lower()
    assert "tw3.write" in s and "filesystem.write" in s


def test_tools_run_invokes_builtin_tools_with_native_kwargs(tmp_path: Path) -> None:
    data = tmp_path / "sample.csv"
    data.write_text("name,count\nalpha,1\n", encoding="utf-8")

    res = runner.invoke(
        app,
        ["tools", "run", "data_preview", "--params", f"path={data},nrows=1"],
        input="\n",
    )

    assert res.exit_code == 0, res.output
    assert '"type": "csv"' in res.stdout
    assert "alpha" in res.stdout

from __future__ import annotations

from pathlib import Path
import os


MERMAID_DECISIONS_ONLY = """
graph TD
  A{Start?} -->|Yes| B{Done}
  A -->|No| C{Done}
""".strip()


def _write_mermaid(tmp_path: Path, name: str = "flow.mmd") -> Path:
    p = tmp_path / name
    p.write_text(MERMAID_DECISIONS_ONLY, encoding="utf-8")
    return p


def test_dspx_mermaid_sig_cli_runs_on_decisions_only(tmp_path: Path) -> None:
    from dspx.cli import dspx_mermaid2dspy as cli

    # Keep runtime lightweight (skip mlflow import/setup)
    os.environ["MLFLOW_ENABLE"] = "0"

    infile = _write_mermaid(tmp_path)
    outdir = tmp_path / "out_sig1"
    rc = cli.main(["-f", str(infile), "-n", "t1", "-o", str(outdir)])
    assert rc == 0
    assert (outdir / "signatures.py").exists()
    assert (outdir / "program_sigpredict.py").exists()
    assert (outdir / "workflow.mmd").exists()
    assert (outdir / "manifest.json").exists()
    # Program graph + artifact JSON present
    assert (outdir / "program_graph.json").exists()
    assert (outdir / "artifact.json").exists()


# Removed legacy alias dspyx2_mermaid2dspy; canonical CLI is dspx_mermaid2dspy

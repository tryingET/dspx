# summary: "Tests Mermaid program generation validation and canonical CLI artifacts."
# read_when:
#   - "Changing Mermaid workflow variants, output files, or CLI behavior."

from __future__ import annotations

from pathlib import Path
import os

import pytest

from dspx.services.mermaid_workflow_service import generate_programs


MERMAID_DECISIONS_ONLY = """
graph TD
  A{Start?} -->|Yes| B{Done}
  A -->|No| C{Done}
""".strip()


def _write_mermaid(tmp_path: Path, name: str = "flow.mmd") -> Path:
    p = tmp_path / name
    p.write_text(MERMAID_DECISIONS_ONLY, encoding="utf-8")
    return p


def test_generate_programs_rejects_invalid_variant_without_output_side_effect(
    tmp_path: Path,
) -> None:
    outdir = tmp_path / "invalid_variant_output"

    with pytest.raises(ValueError, match="Unsupported Mermaid variant"):
        generate_programs(
            MERMAID_DECISIONS_ONLY, name="bad", out_dir=str(outdir), variants=["nope"]
        )

    assert not outdir.exists()


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

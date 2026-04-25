from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def test_smoke_base_loop_materializes_non_authority_playground(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    out_dir = tmp_path / "base-loop"

    env = os.environ.copy()
    env.update(
        {
            "DSPX_PROVIDER": "stub",
            "MLFLOW_ENABLE": "0",
            "DSPX_CACHE_DIR": str(tmp_path / "cache"),
            "DSPX_CACHE_ENABLE": "1",
        }
    )

    proc = subprocess.run(
        ["bash", "scripts/smoke_base_loop.sh", str(out_dir)],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=180,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "[smoke-base] ok" in proc.stdout
    assert "planned_not_exported" in proc.stdout

    program_dir = out_dir / "program"
    expected_files = [
        out_dir / "ticket_sig.py",
        out_dir / "ticket_module.py",
        out_dir / "intent.yaml",
        program_dir / "manifest.json",
        program_dir / "manifest.json.meta.json",
        program_dir / "eval_smoke.py",
        program_dir / "eval_jury.py",
        program_dir / "eval_promotion.py",
        program_dir / "eval_examples.py",
        program_dir / "ak-export-plan.json",
        program_dir / "ak-export-plan.json.meta.json",
    ]
    missing = [str(path) for path in expected_files if not path.exists()]
    assert missing == []

    plan = json.loads((program_dir / "ak-export-plan.json").read_text(encoding="utf-8"))
    assert plan["status"] == "planned_not_exported"
    assert plan["mutation"] == "none"
    assert plan["non_authority"] == {
        "ak_command_invoked": False,
        "external_mutation": False,
        "oracle_authority": False,
        "program_promoted": False,
    }

    manifest = json.loads((program_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "program-candidate-assembly-v1"
    assert manifest["candidate_assembly"]["status"] == "materialized"
    assert manifest["program_promotion_review"]["candidate_status"] == "exploratory"
    assert manifest["program_promotion_review"]["decision"]["status"] == "pending"

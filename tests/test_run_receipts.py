from __future__ import annotations

from pathlib import Path
import json

from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.run_receipts import build_run_receipt, load_run_receipt, write_run_receipt


runner = CliRunner()


def test_run_receipt_roundtrip(tmp_path: Path) -> None:
    out = tmp_path / "artifact.py"
    out.write_text("print('ok')\n", encoding="utf-8")

    receipt = build_run_receipt(
        run_kind="unit-test",
        output_path=out,
        output_hash="abc123",
        template_version="simple-v1",
        cache_key="k1",
        cache_file=str(tmp_path / "cache" / "x.json"),
        cache_enabled=True,
        replay_inputs={"x": 1, "y": [1, 2]},
        run_summary={"ok": True},
        extra={"label": "demo"},
    )
    meta_path = write_run_receipt(out, receipt)
    loaded = load_run_receipt(meta_path)

    assert loaded is not None
    assert loaded["receipt_version"] == "v1"
    assert loaded["run_kind"] == "unit-test"
    assert loaded["hash"] == "abc123"
    assert loaded["cache_key"] == "k1"
    assert loaded["label"] == "demo"
    assert loaded["replay_inputs"]["x"] == 1


def test_cli_meta_receipts_are_versioned(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")

    sig_out = tmp_path / "sig.py"
    r_sig = runner.invoke(
        app,
        [
            "signature",
            "gen",
            "Extract names from text",
            "--template-version",
            "simple-v1",
            "--outfile",
            str(sig_out),
        ],
    )
    assert r_sig.exit_code == 0
    sig_meta = json.loads((tmp_path / "sig.py.meta.json").read_text(encoding="utf-8"))
    assert sig_meta["receipt_version"] == "v1"
    assert sig_meta["run_kind"] == "signature-gen"
    assert sig_meta["output_path"] == str(sig_out)
    assert isinstance(sig_meta.get("replay_inputs"), dict)

    mod_out = tmp_path / "mod.py"
    r_mod = runner.invoke(
        app,
        [
            "module-gen",
            "--name",
            "Summarizer",
            "--description",
            "Summarizes text",
            "--input",
            "text",
            "--output",
            "summary",
            "--template-version",
            "simple-v1",
            "--outfile",
            str(mod_out),
        ],
    )
    assert r_mod.exit_code == 0
    mod_meta = json.loads((tmp_path / "mod.py.meta.json").read_text(encoding="utf-8"))
    assert mod_meta["receipt_version"] == "v1"
    assert mod_meta["run_kind"] == "module-gen"

    gen_out = tmp_path / "gen.py"
    r_gen = runner.invoke(
        app,
        [
            "codegen",
            "A CLI that prints hi",
            "--language",
            "python",
            "--template-version",
            "simple-v1",
            "--outfile",
            str(gen_out),
        ],
    )
    assert r_gen.exit_code == 0
    gen_meta = json.loads((tmp_path / "gen.py.meta.json").read_text(encoding="utf-8"))
    assert gen_meta["receipt_version"] == "v1"
    assert gen_meta["run_kind"] == "codegen"

    refine_out = tmp_path / "refined.py"
    r_refine = runner.invoke(
        app,
        [
            "signature",
            "refine",
            "Extract names from text",
            "--attempts",
            "1",
            "--outfile",
            str(refine_out),
        ],
    )
    assert r_refine.exit_code == 0
    refine_meta = json.loads(
        (tmp_path / "refined.py.meta.json").read_text(encoding="utf-8")
    )
    assert refine_meta["receipt_version"] == "v1"
    assert refine_meta["run_kind"] == "signature-refine"

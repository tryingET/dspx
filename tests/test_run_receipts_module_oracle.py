from __future__ import annotations

import json
from pathlib import Path

import pytest

from dspx.cli.dspx import app
from dspx.run_receipts import (
    load_run_receipt,
)
from run_receipts_helpers import (
    runner,
)


@pytest.mark.slow
def test_module_receipts_use_canonical_default_oracle_index_with_outfile(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_MODULE_SYNTHESIS_QUALITY_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")

    first_out = tmp_path / "first.py"
    first = runner.invoke(
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
            str(first_out),
        ],
    )
    assert first.exit_code == 0

    from dspx.coordinates import CoordinateIndex, get_embedding_engine

    first_meta_path = tmp_path / "first.py.meta.json"
    first_receipt = load_run_receipt(first_meta_path)
    assert isinstance(first_receipt, dict)
    embedding = get_embedding_engine().embed_receipt(
        first_receipt,
        receipt_path=first_meta_path,
    )
    assert embedding is not None
    oracle_index = tmp_path / "generated" / "oracle" / "coordinates.db"
    CoordinateIndex(db_path=oracle_index).upsert(embedding)

    second_out = tmp_path / "second.py"
    second = runner.invoke(
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
            str(second_out),
        ],
    )
    assert second.exit_code == 0

    second_meta = json.loads((tmp_path / "second.py.meta.json").read_text())
    diagnostics = second_meta["synthesis_diagnostics"]
    assert diagnostics["evidence_summary"]["oracle_index_available"] is True
    assert diagnostics["evidence_summary"]["oracle_lookup_status"] == "available"
    assert diagnostics["evidence_summary"]["oracle_neighbor_count"] >= 1
    assert diagnostics["evidence_bundle"]["oracle_index_path"] == str(oracle_index)


@pytest.mark.slow
def test_module_receipts_align_default_oracle_index_with_outfile_root_when_cwd_differs(
    tmp_path: Path, monkeypatch
) -> None:
    cwd = tmp_path / "cwd-root"
    out_root = tmp_path / "out-root"
    cwd.mkdir(parents=True, exist_ok=True)
    out_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.chdir(cwd)
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(cwd / "cache"))
    monkeypatch.setenv("DSPX_MODULE_SYNTHESIS_QUALITY_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")

    first_out = out_root / "first.py"
    first = runner.invoke(
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
            str(first_out),
        ],
    )
    assert first.exit_code == 0

    from dspx.coordinates import CoordinateIndex, get_embedding_engine

    first_meta_path = out_root / "first.py.meta.json"
    first_receipt = load_run_receipt(first_meta_path)
    assert isinstance(first_receipt, dict)
    embedding = get_embedding_engine().embed_receipt(
        first_receipt,
        receipt_path=first_meta_path,
    )
    assert embedding is not None
    oracle_index = out_root / "generated" / "oracle" / "coordinates.db"
    CoordinateIndex(db_path=oracle_index).upsert(embedding)

    second_out = out_root / "second.py"
    second = runner.invoke(
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
            str(second_out),
        ],
    )
    assert second.exit_code == 0

    second_meta = json.loads((out_root / "second.py.meta.json").read_text())
    diagnostics = second_meta["synthesis_diagnostics"]
    assert diagnostics["evidence_bundle"]["receipts_path"] == str(out_root)
    assert diagnostics["evidence_bundle"]["oracle_index_path"] == str(oracle_index)
    assert diagnostics["evidence_summary"]["oracle_lookup_status"] == "available"
    assert diagnostics["evidence_summary"]["oracle_neighbor_count"] >= 1

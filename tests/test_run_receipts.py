from __future__ import annotations

from pathlib import Path
import json

from typer.testing import CliRunner

import dspx.cli.dspx as dspx_cli
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


def test_run_replay_check_only_passes_and_is_local(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))

    out = tmp_path / "sig.py"
    r_gen = runner.invoke(
        app,
        [
            "signature",
            "gen",
            "Extract names from text",
            "--template-version",
            "simple-v1",
            "--outfile",
            str(out),
        ],
    )
    assert r_gen.exit_code == 0

    def _boom() -> bool:
        raise AssertionError("run replay must not bootstrap MLflow")

    monkeypatch.setattr(dspx_cli, "enable_mlflow_from_env", _boom)
    r_replay = runner.invoke(
        app,
        [
            "run",
            "replay",
            "--from",
            str(tmp_path / "sig.py.meta.json"),
            "--check-only",
            "--json",
        ],
    )
    assert r_replay.exit_code == 0, r_replay.stdout
    payload = json.loads(r_replay.stdout)
    assert payload["status"] == "ok"
    assert payload["checks"]["output_hash_match"] is True
    assert payload["checks"]["cache_key_recomputes"] is True
    assert payload["error_codes"] == []


def test_run_replay_fails_on_output_hash_drift(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))

    out = tmp_path / "gen.py"
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
            str(out),
        ],
    )
    assert r_gen.exit_code == 0

    out.write_text("print('drift')\n", encoding="utf-8")

    r_replay = runner.invoke(
        app,
        [
            "run",
            "replay",
            "--from",
            str(tmp_path / "gen.py.meta.json"),
            "--check-only",
            "--json",
        ],
    )
    assert r_replay.exit_code == 1
    payload = json.loads(r_replay.stdout)
    assert payload["status"] == "failed"
    assert payload["checks"]["output_hash_match"] is False
    assert "output_hash_mismatch" in payload["error_codes"]
    assert any(
        d.get("code") == "output_hash_mismatch"
        and d.get("check") == "output_hash_match"
        for d in payload["error_details"]
    )


def test_run_replay_fails_on_cache_provenance_drift(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))

    out = tmp_path / "mod.py"
    r_gen = runner.invoke(
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
            str(out),
        ],
    )
    assert r_gen.exit_code == 0

    receipt = json.loads((tmp_path / "mod.py.meta.json").read_text(encoding="utf-8"))
    cache_file = Path(str(receipt["cache_file"]))
    cache_payload = json.loads(cache_file.read_text(encoding="utf-8"))
    cache_payload["code"] = "print('cache drift')\n"
    cache_file.write_text(json.dumps(cache_payload), encoding="utf-8")

    r_replay = runner.invoke(
        app,
        [
            "run",
            "replay",
            "--from",
            str(tmp_path / "mod.py.meta.json"),
            "--check-only",
            "--json",
        ],
    )
    assert r_replay.exit_code == 1
    payload = json.loads(r_replay.stdout)
    assert payload["status"] == "failed"
    assert payload["checks"]["cache_code_hash_matches_receipt"] is False
    assert "cache_code_hash_mismatch" in payload["error_codes"]
    assert any(
        d.get("code") == "cache_code_hash_mismatch"
        and d.get("check") == "cache_code_hash_matches_receipt"
        for d in payload["error_details"]
    )


def test_run_replay_fails_on_missing_cache_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))

    out = tmp_path / "sig.py"
    r_gen = runner.invoke(
        app,
        [
            "signature",
            "gen",
            "Extract names from text",
            "--template-version",
            "simple-v1",
            "--outfile",
            str(out),
        ],
    )
    assert r_gen.exit_code == 0

    receipt = json.loads((tmp_path / "sig.py.meta.json").read_text(encoding="utf-8"))
    cache_file = Path(str(receipt["cache_file"]))
    assert cache_file.exists()
    cache_file.unlink()

    r_replay = runner.invoke(
        app,
        [
            "run",
            "replay",
            "--from",
            str(tmp_path / "sig.py.meta.json"),
            "--check-only",
            "--json",
        ],
    )
    assert r_replay.exit_code == 1
    payload = json.loads(r_replay.stdout)
    assert payload["status"] == "failed"
    assert payload["checks"]["cache_file_exists"] is False
    assert "cache_file_missing" in payload["error_codes"]
    assert any(
        d.get("code") == "cache_file_missing" and d.get("check") == "cache_file_exists"
        for d in payload["error_details"]
    )


def test_run_replay_fails_on_wrong_cache_kind_folder(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))

    out = tmp_path / "mod.py"
    r_gen = runner.invoke(
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
            str(out),
        ],
    )
    assert r_gen.exit_code == 0

    meta_path = tmp_path / "mod.py.meta.json"
    receipt = json.loads(meta_path.read_text(encoding="utf-8"))
    cache_file = Path(str(receipt["cache_file"]))
    wrong_cache_file = cache_file.parent.parent / "signature" / cache_file.name
    wrong_cache_file.parent.mkdir(parents=True, exist_ok=True)
    wrong_cache_file.write_text(
        cache_file.read_text(encoding="utf-8"), encoding="utf-8"
    )
    receipt["cache_file"] = str(wrong_cache_file)
    meta_path.write_text(json.dumps(receipt), encoding="utf-8")

    r_replay = runner.invoke(
        app,
        ["run", "replay", "--from", str(meta_path), "--check-only", "--json"],
    )
    assert r_replay.exit_code == 1
    payload = json.loads(r_replay.stdout)
    assert payload["status"] == "failed"
    assert payload["checks"]["cache_kind_matches_run_kind"] is False
    assert payload["checks"]["cache_file_exists"] is True
    assert "cache_linkage_kind_mismatch" in payload["error_codes"]
    assert any(
        d.get("code") == "cache_linkage_kind_mismatch"
        and d.get("check") == "cache_kind_matches_run_kind"
        for d in payload["error_details"]
    )


def test_run_replay_fails_on_malformed_cache_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))

    out = tmp_path / "gen.py"
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
            str(out),
        ],
    )
    assert r_gen.exit_code == 0

    receipt = json.loads((tmp_path / "gen.py.meta.json").read_text(encoding="utf-8"))
    cache_file = Path(str(receipt["cache_file"]))
    cache_file.write_text("{ malformed", encoding="utf-8")

    r_replay = runner.invoke(
        app,
        [
            "run",
            "replay",
            "--from",
            str(tmp_path / "gen.py.meta.json"),
            "--check-only",
            "--json",
        ],
    )
    assert r_replay.exit_code == 1
    payload = json.loads(r_replay.stdout)
    assert payload["status"] == "failed"
    assert payload["checks"]["cache_file_json_object"] is False
    assert "cache_file_invalid_json_object" in payload["error_codes"]
    assert any(
        d.get("code") == "cache_file_invalid_json_object"
        and d.get("check") == "cache_file_json_object"
        for d in payload["error_details"]
    )


def test_run_replay_invalid_receipt_exit_code(tmp_path: Path) -> None:
    bad_meta = tmp_path / "bad.meta.json"
    bad_meta.write_text('{"receipt_version":"v1"}\n', encoding="utf-8")

    r_replay = runner.invoke(
        app,
        ["run", "replay", "--from", str(bad_meta), "--check-only", "--json"],
    )
    assert r_replay.exit_code == 2
    payload = json.loads(r_replay.stdout)
    assert payload["status"] == "invalid"
    assert "receipt_missing_required_field" in payload["error_codes"]
    assert any(
        d.get("code") == "receipt_missing_required_field"
        for d in payload["error_details"]
    )


def test_run_explain_local_first_without_mlflow(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))

    out = tmp_path / "sig.py"
    r_gen = runner.invoke(
        app,
        [
            "signature",
            "gen",
            "Extract names from text",
            "--template-version",
            "simple-v1",
            "--outfile",
            str(out),
        ],
    )
    assert r_gen.exit_code == 0

    def _boom() -> bool:
        raise AssertionError("run explain must not bootstrap MLflow by default")

    monkeypatch.setattr(dspx_cli, "enable_mlflow_from_env", _boom)
    r_explain = runner.invoke(
        app,
        [
            "run",
            "explain",
            "--from",
            str(tmp_path / "sig.py.meta.json"),
            "--json",
        ],
    )
    assert r_explain.exit_code == 0
    payload = json.loads(r_explain.stdout)
    assert payload["status"] == "ok"
    assert payload["replay_status"] == "ok"
    assert payload["local_facts"]["run_kind"] == "signature-gen"
    assert payload["replay_checks"]["output_hash_match"] is True
    assert payload["replay_error_codes"] == []
    assert payload["replay_error_details"] == []
    assert payload["mlflow_context"]["requested"] is False
    assert payload["mlflow_context"]["mode"] == "disabled"


def test_run_explain_degraded_status_on_drift(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))

    out = tmp_path / "gen.py"
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
            str(out),
        ],
    )
    assert r_gen.exit_code == 0

    out.write_text("print('drift')\n", encoding="utf-8")

    r_explain = runner.invoke(
        app,
        [
            "run",
            "explain",
            "--from",
            str(tmp_path / "gen.py.meta.json"),
            "--json",
        ],
    )
    assert r_explain.exit_code == 0
    payload = json.loads(r_explain.stdout)
    assert payload["status"] == "degraded"
    assert payload["replay_status"] == "failed"
    assert payload["replay_checks"]["output_hash_match"] is False
    assert "output_hash_match" in payload["local_facts"]["failed_replay_checks"]
    assert "output_hash_mismatch" in payload["replay_error_codes"]
    assert any(
        d.get("code") == "output_hash_mismatch"
        and d.get("check") == "output_hash_match"
        for d in payload["replay_error_details"]
    )
    assert any(
        "replay verification drift detected" in str(w)
        for w in payload.get("warnings") or []
    )


def test_run_explain_with_mlflow_flag_is_graceful(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("MLFLOW_TRACKING_URI", str(tmp_path / "no_mlruns_yet"))

    out = tmp_path / "gen.py"
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
            str(out),
        ],
    )
    assert r_gen.exit_code == 0

    r_explain = runner.invoke(
        app,
        [
            "run",
            "explain",
            "--from",
            str(tmp_path / "gen.py.meta.json"),
            "--with-mlflow",
            "--json",
        ],
    )
    assert r_explain.exit_code == 0
    payload = json.loads(r_explain.stdout)
    assert payload["status"] == "ok"
    assert payload["replay_status"] == "ok"
    assert payload["replay_error_codes"] == []
    assert payload["mlflow_context"]["requested"] is True
    assert payload["mlflow_context"]["mode"] == "local-file-store"
    assert "linked_runs" in payload["mlflow_context"]


def test_run_explain_invalid_receipt_exit_code(tmp_path: Path) -> None:
    bad_meta = tmp_path / "bad-explain.meta.json"
    bad_meta.write_text('{"receipt_version":"v1"}\n', encoding="utf-8")

    r_explain = runner.invoke(
        app,
        ["run", "explain", "--from", str(bad_meta), "--json"],
    )
    assert r_explain.exit_code == 2
    payload = json.loads(r_explain.stdout)
    assert payload["status"] == "invalid"
    assert payload["replay_status"] == "invalid"
    assert "receipt_missing_required_field" in payload["replay_error_codes"]
    assert any(
        d.get("code") == "receipt_missing_required_field"
        for d in payload["replay_error_details"]
    )

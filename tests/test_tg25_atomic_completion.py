from __future__ import annotations

import csv
import logging
from types import SimpleNamespace

import pandas as pd
import pytest

import dspx.policy as policy
import dspx.tools.registry as registry
from dspx.pi_rpc_lm import PiRPCLM
from dspx.tools.registry import _data_preview


def test_policy_bypass_logs_audit_event(
    monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("DSPX_POLICY_BYPASS", "1")

    with caplog.at_level(logging.WARNING, logger="dspx.policy"):
        policy.check_provider_allowed("stub")

    assert any("policy bypass active" in record.message for record in caplog.records)
    assert any(
        getattr(record, "dspx_policy_target", None) == "stub"
        for record in caplog.records
    )


def test_pi_rpc_lm_retries_process_failures_only() -> None:
    lm = PiRPCLM.__new__(PiRPCLM)
    lm.timeout = 1.0

    calls = {"prompt": 0, "restart": 0}

    def _prompt(query: str, timeout: float | None = None):
        calls["prompt"] += 1
        if calls["prompt"] == 1:
            raise BrokenPipeError("broken pipe")
        return SimpleNamespace(text=f"ok:{query}:{timeout}")

    lm.client = SimpleNamespace(
        prompt=_prompt,
        restart=lambda: calls.__setitem__("restart", calls["restart"] + 1),
    )

    result = lm._call_prompt_with_retry("hello")

    assert result == "ok:hello:1.0"
    assert calls == {"prompt": 2, "restart": 1}


def test_pi_rpc_lm_does_not_retry_timeout() -> None:
    lm = PiRPCLM.__new__(PiRPCLM)
    lm.timeout = 1.0

    calls = {"prompt": 0, "restart": 0}

    def _prompt(query: str, timeout: float | None = None):
        calls["prompt"] += 1
        raise TimeoutError("timed out")

    lm.client = SimpleNamespace(
        prompt=_prompt,
        restart=lambda: calls.__setitem__("restart", calls["restart"] + 1),
    )

    with pytest.raises(TimeoutError):
        lm._call_prompt_with_retry("hello")

    assert calls == {"prompt": 1, "restart": 0}


def test_data_preview_bounds_rows_and_cell_sizes(tmp_path, monkeypatch) -> None:
    path = tmp_path / "data.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "note"])
        writer.writeheader()
        for idx in range(80):
            writer.writerow({"id": idx, "note": "x" * 400})

    monkeypatch.setenv("DSPX_FILESYSTEM_ROOT", str(tmp_path))

    preview = _data_preview(str(path), nrows=500)

    assert preview["preview_rows"] == 50
    assert len(preview["rows"]) == 50
    assert str(preview["rows"][0]["note"]).endswith("…[truncated]")
    assert len(str(preview["rows"][0]["note"])) <= 260


def test_data_preview_rejects_oversized_json_fallback_without_full_read(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "data.json"
    path.write_text('[{"id": 1}, {"id": 2}]', encoding="utf-8")
    monkeypatch.setenv("DSPX_FILESYSTEM_ROOT", str(tmp_path))
    monkeypatch.setattr(registry, "_MAX_FULL_JSON_PREVIEW_BYTES", 1)
    calls: list[dict[str, object]] = []

    def fake_read_json(*args, **kwargs):
        calls.append(dict(kwargs))
        raise ValueError("not jsonl")

    monkeypatch.setattr(registry.pd, "read_json", fake_read_json)

    with pytest.raises(ValueError, match="JSON preview.*limited"):
        registry._data_preview(str(path), nrows=1)

    assert calls == []


def test_data_preview_parquet_reads_only_bounded_batch(tmp_path, monkeypatch) -> None:
    pytest.importorskip("pyarrow")
    path = tmp_path / "data.parquet"
    pd.DataFrame([{"id": 1}, {"id": 2}]).to_parquet(path)
    monkeypatch.setenv("DSPX_FILESYSTEM_ROOT", str(tmp_path))

    def fail_if_used(*args, **kwargs):
        raise AssertionError("pd.read_parquet loads the whole file")

    monkeypatch.setattr(registry.pd, "read_parquet", fail_if_used)

    preview = registry._data_preview(str(path), nrows=1)

    assert preview["type"] == "parquet"
    assert preview["columns"] == ["id"]
    assert preview["rows"] == [{"id": 1}]

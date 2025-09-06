from __future__ import annotations

from pathlib import Path

from dspx.cache import (
    make_key,
    write as cache_write,
    read as cache_read,
)


def test_cache_roundtrip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    key = make_key({"a": 1, "b": [2, 3]})
    data = {"result": {"x": 1}}
    p = cache_write("unit", key, data)
    assert p.exists()
    out = cache_read("unit", key)
    assert out == data

from __future__ import annotations

from pathlib import Path

import pytest

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


def test_cache_read_miss_does_not_create_kind_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))

    assert cache_read("unit", "missing") is None
    assert not (tmp_path / "cache" / "unit").exists()


def test_cache_rejects_path_traversal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))

    with pytest.raises(ValueError, match="invalid cache kind"):
        cache_write("../outside", "key", {"x": 1})
    with pytest.raises(ValueError, match="invalid cache key"):
        cache_write("unit", "../../pwned", {"x": 1})
    assert not (tmp_path / "pwned.json").exists()

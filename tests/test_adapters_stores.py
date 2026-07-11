# summary: "Tests LocalObjectStore text round trips and relative-root confinement."
# read_when:
#   - "You are changing local adapter store paths, reads, writes, or existence checks."

from pathlib import Path

from dspx.adapters.stores import LocalObjectStore


def test_local_object_store_roundtrip(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path)
    p = store.put_text("dir/hello.txt", "hi")
    assert Path(p).exists()
    assert store.exists("dir/hello.txt")
    assert store.get_text("dir/hello.txt") == "hi"


def test_local_object_store_accepts_relative_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    store = LocalObjectStore("store")

    p = store.put_text("dir/hello.txt", "hi")

    assert Path(p) == (tmp_path / "store" / "dir" / "hello.txt")
    assert store.exists("dir/hello.txt")
    assert store.get_text("dir/hello.txt") == "hi"

from pathlib import Path

from dspx.adapters.stores import LocalObjectStore


def test_local_object_store_roundtrip(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path)
    p = store.put_text("dir/hello.txt", "hi")
    assert Path(p).exists()
    assert store.exists("dir/hello.txt")
    assert store.get_text("dir/hello.txt") == "hi"

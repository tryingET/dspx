from __future__ import annotations

from dspx.adapters.datasets import train_test_split, train_val_test_split


def test_train_test_split_deterministic() -> None:
    recs = [{"i": i} for i in range(10)]
    tr1, te1 = train_test_split(recs, test_size=0.3, seed=123)
    tr2, te2 = train_test_split(recs, test_size=0.3, seed=123)
    assert tr1 == tr2 and te1 == te2 and len(te1) == 3


def test_train_val_test_split_ratios() -> None:
    recs = [{"i": i} for i in range(20)]
    tr, va, te = train_val_test_split(recs, ratios=(0.6, 0.2, 0.2), seed=42)
    assert len(tr) + len(va) + len(te) == 20
    # Basic sanity: non-empty partitions with these ratios
    assert len(tr) > 0 and len(va) > 0 and len(te) > 0

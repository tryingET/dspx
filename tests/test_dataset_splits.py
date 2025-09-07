from __future__ import annotations

from dspx.adapters.datasets import (
    train_test_split,
    train_val_test_split,
    stratified_train_test_split,
)


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


def test_stratified_train_test_split_preserves_proportions() -> None:
    # 80 of label A, 20 of label B; test_size=0.25 => expect ~20 A and ~5 B in test
    recs = [{"i": i, "y": "A"} for i in range(80)] + [
        {"i": 80 + i, "y": "B"} for i in range(20)
    ]
    tr, te = stratified_train_test_split(recs, label_key="y", test_size=0.25, seed=123)
    a_test = sum(1 for r in te if r["y"] == "A")
    b_test = sum(1 for r in te if r["y"] == "B")
    assert a_test == 20 and b_test == 5
    # Ensure deterministic
    tr2, te2 = stratified_train_test_split(
        recs, label_key="y", test_size=0.25, seed=123
    )
    assert te == te2 and tr == tr2


def test_group_aware_stratified_split_keeps_groups_together() -> None:
    # four groups, two labels; expect groups not to be split across partitions
    recs = []
    gid = 0
    for g, lbl in [("g1", "A"), ("g2", "B"), ("g3", "A"), ("g4", "B")]:
        for j in range(5):
            recs.append({"i": gid, "y": lbl, "grp": g})
            gid += 1
    tr, te = stratified_train_test_split(
        recs, label_key="y", test_size=0.5, seed=7, group_key="grp"
    )
    train_groups = {r["grp"] for r in tr}
    test_groups = {r["grp"] for r in te}
    assert train_groups.isdisjoint(test_groups)
    # Total records conserved
    assert len(tr) + len(te) == len(recs)

from __future__ import annotations

from dspx.adapters.datasets import (
    train_test_split,
    train_val_test_split,
    stratified_train_test_split,
    stratified_train_val_test_split,
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


def _group_label_counts_by_partition(
    part: list[dict], label_key: str, group_key: str
) -> dict[object, set[object]]:
    # returns mapping label -> set of groups present in that partition
    out: dict[object, set[object]] = {}
    for r in part:
        out.setdefault(r[label_key], set()).add(r[group_key])
    return out


def test_group_balance_groups_vs_instances() -> None:
    # Construct groups with imbalanced sizes so 'instances' and 'groups' differ
    # A: one big group + two small groups; B: one big group + two small groups
    recs = []
    # A label groups
    for _ in range(10):
        recs.append({"y": "A", "grp": "a_big"})
    for _ in range(1):
        recs.append({"y": "A", "grp": "a_small1"})
    for _ in range(1):
        recs.append({"y": "A", "grp": "a_small2"})
    # B label groups
    for _ in range(10):
        recs.append({"y": "B", "grp": "b_big"})
    for _ in range(1):
        recs.append({"y": "B", "grp": "b_small1"})
    for _ in range(1):
        recs.append({"y": "B", "grp": "b_small2"})

    # Compare instances vs groups balance at 50/50 split
    tr_i, te_i = stratified_train_test_split(
        recs,
        label_key="y",
        test_size=0.5,
        seed=123,
        group_key="grp",
        group_balance="instances",
    )
    tr_g, te_g = stratified_train_test_split(
        recs,
        label_key="y",
        test_size=0.5,
        seed=123,
        group_key="grp",
        group_balance="groups",
    )

    # Count number of distinct groups per label in each partition
    gi_tr = _group_label_counts_by_partition(tr_i, "y", "grp")
    gi_te = _group_label_counts_by_partition(te_i, "y", "grp")
    gg_tr = _group_label_counts_by_partition(tr_g, "y", "grp")
    gg_te = _group_label_counts_by_partition(te_g, "y", "grp")

    # For each label, the groups mode should not be worse than instances mode
    for lab in {"A", "B"}:
        diff_i = abs(len(gi_tr.get(lab, set())) - len(gi_te.get(lab, set())))
        diff_g = abs(len(gg_tr.get(lab, set())) - len(gg_te.get(lab, set())))
        assert diff_g <= diff_i


def test_stratified_min_per_label_two_way() -> None:
    # 8 of A, 2 of B; with test_size small, default rounding may give 0 B in test.
    # With min_per_label=1, ensure both splits have at least 1 B.
    recs = [{"i": i, "y": "A"} for i in range(8)] + [
        {"i": 8, "y": "B"},
        {"i": 9, "y": "B"},
    ]
    tr, te = stratified_train_test_split(
        recs, label_key="y", test_size=0.1, seed=123, min_per_label=1
    )
    # Count B in each split
    b_train = sum(1 for r in tr if r["y"] == "B")
    b_test = sum(1 for r in te if r["y"] == "B")
    assert b_train >= 1 and b_test >= 1
    # Deterministic for the same seed
    tr2, te2 = stratified_train_test_split(
        recs, label_key="y", test_size=0.1, seed=123, min_per_label=1
    )
    assert tr == tr2 and te == te2


def test_stratified_min_per_label_three_way() -> None:
    # 6 A, 3 B; with ratios, ensure each partition gets at least 1 B
    recs = [{"i": i, "y": "A"} for i in range(6)] + [
        {"i": 6, "y": "B"},
        {"i": 7, "y": "B"},
        {"i": 8, "y": "B"},
    ]
    tr, va, te = stratified_train_val_test_split(
        recs,
        label_key="y",
        ratios=(0.7, 0.2, 0.1),
        seed=7,
        min_per_label=1,
    )
    b_tr = sum(1 for r in tr if r["y"] == "B")
    b_va = sum(1 for r in va if r["y"] == "B")
    b_te = sum(1 for r in te if r["y"] == "B")
    assert b_tr >= 1 and b_va >= 1 and b_te >= 1

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Protocol, Sequence
import random
import hashlib


class DatasetAdapter(Protocol):
    """Protocol for dataset loaders returning a list of row dicts.

    Implementations must be deterministic and avoid network calls.
    """

    def load(self) -> List[Dict[str, Any]]:  # pragma: no cover - interface only
        ...


@dataclass
class CSVDataset(DatasetAdapter):
    path: str | Path
    encoding: str = "utf-8"
    nrows: Optional[int] = None

    def load(self) -> List[Dict[str, Any]]:
        import pandas as pd

        df = pd.read_csv(self.path, encoding=self.encoding, nrows=self.nrows)
        return df.to_dict(orient="records")


@dataclass
class ParquetDataset(DatasetAdapter):
    path: str | Path
    columns: Optional[Sequence[str]] = None
    nrows: Optional[int] = None

    def load(self) -> List[Dict[str, Any]]:
        # Parquet requires an engine (pyarrow/fastparquet)
        import pandas as pd  # type: ignore

        df = pd.read_parquet(self.path, columns=self.columns)
        if self.nrows is not None:
            df = df.head(int(self.nrows))
        return df.to_dict(orient="records")


@dataclass
class MLflowDatasetRef:
    """Descriptor for a dataset stored as an MLflow artifact.

    This is a reference-only container that can be resolved by callers that
    have MLflow configured. The base library does not attempt network calls
    in tests by default.
    """

    run_id: str
    artifact_path: str
    description: str | None = None

    def describe(self) -> Dict[str, Any]:
        return {
            "type": "mlflow_artifact",
            "run_id": self.run_id,
            "artifact_path": self.artifact_path,
            "description": self.description or "",
        }

    def load(self) -> List[Dict[str, Any]]:
        """Attempt to load a tabular artifact via MLflow if available.

        This is best-effort and remains offline-friendly. If MLflow or the
        tracking URI is not available, raise a clear RuntimeError so tests can
        opt to use on-disk datasets instead.
        """
        try:
            import mlflow  # type: ignore
        except Exception as e:  # pragma: no cover - environment dependent
            raise RuntimeError("mlflow is not available to load dataset") from e
        try:
            import pandas as pd  # type: ignore
        except Exception as e:  # pragma: no cover - environment dependent
            raise RuntimeError("pandas is required to load MLflow dataset") from e

        # Try to download artifact to a temp dir
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as td:
            local = Path(
                mlflow.artifacts.download_artifacts(
                    run_id=self.run_id, artifact_path=self.artifact_path, dst_path=td
                )
            )
            # Heuristics: load CSV/Parquet
            if local.is_dir():
                # pick first data-like file
                cands = list(local.rglob("*.csv")) + list(local.rglob("*.parquet"))
                if not cands:
                    raise RuntimeError("No CSV/Parquet artifact found under path")
                local = cands[0]
            lower = local.name.lower()
            if lower.endswith(".csv"):
                df = pd.read_csv(local)
            elif lower.endswith(".parquet"):
                df = pd.read_parquet(local)
            else:
                raise RuntimeError(
                    f"Unsupported artifact type for dataset: {local.name}"
                )
            return df.to_dict(orient="records")


def train_test_split(
    records: List[Dict[str, Any]], *, test_size: float = 0.2, seed: int = 42
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Deterministic train/test split using a seeded shuffle.

    - `test_size` in (0, 1). Rounds down the train size.
    - Returns (train, test).
    """
    if not (0.0 < test_size < 1.0):
        raise ValueError("test_size must be in (0,1)")
    idxs = list(range(len(records)))
    rnd = random.Random(seed)
    rnd.shuffle(idxs)
    n_test = int(round(len(records) * test_size))
    test_idx = set(idxs[:n_test])
    train: List[Dict[str, Any]] = []
    test: List[Dict[str, Any]] = []
    for i, r in enumerate(records):
        (test if i in test_idx else train).append(r)
    return train, test


def train_val_test_split(
    records: List[Dict[str, Any]],
    *,
    ratios: Sequence[float] = (0.8, 0.1, 0.1),
    seed: int = 42,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Deterministic train/val/test split by ratios using a seeded shuffle."""
    if len(ratios) != 3:
        raise ValueError("ratios must be a sequence of three floats")
    total = sum(ratios)
    if not (0.99 <= total <= 1.01):
        raise ValueError("ratios must sum to 1.0")
    idxs = list(range(len(records)))
    rnd = random.Random(seed)
    rnd.shuffle(idxs)
    n = len(records)
    n_train = int(round(n * ratios[0]))
    n_val = int(round(n * ratios[1]))
    train_idx = set(idxs[:n_train])
    val_idx = set(idxs[n_train : n_train + n_val])
    train: List[Dict[str, Any]] = []
    val: List[Dict[str, Any]] = []
    test: List[Dict[str, Any]] = []
    for i, r in enumerate(records):
        if i in train_idx:
            train.append(r)
        elif i in val_idx:
            val.append(r)
        else:
            test.append(r)
    return train, val, test


def _stable_rng_for_key(seed: int, key: object) -> random.Random:
    """Create a deterministic Random based on seed and an arbitrary key.

    Uses sha256 over the composite to avoid process-dependent Python hash salt.
    """
    h = hashlib.sha256(f"{seed}|{repr(key)}".encode("utf-8")).digest()
    # Reduce to 64-bit int for Random seed
    sub = int.from_bytes(h[:8], byteorder="big", signed=False)
    return random.Random((seed ^ sub) & ((1 << 64) - 1))


def stratified_train_test_split(
    records: List[Dict[str, Any]],
    *,
    label_key: str,
    test_size: float = 0.2,
    seed: int = 42,
    group_key: Optional[str] = None,
    group_balance: str = "instances",
    min_per_label: Optional[int] = None,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Stratified train/test split.

    - If `group_key` is provided, keeps all rows with the same group value in
      the same split (group-aware stratification). The `group_balance` option
      controls the balancing objective across labels:
        - "instances" (default): balance per-label instance counts.
        - "groups": balance per-label group counts (a group contributes at
          most 1 to a label regardless of how many instances it contains).
    - Deterministic for a given seed.
    - Returns (train, test).
    """
    if not (0.0 < test_size < 1.0):
        raise ValueError("test_size must be in (0,1)")
    if min_per_label is not None and min_per_label < 0:
        raise ValueError("min_per_label must be >= 0 when provided")
    if not records:
        return [], []
    # Validate keys
    for i, r in enumerate(records):
        if label_key not in r:
            raise KeyError(f"label_key '{label_key}' missing at row {i}")
        if group_key is not None and group_key not in r:
            raise KeyError(f"group_key '{group_key}' missing at row {i}")

    if group_key is None:
        # Per-label stratification without grouping
        by_label: Dict[object, List[int]] = {}
        for idx, r in enumerate(records):
            by_label.setdefault(r[label_key], []).append(idx)
        test_idx: set[int] = set()
        for lbl, idxs in by_label.items():
            rng = _stable_rng_for_key(seed, lbl)
            idxs_local = list(idxs)
            rng.shuffle(idxs_local)
            n = len(idxs_local)
            n_test = int(round(n * test_size))
            if min_per_label is not None:
                m = int(min_per_label)
                if n < 2 * m:
                    raise ValueError(
                        f"Label '{lbl}' has only {n} rows; cannot satisfy min_per_label={m} across 2 splits"
                    )
                lower = m
                upper = n - m
                if n_test < lower:
                    n_test = lower
                elif n_test > upper:
                    n_test = upper
            test_idx.update(idxs_local[:n_test])
        train, test = [], []
        for i, r in enumerate(records):
            (test if i in test_idx else train).append(r)
        return train, test

    # Group-aware stratification: assign whole groups to partitions
    if group_balance not in {"instances", "groups"}:
        raise ValueError("group_balance must be 'instances' or 'groups'")
    # Build groups and label distributions per group
    group_to_idxs: Dict[object, List[int]] = {}
    for idx, r in enumerate(records):
        group_to_idxs.setdefault(r[group_key], []).append(idx)
    labels = {r[label_key] for r in records}

    if group_balance == "instances":
        # Targets per label for each partition based on instance counts
        total_label_counts: Dict[object, int] = {}
        for r in records:
            total_label_counts[r[label_key]] = (
                total_label_counts.get(r[label_key], 0) + 1
            )
        target = {
            0: {
                lbl: int(round(cnt * (1.0 - test_size)))
                for lbl, cnt in total_label_counts.items()
            },
            1: {
                lbl: total_label_counts[lbl]
                - int(round(total_label_counts[lbl] * (1.0 - test_size)))
                for lbl in labels
            },
        }
        # Enforce min constraints by adjusting targets within feasible bounds
        if min_per_label is not None:
            m = int(min_per_label)
            for lbl, cnt in total_label_counts.items():
                if cnt < 2 * m:
                    raise ValueError(
                        f"Label '{lbl}' has only {cnt} rows; cannot satisfy min_per_label={m} across 2 splits"
                    )
                low = m
                up = cnt - m
                t1 = target[1][lbl]
                if t1 < low:
                    t1 = low
                elif t1 > up:
                    t1 = up
                target[1][lbl] = t1
                target[0][lbl] = cnt - t1
        # Current counts per partition
        current = {0: {lbl: 0 for lbl in labels}, 1: {lbl: 0 for lbl in labels}}
    else:
        # Targets per label based on number of groups containing the label at least once
        # Compute group -> label presence (0/1)
        group_label_presence: Dict[object, Dict[object, int]] = {}
        for g, idxs in group_to_idxs.items():
            pres: Dict[object, int] = {lbl: 0 for lbl in labels}
            for i in idxs:
                pres[records[i][label_key]] = 1
            group_label_presence[g] = pres
        total_groups_per_label: Dict[object, int] = {lbl: 0 for lbl in labels}
        for pres in group_label_presence.values():
            for lbl, v in pres.items():
                total_groups_per_label[lbl] += int(v)
        target = {
            0: {
                lbl: int(round(total_groups_per_label[lbl] * (1.0 - test_size)))
                for lbl in labels
            },
            1: {
                lbl: total_groups_per_label[lbl]
                - int(round(total_groups_per_label[lbl] * (1.0 - test_size)))
                for lbl in labels
            },
        }
        if min_per_label is not None:
            # Interpret min_per_label as a minimum number of groups per label here
            m = int(min_per_label)
            for lbl, cnt in total_groups_per_label.items():
                if cnt < 2 * m:
                    raise ValueError(
                        f"Label '{lbl}' has only {cnt} groups; cannot satisfy min_per_label={m} across 2 splits"
                    )
                low = m
                up = cnt - m
                t1 = target[1][lbl]
                if t1 < low:
                    t1 = low
                elif t1 > up:
                    t1 = up
                target[1][lbl] = t1
                target[0][lbl] = cnt - t1
        current = {0: {lbl: 0 for lbl in labels}, 1: {lbl: 0 for lbl in labels}}

    # Deterministic shuffled group order
    rng = random.Random(seed)
    groups = list(group_to_idxs.keys())
    rng.shuffle(groups)

    assign: Dict[object, int] = {}
    for g in groups:
        # Group label signal per chosen balance objective
        if group_balance == "instances":
            glc: Dict[object, int] = {lbl: 0 for lbl in labels}
            for i in group_to_idxs[g]:
                gl = records[i][label_key]
                glc[gl] = glc.get(gl, 0) + 1
        else:
            # groups mode: presence only (0/1)
            glc = {lbl: 0 for lbl in labels}
            for i in group_to_idxs[g]:
                glc[records[i][label_key]] = 1
        # Choose partition to minimize squared error to target after adding group
        best_p = None
        best_score = None
        for p in (0, 1):
            score = 0.0
            for lbl in labels:
                after = current[p][lbl] + glc[lbl]
                tgt = target[p][lbl]
                d = after - tgt
                score += float(d * d)
            if best_score is None or score < best_score - 1e-9:
                best_score = score
                best_p = p
        assert best_p is not None
        assign[g] = best_p
        for lbl in labels:
            current[best_p][lbl] += glc[lbl]

    train, test = [], []
    for g, p in assign.items():
        dest = test if p == 1 else train
        for i in group_to_idxs[g]:
            dest.append(records[i])
    return train, test


def stratified_train_val_test_split(
    records: List[Dict[str, Any]],
    *,
    label_key: str,
    ratios: Sequence[float] = (0.8, 0.1, 0.1),
    seed: int = 42,
    group_key: Optional[str] = None,
    group_balance: str = "instances",
    min_per_label: Optional[int] = None,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Stratified train/val/test split.

    - If `group_key` is provided, keeps groups intact using a greedy assignment
      to approximate per-label targets across the three partitions.
      The `group_balance` option controls the balancing objective across labels:
        - "instances" (default): balance per-label instance counts.
        - "groups": balance per-label group counts (a group contributes at
          most 1 to a label regardless of how many instances it contains).
    - Deterministic for a given seed.
    - Returns (train, val, test).
    """
    if len(ratios) != 3:
        raise ValueError("ratios must be a sequence of three floats")
    total = float(sum(ratios))
    if not (0.99 <= total <= 1.01):
        raise ValueError("ratios must sum to 1.0")
    if min_per_label is not None and min_per_label < 0:
        raise ValueError("min_per_label must be >= 0 when provided")
    if not records:
        return [], [], []
    for i, r in enumerate(records):
        if label_key not in r:
            raise KeyError(f"label_key '{label_key}' missing at row {i}")
        if group_key is not None and group_key not in r:
            raise KeyError(f"group_key '{group_key}' missing at row {i}")

    if group_key is None:
        # Per-label stratification without grouping
        by_label: Dict[object, List[int]] = {}
        for idx, r in enumerate(records):
            by_label.setdefault(r[label_key], []).append(idx)
        train_idx: set[int] = set()
        val_idx: set[int] = set()
        for lbl, idxs in by_label.items():
            rng = _stable_rng_for_key(seed, lbl)
            idxs_local = list(idxs)
            rng.shuffle(idxs_local)
            n = len(idxs_local)
            n_train = int(round(n * ratios[0]))
            n_val = int(round(n * ratios[1]))
            if min_per_label is not None:
                m = int(min_per_label)
                if n < 3 * m:
                    raise ValueError(
                        f"Label '{lbl}' has only {n} rows; cannot satisfy min_per_label={m} across 3 splits"
                    )
                n_test = n - n_train - n_val
                # Raise to minima
                n_train = max(n_train, m)
                n_val = max(n_val, m)
                n_test = max(n_test, m)
                # Reduce if necessary to match total, not going below m
                while (n_train + n_val + n_test) > n:
                    # reduce the partition with largest above-min slack
                    choices = [
                        (n_train - m, 0),
                        (n_val - m, 1),
                        (n_test - m, 2),
                    ]
                    choices.sort(reverse=True)
                    reduced = False
                    for excess, idxp in choices:
                        if excess > 0:
                            if idxp == 0:
                                n_train -= 1
                            elif idxp == 1:
                                n_val -= 1
                            else:
                                n_test -= 1
                            reduced = True
                            break
                    if not reduced:
                        break
                while (n_train + n_val + n_test) < n:
                    # allocate to partition with largest deficit vs desired
                    desired_tr = int(round(n * ratios[0]))
                    desired_va = int(round(n * ratios[1]))
                    desired_te = n - desired_tr - desired_va
                    diffs = [
                        desired_tr - n_train,
                        desired_va - n_val,
                        desired_te - n_test,
                    ]
                    i = max(range(3), key=lambda k: diffs[k])
                    if i == 0:
                        n_train += 1
                    elif i == 1:
                        n_val += 1
                    else:
                        n_test += 1
            # Remaining implicitly go to test
            train_idx.update(idxs_local[:n_train])
            val_idx.update(idxs_local[n_train : n_train + n_val])
        train: List[Dict[str, Any]] = []
        val: List[Dict[str, Any]] = []
        test: List[Dict[str, Any]] = []
        for i, r in enumerate(records):
            if i in train_idx:
                train.append(r)
            elif i in val_idx:
                val.append(r)
            else:
                test.append(r)
        return train, val, test

    # Group-aware 3-way stratification
    if group_balance not in {"instances", "groups"}:
        raise ValueError("group_balance must be 'instances' or 'groups'")
    group_to_idxs: Dict[object, List[int]] = {}
    for idx, r in enumerate(records):
        group_to_idxs.setdefault(r[group_key], []).append(idx)
    labels = {r[label_key] for r in records}
    if group_balance == "instances":
        total_label_counts: Dict[object, int] = {}
        for r in records:
            total_label_counts[r[label_key]] = (
                total_label_counts.get(r[label_key], 0) + 1
            )
        target = {
            0: {
                lbl: int(round(total_label_counts[lbl] * float(ratios[0])))
                for lbl in labels
            },
            1: {
                lbl: int(round(total_label_counts[lbl] * float(ratios[1])))
                for lbl in labels
            },
            2: {
                lbl: total_label_counts[lbl]
                - int(round(total_label_counts[lbl] * float(ratios[0])))
                - int(round(total_label_counts[lbl] * float(ratios[1])))
                for lbl in labels
            },
        }
        if min_per_label is not None:
            m = int(min_per_label)
            for lbl, cnt in total_label_counts.items():
                if cnt < 3 * m:
                    raise ValueError(
                        f"Label '{lbl}' has only {cnt} rows; cannot satisfy min_per_label={m} across 3 splits"
                    )
                t0, t1, t2 = target[0][lbl], target[1][lbl], target[2][lbl]
                t0 = max(t0, m)
                t1 = max(t1, m)
                t2 = max(t2, m)
                while (t0 + t1 + t2) > cnt:
                    choices = [
                        (t0 - m, 0),
                        (t1 - m, 1),
                        (t2 - m, 2),
                    ]
                    choices.sort(reverse=True)
                    for excess, idxp in choices:
                        if excess > 0:
                            if idxp == 0:
                                t0 -= 1
                            elif idxp == 1:
                                t1 -= 1
                            else:
                                t2 -= 1
                            break
                while (t0 + t1 + t2) < cnt:
                    desired0 = int(round(cnt * float(ratios[0])))
                    desired1 = int(round(cnt * float(ratios[1])))
                    desired2 = cnt - desired0 - desired1
                    diffs = [desired0 - t0, desired1 - t1, desired2 - t2]
                    iadd = max(range(3), key=lambda k: diffs[k])
                    if iadd == 0:
                        t0 += 1
                    elif iadd == 1:
                        t1 += 1
                    else:
                        t2 += 1
                target[0][lbl], target[1][lbl], target[2][lbl] = t0, t1, t2
    else:
        # groups mode: balance number of groups containing each label
        group_label_presence: Dict[object, Dict[object, int]] = {}
        for g, idxs in group_to_idxs.items():
            pres: Dict[object, int] = {lbl: 0 for lbl in labels}
            for i in idxs:
                pres[records[i][label_key]] = 1
            group_label_presence[g] = pres
        total_groups_per_label: Dict[object, int] = {lbl: 0 for lbl in labels}
        for pres in group_label_presence.values():
            for lbl, v in pres.items():
                total_groups_per_label[lbl] += int(v)
        target = {
            0: {
                lbl: int(round(total_groups_per_label[lbl] * float(ratios[0])))
                for lbl in labels
            },
            1: {
                lbl: int(round(total_groups_per_label[lbl] * float(ratios[1])))
                for lbl in labels
            },
            2: {
                lbl: total_groups_per_label[lbl]
                - int(round(total_groups_per_label[lbl] * float(ratios[0])))
                - int(round(total_groups_per_label[lbl] * float(ratios[1])))
                for lbl in labels
            },
        }
        if min_per_label is not None:
            # Interpret min_per_label as minimum group count per label per partition
            m = int(min_per_label)
            for lbl, cnt in total_groups_per_label.items():
                if cnt < 3 * m:
                    raise ValueError(
                        f"Label '{lbl}' has only {cnt} groups; cannot satisfy min_per_label={m} across 3 splits"
                    )
                t0, t1, t2 = target[0][lbl], target[1][lbl], target[2][lbl]
                t0 = max(t0, m)
                t1 = max(t1, m)
                t2 = max(t2, m)
                while (t0 + t1 + t2) > cnt:
                    choices = [
                        (t0 - m, 0),
                        (t1 - m, 1),
                        (t2 - m, 2),
                    ]
                    choices.sort(reverse=True)
                    for excess, idxp in choices:
                        if excess > 0:
                            if idxp == 0:
                                t0 -= 1
                            elif idxp == 1:
                                t1 -= 1
                            else:
                                t2 -= 1
                            break
                while (t0 + t1 + t2) < cnt:
                    desired0 = int(round(cnt * float(ratios[0])))
                    desired1 = int(round(cnt * float(ratios[1])))
                    desired2 = cnt - desired0 - desired1
                    diffs = [desired0 - t0, desired1 - t1, desired2 - t2]
                    iadd = max(range(3), key=lambda k: diffs[k])
                    if iadd == 0:
                        t0 += 1
                    elif iadd == 1:
                        t1 += 1
                    else:
                        t2 += 1
                target[0][lbl], target[1][lbl], target[2][lbl] = t0, t1, t2
    current = {
        0: {lbl: 0 for lbl in labels},
        1: {lbl: 0 for lbl in labels},
        2: {lbl: 0 for lbl in labels},
    }

    rng = random.Random(seed)
    groups = list(group_to_idxs.keys())
    rng.shuffle(groups)

    assign: Dict[object, int] = {}
    for g in groups:
        if group_balance == "instances":
            glc: Dict[object, int] = {lbl: 0 for lbl in labels}
            for i in group_to_idxs[g]:
                gl = records[i][label_key]
                glc[gl] = glc.get(gl, 0) + 1
        else:
            glc = {lbl: 0 for lbl in labels}
            for i in group_to_idxs[g]:
                glc[records[i][label_key]] = 1
        best_p = None
        best_score = None
        for p in (0, 1, 2):
            score = 0.0
            for lbl in labels:
                after = current[p][lbl] + glc[lbl]
                tgt = target[p][lbl]
                d = after - tgt
                score += float(d * d)
            if best_score is None or score < best_score - 1e-9:
                best_score = score
                best_p = p
        assert best_p is not None
        assign[g] = best_p
        for lbl in labels:
            current[best_p][lbl] += glc[lbl]

    parts: Dict[int, List[Dict[str, Any]]] = {0: [], 1: [], 2: []}
    for g, p in assign.items():
        for i in group_to_idxs[g]:
            parts[p].append(records[i])
    return parts[0], parts[1], parts[2]


def from_path(path: str | Path, **kwargs: Any) -> DatasetAdapter:
    """Construct a dataset adapter from a file path based on extension."""
    lower = str(path).lower()
    if lower.endswith(".csv"):
        return CSVDataset(path, **kwargs)
    if lower.endswith(".parquet"):
        return ParquetDataset(path, **kwargs)
    raise ValueError(f"Unsupported dataset file extension for: {path}")


def from_spec(spec: Mapping[str, Any]) -> DatasetAdapter:
    """Construct a dataset adapter from a small spec mapping.

    Supported forms:
    - {"type": "csv", "path": "data.csv", ...}
    - {"type": "parquet", "path": "data.parquet", ...}
    - {"type": "mlflow", "run_id": "...", "artifact_path": "..."}
    """
    t = str(spec.get("type", "")).lower()
    if t == "csv":
        path = spec.get("path")
        if not path:
            raise ValueError("csv spec requires 'path'")
        return CSVDataset(str(path), encoding=spec.get("encoding", "utf-8"))
    if t == "parquet":
        path = spec.get("path")
        if not path:
            raise ValueError("parquet spec requires 'path'")
        cols = spec.get("columns")
        nrows = spec.get("nrows")
        return ParquetDataset(str(path), columns=cols, nrows=nrows)
    if t == "mlflow":
        run_id = spec.get("run_id")
        artifact_path = spec.get("artifact_path")
        if not run_id or not artifact_path:
            raise ValueError("mlflow spec requires 'run_id' and 'artifact_path'")
        return MLflowDatasetRef(run_id=str(run_id), artifact_path=str(artifact_path))
    raise ValueError(f"Unknown dataset adapter type: {t}")

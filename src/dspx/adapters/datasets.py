from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Protocol, Sequence
import random


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

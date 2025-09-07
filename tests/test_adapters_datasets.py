from pathlib import Path

import pytest

from dspx.adapters.datasets import (
    CSVDataset,
    ParquetDataset,
    from_path,
    from_spec,
    MLflowDatasetRef,
)


def test_csv_dataset_loads_records(tmp_path: Path) -> None:
    p = tmp_path / "data.csv"
    p.write_text("id,name\n1,Alice\n2,Bob\n", encoding="utf-8")
    ds = CSVDataset(p)
    rows = ds.load()
    assert rows == [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]


def test_parquet_dataset_loads_records(tmp_path: Path) -> None:
    pd = pytest.importorskip("pandas")
    # Parquet engine is optional; skip if not present
    try:
        import pyarrow  # type: ignore  # noqa: F401

        engine = "pyarrow"
    except Exception:
        try:
            import fastparquet  # type: ignore  # noqa: F401

            engine = "fastparquet"
        except Exception:
            pytest.skip("no parquet engine available")
    df = pd.DataFrame({"id": [1, 2], "name": ["Alice", "Bob"]})
    path = tmp_path / "data.parquet"
    df.to_parquet(path, engine=engine)
    ds = ParquetDataset(path, nrows=1)
    rows = ds.load()
    assert rows == [{"id": 1, "name": "Alice"}]


def test_from_path_dispatch_csv_parquet(tmp_path: Path) -> None:
    (tmp_path / "a.csv").write_text("x\n1\n", encoding="utf-8")
    assert isinstance(from_path(tmp_path / "a.csv"), CSVDataset)
    (tmp_path / "b.parquet").write_bytes(b"parquet-file")
    assert isinstance(from_path(tmp_path / "b.parquet"), ParquetDataset)
    with pytest.raises(ValueError):
        from_path(tmp_path / "c.txt")


def test_from_spec_and_mlflow_ref_descriptor(tmp_path: Path) -> None:
    spec_csv = {"type": "csv", "path": str(tmp_path / "d.csv")}
    (tmp_path / "d.csv").write_text("x\n1\n", encoding="utf-8")
    ds1 = from_spec(spec_csv)
    assert isinstance(ds1, CSVDataset)
    rows = ds1.load()
    assert rows == [{"x": 1}]

    spec_parquet = {"type": "parquet", "path": str(tmp_path / "e.parquet")}
    (tmp_path / "e.parquet").write_bytes(b"parquet-file")
    ds2 = from_spec(spec_parquet)
    assert isinstance(ds2, ParquetDataset)

    ref = from_spec({"type": "mlflow", "run_id": "r1", "artifact_path": "d.csv"})
    assert isinstance(ref, MLflowDatasetRef)
    info = ref.describe()
    assert info["type"] == "mlflow_artifact"
    assert info["run_id"] == "r1"
    assert info["artifact_path"] == "d.csv"

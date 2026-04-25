from __future__ import annotations

"""
Lightweight adapter interfaces for datasets, evaluation, stores, and authority export planning.

Phase 7 (MVP):
- datasets: CSV/Parquet loaders and an MLflow dataset reference descriptor.
- eval: simple, deterministic metrics (accuracy, F1 for binary classification).
- stores: minimal local object-store utilities (file-backed) for tests/examples.
- authority: adapter-owned export plans from DSPx evidence into external authority systems.

These adapters are intentionally simple and offline-friendly. They avoid
network calls and large dependencies. Parquet support relies on pandas +
pyarrow/fastparquet; if missing, callers get a clear ImportError.
"""

__all__ = [
    "authority",
    "datasets",
    "eval",
    "stores",
]

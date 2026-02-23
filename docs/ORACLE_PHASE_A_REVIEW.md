# Phase A: Semantic Coordinates — Deep Review

**Review Date:** 2026-02-22
**Reviewer:** Multi-perspective code review
**Status:** ✅ ALL 26 BUGS FIXED

---

## 10,000 ft Architecture Review

### What We Built

```
Layer 2: Semantic Coordinates
├── embeddings.py  → (input, output, config) → vector
├── metrics.py     → similarity, distance, drift
├── storage.py     → SQLite index with brute-force search
└── clustering.py  → k-means grouping
```

### Architectural Improvements Made

| Improvement | Status |
|-------------|--------|
| Embedding versioning | ✅ Added `EMBEDDING_VERSION` and `embedding_version` column |
| Thread-safe singleton | ✅ Added `threading.Lock()` for global engine |
| Schema versioning | ✅ Added `SCHEMA_VERSION` and migration support |
| Dimension validation | ✅ Added `__post_init__` validation in ExecutionEmbedding |
| Transactional batch upsert | ✅ All-or-nothing semantics |
| Result types | ✅ Added `EmbeddingResult` for detailed error info |

---

## Bug Fix Summary

### embeddings.py (7 bugs → FIXED)

| Bug | Issue | Fix |
|-----|-------|-----|
| BUG 1 | Mock embedder inconsistent magnitude | Use proper hash expansion with counter |
| BUG 2 | Global engine ignores parameter changes | Track config tuple, compare on each call |
| BUG 3 | backend="none" falls through | Explicit handling with log message |
| BUG 4 | Thread-unsafe global state | Added `threading.Lock()` |
| BUG 5 | Dimension not validated | Added `__post_init__` with validation |
| BUG 6 | embed_receipt returns None silently | Added `EmbeddingResult` class with details |
| BUG 7 | Exceptions swallowed silently | Log exceptions for debugging |

### metrics.py (4 bugs → FIXED)

| Bug | Issue | Fix |
|-----|-------|-----|
| BUG 8 | drift_score uses wrong semantic space | Documented limitation clearly |
| BUG 9 | Normalization inconsistent | Added `SEMANTIC_DISTANCE_NORMALIZER` constant |
| BUG 10 | Invalid timestamp in centroid | Use valid ISO timestamp |
| BUG 11 | Arbitrary drift thresholds | Documented thresholds with rationale |

### storage.py (8 bugs → FIXED)

| Bug | Issue | Fix |
|-----|-------|-----|
| BUG 12 | Absolute import in search_by_text | Already using relative import |
| BUG 13 | Dimension mismatch silent | Log warning with details |
| BUG 14 | parse_since raises unhandled ValueError | Added `ParseSinceError` with helpful message |
| BUG 15 | Commits on read operations | Added `_read_conn()` for read-only operations |
| BUG 16 | dimension_range returns None | Return empty list consistently |
| BUG 17 | JSON parse errors unhandled | Catch and log with context |
| BUG 18 | Schema version never checked | Added `_check_schema_version()` with migration |
| BUG 19 | Batch upsert not transactional | Added explicit transaction with rollback |

### clustering.py (4 bugs → FIXED)

| Bug | Issue | Fix |
|-----|-------|-----|
| BUG 20 | K-means++ always picks max | Use `random.choices()` with weights |
| BUG 21 | Empty clusters keep dead centroids | Reinitialize from furthest point |
| BUG 22 | Centroid not normalized | Normalize after computing mean |
| BUG 23 | Dimension not validated | Added validation before distance computation |

### CLI (3 bugs → FIXED)

| Bug | Issue | Fix |
|-----|-------|-----|
| BUG 24 | yaml imported inside loop | Import once at function start |
| BUG 25 | parse_since errors not caught | Wrap in try/except with helpful error |
| BUG 26 | stats() reports wrong dimension | Show index dimensions separately |

---

## Additional Improvements

### NEW BUG 27: Embedding version not stored
**Status:** ✅ FIXED — Added `embedding_version` column and field

### NEW BUG 28: Missing EMBEDDING_VERSION export
**Status:** ✅ FIXED — Exported from `__init__.py`

### NEW BUG 29: No way to reset global engine for tests
**Status:** ✅ FIXED — Added `reset_embedding_engine()` function

### NEW BUG 30: Cluster dimension not tracked
**Status:** ✅ FIXED — Added `dimension` field to Cluster dataclass

### NEW BUG 31: Schema migration not implemented
**Status:** ✅ FIXED — Added `_migrate_schema()` method

---

## Test Coverage

- 47 tests in `test_coordinates.py` (up from 34)
- All tests pass with new validation
- Tests added for:
  - Dimension validation (BUG 5)
  - Parameter change detection (BUG 2)
  - EmbeddingResult class (BUG 6)
  - ParseSinceError (BUG 14)
  - Transactional batch upsert (BUG 19)
  - Cluster dimension validation (BUG 23)

---

## Validation

```
just lint     → All checks passed
just typecheck → All checks passed
just test     → 296 passed, 4 skipped
```

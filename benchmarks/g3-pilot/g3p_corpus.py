#!/usr/bin/env python3
"""G3-rev2 feasibility pilot corpus (DIAGNOSTIC SCREEN ONLY; DSPx AK task 5080).

10 harder tasks grounded in real softwareco/owned repos. Every task requires
reading EXISTING code across >= 2 files before any correct change: the spec
defines a composition contract whose semantics live in the repository, and
the frozen acceptance checker derives expected values from the real
(unmodified) repository modules at run time. This is NOT Gate G3, NOT
protocol evidence, and makes no gate claims.

Harder bar vs the closed campaign: no task is a single-function spec; each
deliverable is a standalone re-implementation or integration module whose
exact behavior (thresholds, normalization constants, tie-breaking, ordering,
rendering) is defined by 2-4 existing repo files the executor must read.
"""

from __future__ import annotations

import hashlib
import json

SCHEMA = "dspx.g3pilot-corpus/1"
PILOT_SEED = 20260825

REPOS = {
    "dspx": {
        "repo_identity": "softwareco/owned/dspx",
        "local_path": "/home/tryinget/ai-society/softwareco/owned/dspx",
        "pin": "e74309284972236b996da3cf6dc3f11c8ab3c525",
        "kind": "python",
    },
    "piext": {
        "repo_identity": "softwareco/owned/pi-extensions",
        "local_path": "/home/tryinget/ai-society/softwareco/owned/pi-extensions",
        "pin": "e855d07799f7984770d8a7ce25fc8ebabe1b7e64",
        "kind": "ts",
    },
}

FAMILIES = {
    "fam-gpt": "openai-codex/gpt-5.6-sol:high",
    "fam-glm": "zai/glm-5.3:high",
}

COORD = "packages/dspx-core/src/dspx/coordinates"
CPACK = "packages/pi-context-packer/src"
SSE = "packages/pi-context-packer/src/source-selection-experiment"

PY_COMMON = """You are working in a disposable replica of softwareco/owned/dspx at pinned
revision {pin}. The semantic-coordinates subsystem lives under
`packages/dspx-core/src/dspx/coordinates/` (real modules: metrics.py,
clustering.py, attractors.py, territory.py). Read those existing files FIRST:
your deliverable must reproduce their exact conventions (constants, thresholds,
normalization, tie-breaking, ordering). Do not guess semantics from names.

Create ONE new standalone module `{deliverable}`:
- pure Python 3, standard library only
- no imports from the dspx package or any third-party package
- no module-level side effects, no file or network access
- it will be loaded standalone (importlib, no package context); relative
  imports would fail, so use none
"""

TS_COMMON = """You are working in a disposable replica of softwareco/owned/pi-extensions at
pinned revision {pin}. The `packages/pi-context-packer` package contains real
production modules under `src/`. Read the existing files named below FIRST:
your deliverable must reproduce their exact conventions (constants, thresholds,
string templates, ordering, tie-breaking). Do not guess semantics from names.

Create ONE new file `{deliverable}` (ESM JavaScript, plain Node >= 20,
`node:` builtins only, NO npm installs, no imports except node: builtins):
"""

# ---------------------------------------------------------------- PY-1
PY1_INPUT = [
    {"run_id": "r01", "vector": [0.90, 0.10, 0.00, 0.20, 0.05, 0.00]},
    {"run_id": "r02", "vector": [0.88, 0.12, 0.02, 0.18, 0.04, 0.01]},
    {"run_id": "r03", "vector": [0.10, 0.90, 0.10, 0.00, 0.00, 0.20]},
    {"run_id": "r04", "vector": [0.12, 0.88, 0.12, 0.01, 0.02, 0.18]},
    {"run_id": "r05", "vector": [0.00, 0.10, 0.95, 0.10, 0.05, 0.00]},
    {"run_id": "r06", "vector": [0.02, 0.08, 0.90, 0.12, 0.03, 0.01]},
    {"run_id": "r07", "vector": [-0.70, -0.70, -0.10, 0.00, 0.00, 0.10]},
    {"run_id": "r08", "vector": [0.00, 0.00, 0.00, 0.00, 0.00, 1.00]},
]

PY1_SPEC = PY_COMMON + """It must define exactly one public function:

    def drift_triage(records: list[dict]) -> dict

`records` is a list of dicts with keys `run_id` (str) and `vector`
(list[float]). Return a dict with exactly the keys "centroid", "entries",
"severe":

- "centroid": the centroid of all record vectors computed with the same
  convention as `compute_centroid` in `clustering.py` (element-wise mean,
  then normalized to unit length exactly as that function does; keep the
  empty-list behavior for empty input).
- "entries": one entry per input record, in input order, each a dict with
  exactly "run_id", "distance", "class":
  - "distance": the semantic distance between the record vector and the
    centroid, normalized to [0, 1] exactly the way the repository normalizes
    semantic distance for drift/outlier scoring (see the normalizer constant
    and its usage in `metrics.py`), rounded to 6 decimal places.
  - "class": the drift classification label the repository's drift classifier
    in `metrics.py` returns for that normalized distance (use the repository's
    exact thresholds).
- "severe": the list of run_ids whose "class" equals the repository's most
  severe drift category, in input order.

Files that define the semantics you must match:
- packages/dspx-core/src/dspx/coordinates/metrics.py
- packages/dspx-core/src/dspx/coordinates/clustering.py"""

PY1_CHECKER = '''
import importlib.util, json, pathlib, sys

BASE = pathlib.Path("packages/dspx-core/src/dspx")
DELIVERABLE = pathlib.Path("packages/dspx-core/src/dspx/coordinates/g3p_drift_triage.py")
RECORDS = json.loads(sys.argv[1])
TOL = 1e-9

import types
pkg = types.ModuleType("dspx"); pkg.__path__ = [str(BASE)]; sys.modules["dspx"] = pkg
coord = types.ModuleType("dspx.coordinates"); coord.__path__ = [str(BASE / "coordinates")]
sys.modules["dspx.coordinates"] = coord
metrics = importlib.import_module("dspx.coordinates.metrics")
clustering = importlib.import_module("dspx.coordinates.clustering")

class Emb:
    def __init__(self, rid, vec):
        self.run_id = rid; self.vector = vec; self.dimension = len(vec)
        self.input_text = ""; self.output_text = ""; self.config_text = ""
        self.run_kind = "run"; self.provider = "p"; self.template_version = None

embs = [Emb(r["run_id"], r["vector"]) for r in RECORDS]
centroid = clustering.compute_centroid(embs)
expected_entries = []
for e in embs:
    d = metrics.semantic_distance(e.vector, centroid) / metrics.SEMANTIC_DISTANCE_NORMALIZER
    expected_entries.append({"run_id": e.run_id, "distance": round(d, 6),
                             "class": metrics.classify_drift(d)})
expected_severe = [x["run_id"] for x in expected_entries if x["class"] == "severe"]

assert DELIVERABLE.exists(), "deliverable missing"
spec = importlib.util.spec_from_file_location("g3p_drift_triage", DELIVERABLE)
mod = importlib.util.module_from_spec(spec)
sys.modules["g3p_drift_triage"] = mod
spec.loader.exec_module(mod)

out = mod.drift_triage(RECORDS)
assert set(out) == {"centroid", "entries", "severe"}, sorted(out)
assert len(out["centroid"]) == len(centroid)
for got, want in zip(out["centroid"], centroid):
    assert abs(got - want) <= TOL, (got, want)
assert len(out["entries"]) == len(expected_entries)
for got, want in zip(out["entries"], expected_entries):
    assert set(got) == {"run_id", "distance", "class"}, sorted(got)
    assert got["run_id"] == want["run_id"], (got, want)
    assert got["class"] == want["class"], (got, want)
    assert abs(got["distance"] - want["distance"]) <= TOL, (got, want)
assert out["severe"] == expected_severe, (out["severe"], expected_severe)
print("ACCEPT")
'''

# ---------------------------------------------------------------- PY-2
PY2_INPUT = [
    {"run_id": "s01", "vector": [0.50, 0.50, 0.50, 0.50, 0.00, 0.00], "input_text": "alpha beta gamma", "output_text": "result ok"},
    {"run_id": "s02", "vector": [0.52, 0.48, 0.51, 0.49, 0.01, 0.00], "input_text": "alpha beta gamma delta epsilon zeta eta theta", "output_text": "result ok"},
    {"run_id": "s03", "vector": [0.48, 0.52, 0.49, 0.51, 0.00, 0.01], "input_text": "alpha beta", "output_text": "result"},
    {"run_id": "s04", "vector": [0.51, 0.49, 0.50, 0.50, 0.00, 0.00], "input_text": "alpha beta gamma delta", "output_text": "result ok fine"},
    {"run_id": "s05", "vector": [0.49, 0.51, 0.52, 0.48, 0.01, 0.01], "input_text": "alpha", "output_text": "r"},
    {"run_id": "s06", "vector": [0.50, 0.50, 0.48, 0.52, 0.00, 0.00], "input_text": "alpha beta gamma delta epsilon", "output_text": "result ok"},
]

PY2_SPEC = PY_COMMON + """It must define exactly one public function:

    def stability_summary(records: list[dict]) -> dict

`records` is a list of dicts with keys `run_id` (str), `vector` (list[float]),
`input_text` (str), `output_text` (str). Return a dict with exactly the keys
"stability", "convergence_rate", "internal_variance", "single_stability",
"empty_variance":

- "stability": the stability score the repository computes for the whole set
  with its default options (see `compute_stability_score` in `attractors.py`),
  rounded to 6 decimal places.
- "convergence_rate": the repository's convergence rate for the set (see
  `compute_convergence_rate` in `attractors.py`), rounded to 6 decimal places.
- "internal_variance": the repository's normalized internal variance for the
  set (see `compute_internal_variance` in `territory.py`), rounded to 6
  decimal places.
- "single_stability": the exact sentinel value the repository's stability
  scorer returns for a set containing exactly ONE record.
- "empty_variance": the exact value the repository's internal-variance
  function returns for an EMPTY set.

Files that define the semantics you must match:
- packages/dspx-core/src/dspx/coordinates/attractors.py
- packages/dspx-core/src/dspx/coordinates/territory.py
- packages/dspx-core/src/dspx/coordinates/metrics.py
- packages/dspx-core/src/dspx/coordinates/clustering.py"""

PY2_CHECKER = '''
import importlib.util, json, pathlib, sys, types

BASE = pathlib.Path("packages/dspx-core/src/dspx")
DELIVERABLE = pathlib.Path("packages/dspx-core/src/dspx/coordinates/g3p_stability_summary.py")
RECORDS = json.loads(sys.argv[1])
TOL = 1e-9

pkg = types.ModuleType("dspx"); pkg.__path__ = [str(BASE)]; sys.modules["dspx"] = pkg
coord = types.ModuleType("dspx.coordinates"); coord.__path__ = [str(BASE / "coordinates")]
sys.modules["dspx.coordinates"] = coord
attractors = importlib.import_module("dspx.coordinates.attractors")
territory = importlib.import_module("dspx.coordinates.territory")

def mk(r):
    o = types.SimpleNamespace()
    o.run_id = r["run_id"]; o.vector = r["vector"]; o.dimension = len(r["vector"])
    o.input_text = r.get("input_text", ""); o.output_text = r.get("output_text", "")
    o.config_text = ""; o.run_kind = "run"; o.provider = "p"; o.template_version = None
    return o

embs = [mk(r) for r in RECORDS]
want = {
    "stability": round(attractors.compute_stability_score(embs), 6),
    "convergence_rate": round(attractors.compute_convergence_rate(embs), 6),
    "internal_variance": round(territory.compute_internal_variance(embs), 6),
    "single_stability": attractors.compute_stability_score(embs[:1]),
    "empty_variance": territory.compute_internal_variance([]),
}

assert DELIVERABLE.exists(), "deliverable missing"
spec = importlib.util.spec_from_file_location("g3p_stability_summary", DELIVERABLE)
mod = importlib.util.module_from_spec(spec); sys.modules["g3p_stability_summary"] = mod
spec.loader.exec_module(mod)
out = mod.stability_summary(RECORDS)
assert set(out) == set(want), sorted(out)
for k in ("stability", "convergence_rate", "internal_variance"):
    assert abs(out[k] - want[k]) <= TOL, (k, out[k], want[k])
assert out["single_stability"] == want["single_stability"], (out["single_stability"], want["single_stability"])
assert out["empty_variance"] == want["empty_variance"], (out["empty_variance"], want["empty_variance"])
print("ACCEPT")
'''

# ---------------------------------------------------------------- PY-3
def _blob(seed_vals):
    return [{"run_id": rid, "vector": v, "run_kind": k, "provider": p}
            for rid, v, k, p in seed_vals]

PY3_INPUT = _blob([
    ("a1", [0.90, 0.05, 0.05, 0.20, 0.05, 0.00], "forge", "openai"),
    ("a2", [0.88, 0.07, 0.04, 0.19, 0.04, 0.01], "forge", "openai"),
    ("a3", [0.91, 0.04, 0.06, 0.21, 0.06, 0.00], "forge", "anthropic"),
    ("a4", [0.89, 0.06, 0.05, 0.18, 0.05, 0.02], "replay", "openai"),
    ("b1", [0.05, 0.90, 0.10, 0.00, 0.00, 0.20], "replay", "zai"),
    ("b2", [0.07, 0.88, 0.12, 0.01, 0.02, 0.18], "replay", "zai"),
    ("b3", [0.04, 0.91, 0.09, 0.00, 0.01, 0.21], "replay", "zai"),
    ("b4", [0.06, 0.89, 0.11, 0.02, 0.00, 0.19], "forge", "zai"),
    ("c1", [0.00, 0.10, 0.95, 0.10, 0.05, 0.00], "eval", "openai"),
    ("c2", [0.02, 0.08, 0.90, 0.12, 0.03, 0.01], "eval", "openai"),
    ("c3", [0.01, 0.12, 0.94, 0.09, 0.06, 0.00], "eval", "anthropic"),
    ("c4", [0.00, 0.09, 0.96, 0.11, 0.04, 0.02], "eval", "openai"),
])

PY3_SPEC = PY_COMMON + """It must define exactly one public function:

    def kmeans_partition(records: list[dict], k: int = 3) -> dict

`records` is a list of dicts with keys `run_id` (str), `vector` (list[float]),
`run_kind` (str), `provider` (str). Return a dict with exactly the key
"clusters": a list with one dict per non-empty final cluster, in the
repository's FINAL cluster order (after its post-processing sort and id
reassignment), each dict with exactly the keys "cluster_id",
"member_run_ids", "member_count", "avg_internal_distance",
"dominant_run_kind", "dominant_provider":

- "cluster_id": the reassigned id the repository gives after its final sort
- "member_run_ids": the member run_ids in the repository's member ordering
- "member_count": number of members
- "avg_internal_distance": the cluster's average internal distance as the
  repository computes it (its normalization included), rounded to 6 decimals
- "dominant_run_kind" / "dominant_provider": the dominant values with the
  repository's tie-breaking, or null when the cluster has no such values

You must reproduce the repository's deterministic k-means EXACTLY (the
implementation in `clustering.py`): the seeded RNG object and its exact
sequence of calls, the k-means++-style initialization including the weighted
choice and the all-identical fallback, the assignment tie-breaking, the
centroid update convention (see `compute_centroid`), the empty-cluster
reinitialization rule, the convergence threshold and iteration cap, the
skipping of empty clusters, the final sort, and the id reassignment. A
different-but-similar clustering algorithm will NOT match.

Files that define the semantics you must match:
- packages/dspx-core/src/dspx/coordinates/clustering.py
- packages/dspx-core/src/dspx/coordinates/metrics.py"""

PY3_CHECKER = '''
import importlib.util, json, pathlib, sys, types

BASE = pathlib.Path("packages/dspx-core/src/dspx")
DELIVERABLE = pathlib.Path("packages/dspx-core/src/dspx/coordinates/g3p_kmeans_partition.py")
RECORDS = json.loads(sys.argv[1])
K = json.loads(sys.argv[2])
TOL = 1e-9

pkg = types.ModuleType("dspx"); pkg.__path__ = [str(BASE)]; sys.modules["dspx"] = pkg
coord = types.ModuleType("dspx.coordinates"); coord.__path__ = [str(BASE / "coordinates")]
sys.modules["dspx.coordinates"] = coord
clustering = importlib.import_module("dspx.coordinates.clustering")

def mk(r):
    o = types.SimpleNamespace()
    o.run_id = r["run_id"]; o.vector = r["vector"]; o.dimension = len(r["vector"])
    o.input_text = ""; o.output_text = ""; o.config_text = ""
    o.run_kind = r["run_kind"]; o.provider = r["provider"]; o.template_version = None
    return o

embs = [mk(r) for r in RECORDS]
clusters = clustering.simple_kmeans(embs, k=K)
want = {"clusters": [
    {"cluster_id": c.cluster_id,
     "member_run_ids": list(c.member_ids),
     "member_count": c.member_count,
     "avg_internal_distance": round(c.avg_internal_distance, 6),
     "dominant_run_kind": c.dominant_run_kind,
     "dominant_provider": c.dominant_provider}
    for c in clusters]}

assert DELIVERABLE.exists(), "deliverable missing"
spec = importlib.util.spec_from_file_location("g3p_kmeans_partition", DELIVERABLE)
mod = importlib.util.module_from_spec(spec); sys.modules["g3p_kmeans_partition"] = mod
spec.loader.exec_module(mod)
out = mod.kmeans_partition(RECORDS, k=K)
assert set(out) == {"clusters"}, sorted(out)
assert len(out["clusters"]) == len(want["clusters"]), (len(out["clusters"]), len(want["clusters"]))
for got, exp in zip(out["clusters"], want["clusters"]):
    assert set(got) == set(exp), sorted(got)
    assert got["cluster_id"] == exp["cluster_id"], (got["cluster_id"], exp["cluster_id"])
    assert got["member_run_ids"] == exp["member_run_ids"], (got["member_run_ids"], exp["member_run_ids"])
    assert got["member_count"] == exp["member_count"]
    assert abs(got["avg_internal_distance"] - exp["avg_internal_distance"]) <= TOL, (got, exp)
    assert got["dominant_run_kind"] == exp["dominant_run_kind"], (got, exp)
    assert got["dominant_provider"] == exp["dominant_provider"], (got, exp)
print("ACCEPT")
'''

# ---------------------------------------------------------------- PY-4
def _grp(items):
    return [{"run_id": rid, "vector": v} for rid, v in items]

PY4_INPUT = {
    "groups": [
        _grp([("g1a", [0.90, 0.10, 0.05, 0.20, 0.05, 0.00]),
              ("g1b", [0.91, 0.09, 0.06, 0.19, 0.04, 0.01]),
              ("g1c", [0.89, 0.11, 0.04, 0.21, 0.06, 0.00]),
              ("g1d", [0.90, 0.10, 0.05, 0.20, 0.05, 0.01]),
              ("g1e", [0.92, 0.08, 0.07, 0.18, 0.03, 0.02])]),
        _grp([("g2a", [1.00, 0.00, 0.00, 0.00, 0.00, 0.00]),
              ("g2b", [-1.00, 0.00, 0.00, 0.00, 0.00, 0.00]),
              ("g2c", [0.00, 1.00, 0.00, 0.00, 0.00, 0.00]),
              ("g2d", [0.00, -1.00, 0.00, 0.00, 0.00, 0.00]),
              ("g2e", [0.00, 0.00, 1.00, 0.00, 0.00, 0.00]),
              ("g2f", [0.00, 0.00, -1.00, 0.00, 0.00, 0.00])]),
        _grp([("g3a", [0.00, 0.10, 0.95, 0.10, 0.05, 0.00]),
              ("g3b", [0.02, 0.08, 0.90, 0.12, 0.03, 0.01])]),
        _grp([("g4a", [1.00, 0.00, 0.00, 0.00, 0.00, 0.00])]),
        [],
        _grp([("g6a", [0.70, 0.70, 0.00, 0.00, 0.00, 0.00]),
              ("g6b", [0.71, 0.69, 0.01, 0.01, 0.00, 0.00]),
              ("g6b2", [0.69, 0.71, 0.01, 0.00, 0.01, 0.00]),
              ("g6c", [0.30, 0.30, 0.60, 0.60, 0.00, 0.00]),
              ("g6d", [0.28, 0.32, 0.62, 0.58, 0.01, 0.00]),
              ("g6e", [0.31, 0.29, 0.58, 0.62, 0.00, 0.01])]),
    ],
    "danger_zones": [
        {"zone_id": "Z1", "centroid": [0.90, 0.10, 0.05, 0.20, 0.05, 0.00], "radius": 0.05,
         "reason": "known flaky region", "severity": "high", "dimension": 6},
        {"zone_id": "Z2", "centroid": [0.00, 0.00, 0.00, 0.00, 1.00, 0.00], "radius": 0.10,
         "reason": "unrelated zone", "severity": "low", "dimension": 6},
    ],
    "groups_without_zones": [1],
}

PY4_SPEC = PY_COMMON + """It must define exactly one public function:

    def classify_groups(groups: list[list[dict]], danger_zones: list[dict] | None = None) -> list[dict]

`groups` is a list of groups; each group is a list of dicts with keys
`run_id` (str) and `vector` (list[float]). `danger_zones` (when given) is a
list of dicts with keys `centroid` (list[float]) and `radius` (float) among
others. Return a list with one dict per group, in input order, each with
exactly the keys "type" and "confidence":

- "type": the region-type NAME (the string value of the repository's region
  type enum in `territory.py`) the repository's region classifier assigns to
  that group.
- "confidence": the classifier's confidence for that group, rounded to 4
  decimal places.

You must reproduce the repository's region classifier EXACTLY, including: the
insufficient-sample branches and their distinct confidences, the internal
variance computation it uses (see `compute_internal_variance`, including its
centroid convention from `clustering.py` and the distance normalization from
`metrics.py`), the variance thresholds, the confidence formulas for each
band, the danger-zone rule (distance convention and comparison, and the
danger confidence constant), and the branch order between danger zones and
variance bands.

Files that define the semantics you must match:
- packages/dspx-core/src/dspx/coordinates/territory.py
- packages/dspx-core/src/dspx/coordinates/clustering.py
- packages/dspx-core/src/dspx/coordinates/metrics.py"""

PY4_CHECKER = '''
import importlib.util, json, pathlib, sys, types

BASE = pathlib.Path("packages/dspx-core/src/dspx")
DELIVERABLE = pathlib.Path("packages/dspx-core/src/dspx/coordinates/g3p_classify_groups.py")
INPUT = json.loads(sys.argv[1])

pkg = types.ModuleType("dspx"); pkg.__path__ = [str(BASE)]; sys.modules["dspx"] = pkg
coord = types.ModuleType("dspx.coordinates"); coord.__path__ = [str(BASE / "coordinates")]
sys.modules["dspx.coordinates"] = coord
territory = importlib.import_module("dspx.coordinates.territory")

def mk(r):
    o = types.SimpleNamespace()
    o.run_id = r["run_id"]; o.vector = r["vector"]; o.dimension = len(r["vector"])
    o.input_text = ""; o.output_text = ""; o.config_text = ""
    o.run_kind = "run"; o.provider = "p"; o.template_version = None
    return o

def zones(specs):
    if specs is None:
        return None
    out = []
    for z in specs:
        o = types.SimpleNamespace()
        o.zone_id = z["zone_id"]; o.centroid = z["centroid"]; o.radius = z["radius"]
        o.reason = z.get("reason", ""); o.severity = z.get("severity", "low")
        o.dimension = len(z["centroid"])
        out.append(o)
    return out

groups = [[mk(r) for r in g] for g in INPUT["groups"]]
want_with = []
for g in groups:
    t, c = territory.classify_region(g, known_danger_zones=zones(INPUT["danger_zones"]))
    want_with.append({"type": t.value, "confidence": round(c, 4)})
no_zone_idx = set(INPUT["groups_without_zones"])
want_without = []
for i in sorted(no_zone_idx):
    t, c = territory.classify_region(groups[i])
    want_without.append({"type": t.value, "confidence": round(c, 4)})

assert DELIVERABLE.exists(), "deliverable missing"
spec = importlib.util.spec_from_file_location("g3p_classify_groups", DELIVERABLE)
mod = importlib.util.module_from_spec(spec); sys.modules["g3p_classify_groups"] = mod
spec.loader.exec_module(mod)

out_with = mod.classify_groups(INPUT["groups"], INPUT["danger_zones"])
assert len(out_with) == len(want_with), (len(out_with), len(want_with))
for got, exp in zip(out_with, want_with):
    assert set(got) == {"type", "confidence"}, sorted(got)
    assert got["type"] == exp["type"], (got["type"], exp["type"])
    assert abs(got["confidence"] - exp["confidence"]) <= 1e-9, (got, exp)
out_without = mod.classify_groups([INPUT["groups"][i] for i in sorted(no_zone_idx)])
for got, exp in zip(out_without, want_without):
    assert got["type"] == exp["type"], (got["type"], exp["type"])
    assert abs(got["confidence"] - exp["confidence"]) <= 1e-9, (got, exp)
print("ACCEPT")
'''

# ---------------------------------------------------------------- PY-5
PY5_INPUT = [
    ("a1", [0.90, 0.05, 0.05, 0.20, 0.05, 0.00], "forge", "openai", "alpha beta gamma", "result ok"),
    ("a2", [0.88, 0.07, 0.04, 0.19, 0.04, 0.01], "forge", "openai", "alpha beta gamma delta epsilon", "result ok"),
    ("a3", [0.91, 0.04, 0.06, 0.21, 0.06, 0.00], "forge", "anthropic", "alpha beta", "result"),
    ("a4", [0.89, 0.06, 0.05, 0.18, 0.05, 0.02], "replay", "openai", "alpha beta gamma delta", "result ok fine"),
    ("a5", [0.90, 0.05, 0.05, 0.20, 0.04, 0.01], "forge", "openai", "alpha", "r"),
    ("a6", [0.92, 0.04, 0.05, 0.19, 0.05, 0.00], "forge", "openai", "alpha beta gamma delta epsilon zeta", "result ok"),
    ("b1", [0.05, 0.90, 0.10, 0.00, 0.00, 0.20], "replay", "zai", "x", "y"),
    ("b2", [0.07, 0.88, 0.12, 0.01, 0.02, 0.18], "replay", "zai", "x y z w v u", "y2"),
    ("b3", [0.04, 0.91, 0.09, 0.00, 0.01, 0.21], "replay", "zai", "x y", "y3"),
    ("b4", [0.06, 0.89, 0.11, 0.02, 0.00, 0.19], "forge", "zai", "x y z", "y4"),
    ("b5", [0.05, 0.91, 0.10, 0.01, 0.01, 0.20], "replay", "zai", "x y z w", "y5"),
    ("c1", [0.00, 0.10, 0.95, 0.10, 0.05, 0.00], "eval", "openai", "p", "q"),
    ("c2", [0.02, 0.08, 0.90, 0.12, 0.03, 0.01], "eval", "openai", "p q", "q2"),
    ("c3", [0.01, 0.12, 0.94, 0.09, 0.06, 0.00], "eval", "anthropic", "p q r", "q3"),
]
PY5_INPUT = [{"run_id": t[0], "vector": t[1], "run_kind": t[2], "provider": t[3],
              "input_text": t[4], "output_text": t[5]} for t in PY5_INPUT]

PY5_SPEC = PY_COMMON + """It must define exactly one public function:

    def attractor_landscape(records: list[dict], k: int = 3,
                            min_stability: float = 0.5, min_samples: int = 5) -> dict

`records` is a list of dicts with keys `run_id` (str), `vector` (list[float]),
`run_kind` (str), `provider` (str), `input_text` (str), `output_text` (str).
Return a dict with exactly the keys "attractors", "total_embeddings",
"avg_stability", "strong_attractor_count", "coverage", "health":

- "attractors": the detected attractors in the repository's final order and
  id assignment (see `find_attractors` in `attractors.py`), each a dict with
  exactly "attractor_id", "member_run_ids" (the repository's member
  ordering), "member_count", "stability_score" (rounded 4), "basin_radius"
  (rounded 4), "dominant_run_kind", "dominant_provider" (null when absent).
- "total_embeddings", "strong_attractor_count": integers as the repository
  computes them.
- "avg_stability", "coverage": rounded to 4 decimal places, as the repository
  computes them.
- "health": exactly the dict the repository's attractor-health function
  returns for this landscape (same keys, same values; round any float values
  to 6 decimal places).

You must reproduce the repository's attractor pipeline EXACTLY: its default
minimum-samples constant, its deterministic clustering (see `clustering.py`),
its stability and convergence scoring (see `attractors.py`), its
minimum-stability and minimum-samples filters, its basin-radius rule, its
final sort and id reassignment, its report statistics including the coverage
estimate, and its health verdict thresholds and recommendation rules.

Files that define the semantics you must match:
- packages/dspx-core/src/dspx/coordinates/attractors.py
- packages/dspx-core/src/dspx/coordinates/clustering.py
- packages/dspx-core/src/dspx/coordinates/metrics.py"""

PY5_CHECKER = '''
import importlib.util, json, pathlib, sys, types

BASE = pathlib.Path("packages/dspx-core/src/dspx")
DELIVERABLE = pathlib.Path("packages/dspx-core/src/dspx/coordinates/g3p_attractor_landscape.py")
RECORDS = json.loads(sys.argv[1])
K = json.loads(sys.argv[2])
TOL = 1e-9

pkg = types.ModuleType("dspx"); pkg.__path__ = [str(BASE)]; sys.modules["dspx"] = pkg
coord = types.ModuleType("dspx.coordinates"); coord.__path__ = [str(BASE / "coordinates")]
sys.modules["dspx.coordinates"] = coord
attractors = importlib.import_module("dspx.coordinates.attractors")

def mk(r):
    o = types.SimpleNamespace()
    o.run_id = r["run_id"]; o.vector = r["vector"]; o.dimension = len(r["vector"])
    o.input_text = r.get("input_text", ""); o.output_text = r.get("output_text", "")
    o.config_text = ""; o.run_kind = r["run_kind"]; o.provider = r["provider"]
    o.template_version = None
    return o

embs = [mk(r) for r in RECORDS]
index = types.SimpleNamespace(list_all=lambda limit=10000: embs)
report = attractors.find_attractors(index, k=K)
health = attractors.compute_attractor_health(report)

# membership: recompute the same deterministic clustering and join by centroid
clusters = attractors.simple_kmeans(embs, k=K, seed=42)
cluster_by_centroid = {tuple(round(x, 9) for x in c.centroid): c for c in clusters}
want_attractors = []
for a in report.attractors:
    cl = cluster_by_centroid[tuple(round(x, 9) for x in a.centroid)]
    want_attractors.append({"attractor_id": a.attractor_id,
                            "member_run_ids": list(cl.member_ids),
                            "member_count": a.member_count,
                            "stability_score": round(a.stability_score, 4),
                            "basin_radius": round(a.basin_radius, 4),
                            "dominant_run_kind": a.dominant_run_kind,
                            "dominant_provider": a.dominant_provider})

def r6(x):
    return round(x, 6) if isinstance(x, float) else x

want = {
    "attractors": want_attractors,
    "total_embeddings": report.total_embeddings,
    "avg_stability": round(report.avg_stability, 4),
    "strong_attractor_count": report.strong_attractor_count,
    "coverage": round(report.coverage, 4),
    "health": {k: (r6(v) if not isinstance(v, list) else v) for k, v in health.items()},
}

assert DELIVERABLE.exists(), "deliverable missing"
spec = importlib.util.spec_from_file_location("g3p_attractor_landscape", DELIVERABLE)
mod = importlib.util.module_from_spec(spec); sys.modules["g3p_attractor_landscape"] = mod
spec.loader.exec_module(mod)
out = mod.attractor_landscape(RECORDS, k=K)
assert set(out) == set(want), sorted(out)
assert len(out["attractors"]) == len(want["attractors"]), (len(out["attractors"]), len(want["attractors"]))
for got, exp in zip(out["attractors"], want["attractors"]):
    assert set(got) == set(exp), sorted(got)
    assert got["attractor_id"] == exp["attractor_id"], (got, exp)
    assert got["member_run_ids"] == exp["member_run_ids"], (got["member_run_ids"], exp["member_run_ids"])
    assert got["member_count"] == exp["member_count"], (got, exp)
    assert abs(got["stability_score"] - exp["stability_score"]) <= TOL, (got, exp)
    assert abs(got["basin_radius"] - exp["basin_radius"]) <= TOL, (got, exp)
    assert got["dominant_run_kind"] == exp["dominant_run_kind"], (got, exp)
    assert got["dominant_provider"] == exp["dominant_provider"], (got, exp)
assert out["total_embeddings"] == want["total_embeddings"]
assert out["strong_attractor_count"] == want["strong_attractor_count"]
assert abs(out["avg_stability"] - want["avg_stability"]) <= TOL, (out["avg_stability"], want["avg_stability"])
assert abs(out["coverage"] - want["coverage"]) <= TOL, (out["coverage"], want["coverage"])
assert set(out["health"]) == set(want["health"]), (sorted(out["health"]), sorted(want["health"]))
for k in want["health"]:
    gv, ev = out["health"][k], want["health"][k]
    if isinstance(ev, list):
        assert gv == ev, (k, gv, ev)
    elif isinstance(ev, float):
        assert abs(gv - ev) <= TOL, (k, gv, ev)
    else:
        assert gv == ev, (k, gv, ev)
print("ACCEPT")
'''

# ---------------------------------------------------------------- TS-1
TS1_INPUT = [
    {"kind": "path", "value": "src/app/main.ts"},
    {"kind": "path", "value": " src/leading.ts"},
    {"kind": "path", "value": "https://example.com/x"},
    {"kind": "path", "value": "/abs/path.ts"},
    {"kind": "path", "value": "~/home/x.ts"},
    {"kind": "path", "value": "a\\b\\c.ts"},
    {"kind": "path", "value": "a/../b.ts"},
    {"kind": "path", "value": ".hidden/x.ts"},
    {"kind": "path", "value": "__pycache__/mod.py"},
    {"kind": "path", "value": "node_modules/pkg/index.js"},
    {"kind": "path", "value": "dist/bundle.js"},
    {"kind": "path", "value": ""},
    {"kind": "path", "value": "ok\u0001ctrl.ts"},
    {"kind": "symbol", "value": "buildContextPlan"},
    {"kind": "symbol", "value": "x" * 241},
    {"kind": "symbol", "value": "bad\u007fsymbol"},
    {"kind": "symbol", "value": "  "},
    {"kind": "Path", "value": "src/x.ts"},
    {"kind": 42, "value": "src/y.ts"},
    {"kind": "free_text", "value": "anything goes /abs ~x  ok"},
    {"kind": "ak", "value": "ak://task/5080"},
]

TS1_SPEC = TS_COMMON + """It must export exactly one named function:

    export function auditSeeds(seeds)

`seeds` is an array of objects `{ kind, value }` (kind may be any JSON value,
value a string or other). Return an array with exactly one entry per input
seed, in input order, each entry an object with exactly the keys
`normalizedKind` and `issue`:

- `normalizedKind`: the seed kind normalized with the same convention as
  `normalizeContextPlanSeedKind` in `src/context-plan.js` (including the
  non-string fallback and the unknown-kind fallback).
- `issue`: for a normalized kind of `path`, the exact issue string produced
  by the repository's repo-relative path safety check (or null when the seed
  is safe); for `symbol`, the exact issue string of the repository's symbol
  seed safety check (or null); for every other normalized kind, null. Use the
  default labels of those checks.

Match the repository checks EXACTLY, including: control-character detection
(which code points count), the URI/drive-prefix rule, absolute/home-relative
rules, the backslash rule, current/parent directory traversal, hidden and
internal directory parts, generated/vendor directory parts, the empty-value
rule, the symbol length limit, and whitespace handling.

Files that define the semantics you must match:
- packages/pi-context-packer/src/context-plan.js
- packages/pi-context-packer/src/context-intake-safety.js"""

TS1_CHECKER = '''
import assert from "node:assert/strict";
import test from "node:test";
const { normalizeContextPlanSeedKind } = await import("./src/context-plan.js");
const { repoRelativePathSafetyIssue, symbolSeedSafetyIssue } = await import("./src/context-intake-safety.js");
const mod = await import("./g3p-seed-audit.mjs");
const SEEDS = JSON.parse(process.argv[2] ?? "[]");

test("parity", () => {
  const out = mod.auditSeeds(SEEDS);
  assert.ok(Array.isArray(out) && out.length === SEEDS.length, "shape");
  for (let i = 0; i < SEEDS.length; i += 1) {
    const kind = normalizeContextPlanSeedKind(SEEDS[i].kind);
    let issue = null;
    if (kind === "path") issue = repoRelativePathSafetyIssue(SEEDS[i].value) ?? null;
    if (kind === "symbol") issue = symbolSeedSafetyIssue(SEEDS[i].value) ?? null;
    const got = out[i];
    assert.deepEqual(Object.keys(got).sort(), ["issue", "normalizedKind"], `entry ${i} keys`);
    assert.equal(got.normalizedKind, kind, `entry ${i} kind`);
    assert.equal(got.issue, issue, `entry ${i} issue`);
  }
  console.log("ACCEPT");
});
'''

# ---------------------------------------------------------------- TS-2
TS2_INPUT = {
    "seeds": [
        {"kind": "path", "value": "g3p-fixtures/big-code.ts"},
        {"kind": "path", "value": "g3p-fixtures/big.md"},
        {"kind": "path", "value": "g3p-fixtures/sub/big.test.js"},
        {"kind": "path", "value": "g3p-fixtures/node_modules/skip.js"},
        {"kind": "path", "value": "g3p-fixtures/app.min.js"},
        {"kind": "path", "value": "g3p-fixtures/link.md"},
        {"kind": "path", "value": "g3p-fixtures/missing.ts"},
        {"kind": "path", "value": "../outside.ts"},
        {"kind": "path", "value": "g3p-fixtures/big-code.ts"},
        {"kind": "path", "value": "g3p-fixtures/data.json"},
        {"kind": "path", "value": "g3p-fixtures/fine.ts"},
        {"kind": "path", "value": "/abs/no-final-newline.md"},
        {"kind": "symbol", "value": "not-a-path"},
        {"kind": "path", "value": 42},
    ],
}

TS2_SPEC = TS_COMMON + """It must export exactly one named function:

    export function budgetRisks(seeds, root)

Return an object with exactly the keys `risks` and `unsafeSeeds`.

`risks`: reproduce the semantics of the repository's path-seed file-budget
risk analysis (`fileBudgetRisksForPathSeeds` in `src/file-budget.js`):
- consider only seeds whose kind is exactly `path` with a string value
- resolve each value against `root` exactly as the repository does; skip
  values that resolve outside `root` (containment rule included)
- de-duplicate by the same key the repository uses (first occurrence wins)
- classify each remaining path with the repository's file-budget kind rules
  (excluded directories, excluded suffixes, markdown extensions, code
  extensions, test-file patterns) — unclassified paths produce no risk entry
- skip symbolic links and non-regular/missing files exactly as the repository
  does
- count lines with the repository's line-counting semantics (pay attention to
  the final-newline rule), read byte sizes, and apply the repository's
  per-kind line/byte budgets
- each risk entry is an object with exactly the keys `path`, `kind`,
  `lines`, `bytes`, `maxLines`, `maxBytes` and the repository's value
  conventions (including path normalization); keep the repository's order

`unsafeSeeds`: for every seed with kind exactly `path` and a string value
(in input order, duplicates included), the entries for which the
repository's repo-relative path safety check (`repoRelativePathSafetyIssue`
in `src/context-intake-safety.js`) reports an issue, each an object with
exactly the keys `value` and `issue` (the exact issue string).

The caller will create fixture files under `root/g3p-fixtures/` (and one
root-level file) before calling you; read them from disk like the repository
does.

Files that define the semantics you must match:
- packages/pi-context-packer/src/file-budget.js
- packages/pi-context-packer/src/context-intake-safety.js"""

TS2_CHECKER = '''
import assert from "node:assert/strict";
import test from "node:test";
import path from "node:path";
import { mkdirSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
const { fileBudgetRisksForPathSeeds } = await import("./src/file-budget.js");
const { repoRelativePathSafetyIssue } = await import("./src/context-intake-safety.js");
const mod = await import("./g3p-budget-risks.mjs");
const INPUT = JSON.parse(process.argv[2] ?? "{}");
const root = process.cwd();

rmSync(path.join(root, "g3p-fixtures"), { recursive: true, force: true });
mkdirSync(path.join(root, "g3p-fixtures/sub"), { recursive: true });
mkdirSync(path.join(root, "g3p-fixtures/node_modules"), { recursive: true });
writeFileSync(path.join(root, "g3p-fixtures/big-code.ts"), "x\\n".repeat(600));
writeFileSync(path.join(root, "g3p-fixtures/big.md"), "m".repeat(61 * 1024));
writeFileSync(path.join(root, "g3p-fixtures/sub/big.test.js"), "t\\n".repeat(1100));
writeFileSync(path.join(root, "g3p-fixtures/node_modules/skip.js"), "n".repeat(10));
writeFileSync(path.join(root, "g3p-fixtures/app.min.js"), "a".repeat(10));
writeFileSync(path.join(root, "g3p-fixtures/data.json"), "{}");
writeFileSync(path.join(root, "g3p-fixtures/fine.ts"), "ok();\\n");
writeFileSync(path.join(root, "abs-no-final-newline.md"), "z".repeat(61 * 1024));
writeFileSync(path.join(root, "g3p-fixtures/target.txt"), "hello");
symlinkSync(path.join(root, "g3p-fixtures/target.txt"), path.join(root, "g3p-fixtures/link.md"));

const wantRisks = fileBudgetRisksForPathSeeds({ seeds: INPUT.seeds, cwd: root, repoRoot: root });
const wantUnsafe = INPUT.seeds
  .filter((s) => s?.kind === "path" && typeof s.value === "string")
  .map((s) => ({ value: s.value, issue: repoRelativePathSafetyIssue(s.value) }))
  .filter((s) => s.issue !== undefined);

test("parity", () => {
  const got = mod.budgetRisks(INPUT.seeds, root);
  assert.deepEqual(Object.keys(got).sort(), ["risks", "unsafeSeeds"], "top keys");
  assert.ok(Array.isArray(got.risks) && Array.isArray(got.unsafeSeeds), "arrays");
  assert.equal(got.risks.length, wantRisks.length, JSON.stringify({ got: got.risks, want: wantRisks }, null, 1));
  for (let i = 0; i < wantRisks.length; i += 1) {
    assert.deepEqual(Object.keys(got.risks[i]).sort(), ["bytes", "kind", "lines", "maxBytes", "maxLines", "path"], "keys");
    assert.deepEqual(got.risks[i], wantRisks[i], `risk entry ${i}`);
  }
  assert.equal(got.unsafeSeeds.length, wantUnsafe.length, JSON.stringify({ got: got.unsafeSeeds, want: wantUnsafe }, null, 1));
  for (let i = 0; i < wantUnsafe.length; i += 1) {
    assert.deepEqual(Object.keys(got.unsafeSeeds[i]).sort(), ["issue", "value"], "keys");
    assert.deepEqual(got.unsafeSeeds[i], wantUnsafe[i], `unsafe entry ${i}`);
  }
  console.log("ACCEPT");
});
'''

# ---------------------------------------------------------------- TS-3
TS3_INPUT = {
    "providers": ["agents", "git", "docs", "session", "sci", "prompt_vault", "ak", "fcos", "nope"],
    "cases": [
        {"env": {}, "planContext": {}},
        {"env": {"sciReadOnlySafe": True}, "planContext": {}},
        {"env": {"sciReadOnlySafe": True, "contextUsage": {"tokens": 900000, "windowTokens": 1000000}},
         "planContext": {"reason": "provider required by caller"}},
        {"env": {"sciReadOnlySafe": False, "contextUsage": {"inputTokens": 130000, "limitTokens": 1000000}},
         "planContext": {}},
        {"env": {"sciReadOnlySafe": True, "contextUsage": {"totalTokens": 500, "contextWindow": 1000}},
         "planContext": {"reason": "other"}},
        {"env": {"sciReadOnlySafe": True, "contextUsage": {"usedTokens": 400000, "maxTokens": 500000}},
         "planContext": {}},
    ],
}

TS3_SPEC = TS_COMMON + """It must export exactly one named function:

    export function providerMatrix(providers, env, planContext)

For each provider name in `providers` (array of strings) return an object,
in input order, with exactly the keys `provider`, `adapterStatus`,
`executionStatus` — the capability values the repository's provider
capability classifier returns for that provider under the given `env` and
`planContext`. Unknown providers follow the repository's unknown-provider
convention. You must reproduce the repository's gating rules exactly,
including: the safety gate for the SCI provider, the session-provider
eligibility rule (the caller-reason condition and the context-pressure
condition computed with the repository's session context usage
normalization: which usage fields are read, in which precedence, and the
numeric thresholds that make pressure "high").

Files that define the semantics you must match:
- packages/pi-context-packer/src/provider-capabilities.js
- packages/pi-context-packer/src/session-context.js"""

TS3_CHECKER = '''
import assert from "node:assert/strict";
import test from "node:test";
const { contextPackProviderCapability } = await import("./src/provider-capabilities.js");
const mod = await import("./g3p-provider-matrix.mjs");
const INPUT = JSON.parse(process.argv[2] ?? "{}");

test("parity", () => {
  for (const c of INPUT.cases) {
    const got = mod.providerMatrix(INPUT.providers, c.env, c.planContext);
    assert.ok(Array.isArray(got) && got.length === INPUT.providers.length, "shape");
    INPUT.providers.forEach((p, i) => {
      const want = contextPackProviderCapability(p, c.env, c.planContext);
      assert.deepEqual(Object.keys(got[i]).sort(), ["adapterStatus", "executionStatus", "provider"], "keys");
      assert.equal(got[i].provider, p);
      assert.equal(got[i].adapterStatus, want.adapterStatus, `${p} adapterStatus`);
      assert.equal(got[i].executionStatus, want.executionStatus, `${p} executionStatus`);
    });
  }
  console.log("ACCEPT");
});
'''

# ---------------------------------------------------------------- TS-4
TS4_INPUT_OK = {
    "ok": True,
    "packet": {
        "objective": "Explain <context> pressure and `budgets`",
        "sections": [
            {
                "title": "Repo docs", "provider": "docs", "authority": "docs are data",
                "items": [
                    {"id": "docs/readme", "kind": "markdown", "contentMode": "text",
                     "content": "# Hello\\n\\nSome `code` and ``double`` and ```triple``` fences\\n",
                     "rationale": "primary doc", "provenance": {"path": "README.md"}},
                    {"id": "werd\\tid", "kind": "text", "contentMode": "text",
                     "content": "plain", "rationale": "",
                     "provenance": {"command": "git status --short"}},
                ],
                "estimatedTokens": 42,
            },
            {
                "title": "Git", "provider": "git", "authority": "read-only",
                "items": [], "estimatedTokens": 0,
            },
        ],
        "omissions": [
            {"provider": "sci", "reason": "safety gate", "detail": ""},
            {"provider": "session", "reason": "not eligible", "detail": "caller did not require it"},
        ],
        "ownerSurfaceRecommendations": [
            {"surface": "Prompt Vault", "nextAction": "retrieve template", "nonAuthorization": "read-only"},
        ],
        "totals": {"candidatesSelected": 2, "estimatedTokens": 42, "bytes": 1234},
        "measurementReceipt": {
            "estimatedToolCallsAvoided": 7,
            "packetUtilityRecommendation": {
                "status": "useful", "reason": "bounded read surface",
                "nextAction": "proceed", "nonAuthorization": "advisory only",
            },
            "dogfoodFollowupReceipt": {
                "status": "pending",
                "expectedLowLevelCallsAvoided": 4,
                "nonAuthorization": "record-only",
            },
        },
        "dogfoodObservationTemplate": {"activityType": "implementation"},
        "nonAuthorizations": ["does not mutate files", "does not authorize owner-surface movement"],
    },
}
TS4_INPUT_FAIL = {
    "ok": False,
    "plan": {"ok": False, "errors": ["objective missing", "seeds exceed limit"]},
}
TS4_INPUT_MIN = {
    "ok": True,
    "packet": {
        "objective": "Empty",
        "sections": [],
        "omissions": [],
        "totals": {"candidatesSelected": 0, "estimatedTokens": 0, "bytes": 0},
        "measurementReceipt": {
            "estimatedToolCallsAvoided": 0,
            "packetUtilityRecommendation": None,
            "dogfoodFollowupReceipt": None,
        },
        "nonAuthorizations": [],
    },
}

TS4_SPEC = TS_COMMON + """It must export exactly one named function:

    export function renderPacket(result)

`result` is an object shaped like a context-packet result (fields: `ok`,
`packet`, or `plan`). Return a STRING that is byte-for-byte identical to what
the repository's packet renderer (`formatContextPacket` in
`src/context-pack-result.js`) returns for the same input — including the
not-ok fallback path (which delegates to the context-plan formatter in
`src/context-plan.js`; reproduce its failure line for a failed plan
exactly).

Reproduce the rendering EXACTLY, including: heading and meta lines, optional
provenance lines and their presence rules, inline-label sanitization
(control characters, angle brackets, whitespace collapsing, fallbacks,
truncation with the exact ellipsis character), markdown fence construction
(fence length rule over content and label, the label comment line),
omission lines with their fallbacks, owner-surface recommendation lines,
totals lines, the fixed scaffolding lines, the packet-utility and
dogfood-follow-up sections with their null handling, and the dogfood
observation template block (exact JSON formatting).

Files that define the semantics you must match:
- packages/pi-context-packer/src/context-pack-result.js
- packages/pi-context-packer/src/context-intake-safety.js
- packages/pi-context-packer/src/context-plan.js
- packages/pi-context-packer/src/dogfood-followup-classes.js"""

TS4_CHECKER = '''
import assert from "node:assert/strict";
import test from "node:test";
const { formatContextPacket } = await import("./src/context-pack-result.js");
const mod = await import("./g3p-render-packet.mjs");
const CASES = JSON.parse(process.argv[2] ?? "[]");

test("parity", () => {
  for (const c of CASES) {
    const want = formatContextPacket(c);
    const got = mod.renderPacket(c);
    assert.equal(typeof got, "string", "string result");
    assert.ok(got.length > 0, "non-empty");
    assert.equal(got, want, "byte-identical render");
  }
  console.log("ACCEPT");
});
'''

# ---------------------------------------------------------------- TS-5
TS5_INPUT = {
    "caseDefinition": {
        "question": "change the focused test behavior and its docs for the adapter",
    },
    "repository": {
        "records": [
            {"path": "src/adapter/core.ts", "metadataStatus": "present",
             "summary": "adapter behavior and change handling", "readWhen": ["changing adapter behavior"]},
            {"path": "src/adapter/core.test.ts", "metadataStatus": "present",
             "summary": "tests for adapter change behavior", "readWhen": ["changing focused tests"]},
            {"path": "docs/adapter.md", "metadataStatus": "present",
             "summary": "adapter docs overview", "readWhen": ["docs"]},
            {"path": "src/other/thing.ts", "metadataStatus": "present",
             "summary": "unrelated the and for its with filler", "readWhen": ["other"]},
            {"path": "src/adapter/util.ts", "metadataStatus": "missing",
             "summary": "adapter test change focused behavior", "readWhen": ["adapter tests"]},
            {"path": "src/zeta.ts", "metadataStatus": "present",
             "summary": "", "readWhen": []},
        ],
    },
    "structural": [
        {"path": "src/adapter/core.ts", "directCount": 3, "relatedCount": 1,
         "kindCounts": {"definition": 2, "reference": 1, "match": 0, "graph_node": 0, "graph_edge": 0}},
        {"path": "src/adapter/core.test.ts", "directCount": 3, "relatedCount": 2,
         "kindCounts": {"definition": 1, "reference": 2, "match": 1, "graph_node": 0, "graph_edge": 0}},
        {"path": "docs/adapter.md", "directCount": 1, "relatedCount": 0,
         "kindCounts": {"definition": 0, "reference": 0, "match": 1, "graph_node": 0, "graph_edge": 0}},
        {"path": "src/other/thing.ts", "directCount": 1, "relatedCount": 3,
         "kindCounts": {"definition": 0, "reference": 1, "match": 0, "graph_node": 1, "graph_edge": 1}},
        {"path": "src/adapter/util.ts", "directCount": 0, "relatedCount": 0,
         "kindCounts": {"definition": 0, "reference": 0, "match": 0, "graph_node": 0, "graph_edge": 0}},
        {"path": "src/zeta.ts", "directCount": 0, "relatedCount": 1,
         "kindCounts": {"definition": 1, "reference": 0, "match": 0, "graph_node": 0, "graph_edge": 0}},
    ],
    "arms": ["source_list", "structural", "fusion", "baseline"],
    "maxItemsList": [3, 5],
}

TS5_SPEC = TS_COMMON + """It must export exactly one named function:

    export function rankAndSelect(caseDefinition, repository, structuralEvidence, arm, maxItems)

Reproduce the repository's source-selection experiment ranking and arm
selection EXACTLY (see `src/source-selection-experiment-ranking.js` and the
helpers it uses from `src/source-selection-experiment-structural.js` and
`src/source-selection-experiment-utils.js`):

- build the ranking rows with the repository's token extraction from the
  case question (lowercasing, the word pattern, the minimum token length,
  the stop-word set, the deterministic token ordering), the path score
  (including its multiplier), the metadata score (including the
  metadata-status rule and which record fields feed it), and the structural
  counts taken from `structuralEvidence.stats` (a Map keyed by record path)
- apply the repository's arm-specific comparator cascade exactly
  (structural ordering with its kind tie-break order, the score sums, the
  metadata tie-break, the path-score tie-break, the final deterministic
  path comparison), including which arms use which blocks
- return the selected paths for the given `arm` and `maxItems` in the
  repository's order

Files that define the semantics you must match:
- packages/pi-context-packer/src/source-selection-experiment-ranking.js
- packages/pi-context-packer/src/source-selection-experiment-structural.js
- packages/pi-context-packer/src/source-selection-experiment-utils.js"""

TS5_CHECKER = '''
import assert from "node:assert/strict";
import test from "node:test";
const { buildRankingRows, selectArm } = await import("./src/source-selection-experiment-ranking.js");
const mod = await import("./g3p-rank-select.mjs");
const INPUT = JSON.parse(process.argv[2] ?? "{}");

const stats = new Map(INPUT.structural.map((s) => [s.path, s]));
const structuralEvidence = { stats };

test("parity", () => {
  const rows = buildRankingRows(INPUT.caseDefinition, INPUT.repository, structuralEvidence);
  for (const arm of INPUT.arms) {
    for (const maxItems of INPUT.maxItemsList) {
      const want = selectArm(rows, arm, maxItems);
      const got = mod.rankAndSelect(INPUT.caseDefinition, INPUT.repository, structuralEvidence, arm, maxItems);
      assert.ok(Array.isArray(got), "array");
      assert.deepEqual(got, want, `arm=${arm} maxItems=${maxItems}`);
    }
  }
  console.log("ACCEPT");
});
'''


# ---------------------------------------------------------------- assembly

def _task(task_id, repo_key, title, difficulty, rationale, grounding, deliverable,
          spec, checker, checker_input, run_dir, pv_cmd):
    return {
        "task_id": task_id,
        "repo_key": repo_key,
        "title": title,
        "difficulty": difficulty,
        "difficulty_rationale": rationale,
        "grounding": grounding,
        "deliverable": deliverable,
        "spec": spec.replace("{pin}", REPOS[repo_key]["pin"]).replace("{deliverable}", deliverable),
        "acceptance": {
            "runner": ("python3" if REPOS[repo_key]["kind"] == "python" else "node"),
            "run_dir": run_dir,
            "file_name": f"accept-{task_id.lower()}" + (".py" if REPOS[repo_key]["kind"] == "python" else ".test.mjs"),
            "file_content": checker,
            "checker_input": checker_input if isinstance(checker_input, list) else [checker_input],
        },
        "participant_validation": pv_cmd,
        "new_files": [deliverable],
        "new_symbols": [],
    }


def build_tasks() -> list[dict]:
    tasks = []

    tasks.append(_task(
        "PY-01", "dspx",
        "Drift triage over execution records (metrics+clustering parity)",
        "moderate",
        "Requires reading metrics.py (semantic distance normalizer, drift thresholds and labels) "
        "AND clustering.py (unit-normalized centroid convention) to produce matching distances/classes.",
        [f"{COORD}/metrics.py", f"{COORD}/clustering.py"],
        f"{COORD}/g3p_drift_triage.py",
        PY1_SPEC, PY1_CHECKER,
        [json.dumps(PY1_INPUT)], ".",
        ["python3", "-m", "py_compile", f"{COORD}/g3p_drift_triage.py"]))

    tasks.append(_task(
        "PY-02", "dspx",
        "Stability/convergence/variance summary (attractors+territory parity)",
        "moderate-hard",
        "Requires reading attractors.py (stability scorer with text-variance penalties and sentinel "
        "values; convergence rate) AND territory.py (internal variance) plus their shared "
        "centroid/distance conventions in clustering.py/metrics.py.",
        [f"{COORD}/attractors.py", f"{COORD}/territory.py", f"{COORD}/metrics.py", f"{COORD}/clustering.py"],
        f"{COORD}/g3p_stability_summary.py",
        PY2_SPEC, PY2_CHECKER,
        [json.dumps(PY2_INPUT)], ".",
        ["python3", "-m", "py_compile", f"{COORD}/g3p_stability_summary.py"]))

    tasks.append(_task(
        "PY-03", "dspx",
        "Deterministic k-means partition reproduction",
        "hard",
        "Requires line-by-line reproduction of simple_kmeans in clustering.py (seeded RNG call "
        "sequence, k-means++ init, tie-breaking, centroid re-normalization, empty-cluster "
        "reinit, final sort) plus the metrics.py distance/normalizer conventions.",
        [f"{COORD}/clustering.py", f"{COORD}/metrics.py"],
        f"{COORD}/g3p_kmeans_partition.py",
        PY3_SPEC, PY3_CHECKER,
        [json.dumps(PY3_INPUT), "3"], ".",
        ["python3", "-m", "py_compile", f"{COORD}/g3p_kmeans_partition.py"]))

    tasks.append(_task(
        "PY-04", "dspx",
        "Region classification with danger zones (territory parity)",
        "moderate-hard",
        "Requires reading territory.py (classify_region branch order, confidence formulas, danger "
        "rule) plus compute_internal_variance's centroid convention (clustering.py) and the "
        "distance normalizer (metrics.py).",
        [f"{COORD}/territory.py", f"{COORD}/clustering.py", f"{COORD}/metrics.py"],
        f"{COORD}/g3p_classify_groups.py",
        PY4_SPEC, PY4_CHECKER,
        [json.dumps(PY4_INPUT)], ".",
        ["python3", "-m", "py_compile", f"{COORD}/g3p_classify_groups.py"]))

    tasks.append(_task(
        "PY-05", "dspx",
        "Attractor landscape + health report (full pipeline parity)",
        "hard",
        "Composes deterministic kmeans (clustering.py) + stability/basin rules and health verdicts "
        "(attractors.py) + distance conventions (metrics.py); the flagship multi-file integration task.",
        [f"{COORD}/attractors.py", f"{COORD}/clustering.py", f"{COORD}/metrics.py"],
        f"{COORD}/g3p_attractor_landscape.py",
        PY5_SPEC, PY5_CHECKER,
        [json.dumps(PY5_INPUT), "3"], ".",
        ["python3", "-m", "py_compile", f"{COORD}/g3p_attractor_landscape.py"]))

    tasks.append(_task(
        "TS-01", "piext",
        "Context seed audit (plan kind normalization + intake safety parity)",
        "moderate",
        "Requires reading context-plan.js (seed-kind normalization and fallbacks) AND "
        "context-intake-safety.js (path/symbol safety rules, control-character definition, exact "
        "issue strings) across two files.",
        [f"{CPACK}/context-plan.js", f"{CPACK}/context-intake-safety.js"],
        "packages/pi-context-packer/g3p-seed-audit.mjs",
        TS1_SPEC, TS1_CHECKER,
        [json.dumps(TS1_INPUT)], "packages/pi-context-packer",
        ["node", "--check", "packages/pi-context-packer/g3p-seed-audit.mjs"]))

    tasks.append(_task(
        "TS-02", "piext",
        "Path-seed budget-risk scan with intake safety (disk fixtures)",
        "moderate-hard",
        "Requires reading file-budget.js (classification rules, exclusion lists, line counting "
        "final-newline rule, budgets, containment, dedup) AND context-intake-safety.js (path "
        "safety issue strings); verifies against real files on disk.",
        [f"{CPACK}/file-budget.js", f"{CPACK}/context-intake-safety.js"],
        "packages/pi-context-packer/g3p-budget-risks.mjs",
        TS2_SPEC, TS2_CHECKER,
        [json.dumps(TS2_INPUT)], "packages/pi-context-packer",
        ["node", "--check", "packages/pi-context-packer/g3p-budget-risks.mjs"]))

    tasks.append(_task(
        "TS-03", "piext",
        "Provider capability matrix (provider-capabilities + session-context parity)",
        "moderate",
        "Requires reading provider-capabilities.js (capability table, SCI gate, session gate) AND "
        "session-context.js (usage field precedence and high-pressure thresholds).",
        [f"{CPACK}/provider-capabilities.js", f"{CPACK}/session-context.js"],
        "packages/pi-context-packer/g3p-provider-matrix.mjs",
        TS3_SPEC, TS3_CHECKER,
        [json.dumps(TS3_INPUT)], "packages/pi-context-packer",
        ["node", "--check", "packages/pi-context-packer/g3p-provider-matrix.mjs"]))

    tasks.append(_task(
        "TS-04", "piext",
        "Byte-identical context packet rendering",
        "hard",
        "Requires reading context-pack-result.js (full render template), "
        "context-intake-safety.js (inline label + fence rules) and context-plan.js (failure "
        "fallback) to reproduce the exact output string, byte for byte.",
        [f"{CPACK}/context-pack-result.js", f"{CPACK}/context-intake-safety.js",
         f"{CPACK}/context-plan.js", f"{CPACK}/dogfood-followup-classes.js"],
        "packages/pi-context-packer/g3p-render-packet.mjs",
        TS4_SPEC, TS4_CHECKER,
        [json.dumps([TS4_INPUT_OK, TS4_INPUT_FAIL, TS4_INPUT_MIN])], "packages/pi-context-packer",
        ["node", "--check", "packages/pi-context-packer/g3p-render-packet.mjs"]))

    tasks.append(_task(
        "TS-05", "piext",
        "Source-selection ranking arm selection (experiment suite parity)",
        "moderate-hard",
        "Requires reading the 3-file source-selection-experiment suite: ranking.js (rows, arm "
        "cascades), structural.js (EVIDENCE_KIND_ORDER), utils.js (compareUtf8).",
        [f"{SSE}-ranking.js", f"{SSE}-structural.js", f"{SSE}-utils.js"],
        "packages/pi-context-packer/g3p-rank-select.mjs",
        TS5_SPEC, TS5_CHECKER,
        [json.dumps(TS5_INPUT)], "packages/pi-context-packer",
        ["node", "--check", "packages/pi-context-packer/g3p-rank-select.mjs"]))

    return tasks


def build_corpus() -> dict:
    tasks = build_tasks()
    pairs = []
    for task in tasks:
        for family, model in FAMILIES.items():
            pairs.append({
                "pair_id": f"PL-{task['task_id']}-{family}",
                "task_id": task["task_id"],
                "family": family,
                "model_identity": model,
                "repo_key": task["repo_key"],
                "repo_identity": REPOS[task["repo_key"]]["repo_identity"],
                "repo_pin": REPOS[task["repo_key"]]["pin"],
                "arm_order": ["static", "evidence"] if (hash_fn(task["task_id"] + family) % 2 == 0) else ["evidence", "static"],
                "task": task,
            })
    order = [p["pair_id"] for p in pairs]
    return {"schema": SCHEMA, "pilot_seed": PILOT_SEED, "pairs": pairs, "execution_order": order}


def hash_fn(text: str) -> int:
    return int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)


def digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


if __name__ == "__main__":
    corpus = build_corpus()
    seen = {}
    for p in corpus["pairs"]:
        seen[p["task"]["task_id"]] = p["task"]
    print(json.dumps({
        "schema": corpus["schema"],
        "n_pairs": len(corpus["pairs"]),
        "corpus_digest": digest(corpus),
        "tasks": [f"{t['task_id']}:{t['difficulty']}" for t in sorted(seen.values(), key=lambda t: t["task_id"])],
    }, indent=1))

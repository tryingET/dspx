# summary: "Builds and protects a session-shared immutable candidate-state graph with private mutable test overrides."
# read_when:
#   - "Testing candidate-state consumers, shared production fixtures, or GEPA artifact isolation."

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


GraphBuilder = Callable[[Path], tuple[Path, Path, dict[str, Path]]]


@dataclass(frozen=True, slots=True)
class CandidateStateGraph:
    """Immutable production-built graph shared by candidate-state consumers."""

    source_root: Path
    candidate_root: Path
    paths: dict[str, Path]

    def private_paths(self) -> dict[str, Path]:
        return dict(self.paths)


@dataclass(frozen=True, slots=True)
class _TemplateReceipt:
    source_root: str
    candidate_root: str
    paths: dict[str, str]
    file_hashes: dict[str, str]

    @classmethod
    def load(cls, path: Path) -> _TemplateReceipt:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            source_root=str(payload["source_root"]),
            candidate_root=str(payload["candidate_root"]),
            paths={str(key): str(value) for key, value in payload["paths"].items()},
            file_hashes={
                str(key): str(value) for key, value in payload["file_hashes"].items()
            },
        )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": "dspx-test-candidate-state-template-v1",
            "source_root": self.source_root,
            "candidate_root": self.candidate_root,
            "paths": self.paths,
            "file_hashes": self.file_hashes,
        }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _shared_template_root(tmp_path: Path) -> Path:
    if os.environ.get("PYTEST_XDIST_WORKER"):
        session_root = tmp_path.parents[1]
    else:
        session_root = tmp_path.parent
    return session_root / "candidate-state-production-template"


def _relative_path(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))


def _template_file_hashes(graph_root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(graph_root)): _sha256(path)
        for path in sorted(graph_root.rglob("*"))
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix not in {".pyc", ".pyo"}
    }


def _build_template_receipt(
    graph_root: Path, builder: GraphBuilder
) -> _TemplateReceipt:
    source_root, candidate_root, paths = builder(graph_root)
    # Receipt validation binds generated candidates to their construction cache.
    # Keep that cache inside the immutable template so runtime seams can replay the
    # original receipt without widening to a worker-local cache root.
    return _TemplateReceipt(
        source_root=_relative_path(source_root, graph_root),
        candidate_root=_relative_path(candidate_root, graph_root),
        paths={
            name: _relative_path(path, graph_root)
            for name, path in sorted(paths.items())
        },
        file_hashes=_template_file_hashes(graph_root),
    )


def shared_candidate_state_graph(
    tmp_path: Path,
    *,
    builder: GraphBuilder,
) -> CandidateStateGraph:
    """Build one real graph per pytest session and return immutable references.

    xdist workers coordinate through the pytest session temp root. The graph keeps
    its original absolute paths, so no path or hash rebasing is required.
    """

    template_root = _shared_template_root(tmp_path)
    graph_root = template_root / "graph"
    receipt_path = template_root / "receipt.json"
    template_root.mkdir(parents=True, exist_ok=True)

    with (template_root / "build.lock").open("a+b") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        if not receipt_path.exists():
            shutil.rmtree(graph_root, ignore_errors=True)
            graph_root.mkdir(parents=True)
            try:
                receipt = _build_template_receipt(graph_root, builder)
            except Exception:
                shutil.rmtree(graph_root, ignore_errors=True)
                raise
            pending = receipt_path.with_suffix(".json.pending")
            pending.write_text(
                json.dumps(receipt.payload(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.replace(pending, receipt_path)
        receipt = _TemplateReceipt.load(receipt_path)

    assert_candidate_state_template_unchanged(tmp_path)
    return CandidateStateGraph(
        source_root=graph_root / receipt.source_root,
        candidate_root=graph_root / receipt.candidate_root,
        paths={name: graph_root / path for name, path in receipt.paths.items()},
    )


def assert_candidate_state_template_unchanged(tmp_path: Path) -> None:
    """Fail if a consumer mutated the canonical production-built template."""

    template_root = _shared_template_root(tmp_path)
    receipt_path = template_root / "receipt.json"
    if not receipt_path.exists():
        return
    receipt = _TemplateReceipt.load(receipt_path)
    graph_root = template_root / "graph"
    actual = _template_file_hashes(graph_root)
    assert actual == receipt.file_hashes, "candidate-state shared template was mutated"


def private_mutable_artifact(
    tmp_path: Path,
    paths: dict[str, Path],
    name: str,
) -> Path:
    """Copy one mutable leaf and update this test's private path mapping."""

    source = paths[name]
    destination = tmp_path / "candidate-state-overrides" / name / source.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    paths[name] = destination
    return destination


def private_gepa_optimizer_bundle(
    tmp_path: Path,
    paths: dict[str, Path],
) -> tuple[dict[str, Any], Path]:
    """Clone the mutable GEPA result and optimizer tree without hardlinks."""

    source_result = paths["gepa_refinement"]
    payload = json.loads(source_result.read_text(encoding="utf-8"))
    source_manifest = Path(payload["gepa_output"]["manifest_path"])
    source_root = source_manifest.parent
    destination_root = tmp_path / "candidate-state-overrides" / "gepa_optimizer_output"
    shutil.copytree(source_root, destination_root)
    destination_manifest = destination_root / source_manifest.name
    payload["gepa_output"]["root_path"] = str(destination_root)
    payload["gepa_output"]["manifest_path"] = str(destination_manifest)
    return payload, destination_manifest

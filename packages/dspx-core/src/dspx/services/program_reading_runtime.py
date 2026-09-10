"""Additive synthetic-only two-stage producer, using the real generated DSPy path.

No Oracle invocation/index/semantic/publication. The native local oracle_evidence
readability sidecar remains untouched. No fallback, custody, activation or live
provider is admitted. Transport callables are trusted synthetic test code, not a
sandboxed plugin API. Only StubProvider._render (normal request/response seam) is
instrumented, in a fresh spawned process; invoke/attempt bookkeeping is native.

AK5457 must retain receipt hashes independently, preserve intent generations,
provide a trusted current-intent callback, and acquire real owner publication
locks. Neither this callback nor these local receipts establishes OS authority,
authenticated provider output, quality acceptance or review eligibility.
"""

from __future__ import annotations

import multiprocessing
import os
import sys
import importlib.abc
import importlib.util
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Mapping

from dspx.services.program_reading_contracts import (
    FAMILIES,
    PROPOSAL_INPUTS,
    READING_INPUTS,
    ExpectedReading,
    canonical_bytes,
    native_input_bytes,
    raw_hash,
    require,
    strict_json,
    validate_inputs,
)
from dspx.services.program_reading_receipts import (
    CurrentIntent,
    capture,
    check_current,
    directory_fd,
    exclusive_write,
    write_reading_receipt,
)

SyntheticTransport = Callable[[Any], str]


def exclusive_directory(path: Path) -> None:
    directory = directory_fd(path.parent)
    try:
        os.mkdir(path.name, mode=0o700, dir_fd=directory)
    finally:
        os.close(directory)


class _CapturedLoader(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Exact three-module source loader; never reads executable disk/cache bytes."""

    def __init__(self, sources, root):
        self.root, self.resolved_root = root.absolute(), root.resolve()
        self.code = {
            name: compile(source, str(root / (name + ".py")), "exec")
            for name, source in sources.items()
        }

    def _candidate_path(self, entry):
        path = Path(entry or os.curdir)
        return path.absolute().is_relative_to(
            self.root
        ) or path.resolve().is_relative_to(self.resolved_root)

    def find_spec(self, fullname, path=None, target=None):
        # Native import adds this root. Remove it and aliases/descendants BEFORE
        # fallback; inspecting a fullname at the root misses nested package paths.
        sys.path[:] = [entry for entry in sys.path if not self._candidate_path(entry)]
        if fullname in self.code:
            return importlib.util.spec_from_loader(fullname, self)
        if path is not None and any(self._candidate_path(entry) for entry in path):
            raise ImportError("candidate package search path is forbidden")
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        module.__file__ = str(self.root / (module.__name__ + ".py"))
        exec(self.code[module.__name__], module.__dict__)


@contextmanager
def _captured_sources(captured, root):
    from dspx.services.program_runtime_episode import (
        _generated_surface_static_violations,
        _GENERATED_SURFACE_TOP_LEVEL_NODES,
    )

    sources = {
        name: captured[name + ".py"].decode("utf-8")
        for name in ("program", "module", "signature")
    }
    # Apply the native GENERIC runtime policy to the bytes we will execute.
    # The separate Soomfon protected/auth policy does not admit these surfaces.
    for name, source in sources.items():
        filename = name + ".py"
        require(
            not _generated_surface_static_violations(
                source,
                filename=filename,
                allowed_top_level_nodes=_GENERATED_SURFACE_TOP_LEVEL_NODES[filename],
            ),
            "captured source violates native generated-surface policy",
        )
    finder = _CapturedLoader(sources, root)
    sys.meta_path.insert(0, finder)
    try:
        yield
    finally:
        sys.meta_path.remove(finder)


def stub_only_environment(env: Mapping[str, str] | None = None) -> None:
    """Before generation/provider construction; never switches environment.

    A dedicated worker inherits this explicit posture. This is not an OS sandbox
    and does not grant authority to an untrusted transport callable.
    """
    env = os.environ if env is None else env
    required = {
        "DSPX_PROVIDER": "stub",
        "MLFLOW_ENABLE": "0",
        "DSPX_POLICY_ALLOW_NETWORK_MUTATE": "0",
        "DSPX_POLICY_DISALLOWED_CAPS": "network.read,network.mutate",
    }
    require(
        all(env.get(k) == v for k, v in required.items()),
        "explicit stub-only/no-network/no-MLflow environment required",
    )
    allowed = set(required) | {"DSPX_CACHE_DIR", "DSPX_POLICY_ALLOWED_PROVIDERS"}
    require(
        env.get("DSPX_POLICY_ALLOWED_PROVIDERS", "stub") == "stub",
        "nonstub provider policy",
    )
    require(
        not any(
            (k.startswith("DSPX_") or k.startswith("MLFLOW_")) and k not in allowed
            for k in env
        ),
        "ambient provider/config/custody/fallback/activation rejected",
    )


def capture_candidate(manifest_path: Path) -> dict[str, bytes]:
    """Bounded declared source capture, not a historical whole-graph verifier."""
    root = manifest_path.parent
    manifest_raw = capture(root, manifest_path.name)
    manifest = strict_json(manifest_raw)
    declarations = manifest.get("candidate_assembly", {}).get("surfaces")
    require(
        isinstance(declarations, list) and 0 < len(declarations) <= 64,
        "invalid candidate surfaces",
    )
    captured = {
        manifest_path.name: manifest_raw,
        manifest_path.name + ".meta.json": capture(
            root, manifest_path.name + ".meta.json"
        ),
    }
    for row in declarations:
        require(
            isinstance(row, dict) and isinstance(row.get("path"), str),
            "invalid candidate reference",
        )
        name = row["path"]
        if name == manifest_path.name:
            continue
        raw = capture(root, name)
        require(
            raw_hash(raw).removeprefix("sha256:") == row.get("content_hash"),
            "candidate surface hash mismatch",
        )
        if name.endswith(".json"):
            strict_json(raw)
        captured[name] = raw
    strict_json(captured[manifest_path.name + ".meta.json"])
    require(
        sum(map(len, captured.values())) <= 20_000_000,
        "candidate capture exceeds bound",
    )
    return captured


def _validate_candidate_intent(payload: dict, stage: str) -> None:
    """Admit only inert template generation; no examples/datasets/tools/retrieval."""
    fields = READING_INPUTS if stage == "reading" else PROPOSAL_INPUTS
    outputs = FAMILIES if stage == "reading" else ("reading_proposal_json",)
    allowed = set(
        "schema_version name objective input_fields output_fields options".split()
    )
    require(
        set(payload) == allowed and payload["schema_version"] == "program-intent-v2",
        "candidate intent contains unadmitted generation surfaces",
    )
    require(
        payload["options"]
        == {"focused_json_bundle_runtime": False, "module_inference": False},
        "only non-focused inert template generation allowed",
    )
    for key, names in (("input_fields", fields), ("output_fields", outputs)):
        rows = payload[key]
        require(
            isinstance(rows, list) and [r.get("name") for r in rows] == list(names),
            "candidate fields mismatch",
        )
        require(
            all(
                set(r) == {"name", "type", "desc"}
                and r["type"] == "str"
                and isinstance(r["desc"], str)
                and bool(r["desc"].strip())
                for r in rows
            ),
            "rich string field descriptors required",
        )


def _worker(
    connection: Any,
    operation: str,
    arguments: dict,
    transport: SyntheticTransport | None,
) -> None:
    """Dedicated process; never mutates os.environ or generic source files."""
    try:
        stub_only_environment()
        if operation == "generate":
            from dspx.services.program_service import run_generate_from_intent_path

            artifact = run_generate_from_intent_path(
                arguments["intent_path"], outdir=arguments["candidate_root"]
            )
            connection.send(
                {
                    "ok": True,
                    "manifest_path": str(Path(artifact.root_path) / "manifest.json"),
                }
            )
            return
        from dataclasses import asdict
        import dspy
        from dspx.stub_provider import StubProvider
        from dspx.services.program_runtime_episode import run_program_runtime_episode

        calls: list[dict] = []

        def render(request: Any) -> str:
            # A malformed adapter response must not result in another dispatch.
            if calls:
                exclusive_write(
                    arguments["root"] / "synthetic_retry_rejected.json",
                    canonical_bytes(asdict(request)),
                )
                raise ValueError("synthetic transport retry forbidden")
            calls.append(asdict(request))
            exclusive_write(
                arguments["root"] / "synthetic_requests.json",
                canonical_bytes(calls) + b"\n",
            )
            if transport is None:
                raise ValueError("synthetic transport required")
            response = transport(request)
            require(isinstance(response, str), "synthetic response must be text")
            # Let the real adapter reject malformed fields after StubProvider
            # records its normal attempt; do not manufacture fallback content.
            exclusive_write(
                arguments["root"] / "synthetic_response.json", response.encode("utf-8")
            )
            return response

        setattr(StubProvider, "_render", staticmethod(render))
        dspy.configure(adapter=dspy.JSONAdapter())
        with _captured_sources(
            arguments["captured"], arguments["manifest_path"].parent
        ):
            result = run_program_runtime_episode(
                manifest_path=arguments["manifest_path"],
                inputs_path=arguments["inputs_path"],
                outdir=arguments["root"],
                contract_mode="none",
                skip_oracle_index=True,
                capture_replay_fixture=False,
                run_oracle_semantic=False,
                soomfon_custody=None,
                publication_preflight_out=None,
            )
        exclusive_write(
            arguments["root"] / "synthetic_workflow.json",
            canonical_bytes(result) + b"\n",
        )
        require(
            len(calls) == 1 and result.get("status") == "ok",
            "native synthetic execution failed; evidence retained, no retry",
        )
        connection.send({"ok": True, "native_episode_id": result["runtime_episode_id"]})
    except Exception as exc:
        # Failure is terminal; avoid leaking callback/private diagnostic text.
        connection.send({"ok": False, "error_type": type(exc).__name__})
    finally:
        connection.close()


def _spawn(
    operation: str,
    arguments: dict,
    transport: SyntheticTransport | None,
    timeout: float,
) -> dict:
    stub_only_environment()
    require(0 < timeout <= 180, "bounded worker timeout required")
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(
        target=_worker, args=(child, operation, arguments, transport)
    )
    process.start()
    child.close()
    try:
        if not parent.poll(timeout):
            process.terminate()
            process.join(5)
            raise RuntimeError(
                "synthetic worker outcome unknown; evidence retained, no retry"
            )
        try:
            result = parent.recv()
        except EOFError as exc:
            raise RuntimeError("synthetic worker outcome unknown; no retry") from exc
        process.join(5)
        require(
            result.get("ok") is True and process.exitcode == 0,
            "synthetic worker failed; evidence retained, no retry",
        )
        return result
    finally:
        parent.close()
        if process.is_alive():
            process.terminate()
            process.join(5)


def materialize_reading_candidate(
    *, intent_path: Path, candidate_root: Path, stage: str, timeout: float = 120
) -> dict:
    """Generate actual signature/module; caller independently reviews/holds hash.

    New fixtures use JSON syntax (valid YAML) to permit strict bounded parsing.
    Candidate intent is captured to an exclusive sibling file before the native
    loader runs, avoiding a validate-then-consume reopen of caller-owned bytes.
    """
    stub_only_environment()  # BEFORE any generation/provider construction.
    require(stage in {"proposal", "reading"}, "invalid stage")
    raw = capture(intent_path.parent, intent_path.name)
    payload = strict_json(raw)
    _validate_candidate_intent(payload, stage)
    fd = directory_fd(candidate_root.parent)
    os.close(fd)
    require(
        not candidate_root.exists() and not candidate_root.is_symlink(),
        "candidate directory already exists",
    )
    frozen = candidate_root.with_name(candidate_root.name + ".intent.json")
    exclusive_write(frozen, raw)
    result = _spawn(
        "generate",
        {"intent_path": frozen, "candidate_root": candidate_root},
        None,
        timeout,
    )
    manifest_path = Path(result["manifest_path"])
    manifest_raw = capture(manifest_path.parent, manifest_path.name)
    return {
        "manifest_path": manifest_path,
        "candidate_manifest_sha256": raw_hash(manifest_raw),
    }


def run_reading_producer(
    *,
    manifest_path: Path,
    requests_root: Path,
    expected: ExpectedReading,
    inputs: dict[str, str],
    synthetic_transport: SyntheticTransport,
    current_intent: CurrentIntent | None,
    timeout: float = 120,
) -> dict:
    """One exclusive request, no overwrite/retry. Defer/source_only make zero calls.

    The request ID is independent of native deterministic episode identity.
    A repeated ID at this owner-controlled request root is rejected forever,
    including after failure or stale completion. New work needs a new ID.
    """
    stub_only_environment()
    # Deep capture owner data; callbacks cannot mutate an in-flight generation.
    expected = ExpectedReading(**strict_json(canonical_bytes(expected.payload())))
    inputs = strict_json(canonical_bytes(inputs))
    intent = validate_inputs(inputs, expected)
    check_current(current_intent, intent)
    if intent is not None and intent["mode"] in {"defer", "source_only"}:
        return {"status": "blocked_mode", "transport_calls": 0}
    require(callable(synthetic_transport), "trusted synthetic transport required")
    manifest_raw = capture(manifest_path.parent, manifest_path.name)
    require(
        raw_hash(manifest_raw) == expected.candidate_manifest_sha256,
        "independent candidate hash mismatch",
    )
    candidate_capture = capture_candidate(manifest_path)
    require(
        candidate_capture[manifest_path.name] == manifest_raw,
        "candidate identity changed before source capture",
    )
    manifest = strict_json(manifest_raw)
    require(
        manifest_path.parent not in (requests_root, *requests_root.parents)
        and requests_root not in manifest_path.parent.parents,
        "request root must be disjoint from candidate",
    )
    expected_inputs = READING_INPUTS if expected.stage == "reading" else PROPOSAL_INPUTS
    expected_outputs = (
        FAMILIES if expected.stage == "reading" else ("reading_proposal_json",)
    )
    candidate_intent = manifest.get("intent", {})
    require(
        candidate_intent.get("inputs") == list(expected_inputs)
        and candidate_intent.get("outputs") == list(expected_outputs)
        and candidate_intent.get("options")
        == {"focused_json_bundle_runtime": False, "module_inference": False}
        and not any(
            candidate_intent.get(k)
            for k in (
                "examples",
                "examples_path",
                "dataset",
                "datasets",
                "capabilities",
                "topology",
            )
        ),
        "candidate is not the declared non-focused reading surface",
    )
    key = raw_hash(expected.request_id.encode()).removeprefix("sha256:")
    request_root = requests_root / key
    exclusive_directory(request_root)
    exclusive_write(
        request_root / "admission.json", canonical_bytes(expected.payload()) + b"\n"
    )
    exclusive_write(request_root / "inputs.json", native_input_bytes(inputs))
    if intent is not None:
        exclusive_write(
            request_root / "working_reading_intent.json",
            canonical_bytes(intent) + b"\n",
        )
    runtime_root = request_root / "runtime"
    exclusive_directory(runtime_root)
    result = _spawn(
        "run",
        {
            "manifest_path": manifest_path,
            "inputs_path": request_root / "inputs.json",
            "root": runtime_root,
            "stage": expected.stage,
            "captured": candidate_capture,
        },
        synthetic_transport,
        timeout,
    )
    check_current(
        current_intent, intent
    )  # stale completion stays historical, never rebound.
    require(
        capture_candidate(manifest_path) == candidate_capture,
        "candidate changed during execution",
    )
    receipt_hash = write_reading_receipt(
        root=runtime_root,
        manifest_path=manifest_path,
        expected=expected,
        inputs=inputs,
        native_episode_id=result["native_episode_id"],
        current_intent=current_intent,
    )
    return {
        "status": "local_synthetic_execution_only",
        "root": runtime_root,
        "native_episode_id": result["native_episode_id"],
        "native_index": 0,
        "receipt_sha256": receipt_hash,
    }

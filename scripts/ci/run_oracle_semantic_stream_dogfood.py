#!/usr/bin/env python3
# summary: "Dogfoods typed Codex semantic JSON with one bounded corrective retry."

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import inspect
import json
import os
import pwd
import stat
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from dspx.dspy_lm_auth_lm import DspyLMAuthLM
from dspx.services.program_oracle_semantic_backend import (
    LiveLMOracleSemanticBackend,
    resolve_program_oracle_semantic_backend,
)
from dspx.services.program_oracle_semantic_contract import OracleSemanticRequest
from dspx.services.program_oracle_semantic_scoring import score_analysis

TASK_ID = 4546
SCHEMA = "dspx-oracle-semantic-stream-dogfood-v1"
RESULT_NAME = "semantic-stream-dogfood.json"
CONTRACT_PATH = Path("benchmarks/semantic/oracle-semantic-analysis-evaluation-v1.json")
DEPENDENCY_COMMIT = "e3e6eb258e9714fab5070b82bddc4a9699ea8755"
DEPENDENCY_ORIGIN = "https://github.com/MaximeRivest/dspy-lm-auth"
DEPENDENCY_REVIEWED_REF = "myfork/fix/dspy-3-dict-usage-normalization"
SCRIPT_REPO_ROOT = Path(__file__).resolve().parents[2]
DEPENDENCY_HASHES = {
    "src/dspy_lm_auth/__init__.py": "6ca0881c8a3301b017975aa1507d4b561abd54a6a4d727d6d008cba843fb52f4",
    "src/dspy_lm_auth/lm.py": "10c930b2b00af8acdf8984bfa74281510cec975561e5ed2b4caefa768d14e3a8",
    "src/dspy_lm_auth/codex_stream.py": "b1d2a7baf97ceb21f7b0a5c0ec57f7603cba4c1db523e7507a309aad34980e77",
}


class DogfoodTransportError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


_STREAM_ERROR_CODES = (
    ("location was ambiguous", "stream_location_ambiguous"),
    ("item was absent", "stream_item_absent"),
    ("item was not a message", "stream_item_not_message"),
    ("identity drifted", "stream_item_identity_drift"),
    ("content was absent", "stream_content_absent"),
    ("content was not output text", "stream_content_not_output_text"),
    ("target was not empty", "stream_target_not_empty"),
    ("content was not detached", "stream_content_not_detached"),
    ("without a completed response", "completed_response_missing"),
    ("could not be normalized", "completed_response_normalization_failed"),
    ("completed response returned an error", "completed_response_error"),
    ("completed response returned a refusal", "completed_response_refusal"),
    ("completed response status=", "completed_response_status_invalid"),
    ("response stream ended with error", "response_stream_error"),
    ("response stream returned a refusal", "response_stream_refusal"),
)


def _stream_error_code(error: str) -> str:
    lowered = error.lower()
    for marker, code in _STREAM_ERROR_CODES:
        if marker in lowered:
            return code
    return "stream_adapter_unclassified"


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_private_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = -1
            stream.write(_canonical(dict(payload)) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        _fsync_directory(path.parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _replace_private(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    _write_private_exclusive(temporary, payload)
    try:
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], text=True, stderr=subprocess.STDOUT
    ).strip()


def _tracked_clean(repo: Path) -> None:
    if _git(repo, "status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError(f"tracked source is dirty: {repo}")


def _unexpected_untracked(repo: Path, *, allow_runtime_ontology: bool) -> list[str]:
    raw = subprocess.check_output(
        ["git", "-C", str(repo), "ls-files", "--others", "--exclude-standard", "-z"]
    )
    paths = [item.decode("utf-8") for item in raw.split(b"\0") if item]
    return [
        path
        for path in paths
        if not (allow_runtime_ontology and path.startswith(".ontology/"))
    ]


def _clean_commit(repo: Path, *, allow_runtime_ontology: bool = False) -> str:
    _tracked_clean(repo)
    unexpected = _unexpected_untracked(
        repo, allow_runtime_ontology=allow_runtime_ontology
    )
    if unexpected:
        raise RuntimeError(f"untracked source is present: {unexpected[0]}")
    return _git(repo, "rev-parse", "HEAD")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _executing_source_identity(repo_root: Path) -> dict[str, Any]:
    if repo_root != SCRIPT_REPO_ROOT:
        raise RuntimeError("live dogfood repo root must own the executing script")
    source_objects = {
        "scripts/ci/run_oracle_semantic_stream_dogfood.py": main,
        "packages/dspx-core/src/dspx/dspy_lm_auth_lm.py": DspyLMAuthLM,
        "packages/dspx-core/src/dspx/services/program_oracle_semantic_backend.py": LiveLMOracleSemanticBackend,
    }
    hashes: dict[str, str] = {}
    for expected_path, source_object in source_objects.items():
        observed = Path(inspect.getsourcefile(source_object) or "").resolve()
        expected = (repo_root / expected_path).resolve()
        if observed != expected:
            raise RuntimeError(
                f"executing source does not match repo path: {expected_path}"
            )
        hashes[expected_path] = _sha256(expected)
    return {
        "git_commit": _clean_commit(repo_root, allow_runtime_ontology=True),
        "path_sha256": hashes,
    }


def _dependency_identity() -> dict[str, Any]:
    import dspy_lm_auth

    module_path = Path(dspy_lm_auth.__file__).resolve()
    repo = next(
        (parent for parent in module_path.parents if (parent / ".git").exists()), None
    )
    if repo is None:
        raise RuntimeError("dogfood requires dspy-lm-auth from a clean Git checkout")
    commit = _clean_commit(repo)
    configured_origin_url = _git(repo, "remote", "get-url", "origin")
    try:
        subprocess.check_call(
            [
                "git",
                "-C",
                str(repo),
                "merge-base",
                "--is-ancestor",
                commit,
                DEPENDENCY_REVIEWED_REF,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            "reviewed dependency ref does not contain the commit"
        ) from exc
    if commit != DEPENDENCY_COMMIT or configured_origin_url != DEPENDENCY_ORIGIN:
        raise RuntimeError(
            "dogfood dependency identity does not match the reviewed commit"
        )
    observed_hashes = {path: _sha256(repo / path) for path in DEPENDENCY_HASHES}
    if observed_hashes != DEPENDENCY_HASHES:
        raise RuntimeError("dogfood dependency behavior hash drift")
    return {
        "package": "dspy-lm-auth",
        "candidate_only_not_released": True,
        "version": importlib.metadata.version("dspy-lm-auth"),
        "configured_origin_url": configured_origin_url,
        "reviewed_ref": DEPENDENCY_REVIEWED_REF,
        "git_commit": commit,
        "path_sha256": observed_hashes,
    }


def _load_case(repo_root: Path) -> tuple[dict[str, Any], OracleSemanticRequest]:
    payload = json.loads((repo_root / CONTRACT_PATH).read_text(encoding="utf-8"))
    case = payload["cases"][0]
    request = case["provider_request"]
    return case, OracleSemanticRequest(
        objective=request["objective"],
        evidence=request["evidence"],
        quality_contract=request["quality_contract"],
    )


def _validate_live_backend(backend: Any, *, test_mode: bool) -> DspyLMAuthLM:
    if type(backend) is not LiveLMOracleSemanticBackend:
        raise RuntimeError("dogfood requires the exact live semantic backend")
    lm = backend.lm
    if type(lm) is not DspyLMAuthLM:
        raise RuntimeError("dogfood requires the exact production DspyLMAuthLM adapter")
    if not test_mode:
        if (
            "analyze" in backend.__dict__
            or inspect.getattr_static(type(backend), "analyze")
            is not LiveLMOracleSemanticBackend.analyze
        ):
            raise RuntimeError("semantic backend analyze method is rebound")
        for name in ("_build_inner", "forward", "generate"):
            if name in lm.__dict__ or inspect.getattr_static(
                type(lm), name
            ) is not getattr(DspyLMAuthLM, name):
                raise RuntimeError(f"production adapter method is rebound: {name}")
    if (
        lm.requested_model != "codex/gpt-5.6-sol"
        or lm.auth_provider != "codex"
        or lm.strict is not True
        or lm.kwargs != {"reasoning_effort": "max"}
        or lm.history
    ):
        raise RuntimeError("production adapter route preflight drift")
    return lm


def _transport_after_call(lm: DspyLMAuthLM, before: int) -> dict[str, Any]:
    calls = lm.history[before:]
    try:
        if len(calls) != 1:
            raise DogfoodTransportError("history_cardinality_drift")
        call = calls[0]
        transport = call.transport
        if call.error is not None:
            raise DogfoodTransportError(_stream_error_code(call.error))
        if not isinstance(transport, Mapping):
            raise DogfoodTransportError("transport_metadata_missing")
        counts = transport.get("event_counts")
        chars = transport.get("output_text_chars")
        completed_output_text = transport.get("completed_output_text")
        output_text_source = transport.get("output_text_source")
        stream_output_text_chars = transport.get("stream_output_text_chars")
        stream_completed_match = transport.get("stream_completed_match")
        if (
            not isinstance(counts, Mapping)
            or not isinstance(completed_output_text, bool)
            or output_text_source not in {"completed_response", "typed_stream", "none"}
            or not isinstance(chars, int)
            or isinstance(chars, bool)
            or chars != len(call.text)
            or not isinstance(stream_output_text_chars, int)
            or isinstance(stream_output_text_chars, bool)
            or stream_output_text_chars < 0
            or not isinstance(stream_completed_match, bool)
        ):
            raise DogfoodTransportError("transport_metadata_invalid")
        source_is_bound = (
            (
                output_text_source == "completed_response"
                and completed_output_text
                and chars > 0
            )
            or (
                output_text_source == "typed_stream"
                and not completed_output_text
                and chars > 0
                and stream_output_text_chars == chars
            )
            or (
                output_text_source == "none"
                and not completed_output_text
                and chars == 0
                and stream_output_text_chars == 0
            )
        )
        if not source_is_bound:
            raise DogfoodTransportError("transport_source_unbound")
        return {
            "event_counts": {str(key): counts[key] for key in sorted(counts)},
            "completed_output_text": completed_output_text,
            "output_text_chars": chars,
            "output_text_source": output_text_source,
            "stream_output_text_chars": stream_output_text_chars,
            "stream_completed_match": stream_completed_match,
        }
    finally:
        for call in calls:
            call.text = ""


def _validate_paths(artifact_root: Path, ledger_path: Path) -> None:
    if not artifact_root.is_absolute() or not ledger_path.is_absolute():
        raise RuntimeError("artifact and ledger paths must be absolute")
    if artifact_root.is_symlink() or ledger_path.is_symlink():
        raise RuntimeError("artifact and ledger paths must not be symlinks")
    if artifact_root.exists() or not artifact_root.parent.is_dir():
        raise RuntimeError("artifact root must be new under an existing directory")
    if ledger_path == artifact_root / RESULT_NAME or ledger_path.is_relative_to(
        artifact_root
    ):
        raise RuntimeError("ledger must be outside the artifact root")
    for parent in (artifact_root.parent, ledger_path.parent):
        if parent.is_symlink() or parent.absolute() != parent.resolve():
            raise RuntimeError("artifact and ledger parents must not traverse symlinks")
        if not parent.is_dir() or parent.stat().st_uid != os.getuid():
            raise RuntimeError("artifact and ledger parents must be owner directories")
        if stat.S_IMODE(parent.stat().st_mode) & 0o077:
            raise RuntimeError(
                "artifact and ledger parents must not grant group/world access"
            )


def _run_attempts(
    *,
    backend: LiveLMOracleSemanticBackend,
    lm: DspyLMAuthLM,
    request: OracleSemanticRequest,
    case: Mapping[str, Any],
    source_identity: Mapping[str, Any],
    dependency: Mapping[str, Any],
    artifact_root: Path,
    ledger_path: Path,
    marker: Mapping[str, Any],
    test_mode: bool,
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    final = None
    for attempt_number in (1, 2):
        before = len(lm.history)
        result = backend.analyze(request)
        transport = _transport_after_call(lm, before)
        attempts.append(
            {
                "attempt": attempt_number,
                "execution_status": result.execution_status,
                "live_call_succeeded": result.live_call_succeeded,
                "executed_model": result.executed_model,
                "transport": transport,
                "error": result.error,
            }
        )
        final = result
        if result.execution_status == "succeeded" and result.analysis is not None:
            break
        if (
            attempt_number == 1
            and result.execution_status == "failed_after_live_response"
        ):
            continue
        break

    assert final is not None
    analysis = final.analysis.to_dict() if final.analysis else None
    score = score_analysis(case, analysis) if analysis is not None else None
    mechanics_passed = final.execution_status == "succeeded" and analysis is not None
    live_passed = mechanics_passed and not test_mode
    status = (
        "passed"
        if live_passed
        else "wiring_only_passed"
        if mechanics_passed
        else "failed"
    )
    payload = {
        "schema_version": SCHEMA,
        "ak_task_id": TASK_ID,
        "status": status,
        "source_identity": dict(source_identity),
        "dependency": dict(dependency),
        "request_sha256": request.request_sha256,
        "case_id": case["id"],
        "attempts": attempts,
        "first_pass_status": attempts[0]["execution_status"],
        "recovery": "first_pass" if len(attempts) == 1 else "one_corrective_retry",
        "analysis": analysis,
        "semantic_score": score,
        "claims": {
            "typed_output_json_transport_passed": live_passed,
            "semantic_label_gate_passed": bool(
                live_passed and score and score.get("status") == "passed"
            ),
            "ak_4506_case_reexecuted_under_ak_4546": True,
            "ak_4506_ledger_reused": False,
            "production_activation": False,
            "provider_transport_call_count_proven": False,
        },
    }
    result_path = artifact_root / RESULT_NAME
    _write_private_exclusive(result_path, payload)
    _replace_private(
        ledger_path,
        {
            **marker,
            "status": status,
            "result_sha256": _sha256(result_path),
            "attempt_count": len(attempts),
        },
    )
    return payload


def run(
    *,
    repo_root: Path,
    artifact_root: Path,
    ledger_path: Path,
    resolve_backend: Callable[[], Any] | None = None,
    dependency_identity: Callable[[], dict[str, Any]] | None = None,
    test_mode: bool = False,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    _validate_paths(artifact_root, ledger_path)
    if ledger_path.exists():
        raise FileExistsError(f"AK-{TASK_ID} dogfood ledger is already consumed")
    source_identity = _executing_source_identity(repo_root)
    dependency = (dependency_identity or _dependency_identity)()
    case, request = _load_case(repo_root)
    backend = (resolve_backend or resolve_program_oracle_semantic_backend)()
    lm = _validate_live_backend(backend, test_mode=test_mode)

    marker = {
        "schema_version": SCHEMA,
        "ak_task_id": TASK_ID,
        "status": "started",
        "artifact_root": str(artifact_root),
    }
    _write_private_exclusive(ledger_path, marker)

    try:
        artifact_root.mkdir(mode=0o700)
        return _run_attempts(
            backend=backend,
            lm=lm,
            request=request,
            case=case,
            source_identity=source_identity,
            dependency=dependency,
            artifact_root=artifact_root,
            ledger_path=ledger_path,
            marker=marker,
            test_mode=test_mode,
        )
    except Exception as exc:
        for call in lm.history:
            call.text = ""
        failure = {
            **marker,
            "status": "failed",
            "error_type": type(exc).__name__,
            "attempt_count": len(lm.history),
        }
        if isinstance(exc, DogfoodTransportError):
            failure["error_code"] = exc.code
        _replace_private(ledger_path, failure)
        raise


def _ledger_path() -> Path:
    home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    return home / ".local/state/dspx/oracle-semantic-stream-dogfoods/AK-4546.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    ledger = _ledger_path()
    if not ledger.parent.exists():
        ledger.parent.mkdir(mode=0o700)
    elif (
        ledger.parent.is_symlink()
        or stat.S_IMODE(ledger.parent.stat().st_mode) != 0o700
    ):
        raise RuntimeError(
            "canonical ledger directory must be non-symlink owner-only 0700"
        )
    payload = run(
        repo_root=SCRIPT_REPO_ROOT,
        artifact_root=args.root,
        ledger_path=ledger,
    )
    print(_canonical({"status": payload["status"], "artifact_root": str(args.root)}))
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

# summary: "Fresh -I -B subprocess boundary for one task-local foundry comparison jury."
# read_when:
#   - "Changing how task-local jury provider calls are isolated from the CLI parent process."

"""Per-jury fresh subprocess for task-local foundry comparison juries.

The parent (``program_foundry_gepa_comparison_jury``) keeps the foundry lock,
writes the attempt marker, and then runs

``sys.executable -I -B -m dspx.services.program_foundry_gepa_comparison_jury_child``

with a closed request object on stdin. The child acquires its own model-jury
process slot, binds the task-local runtime (owner verification, AK
revalidation, provider journals under ``<experiment_root>/provider-outcomes``)
and runs ``build_comparison_model_jury_result`` exactly as the in-process path
did. It prints one closed JSON envelope on stdout and nothing else; stderr is
discarded by the parent.

Three envelope kinds, each bound to its own exit status:

* ``jury_ok`` (exit 0): the jury built a results object that passes the shared
  model-jury results contract.
* ``jury_failed`` (exit 4): the jury built a results object (juror records,
  aggregate, provider evidence) but the contract rejects it, for example when
  every juror failed and no judged juror remains. The results object travels
  with the bounded error so the parent can retain it as evidence exactly as
  the in-process path did before raising the same error.
* ``jury_error`` (exit 5): the jury raised before a results object existed
  (indeterminate provider outcome, custody or configuration failure). Only the
  bounded error class and message travel; the parent stays indeterminate.

Any other exit status, empty or unparsable stdout, or a shape that does not
match its kind is indeterminate for the parent: the attempt marker stays and
replay is blocked. Request-level refusals before any provider effect (bad
interpreter posture, unreadable request) still exit 1 with no output.

``--self-check`` prints the interpreter posture observed at start-up (isolated
mode, bytecode disabled, no owner modules) without touching any input.
"""

from __future__ import annotations

import sys

_STARTUP_OWNER_MODULES: tuple[str, ...] = tuple(
    sorted(
        name
        for name in sys.modules
        if name == "dspy_lm_auth" or name.startswith("dspy_lm_auth.")
    )
)

import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import signal  # noqa: E402
import subprocess  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any, Mapping, Sequence, cast  # noqa: E402

from dspx.redaction import sanitize_diagnostic_text  # noqa: E402
from dspx.services.program_foundry_gepa_comparison_jury_provider_family import (  # noqa: E402
    FoundryJuryProviderFamily,
)
from dspx.services.program_foundry_gepa_comparison_jury_runtime import (  # noqa: E402
    ProgramFoundryGepaComparisonJuryError,
    make_task_local_runtime_binding,
    revalidate_execution_request,
    task_local_family,
    task_local_process_slot,
)
from dspx.services.program_foundry_gepa_comparison_model_jury import (  # noqa: E402
    build_comparison_model_jury_result,
)
from dspx.services.program_model_jury_provider_runtime import (  # noqa: E402
    _model_jury_process_slot,
)
from dspx.services.program_model_jury_validation import (  # noqa: E402
    validate_program_model_jury_results_contract,
)

CHILD_MODULE = "dspx.services.program_foundry_gepa_comparison_jury_child"
CHILD_REQUEST_SCHEMA = "dspx-foundry-jury-child-request-v1"
CHILD_RESULT_SCHEMA = "dspx-foundry-jury-child-result-v2"
CHILD_MAX_STDOUT_BYTES = 16 * 1024 * 1024
CHILD_MAX_STDIN_BYTES = 1024 * 1024
CHILD_MAX_ERROR_MESSAGE_CHARS = 2000
CHILD_TIMEOUT_MARGIN_SECONDS = 60.0
CHILD_EXIT_JURY_OK = 0
CHILD_EXIT_JURY_FAILED = 4
CHILD_EXIT_JURY_ERROR = 5
# The parent's results-contract label; the child reuses it so a contract
# rejection carries the same message the in-process validation produced.
JURY_RESULTS_LABEL = "foundry GEPA comparison jury results"
_ENVELOPE_KEYS = frozenset({"schema_version", "kind", "results", "error"})
_ENVELOPE_SHAPES: Mapping[str, tuple[int, frozenset[str]]] = {
    "jury_ok": (CHILD_EXIT_JURY_OK, frozenset({"schema_version", "kind", "results"})),
    "jury_failed": (CHILD_EXIT_JURY_FAILED, _ENVELOPE_KEYS),
    "jury_error": (
        CHILD_EXIT_JURY_ERROR,
        frozenset({"schema_version", "kind", "error"}),
    ),
}
_ERROR_TYPE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_PASSTHROUGH_ENV_KEYS = (
    "HOME",
    "PATH",
    "LANG",
    "LC_ALL",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "DSPX_CACHE_DIR",
)
_FIXED_ENV = {
    "DSPX_CACHE_ENABLE": "0",
    "MLFLOW_ENABLE": "0",
    "PYTHONDONTWRITEBYTECODE": "1",
}
_REQUEST_KEYS = frozenset(
    {
        "schema_version",
        "request",
        "experiment_root",
        "attempt_sha256",
        "candidate_manifest_path",
        "comparison_path",
        "expected_input_sha256",
    }
)


class ProgramFoundryGepaComparisonJuryChildError(RuntimeError):
    """The jury child did not complete; provider calls may have occurred."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"comparison jury child {reason}; one or more provider juror calls "
            "may have occurred"
        )
        self.reason = reason


def default_child_argv() -> tuple[str, ...]:
    return (sys.executable, "-I", "-B", "-m", CHILD_MODULE)


def child_environment(family: FoundryJuryProviderFamily | None) -> dict[str, str]:
    """Scrubbed environment: passthrough allowlist, fixed flags, family endpoint."""

    env = {key: os.environ[key] for key in _PASSTHROUGH_ENV_KEYS if key in os.environ}
    if family is not None and family.endpoint_env is not None:
        endpoint = os.environ.get(family.endpoint_env)
        if endpoint is not None:
            env[family.endpoint_env] = endpoint
    env.update(_FIXED_ENV)
    return env


def child_timeout_seconds(
    expected_juror_count: int, family: FoundryJuryProviderFamily
) -> float:
    """One family-timeout per selected juror plus a fixed start-up margin."""

    return max(1, int(expected_juror_count)) * family.default_timeout_seconds + (
        CHILD_TIMEOUT_MARGIN_SECONDS
    )


def child_request_payload(
    *,
    request: Mapping[str, Any],
    validated: Mapping[str, Any],
    experiment_root: Path,
    attempt_sha256: str,
    input_sha256: Mapping[Path, str],
) -> dict[str, Any]:
    return {
        "schema_version": CHILD_REQUEST_SCHEMA,
        "request": dict(request),
        "experiment_root": str(experiment_root),
        "attempt_sha256": attempt_sha256,
        "candidate_manifest_path": str(validated["candidate_manifest_path"]),
        "comparison_path": str(validated["comparison_path"]),
        "expected_input_sha256": {
            str(path): digest for path, digest in input_sha256.items()
        },
    }


def _terminate_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        process.communicate(timeout=5)
    except (subprocess.TimeoutExpired, OSError, ValueError):
        pass


def _valid_error_payload(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    error = cast(dict[str, Any], value)
    error_type = error.get("type")
    message = error.get("message")
    return (
        set(error) == {"type", "message"}
        and isinstance(error_type, str)
        and _ERROR_TYPE_RE.fullmatch(error_type) is not None
        and isinstance(message, str)
        and len(message) <= CHILD_MAX_ERROR_MESSAGE_CHARS
    )


def _validate_envelope(answer: object, *, returncode: int) -> dict[str, Any]:
    """Accept exactly one closed envelope whose kind matches the exit status."""

    if not isinstance(answer, dict):
        raise ProgramFoundryGepaComparisonJuryChildError("output shape drifted")
    envelope = cast(dict[str, Any], answer)
    kind = envelope.get("kind")
    shape = _ENVELOPE_SHAPES.get(kind) if isinstance(kind, str) else None
    if shape is None:
        raise ProgramFoundryGepaComparisonJuryChildError("output kind is unknown")
    exit_code, keys = shape
    if (
        set(envelope) != keys
        or envelope.get("schema_version") != CHILD_RESULT_SCHEMA
        or returncode != exit_code
        or ("results" in keys and not isinstance(envelope.get("results"), dict))
        or ("error" in keys and not _valid_error_payload(envelope.get("error")))
    ):
        raise ProgramFoundryGepaComparisonJuryChildError("output shape drifted")
    return envelope


def run_task_local_jury_child(
    argv: Sequence[str],
    *,
    payload: Mapping[str, Any],
    env: Mapping[str, str],
    timeout: float,
) -> dict[str, Any]:
    """Spawn one jury child; return its closed envelope or fail indeterminate."""

    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    try:
        process = subprocess.Popen(
            list(argv),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=dict(env),
            close_fds=True,
            start_new_session=True,
        )
    except OSError as exc:
        raise ProgramFoundryGepaComparisonJuryChildError("could not start") from exc
    try:
        stdout, _ = process.communicate(encoded, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _terminate_group(process)
        raise ProgramFoundryGepaComparisonJuryChildError("timed out") from exc
    except BaseException:
        _terminate_group(process)
        raise
    returncode = process.returncode
    if returncode not in {code for code, _ in _ENVELOPE_SHAPES.values()}:
        raise ProgramFoundryGepaComparisonJuryChildError(
            f"exited with status {returncode}"
        )
    if len(stdout) > CHILD_MAX_STDOUT_BYTES:
        raise ProgramFoundryGepaComparisonJuryChildError("output exceeds 16 MiB")
    try:
        answer = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProgramFoundryGepaComparisonJuryChildError("output is not JSON") from exc
    return _validate_envelope(answer, returncode=returncode)


# --- child side -------------------------------------------------------------


def _startup_posture() -> dict[str, Any]:
    return {
        "isolated": bool(sys.flags.isolated),
        "dont_write_bytecode": sys.dont_write_bytecode is True,
        "owner_modules_at_start": list(_STARTUP_OWNER_MODULES),
    }


def _require_fresh_process() -> None:
    posture = _startup_posture()
    if (
        not posture["isolated"]
        or not posture["dont_write_bytecode"]
        or posture["owner_modules_at_start"]
    ):
        raise RuntimeError("jury child requires a fresh -I -B interpreter")


def _decode_request(raw: bytes) -> dict[str, Any]:
    payload = json.loads(raw.decode("utf-8"))
    if (
        not isinstance(payload, dict)
        or set(payload) != _REQUEST_KEYS
        or payload["schema_version"] != CHILD_REQUEST_SCHEMA
        or not isinstance(payload["request"], dict)
        or not isinstance(payload["expected_input_sha256"], dict)
        or not all(
            isinstance(payload[key], str)
            for key in (
                "experiment_root",
                "attempt_sha256",
                "candidate_manifest_path",
                "comparison_path",
            )
        )
        or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in payload["expected_input_sha256"].items()
        )
    ):
        raise ValueError("jury child request shape drifted")
    return payload


def run_child_request(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Execute one task-local jury inside this (fresh) process."""

    request = revalidate_execution_request(payload["request"])
    if task_local_family(request) is None:
        raise ValueError("jury child runs task-local providers only")
    experiment_root = Path(payload["experiment_root"])
    expected_input_sha256 = {
        Path(path): digest for path, digest in payload["expected_input_sha256"].items()
    }
    with (
        task_local_process_slot(request["provider"]),
        _model_jury_process_slot() as slot,
    ):
        binding = make_task_local_runtime_binding(
            request=request,
            experiment_root=experiment_root,
            attempt_sha256=str(payload["attempt_sha256"]),
        )
        return build_comparison_model_jury_result(
            slot,
            manifest_path=Path(payload["candidate_manifest_path"]),
            evidence_paths=[Path(payload["comparison_path"])],
            provider=str(request["provider"]),
            adjudicator_id=str(request["adjudicator_id"]),
            adjudicator_kind=str(request["adjudicator_kind"]),
            adjudicator_repo=request["adjudicator_repo"],
            max_jurors=request["max_jurors"],
            expected_input_sha256=expected_input_sha256,
            provider_runtime_binding=binding,
        )


def classify_child_result(
    payload: Mapping[str, Any], results: Mapping[str, Any]
) -> None:
    """Apply the shared results contract the parent applies after writing.

    Raises ``ProgramFoundryGepaComparisonJuryError`` with the parent's label so
    the ``jury_failed`` envelope carries the in-process error text verbatim.
    """

    manifest_path = str(payload["candidate_manifest_path"])
    manifest_sha256 = payload["expected_input_sha256"].get(manifest_path)
    validate_program_model_jury_results_contract(
        results,
        label=JURY_RESULTS_LABEL,
        error_type=ProgramFoundryGepaComparisonJuryError,
        valid_manifest_refs=(
            {Path(manifest_path): str(manifest_sha256)}
            if isinstance(manifest_sha256, str)
            else None
        ),
    )


def error_payload(exc: BaseException) -> dict[str, str]:
    """Closed, bounded, secret-scrubbed error class and message."""

    reason = getattr(exc, "reason", None)
    text = reason if isinstance(reason, str) and reason else str(exc)
    message = sanitize_diagnostic_text(text, limit=CHILD_MAX_ERROR_MESSAGE_CHARS)
    return {
        "type": type(exc).__name__,
        "message": message[:CHILD_MAX_ERROR_MESSAGE_CHARS],
    }


def respond(payload: Mapping[str, Any]) -> tuple[int, dict[str, Any]]:
    """Run one decoded request and return ``(exit_status, envelope)``."""

    try:
        results = run_child_request(payload)
    except Exception as exc:  # noqa: BLE001 - bounded and reported, never re-raised
        return CHILD_EXIT_JURY_ERROR, {
            "schema_version": CHILD_RESULT_SCHEMA,
            "kind": "jury_error",
            "error": error_payload(exc),
        }
    try:
        classify_child_result(payload, results)
    except ProgramFoundryGepaComparisonJuryError as exc:
        return CHILD_EXIT_JURY_FAILED, {
            "schema_version": CHILD_RESULT_SCHEMA,
            "kind": "jury_failed",
            "results": dict(results),
            "error": error_payload(exc),
        }
    return CHILD_EXIT_JURY_OK, {
        "schema_version": CHILD_RESULT_SCHEMA,
        "kind": "jury_ok",
        "results": dict(results),
    }


def _emit(payload: Mapping[str, Any]) -> None:
    sys.stdout.buffer.write(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    sys.stdout.buffer.flush()


def main(argv: Sequence[str]) -> int:
    if list(argv) == ["--self-check"]:
        _emit(_startup_posture())
        return 0
    if argv:
        return 2
    try:
        _require_fresh_process()
        raw = sys.stdin.buffer.read(CHILD_MAX_STDIN_BYTES + 1)
        if len(raw) > CHILD_MAX_STDIN_BYTES:
            raise ValueError("jury child request too large")
        payload = _decode_request(raw)
    except Exception:  # noqa: BLE001 - pre-effect refusal prints nothing
        return 1
    status, envelope = respond(payload)
    _emit(envelope)
    return status


__all__ = [
    "CHILD_EXIT_JURY_ERROR",
    "CHILD_EXIT_JURY_FAILED",
    "CHILD_EXIT_JURY_OK",
    "CHILD_MAX_ERROR_MESSAGE_CHARS",
    "CHILD_MAX_STDOUT_BYTES",
    "CHILD_MODULE",
    "CHILD_REQUEST_SCHEMA",
    "CHILD_RESULT_SCHEMA",
    "JURY_RESULTS_LABEL",
    "ProgramFoundryGepaComparisonJuryChildError",
    "child_environment",
    "child_request_payload",
    "child_timeout_seconds",
    "classify_child_result",
    "default_child_argv",
    "error_payload",
    "main",
    "respond",
    "run_child_request",
    "run_task_local_jury_child",
]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

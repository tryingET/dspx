# summary: "Opaque-root-bound retained state and no-replace filesystem primitives."
from __future__ import annotations

import json
import os
import re
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast, final

from dspx.services.program_oracle_semantic_gate4_contract_v11 import (
    LEDGER_NAME,
    LEDGER_SCHEMA,
    PROVIDER_OUTCOMES_NAME,
    REJECTED_V10_TASK_ID,
    REQUIRED_LIVE_COMPLETION_KIND,
    RESULT_FRAGMENTS_NAME,
    SemanticV11Error,
    assert_sha256,
    canonical,
    sha256,
)

MAX_RETAINED_BYTES = 1_500_000
__all__ = [
    "LEDGER_KEYS",
    "MAX_RETAINED_BYTES",
    "ConsumedAttempt",
    "TaskBinding",
    "assert_attempt_absent",
    "current_process_identity_sha256",
    "load_consumed_attempt",
    "read_private_json",
    "require_consumed_attempt",
    "state_root_identity_sha256",
]

_ROOT_ID_DOMAIN = b"dspx-oracle-semantic-v11-state-root-v1\0"
_BINDING_ID_DOMAIN = b"dspx-oracle-semantic-v11-root-binding-v1\0"
_PROCESS_ID_DOMAIN = b"dspx-oracle-semantic-v11-process-identity-v1\0"
_COLLISIONS_NAME = ".bindings"
_BOOT_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
_GIT_ID_RE = re.compile(r"^[0-9a-f]{40}$")

LEDGER_KEYS = {
    "schema_version",
    "artifact_kind",
    "live_task_id",
    "state_root_identity_sha256",
    "root_binding_id",
    "root_binding_sha256",
    "ledger_namespace",
    "ledger_key",
    "artifact_key",
    "status",
    "maximum_evaluation_processes",
    "retry_allowed",
    "process_identity_sha256",
    "process_admitted",
    "candidate_commit",
    "candidate_tree",
    "candidate_source_manifest_sha256",
    "contract_sha256",
    "candidate_review_sha256",
    "live_gate_sha256",
    "authority_snapshot_sha256",
    "gate_4_evidence_set_sha256",
    "gate_2_task_contract_sha256",
    "gate_2_guardrails_sha256",
    "remediation_task_contract_sha256",
    "remediation_guardrails_sha256",
    "gate_3_task_id",
    "gate_3_task_contract_sha256",
    "gate_3_guardrails_sha256",
    "gate_4_task_contract_sha256",
    "gate_4_guardrails_sha256",
    "gate_2_evidence_ids",
    "gate_2_evidence_digests",
    "gate_2_evidence_set_sha256",
    "remediation_validation_evidence_id",
    "candidate_review_evidence_id",
    "operator_evidence_id",
    "live_gate_evidence_id",
    "live_authorized",
}


def _private_info(path: Path, *, directory: bool) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError as exc:
        raise SemanticV11Error("private state member missing") from exc
    expected = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if (
        not expected
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600)
        or (not directory and info.st_nlink != 1)
    ):
        raise SemanticV11Error("private state posture drift")
    return info


def state_root_identity_sha256(state_root: Path) -> str:
    """Return a stable identity for one already-private owner root."""

    original = state_root.expanduser()
    info = _private_info(original, directory=True)
    try:
        resolved_info = original.resolve(strict=True).stat()
    except OSError as exc:
        raise SemanticV11Error("private state root unavailable") from exc
    if (info.st_dev, info.st_ino, info.st_uid) != (
        resolved_info.st_dev,
        resolved_info.st_ino,
        resolved_info.st_uid,
    ):
        raise SemanticV11Error("private state root identity drift")
    return sha256(
        _ROOT_ID_DOMAIN
        + canonical({"device": info.st_dev, "inode": info.st_ino, "owner": info.st_uid})
    )


def current_process_identity_sha256() -> str:
    pid = os.getpid()
    try:
        boot_id = (
            Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
        )
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
        tail = raw[raw.rfind(")") + 2 :].split()
        start_ticks = int(tail[19])
    except (OSError, UnicodeError, ValueError, IndexError) as exc:
        raise SemanticV11Error("process identity is unavailable") from exc
    if not _BOOT_ID_RE.fullmatch(boot_id) or start_ticks <= 0:
        raise SemanticV11Error("process identity value drift")
    return sha256(
        _PROCESS_ID_DOMAIN
        + canonical(
            {
                "pid": pid,
                "uid": os.getuid(),
                "boot_id": boot_id,
                "proc_start_ticks": start_ticks,
            }
        )
    )


@final
class TaskBinding:
    """Deterministic task/root identity; it never carries live authority."""

    live_task_id: int
    state_root_identity_sha256: str
    root_binding_id: str
    ledger_namespace: str
    ledger_key: str
    artifact_key: str
    _sealed: bool

    __slots__ = (
        "live_task_id",
        "state_root_identity_sha256",
        "root_binding_id",
        "ledger_namespace",
        "ledger_key",
        "artifact_key",
        "_sealed",
    )

    def __init__(self, live_task_id: int, state_root_identity: str) -> None:
        if (
            isinstance(live_task_id, bool)
            or not isinstance(live_task_id, int)
            or live_task_id <= 0
            or live_task_id == REJECTED_V10_TASK_ID
        ):
            raise SemanticV11Error("future live task binding rejected")
        root_digest = assert_sha256(state_root_identity, "state_root_identity_sha256")
        object.__setattr__(self, "live_task_id", live_task_id)
        object.__setattr__(self, "state_root_identity_sha256", root_digest)
        object.__setattr__(
            self,
            "root_binding_id",
            sha256(
                _BINDING_ID_DOMAIN
                + canonical(
                    {
                        "live_task_id": live_task_id,
                        "state_root_identity_sha256": root_digest,
                    }
                )
            ),
        )
        object.__setattr__(
            self,
            "ledger_namespace",
            f"dspx/oracle-semantic-analysis-evaluations/AK-{live_task_id}/v11",
        )
        object.__setattr__(
            self,
            "ledger_key",
            f"AK-{live_task_id}:oracle-semantic-analysis-v11:one-process",
        )
        object.__setattr__(
            self,
            "artifact_key",
            f"oracle-semantic-analysis-evaluations/AK-{live_task_id}/v11/attempt",
        )
        object.__setattr__(self, "_sealed", True)

    @classmethod
    def create(
        cls, live_task_id: int, completion_kind: str, state_root: Path
    ) -> "TaskBinding":
        if cls is not TaskBinding or completion_kind != REQUIRED_LIVE_COMPLETION_KIND:
            raise SemanticV11Error("future live task binding rejected")
        return cls(live_task_id, state_root_identity_sha256(state_root))

    def __init_subclass__(cls, **_kwargs: object) -> None:
        raise TypeError("TaskBinding is sealed")

    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "_sealed", False):
            raise TypeError("TaskBinding is immutable")
        object.__setattr__(self, name, value)

    def require_canonical(self) -> None:
        expected = TaskBinding(self.live_task_id, self.state_root_identity_sha256)
        if type(self) is not TaskBinding or self.payload() != expected.payload():
            raise SemanticV11Error("task binding canonical drift")

    def payload(self) -> dict[str, Any]:
        return {
            "live_task_id": self.live_task_id,
            "state_root_identity_sha256": self.state_root_identity_sha256,
            "root_binding_id": self.root_binding_id,
            "ledger_namespace": self.ledger_namespace,
            "ledger_key": self.ledger_key,
            "artifact_key": self.artifact_key,
        }


@final
class ConsumedAttempt:
    """Immutable retained-state reader; never accepted as live authorization."""

    binding: TaskBinding
    attempt_root: Path
    ledger_sha256: str
    _ledger_raw: bytes
    _sealed: bool

    __slots__ = ("binding", "attempt_root", "ledger_sha256", "_ledger_raw", "_sealed")

    def __init__(
        self, binding: TaskBinding, attempt_root: Path, ledger_raw: bytes
    ) -> None:
        if type(binding) is not TaskBinding or not isinstance(ledger_raw, bytes):
            raise SemanticV11Error("consumed attempt construction rejected")
        object.__setattr__(self, "binding", binding)
        object.__setattr__(self, "attempt_root", attempt_root)
        object.__setattr__(self, "ledger_sha256", sha256(ledger_raw))
        object.__setattr__(self, "_ledger_raw", bytes(ledger_raw))
        object.__setattr__(self, "_sealed", True)
        require_consumed_attempt(self)

    def __init_subclass__(cls, **_kwargs: object) -> None:
        raise TypeError("ConsumedAttempt is sealed")

    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "_sealed", False):
            raise TypeError("ConsumedAttempt is immutable")
        object.__setattr__(self, name, value)

    @property
    def ledger(self) -> dict[str, Any]:
        try:
            value = json.loads(self._ledger_raw)
        except (UnicodeError, json.JSONDecodeError) as exc:  # pragma: no cover
            raise SemanticV11Error("consumed ledger invalid") from exc
        if not isinstance(value, Mapping):  # pragma: no cover
            raise SemanticV11Error("consumed ledger invalid")
        return dict(value)

    @property
    def live_authorized(self) -> bool:
        return self.ledger.get("live_authorized") is True

    def require_retained(self) -> None:
        require_consumed_attempt(self)


def require_consumed_attempt(value: object) -> ConsumedAttempt:
    if type(value) is not ConsumedAttempt:
        raise SemanticV11Error("exact consumed attempt required")
    attempt = value
    try:
        attempt.binding.require_canonical()
        raw = attempt._ledger_raw
        path = attempt.attempt_root / LEDGER_NAME
        _private_info(path, directory=False)
        retained = path.read_bytes()
    except (AttributeError, OSError) as exc:
        raise SemanticV11Error("consumed ledger invalid") from exc
    if retained != raw or sha256(retained) != attempt.ledger_sha256:
        raise SemanticV11Error("consumed ledger bytes drift")
    try:
        ledger = json.loads(retained)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SemanticV11Error("consumed ledger invalid") from exc
    if not isinstance(ledger, Mapping):
        raise SemanticV11Error("consumed ledger invalid")
    _validate_ledger(attempt.binding, ledger)
    return attempt


def _fsync_directory(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        raise SemanticV11Error("directory sync failed") from exc


def _persist_no_replace(path: Path, payload: Mapping[str, Any]) -> bytes:
    """Same-UID no-replace sink; it is not an authorization mechanism."""

    raw = canonical(dict(payload))
    if not raw or len(raw) > MAX_RETAINED_BYTES:
        raise SemanticV11Error("retained payload size drift")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
        try:
            os.fchmod(fd, 0o600)
            view = memoryview(raw)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise OSError("short write")
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        _fsync_directory(path.parent)
    except FileExistsError as exc:
        raise SemanticV11Error("retained member already exists") from exc
    except SemanticV11Error:
        raise
    except OSError as exc:
        raise SemanticV11Error("retained member write failed") from exc
    return raw


def read_private_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    _private_info(path, directory=False)
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SemanticV11Error(f"{label} invalid") from exc
    if (
        not isinstance(value, Mapping)
        or not raw
        or len(raw) > MAX_RETAINED_BYTES
        or canonical(value) != raw
    ):
        raise SemanticV11Error(f"{label} canonical drift")
    return dict(value), raw


def _mkdir_exclusive(path: Path) -> None:
    try:
        os.mkdir(path, 0o700)
        os.chmod(path, 0o700)
        _fsync_directory(path)
        _fsync_directory(path.parent)
    except FileExistsError as exc:
        raise SemanticV11Error("task-bound state collision") from exc
    except SemanticV11Error:
        raise
    except OSError as exc:
        raise SemanticV11Error("task-bound directory creation failed") from exc


def _paths(state_root: Path, binding: TaskBinding) -> tuple[Path, Path, Path, Path]:
    namespace = state_root / "oracle-semantic-analysis-evaluations"
    task = namespace / f"AK-{binding.live_task_id}"
    version = task / "v11"
    return namespace, task, version, version / "attempt"


def _collision_path(state_root: Path, binding: TaskBinding) -> Path:
    namespace, _, _, _ = _paths(state_root, binding)
    return namespace / _COLLISIONS_NAME / f"{binding.root_binding_id}.json"


def assert_attempt_absent(state_root: Path, binding: TaskBinding) -> None:
    """Absence-only preflight; no path is created."""

    binding.require_canonical()
    root = state_root.expanduser()
    if state_root_identity_sha256(root) != binding.state_root_identity_sha256:
        raise SemanticV11Error("task binding state-root identity drift")
    _, task, version, attempt = _paths(root, binding)
    for path in (task, version, attempt, _collision_path(root, binding)):
        if path.exists() or path.is_symlink():
            raise SemanticV11Error("task-bound attempt already exists")


def _prepare_attempt_directories(state_root: Path, binding: TaskBinding) -> Path:
    """Create only the fixed empty tree; no mapping can mark it live."""

    root = state_root.expanduser()
    assert_attempt_absent(root, binding)
    namespace, task, version, attempt = _paths(root, binding)
    if namespace.exists() or namespace.is_symlink():
        _private_info(namespace, directory=True)
    else:
        _mkdir_exclusive(namespace)
    collisions = namespace / _COLLISIONS_NAME
    if collisions.exists() or collisions.is_symlink():
        _private_info(collisions, directory=True)
    else:
        _mkdir_exclusive(collisions)
    _mkdir_exclusive(task)
    _mkdir_exclusive(version)
    _mkdir_exclusive(attempt)
    _mkdir_exclusive(attempt / PROVIDER_OUTCOMES_NAME)
    _mkdir_exclusive(attempt / RESULT_FRAGMENTS_NAME)
    return attempt


def _validate_ledger(binding: TaskBinding, ledger: Mapping[str, Any]) -> None:
    if (
        set(ledger) != LEDGER_KEYS
        or ledger.get("schema_version") != LEDGER_SCHEMA
        or ledger.get("artifact_kind") != "consumed_attempt"
        or ledger.get("live_task_id") != binding.live_task_id
        or ledger.get("state_root_identity_sha256")
        != binding.state_root_identity_sha256
        or ledger.get("root_binding_id") != binding.root_binding_id
        or ledger.get("ledger_namespace") != binding.ledger_namespace
        or ledger.get("ledger_key") != binding.ledger_key
        or ledger.get("artifact_key") != binding.artifact_key
        or ledger.get("status") != "consumed"
        or ledger.get("maximum_evaluation_processes") != 1
        or ledger.get("retry_allowed") is not False
        or not isinstance(ledger.get("process_admitted"), bool)
        or not isinstance(ledger.get("live_authorized"), bool)
    ):
        raise SemanticV11Error("consumed ledger binding drift")
    for key in LEDGER_KEYS:
        if key.endswith("_sha256"):
            assert_sha256(ledger.get(key), key)
    if not _GIT_ID_RE.fullmatch(
        str(ledger.get("candidate_commit", ""))
    ) or not _GIT_ID_RE.fullmatch(str(ledger.get("candidate_tree", ""))):
        raise SemanticV11Error("consumed candidate Git identity drift")
    digests = ledger.get("gate_2_evidence_digests")
    if (
        ledger.get("gate_2_evidence_ids") != [6729, 6730]
        or not isinstance(digests, list)
        or len(digests) != 2
    ):
        raise SemanticV11Error("consumed Gate-2 evidence binding drift")
    for digest in digests:
        assert_sha256(digest, "Gate-2 full evidence digest")
    int_keys = {
        "gate_3_task_id",
        "remediation_validation_evidence_id",
        "candidate_review_evidence_id",
        "operator_evidence_id",
        "live_gate_evidence_id",
    }
    if any(
        isinstance(ledger.get(key), bool)
        or not isinstance(ledger.get(key), int)
        or cast(int, ledger[key]) <= 0
        for key in int_keys
    ):
        raise SemanticV11Error("consumed authority selector drift")


def _validate_artifact(payload: Mapping[str, Any], schema: str, kind: str) -> None:
    if payload.get("schema_version") != schema or payload.get("artifact_kind") != kind:
        raise SemanticV11Error("authority artifact schema drift")


def _binding_marker(binding: TaskBinding, ledger: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": LEDGER_SCHEMA,
        "artifact_kind": "root_binding_collision",
        "live_task_id": binding.live_task_id,
        "state_root_identity_sha256": binding.state_root_identity_sha256,
        "root_binding_id": binding.root_binding_id,
        "candidate_review_sha256": ledger["candidate_review_sha256"],
        "live_gate_sha256": ledger["live_gate_sha256"],
        "authority_snapshot_sha256": ledger["authority_snapshot_sha256"],
        "retry_allowed": False,
    }


def _consume_fixture_attempt(state_root: Path, binding: TaskBinding) -> ConsumedAttempt:
    """Test-only provider-free state; private and never live-authorized."""

    fixture = sha256(canonical({"fixture_only": True, "binding": binding.payload()}))
    ledger: dict[str, Any] = {
        "schema_version": LEDGER_SCHEMA,
        "artifact_kind": "consumed_attempt",
        **binding.payload(),
        "root_binding_sha256": "0" * 64,
        "status": "consumed",
        "maximum_evaluation_processes": 1,
        "retry_allowed": False,
        "process_identity_sha256": current_process_identity_sha256(),
        "process_admitted": False,
        "candidate_commit": "0" * 40,
        "candidate_tree": "0" * 40,
        "candidate_source_manifest_sha256": fixture,
        "contract_sha256": fixture,
        "candidate_review_sha256": fixture,
        "live_gate_sha256": fixture,
        "authority_snapshot_sha256": fixture,
        "gate_4_evidence_set_sha256": fixture,
        "gate_2_task_contract_sha256": fixture,
        "gate_2_guardrails_sha256": fixture,
        "remediation_task_contract_sha256": fixture,
        "remediation_guardrails_sha256": fixture,
        "gate_3_task_id": binding.live_task_id + 1,
        "gate_3_task_contract_sha256": fixture,
        "gate_3_guardrails_sha256": fixture,
        "gate_4_task_contract_sha256": fixture,
        "gate_4_guardrails_sha256": fixture,
        "gate_2_evidence_ids": [6729, 6730],
        "gate_2_evidence_digests": [fixture, fixture],
        "gate_2_evidence_set_sha256": fixture,
        "remediation_validation_evidence_id": binding.live_task_id + 3,
        "candidate_review_evidence_id": binding.live_task_id + 4,
        "operator_evidence_id": binding.live_task_id + 5,
        "live_gate_evidence_id": binding.live_task_id + 6,
        "live_authorized": False,
    }
    _validate_ledger(binding, ledger)
    attempt_root = _prepare_attempt_directories(state_root, binding)
    marker_raw = _persist_no_replace(
        _collision_path(state_root.expanduser(), binding),
        _binding_marker(binding, ledger),
    )
    ledger["root_binding_sha256"] = sha256(marker_raw)
    _validate_ledger(binding, ledger)
    raw = _persist_no_replace(attempt_root / LEDGER_NAME, ledger)
    return ConsumedAttempt(binding, attempt_root, raw)


def load_consumed_attempt(state_root: Path, live_task_id: int) -> ConsumedAttempt:
    root = state_root.expanduser()
    binding = TaskBinding(live_task_id, state_root_identity_sha256(root))
    _, _, _, attempt_root = _paths(root, binding)
    _private_info(attempt_root, directory=True)
    _private_info(attempt_root / PROVIDER_OUTCOMES_NAME, directory=True)
    _private_info(attempt_root / RESULT_FRAGMENTS_NAME, directory=True)
    _, raw = read_private_json(attempt_root / LEDGER_NAME, "consumed ledger")
    attempt = ConsumedAttempt(binding, attempt_root, raw)
    marker, marker_raw = read_private_json(
        _collision_path(root, binding), "root binding collision"
    )
    if (
        marker != _binding_marker(binding, attempt.ledger)
        or sha256(marker_raw) != attempt.ledger["root_binding_sha256"]
    ):
        raise SemanticV11Error("root binding collision drift")
    return attempt

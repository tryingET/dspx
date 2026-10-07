# summary: "Private immutable image intent/terminal custody, consumed slots and owned-process settlement."
# read_when:
#   - "Changing image effect finalization, no-retry budgets or supervised worker ownership."

from __future__ import annotations

import os
import json
import stat
import time
import uuid
from typing import Any

from .image_admission import (
    ImageContractError,
    canonical,
    closed,
    digest,
    hash_value,
    parse_json,
    require,
    sha,
    uuid_value,
)

from .image_record_validation import validate_terminal

_READY = "schema_version custody_id caller_run_id caller_binding_sha256 caller_expectation_sha256 admission_sha256 source_package_sha256 input_manifest_sha256 runtime_identity_sha256 root_dev root_ino total_dispatch_allowance request_plan_sha256 creator_pid created_utc_ms worker_pid worker_start_identity worker_deadline_ns grant_sha256"
_INTENT = "schema_version custody_id caller_run_id caller_binding_sha256 admission_sha256 input_manifest_sha256 attempt_id attempt_ordinal plan_ordinal request_sha256 request_shape_sha256 image_occurrence_sequence validated_image_count validated_image_bytes reserved_utc_ms deadline_utc_ms"
_TERMINAL = "schema_version custody_id caller_run_id attempt_id attempt_ordinal intent_sha256 request_sha256 dispatch_count provider_disposition observed_model response_sha256 response_byte_count finalization_kind result_finalization_completed typed_finalization_completed failure_code terminal_utc_ms"
_CLOSURE = "schema_version custody_id caller_run_id admission_sha256 input_manifest_sha256 consumed_dispatches terminal_commitments artifact_manifest_sha256 local_outcome closed_utc_ms"
_DISPOSITIONS = {
    "completed_success",
    "completed_failure",
    "effect_indeterminate",
    "preflight_rejected",
}
_FAILURES = {
    "validation",
    "budget",
    "policy",
    "io",
    "response",
    "interruption",
    "finalization",
    "durability",
    "privacy",
}


def now_ms() -> int:
    return time.time_ns() // 1_000_000


def private_root(fd: int) -> os.stat_result:
    row = os.fstat(fd)
    require(
        stat.S_ISDIR(row.st_mode)
        and stat.S_IMODE(row.st_mode) == 0o700
        and row.st_uid == os.geteuid(),
        "image_custody",
    )
    return row


def list_root(root_fd: int) -> list[str]:
    # listdir(fd) consumes its open-description offset, shared across dup/fork.
    # An independently opened description prevents hidden entries on later scans.
    fd = os.open(
        ".", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=root_fd
    )
    try:
        original, current = os.fstat(root_fd), os.fstat(fd)
        require(
            (original.st_dev, original.st_ino) == (current.st_dev, current.st_ino),
            "image_custody",
        )
        return os.listdir(fd)
    finally:
        os.close(fd)


def read_record(root_fd: int, name: str) -> bytes:
    fd = os.open(
        name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root_fd
    )
    try:
        row = os.fstat(fd)
        require(
            stat.S_ISREG(row.st_mode)
            and stat.S_IMODE(row.st_mode) == 0o600
            and row.st_uid == os.geteuid()
            and row.st_nlink == 1
            and 0 < row.st_size <= 65_536,
            "image_custody",
        )
        raw = bytearray()
        while len(raw) <= 65_536:
            block = os.read(fd, min(4096, 65_537 - len(raw)))
            if not block:
                break
            raw.extend(block)
        after = os.fstat(fd)
        require(
            len(raw) == row.st_size
            and (row.st_ino, row.st_size, row.st_mtime_ns, row.st_ctime_ns)
            == (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
            "image_custody",
        )
        result = bytes(raw)
        require(canonical(parse_json(result, limit=65_536)) == result, "image_custody")
        return result
    finally:
        os.close(fd)


def publish(root_fd: int, name: str, record: object) -> str:
    """No-replace durable publication. Unknown completion retains residue and denies."""
    raw = canonical(record)
    require(0 < len(raw) <= 65_536, "image_budget")
    require(
        name == os.path.basename(name) and not name.startswith("."), "image_custody"
    )
    pending = ".pending-" + str(uuid.uuid4())
    fd = -1
    try:
        fd = os.open(
            pending,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
            dir_fd=root_fd,
        )
        offset = 0
        while offset < len(raw):
            written = os.write(fd, raw[offset:])
            require(written > 0, "image_durability")
            offset += written
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.link(
            pending, name, src_dir_fd=root_fd, dst_dir_fd=root_fd, follow_symlinks=False
        )
        os.unlink(pending, dir_fd=root_fd)  # only own, known-settled temporary link
        os.fsync(root_fd)
        require(read_record(root_fd, name) == raw, "image_durability")
        return sha(raw)
    except BaseException:
        raise ImageContractError("image_durability") from None
    finally:
        if fd >= 0:
            os.close(fd)


def residue(name: str) -> bool:
    """Own unsettled publication: exactly `.pending-` and a canonical uuid4."""
    return name.startswith(".pending-") and uuid_value(name[9:])


def scan(
    self: Any,
    *,
    allow_open: bool = False,
    allow_closure: bool = False,
    allow_residue: bool = False,
) -> list[tuple[dict, dict | None]]:
    require(read_record(self.root_fd, "ready.json") == self.ready_raw, "image_custody")
    names = set(list_root(self.root_fd))
    if allow_residue:  # read-only reconciliation only; never a dispatching scan
        names = {name for name in names if not residue(name)}
    require(
        "lock" in names and "ready.json" in names and len(names) <= 131,
        "image_custody",
    )
    allowed = {"lock", "ready.json"} | {
        f"{kind}-{number}.json"
        for kind in ("intent", "terminal")
        for number in range(1, 65)
    }
    if allow_closure:
        allowed.add("closure.json")
    require(names <= allowed, "image_custody")
    rows: list[tuple[dict, dict | None]] = []
    attempts = set()
    missing = False
    for ordinal in range(1, 65):
        intent_name = f"intent-{ordinal}.json"
        terminal_name = f"terminal-{ordinal}.json"
        if intent_name not in names:
            require(terminal_name not in names, "image_custody")
            missing = True
            continue
        require(
            not missing and ordinal <= len(self.record["request_plan"]),
            "image_custody",
        )
        raw = read_record(self.root_fd, intent_name)
        intent = closed(parse_json(raw), _INTENT)
        plan = self.record["request_plan"][ordinal - 1]
        require(
            intent["schema_version"] == "dspx-image-dispatch-intent-v1"
            and intent["attempt_ordinal"] == ordinal
            and intent["plan_ordinal"] == ordinal
            and uuid_value(intent["attempt_id"])
            and intent["attempt_id"] not in attempts,
            "image_custody",
        )
        attempts.add(intent["attempt_id"])
        expected = {
            "custody_id": self.binding["custody_id"],
            "caller_run_id": self.binding["caller_run_id"],
            "caller_binding_sha256": self.binding["caller_binding_sha256"],
            "admission_sha256": self.admission.sha256,
            "input_manifest_sha256": self.manifest_sha256,
            "request_shape_sha256": plan["request_shape_sha256"],
            "image_occurrence_sequence": plan["image_occurrence_sequence"],
        }
        require(
            all(intent[key] == value for key, value in expected.items()),
            "image_custody",
        )
        by_id = {
            row["occurrence_id"]: row
            for row in self.context.source["source_occurrences"]
        }
        seq = plan["image_occurrence_sequence"]
        require(
            intent["validated_image_count"] == len(seq)
            and intent["validated_image_bytes"]
            == sum(by_id[key]["byte_count"] for key in seq),
            "image_custody",
        )
        request_digest = digest(
            "request-v1",
            {
                "admission_sha256": self.admission.sha256,
                "input_manifest_sha256": self.manifest_sha256,
                "plan_ordinal": ordinal,
                "request_shape_sha256": plan["request_shape_sha256"],
            },
        )
        # ubs:ignore -- public sha256 commitment, not a secret
        require(intent["request_sha256"] == request_digest, "image_custody")
        require(
            type(intent["reserved_utc_ms"]) is int
            and type(intent["deadline_utc_ms"]) is int
            and 0
            < intent["reserved_utc_ms"]
            <= intent["deadline_utc_ms"]
            <= self.record["deadlines"]["expires_utc_ms"],
            "image_custody",
        )
        terminal = None
        if terminal_name in names:
            terminal = closed(
                parse_json(read_record(self.root_fd, terminal_name)), _TERMINAL
            )
            require(
                terminal["schema_version"] == "dspx-image-dispatch-terminal-v1"
                and terminal["intent_sha256"] == sha(raw),
                "image_custody",
            )
            require(
                all(
                    terminal[key] == intent[key]
                    for key in (
                        "custody_id",
                        "caller_run_id",
                        "attempt_id",
                        "attempt_ordinal",
                        "request_sha256",
                    )
                ),
                "image_custody",
            )
            require(
                type(terminal["dispatch_count"]) is int
                and terminal["dispatch_count"] in {0, 1}
                and terminal["provider_disposition"] in _DISPOSITIONS,
                "image_custody",
            )
            require(
                terminal["finalization_kind"] in {"direct_provider", "dspy_lm"}
                and type(terminal["result_finalization_completed"]) is bool
                and type(terminal["typed_finalization_completed"]) is bool,
                "image_custody",
            )
            require(
                not terminal["typed_finalization_completed"]
                or (
                    terminal["finalization_kind"] == "dspy_lm"
                    and terminal["result_finalization_completed"]
                ),
                "image_custody",
            )
            require(
                terminal["failure_code"] is None
                or terminal["failure_code"] in _FAILURES,
                "image_custody",
            )
            require(
                terminal["response_sha256"] is None
                or hash_value(terminal["response_sha256"]),
                "image_custody",
            )
            validate_terminal(
                terminal,
                intent,
                model=self.record["model"],
                expires_ms=self.record["deadlines"]["expires_utc_ms"],
                max_response_bytes=self.record["limits"]["max_response_bytes"],
            )
        else:
            require(allow_open, "image_spent")
        rows.append((intent, terminal))
    return rows


def read_image_artifact(fd: int, name: str, *, limit: int = 4_194_304) -> bytes:
    require(
        name == os.path.basename(name) and not name.startswith("."), "image_custody"
    )
    leaf = os.open(
        name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=fd
    )
    try:
        before = os.fstat(leaf)
        require(
            stat.S_ISREG(before.st_mode)
            and stat.S_IMODE(before.st_mode) == 0o600
            and before.st_uid == os.geteuid()
            and before.st_nlink == 1
            and 0 < before.st_size <= limit,
            "image_custody",
        )
        chunks = bytearray()
        while len(chunks) <= limit:
            block = os.read(leaf, min(65_536, limit + 1 - len(chunks)))
            if not block:
                break
            chunks.extend(block)
        after = os.fstat(leaf)
        require(
            len(chunks) == before.st_size
            and (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            == (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ),
            "image_custody",
        )
        return bytes(chunks)
    finally:
        os.close(leaf)


def publish_image_output(fd: int, name: str, record: object) -> str:
    # Output values may have finite floats; custody/commitment records do not.
    raw = json.dumps(
        record,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("ascii")
    require(0 < len(raw) <= 4_194_304, "image_budget")
    pending = ".pending-" + str(uuid.uuid4())
    leaf = os.open(
        pending,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
        0o600,
        dir_fd=fd,
    )
    try:
        offset = 0
        while offset < len(raw):
            written = os.write(leaf, raw[offset:])
            require(written > 0, "image_durability")
            offset += written
        os.fsync(leaf)
    finally:
        os.close(leaf)
    os.link(pending, name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
    os.unlink(pending, dir_fd=fd)
    os.fsync(fd)
    require(read_image_artifact(fd, name) == raw, "image_durability")
    return sha(raw)

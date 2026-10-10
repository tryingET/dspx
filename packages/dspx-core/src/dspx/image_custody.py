# summary: "One private image run, durable consumed slots and late immutable terminals."
from __future__ import annotations
from contextlib import contextmanager
import fcntl
import os
import stat
import threading
import time
import uuid
from typing import Any, Iterator, cast
from .image_admission import (
    ImageAdmission,
    ImageContractError,
    LiveImageAuthority,
    SyntheticImageAuthority,
    canonical,
    closed,
    digest,
    sha,
    parse_json,
    refuse,
    require,
    validate_admission,
)
from .image_input_contract import ImageContext
from .image_records import (
    private_root,
    list_root,
    publish,
    read_record,
    scan,
    now_ms,
    _READY,
    _CLOSURE,
    _DISPOSITIONS,
    _FAILURES,
)
from .image_supervision import (
    worker_deadline,
    parent_ready,
    worker_identity,
    require_admitted_worker_budget,
)
from .image_worker import supervised_worker, worker_binding


def parent_initializer(
    root_fd: int,
    authority,
    admission: ImageAdmission,
    *,
    source_sha256: str,
    manifest_sha256: str,
):
    """Independently expected parent data; a worker message never authorizes itself."""
    require(
        type(authority) in {SyntheticImageAuthority, LiveImageAuthority}
        and not authority._used
        and authority.expected_admission == admission.raw,
        "image_custody",
    )
    root = private_root(root_fd)
    require(not list_root(root_fd), "image_spent")
    record = admission.record
    binding = record["custody"]
    require(
        (root.st_dev, root.st_ino) == (authority.root_dev, authority.root_ino)
        and record["source_package_sha256"] == source_sha256,
        "image_custody",
    )

    # Reserve the nominal parent act BEFORE its bounded IO delegate is forked.
    # A nonempty list is spent for later factories, even on failed publication.
    authority._used.append(False)
    parent_pid = os.getpid()

    def initialize(ready):
        require(authority._used == [False], "image_spent")
        authority._used[0] = True
        closed(ready, _READY)
        expected = {
            "schema_version": "dspx-image-custody-ready-v2",
            **binding,
            "admission_sha256": admission.sha256,
            "source_package_sha256": source_sha256,
            "input_manifest_sha256": manifest_sha256,
            "runtime_identity_sha256": record["runtime_identity_sha256"],
            "total_dispatch_allowance": record["limits"]["total_dispatch_allowance"],
            "request_plan_sha256": digest("request-plan-v1", record["request_plan"]),
            "creator_pid": parent_pid,
            "created_utc_ms": ready["created_utc_ms"],
            # Parent-held truth about the spawned child and its one-use grant.
            **supervised_worker(),
        }
        require(
            ready == expected
            and type(ready["created_utc_ms"]) is int
            and record["deadlines"]["not_before_utc_ms"]
            <= ready["created_utc_ms"]
            <= now_ms()
            < record["deadlines"]["expires_utc_ms"],
            "image_custody",
        )
        # Claim before publishing: O_EXCL on the lock is the one atomic arbiter between
        # contending parents, so a loser fails before it writes anything (no residue).
        fd = os.open(
            "lock",
            os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=root_fd,
        )
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        require(list_root(root_fd) == ["lock"], "image_spent")
        publish(root_fd, "ready.json", ready)  # its directory fsync covers the lock

    return initialize


class ImageCustodySession:
    """One nominal authenticated active run. Existing roots never reconstruct dispatch."""

    def __init__(
        self,
        *,
        root_fd: int,
        admission: ImageAdmission,
        authority: object,
        context: ImageContext,
    ) -> None:
        require(
            type(admission) is ImageAdmission and type(context) is ImageContext,
            "image_custody",
        )
        require(
            type(authority) in {SyntheticImageAuthority, LiveImageAuthority},
            "image_custody",
        )
        # Exact nominal check above excludes subclasses and serialized stand-ins.
        authority = cast(SyntheticImageAuthority | LiveImageAuthority, authority)
        require(authority._used == [False], "image_spent")
        require(authority.expected_admission == admission.raw, "image_custody")
        worker_identity()
        from .image_privacy import runtime_identity

        validate_admission(
            admission.raw,
            source=context.source,
            authority=authority,
            runtime_identity_sha256=runtime_identity(),
        )
        require_admitted_worker_budget(admission.record["deadlines"])
        from .image_admission import bounded_tree

        limits = admission.record["limits"]
        require(
            len(context.input_raw) <= limits["max_input_json_bytes"]
            and sha(context.input_raw) == context.source["raw_input_file_sha256"],
            "image_budget",
        )
        bounded_tree(
            parse_json(context.input_raw),
            max_depth=limits["max_depth"],
            max_nodes=limits["max_nodes"],
        )
        root = private_root(root_fd)
        require(not list_root(root_fd), "image_spent")
        self.root_fd = os.dup(root_fd)
        self._admission = admission
        self._authority = authority
        self._context = context
        require(
            context.source_sha256 == self.record["source_package_sha256"],
            "image_custody",
        )
        self._manifest_raw = canonical(context.manifest(admission.sha256))
        require(
            (root.st_dev, root.st_ino)
            == (self.binding["root_dev"], self.binding["root_ino"]),
            "image_custody",
        )
        self.poisoned = False
        self.closed = False
        self._lock = threading.RLock()
        self._transaction: ImageAttemptTransaction | None = None
        authority._used[0] = True  # this reserved invocation is never reusable
        ready = {
            "schema_version": "dspx-image-custody-ready-v2",
            **self.binding,
            "admission_sha256": admission.sha256,
            "source_package_sha256": context.source_sha256,
            "input_manifest_sha256": self.manifest_sha256,
            "runtime_identity_sha256": self.record["runtime_identity_sha256"],
            "total_dispatch_allowance": self.record["limits"][
                "total_dispatch_allowance"
            ],
            "request_plan_sha256": digest(
                "request-plan-v1", self.record["request_plan"]
            ),
            "creator_pid": os.getppid(),
            "created_utc_ms": now_ms(),
            **worker_binding(),
        }
        closed(ready, _READY)
        self._ready_raw = canonical(ready)
        try:
            parent_ready(ready)
            require(
                read_record(self.root_fd, "ready.json") == self.ready_raw,
                "image_custody",
            )
        except BaseException:
            self.poisoned = True
            raise ImageContractError("image_durability") from None

    @property
    def admission(self) -> ImageAdmission:
        return self._admission

    @property
    def authority(self) -> SyntheticImageAuthority | LiveImageAuthority:
        return self._authority

    @property
    def context(self) -> ImageContext:
        return self._context

    @property
    def record(self) -> dict[str, Any]:
        # Fresh nested views: callers cannot mutate the active plan or ceilings.
        return self.admission.record

    @property
    def binding(self) -> dict[str, Any]:
        return self.record["custody"]

    @property
    def manifest(self) -> dict[str, Any]:
        return parse_json(self._manifest_raw, limit=65_536)

    @property
    def manifest_sha256(self) -> str:
        return digest("manifest-v2", self.manifest)

    @property
    def ready_raw(self) -> bytes:
        return self._ready_raw

    def __repr__(self) -> str:
        return "ImageCustodySession()"

    def _scan(self, *, allow_open: bool = False, allow_closure: bool = False):
        return scan(self, allow_open=allow_open, allow_closure=allow_closure)

    @contextmanager
    def transaction(self, kind: str) -> Iterator[ImageAttemptTransaction]:
        require_admitted_worker_budget(self.record["deadlines"])
        require(
            kind in {"direct_provider", "dspy_lm"}
            and not self.poisoned
            and not self.closed,
            "image_spent",
        )
        with self._lock:
            if self._transaction is not None:
                require(
                    self._transaction.thread == threading.get_ident(), "image_custody"
                )
                yield self._transaction
                return
            # Each process/transaction opens an independent description: never flock an inherited dup.
            fd = os.open(
                "lock",
                os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                dir_fd=self.root_fd,
            )
            try:
                row = os.fstat(fd)
                require(
                    stat.S_ISREG(row.st_mode)
                    and row.st_uid == os.geteuid()
                    and stat.S_IMODE(row.st_mode) == 0o600
                    and row.st_nlink == 1,
                    "image_custody",
                )
                while True:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        worker_deadline()
                        time.sleep(0.005)
                rows = self._scan()
                require(
                    all(
                        terminal is not None
                        and terminal["provider_disposition"] == "completed_success"
                        for _, terminal in rows
                    ),
                    "image_spent",
                )
                require(
                    len(rows) < self.record["limits"]["total_dispatch_allowance"],
                    "image_budget",
                )
                tx = ImageAttemptTransaction(self, kind, len(rows) + 1)
                self._transaction = tx
                try:
                    yield tx
                    require(
                        tx.intent is None or tx.terminal is not None,
                        "image_finalization",
                    )
                except BaseException as error:
                    refuse(self._settle(tx, error))
                finally:
                    self._transaction = None
            finally:
                os.close(fd)

    def _settle(self, tx: ImageAttemptTransaction, error: BaseException) -> str:
        """The one fixed code for a failed body; the caller raises it chain-free."""
        if tx.intent is None:
            # Nothing reserved: a fixed refusal keeps its precise code; any other
            # exception (KeyboardInterrupt, SystemExit, ...) is an interruption.
            return (
                error.code
                if type(error) is ImageContractError
                else "image_interruption"
            )
        if tx.terminal is None:
            self.poisoned = True
            try:
                tx.finish(
                    "effect_indeterminate"
                    if tx.dispatch_entered
                    else "preflight_rejected",
                    failure_code="interruption",
                )
            except ImageContractError as failure:
                return failure.code  # the terminal itself failed (image_durability)
        return "image_interruption"

    def close_run(self, artifacts: object, *, outcome: str) -> None:
        from .image_artifacts import ImageArtifactBinding, verify_artifact_binding

        require(type(artifacts) is ImageArtifactBinding, "image_custody")
        binding = cast(ImageArtifactBinding, artifacts)
        verify_artifact_binding(binding, self)
        artifact_manifest_sha256 = binding.published_sha256
        # Only an all-success run publishes artifacts, so it only closes as completed.
        require(outcome == "completed", "image_custody")
        require(not self.closed and self._transaction is None, "image_spent")
        rows = self._scan()
        require(
            bool(rows)
            and len(rows) == len(self.record["request_plan"])
            and all(
                term is not None and term["provider_disposition"] == "completed_success"
                for _, term in rows
            ),
            "image_custody",
        )
        commitments = [
            {
                "ordinal": row["attempt_ordinal"],
                "attempt_id": row["attempt_id"],
                "terminal_sha256": sha(
                    read_record(self.root_fd, f"terminal-{row['attempt_ordinal']}.json")
                ),
            }
            for row, term in rows
            if term is not None
        ]
        record = {
            "schema_version": "dspx-image-run-closure-v1",
            "custody_id": self.binding["custody_id"],
            "caller_run_id": self.binding["caller_run_id"],
            "admission_sha256": self.admission.sha256,
            "input_manifest_sha256": self.manifest_sha256,
            "consumed_dispatches": len(rows),
            "terminal_commitments": commitments,
            "artifact_manifest_sha256": artifact_manifest_sha256,
            "local_outcome": outcome,
            "closed_utc_ms": now_ms(),
        }
        closed(record, _CLOSURE)
        self.closed = True  # spent before durability, never retry a failed close
        publish(self.root_fd, "closure.json", record)


class ImageAttemptTransaction:
    def __init__(self, session: ImageCustodySession, kind: str, ordinal: int) -> None:
        self.session, self.kind, self.ordinal = session, kind, ordinal
        self.thread = threading.get_ident()
        self.intent: dict[str, Any] | None = None
        self.terminal: dict[str, Any] | None = None
        self.dispatch_entered = False
        self.response_sha256: str | None = None
        self.response_byte_count: int | None = None
        self.observed_model: str | None = None
        self.result_completed = False
        self.typed_completed = False
        self.pending_disposition: str | None = None
        self.pending_failure: str | None = None

    def reserve(self, request_shape_sha256: str, sequence: list[str]) -> str:
        require(self.intent is None, "image_custody")
        require_admitted_worker_budget(self.session.record["deadlines"])
        plan = self.session.record["request_plan"][self.ordinal - 1]
        require(
            request_shape_sha256 == plan["request_shape_sha256"]
            and sequence == plan["image_occurrence_sequence"],
            "image_admission_invalid",
        )
        by_id = {item.occurrence_id: item for item in self.session.context.occurrences}
        record = {
            "schema_version": "dspx-image-dispatch-intent-v1",
            "custody_id": self.session.binding["custody_id"],
            "caller_run_id": self.session.binding["caller_run_id"],
            "caller_binding_sha256": self.session.binding["caller_binding_sha256"],
            "admission_sha256": self.session.admission.sha256,
            "input_manifest_sha256": self.session.manifest_sha256,
            "attempt_id": str(uuid.uuid4()),
            "attempt_ordinal": self.ordinal,
            "plan_ordinal": self.ordinal,
            "request_sha256": digest(
                "request-v1",
                {
                    "admission_sha256": self.session.admission.sha256,
                    "input_manifest_sha256": self.session.manifest_sha256,
                    "plan_ordinal": self.ordinal,
                    "request_shape_sha256": request_shape_sha256,
                },
            ),
            "request_shape_sha256": request_shape_sha256,
            "image_occurrence_sequence": sequence,
            "validated_image_count": len(sequence),
            "validated_image_bytes": sum(len(by_id[key].data) for key in sequence),
            "reserved_utc_ms": now_ms(),
            "deadline_utc_ms": self.session.record["deadlines"]["expires_utc_ms"],
        }
        try:
            self.intent_sha256 = publish(
                self.session.root_fd, f"intent-{self.ordinal}.json", record
            )
        except BaseException:
            self.session.poisoned = True
            raise ImageContractError("image_durability") from None
        self.intent = record  # only after publication is fully known durable
        return record["attempt_id"]

    def finish(self, disposition: str, *, failure_code: str | None = None) -> None:
        intent = self.intent
        if intent is None or self.terminal is not None:
            raise ImageContractError("image_custody") from None
        require(
            disposition in _DISPOSITIONS
            and (failure_code is None or failure_code in _FAILURES),
            "image_custody",
        )
        if disposition == "effect_indeterminate":
            self.session.poisoned = True
        record = {
            "schema_version": "dspx-image-dispatch-terminal-v1",
            "custody_id": intent["custody_id"],
            "caller_run_id": intent["caller_run_id"],
            "attempt_id": intent["attempt_id"],
            "attempt_ordinal": self.ordinal,
            "intent_sha256": self.intent_sha256,
            "request_sha256": intent["request_sha256"],
            "dispatch_count": int(self.dispatch_entered),
            "provider_disposition": disposition,
            "observed_model": self.observed_model,
            "response_sha256": self.response_sha256,
            "response_byte_count": self.response_byte_count,
            "finalization_kind": self.kind,
            "result_finalization_completed": self.result_completed,
            "typed_finalization_completed": self.typed_completed,
            "failure_code": failure_code,
            "terminal_utc_ms": now_ms(),
        }
        try:
            publish(self.session.root_fd, f"terminal-{self.ordinal}.json", record)
            self.terminal = record
        except BaseException:
            self.session.poisoned = True
            raise ImageContractError("image_durability") from None

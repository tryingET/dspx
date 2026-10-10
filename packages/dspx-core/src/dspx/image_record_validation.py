"""Read-only custody views and reconciliation, artifact chains and receipt routing."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass, replace
from typing import Any, cast

from .image_admission import ImageContractError, hash_value, require


def link_window(root_fd: int, names: list[str]) -> dict[str, tuple[int, int]]:
    """Records whose publication stopped between `os.link` and `os.unlink`.

    Such a record has exactly two links, the other its own `.pending-<uuid4>` twin: its
    bytes were written and fsynced, but the publisher never confirmed it. Read-only;
    only reconciliation reads it, never as settled. Any other extra link is refused.
    """
    from .image_records import residue

    try:
        rows = {name: os.lstat(name, dir_fd=root_fd) for name in names}
    except OSError:
        raise ImageContractError("image_custody") from None
    pairs = {
        name: (row.st_dev, row.st_ino)
        for name, row in rows.items()
        if stat.S_ISREG(row.st_mode) and row.st_nlink == 2 and name != "lock"
    }
    twins = {pair for name, pair in pairs.items() if residue(name)}
    return {
        name: pair
        for name, pair in pairs.items()
        if not residue(name) and pair in twins
    }


@dataclass(frozen=True, slots=True)
class _ReadOnlySource:
    source: dict[str, object]


@dataclass(frozen=True, slots=True)
class ReadOnlyCustody:
    """Caller-anchored, payload-free view of a spent root; never a dispatch handle."""

    root_fd: int
    admission: Any
    context: _ReadOnlySource
    manifest_sha256: str
    ready_raw: bytes | None  # None: claimed but never ready (reconciliation only)

    def _scan(self):
        from .image_records import scan

        require(self.ready_raw is not None, "image_custody")
        return scan(self, allow_closure=True)

    @property
    def record(self):
        return self.admission.record

    @property
    def binding(self):
        return self.record["custody"]


def read_only_custody(
    custody_fd: int,
    *,
    admission_raw: bytes,
    source_raw: bytes,
    manifest_raw: bytes,
    unready: bool = False,
) -> ReadOnlyCustody:
    from .image_admission import (
        ImageAdmission,
        closed,
        digest,
        parse_json,
        validate_source,
    )
    from .image_records import _READY, list_root, private_root, read_record, residue

    root = private_root(custody_fd)
    admission = ImageAdmission(
        admission_raw, digest("admission-v2", parse_json(admission_raw))
    )
    record = admission.record
    source = validate_source(parse_json(source_raw))
    manifest = closed(
        parse_json(manifest_raw),
        "schema_version source_package_sha256 admission_sha256 marker_entries",
    )
    require(
        manifest["schema_version"] == "dspx-image-input-manifest-v2"
        # ubs:ignore -- public sha256 commitment, not a secret
        and manifest["source_package_sha256"] == digest("source-v1", source)
        and manifest["admission_sha256"] == admission.sha256
        and record["source_package_sha256"] == manifest["source_package_sha256"],
        "image_custody",
    )
    view = ReadOnlyCustody(
        custody_fd,
        admission,
        _ReadOnlySource(source),
        digest("manifest-v2", manifest),
        None,
    )
    names = list_root(custody_fd)
    require(len(names) <= 131, "image_custody")  # the scan's bound, before any stat
    if unready and (
        "ready.json" not in names or "ready.json" in link_window(custody_fd, names)
    ):
        # The initializer died between its O_EXCL claim and a settled ready.json, so
        # nothing could dispatch. Names and inode metadata only: no record (not even
        # a complete ready.json inside its link window) is read or trusted.
        require(
            {name for name in names if not residue(name)} - {"ready.json"} == {"lock"}
            and (root.st_dev, root.st_ino)
            == (view.binding["root_dev"], view.binding["root_ino"]),
            "image_custody",
        )
        try:
            lock = os.lstat("lock", dir_fd=custody_fd)
        except OSError:
            raise ImageContractError("image_custody") from None
        require(
            stat.S_ISREG(lock.st_mode)
            and stat.S_IMODE(lock.st_mode) == 0o600
            and (lock.st_uid, lock.st_nlink, lock.st_size) == (os.geteuid(), 1, 0),
            "image_custody",
        )
        return view
    require("ready.json" in names, "image_custody")
    ready_raw = read_record(custody_fd, "ready.json")
    ready = closed(parse_json(ready_raw), _READY)
    require(
        all(ready[key] == value for key, value in record["custody"].items())
        and ready["admission_sha256"] == admission.sha256
        # ubs:ignore -- public sha256 commitment, not a secret
        and ready["input_manifest_sha256"] == digest("manifest-v2", manifest)
        # Worker binding (custody ready v2): a distinct child, its deadline and grant.
        and ready["schema_version"] == "dspx-image-custody-ready-v2"
        and type(ready["worker_pid"]) is int
        and ready["worker_pid"] not in {0, ready["creator_pid"]}
        and type(ready["worker_deadline_ns"]) is int
        and ready["worker_deadline_ns"] > 0
        and str(ready["worker_start_identity"]).isdecimal()
        and hash_value(ready["grant_sha256"]),
        "image_custody",
    )
    return replace(view, ready_raw=ready_raw)


def reconcile(view: ReadOnlyCustody) -> dict[str, Any]:
    """Read-only settlement: an intent without its terminal is effect_indeterminate.

    Nothing is written, so no terminal is minted for an outcome nobody recorded: an
    absent terminal keeps an unknown dispatch count and is never success. Own
    publication residue is counted, never trusted as a record; a complete residue
    terminal for the same attempt with another disposition (the worker reclassified an
    unconfirmed publication) contradicts the linked one, which is then never success.
    A record still linked to its own pending twin (publication killed between link and
    unlink) is read, never settled: its attempt is effect_indeterminate with an
    unknown dispatch count, and such a closure is not present. A root claimed but
    never ready reports no attempt; nothing in it is read.
    The root stays spent; no session, allowance or retry derives from this report.
    """
    from .image_admission import parse_json, sha
    from .image_records import list_root, read_record, residue, scan

    names = list_root(view.root_fd)
    require(len(names) <= 131, "image_custody")  # the scan's bound, before any read
    window = link_window(view.root_fd, names)
    ready = view.ready_raw is not None
    require(  # an unready view is re-checked on this listing, not trusted from before
        ready
        or {name for name in names if not residue(name)} - {"ready.json"} == {"lock"}
        and ("ready.json" not in names or "ready.json" in window),
        "image_custody",
    )
    claims = set()
    for name in filter(residue, names if ready else ()):
        try:
            row = parse_json(read_record(view.root_fd, name), limit=65_536)
        except (ImageContractError, OSError):
            continue  # empty or partial residue proves nothing
        if type(row) is not dict:
            continue
        claim = (row.get("attempt_id"), row.get("provider_disposition"))
        if row.get("schema_version") == "dspx-image-dispatch-terminal-v1" and all(
            type(value) is str for value in claim
        ):
            claims.add(claim)
    attempts = []
    rows = []  # a root that never got ready has no attempt; no record is read
    if ready:
        rows = scan(
            view, allow_open=True, allow_closure=True, allow_residue=True, window=window
        )
    for intent, terminal in rows:
        ordinal = intent["attempt_ordinal"]
        recorded = None if terminal is None else terminal["provider_disposition"]
        contradicted = any(
            attempt == intent["attempt_id"] and claim != recorded
            for attempt, claim in claims
        )
        intent_name = f"intent-{ordinal}.json"
        terminal_name = f"terminal-{ordinal}.json"
        unsettled = intent_name in window or terminal_name in window
        settled = None if unsettled else terminal  # only a settled terminal counts
        attempts.append(
            {
                "attempt_ordinal": ordinal,
                "attempt_id": intent["attempt_id"],
                "intent_sha256": sha(
                    read_record(view.root_fd, intent_name, twin=window.get(intent_name))
                ),
                "terminal_sha256": None
                if terminal is None
                else sha(
                    read_record(
                        view.root_fd, terminal_name, twin=window.get(terminal_name)
                    )
                ),
                "provider_disposition": "effect_indeterminate"
                if settled is None or contradicted
                else recorded,
                "dispatch_count": None
                if settled is None
                else settled["dispatch_count"],
                "terminal_contradicted": terminal is not None and contradicted,
                "publication_unsettled": unsettled,
            }
        )
    # Worst attempt wins; a completion is never claimed for a root that never dispatched.
    effects = {row["provider_disposition"] for row in attempts}
    effect = "none" if not attempts else "completed_success"
    for worse in ("preflight_rejected", "completed_failure", "effect_indeterminate"):
        effect = worse if worse in effects else effect
    return {
        "schema_version": "dspx-image-custody-reconciliation-v1",
        "status": "spent",
        "dispatch_available": False,
        "ready_present": ready,
        "planned_dispatches": len(view.record["request_plan"]),
        "consumed_dispatches": len(attempts),
        "publication_residue": sum(residue(name) for name in names),
        "closure_present": "closure.json" in names and "closure.json" not in window,
        "terminal_effect": effect,
        "attempts": attempts,
    }


def reconcile_image_custody(
    custody_fd: int, *, admission_raw: bytes, source_raw: bytes, manifest_raw: bytes
) -> dict[str, Any]:
    """Parent-side report for a root whose worker is settled; reads records only."""
    return reconcile(
        read_only_custody(
            custody_fd,
            admission_raw=admission_raw,
            source_raw=source_raw,
            manifest_raw=manifest_raw,
            unready=True,
        )
    )


_ARTIFACT_KEYS = {
    "runtime_image_inputs.json": "schema_version source_package_sha256 input_manifest_sha256 input_shape_sha256 plain_text_commitments",
    "image_behavior_results.json": "schema_version caller_run_id candidate_manifest_sha256 source_package_sha256 execution_status local_outcome output_commitments quality_status failure_code",
    "image_program_runtime_traces.json": "schema_version caller_run_id predictor_plan_ordinals attempt_ids",
    "image_oracle_evidence.json": "schema_version caller_run_id source_package_sha256 artifact_manifest_sha256 authority",
    "runtime_image_episode.json": "schema_version caller_run_id candidate_manifest_sha256 source_package_sha256 input_manifest_sha256 admission_sha256 effect_evidence artifact_manifest_sha256 local_outcome non_authority",
    "runtime_image_episode.json.meta.json": "schema_version run_kind caller_run_id candidate_manifest_sha256 source_package_sha256 admission_sha256 input_manifest_sha256 content_artifact_manifest_sha256 effect_evidence local_outcome replay_policy non_authority",
    "direct_image_run_receipt.json": "schema_version run_kind caller_run_id candidate_manifest_sha256 source_package_sha256 admission_sha256 input_manifest_sha256 content_artifact_manifest_sha256 effect_evidence local_outcome replay_policy non_authority",
}


def validate_artifact_chain(
    fd: int,
    published_sha256: str,
    session,
    source_raw: bytes,
    manifest_raw: bytes,
    output_slots: int,
) -> str:
    """The same exact closed chain is checked BEFORE immutable closure and on readback."""
    from .image_admission import canonical, closed, digest, parse_json
    from .image_artifacts import (
        _check_manifest,
        _entry,
        _read,
        _SCHEMAS,
        _NON_AUTHORITY,
        _REPLAY,
    )
    from .image_records import list_root
    from .image_effects import image_effect_envelope
    from .image_input_contract import reject_output

    require(type(output_slots) is int and 0 < output_slots <= 4096, "image_custody")
    caller = session.binding["caller_run_id"]
    source = parse_json(source_raw)
    manifest = parse_json(manifest_raw)
    published = _check_manifest(
        fd, "image_published_artifacts.json", published_sha256, caller
    )
    entries = published["artifacts"]
    names = {entry["name"] for entry in entries}
    receipts = names & {
        "runtime_image_episode.json.meta.json",
        "direct_image_run_receipt.json",
    }
    require(len(receipts) == 1, "image_custody")
    receipt_name = next(iter(receipts))
    episode = receipt_name == "runtime_image_episode.json.meta.json"
    output_names = [f"image_output_{slot:06d}.json" for slot in range(output_slots)]
    content_names = {
        "image_source_package.json",
        "image_input_manifest.json",
        "runtime_image_inputs.json",
        "image_behavior_results.json",
        "image_program_runtime_traces.json",
        *output_names,
    }
    expected_names = content_names | {
        "image_content_artifacts.json",
        "image_oracle_evidence.json",
        receipt_name,
    }
    if episode:
        expected_names.add("runtime_image_episode.json")
    require(
        names == expected_names
        and set(list_root(fd)) == expected_names | {"image_published_artifacts.json"},
        "image_custody",
    )
    by_name = {entry["name"]: entry for entry in entries}
    content_sha = by_name["image_content_artifacts.json"]["sha256"]
    content = _check_manifest(fd, "image_content_artifacts.json", content_sha, caller)
    require(
        {entry["name"] for entry in content["artifacts"]} == content_names
        and all(entry == by_name[entry["name"]] for entry in content["artifacts"]),
        "image_custody",
    )
    require(
        _read(fd, "image_source_package.json") == source_raw
        and _read(fd, "image_input_manifest.json") == manifest_raw
        # ubs:ignore -- public sha256 commitment, not a secret
        and digest("source-v1", source) == session.record["source_package_sha256"]
        # ubs:ignore -- public sha256 commitment, not a secret
        and digest("manifest-v2", manifest) == session.manifest_sha256,
        "image_custody",
    )
    rows = session._scan()
    require(
        bool(rows)
        and len(rows) == len(session.record["request_plan"])
        and all(
            term is not None
            and term["provider_disposition"] == "completed_success"
            and term["typed_finalization_completed"] is True
            for _, term in rows
        ),
        "image_custody",
    )
    envelope = image_effect_envelope(session)
    expected_common = {
        "caller_run_id": caller,
        "source_package_sha256": session.record["source_package_sha256"],
        "candidate_manifest_sha256": session.record["candidate_manifest_sha256"],
        "admission_sha256": session.admission.sha256,
        "input_manifest_sha256": session.manifest_sha256,
        "local_outcome": "completed",
    }
    subjects = {}
    for name in expected_names - content_names - {"image_content_artifacts.json"} | (
        content_names
        - {"image_source_package.json", "image_input_manifest.json", *output_names}
    ):
        row = closed(parse_json(_read(fd, name)), _ARTIFACT_KEYS[name])
        require(row["schema_version"] == _SCHEMAS[name], "image_custody")
        for key, value in expected_common.items():
            if key in row:
                require(canonical(row[key]) == canonical(value), "image_custody")
        if "effect_evidence" in row:
            require(
                canonical(row["effect_evidence"]) == canonical(envelope),
                "image_custody",
            )
        if "non_authority" in row:
            require(
                canonical(row["non_authority"])
                == canonical(dict.fromkeys(_NON_AUTHORITY.split(), False)),
                "image_custody",
            )
        if "artifact_manifest_sha256" in row:
            require(row["artifact_manifest_sha256"] == content_sha, "image_custody")
        subjects[name] = row
    projected = subjects["runtime_image_inputs.json"]
    require(
        projected["input_shape_sha256"] == source["input_shape_sha256"]
        and canonical(projected["plain_text_commitments"])
        == canonical(source["plain_text_slots"]),
        "image_custody",
    )
    traces = subjects["image_program_runtime_traces.json"]
    require(
        traces["predictor_plan_ordinals"]
        == [intent["plan_ordinal"] for intent, _ in rows]
        and traces["attempt_ids"] == [intent["attempt_id"] for intent, _ in rows],
        "image_custody",
    )
    behavior = subjects["image_behavior_results.json"]
    require(
        behavior["execution_status"] == "executed"
        and behavior["quality_status"] == "not_evaluated"
        and behavior["failure_code"] is None,
        "image_custody",
    )
    total = 0
    commitments = []
    for slot, name in enumerate(output_names):
        raw = _read(fd, name)
        output = parse_json(raw, limit=4_194_304)
        require(
            type(output) is dict
            and set(output)
            == {"schema_version", "caller_run_id", "field_slot", "value"}
            and output["schema_version"] == "program-image-output-v1"
            and output["caller_run_id"] == caller
            and type(output["field_slot"]) is int
            and output["field_slot"] == slot,
            "image_custody",
        )
        # Read-only verification has no source payloads. Generic deny scanning is
        # still mandatory; publication additionally scans against actual source bytes.
        reject_output(output["value"], None)
        total += len(raw)
        entry = _entry(fd, name)
        commitments.append(
            {
                "field_slot": slot,
                "sha256": entry["sha256"],
                "byte_count": entry["byte_count"],
            }
        )
    require(
        total <= session.record["limits"]["max_output_artifact_bytes"]
        and canonical(behavior["output_commitments"]) == canonical(commitments),
        "image_custody",
    )
    receipt = subjects[receipt_name]
    require(
        receipt["content_artifact_manifest_sha256"] == content_sha
        and canonical(receipt["replay_policy"]) == canonical(_REPLAY)
        and receipt["run_kind"]
        == ("program-runtime-image" if episode else "generated-direct-image")
        and subjects["image_oracle_evidence.json"]["authority"]
        == "local_non_authoritative",
        "image_custody",
    )
    return content_sha


_IMAGE_RUN_KINDS = frozenset({"program-runtime-image", "generated-direct-image"})
# Image-only receipt rows (the closed image receipt minus its kind and schema): a v1
# receipt carrying any of them is mixed, never v1.
_IMAGE_ROWS: frozenset[str] = frozenset(
    _ARTIFACT_KEYS["direct_image_run_receipt.json"].split()
) - {"schema_version", "run_kind"}


def is_image_receipt(receipt: object) -> bool:
    """Image-domain receipts never enter the ordinary text check or replay path."""
    if type(receipt) is not dict:
        return False
    row = cast(dict[str, Any], receipt)
    return (
        row.get("run_kind") in _IMAGE_RUN_KINDS
        or str(row.get("schema_version", "")).startswith(
            ("dspx-image-", "generated-dspy-direct-image")
        )
        or not _IMAGE_ROWS.isdisjoint(row)
    )


def image_receipt_refusal(code: str, *, replay: bool = False) -> dict[str, object]:
    """Fixed report: no path, receipt value, anchor attribute or exception text."""
    report: dict[str, object] = {"status": "invalid", "error_codes": [code]}
    if replay:  # historical key order of the replay refusal
        report["execution"] = {"attempted": False, "strategy": None}
    report.update(execution_reproduction=False, dispatch_available=False)
    return report

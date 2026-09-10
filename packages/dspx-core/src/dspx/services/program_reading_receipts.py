"""Local synthetic receipts; not AK5511's historical graph verifier.

Independent custody binds receipt hash, request, manifest and native episode/index.
Consume captured bytes; bundle-selected hashes are not trusted custody.
Owner callbacks are not OS authority or an AK5457 publication lock.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any, Callable, Mapping

from dspx.services.program_reading_contracts import (
    CEILING,
    FAMILIES,
    MAX_BYTES,
    ExpectedReading,
    canonical_bytes,
    digest,
    check_current,
    native_input_bytes,
    native_output_bytes,
    raw_hash,
    require,
    strict_json,
    validate_inputs,
    validate_outputs,
    _bound,
    _locator,
    _text,
)

LEVEL_FIELDS = {
    key: tuple(fields.split())
    for key, fields in {
        "L1": "paraphrase",
        "L2": "main_point elaboration example analogy example_origin",
        "L3": "purpose question information concepts assumptions inferences implications point_of_view",
        "L4": "clarity accuracy precision relevance depth breadth logic significance fairness",
        "L5": "question simulated_answer uncertainty",
        "L6": "application limits counterexample observable_test recipient uncertainty",
    }.items()
}


def validate_reading_packet(
    parsed: dict, source: dict, inputs: Mapping[str, str], expected: ExpectedReading
) -> None:
    """Closed structural schemas, not semantic acceptance or arbitrary payloads."""
    common = {"request_id", "source_sha256", "reading_intent_binding"}
    flags = {**CEILING, "canonical_mutation_performed": False}
    containers = set(
        "reading_intent_binding evidence contrary_evidence paragraphs levels operations rows note_campaign_review_packet raw_artifact_views".split()
    )
    frame_fields = "purpose_in_source whole_map selected_parts whole_synthesis counterevidence contrary_evidence levels"
    extras = {
        "frame": frame_fields,
        "level": "content operations status reason simulation added_extension",
        "campaign": "candidate_name recommended_next_step",
    }

    def bound(value, fields):
        _bound(value, expected)
        require(
            set(value) <= common | set(flags) | set(fields.split()),
            "unsupported nested structure",
        )
        for key, item in value.items():
            if key in flags:
                require(
                    type(item) is type(flags[key]) and item == flags[key],
                    "contradictory authority flag",
                )
            elif key in {"simulation", "added_extension"}:
                require(item is True, "invalid level attribution")
            elif key not in containers:
                require(_text(item), "nonempty scalar field required")

    def evidence(value):
        require(isinstance(value, dict), "missing evidence")
        fields = (
            "status reason"
            if value.get("status") == "insufficient_evidence"
            else "source_ref markdown_sha256 start end excerpt excerpt_sha256 quotation_status page section paragraph"
        )
        require(set(value) == set(fields.split()), "unsupported evidence structure")
        _locator(value, source, inputs["marker_markdown"])

    def rows(value, role, depth=0):
        require(
            isinstance(value, list) and bool(value) and depth < 16,
            "nonempty bounded descendant rows required",
        )
        for item in value:
            row(item, role, depth)

    def row(value, role, depth=0, level=None):
        bound(
            value,
            "section_id evidence title markdown paragraphs " + extras.get(role, ""),
        )
        required = (
            "candidate_name recommended_next_step"
            if role == "campaign"
            else "section_id evidence"
        )
        if role == "level":
            required = "content evidence"
        if role in {"draft", "paragraph"}:
            required += " title markdown" if role == "draft" else " markdown"
        if role == "frame":
            required += " " + frame_fields
        require(set(required.split()) <= set(value), "missing required row fields")
        if "section_id" in value:
            require(value["section_id"] in ids, "dangling section reference")
        for key in ("evidence", "contrary_evidence"):
            if key in value:
                evidence(value[key])
        if "paragraphs" in value:
            rows(value["paragraphs"], "paragraph", depth + 1)
        if role == "frame":
            require(
                isinstance(value["levels"], dict)
                and set(value["levels"]) == set(LEVEL_FIELDS),
                "original L1-L5 plus added L6 required",
            )
            for name, child in value["levels"].items():
                row(child, "level", depth + 1, name)
        if role == "level":
            if value.get("status") == "insufficient_evidence":
                require(_text(value.get("reason")), "incomplete level needs reason")
            if "operations" in value or value.get("status") != "insufficient_evidence":
                operations = value.get("operations")
                require(
                    isinstance(operations, dict)
                    and set(operations) == set(LEVEL_FIELDS[level])
                    and all(_text(v) for v in operations.values()),
                    "missing original reading operations",
                )
            for name, field in (("L5", "simulation"), ("L6", "added_extension")):
                if level == name:
                    require(
                        value.get(field) is True, "missing reading level attribution"
                    )

    sections = parsed["section_units_json"].get("rows")
    require(
        isinstance(sections, list) and all(isinstance(r, dict) for r in sections),
        "invalid sections",
    )
    ids = [r.get("section_id") for r in sections]
    require(
        all(_text(i) for i in ids) and len(set(ids)) == len(ids), "invalid section IDs"
    )
    for family, value in parsed.items():
        field = (
            "note_campaign_review_packet" if family == "review_packet_json" else "rows"
        )
        bound(value, field)
        require(
            value.get("canonical_mutation_performed") is False,
            "canonical mutation claim",
        )
        if field == "rows":
            role = {
                "distillation_frames_json": "frame",
                "wiki_note_drafts_json": "draft",
            }.get(family, "row")
            rows(value.get("rows"), role)
    packet = parsed["review_packet_json"].get("note_campaign_review_packet")
    bound(packet, "schema_version artifact_type packet_state raw_artifact_views")
    require(
        packet.get("schema_version") == "mobile-note-campaign-review-packet-v2"
        and packet.get("artifact_type") == "note_campaign_review_packet"
        and packet.get("packet_state") == "generated",
        "generated v2 packet required",
    )
    raw = packet.get("raw_artifact_views")
    require(
        isinstance(raw, dict)
        and set(raw) == {"candidate_notes", "campaign_rows", "downstream"},
        "unsupported packet views",
    )
    rows(raw["candidate_notes"], "draft")
    rows(raw["campaign_rows"], "campaign")
    downstream = raw["downstream"]
    require(
        isinstance(downstream, dict)
        and set(downstream)
        <= {"measurement_proposals", "paragraphs", "note_proposals"},
        "unsupported downstream structure",
    )
    for key, children in downstream.items():
        rows(children, "paragraph" if key == "paragraphs" else "draft")


SCHEMA = "dspx-program-reading-receipt-v1"
SIDECARS = (
    "runtime_inputs.json",
    "behavior_results.json",
    "program_runtime_traces.json",
    "manifest.json",
    "oracle_evidence.json",
    "runtime_episode.json",
    "runtime_episode.json.meta.json",
    "synthetic_requests.json",
    "synthetic_response.json",
)
CurrentIntent = Callable[[], dict[str, Any]]


def directory_fd(path: Path) -> int:
    """Walk absolute directories with O_NOFOLLOW, including every ancestor."""
    require(
        path.is_absolute() and ".." not in path.parts, "absolute confined root required"
    )
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = new
        return fd
    except BaseException:
        os.close(fd)
        raise


def capture(root: Path, relative: str) -> bytes:
    parts = Path(relative).parts
    require(
        bool(parts)
        and not Path(relative).is_absolute()
        and all(p not in {".", ".."} for p in parts)
        and str(Path(relative)) == relative,
        "unconfined relative reference",
    )
    directory = directory_fd(root)
    try:
        for part in parts[:-1]:
            new = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
            )
            os.close(directory)
            directory = new
        fd = os.open(
            parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
        )
        try:
            before = os.fstat(fd)
            require(
                stat.S_ISREG(before.st_mode)
                and before.st_nlink == 1
                and before.st_size <= MAX_BYTES,
                "not a bounded private regular file",
            )
            data = b""
            while len(data) <= MAX_BYTES:
                chunk = os.read(fd, min(65536, MAX_BYTES + 1 - len(data)))
                if not chunk:
                    break
                data += chunk
            after = os.fstat(fd)
            require(
                all(
                    getattr(before, key) == getattr(after, key)
                    for key in (
                        "st_dev",
                        "st_ino",
                        "st_size",
                        "st_mtime_ns",
                        "st_ctime_ns",
                    )
                )
                and len(data) == before.st_size,
                "file changed during capture",
            )
            return data
        finally:
            os.close(fd)
    finally:
        os.close(directory)


def exclusive_write(path: Path, raw: bytes) -> None:
    require(len(raw) <= MAX_BYTES, "file exceeds bound")
    directory = directory_fd(path.parent)
    try:
        fd = os.open(
            path.name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory,
        )
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(directory)


def _native_capture(
    root: Path,
    manifest_path: Path,
    expected: ExpectedReading,
    inputs: dict[str, str],
    native_episode_id: str,
) -> tuple[dict, dict, dict]:
    from dspx.services.program_runtime_episode import (
        load_validated_program_runtime_episode_bundle,
    )

    from dspx.services.program_reading_runtime import capture_candidate

    candidate_capture = capture_candidate(manifest_path)
    manifest_raw = candidate_capture[manifest_path.name]
    require(
        raw_hash(manifest_raw) == expected.candidate_manifest_sha256,
        "candidate hash mismatch",
    )
    manifest = strict_json(manifest_raw)
    fields = FAMILIES if expected.stage == "reading" else ("reading_proposal_json",)
    captured = {name: capture(root, name) for name in (*SIDECARS, *fields)}
    parsed = {
        name: strict_json(raw) for name, raw in captured.items() if name in SIDECARS
    }
    require(
        captured["runtime_inputs.json"] == native_input_bytes(inputs),
        "native input bytes mismatch",
    )
    episode = parsed["runtime_episode.json"]
    require(
        episode.get("runtime_episode_id") == native_episode_id
        and episode.get("execution_status") == "executed",
        "wrong/failed native episode",
    )
    require(
        set(episode.get("output_files", [])) == set(fields),
        "native output references mismatch",
    )
    behavior = parsed["behavior_results.json"]
    rows = behavior.get("examples")
    require(
        isinstance(rows, list)
        and len(rows) == 1
        and type(rows[0].get("index")) is int
        and rows[0]["index"] == 0
        and rows[0].get("inputs") == inputs,
        "wrong native example/index/input",
    )
    observed = rows[0]["observed_outputs"]
    response = parsed["synthetic_response.json"]
    require(
        {k: v for k, v in response.items() if k != "reasoning"} == observed,
        "transport/output mismatch",
    )
    outputs = validate_outputs(observed, inputs, expected)
    for name in fields:
        require(
            captured[name] == native_output_bytes(observed[name]),
            "raw output bytes mismatch",
        )
    provider = episode.get("provider", {})
    metadata = provider.get("metadata", {})
    require(metadata.get("provider") == "stub", "nonstub evidence")
    effects = provider.get("effect_evidence", {})
    require(
        effects.get("attempt_total") == 1,
        "expected exactly one synthetic transport attempt",
    )
    bundle = load_validated_program_runtime_episode_bundle(
        runtime_episode_path=root / "runtime_episode.json",
        expected_manifest_path=manifest_path,
        expected_manifest=manifest,
        expected_manifest_sha256=expected.candidate_manifest_sha256.removeprefix(
            "sha256:"
        ),
    )
    require(
        all(capture(root, name) == raw for name, raw in captured.items())
        and capture_candidate(manifest_path) == candidate_capture,
        "native files changed during readback",
    )
    require(
        bundle.runtime_episode == episode and bundle.behavior_results == behavior,
        "readback differs from captured bytes",
    )
    hashes = {name: raw_hash(raw) for name, raw in captured.items()}
    readback = {
        "runtime_episode_id": native_episode_id,
        "index": 0,
        "runtime_episode_raw_sha256": "sha256:" + bundle.runtime_episode_sha256,
        "behavior_results_raw_sha256": "sha256:" + bundle.behavior_results_sha256,
        "native_receipt_raw_sha256": "sha256:" + bundle.runtime_receipt_sha256,
        "validator": "load_validated_program_runtime_episode_bundle",
    }
    return outputs, hashes, readback


def write_reading_receipt(
    *,
    root: Path,
    manifest_path: Path,
    expected: ExpectedReading,
    inputs: dict[str, str],
    native_episode_id: str,
    current_intent: CurrentIntent | None,
) -> str:
    """Wrapper-generated receipt hash returned for separate trusted owner custody."""
    intent = validate_inputs(inputs, expected)
    outputs, hashes, readback = _native_capture(
        root, manifest_path, expected, inputs, native_episode_id
    )
    check_current(current_intent, intent)
    readback_raw = canonical_bytes(readback) + b"\n"
    exclusive_write(root / "reading_readback.json", readback_raw)
    receipt = {
        "schema_version": SCHEMA,
        **CEILING,
        "expected": expected.payload(),
        "native_episode_id": native_episode_id,
        "native_index": 0,
        "raw_file_sha256": hashes,
        "output_parsed_sha256": {
            name: digest(value) for name, value in outputs.items()
        },
        "readback_raw_sha256": raw_hash(readback_raw),
        "readback_parsed_sha256": digest(readback),
    }
    raw = canonical_bytes(receipt) + b"\n"
    exclusive_write(root / "reading_receipt.json", raw)
    return raw_hash(raw)


def consume_reading_receipt(
    *,
    root: Path,
    trusted_receipt_sha256: str,
    manifest_path: Path,
    expected: ExpectedReading,
    inputs: dict[str, str],
    expected_native_episode_id: str,
    expected_native_index: int,
    current_intent: CurrentIntent | None,
) -> dict:
    """Consume local synthetic output, never create a review-eligible publication.

    trusted_receipt_sha256 must arrive through independent owner custody, NOT by
    reading a hash selected by this bundle. Start/end callbacks are observation,
    not an atomic publication lock; AK5457 must lock and recheck before publishing.
    """
    intent = validate_inputs(inputs, expected)
    check_current(current_intent, intent)
    require(
        type(expected_native_index) is int and expected_native_index == 0,
        "exact native index 0 required",
    )
    raw = capture(root, "reading_receipt.json")
    require(raw_hash(raw) == trusted_receipt_sha256, "trusted receipt hash mismatch")
    receipt = strict_json(raw)
    require(
        receipt.get("schema_version") == SCHEMA
        and receipt.get("expected") == expected.payload()
        and receipt.get("native_episode_id") == expected_native_episode_id
        and type(receipt.get("native_index")) is int
        and receipt["native_index"] == 0,
        "receipt independent identity mismatch",
    )
    require(
        all(
            receipt.get(k) == v and type(receipt.get(k)) is type(v)
            for k, v in CEILING.items()
        ),
        "receipt claim escalation",
    )
    outputs, hashes, readback = _native_capture(
        root, manifest_path, expected, inputs, expected_native_episode_id
    )
    require(
        receipt.get("raw_file_sha256") == hashes
        and receipt.get("output_parsed_sha256")
        == {k: digest(v) for k, v in outputs.items()},
        "receipt file/output hash mismatch",
    )
    readback_raw = capture(root, "reading_readback.json")
    require(
        raw_hash(readback_raw) == receipt.get("readback_raw_sha256")
        and strict_json(readback_raw) == readback
        and digest(readback) == receipt.get("readback_parsed_sha256"),
        "readback hash mismatch",
    )
    require(
        capture(root, "reading_receipt.json") == raw,
        "receipt changed during consumption",
    )
    check_current(current_intent, intent)
    return outputs

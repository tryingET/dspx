"""Synthetic reading contracts; no semantic acceptance, puzzle registration or approval.
The Obsidian owner supplies immutable working-reading-intent-v1 generations.
AK5457 owns publication locks, current-owner custody and review admission.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Callable, Mapping

MAX_BYTES = 1_000_000
HASH_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
FAMILIES = (
    "section_units_json",
    "distillation_frames_json",
    "evidence_cards_json",
    "merge_create_proposals_json",
    "review_packet_json",
    "artifact_contract_manifest_json",
    "frontmatter_plans_json",
    "wiki_note_drafts_json",
)
PDF_INPUTS = (
    "source_package_manifest_json",
    "marker_markdown",
    "existing_wiki_index_json",
    "declared_output_root",
)
READING_INPUTS = PDF_INPUTS + (
    "puzzle_set_snapshot_json",
    "working_reading_intent_json",
    "reading_intent_binding_json",
    "producer_context_json",
)
PROPOSAL_INPUTS = PDF_INPUTS + ("puzzle_set_snapshot_json", "producer_context_json")
CEILING = {
    "claim_ceiling": "local_synthetic_execution_only",
    "origin": "injected_synthetic_transport/stub",
    "provider_output_authentication": "not_established",
    "quality_acceptance": "unknown",
    "canonical_apply_allowed": False,
    "review_eligible": False,
    "oracle_invocation": False,
    "oracle_index": False,
    "oracle_semantic": False,
    "publication": False,
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def strict_json(raw: bytes | str) -> Any:
    data = raw.encode("utf-8") if isinstance(raw, str) else raw
    require(len(data) <= MAX_BYTES, "JSON exceeds bound")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result

    def invalid(_: str) -> None:
        raise ValueError("nonfinite JSON")

    try:
        value = json.loads(
            data.decode("utf-8"), object_pairs_hook=pairs, parse_constant=invalid
        )
        canonical_bytes(value)  # Also rejects exponent overflow (1e999).
        return value
    except (UnicodeError, RecursionError) as exc:
        raise ValueError("invalid bounded JSON") from exc


def canonical_bytes(value: Any) -> bytes:
    try:
        data = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (RecursionError, UnicodeError) as exc:
        raise ValueError("invalid JSON value") from exc
    require(len(data) <= MAX_BYTES, "JSON exceeds bound")
    return data


def raw_hash(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def digest(value: Any) -> str:
    return raw_hash(canonical_bytes(value))


def intent_hash(intent: Mapping[str, Any]) -> str:
    """Hash ALL owner fields except hash, without normalizing or pruning."""
    return digest({key: value for key, value in intent.items() if key != "hash"})


def native_input_bytes(inputs: Mapping[str, Any]) -> bytes:
    payload = {"inputs": inputs}
    text = json.dumps(
        payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False
    )
    return (text + "\n").encode("utf-8")


def native_output_bytes(value: Any) -> bytes:
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    return (value.rstrip() + "\n").encode("utf-8")


def identity(intent: Mapping[str, Any]) -> dict[str, Any]:
    return {key: intent[key] for key in ("intent_id", "revision", "hash")}


def check_current(
    current: Callable[[], dict[str, Any]] | None, intent: dict | None
) -> None:
    if intent is None:
        require(current is None, "proposal does not approve a current intent")
        return
    if not callable(current):
        raise ValueError("trusted current-intent callback required")
    observed = strict_json(canonical_bytes(current()))
    require(
        canonical_bytes(observed) == canonical_bytes(intent),
        "stale completion/current intent mismatch; no rebinding",
    )


def stub_only_environment(env: Mapping[str, str] | None = None) -> None:
    """Delegate to the execution boundary without changing the environment."""
    from dspx.services.program_reading_runtime import stub_only_environment as check

    check(env)


@dataclass(frozen=True)
class ExpectedReading:
    """Independent owner inputs, never populated from evidence or model echoes."""

    stage: str
    request_id: str
    source_ref: str
    source_sha256: str
    puzzle_snapshot_sha256: str
    candidate_manifest_sha256: str
    input_raw_sha256: str
    reading_intent_binding: dict[str, Any] | None

    def payload(self) -> dict[str, Any]:
        return asdict(self)

    def validate(self) -> None:
        for key in (
            "source_sha256",
            "puzzle_snapshot_sha256",
            "candidate_manifest_sha256",
            "input_raw_sha256",
        ):
            value = getattr(self, key)
            require(
                isinstance(value, str) and HASH_PATTERN.fullmatch(value) is not None,
                "invalid expected hash",
            )
        if self.stage == "reading":
            binding = self.reading_intent_binding
            require(
                isinstance(binding, dict)
                and set(binding) == {"intent_id", "revision", "hash"}
                and type(binding["revision"]) is int
                and binding["revision"] > 0
                and _text(binding["intent_id"])
                and isinstance(binding["hash"], str)
                and HASH_PATTERN.fullmatch(binding["hash"]) is not None,
                "invalid expected binding",
            )


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def snapshots(
    inputs: Mapping[str, Any], expected: ExpectedReading
) -> tuple[dict, dict]:
    source = strict_json(inputs["source_package_manifest_json"])
    puzzles = strict_json(inputs["puzzle_set_snapshot_json"])
    require(
        isinstance(source, dict) and source.get("synthetic") is True,
        "caller-supplied synthetic source required",
    )
    require(
        isinstance(puzzles, dict) and puzzles.get("synthetic") is True,
        "caller-supplied synthetic puzzle snapshot required",
    )
    require(source.get("source_ref") == expected.source_ref, "source identity mismatch")
    require(digest(source) == expected.source_sha256, "source hash mismatch")
    require(
        digest(puzzles) == expected.puzzle_snapshot_sha256, "puzzle snapshot mismatch"
    )
    require(
        source.get("markdown_sha256") == raw_hash(inputs["marker_markdown"].encode()),
        "source markdown hash mismatch",
    )
    rows = puzzles.get("puzzles")
    require(
        isinstance(rows, list)
        and all(
            isinstance(r, dict)
            and _text(r.get("puzzle_id"))
            and _text(r.get("question"))
            for r in rows
        ),
        "invalid puzzle snapshot",
    )
    require(len({r["puzzle_id"] for r in rows}) == len(rows), "duplicate puzzles")
    return source, puzzles


def validate_inputs(
    inputs: Mapping[str, Any], expected: ExpectedReading
) -> dict | None:
    expected.validate()
    require(expected.stage in {"proposal", "reading"}, "invalid stage")
    require(
        _text(expected.request_id) and _text(expected.source_ref),
        "missing expected identity",
    )
    fields = READING_INPUTS if expected.stage == "reading" else PROPOSAL_INPUTS
    require(set(inputs) == set(fields), "declared inputs mismatch")
    require(all(isinstance(v, str) for v in inputs.values()), "inputs must be strings")
    require(
        raw_hash(native_input_bytes(inputs)) == expected.input_raw_sha256,
        "input bytes mismatch",
    )
    source, puzzles = snapshots(inputs, expected)
    require(
        inputs["declared_output_root"] == "synthetic-review-only",
        "no external output destination allowed",
    )
    require(
        strict_json(inputs["existing_wiki_index_json"])
        == {"synthetic": True, "notes": []},
        "only empty synthetic wiki index admitted",
    )
    context = strict_json(inputs["producer_context_json"])
    require(
        context
        == {
            "request_id": expected.request_id,
            "synthetic": True,
            "source_sha256": expected.source_sha256,
            "puzzle_snapshot_sha256": expected.puzzle_snapshot_sha256,
        },
        "producer context mismatch",
    )
    if expected.stage == "proposal":
        require(
            expected.reading_intent_binding is None,
            "proposal cannot bind approved intent",
        )
        return None
    intent = strict_json(inputs["working_reading_intent_json"])
    binding = strict_json(inputs["reading_intent_binding_json"])
    require(isinstance(intent, dict), "working intent must be an object")
    required = set(
        (
            "schema_version intent_id revision hash supersedes decision_id source_ref "
            "candidate_puzzle_ids candidate_provenance reviewed_input_hash mode "
            "selected_puzzle_id reader_purpose exception_reason authority consumer_status"
        ).split()
    )
    require(required <= set(intent), "incomplete owner working intent")
    require(
        intent["schema_version"] == "working-reading-intent-v1"
        and type(intent["revision"]) is int
        and intent["revision"] > 0,
        "invalid intent schema/revision",
    )
    require(
        _text(intent["intent_id"])
        and _text(intent["decision_id"])
        and _text(intent["reviewed_input_hash"]),
        "empty owner identity",
    )
    prior = intent["supersedes"]
    if intent["revision"] == 1:
        require(prior is None, "first intent cannot supersede another generation")
    else:
        require(
            isinstance(prior, dict)
            and set(prior) == {"intent_id", "revision", "hash"}
            and prior["intent_id"] == intent["intent_id"]
            and type(prior["revision"]) is int
            and prior["revision"] == intent["revision"] - 1
            and isinstance(prior["hash"], str)
            and HASH_PATTERN.fullmatch(prior["hash"]) is not None,
            "invalid superseded generation",
        )
    require(intent_hash(intent) == intent["hash"], "full working intent hash mismatch")
    require(
        binding == identity(intent) == expected.reading_intent_binding
        and type(binding.get("revision")) is int,
        "intent binding mismatch",
    )
    require(intent["source_ref"] == source["source_ref"], "intent source mismatch")
    require(
        intent["authority"] == "noncanonical_working_intent_only"
        and intent["consumer_status"] == "recorded_request_no_live_consumer",
        "intent authority escalation",
    )
    ids = intent["candidate_puzzle_ids"]
    require(
        isinstance(ids, list)
        and all(_text(i) for i in ids)
        and len(set(ids)) == len(ids)
        and set(ids) <= {r["puzzle_id"] for r in puzzles["puzzles"]},
        "invalid candidate membership",
    )
    provenance = intent["candidate_provenance"]
    require(
        isinstance(provenance, dict)
        and provenance.get("source_sha256") == expected.source_sha256
        and provenance.get("puzzle_snapshot_sha256") == expected.puzzle_snapshot_sha256,
        "candidate provenance mismatch",
    )
    mode = intent["mode"]
    require(
        mode in {"puzzle", "wiki_atlas_direct", "defer", "source_only"}, "invalid mode"
    )
    require(
        _text(intent["reader_purpose"]) and len(intent["reader_purpose"]) <= 8000,
        "reader purpose required",
    )
    require(
        isinstance(intent["exception_reason"], str)
        and len(intent["exception_reason"]) <= 8000,
        "invalid exception reason",
    )
    if mode == "puzzle":
        require(intent["selected_puzzle_id"] in ids, "selected puzzle not a candidate")
    else:
        require(
            intent["selected_puzzle_id"] is None and _text(intent["exception_reason"]),
            "non-puzzle mode requires null puzzle and reason",
        )
    return intent


def _bound(row: Any, expected: ExpectedReading) -> None:
    require(
        isinstance(row, dict)
        and "reading_intent_binding" in row
        and row.get("request_id") == expected.request_id
        and canonical_bytes(row.get("reading_intent_binding"))
        == canonical_bytes(expected.reading_intent_binding)
        and row.get("source_sha256") == expected.source_sha256,
        "dependent binding mismatch",
    )


def _locator(row: Any, source: dict, markdown: str) -> None:
    require(isinstance(row, dict), "locator must be an object")
    fields = (
        "status reason"
        if row.get("status") == "insufficient_evidence"
        else "source_ref markdown_sha256 start end excerpt excerpt_sha256 quotation_status page section paragraph"
    )
    require(set(row) == set(fields.split()), "unsupported evidence structure")
    if row.get("status") == "insufficient_evidence":
        require(_text(row.get("reason")), "insufficient evidence requires reason")
        return
    require(
        row.get("source_ref") == source["source_ref"]
        and row.get("markdown_sha256") == source["markdown_sha256"],
        "locator source mismatch",
    )
    start, end = row.get("start"), row.get("end")
    require(
        type(start) is int and type(end) is int and 0 <= start < end <= len(markdown),
        "invalid exact excerpt range",
    )
    require(
        row.get("excerpt") == markdown[start:end]
        and row.get("excerpt_sha256") == raw_hash(markdown[start:end].encode())
        and row.get("quotation_status") == "exact",
        "excerpt content/hash mismatch",
    )
    require(
        all(_text(row.get(k)) for k in ("page", "section", "paragraph")),
        "missing source locator",
    )


def validate_outputs(
    observed: Mapping[str, Any], inputs: Mapping[str, str], expected: ExpectedReading
) -> dict:
    source, puzzles = snapshots(inputs, expected)
    fields = FAMILIES if expected.stage == "reading" else ("reading_proposal_json",)
    require(set(observed) == set(fields), "missing or extra output families")
    require(
        all(isinstance(v, str) and v.strip() for v in observed.values()),
        "missing/malformed generated output",
    )
    parsed = {k: strict_json(v) for k, v in observed.items()}
    if expected.stage == "proposal":
        proposal = parsed["reading_proposal_json"]
        _bound(proposal, expected)
        known = {r["puzzle_id"] for r in puzzles["puzzles"]}

        def node(row, envelope=False, depth=0):
            # Alternatives recursively use the same existing-puzzle suggestion
            # schema. No authority fields or opaque nested payloads are admitted.
            fields = "rationale uncertainty alternatives evidence " + (
                "request_id source_sha256 reading_intent_binding disposition later_puzzle_linkage"
                if envelope
                else "candidate_id proposed_reader_purpose"
            )
            require(
                isinstance(row, dict)
                and set(row) == set(fields.split())
                and depth < 16,
                "unsupported proposal structure",
            )
            require(
                all(_text(row[k]) for k in ("rationale", "uncertainty"))
                and isinstance(row["alternatives"], list),
                "missing proposal reasoning",
            )
            if not envelope:
                require(
                    _text(row["candidate_id"])
                    and row["candidate_id"] in known
                    and _text(row["proposed_reader_purpose"]),
                    "invalid proposal alternative/purpose",
                )
            _locator(row["evidence"], source, inputs["marker_markdown"])
            for alternative in row["alternatives"]:
                node(alternative, depth=depth + 1)

        node(proposal, envelope=True)
        require(
            _text(proposal["disposition"])
            and proposal["disposition"]
            in {"candidates", "no_match", "direct", "defer"},
            "invalid proposal disposition",
        )
        linkage = proposal["later_puzzle_linkage"]
        fields = "source_sha256 puzzle_snapshot_sha256 candidate_puzzle_ids candidate_puzzle_suggestions"
        require(
            isinstance(linkage, dict) and set(linkage) == set(fields.split()),
            "unsupported proposal linkage",
        )
        require(
            linkage["source_sha256"] == expected.source_sha256
            and linkage["puzzle_snapshot_sha256"] == expected.puzzle_snapshot_sha256,
            "proposal provenance mismatch",
        )
        ids, rows = (
            linkage["candidate_puzzle_ids"],
            linkage["candidate_puzzle_suggestions"],
        )
        require(
            isinstance(ids, list)
            and all(_text(i) for i in ids)
            and isinstance(rows, list),
            "invalid proposal candidates",
        )
        require(
            len(set(ids)) == len(ids) and set(ids) <= known,
            "proposal invented a puzzle",
        )
        for row in rows:
            node(row)
        require(
            [r["candidate_id"] for r in rows] == ids, "proposal suggestions mismatch"
        )
        require(
            bool(ids) == (proposal["disposition"] == "candidates"),
            "forced/missing candidate",
        )
        return parsed
    from dspx.services.program_reading_receipts import validate_reading_packet

    validate_reading_packet(parsed, source, inputs, expected)
    return parsed

# summary: "Closed bounded image commitments and nominal parent authority; JSON is never permission."
# read_when:
#   - "Changing image source/admission identity, ceilings or trusted-parent bindings."

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
import re
import time
import uuid
from typing import Any, Final, cast

CEILINGS: Final = {
    "max_source_images": 6,
    "max_request_images": 6,
    "max_image_bytes": 8_388_608,
    "max_source_image_bytes": 25_165_824,
    "max_request_image_bytes": 25_165_824,
    "max_pixels": 16_000_000,
    "max_width": 8192,
    "max_height": 8192,
    "max_input_json_bytes": 41_943_040,
    "max_request_body_bytes": 41_943_040,
    "max_text_chars": 1_000_000,
    "max_messages": 256,
    "max_parts": 512,
    "max_depth": 16,
    "max_nodes": 4096,
    "max_response_bytes": 2_000_000,
    "max_output_chars": 1_000_000,
    "max_output_artifact_bytes": 4_194_304,
    "total_dispatch_allowance": 64,
}
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_CODES = frozenset(
    {
        "image_execution_unavailable",
        "image_generation_inputs_unsupported",
        "image_input_invalid",
        "image_budget",
        "image_decoder_unavailable",
        "image_decoder_invalid",
        "image_admission_invalid",
        "image_privacy",
        "signature_input_shape",
        "image_marker_invalid",
        "image_custody",
        "image_durability",
        "image_interruption",
        "image_spent",
        "image_finalization",
        "image_replay_unsupported",
        "image_parallel_unsupported",
    }
)


class ImageContractError(ValueError):
    """Fixed code only: no arbitrary value formatting or chained exception text."""

    def __init__(self, code: str = "image_input_invalid") -> None:
        self.code = code if code in _CODES else "image_input_invalid"
        super().__init__(self.code)


def require(condition: bool, code: str = "image_admission_invalid") -> None:
    if not condition:
        raise ImageContractError(code) from None


def bounded_tree(
    value: object,
    *,
    depth: int = 0,
    counter: list[int] | None = None,
    integers_only: bool = False,
    max_depth: int = 16,
    max_nodes: int = 4096,
) -> None:
    require(
        type(max_depth) is int
        and 0 < max_depth <= 16
        and type(max_nodes) is int
        and 0 < max_nodes <= 4096,
        "image_budget",
    )
    counter = [0] if counter is None else counter
    counter[0] += 1
    require(depth <= max_depth and counter[0] <= max_nodes, "image_budget")
    kind = type(value)
    require(
        kind in {dict, list, tuple, str, int, bool, type(None)}
        or (not integers_only and type(value) is float and math.isfinite(value)),
        "image_input_invalid",
    )
    if type(value) is dict:
        require(all(type(key) is str for key in value), "image_input_invalid")
        for item in value.values():
            bounded_tree(
                item,
                depth=depth + 1,
                counter=counter,
                integers_only=integers_only,
                max_depth=max_depth,
                max_nodes=max_nodes,
            )
    elif type(value) is list or type(value) is tuple:
        for item in value:
            bounded_tree(
                item,
                depth=depth + 1,
                counter=counter,
                integers_only=integers_only,
                max_depth=max_depth,
                max_nodes=max_nodes,
            )


def canonical(record: object) -> bytes:
    bounded_tree(record, integers_only=True)
    return json.dumps(
        record, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def digest(domain: str, record: object) -> str:
    return hashlib.sha256(
        domain.encode("ascii") + b"\0" + canonical(record)
    ).hexdigest()


def sha(raw: bytes) -> str:
    require(type(raw) is bytes, "image_input_invalid")
    return hashlib.sha256(raw).hexdigest()


def hash_value(value: object) -> bool:
    return type(value) is str and _HASH.fullmatch(value) is not None


def uuid_value(value: object) -> bool:
    if type(value) is not str:
        return False
    try:
        parsed = uuid.UUID(value)
        return parsed.version == 4 and str(parsed) == value
    except ValueError:
        return False


def closed(record: object, names: str) -> dict[str, Any]:
    require(type(record) is dict and set(record) == set(names.split()))
    bounded_tree(record, integers_only=True)
    return cast(dict[str, Any], record)


def positive(value: object, ceiling: int) -> bool:
    return type(value) is int and 0 < value <= ceiling


def parse_json(raw: bytes, *, limit: int = 41_943_040) -> Any:
    require(type(raw) is bytes and 0 < len(raw) <= limit, "image_budget")

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "image_input_invalid")
            result[key] = value
        return result

    try:
        result = json.loads(
            raw,
            object_pairs_hook=pairs,
            parse_constant=lambda _: require(False, "image_input_invalid"),
        )
        bounded_tree(result)
        return result
    except Exception:
        raise ImageContractError("image_input_invalid") from None


@dataclass(frozen=True, slots=True, repr=False)
class SyntheticImageAuthority:
    """Trusted test parent holds exact independently expected admission bytes."""

    expected_admission: bytes = field(repr=False)
    caller_expectation_sha256: str
    root_dev: int
    root_ino: int
    _used: list[bool] = field(default_factory=list, repr=False, compare=False)


@dataclass(frozen=True, slots=True, repr=False)
class LiveImageAuthority:
    """Trusted parent authenticates operator out of band; refs do not do so."""

    expected_admission: bytes = field(repr=False)
    caller_expectation_sha256: str
    root_dev: int
    root_ino: int
    owning_ak_task: int
    operator_evidence_ref: str
    parent_confirmation_sha256: str
    _used: list[bool] = field(default_factory=list, repr=False, compare=False)


@dataclass(frozen=True, slots=True, repr=False)
class ImageAdmission:
    raw: bytes = field(repr=False)
    sha256: str

    def __post_init__(self) -> None:
        record = parse_json(self.raw, limit=65_536)
        require(
            canonical(record) == self.raw
            # ubs:ignore -- public sha256 commitment, not a secret
            and self.sha256 == digest("admission-v2", record),
            "image_admission_invalid",
        )

    @property
    def record(self) -> dict[str, Any]:
        return parse_json(self.raw, limit=65_536)


def validate_source(record: object) -> dict[str, Any]:
    source = closed(
        record,
        "schema_version candidate_manifest_sha256 candidate_source_sha256 "
        "raw_input_file_sha256 input_shape_sha256 decoder_profile_sha256 "
        "source_occurrences plain_text_slots",
    )
    require(source["schema_version"] == "dspx-image-source-package-v1")
    require(
        all(
            hash_value(source[key])
            for key in (
                "candidate_manifest_sha256",
                "candidate_source_sha256",
                "raw_input_file_sha256",
                "input_shape_sha256",
                "decoder_profile_sha256",
            )
        )
    )
    occurrences = source["source_occurrences"]
    require(type(occurrences) is list and 0 < len(occurrences) <= 6)
    total = 0
    for index, value in enumerate(occurrences, 1):
        row = closed(
            value,
            "occurrence_id field_slot list_ordinal media_type content_sha256 "
            "byte_count width height",
        )
        require(row["occurrence_id"] == f"s{index:06d}")
        require(type(row["field_slot"]) is int and 0 <= row["field_slot"] < 4096)
        require(type(row["list_ordinal"]) is int and 0 <= row["list_ordinal"] < 4096)
        require(
            row["media_type"] in {"image/png", "image/jpeg"}
            and hash_value(row["content_sha256"])
        )
        require(positive(row["byte_count"], 8_388_608))
        require(positive(row["width"], 8192) and positive(row["height"], 8192))
        require(row["width"] * row["height"] <= 16_000_000)
        total += row["byte_count"]
    require(total <= 25_165_824)
    require(type(source["plain_text_slots"]) is list)
    chars = 0
    for value in source["plain_text_slots"]:
        row = closed(value, "field_slot text_sha256 char_count")
        require(type(row["field_slot"]) is int and 0 <= row["field_slot"] < 4096)
        require(
            hash_value(row["text_sha256"])
            and type(row["char_count"]) is int
            and row["char_count"] >= 0
        )
        chars += row["char_count"]
    require(chars <= 1_000_000)
    return source


def validate_admission(
    raw: bytes,
    *,
    source: dict[str, Any],
    authority: SyntheticImageAuthority | LiveImageAuthority,
    runtime_identity_sha256: str,
    now_ms: int | None = None,
) -> ImageAdmission:
    """Closed S -> A check against actual parent objects, never truthy flags."""
    require(type(authority) in {SyntheticImageAuthority, LiveImageAuthority})
    require(type(raw) is bytes and raw == authority.expected_admission)
    record = closed(
        parse_json(raw, limit=65_536),
        "schema_version mode provider_kind model canonical_base_endpoint source_package_sha256 "
        "candidate_manifest_sha256 runtime_identity_sha256 decoder_profile_sha256 request_plan "
        "limits deadlines custody approval_binding",
    )
    require(canonical(record) == raw)
    require(record["schema_version"] == "dspx-image-admission-v2")
    synthetic = type(authority) is SyntheticImageAuthority
    require(record["mode"] == ("synthetic" if synthetic else "live"))
    require(record["provider_kind"] == "openai-compatible")
    # Lazy import prevents any provider/client initialization during preparation.
    from .openai_compatible_provider import _validated_endpoint, _validated_model

    try:
        require(_validated_model(record["model"]) == record["model"])
        require(
            _validated_endpoint(record["canonical_base_endpoint"])[0]
            == record["canonical_base_endpoint"]
        )
    except Exception:
        raise ImageContractError("image_admission_invalid") from None
    source = validate_source(source)
    # ubs:ignore -- public sha256 commitment, not a secret
    require(record["source_package_sha256"] == digest("source-v1", source))
    require(record["candidate_manifest_sha256"] == source["candidate_manifest_sha256"])
    require(record["decoder_profile_sha256"] == source["decoder_profile_sha256"])
    require(
        record["runtime_identity_sha256"] == runtime_identity_sha256
        and hash_value(runtime_identity_sha256)
    )
    limits = closed(record["limits"], " ".join(CEILINGS))
    require(all(positive(limits[key], ceiling) for key, ceiling in CEILINGS.items()))
    rows = source["source_occurrences"]
    require(len(rows) <= limits["max_source_images"])
    require(sum(row["byte_count"] for row in rows) <= limits["max_source_image_bytes"])
    for row in rows:
        require(
            row["byte_count"] <= limits["max_image_bytes"]
            and row["width"] <= limits["max_width"]
            and row["height"] <= limits["max_height"]
            and row["width"] * row["height"] <= limits["max_pixels"]
        )
    require(
        sum(row["char_count"] for row in source["plain_text_slots"])
        <= limits["max_text_chars"]
    )
    plan = record["request_plan"]
    require(
        type(plan) is list
        and 0 < len(plan) <= 64
        and len(plan) == limits["total_dispatch_allowance"]
    )
    by_id = {row["occurrence_id"]: row for row in rows}
    used = set()
    for index, value in enumerate(plan, 1):
        row = closed(
            value,
            "plan_ordinal predictor_slot request_shape_sha256 image_occurrence_sequence",
        )
        require(
            row["plan_ordinal"] == index
            and type(row["predictor_slot"]) is int
            and row["predictor_slot"] >= 0
        )
        require(hash_value(row["request_shape_sha256"]))
        seq = row["image_occurrence_sequence"]
        require(type(seq) is list and 0 < len(seq) <= limits["max_request_images"])
        require(all(type(item) is str and item in by_id for item in seq))
        require(
            sum(by_id[item]["byte_count"] for item in seq)
            <= limits["max_request_image_bytes"]
        )
        used.update(seq)
    require(used == set(by_id))
    deadlines = closed(
        record["deadlines"],
        "not_before_utc_ms expires_utc_ms total_wall_ms per_request_io_timeout_ms",
    )
    require(all(type(value) is int and value > 0 for value in deadlines.values()))
    now_ms = time.time_ns() // 1_000_000 if now_ms is None else now_ms
    require(deadlines["not_before_utc_ms"] <= now_ms < deadlines["expires_utc_ms"])
    require(positive(deadlines["total_wall_ms"], 180_000))
    require(
        positive(
            deadlines["per_request_io_timeout_ms"],
            min(30_000, deadlines["total_wall_ms"]),
        )
    )
    custody = closed(
        record["custody"],
        "custody_id caller_run_id caller_binding_sha256 root_dev root_ino caller_expectation_sha256",
    )
    require(uuid_value(custody["custody_id"]) and uuid_value(custody["caller_run_id"]))
    require(hash_value(custody["caller_binding_sha256"]))
    require(
        hash_value(custody["caller_expectation_sha256"])
        and custody["caller_expectation_sha256"] == authority.caller_expectation_sha256
    )
    require(type(custody["root_dev"]) is int and type(custody["root_ino"]) is int)
    require(
        (custody["root_dev"], custody["root_ino"])
        == (authority.root_dev, authority.root_ino)
    )
    approval = closed(
        record["approval_binding"],
        "owning_ak_task operator_evidence_ref parent_confirmation_sha256",
    )
    if synthetic:
        require(all(value is None for value in approval.values()))
    else:
        require(
            type(approval["owning_ak_task"]) is int and approval["owning_ak_task"] > 0
        )
        require(
            type(approval["operator_evidence_ref"]) is str
            and re.fullmatch(
                r"ak://evidence/[1-9][0-9]*", approval["operator_evidence_ref"]
            )
            is not None
        )
        require(hash_value(approval["parent_confirmation_sha256"]))
        require(approval == {key: getattr(authority, key) for key in approval})
    return ImageAdmission(raw, digest("admission-v2", record))


def validate_image_provider_binding(
    session: object,
    *,
    model: str,
    base_url: str,
    transport: object,
) -> None:
    """Check the nominal caller/session and transport before client construction."""
    from .image_worker import require_clean_boundary

    require_clean_boundary()
    import httpx
    from .image_custody import ImageCustodySession
    from .image_privacy import require_privacy

    active = require_privacy()
    active.check()
    if type(session) is not ImageCustodySession:
        raise ImageContractError("image_admission_invalid") from None
    require(active.session is session, "image_admission_invalid")
    if type(session.authority) is SyntheticImageAuthority:
        require(type(transport) is httpx.MockTransport, "image_admission_invalid")
    require(
        model == session.record["model"]
        and base_url == session.record["canonical_base_endpoint"],
        "image_admission_invalid",
    )

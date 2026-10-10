# summary: "Bounded generation ingress and source primitives; image orchestration remains unintegrated."
# read_when:
#   - "Changing generation refusal or bounded source reads; see AK6607 for unfinished orchestration."

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
import re
from typing import Any, Mapping, cast
from dataclasses import dataclass, field
import json

from .image_admission import (
    ImageContractError,
    bounded_tree,
    canonical,
    digest,
    parse_json,
    require,
    sha,
)

from .image_source_io import open_root, read_relative, plain_text, image_bytes
from .image_source_io import END, START, _RESERVED, _UNSAFE_TEXT

_SOURCES = {"image_file": "path", "image_base64": "data", "image_url": "url"}
# Closed DesignMD image keys: anything else (a thumbnail, a label, a second source
# or MIME alias) is refused, never forwarded as plain text beside the image.
_ENVELOPE = {"imageDataBase64", "imageDataMimeType", "pixelInspectionInputStatus"}


def generation_preflight(value: object) -> bool:
    """No-effects refusal shared by ingress and every intent-taking renderer."""
    bounded_tree(value)
    pending: list[Any] = [value]
    image_profile = False
    while pending:
        item = pending.pop()
        if type(item) is str:
            require(
                _UNSAFE_TEXT.search(item) is None, "image_generation_inputs_unsupported"
            )
        elif type(item) is dict:
            require(
                not (_RESERVED & set(item))
                and item.get("type", item.get("kind"))
                not in {"image_file", "image_base64", "image_url"},
                "image_generation_inputs_unsupported",
            )
            if item.get("image_contract_version") or item.get("image_enabled"):
                image_profile = True
            pending.extend(item.keys())
            pending.extend(item.values())
        elif type(item) is list or type(item) is tuple:
            if "visual_image_inputs_json" in item:
                image_profile = True
            pending.extend(item)
    if type(value) is dict and image_profile:
        require(
            not any(
                cast(dict[str, Any], value).get(key)
                for key in ("examples", "examples_path", "dataset", "datasets")
            ),
            "image_generation_inputs_unsupported",
        )
        require(
            not cast(dict[str, Any], value).get("topology"),
            "image_generation_inputs_unsupported",
        )
    return image_profile


def refuse_runtime_image_inputs(runtime_inputs: Mapping[str, Any]) -> None:
    """Unbound historical episode inputs are never an image admission surface."""
    try:
        generation_preflight(dict(runtime_inputs))
        return
    except ImageContractError:
        pass  # leave the handler first: no payload-bearing context survives
    raise ImageContractError("image_admission_invalid") from None


_INTENT_DATA = ("examples", "examples_path", "dataset", "datasets", "options")


def intent_document(intent: object) -> dict[str, Any] | None:
    """Every data-bearing intent shape is preflighted; only data-less stand-ins are not."""
    dump = getattr(intent, "model_dump", None)
    if isinstance(intent, Mapping):
        return dict(cast(Mapping[str, Any], intent))
    if callable(dump):
        return dump(mode="json")
    data = {key: getattr(intent, key, None) for key in (*_INTENT_DATA, "topology")}
    return {key: value for key, value in data.items() if value is not None} or None


def generation_intent_preflight(intent: object) -> None:
    """Refuse generation-time image payloads before any renderer runs."""
    document = intent_document(intent)
    if document is not None:
        generation_preflight(document)


def safe_generation_document(path: Path) -> Any:
    """Bounded first ingress; raw syntax errors never reach CLI or an error chain."""
    try:
        root = path.absolute().parent
        fd = open_root(root)
        try:
            raw = read_relative(fd, path.name, limit=41_943_040)
        finally:
            os.close(fd)
        text = raw.decode("utf-8")
        require(
            _UNSAFE_TEXT.search(text) is None, "image_generation_inputs_unsupported"
        )
        if path.suffix.lower() == ".json":
            result = parse_json(raw)
        else:
            import yaml

            # Check amplification/depth before constructing YAML values.
            depth = 0
            count = 0
            for event in yaml.parse(text):
                count += 1
                if isinstance(
                    event,
                    (yaml.events.MappingStartEvent, yaml.events.SequenceStartEvent),
                ):
                    depth += 1
                elif isinstance(
                    event, (yaml.events.MappingEndEvent, yaml.events.SequenceEndEvent)
                ):
                    depth -= 1
                require(
                    depth <= 16 and count <= 8192,
                    "image_budget",
                )
            result = yaml.safe_load(text)
        generation_preflight(result)
        return result
    except ImageContractError as error:
        code = error.code
    except Exception:
        code = "image_input_invalid"
    raise ImageContractError(code) from None


@dataclass(frozen=True, slots=True)
class ImageOccurrence:
    occurrence_id: str
    field_slot: int
    list_ordinal: int
    media_type: str
    data: bytes = field(repr=False)
    width: int
    height: int
    marker: str = field(repr=False)

    def record(self) -> dict[str, Any]:
        return {
            "occurrence_id": self.occurrence_id,
            "field_slot": self.field_slot,
            "list_ordinal": self.list_ordinal,
            "media_type": self.media_type,
            "content_sha256": sha(self.data),
            "byte_count": len(self.data),
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen=True, slots=True, repr=False)
class ImageContext:
    fields: tuple[str, ...]
    values: tuple[object, ...] = field(repr=False)
    occurrences: tuple[ImageOccurrence, ...] = field(repr=False)
    source_raw: bytes = field(repr=False)
    input_raw: bytes = field(repr=False)

    @property
    def source(self) -> dict[str, Any]:
        return parse_json(self.source_raw)

    @property
    def source_sha256(self) -> str:
        return digest("source-v1", self.source)

    def materialized(self) -> dict[str, object]:
        return dict(zip(self.fields, self.values, strict=True))

    def manifest(self, admission_sha256: str) -> dict[str, Any]:
        return {
            "schema_version": "dspx-image-input-manifest-v2",
            "source_package_sha256": self.source_sha256,
            "admission_sha256": admission_sha256,
            "marker_entries": [
                {
                    "occurrence_id": item.occurrence_id,
                    "marker_sha256": sha(item.marker.encode("ascii")),
                }
                for item in self.occurrences
            ],
        }

    def split(self, text: str, *, slot: int | None = None) -> tuple[object, ...]:
        """Linear strict registered marker scan before any DSPy legacy normalizer."""
        require(type(text) is str and len(text) <= 41_943_040, "image_marker_invalid")
        parts: list[object] = []
        pos = 0
        by_marker = {item.marker for item in self.occurrences}
        while pos < len(text):
            start = text.find(START, pos)
            orphan_end = text.find(END, pos)
            require(
                orphan_end < 0 or (start >= 0 and orphan_end > start),
                "image_marker_invalid",
            )
            if start < 0:
                tail = text[pos:]
                plain_text(tail)
                if tail:
                    parts.append(tail)
                break
            if start > pos:
                parts.append(plain_text(text[pos:start]))
            end = text.find(END, start + len(START))
            require(
                end >= 0 and text.find(START, start + len(START), end) < 0,
                "image_marker_invalid",
            )
            marker = text[start : end + len(END)]
            require(marker in by_marker, "image_marker_invalid")
            # Exact bytes were issued once; duplicate occurrences are disambiguated by order below.
            same = [
                item
                for item in self.occurrences
                if item.marker == marker and (slot is None or item.field_slot == slot)
            ]
            used = sum(
                type(item) is ImageOccurrence and item.marker == marker
                for item in parts
            )
            require(used < len(same), "image_marker_invalid")
            parts.append(same[used])
            pos = end + len(END)
        return tuple(parts)


def materialize_image_inputs(
    raw: bytes,
    *,
    root_fd: int,
    fields: tuple[str, ...],
    candidate_manifest_sha256: str,
    candidate_source_sha256: str,
    decoder: object,
) -> ImageContext:
    """One source implementation used by both entrypoints, inside outer privacy."""
    from .image_worker import require_clean_boundary

    require_clean_boundary()
    from .image_decoder import FrozenImageDecoder
    from .image_privacy import require_privacy

    require_privacy()
    if type(decoder) is not FrozenImageDecoder:
        raise ImageContractError("image_decoder_unavailable") from None
    parsed = parse_json(raw)
    require(type(parsed) is dict, "image_input_invalid")
    inputs = parsed.get("inputs", parsed)
    require(
        type(inputs) is dict and set(inputs) == set(fields), "signature_input_shape"
    )
    occurrences: list[ImageOccurrence] = []
    # Derived commitments never outgrow the input's own bounds (AK6810): the shape
    # mirrors it node for node (a leaf becomes its kind name, lists and dicts keep
    # their items and keys), and each field slot gets one text row over its
    # length-framed texts, so canonical() bounds both exactly as parse_json did.
    text_digests: dict[int, Any] = {}
    text_chars: dict[int, int] = {}
    text_count = 0
    byte_count = 0
    shape: list[object] = []

    def visit(value: object, slot: int, ordinal: int = 0) -> tuple[object, object]:
        nonlocal text_count, byte_count
        if type(value) is str:
            plain_text(value)
            text_count += len(value)
            require(text_count <= 1_000_000, "image_budget")
            encoded = value.encode("utf-8")
            framed = len(encoded).to_bytes(8, "big") + encoded
            text_digests.setdefault(slot, hashlib.sha256(b"text-slot-v1\0")).update(
                framed
            )
            text_chars[slot] = text_chars.get(slot, 0) + len(value)
            return value, "str"
        # parse_json/bounded_tree proved exact dictionaries with string keys.
        descriptor = cast(dict[str, object], value) if type(value) is dict else None
        kind = descriptor.get("type") if descriptor is not None else None
        if descriptor is not None and type(kind) is str and kind in _SOURCES:
            require(
                set(descriptor) == {"type", "media_type", _SOURCES[kind]},
                "image_input_invalid",
            )
            media, source = descriptor["media_type"], descriptor[_SOURCES[kind]]
            if type(media) is not str or type(source) is not str:
                raise ImageContractError("image_input_invalid") from None
            require(
                media in {"image/png", "image/jpeg"},
                "image_input_invalid",
            )
            # An image_url is an inline data URI, never a bare body (no laundering).
            require(
                kind != "image_url" or source.startswith("data:"), "image_input_invalid"
            )
            require(len(occurrences) < 6, "image_budget")
            data = (
                read_relative(root_fd, source, limit=8_388_608)
                if kind == "image_file"
                else image_bytes(source, media)
            )
            byte_count += len(data)
            require(byte_count <= 25_165_824, "image_budget")
            width, height = decoder.decode(data, media)
            uri = f"data:{media};base64," + base64.b64encode(data).decode("ascii")
            marker = (
                START
                + json.dumps(
                    [{"type": "image_url", "image_url": {"url": uri}}],
                    separators=(",", ":"),
                )
                + END
            )
            item = ImageOccurrence(
                f"s{len(occurrences) + 1:06d}",
                slot,
                ordinal,
                media,
                data,
                width,
                height,
                marker,
            )
            occurrences.append(item)
            return marker, "str"
        if type(value) is list:
            segments = [visit(item, slot, index) for index, item in enumerate(value)]
            if any(
                type(item) is dict
                and cast(dict[str, object], item).get("type")
                in {"image_file", "image_base64", "image_url"}
                for item in value
            ):
                texts: list[str] = []
                for segment, _ in segments:
                    if type(segment) is not str:
                        raise ImageContractError("image_input_invalid") from None
                    texts.append(segment)
                return "\n".join(texts), "str"
            return [item[0] for item in segments], [item[1] for item in segments]
        if type(value) is dict:
            require(not (_RESERVED & set(value)), "image_input_invalid")
            for key in value:
                visit(key, slot)
            converted = {key: visit(item, slot) for key, item in value.items()}
            return {key: item[0] for key, item in converted.items()}, {
                key: item[1] for key, item in converted.items()
            }
        require(type(value) in {int, float, bool, type(None)}, "image_input_invalid")
        return value, {int: "int", float: "float", bool: "bool", type(None): "null"}[
            type(value)
        ]

    values = []
    for slot, name in enumerate(fields):
        value = inputs[name]
        if name == "visual_image_inputs_json":
            require(type(value) is str, "image_input_invalid")
            packet = parse_json(value.encode("utf-8"))
            require(
                type(packet) is dict
                and set(packet) == {"images"}
                and type(packet.get("images")) is list
                and packet["images"],
                "image_input_invalid",
            )
            segments = ["image-input-envelope-v1"]
            for index, image in enumerate(packet["images"]):
                require(
                    type(image) is dict
                    and set(image) <= _ENVELOPE | {"mimeType"}
                    and image.get("pixelInspectionInputStatus")
                    == "available_bounded_inline_image_payload",
                    "image_input_invalid",
                )
                media = image.get("imageDataMimeType")
                require(image.get("mimeType", media) == media, "image_input_invalid")
                require(media in {"image/png", "image/jpeg"}, "image_input_invalid")
                safe = {
                    key: item for key, item in image.items() if key not in _ENVELOPE
                }
                marker, _ = visit(
                    {
                        "type": "image_base64",
                        "data": image.get("imageDataBase64"),
                        "media_type": media,
                    },
                    slot,
                    index,
                )
                segments.extend(
                    [canonical(safe).decode("ascii"), f"slot:{slot}:{index}", marker]
                )
            converted, field_shape = "\n".join(segments), "str"
        else:
            converted, field_shape = visit(value, slot)
        values.append(converted)
        shape.append(field_shape)
    require(bool(occurrences), "image_input_invalid")
    source = {
        "schema_version": "dspx-image-source-package-v1",
        "candidate_manifest_sha256": candidate_manifest_sha256,
        "candidate_source_sha256": candidate_source_sha256,
        "raw_input_file_sha256": sha(raw),
        "input_shape_sha256": digest("shape-v2", shape),
        "decoder_profile_sha256": decoder.profile_sha256,
        "source_occurrences": [item.record() for item in occurrences],
        "plain_text_slots": [
            {
                "field_slot": slot,
                "text_sha256": text_digests[slot].hexdigest(),
                "char_count": count,
            }
            for slot, count in text_chars.items()
        ],
    }
    return ImageContext(
        fields, tuple(values), tuple(occurrences), canonical(source), raw
    )


def reject_output(value: object, context: ImageContext | None) -> None:
    """Conservative bounded output membrane, not semantic confidentiality proof."""
    bounded_tree(value)
    if type(value) is str:
        require(
            len(value) <= 1_000_000
            and _UNSAFE_TEXT.search(value) is None
            and "iVBORw0KGgo" not in value
            and "/9j/" not in value,
            "image_privacy",
        )
        require(re.search(r"[A-Za-z0-9+/]{128,}={0,2}", value) is None, "image_privacy")
        for item in () if context is None else context.occurrences:
            encoded = base64.b64encode(item.data).decode("ascii")
            require(
                encoded not in value and encoded.replace("/", "\\/") not in value,
                "image_privacy",
            )
    elif type(value) is dict:
        require(not (_RESERVED & set(value)), "image_privacy")
        for item in value.values():
            reject_output(item, context)
    elif type(value) is list or type(value) is tuple:
        for item in value:
            reject_output(item, context)

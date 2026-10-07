"""Generation attachment custody, and the source membrane red matrix (AK6756).

The harness below runs the production materializer inside the clean worker with
effect, read, open and decoder spies; the worker publishes only safe facts (codes,
counters, hashes) and every assertion about them runs in this parent. Rows S07, S08,
S13 and S15-extra live here; S09-S12 and S38-S41 in test_image_input_contract.py.
"""

from __future__ import annotations

import base64
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import struct
from typing import Any
import zlib

import pytest

from dspx.image_admission import ImageContractError, SyntheticImageAuthority, sha
from dspx.image_decoder import FrozenImageDecoder
from dspx.image_source_io import contract_verification_metadata, open_root
from dspx.image_source_io import read_relative
from dspx.image_worker import worker_entry

_HERE = "test_image_source_io"
_PNG, _JPEG = "image/png", "image/jpeg"
_ENVELOPE = "available_bounded_inline_image_payload"
_COUNTERS = ("effects", "upstream", "opens", "native", "meta", "decode", "faults")


def _attachment(source: Path) -> dict[str, object]:
    return {
        "schema_version": "program-architecture-contract-verification-v1",
        "status": "verified_contract_intent",
        "materialization_allowed_by_contract_verification": True,
        "materialization_gate": {
            "status": "verified_for_explicit_program_gen_materialization",
            "program_gen_must_match_intent_hash": hashlib.sha256(
                source.read_bytes()
            ).hexdigest(),
            "allows_live_tools": False,
            "allows_custom_imports": False,
            "allows_external_retrievers": False,
        },
        "non_authority": {"promotion_authority": False},
    }


@pytest.mark.parametrize("image_profile", [False, True])
def test_verification_attachment_keeps_exact_bytes_and_actual_source_binding(
    tmp_path: Path,
    image_profile: bool,
) -> None:
    source = tmp_path / "intent.json"
    source.write_text('{"objective":"safe"}\n', encoding="utf-8")
    attachment = tmp_path / "verification.json"
    raw = json.dumps(_attachment(source), indent=3) + "\n"
    attachment.write_text(raw, encoding="utf-8")
    root = tmp_path / "candidate"
    root.mkdir()
    result = contract_verification_metadata(
        attachment,
        root=root,
        intent_source=source,
        image_profile=image_profile,
    )
    assert result is not None
    assert result["content_hash"] == hashlib.sha256(raw.encode()).hexdigest()
    assert result["non_authority"] == {"promotion_authority": False}
    assert (
        root / "program_architecture_contract_verification.json"
    ).read_bytes() == raw.encode()
    different_root = tmp_path / "different"
    different_root.mkdir()
    source.write_text('{"objective":"changed"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="intent_hash_mismatch"):
        contract_verification_metadata(
            attachment,
            root=different_root,
            intent_source=source,
            image_profile=image_profile,
        )
    assert list(different_root.iterdir()) == []


@pytest.mark.parametrize(
    "payload", ["data:image/png;base64,QUJD", "<<CUSTOM-TYPE-END-IDENTIFIER>>"]
)
def test_attachment_privacy_branch_does_not_redefine_text_attachments(
    tmp_path: Path,
    payload: str,
) -> None:
    source = tmp_path / "intent.json"
    source.write_text('{"objective":"text"}', encoding="utf-8")
    record = _attachment(source)
    record["legacy_extra"] = payload
    attachment = tmp_path / "verification.json"
    raw = json.dumps(record)
    attachment.write_text(raw, encoding="utf-8")
    text_root = tmp_path / "text"
    image_root = tmp_path / "image"
    text_root.mkdir()
    image_root.mkdir()
    contract_verification_metadata(attachment, root=text_root, intent_source=source)
    assert (
        text_root / "program_architecture_contract_verification.json"
    ).read_text() == raw
    with pytest.raises(ImageContractError, match="image_generation_inputs_unsupported"):
        contract_verification_metadata(
            attachment,
            root=image_root,
            intent_source=source,
            image_profile=True,
        )
    assert list(image_root.iterdir()) == []


def _chunk(kind: bytes, data: bytes) -> bytes:
    crc = struct.pack(">I", zlib.crc32(kind + data))
    return struct.pack(">I", len(data)) + kind + data + crc


def gray_png(
    width: int = 1,
    height: int = 1,
    *,
    shade: int = 0x80,
    total: int | None = None,
    extra: bytes = b"",
) -> bytes:
    """Valid 8-bit grayscale PNG; `total` pads with stored deflate blocks to exact bytes."""
    raw = (b"\0" + bytes([shade]) * width) * height
    parts = [zlib.compress(raw, 9)]
    if total is not None:
        blocks = [raw[index : index + 65_535] for index in range(0, len(raw), 65_535)]
        spare = total - (63 + len(extra) + len(raw) + 5 * len(blocks))
        splits = next(
            n for n in range(12) if spare >= 12 * n and (spare - 12 * n) % 5 == 0
        )
        blocks += [b""] * ((spare - 12 * splits) // 5)
        stream = b"\x78\x01"
        for index, block in enumerate(blocks):
            size = struct.pack("<HH", len(block), 0xFFFF ^ len(block))
            stream += bytes([index == len(blocks) - 1]) + size + block
        stream += struct.pack(">I", zlib.adler32(raw))
        cut = len(stream) // (splits + 1)
        parts = [stream[n * cut : (n + 1) * cut] for n in range(splits)]
        parts.append(stream[splits * cut :])
    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    out = b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header) + extra
    out += b"".join(_chunk(b"IDAT", part) for part in parts) + _chunk(b"IEND", b"")
    assert total is None or len(out) == total
    return out


def jpeg(width: int = 2, height: int = 2, *, shade: int = 0x80) -> bytes:
    from PIL import Image

    out = BytesIO()
    with Image.new("L", (width, height), shade) as fixture:
        fixture.save(out, format="JPEG")
    return out.getvalue()


def webp() -> bytes:
    from PIL import Image

    out = BytesIO()
    with Image.new("RGB", (4, 4), "red") as fixture:
        fixture.save(out, format="WEBP")
    return out.getvalue()


def b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def image(kind: str, source: str, media: str = _PNG) -> dict[str, str]:
    key = {"image_file": "path", "image_base64": "data", "image_url": "url"}[kind]
    return {"type": kind, key: source, "media_type": media}


def envelope(raw: bytes, media: str = _PNG, **extra: object) -> str:
    row = {
        "imageDataBase64": b64(raw),
        "imageDataMimeType": media,
        "pixelInspectionInputStatus": _ENVELOPE,
        **extra,
    }
    return json.dumps({"images": [row]})


def inputs_dir(tmp_path: Path) -> Path:
    inputs = tmp_path / "inputs"
    inputs.mkdir(exist_ok=True)
    return inputs


def run_cases(
    tmp_path: Path,
    cases: list[dict[str, Any]],
    *,
    files: dict[str, bytes] | None = None,
    watch: dict[str, Path] | None = None,
    needles: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    """Materialize each case in one clean worker; return the published safe facts.

    A case is {"document": JSON value or raw bytes, "fields": names, "options": {...}}.
    """
    from dspx.image_records import read_record
    from dspx.image_supervision import supervise_image_worker

    inputs = inputs_dir(tmp_path)
    for name, raw in (files or {}).items():
        (inputs / name).parent.mkdir(parents=True, exist_ok=True)
        (inputs / name).write_bytes(raw)
    rows = []
    for index, case in enumerate(cases):
        document = case["document"]
        raw = document if type(document) is bytes else json.dumps(document).encode()
        (inputs / f"case-{index}.json").write_bytes(raw)
        rows.append(
            {
                "input": f"case-{index}.json",
                "fields": list(case.get("fields", ("visual", "text"))),
                "options": dict(case.get("options", {})),
            }
        )
    pending: list[object] = [case["document"] for case in cases]
    while pending:  # every long input string is a needle (its tail keeps params small)
        item = pending.pop()
        if type(item) is str and len(item) >= 24:
            needles += (item[-32:],)
        elif type(item) is dict or type(item) is list:
            pending.extend(item.values() if type(item) is dict else item)
    identities = {}
    for name, path in (watch or {}).items():
        row = os.stat(path, follow_symlinks=False)
        identities[name] = [row.st_dev, row.st_ino]
    facts_dir = tmp_path / f"facts-{len(list(tmp_path.glob('facts-*')))}"
    facts_dir.mkdir(mode=0o700)
    root = open_root(inputs)
    facts_fd = os.open(facts_dir, os.O_RDONLY | os.O_DIRECTORY)
    try:
        status = supervise_image_worker(
            f"{_HERE}:_materialize_entry",
            {
                "root_fd": root,
                "facts_fd": facts_fd,
                "cases": rows,
                "watch": identities,
                "needles": sorted({str(tmp_path), *needles}),
            },
            fds=(root, facts_fd),
            wall_ms=120_000,
        )
        published = read_record(facts_fd, "facts.json")
    finally:
        os.close(root)
        os.close(facts_fd)
    assert status == {
        "status": "prepared",
        "commitment_sha256": sha(published),
        "fixture_evidence": True,
        "live_authorized": False,
        "failure_code": None,
    }
    facts = json.loads(published)
    assert facts["harness"] is None, facts["harness"]
    return facts["cases"]


def refused(fact: dict[str, Any], code: str, *, decoded: bool = False) -> None:
    """Then-steps shared by every refusal: fixed clean error, no effect, nothing kept.

    Unless the decoder was legitimately entered, no Pillow open, native decoder or
    metadata decompression ran either.
    """
    assert (fact["code"], fact["clean"]) == (code, True), fact
    assert fact["effects"] == fact["upstream"] == fact["leaks"] == 0, fact
    assert fact["written"] is False and fact["occurrences"] == [], fact
    if not decoded:
        assert fact["opens"] == fact["native"] == fact["meta"] == 0, fact


def accepted(fact: dict[str, Any], count: int) -> None:
    assert (fact["code"], fact["clean"]) == ("ok", None), fact
    assert fact["effects"] == fact["upstream"] == fact["leaks"] == 0, fact
    assert fact["written"] is False and len(fact["occurrences"]) == count, fact


class _ShadowDecoder(FrozenImageDecoder):
    """A real, fully checked decoder that is nevertheless not the frozen type."""


def _clean_error(error: ImageContractError, needles: list[str]) -> bool:
    import traceback

    texts = ["".join(traceback.format_exception(error))]
    item: BaseException | None = error
    for _ in range(8):
        if item is None:
            break
        texts += [str(item), repr(item), repr(item.args), repr(vars(item))]
        item = item.__cause__ or item.__context__
    return (
        str(error) == error.code
        and error.args == (error.code,)
        and error.__cause__ is None
        and (error.__context__ is None or error.__suppress_context__)
        and not any(needle in text for needle in needles for text in texts)
    )


@worker_entry
def _materialize_entry(params):
    from dspx.image_records import publish

    try:
        facts: dict[str, object] = {"harness": None, "cases": _observe(params)}
    except Exception as error:  # a harness defect only, never a production outcome
        import traceback

        frame = traceback.extract_tb(error.__traceback__)[-1]
        facts = {"harness": f"{type(error).__name__}:{frame.name}:{frame.lineno}"}
    return {
        "status": "prepared",
        "commitment_sha256": publish(params["facts_fd"], "facts.json", facts),
        "fixture_evidence": True,
        "live_authorized": False,
        "failure_code": None,
    }


def _observe(params):
    import importlib.metadata
    import logging
    import socket
    import urllib.request
    import warnings

    import httpx
    from PIL import Image, PngImagePlugin
    import dspy.adapters._legacy_type_markers as legacy
    import dspy.clients.openai_format as openai_format
    import dspy.core.types as core_types
    from dspx.image_admission import CEILINGS
    from dspx.image_input_contract import materialize_image_inputs
    from dspx.image_privacy import image_privacy
    from dspx.image_records import list_root
    from dspx.openai_compatible_provider import OpenAICompatibleProvider
    from dspx.stub_provider import StubProvider

    root, needles = params["root_fd"], params["needles"]
    watch = {name: tuple(row) for name, row in params["watch"].items()}
    counts = dict.fromkeys(_COUNTERS, 0)
    opened, reads = dict.fromkeys(watch, 0), dict.fromkeys(watch, 0)
    real_open, real_read, real_decode = os.open, os.read, FrozenImageDecoder.decode
    retarget: list[str] = []
    records: list[logging.LogRecord] = []

    def watched(fd: int) -> list[str]:
        row = os.fstat(fd)
        return [name for name, key in watch.items() if key == (row.st_dev, row.st_ino)]

    def open_spy(name, flags, *args, **kwargs):
        fd = real_open(name, flags, *args, **kwargs)
        for item in watched(fd):
            opened[item] += 1
        if retarget and os.fspath(name) == retarget[0]:
            os.rename(retarget[1], retarget[2])  # relocate after the component opened
        return fd

    def read_spy(fd, count):
        for item in watched(fd):
            reads[item] += 1
        return real_read(fd, count)

    def counted(key, original):
        def spy(*args, **kwargs):
            counts[key] += 1
            return original(*args, **kwargs)

        return spy

    def denied(*args, **kwargs):
        counts["effects"] += 1
        raise AssertionError("source membrane entered an effect")

    def decode_spy(self, data, media):
        counts["decode"] += 1
        return real_decode(self, data, media)

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger, handler = logging.getLogger(), Capture(level=1)
    level = logger.level
    logger.addHandler(handler)
    logger.setLevel(1)
    results = []
    try:
        with pytest.MonkeyPatch.context() as spies:
            for owner, names in (
                (httpx.Client, "__init__ send"),
                (httpx.AsyncClient, "__init__"),
                (StubProvider, "invoke"),
                (OpenAICompatibleProvider, "__init__ invoke"),
                (socket.socket, "connect"),
                (socket, "getaddrinfo create_connection"),
                (urllib.request, "urlopen"),
            ):
                for name in names.split():
                    spies.setattr(owner, name, denied)
            for owner in (openai_format, core_types, legacy):  # upstream normalizers
                name = "split_data_uri" if owner is openai_format else "_split_data_uri"
                spies.setattr(owner, name, counted("upstream", getattr(owner, name)))
            spies.setattr(Image, "preinit", counted("opens", Image.preinit))
            spies.setattr(
                PngImagePlugin,
                "_safe_zlib_decompress",
                counted("meta", PngImagePlugin._safe_zlib_decompress),
            )
            for name in ("zip_decoder", "jpeg_decoder"):
                spies.setattr(
                    Image.core, name, counted("native", getattr(Image.core, name))
                )
            spies.setattr(FrozenImageDecoder, "decode", decode_spy)
            spies.setattr(os, "open", open_spy)
            spies.setattr(os, "read", read_spy)
            for case in params["cases"]:
                options = case["options"]
                for key in counts:
                    counts[key] = 0
                for key in watch:
                    opened[key] = reads[key] = 0
                retarget[:] = options.get("retarget", [])
                del records[:]
                before = sorted(list_root(root))
                with pytest.MonkeyPatch.context() as faults:
                    fault = options.get("fault")
                    for name in ("zip_decoder", "jpeg_decoder"):
                        native = getattr(Image.core, name)
                        if fault == "codec":
                            faults.delattr(Image.core, name)
                        elif fault == "warning":

                            def noisy(*args, _native=native):
                                counts["faults"] += 1
                                warnings.warn(
                                    "synthetic", Image.DecompressionBombWarning
                                )
                                return _native(*args)

                            faults.setattr(Image.core, name, noisy)
                    if options.get("decoder") == "absent":

                        def missing(name):
                            raise importlib.metadata.PackageNotFoundError(name)

                        faults.setattr(importlib.metadata, "version", missing)
                    with warnings.catch_warnings(record=True) as caught:
                        warnings.simplefilter("always")
                        fact = _case(
                            case,
                            root=root,
                            needles=needles,
                            limit=options.get(
                                "input_limit", CEILINGS["max_input_json_bytes"]
                            ),
                            privacy=image_privacy,
                            materialize=materialize_image_inputs,
                        )
                texts = [str(item.message) for item in caught]
                texts += [str(record.msg) + repr(record.args) for record in records]
                fact.update(counts)
                fact["opened"], fact["reads"] = dict(opened), dict(reads)
                fact["leaks"] = sum(any(n in text for n in needles) for text in texts)
                fact["written"] = sorted(list_root(root)) != before
                results.append(fact)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(level)
    return results


def _case(case, *, root, needles, limit, privacy, materialize) -> dict[str, object]:
    options = case["options"]
    fact: dict[str, object] = {"decoder": "ok", "stage": "read", "clean": None}
    decoder: object = None
    try:
        decoder = (
            _ShadowDecoder if options.get("decoder") == "shadow" else FrozenImageDecoder
        )()
    except ImageContractError as error:
        fact["decoder"] = error.code
    context = None
    with privacy() as active:
        try:
            raw = read_relative(root, case["input"], limit=limit)
            fact["stage"] = "materialize"
            context = materialize(
                raw,
                root_fd=root,
                fields=tuple(case["fields"]),
                candidate_manifest_sha256="1" * 64,
                candidate_source_sha256="2" * 64,
                decoder=decoder,
            )
        except ImageContractError as error:
            fact["code"], fact["clean"] = error.code, _clean_error(error, needles)
        else:
            fact["code"] = "ok"
            fact["post"] = {
                name: _POST[name](active, context) for name in options.get("post", [])
            }
    rows = [] if context is None else context.source["source_occurrences"]
    fact["occurrences"] = rows
    fact["text_chars"] = (
        0
        if context is None
        else sum(row["char_count"] for row in context.source["plain_text_slots"])
    )
    fact["source"] = (
        context.source if context is not None and options.get("source") else None
    )
    return fact


def _post_budgets(active, context) -> dict[str, object]:
    """Revalidate the actual ordered request with the pre-send request builder."""
    from types import SimpleNamespace

    from dspx.image_admission import CEILINGS
    from dspx.provider_contract import (
        ProviderImagePart,
        ProviderPartsMessage,
        ProviderRequest,
        ProviderTextPart,
        image_payload,
    )

    def attempt(repeat: int = 0, **limits: int) -> tuple[str, int, int]:
        parts: list[ProviderTextPart | ProviderImagePart] = [ProviderTextPart("A")]
        for item in [*context.occurrences, *[context.occurrences[0]] * repeat]:
            ident = (sha(item.data), len(item.data), item.width, item.height)
            data = (item.media_type, item.data, *ident, item.occurrence_id)
            parts += [ProviderImagePart(*data), ProviderTextPart("B")]
        record = {"model": "synthetic-vision-fixture", "limits": {**CEILINGS, **limits}}
        session = SimpleNamespace(record=record, context=context)
        message = ProviderPartsMessage("user", tuple(parts))
        request = ProviderRequest(record["model"], (message,), session)
        try:
            body, _, _ = image_payload(request, session)
        except ImageContractError as error:
            return error.code, 0, 0
        wire = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
        return "ok", len(wire.encode("utf-8")), len(parts)

    _, size, parts = attempt()
    return {
        "body_at_limit": attempt(max_request_body_bytes=size)[0],
        "body_over": attempt(max_request_body_bytes=size - 1)[0],
        "parts_at_limit": attempt(max_parts=parts)[0],
        "parts_over": attempt(max_parts=parts - 1)[0],
        "repeated": attempt(repeat=1)[0],
    }


def _post_demo(active, context) -> dict[str, object]:
    """A demo repeating a source image is refused at binding and at formatting."""
    import dspy
    from dspy.core.types import LMImagePart

    active.context = context
    values = context.materialized()
    clean, shown = dspy.Predict("visual -> answer"), dspy.Predict("visual -> answer")
    shown.demos = [dspy.Example(visual=values["visual"], answer="seen")]
    outcome: dict[str, object] = {}
    for name, step in (
        ("bind_clean", lambda: active.bind_graph(clean)),
        ("bind_demo", lambda: active.bind_graph(shown)),
        (
            "format_demo",
            lambda: active.formatter.format(clean.signature, shown.demos, values),
        ),
    ):
        try:
            step()
            outcome[name] = "ok"
        except ImageContractError as error:
            outcome[name] = error.code
    messages = active.formatter.format(clean.signature, [], values)
    outcome["format_images"] = sum(
        type(part) is LMImagePart for message in messages for part in message.parts
    )
    return outcome


_POST = {"budgets": _post_budgets, "demo": _post_demo}


PIXELS = gray_png(2, 2)
_INVALID, _DECODER, _BUDGET = (
    "image_input_invalid",
    "image_decoder_invalid",
    "image_budget",
)


def one(value: object, **options: object) -> dict[str, object]:
    """One case whose `visual` field is `value` (normally a descriptor) beside text."""
    return {"document": {"visual": value, "text": "t"}, "options": options}


def inline(raw: bytes, media: str = _PNG, **options: object) -> dict[str, object]:
    return one(image("image_base64", b64(raw), media), **options)


def _enveloped(raw: str, text: str = "t") -> dict[str, object]:
    fields = ("visual_image_inputs_json", "text")
    return {"document": dict(zip(fields, (raw, text))), "fields": fields}


def _s07(tmp_path: Path, example: str) -> tuple[list[tuple[dict, str]], dict]:
    """Per Examples row: (case, expected code) pairs plus run_cases keyword arguments."""
    encoded, photo, uri = b64(PIXELS), jpeg(), "data:image/png;base64,"
    inputs = inputs_dir(tmp_path)
    if example == "E01-invalid-alphabet":
        bad = encoded[:8] + "*" + encoded[9:]
        urls = [uri + bad, uri + encoded[:-4] + "!!!!"]
        rows = [one(image("image_base64", bad))] + [
            one(image("image_url", u)) for u in urls
        ]
        return [(case, _INVALID) for case in rows], {"needles": (encoded[9:],)}
    if example == "E02-url-safe":
        shades = (gray_png(2, 2, shade=shade) for shade in range(256))
        raw = next(item for item in shades if {"+", "/"} & set(b64(item)))
        safe = base64.urlsafe_b64encode(raw).decode("ascii")
        assert safe != b64(raw) and base64.urlsafe_b64decode(safe) == raw
        rows = [one(image("image_base64", safe)), one(image("image_url", uri + safe))]
        return [(case, _INVALID) for case in rows], {"needles": (safe,)}
    if example == "E03-whitespace":
        wrapped = "\n".join(encoded[n : n + 16] for n in range(0, len(encoded), 16))
        values = [
            encoded + " ",
            " " + encoded,
            wrapped,
            encoded[:8] + "\t" + encoded[8:],
        ]
        rows = [one(image("image_base64", value)) for value in values]
        return [(case, _INVALID) for case in rows], {"needles": (encoded[16:],)}
    if example == "E04-noncanonical-padding":
        canonical = b64(raw := gray_png(1, 2, total=121))
        assert canonical.endswith("==") and canonical[-3] in "AQgw"
        bits = canonical[:-3] + chr(ord(canonical[-3]) + 1) + "=="
        assert base64.b64decode(bits) == raw  # a permissive decoder would accept it
        values = [canonical[:-2], canonical + "=", canonical[:-1], bits]
        rows = [one(image("image_base64", value)) for value in values]
        return [(case, _INVALID) for case in rows], {"needles": (canonical[:-3],)}
    if example == "E05-empty":
        (inputs / "empty.png").write_bytes(b"")
        rows = [
            (one(image("image_base64", "")), _BUDGET),
            (one(image("image_url", uri)), _BUDGET),
        ]
        rows.append((one(image("image_file", "empty.png")), _INVALID))
        return rows, {"watch": {"empty": inputs / "empty.png"}}
    if example == "E06-mime-mismatch":
        (inputs / "ref.png").write_bytes(PIXELS)
        rows = [(inline(PIXELS, _JPEG), _DECODER), (inline(photo, _PNG), _DECODER)]
        rows.append(
            (one(image("image_url", "data:image/jpeg;base64," + encoded)), _INVALID)
        )
        rows.append((one(image("image_file", "ref.png", _JPEG)), _DECODER))
        return rows, {"needles": (encoded, b64(photo))}
    if example == "E07-svg":
        svg, media = b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/svg+xml"
        (inputs / "pic.svg").write_bytes(svg)
        rows = [inline(svg, media), _enveloped(envelope(svg, media))]
        rows.append(one(image("image_url", f"data:{media};base64," + b64(svg), media)))
        rows.append(one(image("image_file", "pic.svg", media)))
        return [(case, _INVALID) for case in rows], {
            "watch": {"svg": inputs / "pic.svg"}
        }
    if example == "E08-animated-png":
        frame = struct.pack(">IIIIIHHBB", 0, 2, 2, 0, 0, 1, 1, 0, 0)
        animation = _chunk(b"acTL", struct.pack(">II", 1, 0))
        values = [animation, animation + _chunk(b"fcTL", frame)]
        rows = [inline(gray_png(2, 2, extra=extra)) for extra in values]
        return [(case, _DECODER) for case in rows], {}
    if example == "E09-webp":
        raw, media = webp(), "image/webp"
        rows = [(inline(raw, _PNG), _DECODER), (inline(raw, _JPEG), _DECODER)]
        rows += [
            (inline(raw, media), _INVALID),
            (_enveloped(envelope(raw, media)), _INVALID),
        ]
        rows.append(
            (
                one(image("image_url", f"data:{media};base64," + b64(raw), media)),
                _INVALID,
            )
        )
        return rows, {"needles": (b64(raw),)}
    assert example == "E10-truncated-jpeg"
    values = [photo[:-2], photo[: len(photo) // 2], photo[:-1]]
    return [(inline(value, _JPEG), _DECODER) for value in values], {}


@pytest.mark.parametrize(
    "example",
    [
        "E01-invalid-alphabet",
        "E02-url-safe",
        "E03-whitespace",
        "E04-noncanonical-padding",
        "E05-empty",
        "E06-mime-mismatch",
        "E07-svg",
        "E08-animated-png",
        "E09-webp",
        "E10-truncated-jpeg",
    ],
)
def test_s07_malformed_image_data_never_enters_effects(
    tmp_path: Path, example: str
) -> None:
    """AK6607-S07: Given a malformed source; When the materializer validates it;
    Then it rejects before provider invoke and send, no remote fetch occurs, and the
    error chain and logs carry no raw data."""
    rows, extra = _s07(tmp_path, example)
    facts = run_cases(tmp_path, [case for case, _ in rows], **extra)
    for fact, (_, code) in zip(facts, rows, strict=True):
        refused(fact, code)  # a decoder refusal here is structural: no Pillow open
        assert fact["decode"] == (code == _DECODER), fact
        assert sum(fact["reads"].values()) == 0, fact
        if example == "E07-svg":  # media refusal precedes even the confined open
            assert fact["opened"] == {"svg": 0}, fact


@pytest.mark.parametrize("example", ["E11-decoder-warning", "E12-absent-codec"])
def test_s07_decoder_faults_reject_inside_the_frozen_decoder(
    tmp_path: Path, example: str
) -> None:
    """AK6607-S07-E11/E12: a decompression warning or a missing native codec during
    the restricted load is a fixed refusal, never a degraded or partial image."""
    fault = "warning" if example.startswith("E11") else "codec"
    sources = [(PIXELS, _PNG), (jpeg(), _JPEG)]
    faulty = [inline(raw, media, fault=fault) for raw, media in sources]
    facts = run_cases(tmp_path, faulty + [inline(raw, media) for raw, media in sources])
    for fact in facts[:2]:  # the warning is an error before the native decoder runs
        refused(fact, _DECODER, decoded=True)
        assert fact["decode"] == 1 and fact["opens"] >= 1 and fact["native"] == 0, fact
        assert fact["faults"] == (1 if fault == "warning" else 0), fact
    for fact in facts[2:]:  # the same sources decode once the fault is absent
        accepted(fact, 1)
        assert fact["opens"] == 2 and fact["native"] == 1, fact


def test_s07_e13_absent_or_unfrozen_decoder_is_unavailable(tmp_path: Path) -> None:
    """AK6607-S07-E13: absent Pillow, or any decoder object that is not exactly the
    frozen decoder, refuses with image_decoder_unavailable before any source read."""
    (inputs_dir(tmp_path) / "ref.png").write_bytes(PIXELS)
    part = image("image_file", "ref.png")
    facts = run_cases(
        tmp_path,
        [one(part, decoder="absent"), one(part, decoder="shadow"), one(part)],
        watch={"ref": inputs_dir(tmp_path) / "ref.png"},
    )
    decoders = [fact["decoder"] for fact in facts]
    assert decoders == ["image_decoder_unavailable", "ok", "ok"]
    for fact in facts[:2]:
        refused(fact, "image_decoder_unavailable")
        assert fact["stage"] == "materialize" and fact["decode"] == 0, fact
        assert fact["opened"] == fact["reads"] == {"ref": 0}, fact
    accepted(facts[2], 1)
    assert facts[2]["reads"]["ref"] > 0, facts[2]


@pytest.mark.parametrize(
    "example", ["E14-alias-conflict", "E15-multiple-sources", "E16-duplicate-key"]
)
def test_s07_ambiguous_descriptors_reject_before_any_read(
    tmp_path: Path, example: str
) -> None:
    """AK6607-S07-E14..E16: a descriptor or DesignMD envelope image that names a
    second MIME alias, a second typed source, or repeats a key is refused before the
    source is read or decoded; nothing falls through as harmless metadata."""
    encoded = b64(PIXELS)
    (inputs_dir(tmp_path) / "ref.png").write_bytes(PIXELS)
    file_part, plain = image("image_file", "ref.png"), image("image_base64", encoded)
    if example == "E14-alias-conflict":
        cases = [
            _enveloped(envelope(PIXELS, mimeType=_JPEG)),
            _enveloped(envelope(PIXELS, media_type=_JPEG)),
            one({**plain, "mime_type": _PNG}),
            one({"type": "image_base64", "data": encoded, "mediaType": _PNG}),
        ]
    elif example == "E15-multiple-sources":
        cases = [
            one({**plain, "url": "data:image/png;base64," + encoded}),
            one({**file_part, "data": encoded}),
            _enveloped(envelope(PIXELS, url="https://127.0.0.1/image.png")),
            _enveloped(envelope(PIXELS, path="ref.png")),
            _enveloped(envelope(PIXELS, **file_part)),
            _enveloped(envelope(PIXELS, data=encoded)),
        ]
    else:
        row = '"type":"image_base64","data":"%s","media_type":"image/png"' % encoded
        twice = '"imageDataBase64":"%s",' % encoded * 2
        inner = '{"images":[{%s"imageDataMimeType":"image/png",%s}]}' % (
            twice,
            '"pixelInspectionInputStatus":"%s"' % _ENVELOPE,
        )
        documents = [
            '{"visual":{%s,"data":"%s"},"text":"t"}' % (row, encoded),
            '{"visual":{%s,"media_type":"image/jpeg"},"text":"t"}' % row,
            '{"visual":{%s},"visual":"t","text":"t"}' % row,
        ]
        cases = [{"document": raw.encode()} for raw in documents]
        cases.append(_enveloped(inner))
    watch = {"ref": inputs_dir(tmp_path) / "ref.png"}
    for fact in run_cases(tmp_path, cases, watch=watch, needles=(encoded[-32:],)):
        refused(fact, _INVALID)
        assert fact["decode"] == 0 and fact["reads"] == {"ref": 0}, fact


def test_s08_image_url_without_canonical_base64_header_is_never_laundered(
    tmp_path: Path,
) -> None:
    """AK6607-S08: Given an image_url whose base64-looking body lacks the canonical
    ;base64 header; When the protected entry receives it; Then it rejects before any
    upstream split_data_uri normalization or send, and a normalized body is not proof."""
    encoded = b64(PIXELS)
    headers = [
        "",  # bare body: upstream split_data_uri would call it octet-stream data
        "data:image/png,",
        "data:image/png;foo=x;base64,",
        "data:image/png;charset=utf-8;base64,",
        "data:;base64,",
        "data:image/PNG;base64,",
        "DATA:image/png;base64,",
        " data:image/png;base64,",
        "data:image/png;base64, ",
        "data:image/png;base64,",  # the canonical control
    ]
    cases = [one(image("image_url", header + encoded)) for header in headers]
    facts = run_cases(tmp_path, cases)
    for fact in facts[:-1]:
        refused(fact, _INVALID)
        assert fact["decode"] == 0, fact
    accepted(facts[-1], 1)
    assert facts[-1]["occurrences"][0]["content_sha256"] == sha(PIXELS)


def _synthetic_admission(
    source: dict, root: Path
) -> tuple[bytes, SyntheticImageAuthority]:
    import time
    import uuid

    from dspx.image_admission import CEILINGS, canonical, digest
    from dspx.image_privacy import runtime_identity

    row = os.stat(root)
    now = time.time_ns() // 1_000_000
    record = {
        "schema_version": "dspx-image-admission-v2",
        "mode": "synthetic",
        "provider_kind": "openai-compatible",
        "model": "synthetic-vision-fixture",
        "canonical_base_endpoint": "http://127.0.0.1:8000/v1",
        "source_package_sha256": digest("source-v1", source),
        "candidate_manifest_sha256": source["candidate_manifest_sha256"],
        "runtime_identity_sha256": runtime_identity(),
        "decoder_profile_sha256": source["decoder_profile_sha256"],
        "request_plan": [
            {
                "plan_ordinal": 1,
                "predictor_slot": 0,
                "request_shape_sha256": "4" * 64,
                "image_occurrence_sequence": ["s000001"],
            }
        ],
        "limits": {**CEILINGS, "total_dispatch_allowance": 1},
        "deadlines": {
            "not_before_utc_ms": now - 1000,
            "expires_utc_ms": now + 60_000,
            "total_wall_ms": 30_000,
            "per_request_io_timeout_ms": 30_000,
        },
        "custody": {
            "custody_id": str(uuid.uuid4()),
            "caller_run_id": str(uuid.uuid4()),
            "caller_binding_sha256": "2" * 64,
            "root_dev": row.st_dev,
            "root_ino": row.st_ino,
            "caller_expectation_sha256": "3" * 64,
        },
        "approval_binding": dict.fromkeys(
            ("owning_ak_task", "operator_evidence_ref", "parent_confirmation_sha256")
        ),
    }
    raw = canonical(record)
    return raw, SyntheticImageAuthority(raw, "3" * 64, row.st_dev, row.st_ino)


def test_s13_same_filename_with_new_pixels_gets_new_identity(tmp_path: Path) -> None:
    """AK6607-S13: Given an unchanged descriptor and relative filename; When the bytes
    change before a new invocation; Then the rederived image commitment and source
    package identity change, and the old admission cannot approve the new bytes."""
    from dspx.image_admission import digest, validate_admission
    from dspx.image_privacy import runtime_identity

    document = {"visual": image("image_file", "ref.png"), "text": "t"}
    sources = []
    for shade in (0x10, 0x20):
        (inputs_dir(tmp_path) / "ref.png").write_bytes(gray_png(2, 2, shade=shade))
        (fact,) = run_cases(
            tmp_path, [{"document": document, "options": {"source": True}}]
        )
        accepted(fact, 1)
        sources.append(fact["source"])
    old, new = sources
    assert old["raw_input_file_sha256"] == new["raw_input_file_sha256"]
    assert [
        row["content_sha256"]
        for row in (*old["source_occurrences"], *new["source_occurrences"])
    ] == [
        sha(gray_png(2, 2, shade=0x10)),
        sha(gray_png(2, 2, shade=0x20)),
    ]
    # ubs:ignore -- public sha256 content commitments, not secrets
    assert digest("source-v1", old) != digest("source-v1", new)
    raw, authority = _synthetic_admission(old, tmp_path)
    identity = runtime_identity()
    approved = validate_admission(
        raw, source=old, authority=authority, runtime_identity_sha256=identity
    )
    assert approved.sha256
    with pytest.raises(ImageContractError, match="^image_admission_invalid$"):
        validate_admission(
            raw, source=new, authority=authority, runtime_identity_sha256=identity
        )


def test_s15_extra_envelope_key_is_refused_before_any_decode(tmp_path: Path) -> None:
    """S15-extra-envelope-key (outside the matrix rows): a DesignMD envelope or image
    carrying any key beyond the closed set, e.g. a `thumbnail` with the raw base64, is
    refused with a fixed code before any read or decode, so the payload can never
    reach the provider as plain text; neither the error nor the facts carry it."""
    encoded = b64(PIXELS)
    packet = json.loads(envelope(PIXELS, mimeType=_PNG))
    extra = [{"thumbnail": encoded}, {"label": "front"}, {"imageDataUrl": "x"}]
    rows = [{"images": [{**packet["images"][0], **item}]} for item in extra]
    rows.append({**packet, "thumbnail": encoded})
    cases = [_enveloped(json.dumps(row)) for row in [*rows, packet]]
    facts = run_cases(tmp_path, cases, needles=(encoded[-32:],))
    for fact in facts[:-1]:
        refused(fact, _INVALID)
        assert fact["decode"] == 0, fact
    accepted(
        facts[-1], 1
    )  # the closed set itself: data, MIME (and equal alias), status
    assert encoded[-32:] not in json.dumps(facts)


def test_harness_leak_check_sees_every_chain_link() -> None:
    """The error check behind every refusal row flags a payload in any chain link."""
    assert _clean_error(ImageContractError("image_budget"), ["secret-payload"])
    for context in (
        ValueError("secret-payload"),
        json.JSONDecodeError("bad", "secret-payload", 0),  # only in its .doc
    ):
        error = ImageContractError("image_budget")
        error.__context__, error.__suppress_context__ = context, True
        assert not _clean_error(error, ["secret-payload"])

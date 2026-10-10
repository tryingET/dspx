# summary: "Provider-free bounded decoder, fd, ingress and direct image preflight falsifiers."
# read_when:
#   - "Changing image source confinement or the optional frozen decoder subset."
#   - "Executing AK6756 rows S09-S12, S38-S41 (harness in test_image_source_io.py)."

from __future__ import annotations

import base64
from io import BytesIO
import json
import os
from pathlib import Path
import struct
import zlib

import pytest

from dspx.image_admission import ImageContractError, bounded_tree, canonical, sha
from dspx.image_admission import validate_source
from dspx.image_decoder import FrozenImageDecoder, scan_png, scan_jpeg
from dspx.image_input_contract import image_bytes, open_root, read_relative
from dspx.image_worker import worker_entry
from dspx.services.program_runtime_episode import _materialize_runtime_inputs
from test_image_source_io import PIXELS, accepted, b64, gray_png
from test_image_source_io import image, inline, inputs_dir, jpeg, one, refused
from test_image_source_io import run_cases, webp


def png(width: int = 1, height: int = 1, *, extra: bytes = b"") -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data))
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + extra
        + chunk(b"IDAT", zlib.compress(b"\0\xff\0\0"))
        + chunk(b"IEND", b"")
    )


def test_existing_episode_materializer_denies_images_without_context(
    tmp_path: Path,
) -> None:
    descriptor = {
        "type": "image_base64",
        "data": base64.b64encode(png()).decode("ascii"),
        "media_type": "image/png",
    }
    with pytest.raises(ImageContractError):
        _materialize_runtime_inputs(
            {"visual": descriptor}, inputs_path=tmp_path / "input.json"
        )


def test_strict_png_and_optional_frozen_decoder() -> None:
    assert scan_png(png()) == (1, 1)
    decoder = FrozenImageDecoder()
    assert decoder.decode(png(), "image/png") == (1, 1)
    assert len(decoder.profile_sha256) == 64


def test_baseline_jpeg_scanner_and_decoder() -> None:
    from PIL import Image

    out = BytesIO()
    with Image.new("RGB", (2, 3), "white") as fixture:
        fixture.save(out, format="JPEG")
    raw = out.getvalue()
    assert scan_jpeg(raw) == (2, 3)
    assert FrozenImageDecoder().decode(raw, "image/jpeg") == (2, 3)
    with pytest.raises(ImageContractError):
        scan_jpeg(raw + b"trailing")


@pytest.mark.parametrize("kind", [b"iCCP", b"tEXt", b"acTL", b"eXIf", b"zTXt", b"iTXt"])
def test_unsupported_png_chunks_refused_without_native_open(
    kind: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PIL import Image

    entered: list[bool] = []

    def forbidden(*args, **kwargs):
        entered.append(True)
        raise AssertionError("native open forbidden")

    monkeypatch.setattr(Image, "open", forbidden)
    data = b"bounded"
    extra = (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data))
    )
    with pytest.raises(ImageContractError):
        scan_png(png(extra=extra))
    assert not entered


@pytest.mark.parametrize("size", [(8193, 1), (1, 8193), (4001, 4000)])
def test_dimensions_reject_before_native_open(
    size, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PIL import Image

    entered: list[bool] = []

    def forbidden(*args, **kwargs):
        entered.append(True)
        raise AssertionError("native open forbidden")

    monkeypatch.setattr(Image, "open", forbidden)
    with pytest.raises(ImageContractError):
        scan_png(png(*size))
    assert not entered


@pytest.mark.parametrize(
    "source",
    [
        "",
        "QUJD ",
        "QUJD\n",
        "-_==",
        "QQ",
        "QQ===",
        "QR==",
        "data:image/png,QUJD",
        "data:image/png;foo=x;base64,QUJD",
        "https://127.0.0.1/image.png",
    ],
)
def test_strict_base64_never_repairs(source: str) -> None:
    with pytest.raises(ImageContractError):
        image_bytes(source, "image/png")


def test_fifo_open_is_nofollow_nonblocking_before_fstat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AK6607-S41: the FIFO leaf (no writer) is opened O_NONBLOCK|O_NOFOLLOW, then
    fstat-ed, and refused without any read; a blocking open would never return."""
    fifo = tmp_path / "image.png"
    os.mkfifo(fifo)
    identity = (fifo.stat().st_dev, fifo.stat().st_ino)
    root = open_root(tmp_path)
    real_open, real_fstat, real_read = os.open, os.fstat, os.read
    flags_seen: list[int] = []
    events: list[str] = []

    def spy(path, flags, *args, **kwargs):
        if path == fifo.name:
            flags_seen.append(flags)
            events.append("open")
        return real_open(path, flags, *args, **kwargs)

    def is_fifo(fd: int) -> bool:
        row = real_fstat(fd)
        return (row.st_dev, row.st_ino) == identity

    def fstat_spy(fd: int):
        if is_fifo(fd):
            events.append("fstat")
        return real_fstat(fd)

    def read_spy(fd: int, count: int) -> bytes:
        if is_fifo(fd):
            events.append("read")
        return real_read(fd, count)

    monkeypatch.setattr(os, "open", spy)
    monkeypatch.setattr(os, "fstat", fstat_spy)
    monkeypatch.setattr(os, "read", read_spy)
    try:
        with pytest.raises(ImageContractError, match="^image_input_invalid$"):
            read_relative(root, fifo.name, limit=1024)
    finally:
        os.close(root)
    assert len(flags_seen) == 1
    assert flags_seen[0] & os.O_NOFOLLOW and flags_seen[0] & os.O_NONBLOCK
    assert events[0] == "open" and "fstat" in events and "read" not in events


@pytest.mark.parametrize(
    "name",
    [
        "/absolute.png",
        "../escape.png",
        "a/../escape.png",
        "a\\b",
        "file:input",
        "~/input",
    ],
)
def test_confined_fd_denies_path_spellings(tmp_path: Path, name: str) -> None:
    root = open_root(tmp_path)
    try:
        with pytest.raises(ImageContractError):
            read_relative(root, name, limit=1024)
    finally:
        os.close(root)


def test_relocated_open_ancestor_rejects_before_leaf_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "base"
    child = base / "child"
    child.mkdir(parents=True)
    source = child / "image.png"
    source.write_bytes(png())
    identity = source.stat()
    root = open_root(base)
    real_open, real_read = os.open, os.read
    reads: list[bool] = []

    def open_spy(name, flags, *args, **kwargs):
        fd = real_open(name, flags, *args, **kwargs)
        if name == "child":
            child.rename(tmp_path / "escaped-child")
        return fd

    def read_spy(fd: int, size: int) -> bytes:
        row = os.fstat(fd)
        if (row.st_dev, row.st_ino) == (identity.st_dev, identity.st_ino):
            reads.append(True)
        return real_read(fd, size)

    monkeypatch.setattr(os, "open", open_spy)
    monkeypatch.setattr(os, "read", read_spy)
    try:
        with pytest.raises(ImageContractError):
            read_relative(root, "child/image.png", limit=1024)
    finally:
        os.close(root)
    assert not reads, "relocated ancestor allowed an out-of-root leaf read"


def test_symlink_and_changed_source_are_not_reopened(tmp_path: Path) -> None:
    real = tmp_path / "real.png"
    real.write_bytes(png())
    (tmp_path / "linked.png").symlink_to(real.name)
    root = open_root(tmp_path)
    try:
        assert read_relative(root, real.name, limit=1024) == png()
        with pytest.raises(ImageContractError):
            read_relative(root, "linked.png", limit=1024)
    finally:
        os.close(root)


@pytest.mark.parametrize(
    "mode", ["positive", "remote", "outside", "bad_data", "bad_media", "mixed_list"]
)
def test_supervised_prepare_source_membrane(tmp_path: Path, mode: str) -> None:
    """Given supervised prepare-only; When sources enter; Then no dispatch authority.

    Preparation precedes S -> A -> M; this is not shipped episode execution.
    Counters are asserted inside the clean worker and a safe status is required.
    """
    import json
    from dspx.image_admission import digest
    from dspx.image_supervision import supervise_image_worker

    source = tmp_path / "inputs"
    source.mkdir()
    pixels = png()
    leaf, outside = source / "ref.png", tmp_path / "outside.png"
    leaf.write_bytes(pixels)
    outside.write_bytes(pixels)
    leaf_stat, outside_stat = leaf.stat(), outside.stat()
    encoded = base64.b64encode(pixels).decode("ascii")
    file_part = {"type": "image_file", "path": leaf.name, "media_type": "image/png"}
    uri_part = {
        "type": "image_url",
        "url": "data:image/png;base64," + encoded,
        "media_type": "image/png",
    }
    visual: object = ["A", file_part, "B", uri_part, "C"]
    if mode == "remote":
        visual = {**uri_part, "url": "http://169.254.169.254/latest/meta-data/"}
    elif mode == "outside":
        visual = {**file_part, "path": str(outside)}
    elif mode == "bad_data":
        visual = {"type": "image_base64", "data": 7, "media_type": "image/png"}
    elif mode == "bad_media":
        visual = {"type": "image_base64", "data": encoded, "media_type": False}
    elif mode == "mixed_list":
        visual = [file_part, 7]
    (source / "inputs.json").write_text(
        json.dumps({"visual": visual, "text": "unchanged"})
    )
    root = open_root(source)
    params = {
        "mode": mode,
        "root_fd": root,
        "outside": str(outside),
        "outside_id": [outside_stat.st_dev, outside_stat.st_ino],
        "leaf_id": [leaf_stat.st_dev, leaf_stat.st_ino],
    }
    try:
        status = supervise_image_worker(
            "test_image_input_contract:_source_membrane_entry",
            params,
            fds=(root,),
            wall_ms=30_000,
        )
        assert status["status"] == "prepared" and status["live_authorized"] is False
        # ubs:ignore -- public sha256 commitment, not a secret
        assert status["commitment_sha256"] == digest("prepare-case", {"mode": mode})
    finally:
        os.close(root)


@worker_entry
def _source_membrane_entry(params):
    import httpx
    from dspx.image_admission import digest, sha
    from dspx.image_input_contract import ImageOccurrence, materialize_image_inputs
    from dspx.image_privacy import image_privacy
    from dspx.openai_compatible_provider import OpenAICompatibleProvider
    from dspx.stub_provider import StubProvider

    mode, root, outside = params["mode"], params["root_fd"], params["outside"]
    outside_id, leaf_id = tuple(params["outside_id"]), tuple(params["leaf_id"])
    raw = read_relative(root, "inputs.json", limit=1 << 20)
    pixels = read_relative(root, "ref.png", limit=1 << 20)
    calls = {
        "effects": 0,
        "outside_open": 0,
        "outside_read": 0,
        "leaf_read": 0,
        "decode": 0,
    }
    real_open, real_read, real_decode = os.open, os.read, FrozenImageDecoder.decode

    def deny(*args, **kwargs):
        calls["effects"] += 1
        raise AssertionError("provider-free preparation entered an effect")

    def open_spy(name, flags, *args, **kwargs):
        if os.fspath(name) == outside:
            calls["outside_open"] += 1
        return real_open(name, flags, *args, **kwargs)

    def read_spy(fd, count):
        row = os.fstat(fd)
        identity = (row.st_dev, row.st_ino)
        if identity == outside_id:
            calls["outside_read"] += 1
        if identity == leaf_id:
            calls["leaf_read"] += 1
        return real_read(fd, count)

    def decode_spy(self, data, media):
        calls["decode"] += 1
        return real_decode(self, data, media)

    with pytest.MonkeyPatch.context() as spies:
        for owner, name in (
            (httpx.Client, "__init__"),
            (httpx.Client, "send"),
            (StubProvider, "invoke"),
            (OpenAICompatibleProvider, "invoke"),
            (OpenAICompatibleProvider, "__init__"),
        ):
            spies.setattr(owner, name, deny)
        spies.setattr(os, "open", open_spy)
        spies.setattr(os, "read", read_spy)
        spies.setattr(FrozenImageDecoder, "decode", decode_spy)
        with image_privacy() as active:
            assert active.session is None and active.lm is None
            rejected = False
            try:
                context = materialize_image_inputs(
                    raw,
                    root_fd=root,
                    fields=("visual", "text"),
                    candidate_manifest_sha256="1" * 64,
                    candidate_source_sha256="2" * 64,
                    decoder=FrozenImageDecoder(),
                )
            except ImageContractError as error:
                assert str(error) == "image_input_invalid"
                rejected = True
            else:
                assert mode == "positive"
                assert context.materialized()["text"] == "unchanged"
                visual_text = context.materialized()["visual"]
                assert type(visual_text) is str
                parts = context.split(visual_text)
                images = [item for item in parts if type(item) is ImageOccurrence]
                assert [item.occurrence_id for item in images] == [
                    "s000001",
                    "s000002",
                ]
                assert all(
                    item.data == pixels and (item.width, item.height) == (1, 1)
                    for item in images
                )
                assert context.source["raw_input_file_sha256"] == sha(raw)
                assert [
                    row["content_sha256"]
                    for row in context.source["source_occurrences"]
                ] == [sha(pixels)] * 2
            assert active.session is None and active.lm is None
        assert rejected == (mode != "positive")
        assert calls["effects"] == calls["outside_open"] == calls["outside_read"] == 0
        if mode == "positive":
            assert calls["leaf_read"] > 0 and calls["decode"] == 2
        elif mode != "mixed_list":
            assert calls["leaf_read"] == calls["decode"] == 0
    return {
        "status": "prepared",
        "commitment_sha256": digest("prepare-case", {"mode": mode}),
        "fixture_evidence": True,
        "live_authorized": False,
        "failure_code": None,
    }


def _prepared() -> dict[str, object]:
    return {
        "status": "prepared",
        "commitment_sha256": "1" * 64,
        "fixture_evidence": True,
        "live_authorized": False,
        "failure_code": None,
    }


@worker_entry
def _history_entry(params):
    from dspy.clients.base_lm import GLOBAL_HISTORY
    from dspx.image_privacy import image_privacy

    # The clean interpreter never inherits the parent's history.
    assert GLOBAL_HISTORY == []
    if params["dirty"]:
        GLOBAL_HISTORY.append(object())
    entered = False
    try:
        with image_privacy():
            entered = True
    except ImageContractError as error:
        assert params["dirty"] and str(error) == "image_privacy"
    assert entered is not params["dirty"]
    return _prepared()


@pytest.mark.parametrize("dirty", [False, True])
def test_dirty_history_is_never_inherited_and_worker_dirt_refuses(dirty: bool) -> None:
    """Given a dirty parent; When a clean worker starts; Then nothing is inherited.

    A history entry created inside the worker itself still refuses, never normalized.
    """
    from dspy.clients.base_lm import GLOBAL_HISTORY
    from dspx.image_supervision import supervise_image_worker

    owned_sentinel = object()
    before = tuple(GLOBAL_HISTORY)
    GLOBAL_HISTORY.append(owned_sentinel)
    try:
        status = supervise_image_worker(
            "test_image_input_contract:_history_entry",
            {"dirty": dirty},
            wall_ms=30_000,
        )
        assert status == _prepared()
        assert GLOBAL_HISTORY[-1] is owned_sentinel
    finally:
        assert GLOBAL_HISTORY[-1] is owned_sentinel
        GLOBAL_HISTORY.pop()  # only this test's sentinel; no ambient history reset
    assert tuple(GLOBAL_HISTORY) == before


# AK6756: request-global budgets, repetition, confinement and decoder structure rows.
_BIG = (4095, 2047)  # 8_386_560 raw pixels; stored deflate pads to an exact file size


def _budget_cases(tmp_path: Path, example: str) -> list[dict]:
    inputs = inputs_dir(tmp_path)
    if example == "E01-occurrences":
        for n in range(1, 8):
            (inputs / f"img-{n}.png").write_bytes(gray_png(1, n))
        files = [image("image_file", f"img-{n}.png") for n in range(1, 8)]
        return [
            {"document": {"a": files[:4], "b": files[4:end]}, "fields": ("a", "b")}
            for end in (6, 7)
        ]
    if example == "E02-image-bytes":
        exact, over = gray_png(*_BIG, total=8_388_608), gray_png(*_BIG, total=8_388_609)
        (inputs / "exact.png").write_bytes(exact)
        (inputs / "over.png").write_bytes(over)
        files = [one(image("image_file", name)) for name in ("exact.png", "over.png")]
        return [*files, inline(exact), inline(over)]
    if example == "E03-summed-bytes":
        sizes = {"full": 8_388_608, "rest": 8_388_488, "more": 8_388_489, "tiny": 120}
        for name, size in sizes.items():
            shape = (1, 2) if name == "tiny" else _BIG
            (inputs / f"{name}.png").write_bytes(gray_png(*shape, total=size))
        assert 2 * sizes["full"] + sizes["rest"] + sizes["tiny"] == 25_165_824
        return [
            {
                "document": {
                    f: image("image_file", f"{n}.png") for f, n in zip("abcd", row)
                },
                "fields": tuple("abcd"),
            }
            for row in (
                ("full", "full", "rest", "tiny"),
                ("full", "full", "more", "tiny"),
            )
        ]
    sizes = {
        "E04-pixels": ((4000, 4000), (3727, 4293)),
        "E05-width": ((8192, 1), (8193, 1)),
        "E06-height": ((1, 8192), (1, 8193)),
    }[example]
    return [inline(gray_png(*size)) for size in sizes]


@pytest.mark.parametrize(
    "example",
    [
        "E01-occurrences",
        "E02-image-bytes",
        "E03-summed-bytes",
        "E04-pixels",
        "E05-width",
        "E06-height",
    ],
)
def test_s09_image_budgets_are_request_global_and_fail_closed(
    tmp_path: Path, example: str
) -> None:
    """AK6607-S09-E01..E06: Given valid synthetic images; When one budget is exactly
    at its limit it passes; When it exceeds it by one, rejection precedes any send and
    no earlier valid image survives as a partial request.

    Pixels cannot exceed 16_000_000 by exactly one: 16_000_001 has no factor pair
    within 8192 x 8192, so the smallest representable excess (3727 x 4293) is used.
    """
    limit = 16_000_001
    assert not any(limit % w == 0 and limit // w <= 8192 for w in range(1, 8193))
    assert 3727 * 4293 == 16_000_011
    cases = _budget_cases(tmp_path, example)
    name = {"E01-occurrences": "img-7.png", "E02-image-bytes": "over.png"}.get(example)
    watch = {"over": inputs_dir(tmp_path) / name} if name else None
    facts = run_cases(tmp_path, cases, watch=watch)
    if example == "E01-occurrences":
        accepted(facts[0], 6)
        refused(facts[1], "image_budget", decoded=True)
        assert facts[1]["decode"] == 6, facts[1]  # the seventh is never opened
        assert facts[1]["opened"] == facts[1]["reads"] == {"over": 0}, facts[1]
    elif example == "E02-image-bytes":
        accepted(facts[0], 1)
        accepted(facts[2], 1)
        assert facts[0]["occurrences"][0]["byte_count"] == 8_388_608
        for fact in (facts[1], facts[3]):
            refused(fact, "image_input_invalid")
            assert fact["decode"] == 0 and fact["reads"] == {"over": 0}, fact
    elif example == "E03-summed-bytes":
        accepted(facts[0], 4)
        assert sum(row["byte_count"] for row in facts[0]["occurrences"]) == 25_165_824
        refused(facts[1], "image_budget", decoded=True)
        assert facts[1]["decode"] == 3, facts[1]  # the fourth is never decoded
    else:
        accepted(facts[0], 1)
        assert facts[0]["opens"] == 2, facts[0]
        refused(facts[1], "image_budget")
        assert facts[1]["decode"] == 1, facts[1]  # structural header refusal only


def _nested(depth: int) -> object:
    value: object = "x"
    for _ in range(depth):
        value = [value]
    return value


def test_s09_input_json_bytes_depth_nodes_and_text_are_bounded(tmp_path: Path) -> None:
    """AK6607-S09-E07/E09/E11/E12: raw input JSON bytes, aggregate text characters,
    nesting depth and traversal nodes pass exactly at their limits and refuse one
    beyond them before any send (envelope metadata text cannot exist: its key set is
    closed, see S15-extra)."""
    visual = image("image_base64", b64(PIXELS))
    doc = json.dumps(one(visual)["document"]).encode()
    at_limit = doc + b" " * (41_943_040 - len(doc))
    text = {"visual": visual, "a": "x" * 500_000, "b": "y" * 500_000}
    over_text = {**text, "b": "y" * 500_001}

    # Exactly at the input ceilings (AK6810): "x" at depth 16, and 1 + 1 + 3 + 1 +
    # 4090 == 4096 nodes, checked with the production counter; one more refuses.
    deep = {"visual": visual, "text": _nested(15)}
    nodes = {"visual": visual, "text": ["x"] * 4090}
    for document, depth, count in ((deep, 15, 4096), (nodes, 16, 4095)):
        bounded_tree(document)
        with pytest.raises(ImageContractError, match="^image_budget$"):
            bounded_tree(document, max_depth=depth, max_nodes=count)
    cases = [
        {"document": at_limit},
        {"document": at_limit + b" "},
        {"document": at_limit + b" ", "options": {"input_limit": 41_943_041}},
        {"document": text, "fields": ("visual", "a", "b")},
        {"document": over_text, "fields": ("visual", "a", "b")},
        {"document": deep, "options": {"source": True}},
        {"document": {**deep, "text": _nested(16)}},
        {"document": nodes, "options": {"source": True}},
        {"document": {**nodes, "text": ["x"] * 4091}},
    ]
    facts = run_cases(
        tmp_path, cases, watch={"over": inputs_dir(tmp_path) / "case-1.json"}
    )
    # (code, stage, images decoded before the refusal; none survives as a partial)
    expected = [
        ("ok", None, 1),
        ("image_input_invalid", "read", 0),  # the production read cap refuses unread
        ("image_budget", "materialize", 0),  # the materializer's own JSON cap
        ("ok", None, 1),
        ("image_budget", "materialize", 1),
        ("ok", None, 1),
        ("image_input_invalid", "materialize", 0),
        ("ok", None, 1),
        ("image_input_invalid", "materialize", 0),
    ]
    for fact, (code, stage, decoded) in zip(facts, expected, strict=True):
        assert fact["decode"] == decoded, fact
        if code == "ok":
            accepted(fact, 1)
        else:
            refused(fact, code, decoded=bool(decoded))
            assert fact["stage"] == stage, fact
    assert facts[1]["reads"] == {"over": 0} and facts[1]["opened"] == {"over": 1}
    assert facts[3]["text_chars"] == 1_000_000
    # At the limits the derived commitments exist and fit one custody record.
    for fact, chars in ((facts[5], 1), (facts[7], 4090)):
        source = validate_source(fact["source"])
        assert len(canonical(source)) <= 65_536 and fact["text_chars"] == chars


def test_s09_s10_s11_actual_request_occurrences_and_bytes_are_counted(
    tmp_path: Path,
) -> None:
    """AK6607-S09-E08/E10, S10, S11: Given six materialized images (identical bytes
    in different fields and kinds), the actual ordered request is revalidated by the
    pre-send request builder: body bytes and total parts pass at their limit and fail
    one beyond; a seventh occurrence, identical bytes or a repeated demo image alike,
    is refused; deduplication never lowers the occurrence or byte budget; and a demo
    cannot even be bound or formatted (S11's repetition is refused by design)."""
    inputs = inputs_dir(tmp_path)
    (inputs / "ref.png").write_bytes(PIXELS)
    big = gray_png(*_BIG, total=8_388_608)
    (inputs / "big.png").write_bytes(big)
    kinds = [
        image("image_file", "ref.png"),
        image("image_base64", b64(PIXELS)),
        image("image_url", "data:image/png;base64," + b64(PIXELS)),
    ]
    seven = [kinds[n % 3] for n in range(7)]
    fields = tuple("abcdefg")
    distinct = [image("image_base64", b64(gray_png(1, n))) for n in range(1, 7)]
    facts = run_cases(
        tmp_path,
        [
            {"document": dict(zip(fields[:6], seven)), "fields": fields[:6]},
            {"document": dict(zip(fields, seven)), "fields": fields},
            {
                "document": dict(zip("abcd", [image("image_file", "big.png")] * 4)),
                "fields": tuple("abcd"),
            },
            {
                "document": {"visual": distinct},
                "fields": ("visual",),
                "options": {"post": ["budgets", "demo"]},
            },
        ],
    )
    accepted(facts[0], 6)
    rows = facts[0]["occurrences"]
    assert [row["occurrence_id"] for row in rows] == [f"s00000{n}" for n in range(1, 7)]
    assert {row["content_sha256"] for row in rows} == {sha(PIXELS)}
    assert [row["field_slot"] for row in rows] == list(range(6))
    refused(facts[1], "image_budget", decoded=True)
    assert facts[1]["decode"] == 6, facts[1]
    refused(facts[2], "image_budget", decoded=True)  # 4 x 8 MiB of one identical file
    assert facts[2]["decode"] == 3, facts[2]
    accepted(facts[3], 6)  # spies stay at zero through the post-materialization steps
    assert facts[3]["post"]["budgets"] == {
        "body_at_limit": "ok",
        "body_over": "image_budget",
        "parts_at_limit": "ok",
        "parts_over": "image_budget",
        "repeated": "image_budget",
    }
    assert facts[3]["post"]["demo"] == {
        "bind_clean": "ok",
        "bind_demo": "image_privacy",
        "format_demo": "image_privacy",
        "format_images": 6,
    }


def test_s12_local_reads_stay_inside_the_explicit_input_parent(tmp_path: Path) -> None:
    """AK6607-S12-E01..E10: Given an image_file path kind; When the materializer reads
    it; Then it refuses without opening or reading the forbidden target, and the
    public failure is the fixed code (the harness also checks the error chain and
    logs for every absolute fixture path)."""
    import stat

    inputs = inputs_dir(tmp_path)
    outside_dir = tmp_path / "outside-dir"
    (inputs / "a").mkdir()
    (inputs / "~").mkdir()
    (inputs / "child").mkdir()
    outside_dir.mkdir()
    for path in (
        inputs / "ref.png",
        inputs / "a" / "ref.png",
        inputs / "~" / "input",
        inputs / "child" / "image.png",
        tmp_path / "outside.png",
        outside_dir / "ref.png",
    ):
        path.write_bytes(PIXELS)
    (inputs / "big.png").write_bytes(gray_png(*_BIG, total=8_388_609))
    (inputs / "out-link.png").symlink_to("../outside.png")
    (inputs / "in-link.png").symlink_to("ref.png")
    (inputs / "out-dir").symlink_to("../outside-dir")
    (inputs / "in-dir").symlink_to("a")
    os.mkfifo(inputs / "pipe.png")
    os.mknod(inputs / "sock.png", stat.S_IFSOCK | 0o600)
    escaped = tmp_path / "escaped-child"
    paths = {
        "E01": [str(tmp_path / "outside.png"), str(inputs / "ref.png")],
        "E02": ["../outside.png", "a/../ref.png", "./ref.png"],
        "E03": ["~/input", "~"],
        "E04": ["out-link.png"],
        "E05": ["in-link.png"],
        "E06": ["out-dir/ref.png", "in-dir/ref.png"],
        "E07": ["pipe.png"],
        "E08": ["sock.png"],
        "E09": ["child/image.png"],
        "E10": ["big.png"],
    }
    cases = [
        {
            "document": {"visual": image("image_file", path), "text": "t"},
            "options": {"retarget": ["child", str(inputs / "child"), str(escaped)]}
            if example == "E09"
            else {},
        }
        for example, rows in paths.items()
        for path in rows
    ]
    watch = {
        "ref": inputs / "ref.png",
        "a_ref": inputs / "a" / "ref.png",
        "home": inputs / "~" / "input",
        "child": inputs / "child" / "image.png",
        "outside": tmp_path / "outside.png",
        "outside_dir": outside_dir / "ref.png",
        "pipe": inputs / "pipe.png",
        "sock": inputs / "sock.png",
        "big": inputs / "big.png",
    }
    facts = run_cases(
        tmp_path,
        [*cases, {"document": {"visual": image("image_file", "ref.png"), "text": "t"}}],
        watch=watch,
    )
    relocated = [path for rows in paths.values() for path in rows].index(
        "child/image.png"
    )
    assert facts[relocated]["written"] is True  # only the fixture's own relocation
    facts[relocated]["written"] = False
    for fact in facts[:-1]:
        refused(fact, "image_input_invalid")
        assert fact["decode"] == 0 and set(fact["reads"].values()) == {0}, fact
    opened = {
        name for fact in facts[:-1] for name, count in fact["opened"].items() if count
    }
    # Only two confined leaves were ever opened: the FIFO nonblocking and the
    # oversized file, each for its fstat. A relocated ancestor stops before its leaf.
    assert opened == {"pipe", "big"}, opened
    accepted(facts[-1], 1)
    assert facts[-1]["reads"]["ref"] > 0


def _ancillary(kind: bytes) -> bytes:
    payload = zlib.compress(b"metadata " * 512)
    data = {
        b"iCCP": b"profile\0\0" + payload,
        b"zTXt": b"Comment\0\0" + payload,
        b"iTXt": b"Comment\0\x01\0\0\0" + payload,
        b"tEXt": b"Comment\0bounded",
        b"eXIf": b"MM\0*\0\0\0\x08\0\0",
        b"acTL": struct.pack(">II", 1, 0),
    }[kind]
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data))
    )


def test_s38_s40_structure_and_dimensions_refuse_before_any_pillow_open(
    tmp_path: Path,
) -> None:
    """AK6607-S38/S40: Given a valid bounded PNG or baseline JPEG whose header exceeds
    a dimension limit, or a PNG carrying iCCP/zTXt/iTXt/tEXt/eXIf/APNG chunks; When
    the materializer validates it; Then Image.open, native decoders and metadata
    decompression stay at zero, and no chunk is stripped to make it acceptable."""
    oversized = [jpeg(8193, 1), jpeg(1, 8193), jpeg(4001, 4000)]
    chunks = [b"iCCP", b"zTXt", b"iTXt", b"tEXt", b"eXIf", b"acTL"]
    marked = [gray_png(2, 2, extra=_ancillary(kind)) for kind in chunks]
    controls = [jpeg(8192, 1), PIXELS]

    def case(raw: bytes, media: str) -> dict:
        return {
            "document": {"visual": image("image_base64", b64(raw), media), "text": "t"}
        }

    facts = run_cases(
        tmp_path,
        [case(raw, "image/jpeg") for raw in oversized]
        + [case(raw, "image/png") for raw in marked]
        + [case(controls[0], "image/jpeg"), case(controls[1], "image/png")],
        needles=tuple(b64(raw)[-40:] for raw in (*oversized, *marked)),
    )
    for fact in facts[:3]:
        refused(fact, "image_budget")  # opens == native == meta == 0
        assert fact["decode"] == 1, fact
    for fact in facts[3:9]:
        refused(fact, "image_decoder_invalid")
        assert fact["decode"] == 1, fact
    for fact, raw in zip(facts[9:], controls, strict=True):
        accepted(
            fact, 1
        )  # the spies do fire for an admitted image: two opens, one load
        assert (fact["opens"], fact["native"], fact["meta"]) == (2, 1, 0), fact
        assert fact["occurrences"][0]["content_sha256"] == sha(raw)


def _tamper(monkeypatch: pytest.MonkeyPatch, variant: str) -> None:
    from types import FunctionType

    from PIL import Image, ImageFile, JpegImagePlugin, PngImagePlugin

    def accept(prefix: bytes) -> bool:
        return True

    class Widened(PngImagePlugin.PngImageFile):
        pass

    class Impostor:  # borrows the real code object and globals, runs its own call
        def __init__(self) -> None:
            self.__code__, self.__globals__ = Image.open.__code__, vars(Image)
            self.__qualname__ = "open"

        def __call__(self, *args, **kwargs):
            Image.preinit()
            raise OSError("impostor open ran")

    registry = {"PNG": Image.OPEN["PNG"], "JPEG": Image.OPEN["JPEG"]}
    if variant in ("png_factory", "jpeg_accept"):
        key = variant[: -len("_factory")].upper() if "factory" in variant else "JPEG"
        entry = (
            (Widened, registry[key][1]) if key == "PNG" else (registry[key][0], accept)
        )
        monkeypatch.setitem(Image.OPEN, key, entry)
        return
    # Same code object, foreign globals: its OPEN maps PNG bytes to the JPEG plugin.
    namespace = {**vars(Image), "OPEN": {**Image.OPEN, "PNG": registry["JPEG"]}}
    clone = FunctionType(
        Image.open.__code__, namespace, "open", Image.open.__defaults__
    )
    target = {
        "open_clone": (Image, "open", clone),
        "open_impostor": (Image, "open", Impostor()),
        "module_accept": (PngImagePlugin, "_accept", accept),
        "plugin_origin": (PngImagePlugin, "__file__", JpegImagePlugin.__file__),
        "plugin_open": (PngImagePlugin.PngImageFile, "_open", lambda self: None),
        "bomb_check": (Image, "_decompression_bomb_check", lambda size: None),
        "load_truncated": (ImageFile, "LOAD_TRUNCATED_IMAGES", True),
        "max_pixels": (Image, "MAX_IMAGE_PIXELS", None),
        "text_chunk": (PngImagePlugin, "MAX_TEXT_CHUNK", 1 << 30),
        "text_memory": (PngImagePlugin, "MAX_TEXT_MEMORY", 1 << 30),
    }[variant]
    monkeypatch.setattr(*target)


def test_s39_frozen_formats_and_plugin_identity_cannot_be_widened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AK6607-S39: Given a valid PNG or baseline JPEG; When verification and reopen
    load run; Then both Image.open calls pass exactly formats ("PNG", "JPEG").
    Replacing an OPEN factory/accept, Image.open (even by a same-code clone or an
    object borrowing its code), a plugin's origin or code, or altering
    LOAD_TRUNCATED_IMAGES or another security constant refuses before any open; WebP
    is refused even though the installed plugin decodes it."""
    import sys

    from PIL import Image

    decoder, photo = FrozenImageDecoder(), jpeg()
    real_preinit, real_code = Image.preinit, Image.open.__code__
    calls: list[tuple[bool, object]] = []

    def preinit() -> None:  # runs inside Image.open, after its formats check
        frame = sys._getframe(1)
        calls.append((frame.f_code is real_code, frame.f_locals.get("formats")))
        real_preinit()

    with monkeypatch.context() as spy:
        spy.setattr(Image, "preinit", preinit)
        for raw, media in ((PIXELS, "image/png"), (photo, "image/jpeg")):
            assert decoder.decode(raw, media) == (2, 2)
            assert calls == [(True, ("PNG", "JPEG"))] * 2, media
            del calls[:]
        for variant in (
            "png_factory jpeg_accept open_clone open_impostor module_accept "
            "plugin_origin plugin_open bomb_check load_truncated max_pixels "
            "text_chunk text_memory"
        ).split():
            with monkeypatch.context() as tampered:
                _tamper(tampered, variant)
                for attempt in (
                    lambda: decoder.decode(PIXELS, "image/png"),
                    FrozenImageDecoder,
                ):
                    with pytest.raises(ImageContractError) as refusal:
                        attempt()
                    assert (refusal.value.code, calls) == (
                        "image_decoder_unavailable",
                        [],
                    ), variant
    raw = webp()
    with Image.open(BytesIO(raw)) as unrestricted:  # the installed plugin can decode it
        assert unrestricted.format == "WEBP"
    with pytest.raises(Image.UnidentifiedImageError):
        Image.open(BytesIO(raw), formats=("PNG", "JPEG"))
    for media in ("image/png", "image/jpeg", "image/webp"):
        with pytest.raises(ImageContractError, match="^image_decoder_invalid$"):
            decoder.decode(raw, media)
    assert decoder.decode(PIXELS, "image/png") == (2, 2)  # every tamper was undone

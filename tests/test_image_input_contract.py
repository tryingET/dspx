# summary: "Provider-free bounded decoder, fd, ingress and direct image preflight falsifiers."
# read_when:
#   - "Changing image source confinement or the optional frozen decoder subset."

from __future__ import annotations

import base64
from io import BytesIO
import os
from pathlib import Path
import struct
import zlib

import pytest

from dspx.image_admission import ImageContractError
from dspx.image_decoder import FrozenImageDecoder, scan_png, scan_jpeg
from dspx.image_input_contract import image_bytes, open_root, read_relative
from dspx.image_worker import worker_entry
from dspx.services.program_runtime_episode import _materialize_runtime_inputs


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


@pytest.mark.parametrize("kind", [b"iCCP", b"tEXt", b"acTL", b"eXIf", b"zTXt"])
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
    fifo = tmp_path / "image.png"
    os.mkfifo(fifo)
    root = open_root(tmp_path)
    real_open = os.open
    flags_seen: list[int] = []

    def spy(path, flags, *args, **kwargs):
        if path == fifo.name:
            flags_seen.append(flags)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", spy)
    try:
        with pytest.raises(ImageContractError):
            read_relative(root, fifo.name, limit=1024)
    finally:
        os.close(root)
    assert len(flags_seen) == 1
    assert flags_seen[0] & os.O_NOFOLLOW and flags_seen[0] & os.O_NONBLOCK


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

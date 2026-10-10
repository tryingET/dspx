# summary: "AK6938: PNG IDAT data inflates to exactly the IHDR scanline bytes and ends with its zlib stream."
# read_when:
#   - "Changing the PNG structure scan, its bounded IDAT inflation or decoder refusals."

from __future__ import annotations

from io import BytesIO
import struct
import zlib

import pytest

from dspx.image_admission import ImageContractError
from dspx.image_decoder import FrozenImageDecoder, scan_png
from test_image_source_io import accepted, b64, gray_png, image, refused, run_cases

_HIDDEN = b"HIDDEN-PAYLOAD"
_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
_LEGAL = [
    (color, depth)
    for color, depths in {
        0: (1, 2, 4, 8, 16),
        2: (8, 16),
        3: (1, 2, 4, 8),
        4: (8, 16),
        6: (8, 16),
    }.items()
    for depth in depths
]
_SHAPE = (5, 3, 2, 8)  # width, height, RGB, 8-bit: 3 rows of 1 + 15 bytes
_EXPECTED = 3 * (1 + 15)


def _chunk(kind: bytes, data: bytes) -> bytes:
    crc = struct.pack(">I", zlib.crc32(kind + data))
    return struct.pack(">I", len(data)) + kind + data + crc


def _scanlines(width: int, height: int, color: int, depth: int) -> bytes:
    row = (width * _CHANNELS[color] * depth + 7) // 8
    return b"".join(
        b"\0" + bytes((x * 29 + y * 7) & 0xFF for x in range(row))
        for y in range(height)
    )


def _png(
    width: int, height: int, color: int, depth: int, idat: list[bytes] | None = None
) -> bytes:
    if idat is None:
        idat = [zlib.compress(_scanlines(width, height, color, depth))]
    header = struct.pack(">IIBBBBB", width, height, depth, color, 0, 0, 0)
    palette = bytes(n & 0xFF for n in range(3 * 2**depth)) if color == 3 else b""
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + (_chunk(b"PLTE", palette) if palette else b"")
        + b"".join(_chunk(b"IDAT", part) for part in idat)
        + _chunk(b"IEND", b"")
    )


def _variants() -> dict[str, list[bytes]]:
    lines = _scanlines(*_SHAPE)
    good = zlib.compress(lines)
    check = struct.pack(">I", (zlib.adler32(lines) + 1) & 0xFFFFFFFF)
    return {
        "appended": [good + _HIDDEN],
        "appended-chunk": [good, _HIDDEN],
        "truncated-check": [good[:-3]],
        "truncated-deflate": [good[: len(good) // 2]],
        "empty": [b""],
        "too-many": [zlib.compress(lines + b"\0")],
        "too-few": [zlib.compress(lines[:-1])],
        "bomb": [zlib.compress(bytes(16 << 20), 9)],
        "corrupt-header": [b"\x78\x00" + good[2:]],
        "corrupt-block": [good[:2] + b"\x07" + good[3:]],
        "corrupt-check": [good[:-4] + check],
    }


@pytest.fixture(scope="module")
def decoder() -> FrozenImageDecoder:
    return FrozenImageDecoder()


@pytest.fixture
def pillow(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """The worker harness's decoder spies: Image.open, native zip decoder, metadata."""
    from PIL import Image, PngImagePlugin

    counts = dict.fromkeys(("opens", "native", "meta"), 0)

    def counted(key: str, original):
        def spy(*args, **kwargs):
            counts[key] += 1
            return original(*args, **kwargs)

        return spy

    monkeypatch.setattr(Image, "preinit", counted("opens", Image.preinit))
    monkeypatch.setattr(
        Image.core, "zip_decoder", counted("native", Image.core.zip_decoder)
    )
    monkeypatch.setattr(
        PngImagePlugin,
        "_safe_zlib_decompress",
        counted("meta", PngImagePlugin._safe_zlib_decompress),
    )
    return counts


@pytest.fixture
def inflation(monkeypatch: pytest.MonkeyPatch) -> list[list[int]]:
    """Record every decompress call as [max_length, produced bytes]."""
    calls: list[list[int]] = []
    real = zlib.decompressobj

    class Counting:
        def __init__(self, *args, **kwargs) -> None:
            self._inner = real(*args, **kwargs)

        def decompress(self, data: bytes, max_length: int = 0) -> bytes:
            calls.append([max_length, 0])  # recorded even when the stream is corrupt
            out = self._inner.decompress(data, max_length)
            calls[-1][1] = len(out)
            return out

        def __getattr__(self, name: str):
            return getattr(self._inner, name)

    monkeypatch.setattr(zlib, "decompressobj", Counting)
    return calls


@pytest.mark.parametrize("parts", [1, 3])
@pytest.mark.parametrize(("color", "depth"), _LEGAL)
def test_every_legal_colour_type_and_depth_still_decodes_with_matching_size(
    decoder: FrozenImageDecoder,
    pillow: dict[str, int],
    color: int,
    depth: int,
    parts: int,
) -> None:
    """Given a valid PNG of each legal colour type and bit depth, an odd width that
    leaves sub-byte rows partial, and its zlib stream in one or three IDAT chunks;
    When it is scanned and decoded; Then its IDAT inflates to exactly the IHDR
    scanline bytes and both the scanner and Pillow report the same size."""
    stream = zlib.compress(_scanlines(5, 3, color, depth))
    cut = len(stream) // parts
    idat = [stream[n * cut : (n + 1) * cut] for n in range(parts - 1)]
    raw = _png(5, 3, color, depth, [*idat, stream[(parts - 1) * cut :]])
    assert scan_png(raw) == (5, 3)
    assert decoder.decode(raw, "image/png") == (5, 3)
    assert pillow == {"opens": 2, "native": 1, "meta": 0}  # the spies are live


@pytest.mark.parametrize("variant", sorted(_variants()))
def test_idat_data_off_the_zlib_stream_end_refuses_before_any_pillow_open(
    decoder: FrozenImageDecoder,
    pillow: dict[str, int],
    inflation: list[list[int]],
    variant: str,
) -> None:
    """AK6938: Given a PNG whose IDAT data carries bytes after the zlib stream end, a
    truncated or corrupt stream, or one inflating to more or fewer bytes than IHDR's
    scanlines; When it is scanned or decoded; Then the fixed image_decoder_invalid
    code refuses, with neither payload nor chained cause, before Image.open, the
    native decoder or metadata decompression, and no inflation step ever produces
    more than one byte beyond the expected scanline size."""
    raw = _png(*_SHAPE, _variants()[variant])
    for attempt in (lambda: scan_png(raw), lambda: decoder.decode(raw, "image/png")):
        with pytest.raises(ImageContractError) as caught:
            attempt()
        error = caught.value
        assert (error.code, error.args, error.__cause__, error.__context__) == (
            "image_decoder_invalid",
            ("image_decoder_invalid",),
            None,
            None,
        ), variant
    assert pillow == {"opens": 0, "native": 0, "meta": 0}, variant
    assert inflation, variant  # the stream was inspected, not merely skipped
    assert sum(produced for _, produced in inflation) <= 2 * (_EXPECTED + 1), variant
    assert all(0 < limit <= _EXPECTED + 1 for limit, _ in inflation), variant


def test_unrestricted_pillow_admits_the_hidden_bytes_the_scanner_refuses() -> None:
    """The finding: Pillow 12.1.1 alone loads these, so the scanner is the guard."""
    from PIL import Image

    variants = _variants()
    for name in ("appended", "appended-chunk", "too-many", "truncated-check", "bomb"):
        raw = _png(*_SHAPE, variants[name])
        with Image.open(BytesIO(raw), formats=("PNG",)) as fixture:
            fixture.load()
            assert fixture.size == _SHAPE[:2], name


@pytest.mark.parametrize(
    "build",
    [
        lambda: gray_png(4095, 2047, total=8_388_608),  # stored blocks, 8 MiB, split
        lambda: gray_png(4000, 4000),  # 16_000_000 pixels
        lambda: gray_png(8192, 1),
        lambda: gray_png(1, 8192),
    ],
    ids=["bytes", "pixels", "width", "height"],
)
def test_images_at_the_limits_inflate_in_bounded_steps(
    inflation: list[list[int]], build
) -> None:
    """Given a PNG exactly at a byte, pixel, width or height limit; When it is scanned;
    Then it is admitted, its IDAT inflates to exactly its scanline bytes, and no
    single step produces more than 1 MiB + 1 bytes."""
    raw = build()
    width, height = struct.unpack(">II", raw[16:24])
    assert scan_png(raw) == (width, height)
    assert sum(produced for _, produced in inflation) == height * (1 + width)
    assert max(limit for limit, _ in inflation) <= (1 << 20) + 1


def test_hidden_idat_bytes_never_reach_a_request_through_the_clean_worker(
    tmp_path,
) -> None:
    """AK6938 through production materialization: each malformed PNG is refused with
    image_decoder_invalid after one decoder entry, Pillow's open, native decoder and
    metadata spies stay at zero, nothing is kept; the well-formed control passes."""
    variants = _variants()
    names = ("appended", "appended-chunk", "too-many", "too-few", "truncated-check")
    raws = [_png(*_SHAPE, variants[name]) for name in names] + [_png(*_SHAPE)]
    facts = run_cases(
        tmp_path,
        [
            {"document": {"visual": image("image_base64", b64(raw)), "text": "t"}}
            for raw in raws
        ],
        needles=(_HIDDEN.decode(), b64(_HIDDEN)),
    )
    for fact, name in zip(facts[:-1], names, strict=True):
        refused(fact, "image_decoder_invalid")
        assert fact["decode"] == 1, (name, fact)
    accepted(facts[-1], 1)
    assert (facts[-1]["opens"], facts[-1]["native"], facts[-1]["meta"]) == (2, 1, 0)

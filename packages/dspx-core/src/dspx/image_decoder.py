# summary: "Optional frozen Pillow PNG/baseline-JPEG decoder, with complete structural predimension refusal."
# read_when:
#   - "Changing admitted image formats, decoder identity or native resource boundaries."

from __future__ import annotations

from io import BytesIO
import importlib
import importlib.metadata
import importlib.util
from pathlib import Path
import struct
from types import CodeType
import warnings
import zlib

from .image_admission import ImageContractError, digest, require, sha

# Exact existing decoder closure. Unsupported platform/install is unavailable, not repaired.
_MEMBERS = {
    "PIL/Image.py": "3e5ecdcc3e8800749901e61c8108bd3c49063d3ba444fa0b62b0c18af022007f",
    "PIL/ImageFile.py": "5b9fd050b656798ecaab3d3870bba356ed244819ca66eee588b082aa85cef863",
    "PIL/_binary.py": "a5c33a00bd381b182619e2df707d55d4164710dc08ad01f4bb1849eebd0720bd",
    "PIL/ImagePalette.py": "b8f3ffa965924d68ad96fe16757b9c645e27fb664db078e0e07dfa83e269bb15",
    "PIL/PngImagePlugin.py": "5da5590ca2487f7ec2a7db5266bef89185854d57d5e4f619f507a8f2955b7aaa",
    "PIL/JpegImagePlugin.py": "9162d130d4d5adf707688a59a5c2ec68bb7169e7eb7a759d20b656c197d8119f",
    "PIL/_imaging.cpython-313-x86_64-linux-gnu.so": "c89ab4fdeda31f553cf149d52a2b33abfb25e1f0eeb9029f9a580d3239d4191e",
    "pillow-12.1.1.dist-info/METADATA": "17ff1f2d2adbc1ee618e97f149a81caaf4c3293d5a687227b6289199e70f2d17",
    "pillow.libs/libjpeg-32d42e18.so.62.4.0": "debdae3aabf89e399ed90be4cddc23a5bbca7a3ad3c8e2104cbcfe4782030c33",
    "pillow.libs/libtiff-295fd75c.so.6.2.0": "b2d14f0beb2e667c904ee697a8fe15bcc2d818249b83210e84b2852a3d331356",
    "pillow.libs/libopenjp2-94e588ba.so.2.5.4": "e727b69b0ccf612a38e3b573b1c0463bf6565f20601443c5458e398655cb230d",
    "pillow.libs/libxcb-64009ff3.so.1.1.0": "b7437ed16bae7ac4498049fd14e10d1bd1c3e7d15d0e5eab1d2ead42a83a49d1",
    "pillow.libs/libXau-154567c4.so.6.0.0": "05484d24bf78cb8ed03169f1cb067204d829cb7af21de8820400d29d115e4320",
    "pillow.libs/liblzma-61b1002e.so.5.8.2": "f165acd1f5452f8789768d184bb250c8296f428817129667626b5c01d6ca0594",
    "pillow.libs/libzstd-761a17b6.so.1.5.7": "8ca10640e6c6a996856f1a641995fc8f3b2d2557078493e1e124a19c68198c1f",
}
_SYSTEM = {
    "/usr/lib/libz.so.1": "9ba92a0b85dc9b659e8f5e596a69452cec801def6ece0883a8a2c1f032e52397",
    "/usr/lib/libpthread.so.0": "839b91403f89fa4c6888d50deb2b59cd0612f8cfe3d57dd9d6314832b4cb31ab",
    "/usr/lib/libc.so.6": "e221b10fee9ee4776d8f0f1701253bc06817f7a4dbe6c5292487277d0bf8ffff",
    "/usr/lib/libm.so.6": "965106704753eefe8c31ae7da6daba3ead3d18c52b19b5fcc41178bcc4aa999d",
    "/usr/lib64/ld-linux-x86-64.so.2": "d011113b7054c641c8ca064f58bcc23804fd2654a3dff2444dad06ddeda61bfb",
}


def dimensions(width: int, height: int) -> tuple[int, int]:
    require(
        0 < width <= 8192 and 0 < height <= 8192 and width * height <= 16_000_000,
        "image_budget",
    )
    return width, height


def scan_png(raw: bytes) -> tuple[int, int]:
    require(raw.startswith(b"\x89PNG\r\n\x1a\n"), "image_decoder_invalid")
    pos, count = 8, 0
    seen: set[bytes] = set()
    idat_ended = False
    width = height = color = depth = 0
    palette_count = 0
    while pos < len(raw):
        require(pos + 12 <= len(raw), "image_decoder_invalid")
        length = int.from_bytes(raw[pos : pos + 4], "big")
        kind = raw[pos + 4 : pos + 8]
        end = pos + 12 + length
        count += 1
        require(count <= 4096 and end <= len(raw), "image_decoder_invalid")
        data = raw[pos + 8 : end - 4]
        crc = int.from_bytes(raw[end - 4 : end], "big")
        require(zlib.crc32(kind + data) & 0xFFFFFFFF == crc, "image_decoder_invalid")
        require(
            kind
            in {
                b"IHDR",
                b"PLTE",
                b"tRNS",
                b"IDAT",
                b"IEND",
                b"sRGB",
                b"gAMA",
                b"cHRM",
                b"pHYs",
            },
            "image_decoder_invalid",
        )
        require(count != 1 or kind == b"IHDR", "image_decoder_invalid")
        if kind != b"IDAT":
            require(kind not in seen, "image_decoder_invalid")
        if kind == b"IHDR":
            require(count == 1 and length == 13, "image_decoder_invalid")
            width, height, depth, color, compression, filtering, interlace = (
                struct.unpack(">IIBBBBB", data)
            )
            dimensions(width, height)
            legal = {
                0: {1, 2, 4, 8, 16},
                2: {8, 16},
                3: {1, 2, 4, 8},
                4: {8, 16},
                6: {8, 16},
            }
            require(
                color in legal
                and depth in legal[color]
                and compression == filtering == interlace == 0,
                "image_decoder_invalid",
            )
        elif kind == b"PLTE":
            require(
                b"IDAT" not in seen
                and color in {2, 3, 6}
                and 0 < length <= 768
                and length % 3 == 0,
                "image_decoder_invalid",
            )
            palette_count = length // 3
            require(color != 3 or palette_count <= 2**depth, "image_decoder_invalid")
        elif kind == b"tRNS":
            require(b"IDAT" not in seen and color in {0, 2, 3}, "image_decoder_invalid")
            require(
                (color == 0 and length == 2)
                or (color == 2 and length == 6)
                or (color == 3 and b"PLTE" in seen and 0 < length <= palette_count),
                "image_decoder_invalid",
            )
        elif kind == b"IDAT":
            require(
                not idat_ended and (color != 3 or b"PLTE" in seen),
                "image_decoder_invalid",
            )
        elif kind == b"IEND":
            require(
                length == 0 and b"IDAT" in seen and end == len(raw),
                "image_decoder_invalid",
            )
            return width, height
        else:
            require(b"IDAT" not in seen, "image_decoder_invalid")
            require(
                length == {b"sRGB": 1, b"gAMA": 4, b"cHRM": 32, b"pHYs": 9}[kind],
                "image_decoder_invalid",
            )
            require(kind != b"sRGB" or data[0] <= 3, "image_decoder_invalid")
            require(kind != b"pHYs" or data[-1] <= 1, "image_decoder_invalid")
        if b"IDAT" in seen and kind != b"IDAT":
            idat_ended = True
        seen.add(kind)
        pos = end
    raise ImageContractError("image_decoder_invalid") from None


def scan_jpeg(raw: bytes) -> tuple[int, int]:
    require(raw.startswith(b"\xff\xd8"), "image_decoder_invalid")
    pos, segments = 2, 0
    components: dict[int, int] = {}
    tables: set[int] = set()
    huffman: set[tuple[int, int]] = set()
    width = height = 0
    jfif = False
    dri = False
    while pos < len(raw):
        require(
            pos + 4 <= len(raw) and raw[pos] == 255 and raw[pos + 1] not in {0, 255},
            "image_decoder_invalid",
        )
        marker = raw[pos + 1]
        length = int.from_bytes(raw[pos + 2 : pos + 4], "big")
        end = pos + 2 + length
        segments += 1
        require(
            segments <= 4096 and length >= 2 and end <= len(raw),
            "image_decoder_invalid",
        )
        data = raw[pos + 4 : end]
        if marker == 0xE0:
            require(
                not jfif
                and not components
                and len(data) == 14
                and data[:5] == b"JFIF\0"
                and data[5:7] in {b"\x01\x00", b"\x01\x01", b"\x01\x02"}
                and data[7] <= 2
                and data[12:] == b"\0\0",
                "image_decoder_invalid",
            )
            jfif = True
        elif marker == 0xC0:
            require(
                not components and len(data) >= 6 and data[0] == 8,
                "image_decoder_invalid",
            )
            height, width = struct.unpack(">HH", data[1:5])
            dimensions(width, height)
            number = data[5]
            require(
                number in {1, 3} and len(data) == 6 + 3 * number,
                "image_decoder_invalid",
            )
            for offset in range(6, len(data), 3):
                cid, sampling, table = data[offset : offset + 3]
                require(
                    cid not in components
                    and 1 <= sampling >> 4 <= 4
                    and 1 <= sampling & 15 <= 4
                    and table <= 3,
                    "image_decoder_invalid",
                )
                components[cid] = table
        elif marker == 0xDB:
            offset = 0
            while offset < len(data):
                ident = data[offset]
                require(
                    ident <= 3 and offset + 65 <= len(data), "image_decoder_invalid"
                )
                require(all(data[offset + 1 : offset + 65]), "image_decoder_invalid")
                tables.add(ident)
                offset += 65
            require(offset == len(data) and offset > 0, "image_decoder_invalid")
        elif marker == 0xC4:
            offset = 0
            while offset < len(data):
                require(offset + 17 <= len(data), "image_decoder_invalid")
                ident = data[offset]
                table_class, table = ident >> 4, ident & 15
                require(table_class in {0, 1} and table <= 3, "image_decoder_invalid")
                counts = data[offset + 1 : offset + 17]
                count = sum(counts)
                available = 1
                for size in counts:
                    available = available * 2 - size
                    require(available >= 0, "image_decoder_invalid")
                require(
                    0 < count <= 256 and offset + 17 + count <= len(data),
                    "image_decoder_invalid",
                )
                huffman.add((table_class, table))
                offset += 17 + count
            require(offset == len(data) and offset > 0, "image_decoder_invalid")
        elif marker == 0xDD:
            require(not dri and len(data) == 2, "image_decoder_invalid")
            dri = True
        elif marker == 0xDA:
            require(
                bool(components)
                and len(data) >= 6
                and data[0] == len(components)
                and len(data) == 1 + 2 * len(components) + 3
                and data[-3:] == b"\0\x3f\0",
                "image_decoder_invalid",
            )
            seen = set()
            for offset in range(1, len(data) - 3, 2):
                cid, selectors = data[offset : offset + 2]
                require(
                    cid in components
                    and cid not in seen
                    and components[cid] in tables
                    and (0, selectors >> 4) in huffman
                    and (1, selectors & 15) in huffman,
                    "image_decoder_invalid",
                )
                seen.add(cid)
            pos = end
            while pos < len(raw):
                if raw[pos] != 255:
                    pos += 1
                    continue
                require(pos + 1 < len(raw), "image_decoder_invalid")
                following = raw[pos + 1]
                if following == 0 or (dri and 0xD0 <= following <= 0xD7):
                    pos += 2
                elif following == 0xD9:
                    require(pos + 2 == len(raw), "image_decoder_invalid")
                    return width, height
                else:
                    raise ImageContractError("image_decoder_invalid") from None
            raise ImageContractError("image_decoder_invalid") from None
        else:
            raise ImageContractError("image_decoder_invalid") from None
        pos = end
    raise ImageContractError("image_decoder_invalid") from None


def _code_at(code: CodeType, name: str) -> CodeType | None:
    if code.co_qualname == name:
        return code
    for constant in code.co_consts:
        if type(constant) is CodeType:
            found = _code_at(constant, name)
            if found is not None:
                return found
    return None


class FrozenImageDecoder:
    """No source repair, stripping, transcode, automatic alternate-format attempt or install."""

    def __init__(self) -> None:
        try:
            require(
                importlib.metadata.version("Pillow") == "12.1.1",
                "image_decoder_unavailable",
            )
            spec = importlib.util.find_spec("PIL")
            if spec is None or spec.origin is None:
                raise ImageContractError("image_decoder_unavailable") from None
            self._site = Path(spec.origin).parent.parent
            self._image = importlib.import_module("PIL.Image")
            self._file = importlib.import_module("PIL.ImageFile")
            self._png = importlib.import_module("PIL.PngImagePlugin")
            self._jpeg = importlib.import_module("PIL.JpegImagePlugin")
            self.check()
            self.profile_sha256 = digest(
                "decoder-profile-v1",
                {
                    "schema_version": "decoder-profile-v1",
                    "version": "12.1.1",
                    "members": _MEMBERS,
                    "runtime_native_members": {
                        f"native{index}": value
                        for index, value in enumerate(_SYSTEM.values())
                    },
                    "formats": ["PNG", "JPEG"],
                    "max_image_pixels": 89_478_485,
                    "load_truncated_images": False,
                    "max_text_chunk": 1_048_576,
                    "max_text_memory": 67_108_864,
                },
            )
        except Exception:
            raise ImageContractError("image_decoder_unavailable") from None

    def check(self) -> None:
        try:
            for name, expected in _MEMBERS.items():
                path = self._site / name
                require(
                    path.is_file() and sha(path.read_bytes()) == expected,
                    "image_decoder_unavailable",
                )
            for name, expected in _SYSTEM.items():
                require(
                    sha(Path(name).read_bytes()) == expected,
                    "image_decoder_unavailable",
                )
            require(
                self._image.MAX_IMAGE_PIXELS == 89_478_485
                and self._file.LOAD_TRUNCATED_IMAGES is False
                and self._png.MAX_TEXT_CHUNK == 1_048_576
                and self._png.MAX_TEXT_MEMORY == 67_108_864,
                "image_decoder_unavailable",
            )
            for fmt, module, factory in (
                ("PNG", self._png, self._png.PngImageFile),
                ("JPEG", self._jpeg, self._jpeg.jpeg_factory),
            ):
                require(
                    self._image.OPEN.get(fmt) == (factory, module._accept),
                    "image_decoder_unavailable",
                )
            # Verify executable origins against compiled, already hash-bound module bytes.
            for module, functions in (
                (
                    self._image,
                    [self._image.open, self._image._decompression_bomb_check],
                ),
                (self._file, [self._file.ImageFile.load]),
                (
                    self._png,
                    [
                        self._png._accept,
                        self._png.PngImageFile._open,
                        self._png.PngImageFile.verify,
                    ],
                ),
                (
                    self._jpeg,
                    [
                        self._jpeg._accept,
                        self._jpeg.jpeg_factory,
                        self._jpeg.JpegImageFile._open,
                    ],
                ),
            ):
                path = self._site / _MEMBERS_KEY(module.__name__)
                require(
                    Path(module.__file__).resolve() == path.resolve(),
                    "image_decoder_unavailable",
                )
                for function in functions:
                    require(hasattr(function, "__code__"), "image_decoder_unavailable")
                    compiled = compile(
                        path.read_bytes(),
                        function.__code__.co_filename,
                        "exec",
                        dont_inherit=True,
                    )
                    require(
                        _code_at(compiled, function.__qualname__) == function.__code__,
                        "image_decoder_unavailable",
                    )
        except Exception:
            raise ImageContractError("image_decoder_unavailable") from None

    def decode(self, raw: bytes, media_type: str) -> tuple[int, int]:
        require(type(raw) is bytes and 0 < len(raw) <= 8_388_608, "image_budget")
        expected = {"image/png": "PNG", "image/jpeg": "JPEG"}.get(media_type)
        require(expected is not None, "image_decoder_invalid")
        size = scan_png(raw) if expected == "PNG" else scan_jpeg(raw)
        self.check()  # structural dimensions and metadata refusal precede any native open
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error")
                for verify in (True, False):
                    with self._image.open(
                        BytesIO(raw), formats=("PNG", "JPEG")
                    ) as image:
                        factory = (
                            self._png.PngImageFile
                            if expected == "PNG"
                            else self._jpeg.JpegImageFile
                        )
                        require(
                            type(image) is factory
                            and image.format == expected
                            and image.size == size
                            and image.mode
                            in {"1", "L", "LA", "P", "RGB", "RGBA", "I;16"}
                            and getattr(image, "n_frames", 1) == 1
                            and not getattr(image, "is_animated", False),
                            "image_decoder_invalid",
                        )
                        image.verify() if verify else image.load()
                        require(
                            image.size == size and getattr(image, "n_frames", 1) == 1,
                            "image_decoder_invalid",
                        )
            return size
        except Exception:
            raise ImageContractError("image_decoder_invalid") from None


def _MEMBERS_KEY(module: str) -> str:
    return module.replace(".", "/") + ".py"

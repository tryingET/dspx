"""Read-only PyPI reconciliation; never install, execute, or upload candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from collections.abc import Iterator
from http.client import HTTPException
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

PACKAGES = ("dspx-core", "dspx-forge")
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_FILE_BYTES = 512 * 1024 * 1024
CHUNK_BYTES = 64 * 1024
SOCKET_TIMEOUT = 30
READ_SECONDS = 120


class RegistryError(RuntimeError):
    """An unknown or conflicting observation blocks publication."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        # Validate the original URL only; never follow even an official redirect.
        return None


def _open(url: str) -> Any:
    request = Request(url, headers={"Accept-Encoding": "identity"})
    response = build_opener(_NoRedirect()).open(request, timeout=SOCKET_TIMEOUT)
    if response.status != 200 or response.geturl() != url:
        response.close()
        raise RegistryError("unexpected response status or URL")
    return response


def _chunks(response: Any, limit: int) -> Iterator[bytes]:
    total = 0
    deadline = time.monotonic() + READ_SECONDS
    while True:
        if time.monotonic() > deadline:
            raise RegistryError("response exceeded read deadline")
        # read1 avoids a single read waiting indefinitely on a trickling body.
        chunk = response.read1(min(CHUNK_BYTES, limit - total + 1))
        if time.monotonic() > deadline:
            raise RegistryError("response exceeded read deadline")
        total += len(chunk)
        if total > limit:
            raise RegistryError("response exceeds byte limit")
        if not chunk:
            return
        yield chunk


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RegistryError("duplicate JSON key")
        result[key] = value
    return result


def _bad_constant(value: str) -> None:
    raise RegistryError(f"invalid JSON constant: {value}")


def _metadata(package: str, version: str) -> dict[str, Any] | None:
    url = f"https://pypi.org/pypi/{package}/{quote(version, safe='')}/json"
    try:
        with _open(url) as response:
            data = b"".join(_chunks(response, MAX_JSON_BYTES))
    except HTTPError as exc:
        exc.close()
        if exc.code == 404:
            return None
        raise RegistryError(f"registry HTTP {exc.code}") from exc
    except (OSError, URLError, HTTPException) as exc:
        raise RegistryError("registry transport failed") from exc
    try:
        payload = json.loads(
            data,
            object_pairs_hook=_unique_object,
            parse_constant=_bad_constant,
        )
    except (ValueError, UnicodeError) as exc:
        raise RegistryError("malformed registry JSON") from exc
    if not isinstance(payload, dict):
        raise RegistryError("registry JSON must be an object")
    return payload


def _file_url(url: Any, filename: str) -> str:
    if not isinstance(url, str) or any(ord(c) <= 32 for c in url):
        raise RegistryError("invalid distribution URL")
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise RegistryError("invalid distribution URL") from exc
    if (
        parts.scheme != "https"
        or parts.netloc != "files.pythonhosted.org"
        or parts.query
        or parts.fragment
        or unquote(parts.path).rsplit("/", 1)[-1] != filename
    ):
        raise RegistryError("distribution URL is not official or has wrong filename")
    return url


def _inventory(
    payload: dict[str, Any] | None,
    package: str,
    version: str,
    expected: dict[str, dict[str, Any]],
) -> tuple[str, list[str], dict[str, str]]:
    if payload is None:
        return "absent", sorted(expected), {}
    info = payload.get("info")
    if (
        not isinstance(info, dict)
        or info.get("name") != package
        or info.get("version") != version
    ):
        raise RegistryError("registry package/version metadata mismatch")
    rows = payload.get("urls")
    if not isinstance(rows, list):
        raise RegistryError("registry inventory missing or malformed")
    urls: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise RegistryError("malformed registry file entry")
        filename = row.get("filename")
        if not isinstance(filename, str) or filename not in expected:
            raise RegistryError("unexpected registry filename")
        if filename in urls:
            raise RegistryError("duplicate registry filename")
        wanted = expected[filename]
        digests = row.get("digests")
        if (
            type(row.get("size")) is not int
            or row["size"] != wanted["bytes"]
            or not isinstance(digests, dict)
            or digests.get("sha256") != wanted["sha256"]
        ):
            raise RegistryError(f"registry size/hash mismatch: {filename}")
        if row.get("yanked") is not False:
            raise RegistryError(f"registry file yanked or unknown: {filename}")
        urls[filename] = _file_url(row.get("url"), filename)
    missing = sorted(expected.keys() - urls.keys())
    return ("partial_exact" if missing else "exact"), missing, urls


def _download(url: str, expected: dict[str, Any]) -> dict[str, Any]:
    digest = hashlib.sha256()
    size = 0
    try:
        with _open(url) as response:
            for chunk in _chunks(response, expected["bytes"]):
                digest.update(chunk)
                size += len(chunk)
    except HTTPError as exc:
        exc.close()
        raise RegistryError(f"distribution download HTTP {exc.code}") from exc
    except (OSError, URLError, HTTPException) as exc:
        raise RegistryError("distribution download failed") from exc
    if size != expected["bytes"] or digest.hexdigest() != expected["sha256"]:
        raise RegistryError(f"download size/hash mismatch: {expected['filename']}")
    return {
        "filename": expected["filename"],
        "package": expected["package"],
        "version": expected["version"],
        "url": url,
        "sha256": digest.hexdigest(),
        "bytes": size,
    }


def _stage(
    dist: Path, output: Path, missing: list[str], expected: dict[str, dict[str, Any]]
) -> None:
    output.mkdir(mode=0o700, exist_ok=False)
    created: list[Path] = []
    try:
        for filename in missing:
            target = output / filename
            digest = hashlib.sha256()
            size = 0
            with target.open("xb") as destination:
                created.append(target)
                with (dist / filename).open("rb") as source:
                    while chunk := source.read(CHUNK_BYTES):
                        size += len(chunk)
                        if size > expected[filename]["bytes"]:
                            raise RegistryError("local artifact changed during staging")
                        digest.update(chunk)
                        destination.write(chunk)
            if (
                size != expected[filename]["bytes"]
                or digest.hexdigest() != expected[filename]["sha256"]
            ):
                raise RegistryError("local artifact changed during staging")
    except BaseException:
        # Remove only files this invocation created, never pre-existing content.
        for target in created:
            target.unlink()
        output.rmdir()
        raise


def reconcile(
    dist: Path,
    expected_commit: str,
    expected_manifest_sha256: str,
    package: str,
    *,
    stage: Path | None = None,
    verify: bool = False,
    attempts: int = 12,
    delay: float = 10,
) -> dict[str, Any]:
    """Validate custody, observe PyPI, then stage missing files or prove all bytes.

    Polling is read-only and limited to absent/exact-subset inventories in verify
    mode. Callers must supply a new --stage path for stage mode. Success does not
    claim installation, owner approval, or paired-package release completion.
    """
    if package not in PACKAGES:
        raise RegistryError("unsupported package")
    if (verify and stage is not None) or (not verify and stage is None):
        raise RegistryError("stage mode requires output; verify forbids output")
    if type(attempts) is not int or not 1 <= attempts <= 12:
        raise RegistryError("attempts must be between 1 and 12")
    if not math.isfinite(delay) or not 0 <= delay <= 10:
        raise RegistryError("delay must be between 0 and 10 seconds")

    # Sibling import: privileged jobs need only stdlib and these reviewed scripts.
    from artifacts import load_and_verify

    manifest = load_and_verify(dist, expected_commit, expected_manifest_sha256)
    version = manifest["versions"][package]
    rows = [row for row in manifest["files"] if row["package"] == package]
    expected = {row["filename"]: row for row in rows}
    if len(rows) != 2 or len(expected) != 2:
        raise RegistryError("expected exactly two package artifacts")
    for filename, row in expected.items():
        if (
            Path(filename).name != filename
            or filename in (".", "..")
            or row["version"] != version
            or type(row["bytes"]) is not int
            or not 0 <= row["bytes"] <= MAX_FILE_BYTES
        ):
            raise RegistryError("invalid or oversized expected artifact")

    for attempt in range(attempts if verify else 1):
        state, missing, urls = _inventory(
            _metadata(package, version), package, version, expected
        )
        if not verify or state == "exact":
            break
        if attempt + 1 == attempts:
            raise RegistryError(
                f"registry remains {state} after {attempts} attempts; missing: {missing}"
            )
        time.sleep(delay)

    downloads = []
    if verify:
        downloads = [_download(urls[name], expected[name]) for name in sorted(urls)]
    elif stage is not None:
        _stage(dist, stage, missing, expected)
    return {
        "state": state,
        "missing": missing,
        "stage": str(stage) if stage is not None else None,
        "package": package,
        "version": version,
        "versions": manifest["versions"],
        "downloads": downloads,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("stage", "verify"))
    parser.add_argument("--dist", required=True, type=Path)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--package", required=True, choices=PACKAGES)
    parser.add_argument("--stage", type=Path)
    args = parser.parse_args(argv)
    try:
        result = reconcile(
            args.dist,
            args.commit,
            args.manifest_sha256,
            args.package,
            stage=args.stage,
            verify=args.mode == "verify",
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

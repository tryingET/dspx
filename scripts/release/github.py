"""Finalize approved exact-byte GitHub releases; caller owns approval/registry gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Any

REPO = "tryingET/dspx"
ROOT = f"repos/{REPO}"
MANIFEST = "release-manifest.json"
SHA = re.compile(r"[a-f0-9]{40}")


class ReleaseError(ValueError):
    """Conflicting, unknown, or indeterminate release state; never retry writes."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReleaseError(message)


def run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["gh", *args], stderr=subprocess.PIPE, timeout=300, check=False, **kwargs
    )


def api(path: str, *, absent_ok: bool = False) -> Any:
    result = run(
        ["api", "--hostname", "github.com", "--method", "GET", path],
        stdout=subprocess.PIPE,
    )
    if result.returncode:
        if absent_ok and re.search(rb"\(HTTP 404\)", result.stderr):
            return None
        raise ReleaseError(f"GitHub GET failed: {path}")
    data = json.loads(result.stdout)
    require(isinstance(data, (dict, list)), "unknown GitHub response")
    return data


def pages(path: str) -> list[dict[str, Any]]:
    rows = []
    for page in range(1, 101):
        batch = api(f"{path}?per_page=100&page={page}")
        require(isinstance(batch, list), "unknown GitHub inventory")
        require(all(isinstance(row, dict) for row in batch), "invalid inventory row")
        rows.extend(batch)
        if len(batch) < 100:
            return rows
    raise ReleaseError("GitHub inventory exceeds pagination budget")


def tag_commit(tag: str) -> str | None:
    ref = api(f"{ROOT}/git/ref/tags/{tag}", absent_ok=True)
    if ref is None:
        return None
    require(
        isinstance(ref, dict) and ref.get("ref") == f"refs/tags/{tag}", "wrong tag ref"
    )
    obj = ref.get("object")
    seen = set()
    for _ in range(16):
        require(isinstance(obj, dict), "unknown tag target")
        sha = obj.get("sha")
        require(
            isinstance(sha, str) and SHA.fullmatch(sha) is not None, "invalid tag SHA"
        )
        if obj.get("type") == "commit":
            return sha
        require(
            obj.get("type") == "tag" and sha not in seen, "invalid/cyclic tag target"
        )
        seen.add(sha)
        annotated = api(f"{ROOT}/git/tags/{sha}")
        require(
            isinstance(annotated, dict) and annotated.get("sha") == sha,
            "wrong tag object",
        )
        obj = annotated.get("object")
    raise ReleaseError("tag dereference budget exceeded")


def asset_bytes(asset_id: int, expected: dict[str, Any]) -> None:
    # API asset IDs avoid untrusted download URLs; temporary bytes never execute.
    with tempfile.TemporaryFile() as stream:
        result = run(
            [
                "api",
                "--hostname",
                "github.com",
                "--method",
                "GET",
                f"{ROOT}/releases/assets/{asset_id}",
                "-H",
                "Accept: application/octet-stream",
            ],
            stdout=stream,
        )
        require(result.returncode == 0, "asset download failed")
        require(stream.tell() == expected["bytes"], "downloaded asset size mismatch")
        stream.seek(0)
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
        require(
            digest.hexdigest() == expected["sha256"],
            "downloaded asset checksum mismatch",
        )


def inspect(
    tag: str, commit: str, expected: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    # The tag endpoint alone cannot discover drafts. List with writer credentials.
    releases = pages(f"{ROOT}/releases")
    require(
        all(isinstance(r.get("tag_name"), str) and r["tag_name"] for r in releases),
        "unknown release tag identity",
    )
    matches = [r for r in releases if r["tag_name"] == tag]
    require(len(matches) <= 1, "duplicate releases for tag")
    target = tag_commit(tag)
    require(target is None or target == commit, "tag points to wrong commit")
    if not matches:
        return {"state": "absent", "id": None, "missing": sorted(expected)}
    release = matches[0]
    identity = release.get("id")
    require(type(identity) is int and identity > 0, "unknown release identity")
    require(type(release.get("draft")) is bool, "unknown draft state")
    require(release.get("prerelease") is False, "unexpected prerelease state")
    draft = release["draft"]
    if draft:
        require(
            release.get("target_commitish") == commit,
            "unknown/conflicting draft target commit",
        )
    else:
        require(target == commit, "published release tag missing")
    assets = pages(f"{ROOT}/releases/{identity}/assets")
    names, ids = set(), set()
    for asset in assets:
        name, asset_id = asset.get("name"), asset.get("id")
        require(isinstance(name, str) and name in expected, "unexpected release asset")
        require(name not in names, "duplicate asset name")
        require(
            type(asset_id) is int and asset_id > 0 and asset_id not in ids,
            "invalid/duplicate asset ID",
        )
        names.add(name)
        ids.add(asset_id)
        row = expected[name]
        require(asset.get("state") == "uploaded", "asset upload incomplete")
        require(
            type(asset.get("size")) is int and asset["size"] == row["bytes"],
            "asset size mismatch",
        )
        asset_bytes(asset_id, row)
    missing = sorted(set(expected) - names)
    require(draft or not missing, "published release assets missing")
    return {
        "state": "draft" if draft else "published",
        "id": identity,
        "missing": missing,
    }


def mutate(
    args: list[str],
    tag: str,
    commit: str,
    expected: dict[str, dict[str, Any]],
    before: dict[str, Any],
    wanted: str,
) -> dict[str, Any]:
    failure = None
    try:
        result = run(
            ["release", *args, "--repo", f"github.com/{REPO}"], stdout=subprocess.PIPE
        )
        if result.returncode:
            failure = "nonzero mutation response"
    except (OSError, subprocess.SubprocessError):
        failure = "lost mutation response"
    # Exactly one reconciliation pass, including after a timeout or failed write.
    try:
        after = inspect(tag, commit, expected)
        require(
            before["id"] is None or after["id"] == before["id"],
            "release identity changed",
        )
        require(
            after["state"] == wanted and not after["missing"],
            "incomplete mutation readback",
        )
    except (
        ValueError,
        KeyError,
        TypeError,
        OSError,
        subprocess.SubprocessError,
    ) as exc:
        raise ReleaseError(
            f"effect_indeterminate: {tag}; readback failed: {exc}"
        ) from exc
    if failure:
        raise ReleaseError(
            f"effect_indeterminate: {tag}; {failure}; readback={after['state']}; no retry"
        )
    return after


def emit(event: dict[str, Any]) -> None:
    print(json.dumps(event, sort_keys=True), flush=True)


def finalize(
    dist: Path, commit: str, manifest_digest: str, *, check_only: bool = False
) -> None:
    from artifacts import load_and_verify

    manifest = load_and_verify(
        dist, commit, manifest_digest
    )  # Before any GitHub request.
    dist = dist.resolve()
    require(
        not any(c in str(dist) for c in "#*?[]"),
        "gh asset path contains label/glob syntax",
    )
    immutability = "unknown"
    try:
        repo = api(ROOT)
        require(
            isinstance(repo, dict) and repo.get("full_name") == REPO, "wrong repository"
        )
        value = repo.get("immutable_releases_enabled")
        if type(value) is bool:
            immutability = "enabled" if value else "disabled"
    except (ValueError, OSError, subprocess.SubprocessError):
        pass  # Configuration visibility is advisory, never an enabled claim.
    emit({"repository": REPO, "release_immutability": immutability})
    plans = []
    for package in ("dspx-core", "dspx-forge"):
        tag = f"{package}-v{manifest['versions'][package]}"
        expected = {
            r["filename"]: r for r in manifest["files"] if r["package"] == package
        }
        expected[MANIFEST] = {
            "sha256": manifest_digest,
            "bytes": (dist / MANIFEST).stat().st_size,
        }
        plans.append((package, tag, expected))
    # Detect conflicts in either component before the first mutation.
    for _, tag, expected in plans:
        inspect(tag, commit, expected)
    if check_only:
        emit(
            {
                "result": "preflight_only",
                "commit": commit,
                "manifest_sha256": manifest_digest,
            }
        )
        return
    for package, tag, expected in plans:
        before = inspect(tag, commit, expected)
        noop = before["state"] == "published"
        if before["state"] == "absent":
            before = mutate(
                [
                    "create",
                    tag,
                    *[str(dist / name) for name in sorted(expected)],
                    "--draft",
                    "--target",
                    commit,
                    "--title",
                    tag,
                    "--notes",
                    f"{package} {manifest['versions'][package]}.\nSource: {commit}.\n"
                    f"Release manifest SHA-256: {manifest_digest}.\n"
                    "Assets are the exact manifest-bound wheel, sdist, and manifest.",
                    "--latest=false",
                ],
                tag,
                commit,
                expected,
                before,
                "draft",
            )
        if before["state"] == "draft":
            if before["missing"]:
                before = mutate(
                    ["upload", tag, *[str(dist / name) for name in before["missing"]]],
                    tag,
                    commit,
                    expected,
                    before,
                    "draft",
                )
            mutate(
                [
                    "edit",
                    tag,
                    "--draft=false",
                    f"--latest={'true' if package == 'dspx-core' else 'false'}",
                ],
                tag,
                commit,
                expected,
                before,
                "published",
            )
        emit(
            {
                "tag": tag,
                "commit": commit,
                "manifest_sha256": manifest_digest,
                "result": "verified_noop" if noop else "verified_published",
            }
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.check_only:
            finalize(args.dist, args.commit, args.manifest_sha256, check_only=True)
        else:
            finalize(args.dist, args.commit, args.manifest_sha256)
    except (
        zipfile.BadZipFile,
        tarfile.TarError,
        ValueError,
        KeyError,
        TypeError,
        OSError,
        subprocess.SubprocessError,
    ) as exc:
        print(
            json.dumps({"result": "blocked_or_unverified", "error": str(exc)}),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

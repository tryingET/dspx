#!/usr/bin/env python3
# ---
# summary: "Builds and validates an atomic local bundle of unsigned Core release evidence."
# read_when:
#   - "Changing retained Core package evidence, local provenance, or release bundle publication."
# ---

from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any

from core_release_bundle_contract import (
    BUNDLE_SCHEMA as _CONTRACT_BUNDLE_SCHEMA,
    BUNDLE_SCHEMA_V1 as _CONTRACT_BUNDLE_SCHEMA_V1,
    BUNDLE_SCHEMA_V2 as _CONTRACT_BUNDLE_SCHEMA_V2,
    BUNDLE_SCHEMA_V3 as _CONTRACT_BUNDLE_SCHEMA_V3,
    PROVENANCE_SCHEMA as _CONTRACT_PROVENANCE_SCHEMA,
    _BUNDLE_CLAIMS as _CONTRACT_BUNDLE_CLAIMS,
    _BUNDLE_CLAIMS_V1 as _CONTRACT_BUNDLE_CLAIMS_V1,
    _BUNDLE_CLAIMS_V2 as _CONTRACT_BUNDLE_CLAIMS_V2,
    _BUNDLE_CLAIMS_V3 as _CONTRACT_BUNDLE_CLAIMS_V3,
    _FILE_ROLES as _CONTRACT_FILE_ROLES,
    _FILE_ROLES_V1 as _CONTRACT_FILE_ROLES_V1,
    _FILE_ROLES_V2 as _CONTRACT_FILE_ROLES_V2,
    _FILE_ROLES_V3 as _CONTRACT_FILE_ROLES_V3,
    _FIXED_NAMES,
    _ENVIRONMENT_SBOM_NAME,
    _INSTALLED_PROOF_NAME,
    _MANIFEST_NAME,
    _MAX_BUNDLE_BYTES,
    _PROVENANCE_NAME,
    _RELEASE_EVIDENCE_NAME,
    _SBOM_NAME,
    _archive_bytes,
    _json_bytes,
    _json_object,
    _mapping,
    _manifest,
    _provenance_statement,
    _release_subjects,
    _safe_member_name,
    _validate_bundle_raw,
    validate_bundle,
)
from core_release_evidence import validate_evidence
from core_release_evidence_io import (
    MAX_ARTIFACT_BYTES,
    MAX_JSON_BYTES,
    CoreReleaseEvidenceError,
    git as _git,
    sha256 as _sha256,
    stable_regular_bytes as _stable_regular_bytes,
    validate_sdist as _validate_sdist,
    wheel_metadata as _wheel_metadata,
)
from core_release_proof_contract import validate_installed_proof
from core_release_environment_sbom import (
    load_environment_sbom_bytes,
    validate_retained_environment_sbom,
)
from core_release_sbom import load_sbom_bytes, validate_sbom

# Re-exported for focused contract tests and downstream diagnostics.
BUNDLE_SCHEMA = _CONTRACT_BUNDLE_SCHEMA
BUNDLE_SCHEMA_V1 = _CONTRACT_BUNDLE_SCHEMA_V1
BUNDLE_SCHEMA_V2 = _CONTRACT_BUNDLE_SCHEMA_V2
BUNDLE_SCHEMA_V3 = _CONTRACT_BUNDLE_SCHEMA_V3
PROVENANCE_SCHEMA = _CONTRACT_PROVENANCE_SCHEMA
_BUNDLE_CLAIMS = _CONTRACT_BUNDLE_CLAIMS
_BUNDLE_CLAIMS_V1 = _CONTRACT_BUNDLE_CLAIMS_V1
_BUNDLE_CLAIMS_V2 = _CONTRACT_BUNDLE_CLAIMS_V2
_BUNDLE_CLAIMS_V3 = _CONTRACT_BUNDLE_CLAIMS_V3
_FILE_ROLES = _CONTRACT_FILE_ROLES
_FILE_ROLES_V1 = _CONTRACT_FILE_ROLES_V1
_FILE_ROLES_V2 = _CONTRACT_FILE_ROLES_V2
_FILE_ROLES_V3 = _CONTRACT_FILE_ROLES_V3


def _open_directory_path_no_follow(path: Path) -> int:
    absolute = path.absolute()
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open("/", flags)
    try:
        for component in absolute.parts[1:]:
            next_descriptor = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise CoreReleaseEvidenceError(
                "Core release bundle parent must be a directory"
            )
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _assert_directory_identity(path: Path, expected_descriptor: int) -> None:
    try:
        observed_descriptor = _open_directory_path_no_follow(path)
    except OSError as exc:
        raise CoreReleaseEvidenceError(
            f"Core release bundle parent identity cannot be revalidated: {exc}"
        ) from exc
    try:
        expected = os.fstat(expected_descriptor)
        observed = os.fstat(observed_descriptor)
        if (expected.st_dev, expected.st_ino) != (observed.st_dev, observed.st_ino):
            raise CoreReleaseEvidenceError(
                "Core release bundle parent identity changed"
            )
    finally:
        os.close(observed_descriptor)


def _relative_entry_exists(directory_descriptor: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False


def _create_temporary_file(
    directory_descriptor: int, output_name: str
) -> tuple[int, str]:
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    for _attempt in range(128):
        name = f".{output_name}.{secrets.token_hex(12)}.tmp"
        try:
            descriptor = os.open(name, flags, 0o600, dir_fd=directory_descriptor)
        except FileExistsError:
            continue
        try:
            os.fchmod(descriptor, 0o600)
        except Exception:
            os.close(descriptor)
            os.unlink(name, dir_fd=directory_descriptor)
            raise
        return descriptor, name
    raise CoreReleaseEvidenceError("cannot reserve a temporary release bundle file")


def _close_quietly(descriptor: int | None) -> None:
    if descriptor is None:
        return
    try:
        os.close(descriptor)
    except OSError:
        # Both descriptors have already been fsynced and all publication semantics
        # have been decided. A close error cannot make the retained bytes less durable.
        pass


def _write_descriptor(descriptor: int, raw: bytes) -> None:
    os.ftruncate(descriptor, 0)
    os.lseek(descriptor, 0, os.SEEK_SET)
    offset = 0
    while offset < len(raw):
        written = os.write(descriptor, raw[offset:])
        if written <= 0:
            raise CoreReleaseEvidenceError("Core release bundle write made no progress")
        offset += written
    os.fsync(descriptor)


def _descriptor_bytes(descriptor: int, *, label: str, limit: int) -> bytes:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
        raise CoreReleaseEvidenceError(f"{label} is invalid or oversized")
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(descriptor, min(1024 * 1024, limit + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > limit:
            raise CoreReleaseEvidenceError(f"{label} exceeds {limit} bytes")
    after = os.fstat(descriptor)
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise CoreReleaseEvidenceError(f"{label} changed while reading")
    return b"".join(chunks)


def _source_observation(repo_root: Path) -> dict[str, object]:
    repo = repo_root.resolve()
    commit_before = _git(repo, "rev-parse", "HEAD")
    status_before = _git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    commit_after = _git(repo, "rev-parse", "HEAD")
    status_after = _git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    if (commit_before, status_before) != (commit_after, status_after):
        raise CoreReleaseEvidenceError(
            "repository source observation changed during bundle preflight"
        )
    dirty = bool(status_before)
    return {
        "git_commit": commit_before,
        "tree_state": "dirty" if dirty else "clean",
        "commit_binding_status": (
            "working_tree_not_commit_bound" if dirty else "commit_bound_clean_tree"
        ),
    }


def _cross_validate_inputs(
    *,
    expected_source: Mapping[str, object],
    wheel_name: str,
    wheel_raw: bytes,
    sdist_name: str,
    sdist_raw: bytes,
    proof_raw: bytes,
    release_raw: bytes,
    sbom_raw: bytes | None,
    environment_sbom_raw: bytes | None,
) -> Mapping[str, Any]:
    release = _json_object(release_raw, "Core release evidence")
    validate_evidence(release)
    package = _mapping(release.get("package"), "release evidence package")
    package_name = str(package["name"])
    package_version = str(package["version"])
    observed_name, observed_version = _wheel_metadata(wheel_raw)
    if (observed_name, observed_version) != (package_name, package_version):
        raise CoreReleaseEvidenceError("bundle wheel package identity drift")
    _validate_sdist(
        sdist_raw,
        expected_name=package_name,
        expected_version=package_version,
    )
    release_schema = release.get("schema_version")
    if environment_sbom_raw is not None and sbom_raw is None:
        raise CoreReleaseEvidenceError(
            "resolved environment SBOM requires a retained exact-wheel SBOM"
        )
    if sbom_raw is None:
        if release_schema != "dspx-core-release-evidence-v1":
            raise CoreReleaseEvidenceError(
                "newer release evidence requires a retained SBOM"
            )
    else:
        expected_schema = (
            "dspx-core-release-evidence-v3"
            if environment_sbom_raw is not None
            else "dspx-core-release-evidence-v2"
        )
        if release_schema != expected_schema:
            raise CoreReleaseEvidenceError(
                "retained SBOM set does not match release evidence schema"
                if environment_sbom_raw is not None
                else "retained SBOM requires v2 release evidence"
            )
        validate_sbom(
            load_sbom_bytes(sbom_raw),
            wheel_raw=wheel_raw,
            wheel_filename=wheel_name,
        )
        sbom_summary = _mapping(release.get("sbom"), "release evidence SBOM")
        if sbom_summary.get("sha256") != _sha256(sbom_raw) or sbom_summary.get(
            "wheel_sha256"
        ) != _sha256(wheel_raw):
            raise CoreReleaseEvidenceError("release evidence SBOM binding drift")
        if environment_sbom_raw is not None:
            validate_retained_environment_sbom(
                load_environment_sbom_bytes(environment_sbom_raw),
                wheel_raw=wheel_raw,
                wheel_filename=wheel_name,
                installed_proof_raw=proof_raw,
            )
            environment_summary = _mapping(
                release.get("resolved_environment_sbom"),
                "resolved environment SBOM summary",
            )
            if (
                environment_summary.get("sha256") != _sha256(environment_sbom_raw)
                or environment_summary.get("wheel_sha256") != _sha256(wheel_raw)
                or environment_summary.get("installed_proof_sha256")
                != _sha256(proof_raw)
            ):
                raise CoreReleaseEvidenceError(
                    "release evidence resolved environment SBOM binding drift"
                )

    subjects = _release_subjects(release)
    for role, filename, raw in (
        ("core-wheel", wheel_name, wheel_raw),
        ("core-sdist", sdist_name, sdist_raw),
    ):
        subject = subjects.get(role)
        if subject is None:
            raise CoreReleaseEvidenceError(f"release evidence lacks {role} subject")
        expected = {
            "role": role,
            "filename": filename,
            "size": len(raw),
            "sha256": _sha256(raw),
        }
        if dict(subject) != expected:
            raise CoreReleaseEvidenceError(f"release evidence {role} subject drift")

    installed = _mapping(
        release.get("installed_wheel_proof"), "installed wheel proof summary"
    )
    if installed.get("sha256") != _sha256(proof_raw):
        raise CoreReleaseEvidenceError("installed proof retained-byte hash drift")
    proof = _json_object(proof_raw, "installed Core proof")
    validate_installed_proof(
        proof,
        expected_name=package_name,
        expected_version=package_version,
        expected_wheel_filename=wheel_name,
        expected_wheel_sha256=_sha256(wheel_raw),
    )

    source = _mapping(release.get("source"), "release evidence source")
    if dict(source) != dict(expected_source):
        raise CoreReleaseEvidenceError("release evidence source observation drift")
    return release


def build_bundle(
    *,
    repo_root: Path,
    wheel_path: Path,
    sdist_path: Path,
    installed_proof_path: Path,
    release_evidence_path: Path,
    sbom_path: Path | None = None,
    resolved_environment_sbom_path: Path | None = None,
    out_path: Path,
) -> dict[str, Any]:
    wheel_raw = _stable_regular_bytes(
        wheel_path, label="Core wheel", limit=MAX_ARTIFACT_BYTES
    )
    sdist_raw = _stable_regular_bytes(
        sdist_path, label="Core sdist", limit=MAX_ARTIFACT_BYTES
    )
    proof_raw = _stable_regular_bytes(
        installed_proof_path, label="installed Core proof", limit=MAX_JSON_BYTES
    )
    release_raw = _stable_regular_bytes(
        release_evidence_path, label="Core release evidence", limit=MAX_JSON_BYTES
    )
    sbom_raw = (
        _stable_regular_bytes(sbom_path, label="Core wheel SBOM", limit=MAX_JSON_BYTES)
        if sbom_path is not None
        else None
    )
    environment_sbom_raw = (
        _stable_regular_bytes(
            resolved_environment_sbom_path,
            label="resolved environment SBOM",
            limit=MAX_JSON_BYTES,
        )
        if resolved_environment_sbom_path is not None
        else None
    )
    wheel_name = _safe_member_name(wheel_path.name, "Core wheel")
    sdist_name = _safe_member_name(sdist_path.name, "Core sdist")
    if wheel_name == sdist_name or {wheel_name, sdist_name} & _FIXED_NAMES:
        raise CoreReleaseEvidenceError("Core release bundle filename collision")
    output = out_path.absolute()
    output_name = _safe_member_name(output.name, "Core release bundle output")
    source_paths = {
        path.absolute()
        for path in (
            wheel_path,
            sdist_path,
            installed_proof_path,
            release_evidence_path,
        )
    }
    if sbom_path is not None:
        source_paths.add(sbom_path.absolute())
    if resolved_environment_sbom_path is not None:
        source_paths.add(resolved_environment_sbom_path.absolute())
    if output in source_paths:
        raise CoreReleaseEvidenceError("Core release bundle output overlaps an input")
    parent = output.parent
    try:
        parent_descriptor = _open_directory_path_no_follow(parent)
    except OSError as exc:
        raise CoreReleaseEvidenceError(
            f"Core release bundle parent is unavailable or symlinked: {exc}"
        ) from exc

    temporary_descriptor: int | None = None
    temporary_name: str | None = None
    published = False
    try:
        if _relative_entry_exists(parent_descriptor, output_name):
            raise CoreReleaseEvidenceError(
                f"Core release bundle output already exists: {output}"
            )
        source_before = _source_observation(repo_root)
        release = _cross_validate_inputs(
            expected_source=source_before,
            wheel_name=wheel_name,
            wheel_raw=wheel_raw,
            sdist_name=sdist_name,
            sdist_raw=sdist_raw,
            proof_raw=proof_raw,
            release_raw=release_raw,
            sbom_raw=sbom_raw,
            environment_sbom_raw=environment_sbom_raw,
        )
        source_after = _source_observation(repo_root)
        if source_after != source_before:
            raise CoreReleaseEvidenceError(
                "repository source observation changed during bundle construction"
            )

        provenance_raw = _json_bytes(_provenance_statement(release))
        member_roles: dict[str, tuple[str, bytes]] = {
            wheel_name: ("core-wheel", wheel_raw),
            sdist_name: ("core-sdist", sdist_raw),
            _INSTALLED_PROOF_NAME: ("installed-proof", proof_raw),
            _RELEASE_EVIDENCE_NAME: ("release-evidence", release_raw),
            _PROVENANCE_NAME: ("local-build-provenance", provenance_raw),
        }
        if sbom_raw is not None:
            member_roles[_SBOM_NAME] = ("core-sbom", sbom_raw)
        if environment_sbom_raw is not None:
            member_roles[_ENVIRONMENT_SBOM_NAME] = (
                "core-installed-environment-sbom",
                environment_sbom_raw,
            )
        manifest_raw = _json_bytes(_manifest(release, member_roles))
        archive_members = {
            filename: raw for filename, (_role, raw) in member_roles.items()
        }
        archive_members[_MANIFEST_NAME] = manifest_raw
        archive_raw = _archive_bytes(archive_members)

        temporary_descriptor, temporary_name = _create_temporary_file(
            parent_descriptor, output_name
        )
        _write_descriptor(temporary_descriptor, archive_raw)
        observed_raw = _descriptor_bytes(
            temporary_descriptor,
            label="temporary Core release bundle",
            limit=_MAX_BUNDLE_BYTES,
        )
        manifest = _validate_bundle_raw(observed_raw)
        _assert_directory_identity(parent, parent_descriptor)
        if _relative_entry_exists(parent_descriptor, output_name):
            raise CoreReleaseEvidenceError(
                f"Core release bundle output already exists: {output}"
            )
        try:
            os.link(
                temporary_name,
                output_name,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileExistsError as exc:
            raise CoreReleaseEvidenceError(
                f"Core release bundle output already exists: {output}"
            ) from exc
        published = True
        try:
            os.fsync(parent_descriptor)
            _assert_directory_identity(parent, parent_descriptor)
            output_stat = os.stat(
                output_name, dir_fd=parent_descriptor, follow_symlinks=False
            )
            temporary_stat = os.fstat(temporary_descriptor)
            if (output_stat.st_dev, output_stat.st_ino) != (
                temporary_stat.st_dev,
                temporary_stat.st_ino,
            ):
                raise CoreReleaseEvidenceError(
                    "published Core release bundle identity drift"
                )
            _validate_bundle_raw(
                _descriptor_bytes(
                    temporary_descriptor,
                    label="published Core release bundle",
                    limit=_MAX_BUNDLE_BYTES,
                )
            )
            os.unlink(temporary_name, dir_fd=parent_descriptor)
            temporary_name = None
            os.fsync(parent_descriptor)
        except Exception as exc:
            raise CoreReleaseEvidenceError(
                f"Core release bundle publication effect is indeterminate: {exc}"
            ) from exc
        return manifest
    except Exception as exc:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=parent_descriptor)
            except FileNotFoundError:
                pass
            except OSError as cleanup_exc:
                if not published:
                    raise CoreReleaseEvidenceError(
                        f"Core release bundle cleanup failed: {cleanup_exc}"
                    ) from exc
        if published and not (
            isinstance(exc, CoreReleaseEvidenceError)
            and "effect is indeterminate" in str(exc)
        ):
            raise CoreReleaseEvidenceError(
                f"Core release bundle publication effect is indeterminate: {exc}"
            ) from exc
        raise
    finally:
        _close_quietly(temporary_descriptor)
        _close_quietly(parent_descriptor)


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--repo-root", type=Path, required=True)
    build.add_argument("--wheel", type=Path, required=True)
    build.add_argument("--sdist", type=Path, required=True)
    build.add_argument("--installed-proof", type=Path, required=True)
    build.add_argument("--release-evidence", type=Path, required=True)
    build.add_argument("--sbom", type=Path)
    build.add_argument("--resolved-environment-sbom", type=Path)
    build.add_argument("--out", type=Path, required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "build":
        payload = build_bundle(
            repo_root=args.repo_root,
            wheel_path=args.wheel,
            sdist_path=args.sdist,
            installed_proof_path=args.installed_proof,
            release_evidence_path=args.release_evidence,
            sbom_path=args.sbom,
            resolved_environment_sbom_path=args.resolved_environment_sbom,
            out_path=args.out,
        )
        print(json.dumps(payload, sort_keys=True))
        return 0
    payload = validate_bundle(args.bundle)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CoreReleaseEvidenceError as exc:
        raise SystemExit(f"Core release bundle failed: {exc}") from exc

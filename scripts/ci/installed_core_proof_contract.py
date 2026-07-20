# summary: "Validates behavior and Oracle evidence semantics for installed Core package proof."
# read_when:
#   - "Changing installed Core behavior-evidence or Oracle-evidence proof claims."

from __future__ import annotations

from collections.abc import Mapping
import importlib.util
from importlib.metadata import PackageNotFoundError, distribution, version
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any, cast
from urllib.parse import unquote, urlparse

from installed_core_proof_io import InstalledCoreGoldenPathError

GOLDEN_INTENT = {
    "name": "InstalledWheelTicketProgram",
    "objective": "Classify support ticket urgency from the supplied ticket text.",
    "inputs": ["ticket_text"],
    "outputs": ["urgency"],
    "metric": "exact_match",
    "examples": [
        {
            "inputs": {"ticket_text": "Production outage for all users"},
            "outputs": {"urgency": "high"},
        }
    ],
}
EXPECTED_NORMALIZED_INTENT = {
    "capabilities": {},
    "constraints": [],
    "dataset": {},
    "datasets": {},
    "examples": GOLDEN_INTENT["examples"],
    "input_fields": [],
    "inputs": GOLDEN_INTENT["inputs"],
    "jury": {},
    "metric": GOLDEN_INTENT["metric"],
    "name": GOLDEN_INTENT["name"],
    "objective": GOLDEN_INTENT["objective"],
    "options": {},
    "output_fields": [],
    "outputs": GOLDEN_INTENT["outputs"],
    "promotion": {},
    "quality_criteria": [],
    "runtime": {},
    "schema_version": "program-intent-v2",
    "task_type": "single_module",
    "topology": {},
}


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _stable_wheel_hash(path: Path) -> str:
    lexical = path.absolute()
    before = lexical.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise InstalledCoreGoldenPathError(
            "installed Core wheel must be a non-symlink regular file"
        )
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(lexical, flags)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise InstalledCoreGoldenPathError(
                "installed Core wheel changed before verification"
            )
        digest = hashlib.sha256()
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
        after = os.fstat(descriptor)
        if (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
        ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise InstalledCoreGoldenPathError(
                "installed Core wheel changed while verifying"
            )
        return digest.hexdigest()
    finally:
        os.close(descriptor)


def verify_install_origin(
    *,
    venv_root: Path,
    repo_root: Path,
    wheel_path: Path | None = None,
    expected_wheel_sha256: str | None = None,
) -> dict[str, Any]:
    if os.environ.get("PYTHONPATH"):
        raise InstalledCoreGoldenPathError("PYTHONPATH must be unset for wheel proof")
    cwd = Path.cwd().resolve()
    repo = repo_root.resolve()
    if _is_within(cwd, repo):
        raise InstalledCoreGoldenPathError(
            "installed Core proof must run outside the source checkout"
        )
    try:
        import dspx
    except ImportError as exc:
        raise InstalledCoreGoldenPathError(
            "installed Core module is unavailable"
        ) from exc
    module_path = Path(str(dspx.__file__)).resolve()
    venv = venv_root.resolve()
    if not _is_within(module_path, venv):
        raise InstalledCoreGoldenPathError(
            f"dspx import leaked outside the clean Core venv: {module_path}"
        )
    if _is_within(module_path, repo):
        raise InstalledCoreGoldenPathError(
            f"dspx import resolved from the source checkout: {module_path}"
        )
    if importlib.util.find_spec("dspx_forge") is not None:
        raise InstalledCoreGoldenPathError(
            "Forge must not be installed during the Core-only proof"
        )
    try:
        distribution_version = version("dspx-core")
    except PackageNotFoundError as exc:
        raise InstalledCoreGoldenPathError(
            "dspx-core distribution metadata is unavailable"
        ) from exc
    result: dict[str, Any] = {
        "module_path": str(module_path),
        "distribution_version": distribution_version,
    }
    if (wheel_path is None) != (expected_wheel_sha256 is None):
        raise InstalledCoreGoldenPathError(
            "wheel path and expected SHA-256 must be supplied together"
        )
    if wheel_path is not None and expected_wheel_sha256 is not None:
        if len(expected_wheel_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in expected_wheel_sha256
        ):
            raise InstalledCoreGoldenPathError("expected wheel SHA-256 is invalid")
        wheel = wheel_path.absolute()
        actual_wheel_sha256 = _stable_wheel_hash(wheel)
        if actual_wheel_sha256 != expected_wheel_sha256:
            raise InstalledCoreGoldenPathError(
                "installed Core wheel hash does not match the selected build artifact"
            )
        direct_url_raw = distribution("dspx-core").read_text("direct_url.json")
        if direct_url_raw is None:
            raise InstalledCoreGoldenPathError(
                "installed Core distribution lacks direct_url.json"
            )
        try:
            direct_url = _mapping(json.loads(direct_url_raw), "installed direct URL")
        except json.JSONDecodeError as exc:
            raise InstalledCoreGoldenPathError(
                "installed Core direct_url.json is invalid"
            ) from exc
        if set(direct_url) != {"url", "archive_info"}:
            raise InstalledCoreGoldenPathError(
                "installed Core direct_url.json fields are not exact"
            )
        parsed = urlparse(str(direct_url.get("url", "")))
        if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
            raise InstalledCoreGoldenPathError(
                "installed Core direct URL is not a local wheel"
            )
        if parsed.query or parsed.fragment != f"sha256={expected_wheel_sha256}":
            raise InstalledCoreGoldenPathError(
                "installed Core direct URL does not bind the selected wheel SHA-256"
            )
        installed_from = Path(unquote(parsed.path)).absolute()
        if installed_from != wheel:
            raise InstalledCoreGoldenPathError(
                "installed Core direct URL does not name the selected wheel"
            )
        archive_info = _mapping(
            direct_url.get("archive_info"), "installed direct URL archive_info"
        )
        if archive_info:
            raise InstalledCoreGoldenPathError(
                "installed Core direct URL archive_info must be empty when the exact hash is URL-bound"
            )
        result["artifact_under_test"] = {
            "filename": wheel.name,
            "sha256": actual_wheel_sha256,
            "distribution_name": "dspx-core",
            "distribution_version": distribution_version,
            "direct_url_bound": True,
        }
    return result


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InstalledCoreGoldenPathError(f"{label} must be an object")
    return cast(Mapping[str, Any], value)


def _expect(value: object, expected: object, label: str) -> None:
    if value != expected:
        raise InstalledCoreGoldenPathError(
            f"{label} drift: expected {expected!r}, observed {value!r}"
        )


def _validate_behavior_non_authority(value: object, label: str) -> None:
    flags = _mapping(value, label)
    for field in (
        "external_authority_mutated",
        "external_mutation",
        "governance_authority",
        "optimization_authority",
        "oracle_promotion",
        "oracle_pruning",
        "oracle_ranking",
        "promotion_authority",
        "winner_selection",
    ):
        _expect(flags.get(field), False, f"{label}.{field}")


def validate_behavior_evidence(
    *,
    episode: Mapping[str, Any],
    results: Mapping[str, Any],
    results_hash: str,
) -> None:
    _expect(
        episode.get("schema_version"),
        "program-behavior-episode-v1",
        "behavior episode schema",
    )
    _expect(episode.get("status"), "passed", "behavior episode status")
    _expect(
        episode.get("authority"),
        "behavior_evidence_only_non_authoritative",
        "behavior episode authority",
    )
    _validate_behavior_non_authority(
        episode.get("non_authority"), "behavior episode non_authority"
    )
    episode_summary = _mapping(episode.get("summary"), "behavior episode summary")
    _expect(episode_summary.get("status"), "passed", "behavior episode summary status")
    _expect(episode_summary.get("total"), 1, "behavior episode total")
    _expect(episode_summary.get("passed"), 1, "behavior episode passed count")
    sources = episode.get("sources")
    if not isinstance(sources, list) or len(sources) != 1:
        raise InstalledCoreGoldenPathError("behavior episode must contain one source")
    source = _mapping(sources[0], "behavior episode source")
    _expect(source.get("status"), "passed", "behavior source status")
    _expect(source.get("returncode"), 0, "behavior source return code")
    _expect(source.get("count"), 1, "behavior source count")
    _expect(
        source.get("behavior_results_path"),
        "behavior_results.json",
        "behavior results path",
    )
    _expect(
        source.get("behavior_results_hash"),
        results_hash,
        "behavior source results hash",
    )
    provider = _mapping(source.get("provider"), "behavior source provider")
    _expect(provider.get("provider"), "stub/echo", "behavior source provider name")
    _expect(provider.get("status"), "configured", "behavior source provider status")

    _expect(
        results.get("schema_version"),
        "program-behavior-results-v1",
        "behavior results schema",
    )
    _expect(
        results.get("authority"),
        "behavior_evidence_only_non_authoritative",
        "behavior results authority",
    )
    _validate_behavior_non_authority(
        results.get("non_authority"), "behavior results non_authority"
    )
    summary = _mapping(results.get("summary"), "behavior results summary")
    _expect(summary.get("status"), "passed", "behavior results status")
    _expect(summary.get("total"), 1, "behavior results total")
    _expect(summary.get("passed"), 1, "behavior results passed count")
    examples = results.get("examples")
    if not isinstance(examples, list) or len(examples) != 1:
        raise InstalledCoreGoldenPathError("behavior results must contain one example")
    example = _mapping(examples[0], "behavior results example")
    _expect(example.get("status"), "passed", "behavior example status")
    _expect(
        example.get("inputs"),
        {"ticket_text": "Production outage for all users"},
        "behavior example inputs",
    )
    _expect(
        example.get("expected_outputs"),
        {"urgency": "high"},
        "behavior expected outputs",
    )
    _expect(
        example.get("observed_outputs"),
        {"urgency": "high"},
        "behavior observed outputs",
    )
    result_provider = _mapping(results.get("provider"), "behavior results provider")
    _expect(
        result_provider.get("provider"), "stub/echo", "behavior results provider name"
    )


def validate_oracle_evidence(
    payload: Mapping[str, Any],
    *,
    expected_identity: Mapping[str, Any],
    behavior_results_hash: str,
) -> None:
    _expect(
        payload.get("schema_version"),
        "program-oracle-evidence-v1",
        "Oracle evidence schema",
    )
    _expect(
        payload.get("evidence_kind"),
        "program_execution_episode",
        "Oracle evidence kind",
    )
    _expect(
        payload.get("authority"),
        "oracle_readability_only_non_authoritative",
        "Oracle evidence authority",
    )
    _expect(payload.get("identity"), expected_identity, "Oracle evidence identity")
    flags = _mapping(payload.get("non_authority"), "Oracle evidence non_authority")
    for field in (
        "external_mutation",
        "governance_authority",
        "oracle_promotion",
        "oracle_pruning",
        "oracle_ranking",
    ):
        _expect(flags.get(field), False, f"Oracle evidence non_authority.{field}")
    behavior = _mapping(payload.get("behavior"), "Oracle evidence behavior")
    summary = _mapping(behavior.get("summary"), "Oracle evidence behavior summary")
    _expect(summary.get("status"), "passed", "Oracle behavior status")
    _expect(summary.get("total"), 1, "Oracle behavior total")
    _expect(
        behavior.get("result_path"),
        "behavior_results.json",
        "Oracle behavior result path",
    )
    _expect(
        behavior.get("result_hash"),
        behavior_results_hash,
        "Oracle behavior result hash",
    )
    facets = _mapping(payload.get("oracle_facets"), "Oracle evidence facets")
    _expect(facets.get("behavior_status"), "passed", "Oracle facet behavior status")
    _expect(facets.get("total_evaluation_count"), 1, "Oracle facet evaluation count")
    artifacts = payload.get("source_artifacts")
    if not isinstance(artifacts, list):
        raise InstalledCoreGoldenPathError("Oracle source artifacts must be a list")
    behavior_rows = [
        row
        for row in artifacts
        if isinstance(row, Mapping) and row.get("kind") == "behavior_results"
    ]
    if len(behavior_rows) != 1:
        raise InstalledCoreGoldenPathError(
            "Oracle evidence must bind one behavior-results artifact"
        )
    _expect(
        behavior_rows[0].get("path"),
        "behavior_results.json",
        "Oracle source behavior path",
    )
    _expect(
        behavior_rows[0].get("content_hash"),
        behavior_results_hash,
        "Oracle source behavior hash",
    )

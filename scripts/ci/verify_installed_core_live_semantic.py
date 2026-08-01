#!/usr/bin/env python3
# ---
# summary: "Publishes verified exact-install evidence for the opt-in installed-wheel live semantic journey."
# read_when:
#   - "Changing installed-wheel live-provider installation, current replay, or proof publication."
# ---

from __future__ import annotations

import argparse
from importlib import import_module
from importlib.metadata import PackageNotFoundError, distribution, version
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
from urllib.parse import unquote, urlparse

from installed_core_live_semantic_contract import CASE_ID, verify_journey_artifacts
from installed_core_payload_contract import verify_installed_payload
from installed_core_proof_contract import verify_install_origin
from installed_core_proof_io import (
    InstalledCoreGoldenPathError,
    open_root,
    root_still_names_descriptor,
    write_result_at,
)

EXPECTED_AUTH_DISTRIBUTION = "dspy-lm-auth"
EXPECTED_AUTH_VERSION = "0.1.3"


def _verify_auth_install(
    venv_root: Path, *, wheel_path: Path, expected_sha256: str
) -> dict[str, Any]:
    try:
        observed_version = version(EXPECTED_AUTH_DISTRIBUTION)
        installed = distribution(EXPECTED_AUTH_DISTRIBUTION)
        module = import_module("dspy_lm_auth")
    except (ImportError, PackageNotFoundError) as exc:
        raise InstalledCoreGoldenPathError(
            "released dspy-lm-auth dependency is unavailable"
        ) from exc
    if observed_version != EXPECTED_AUTH_VERSION:
        raise InstalledCoreGoldenPathError(
            "dspy-lm-auth version does not match the reviewed released pin"
        )
    module_path = Path(str(module.__file__)).resolve()
    venv = venv_root.resolve()
    try:
        module_path.relative_to(venv)
    except ValueError as exc:
        raise InstalledCoreGoldenPathError(
            "dspy-lm-auth import escaped the clean journey environment"
        ) from exc
    wheel = wheel_path.absolute()
    payload = verify_installed_payload(
        wheel_path=wheel,
        site_packages_root=Path(str(installed.locate_file(""))),
        package_root_name="dspy_lm_auth",
    )
    if payload["wheel_sha256"] != expected_sha256:
        raise InstalledCoreGoldenPathError(
            "dspy-lm-auth wheel hash does not match the reviewed release artifact"
        )
    direct_url_raw = installed.read_text("direct_url.json")
    if direct_url_raw is None:
        raise InstalledCoreGoldenPathError("dspy-lm-auth lacks direct_url.json")
    try:
        direct_url = json.loads(direct_url_raw)
    except json.JSONDecodeError as exc:
        raise InstalledCoreGoldenPathError(
            "dspy-lm-auth direct_url.json is invalid"
        ) from exc
    if not isinstance(direct_url, dict) or set(direct_url) != {"url", "archive_info"}:
        raise InstalledCoreGoldenPathError(
            "dspy-lm-auth direct URL fields are not exact"
        )
    parsed = urlparse(str(direct_url["url"]))
    if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
        raise InstalledCoreGoldenPathError(
            "dspy-lm-auth direct URL is not a local wheel"
        )
    if parsed.query or parsed.fragment != f"sha256={expected_sha256}":
        raise InstalledCoreGoldenPathError("dspy-lm-auth direct URL hash is not exact")
    if Path(unquote(parsed.path)).absolute() != wheel:
        raise InstalledCoreGoldenPathError(
            "dspy-lm-auth direct URL names another wheel"
        )
    if direct_url["archive_info"]:
        raise InstalledCoreGoldenPathError(
            "dspy-lm-auth direct URL archive_info must be empty"
        )
    return {
        "distribution": EXPECTED_AUTH_DISTRIBUTION,
        "version": observed_version,
        "module_path": str(module_path),
        "distribution_root": str(Path(str(installed.locate_file(""))).resolve()),
        "released_pin_exact": True,
        "wheel_filename": wheel.name,
        "wheel_sha256": expected_sha256,
        "direct_url_bound": True,
        "installed_payload_record_verified": True,
        "installed_payload_file_count": payload["record_verified_file_count"],
    }


def _verify_current_replay(*, journey_root: Path, venv_root: Path) -> None:
    receipt_path = Path("benchmark") / CASE_ID / "manifest.json.meta.json"
    replay_environment = os.environ.copy()
    replay_environment["DSPX_CACHE_DIR"] = str(
        journey_root / "benchmark" / ".cache" / CASE_ID
    )
    replay_environment.pop("PYTHONPATH", None)
    current_replay = subprocess.run(
        [
            str(venv_root / "bin" / "dspx"),
            "run",
            "replay",
            "--from",
            str(receipt_path),
            "--check-only",
            "--json",
        ],
        cwd=journey_root,
        env=replay_environment,
        capture_output=True,
        check=False,
        text=True,
    )
    if current_replay.returncode != 0:
        raise InstalledCoreGoldenPathError("current replay rejected")
    try:
        current_payload = json.loads(current_replay.stdout)
        recorded_payload = json.loads((journey_root / "replay-check.json").read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise InstalledCoreGoldenPathError("replay evidence is invalid") from exc
    if current_payload != recorded_payload:
        raise InstalledCoreGoldenPathError("replay evidence is stale")


def _verify_current_oracle_report(*, journey_root: Path, venv_root: Path) -> None:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["DSPX_ORACLE_EMBEDDING_BACKEND"] = "mock"
    current = subprocess.run(
        [
            str(venv_root / "bin" / "dspx"),
            "oracle",
            "program-evidence",
            "report",
            "--index-path",
            "oracle/coordinates.db",
            "--json",
        ],
        cwd=journey_root,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
    )
    if current.returncode != 0:
        raise InstalledCoreGoldenPathError("current Oracle report rejected")
    try:
        current_payload = json.loads(current.stdout)
        recorded_payload = json.loads((journey_root / "oracle-report.json").read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise InstalledCoreGoldenPathError("Oracle report evidence is invalid") from exc
    if current_payload != recorded_payload:
        raise InstalledCoreGoldenPathError("Oracle report evidence is stale")


def main() -> int:
    """Verify current receipt state, exact installs, artifact bindings, and one proof."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journey-root", type=Path, required=True)
    parser.add_argument("--venv-root", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--expected-wheel-sha256", required=True)
    parser.add_argument("--auth-wheel", type=Path, required=True)
    parser.add_argument("--expected-auth-wheel-sha256", required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--requested-model", required=True)
    args = parser.parse_args()
    if args.provider != "dspy-lm-auth":
        parser.error("--provider must be dspy-lm-auth for this bounded journey")
    journey_root = args.journey_root.absolute()
    venv_root = args.venv_root.absolute()
    try:
        _verify_current_replay(journey_root=journey_root, venv_root=venv_root)
        _verify_current_oracle_report(
            journey_root=journey_root,
            venv_root=venv_root,
        )
        install = verify_install_origin(
            venv_root=venv_root,
            repo_root=args.repo_root.absolute(),
            wheel_path=args.wheel,
            expected_wheel_sha256=args.expected_wheel_sha256,
        )
        auth_install = _verify_auth_install(
            venv_root,
            wheel_path=args.auth_wheel,
            expected_sha256=args.expected_auth_wheel_sha256,
        )
        proof = verify_journey_artifacts(
            journey_root,
            provider=args.provider,
            requested_model=args.requested_model,
        )
        proof["install"] = install
        proof["auth_dependency"] = auth_install
        root_descriptor = open_root(journey_root)
        try:
            root_still_names_descriptor(journey_root, root_descriptor)
            write_result_at(
                root_descriptor,
                "installed-core-live-semantic-proof.json",
                proof,
            )
        finally:
            os.close(root_descriptor)
    except InstalledCoreGoldenPathError as exc:
        print(f"installed live semantic verification failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(proof, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

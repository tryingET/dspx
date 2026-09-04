"""Write-free preflight for task-local foundry comparison juries.

Runs before the attempt marker exists, so every rejection here leaves no
attempt, journal directory, or result behind and makes zero provider
completion calls. It proves posture at T0: exact owner source, dependency
identity, bytecode posture, private cache/receipt destinations, an active
AK claim whose lease covers every selected juror at the family's per-call
timeout, credential presence and
expiry through the owner's own reader (in an isolated child), and read-only
catalog membership of the requested model. It cannot prove capacity or
entitlement at completion time; a provider-side 429 after the marker still
burns the one-shot slot by design.

Facts are closed (booleans, counts, hashes, ids) and are never bound into the
attempt or receipt; they surface through CLI output only.
"""

from __future__ import annotations

import importlib.metadata
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

from dspx.services.program_foundry_gepa_comparison_jury_owner import (
    _EXTRA_OWNER_FILES,
    FOUNDRY_JURY_OWNER_SOURCE,
    OWNER_COMMIT,
    expected_foundry_jury_dependency_identity,
    verify_foundry_jury_owner_source,
)
from dspx.services.program_foundry_gepa_comparison_jury_provider_custody import (
    _private_directory,
    canonical_ak_task_revalidator,
)
from dspx.services.program_foundry_gepa_comparison_jury_provider_family import (
    AUTH_MODE_PI_API_KEY,
    FoundryJuryProviderFamily,
    family_for_request,
)
from dspx.services.program_foundry_gepa_comparison_jury_runtime import (
    ProgramFoundryGepaComparisonJuryError,
)
from dspx.services.program_foundry_gepa_proposal_io import read_regular_bytes
from dspx.services.soomfon_provider_outcome_receipt_contract import (
    canonical_json,
    sha256,
)
from dspx.services.soomfon_provider_outcome_receipt_identity import _record_digest

PREFLIGHT_SCHEMA = "dspx-foundry-jury-preflight-v1"
_OWNER_AUTH_RELATIVE = "src/dspy_lm_auth/auth.py"
_OWNER_AUTH_SHA256 = _EXTRA_OWNER_FILES[_OWNER_AUTH_RELATIVE]
_OWNER_CREDENTIAL_RELATIVE = "src/dspy_lm_auth/_chat_credential.py"
_OWNER_CREDENTIAL_SHA256 = _EXTRA_OWNER_FILES[_OWNER_CREDENTIAL_RELATIVE]
_PROBE_PATH = Path(__file__).with_name(
    "program_foundry_gepa_comparison_jury_preflight_probe.py"
)
_PROBE_MAX_OUTPUT_BYTES = 256 * 1024
_PROBE_TIMEOUT_SECONDS = 5.0
_PROBE_CATALOG_TIMEOUT_SECONDS = 10.0
_PROBE_ENV_KEYS = ("HOME", "PATH", "SSL_CERT_FILE", "SSL_CERT_DIR")
_CREDENTIAL_KEYS = frozenset(
    {"credential_present", "expiry_ok", "expires_ms", "endpoint_fixed", "catalog"}
)
_CATALOG_KEYS = frozenset(
    {
        "status_class",
        "status_code",
        "catalog_count",
        "catalog_ids_sha256",
        "model_listed",
    }
)


def _reject(reason: str) -> ProgramFoundryGepaComparisonJuryError:
    return ProgramFoundryGepaComparisonJuryError(
        f"task-local provider preflight rejected: {reason}"
    )


def selected_juror_count(
    candidate_manifest_path: Path, *, max_jurors: int | None
) -> int:
    """Count selected jurors exactly as the model jury will, truncated by max_jurors."""

    selection_path = candidate_manifest_path.expanduser().absolute().parent
    selection_path = selection_path / "jury_selection.json"
    try:
        payload = json.loads(
            read_regular_bytes(selection_path, label="jury selection").decode("utf-8")
        )
    except (ValueError, UnicodeDecodeError) as exc:
        raise _reject("jury selection is unreadable") from exc
    rows = payload.get("selected_jurors") if isinstance(payload, dict) else None
    selected = (
        [row for row in rows if isinstance(row, Mapping)]
        if isinstance(rows, list)
        else []
    )
    if max_jurors is not None:
        selected = selected[: max(0, int(max_jurors))]
    return len(selected)


def _check_bytecode_posture() -> None:
    if (
        sys.dont_write_bytecode is not True
        or os.environ.get("PYTHONDONTWRITEBYTECODE") != "1"
    ):
        raise _reject(
            "PYTHONDONTWRITEBYTECODE=1 and sys.dont_write_bytecode are required"
        )


def _check_cache_dir(owner_source_root: Path) -> None:
    """DSPX_CACHE_DIR must be an absolute, owned, non-symlink directory that
    nobody else can write to, outside the owner source root.

    Staged lineages keep their candidate run receipt under ``<lineage>/cache``
    (created 0755 by the foundry tooling) and consumption re-validation binds
    that exact root, so exact-0700 posture is not required here; group/world
    write bits are.
    """

    raw = os.environ.get("DSPX_CACHE_DIR")
    if not raw or not Path(raw).is_absolute():
        raise _reject("DSPX_CACHE_DIR must be set to an absolute private directory")
    target = Path(raw)
    try:
        info = target.lstat()
        resolved = target.resolve(strict=True)
    except OSError as exc:
        raise _reject("DSPX_CACHE_DIR posture is not private") from exc
    if (
        target.is_symlink()
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) & 0o022
        or resolved != target
    ):
        raise _reject("DSPX_CACHE_DIR posture is not private")
    if resolved == owner_source_root or owner_source_root in resolved.parents:
        raise _reject("DSPX_CACHE_DIR must not live inside the owner source root")


def _check_destination(experiment_root: Path) -> None:
    try:
        _private_directory(experiment_root)
    except ValueError as exc:
        raise _reject("experiment root posture is not private") from exc
    outcomes = experiment_root / "provider-outcomes"
    if outcomes.exists() or outcomes.is_symlink():
        raise _reject("provider-outcomes journal root already exists")


def _check_owner_not_preloaded() -> None:
    if any(
        name == "dspy_lm_auth" or name.startswith("dspy_lm_auth.")
        for name in sys.modules
    ):
        raise _reject("owner package is already imported; use a fresh one-shot process")


def _dependency_identity_sha256() -> str:
    """Verify installed dependency payloads against the pinned identity, no owner import."""

    expected = expected_foundry_jury_dependency_identity()
    observed: dict[str, Any] = {}
    for name, dependency in sorted(FOUNDRY_JURY_OWNER_SOURCE.dependencies.items()):
        try:
            distribution = importlib.metadata.distribution(name)
            digest = _record_digest(distribution, dependency.module_name)
        except (importlib.metadata.PackageNotFoundError, ValueError) as exc:
            raise _reject(f"dependency {name} identity is unavailable") from exc
        observed[name] = {
            "version": distribution.version,
            "locked_wheel_sha256": dependency.wheel_sha256,
            **digest,
        }
    if observed != expected:
        raise _reject("installed dependency identity drifted from the pinned owner")
    return sha256(canonical_json(expected))


def _probe_config(
    family: FoundryJuryProviderFamily,
    *,
    owner_source_root: Path,
    model: str,
    auth_path: Path | None,
) -> dict[str, Any]:
    config: dict[str, Any] = {
        "auth_provider": family.auth_provider,
        "auth_mode": family.auth_mode,
        "model": model,
        "catalog_url": family.catalog_url,
        "auth_module_path": str(owner_source_root / _OWNER_AUTH_RELATIVE),
        "auth_module_sha256": _OWNER_AUTH_SHA256,
        "auth_path": None if auth_path is None else str(auth_path),
    }
    if family.auth_mode == AUTH_MODE_PI_API_KEY:
        config["credential_module_path"] = str(
            owner_source_root / _OWNER_CREDENTIAL_RELATIVE
        )
        config["credential_module_sha256"] = _OWNER_CREDENTIAL_SHA256
    return config


def run_probe(config: Mapping[str, Any]) -> dict[str, Any]:
    """Spawn the isolated probe child and return its closed facts."""

    timeout = _PROBE_TIMEOUT_SECONDS
    if config.get("catalog_url"):
        timeout += _PROBE_CATALOG_TIMEOUT_SECONDS
    env = {key: os.environ[key] for key in _PROBE_ENV_KEYS if key in os.environ}
    env.update({"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"})
    try:
        completed = subprocess.run(
            [sys.executable, "-I", "-B", str(_PROBE_PATH), json.dumps(config)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            env=env,
            timeout=timeout,
            check=False,
            close_fds=True,
            start_new_session=True,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise _reject("credential probe did not complete") from exc
    if completed.returncode != 0 or len(completed.stdout) > _PROBE_MAX_OUTPUT_BYTES:
        raise _reject("credential probe failed closed")
    try:
        facts = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _reject("credential probe output is not JSON") from exc
    if not isinstance(facts, dict) or set(facts) != _CREDENTIAL_KEYS:
        raise _reject("credential probe output shape drifted")
    catalog = facts["catalog"]
    if catalog is not None and (
        not isinstance(catalog, dict) or set(catalog) != _CATALOG_KEYS
    ):
        raise _reject("catalog probe output shape drifted")
    return facts


def probe_credential_and_catalog(
    family: FoundryJuryProviderFamily,
    *,
    owner_source_root: Path,
    model: str,
    auth_path: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (credential facts, catalog facts); fail closed on any gap."""

    facts = run_probe(
        _probe_config(
            family,
            owner_source_root=owner_source_root,
            model=model,
            auth_path=auth_path,
        )
    )
    probed = family.auth_mode != "none"
    credential = {
        "probed": probed,
        "credential_present": bool(facts["credential_present"]),
        "expiry_ok": bool(facts["expiry_ok"]),
        "expires_ms": int(facts["expires_ms"]),
        "endpoint_fixed": bool(facts["endpoint_fixed"]),
    }
    if probed and not (
        credential["credential_present"]
        and credential["expiry_ok"]
        and credential["endpoint_fixed"]
    ):
        raise _reject(
            f"{family.auth_provider} credential is absent, expired, or misrouted"
        )
    raw_catalog = facts["catalog"]
    catalog: dict[str, Any] = {
        "checked": family.catalog_url is not None,
        "status_class": None,
        "catalog_count": None,
        "catalog_ids_sha256": None,
        "model_listed": None,
    }
    if family.catalog_url is not None:
        if raw_catalog is None:
            raise _reject("catalog listing was not fetched")
        catalog.update(
            {
                "status_class": str(raw_catalog["status_class"]),
                "catalog_count": int(raw_catalog["catalog_count"]),
                "catalog_ids_sha256": str(raw_catalog["catalog_ids_sha256"]),
                "model_listed": bool(raw_catalog["model_listed"]),
            }
        )
        if catalog["status_class"] != "2xx" or catalog["model_listed"] is not True:
            raise _reject(
                f"{family.auth_provider} catalog does not serve {model} "
                f"(status_class={catalog['status_class']})"
            )
    return credential, catalog


def run_task_local_preflight(
    request: Mapping[str, Any],
    *,
    experiment_root: Path,
    expected_juror_count: int,
    repo_root: Path,
    auth_path: Path | None = None,
) -> dict[str, Any]:
    """Deterministic write-free preflight; raises before any marker exists."""

    try:
        family = family_for_request(request)
    except ValueError as exc:
        raise _reject("task-local provider endpoint is not bound") from exc
    if family is None:
        raise _reject("provider is not a task-local family")
    if not family.model_allowed(request.get(family.model_key)):
        raise _reject("model is outside the family rule")
    model = str(request[family.model_key])
    if isinstance(expected_juror_count, bool) or expected_juror_count < 1:
        raise _reject("jury selection contains no selected jurors")
    owner_source_root = Path(str(request["owner_source_root"]))
    _check_bytecode_posture()
    _check_owner_not_preloaded()
    _check_cache_dir(owner_source_root)
    _check_destination(experiment_root)
    try:
        verify_foundry_jury_owner_source(owner_source_root)
    except (ValueError, OSError) as exc:
        raise _reject("exact owner source verification failed") from exc
    dependency_sha256 = _dependency_identity_sha256()
    minimum_lease = expected_juror_count * family.default_timeout_seconds + 30.0
    try:
        canonical_ak_task_revalidator(
            execution_task_id=int(request["execution_task_id"]),
            execution_claimant=str(request["execution_claimant"]),
            repo_root=repo_root,
            minimum_lease_seconds=minimum_lease,
            family=family,
        )()
    except ValueError as exc:
        raise _reject(
            "canonical AK task authority is not active for the lease"
        ) from exc
    credential, catalog = probe_credential_and_catalog(
        family, owner_source_root=owner_source_root, model=model, auth_path=auth_path
    )
    return {
        "schema_version": PREFLIGHT_SCHEMA,
        "provider": family.provider_name,
        "auth_provider": family.auth_provider,
        "model": model,
        "endpoint_origin_sha256": family.endpoint_origin_sha256,
        "bytecode_disabled": True,
        "owner_not_preloaded": True,
        "cache_dir_private": True,
        "destination_private": True,
        "provider_outcomes_absent": True,
        "owner_source_verified": True,
        "owner_commit": OWNER_COMMIT,
        "dependency_identity_sha256": dependency_sha256,
        "expected_juror_count": expected_juror_count,
        "ak_task_id": int(request["execution_task_id"]),
        "ak_minimum_lease_seconds": minimum_lease,
        "ak_authority_active": True,
        "credential": credential,
        "catalog": catalog,
        "provider_completion_calls": 0,
        "proves": ["reachability", "credential_validity_at_t0", "catalog_membership"],
        "cannot_prove": ["capacity_at_completion", "entitlement_at_completion"],
    }


__all__ = [
    "PREFLIGHT_SCHEMA",
    "probe_credential_and_catalog",
    "run_probe",
    "run_task_local_preflight",
    "selected_juror_count",
]

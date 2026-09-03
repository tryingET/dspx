# summary: "Tests the write-free task-local foundry jury preflight, the isolated credential probe, and the read-only catalog check."

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

import dspx.services.program_foundry_gepa_comparison_jury as comparison_jury
import dspx.services.program_foundry_gepa_comparison_jury_receipt_validation as receipt_validation
import dspx.services.program_foundry_gepa_comparison_jury_preflight as preflight
from dspx.cli.dspx import app
from dspx.services.program_foundry_gepa_comparison_jury_provider_family import (
    CODEX_FAMILY,
    COPILOT_FAMILY,
    LOCAL_VLLM_FAMILY,
    XAI_FAMILY,
)
from test_program_foundry_gepa_comparison_jury import _fixture, _model_result

SECRET = "SECRET-TOKEN-XYZ-0123456789"
MODEL = "grok-4.6"
FAKE_AUTH_MODULE = """
from pathlib import Path
import json, time
DEFAULT_PI_AUTH_PATH = Path("/nonexistent/auth.json")
GITHUB_COPILOT_API_BASE = "https://api.individual.githubcopilot.com"
def validate_oauth_credential_expiry(expires, *, now=None):
    current = time.time() if now is None else now
    if not isinstance(expires, (int, float)) or expires <= (current + 300) * 1000:
        raise ValueError("expired")
def read_existing_oauth_credential_without_refresh(path, provider, *, now=None):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("unreadable") from exc
    cred = data.get(provider) if isinstance(data, dict) else None
    if not isinstance(cred, dict) or cred.get("type") != "oauth":
        raise ValueError("missing")
    validate_oauth_credential_expiry(cred["expires"], now=now)
    return cred["access"], None, cred["expires"]
def github_copilot_base_url(token):
    if "proxy-ep=" in token:
        return "https://api.other.githubcopilot.com"
    return GITHUB_COPILOT_API_BASE
"""


@pytest.fixture(autouse=True)
def _in_process_jury(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run task-local juries in this process so patched fakes stay reachable."""

    monkeypatch.setattr(comparison_jury, "_CHILD_ARGV", None)


class _Catalog:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self.body = body
        self.requests: list[tuple[str, str, dict[str, str]]] = []


def _serve(catalog: _Catalog) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def _record(self) -> None:
            catalog.requests.append(
                (self.command, self.path, {k: v for k, v in self.headers.items()})
            )

        def do_GET(self) -> None:  # noqa: N802
            self._record()
            self.send_response(catalog.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(catalog.body)))
            self.end_headers()
            self.wfile.write(catalog.body)

        def do_POST(self) -> None:  # noqa: N802
            self._record()
            self.send_response(500)
            self.end_headers()

        def log_message(self, *args: Any) -> None:
            del args

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def catalog_server() -> Iterator[tuple[_Catalog, str]]:
    catalog = _Catalog(200, json.dumps({"data": [{"id": MODEL}, {"id": "x"}]}).encode())
    generator = _serve(catalog)
    base = next(generator)
    try:
        yield catalog, base
    finally:
        next(generator, None)


def _fake_owner(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "owner"
    (root / "src" / "dspy_lm_auth").mkdir(parents=True, exist_ok=True)
    module = root / "src" / "dspy_lm_auth" / "auth.py"
    module.write_text(FAKE_AUTH_MODULE, encoding="utf-8")
    return root, hashlib.sha256(module.read_bytes()).hexdigest()


def _auth_json(tmp_path: Path, provider: str, *, expires_ms: int | None = None) -> Path:
    path = tmp_path / "auth.json"
    expires = expires_ms if expires_ms is not None else int((time.time() + 3600) * 1000)
    path.write_text(
        json.dumps({provider: {"type": "oauth", "access": SECRET, "expires": expires}}),
        encoding="utf-8",
    )
    return path


def _probe_config(
    tmp_path: Path,
    *,
    auth_provider: str,
    catalog_url: str | None,
    model: str = MODEL,
    expires_ms: int | None = None,
) -> dict[str, Any]:
    root, digest = _fake_owner(tmp_path)
    return {
        "auth_provider": auth_provider,
        "model": model,
        "catalog_url": catalog_url,
        "auth_module_path": str(root / "src" / "dspy_lm_auth" / "auth.py"),
        "auth_module_sha256": digest,
        "auth_path": str(_auth_json(tmp_path, auth_provider, expires_ms=expires_ms)),
    }


def _task_local_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, owner_root: Path
) -> None:
    cache = tmp_path / "cache"
    cache.mkdir(mode=0o700)
    monkeypatch.setenv("DSPX_CACHE_DIR", str(cache))
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    monkeypatch.setattr(preflight, "verify_foundry_jury_owner_source", lambda root: {})
    monkeypatch.setattr(preflight, "_dependency_identity_sha256", lambda: "d" * 64)
    monkeypatch.setattr(
        preflight,
        "probe_credential_and_catalog",
        lambda family, **kwargs: (
            {
                "probed": True,
                "credential_present": True,
                "expiry_ok": True,
                "expires_ms": 1,
                "endpoint_fixed": True,
            },
            {
                "checked": True,
                "status_class": "2xx",
                "catalog_count": 1,
                "catalog_ids_sha256": "c" * 64,
                "model_listed": True,
            },
        ),
    )


def _request(owner_root: Path, *, max_jurors: int | None = None) -> dict[str, Any]:
    return comparison_jury._execution_request(
        provider=XAI_FAMILY.provider_name,
        adjudicator_id="local",
        adjudicator_kind="local",
        adjudicator_repo=None,
        max_jurors=max_jurors,
        owner_source_root=owner_root,
        execution_task_id=6000,
        execution_claimant="pi:test",
    )


def _selection(validated: dict[str, Any], count: int) -> None:
    Path(validated["candidate_manifest_path"]).parent.joinpath(
        "jury_selection.json"
    ).write_text(
        json.dumps(
            {
                "schema_version": "program-jury-selection-v1",
                "selected_jurors": [{"id": f"j{i}"} for i in range(count)],
            }
        ),
        encoding="utf-8",
    )


def _revalidator_capture(
    monkeypatch: pytest.MonkeyPatch, seen: list[dict[str, Any]]
) -> None:
    def make(**kwargs: Any) -> Any:
        seen.append(kwargs)
        return lambda: None

    monkeypatch.setattr(preflight, "canonical_ak_task_revalidator", make)


# --- slice A: local preflight -------------------------------------------------


def test_preflight_rejects_missing_cache_dir_before_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, validated = _fixture(tmp_path)
    Path(validated["experiment_root"]).chmod(0o700)
    _selection(validated, 1)
    owner_root = tmp_path / "owner"
    owner_root.mkdir()
    _task_local_env(monkeypatch, tmp_path, owner_root)
    _revalidator_capture(monkeypatch, [])
    monkeypatch.delenv("DSPX_CACHE_DIR")
    monkeypatch.setattr(
        comparison_jury,
        "validate_successful_program_foundry_gepa_consumption_receipt",
        lambda path, **kwargs: dict(validated),
    )
    monkeypatch.setattr(
        comparison_jury,
        "build_comparison_model_jury_result",
        lambda *a, **k: pytest.fail("provider path must not run"),
    )
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError,
        match="DSPX_CACHE_DIR must be set",
    ):
        comparison_jury.execute_program_foundry_gepa_comparison_jury(
            consumption_receipt_path=receipt,
            provider=XAI_FAMILY.provider_name,
            owner_source_root=owner_root,
            execution_task_id=6000,
            execution_claimant="pi:test",
        )
    experiment = Path(validated["experiment_root"])
    assert not (experiment / "comparison-jury-attempt.json").exists()
    assert not (experiment / "comparison-jury-results.json").exists()
    assert not (experiment / "provider-outcomes").exists()


def test_preflight_lease_margin_scales_with_selected_jurors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_root = tmp_path / "owner"
    owner_root.mkdir()
    experiment = tmp_path / "gepa-experiment"
    experiment.mkdir(mode=0o700)
    _task_local_env(monkeypatch, tmp_path, owner_root)
    seen: list[dict[str, Any]] = []
    _revalidator_capture(monkeypatch, seen)
    # xAI pins a 180 s per-call timeout (grok-4.6 reasons before answering).
    assert XAI_FAMILY.default_timeout_seconds == 180.0
    for count, expected in ((1, 210.0), (3, 570.0), (6, 1110.0)):
        facts = preflight.run_task_local_preflight(
            _request(owner_root),
            experiment_root=experiment,
            expected_juror_count=count,
            repo_root=tmp_path,
        )
        assert seen[-1]["minimum_lease_seconds"] == expected
        assert seen[-1]["family"] is XAI_FAMILY
        assert facts["ak_minimum_lease_seconds"] == expected
        assert facts["expected_juror_count"] == count
    # Other families keep the shared 60 s default and the historical margins.
    copilot_request = comparison_jury._execution_request(
        provider=COPILOT_FAMILY.provider_name,
        adjudicator_id="local",
        adjudicator_kind="local",
        adjudicator_repo=None,
        max_jurors=None,
        owner_source_root=owner_root,
        execution_task_id=6000,
        execution_claimant="pi:test",
    )
    for count, expected in ((1, 90.0), (3, 210.0), (6, 390.0)):
        facts = preflight.run_task_local_preflight(
            copilot_request,
            experiment_root=experiment,
            expected_juror_count=count,
            repo_root=tmp_path,
        )
        assert seen[-1]["minimum_lease_seconds"] == expected
        assert seen[-1]["family"] is COPILOT_FAMILY
        assert facts["ak_minimum_lease_seconds"] == expected


def test_preflight_rejects_zero_selected_jurors_before_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, validated = _fixture(tmp_path)
    Path(validated["experiment_root"]).chmod(0o700)
    owner_root = tmp_path / "owner"
    owner_root.mkdir()
    _task_local_env(monkeypatch, tmp_path, owner_root)
    _revalidator_capture(monkeypatch, [])
    monkeypatch.setattr(
        comparison_jury,
        "validate_successful_program_foundry_gepa_consumption_receipt",
        lambda path, **kwargs: dict(validated),
    )
    assert (
        preflight.selected_juror_count(
            Path(validated["candidate_manifest_path"]), max_jurors=None
        )
        == 0
    )
    _selection(validated, 3)
    assert (
        preflight.selected_juror_count(
            Path(validated["candidate_manifest_path"]), max_jurors=2
        )
        == 2
    )
    _selection(validated, 0)
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError,
        match="no selected jurors",
    ):
        comparison_jury.execute_program_foundry_gepa_comparison_jury(
            consumption_receipt_path=receipt,
            provider=XAI_FAMILY.provider_name,
            owner_source_root=owner_root,
            execution_task_id=6000,
            execution_claimant="pi:test",
        )
    assert not (receipt.parent / "comparison-jury-attempt.json").exists()


def test_preflight_rejects_existing_provider_outcomes_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_root = tmp_path / "owner"
    owner_root.mkdir()
    experiment = tmp_path / "gepa-experiment"
    experiment.mkdir(mode=0o700)
    (experiment / "provider-outcomes").mkdir(mode=0o700)
    _task_local_env(monkeypatch, tmp_path, owner_root)
    _revalidator_capture(monkeypatch, [])
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError,
        match="provider-outcomes journal root already exists",
    ):
        preflight.run_task_local_preflight(
            _request(owner_root),
            experiment_root=experiment,
            expected_juror_count=1,
            repo_root=tmp_path,
        )


def test_preflight_rejects_bytecode_and_preloaded_owner_posture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_root = tmp_path / "owner"
    owner_root.mkdir()
    experiment = tmp_path / "gepa-experiment"
    experiment.mkdir(mode=0o700)
    _task_local_env(monkeypatch, tmp_path, owner_root)
    _revalidator_capture(monkeypatch, [])
    monkeypatch.delenv("PYTHONDONTWRITEBYTECODE")
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError,
        match="PYTHONDONTWRITEBYTECODE",
    ):
        preflight.run_task_local_preflight(
            _request(owner_root),
            experiment_root=experiment,
            expected_juror_count=1,
            repo_root=tmp_path,
        )
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    monkeypatch.setitem(sys.modules, "dspy_lm_auth.auth", object())
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError,
        match="already imported",
    ):
        preflight.run_task_local_preflight(
            _request(owner_root),
            experiment_root=experiment,
            expected_juror_count=1,
            repo_root=tmp_path,
        )


def test_preflight_rejects_cache_dir_inside_owner_root_or_non_private(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_root = tmp_path / "owner"
    owner_root.mkdir()
    experiment = tmp_path / "gepa-experiment"
    experiment.mkdir(mode=0o700)
    _task_local_env(monkeypatch, tmp_path, owner_root)
    _revalidator_capture(monkeypatch, [])
    inside = owner_root / "cache"
    inside.mkdir(mode=0o700)
    monkeypatch.setenv("DSPX_CACHE_DIR", str(inside))
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError,
        match="inside the owner source root",
    ):
        preflight.run_task_local_preflight(
            _request(owner_root),
            experiment_root=experiment,
            expected_juror_count=1,
            repo_root=tmp_path,
        )
    loose = tmp_path / "loose"
    loose.mkdir()
    loose.chmod(0o775)
    monkeypatch.setenv("DSPX_CACHE_DIR", str(loose))
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError,
        match="posture is not private",
    ):
        preflight.run_task_local_preflight(
            _request(owner_root),
            experiment_root=experiment,
            expected_juror_count=1,
            repo_root=tmp_path,
        )
    link = tmp_path / "cache-link"
    link.symlink_to(tmp_path / "cache")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(link))
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError,
        match="posture is not private",
    ):
        preflight.run_task_local_preflight(
            _request(owner_root),
            experiment_root=experiment,
            expected_juror_count=1,
            repo_root=tmp_path,
        )
    # Staged lineages create <lineage>/cache as 0755; readable-by-others is
    # accepted, writable-by-others is not.
    staged = tmp_path / "staged-cache"
    staged.mkdir(mode=0o755)
    monkeypatch.setenv("DSPX_CACHE_DIR", str(staged))
    facts = preflight.run_task_local_preflight(
        _request(owner_root),
        experiment_root=experiment,
        expected_juror_count=1,
        repo_root=tmp_path,
    )
    assert facts["cache_dir_private"] is True


def test_preflight_facts_are_closed_and_json_canonical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_root = tmp_path / "owner"
    owner_root.mkdir()
    experiment = tmp_path / "gepa-experiment"
    experiment.mkdir(mode=0o700)
    _task_local_env(monkeypatch, tmp_path, owner_root)
    _revalidator_capture(monkeypatch, [])
    facts = preflight.run_task_local_preflight(
        _request(owner_root),
        experiment_root=experiment,
        expected_juror_count=2,
        repo_root=tmp_path,
    )
    assert set(facts) == {
        "schema_version",
        "provider",
        "auth_provider",
        "model",
        "endpoint_origin_sha256",
        "bytecode_disabled",
        "owner_not_preloaded",
        "cache_dir_private",
        "destination_private",
        "provider_outcomes_absent",
        "owner_source_verified",
        "owner_commit",
        "dependency_identity_sha256",
        "expected_juror_count",
        "ak_task_id",
        "ak_minimum_lease_seconds",
        "ak_authority_active",
        "credential",
        "catalog",
        "provider_completion_calls",
        "proves",
        "cannot_prove",
    }
    assert facts["schema_version"] == "dspx-foundry-jury-preflight-v1"
    assert facts["provider_completion_calls"] == 0
    assert facts["model"] == MODEL
    assert facts["credential"]["probed"] is True
    assert facts["catalog"]["model_listed"] is True
    encoded = json.dumps(facts, sort_keys=True, allow_nan=False, separators=(",", ":"))
    assert json.loads(encoded) == facts
    assert str(owner_root) not in encoded
    assert "auth.json" not in encoded


def test_preflight_rejects_when_owner_source_or_ak_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_root = tmp_path / "owner"
    owner_root.mkdir()
    experiment = tmp_path / "gepa-experiment"
    experiment.mkdir(mode=0o700)
    _task_local_env(monkeypatch, tmp_path, owner_root)
    _revalidator_capture(monkeypatch, [])

    def drift(root: Path) -> dict[str, Any]:
        raise ValueError("owner_git_identity_drift")

    monkeypatch.setattr(preflight, "verify_foundry_jury_owner_source", drift)
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError,
        match="owner source verification failed",
    ):
        preflight.run_task_local_preflight(
            _request(owner_root),
            experiment_root=experiment,
            expected_juror_count=1,
            repo_root=tmp_path,
        )
    monkeypatch.setattr(preflight, "verify_foundry_jury_owner_source", lambda root: {})

    def stale(**kwargs: Any) -> Any:
        def revalidate() -> None:
            raise ValueError("canonical AK task authority is not active")

        return revalidate

    monkeypatch.setattr(preflight, "canonical_ak_task_revalidator", stale)
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError,
        match="AK task authority is not active",
    ):
        preflight.run_task_local_preflight(
            _request(owner_root),
            experiment_root=experiment,
            expected_juror_count=1,
            repo_root=tmp_path,
        )


def test_live_run_json_carries_unbound_preflight_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, validated = _fixture(tmp_path)
    owner_root = tmp_path / "owner"
    owner_root.mkdir()
    monkeypatch.setattr(
        comparison_jury,
        "validate_successful_program_foundry_gepa_consumption_receipt",
        lambda path, **kwargs: dict(validated),
    )
    monkeypatch.setattr(
        comparison_jury,
        "run_task_local_preflight",
        lambda request, **kwargs: {"schema_version": "dspx-foundry-jury-preflight-v1"},
    )
    monkeypatch.setattr(
        comparison_jury,
        "build_comparison_model_jury_result",
        lambda slot, **kwargs: _model_result(validated),
    )
    monkeypatch.setattr(
        receipt_validation,
        "_validate_jury_result",
        lambda *, result_path, **kwargs: (
            json.loads(result_path.read_text(encoding="utf-8")),
            hashlib.sha256(result_path.read_bytes()).hexdigest(),
        ),
    )
    payload = comparison_jury.execute_program_foundry_gepa_comparison_jury(
        consumption_receipt_path=receipt,
        provider=XAI_FAMILY.provider_name,
        owner_source_root=owner_root,
        execution_task_id=6000,
        execution_claimant="pi:test",
    )
    assert payload["status"] == "ok"
    assert payload["preflight"] == {"schema_version": "dspx-foundry-jury-preflight-v1"}
    receipt_payload = json.loads(
        (receipt.parent / "comparison-jury-receipt.json").read_text(encoding="utf-8")
    )
    attempt_payload = json.loads(
        (receipt.parent / "comparison-jury-attempt.json").read_text(encoding="utf-8")
    )
    assert "preflight" not in receipt_payload
    assert "preflight" not in attempt_payload


def test_preflight_only_writes_nothing_and_returns_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt, validated = _fixture(tmp_path)
    owner_root = tmp_path / "owner"
    owner_root.mkdir()
    monkeypatch.setattr(
        comparison_jury,
        "validate_successful_program_foundry_gepa_consumption_receipt",
        lambda path, **kwargs: dict(validated),
    )
    monkeypatch.setattr(
        comparison_jury, "run_task_local_preflight", lambda request, **kwargs: {"ok": 1}
    )
    monkeypatch.setattr(
        comparison_jury,
        "build_comparison_model_jury_result",
        lambda *a, **k: pytest.fail("preflight-only must not run the jury"),
    )
    payload = comparison_jury.execute_program_foundry_gepa_comparison_jury(
        consumption_receipt_path=receipt,
        provider=XAI_FAMILY.provider_name,
        owner_source_root=owner_root,
        execution_task_id=6000,
        execution_claimant="pi:test",
        preflight_only=True,
    )
    assert payload == {"status": "preflight_ok", "preflight": {"ok": 1}}
    assert sorted(p.name for p in receipt.parent.iterdir()) == [
        "candidate-comparison.json",
        "consumption-receipt.json",
        "execution-receipt.json",
        "materialized-candidate",
    ]
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError,
        match="defined for task-local providers",
    ):
        comparison_jury.execute_program_foundry_gepa_comparison_jury(
            consumption_receipt_path=receipt,
            provider="fixture-provider",
            preflight_only=True,
        )


def test_preflight_only_cli_prints_facts_and_forwards_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt = tmp_path / "consumption-receipt.json"
    receipt.write_text("{}", encoding="utf-8")
    calls: list[dict[str, Any]] = []

    def execute(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {"status": "preflight_ok", "preflight": {"model": MODEL}}

    monkeypatch.setattr(
        comparison_jury, "execute_program_foundry_gepa_comparison_jury", execute
    )
    result = CliRunner().invoke(
        app,
        [
            "program-refine",
            "jury-foundry-gepa-comparison",
            "--receipt",
            str(receipt),
            "--provider",
            XAI_FAMILY.provider_name,
            "--owner-source-root",
            str(tmp_path),
            "--execution-task-id",
            "6000",
            "--execution-claimant",
            "pi:test",
            "--preflight-only",
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {
        "status": "preflight_ok",
        "preflight": {"model": MODEL},
    }
    assert calls[0]["preflight_only"] is True

    def rejected(**kwargs: Any) -> dict[str, Any]:
        raise comparison_jury.ProgramFoundryGepaComparisonJuryError(
            "task-local provider preflight rejected: x"
        )

    monkeypatch.setattr(
        comparison_jury, "execute_program_foundry_gepa_comparison_jury", rejected
    )
    result = CliRunner().invoke(
        app,
        [
            "program-refine",
            "jury-foundry-gepa-comparison",
            "--receipt",
            str(receipt),
            "--provider",
            XAI_FAMILY.provider_name,
            "--preflight-only",
        ],
    )
    assert result.exit_code == 2
    assert "preflight rejected" in result.output


# --- credential probe child ---------------------------------------------------


def test_credential_probe_never_returns_token(
    tmp_path: Path, catalog_server: tuple[_Catalog, str]
) -> None:
    catalog, base = catalog_server
    facts = preflight.run_probe(
        _probe_config(tmp_path, auth_provider="xai", catalog_url=base + "/models")
    )
    encoded = json.dumps(facts)
    assert SECRET not in encoded
    assert set(facts) == {
        "credential_present",
        "expiry_ok",
        "expires_ms",
        "endpoint_fixed",
        "catalog",
    }
    assert facts["credential_present"] is True
    assert facts["expiry_ok"] is True
    assert facts["endpoint_fixed"] is True
    assert facts["expires_ms"] > 0
    assert facts["catalog"]["model_listed"] is True
    assert catalog.requests[0][2]["Authorization"] == f"Bearer {SECRET}"


def test_credential_probe_reports_missing_or_expired_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _probe_config(tmp_path, auth_provider="xai", catalog_url=None)
    monkeypatch.setattr(preflight, "_OWNER_AUTH_SHA256", config["auth_module_sha256"])
    Path(config["auth_path"]).write_text("{}", encoding="utf-8")
    facts = preflight.run_probe(config)
    assert facts["credential_present"] is False
    assert facts["catalog"] is None
    expired = _probe_config(
        tmp_path, auth_provider="xai", catalog_url=None, expires_ms=1
    )
    facts = preflight.run_probe(expired)
    assert facts["credential_present"] is False
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError,
        match="credential is absent, expired, or misrouted",
    ):
        preflight.probe_credential_and_catalog(
            XAI_FAMILY,
            owner_source_root=tmp_path / "owner",
            model=MODEL,
            auth_path=Path(expired["auth_path"]),
        )


def test_credential_probe_fails_closed_on_owner_auth_hash_drift(
    tmp_path: Path,
) -> None:
    config = _probe_config(tmp_path, auth_provider="xai", catalog_url=None)
    config["auth_module_sha256"] = "0" * 64
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError,
        match="probe failed closed",
    ):
        preflight.run_probe(config)


def test_credential_probe_skips_owner_reader_for_local_vllm(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    catalog_server: tuple[_Catalog, str],
) -> None:
    catalog, base = catalog_server
    catalog.body = json.dumps({"data": [{"id": "local/qwen"}]}).encode()
    family = LOCAL_VLLM_FAMILY.with_endpoint(base)
    seen: list[dict[str, Any]] = []
    real_run_probe = preflight.run_probe

    def spy(config: dict[str, Any]) -> dict[str, Any]:
        seen.append(dict(config))
        return real_run_probe(config)

    monkeypatch.setattr(preflight, "run_probe", spy)
    credential, facts = preflight.probe_credential_and_catalog(
        family, owner_source_root=tmp_path / "missing-owner", model="local/qwen"
    )
    assert seen[0]["auth_provider"] == "none"
    assert credential["probed"] is False
    assert facts["model_listed"] is True
    assert "Authorization" not in catalog.requests[0][2]
    assert catalog.requests[0][1] == "/v1/models"


def test_credential_probe_child_runs_isolated_without_bytecode(tmp_path: Path) -> None:
    config = _probe_config(tmp_path, auth_provider="none", catalog_url=None)
    facts = preflight.run_probe(config)
    assert facts == {
        "credential_present": True,
        "expiry_ok": True,
        "expires_ms": 0,
        "endpoint_fixed": True,
        "catalog": None,
    }
    assert not list(Path(config["auth_module_path"]).parent.rglob("__pycache__"))
    assert not list(preflight._PROBE_PATH.parent.rglob("*preflight_probe*.pyc"))


# --- slice B: catalog check ---------------------------------------------------


@pytest.mark.parametrize(
    ("family", "expected"),
    [
        (CODEX_FAMILY, None),
        (COPILOT_FAMILY, "https://api.individual.githubcopilot.com/models"),
        (XAI_FAMILY, "https://api.x.ai/v1/models"),
        (LOCAL_VLLM_FAMILY, "http://127.0.0.1:2456/v1/models"),
    ],
)
def test_catalog_url_is_fixed_per_family(family: Any, expected: str | None) -> None:
    assert family.catalog_url == expected
    assert (family.catalog_path is None) == (expected is None)


def test_codex_family_has_no_catalog_and_uses_regex_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(
        preflight,
        "run_probe",
        lambda config: (
            seen.append(dict(config))
            or {
                "credential_present": True,
                "expiry_ok": True,
                "expires_ms": 5,
                "endpoint_fixed": True,
                "catalog": None,
            }
        ),
    )
    credential, catalog = preflight.probe_credential_and_catalog(
        CODEX_FAMILY, owner_source_root=tmp_path, model="gpt-5.4"
    )
    assert seen[0]["catalog_url"] is None
    assert credential["credential_present"] is True
    assert catalog == {
        "checked": False,
        "status_class": None,
        "catalog_count": None,
        "catalog_ids_sha256": None,
        "model_listed": None,
    }


def test_catalog_rejects_regex_valid_unserved_model(
    tmp_path: Path, catalog_server: tuple[_Catalog, str]
) -> None:
    catalog, base = catalog_server
    family = LOCAL_VLLM_FAMILY.with_endpoint(base)
    assert family.model_allowed("local/unserved")
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError,
        match=r"catalog does not serve local/unserved \(status_class=2xx\)",
    ):
        preflight.probe_credential_and_catalog(
            family, owner_source_root=tmp_path, model="local/unserved"
        )
    assert [item[0] for item in catalog.requests] == ["GET"]


def test_catalog_fails_closed_on_429_and_non_json(
    tmp_path: Path, catalog_server: tuple[_Catalog, str]
) -> None:
    catalog, base = catalog_server
    family = LOCAL_VLLM_FAMILY.with_endpoint(base)
    catalog.status = 429
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError,
        match=r"status_class=4xx",
    ):
        preflight.probe_credential_and_catalog(
            family, owner_source_root=tmp_path, model=MODEL
        )
    catalog.status = 200
    catalog.body = b"<html>not json</html>"
    with pytest.raises(
        comparison_jury.ProgramFoundryGepaComparisonJuryError,
        match=r"status_class=non_json",
    ):
        preflight.probe_credential_and_catalog(
            family, owner_source_root=tmp_path, model=MODEL
        )
    assert {item[0] for item in catalog.requests} == {"GET"}


@pytest.mark.parametrize("auth_provider", ["github-copilot", "xai", "none"])
def test_catalog_probe_sends_only_get_with_family_headers(
    tmp_path: Path,
    catalog_server: tuple[_Catalog, str],
    auth_provider: str,
) -> None:
    catalog, base = catalog_server
    facts = preflight.run_probe(
        _probe_config(
            tmp_path, auth_provider=auth_provider, catalog_url=base + "/models"
        )
    )
    assert facts["catalog"]["status_class"] == "2xx"
    assert facts["catalog"]["catalog_count"] == 2
    assert facts["catalog"]["model_listed"] is True
    assert (
        facts["catalog"]["catalog_ids_sha256"]
        == hashlib.sha256(
            json.dumps(sorted([MODEL, "x"]), separators=(",", ":")).encode()
        ).hexdigest()
    )
    method, path, headers = catalog.requests[0]
    assert (method, path) == ("GET", "/v1/models")
    assert headers["Accept-Encoding"] == "identity"
    if auth_provider == "none":
        assert "Authorization" not in headers
    else:
        assert headers["Authorization"] == f"Bearer {SECRET}"
    if auth_provider == "github-copilot":
        assert headers["Copilot-Integration-Id"] == "vscode-chat"
        assert headers["Editor-Version"] == "vscode/1.107.0"
    else:
        assert "Copilot-Integration-Id" not in headers
    assert len(catalog.requests) == 1


def test_catalog_probe_caps_body_and_reports_timeout(
    tmp_path: Path, catalog_server: tuple[_Catalog, str]
) -> None:
    catalog, base = catalog_server
    catalog.body = b'{"data": [' + b'{"id": "aaaaaaaa"},' * 120_000 + b'{"id": "z"}]}'
    assert len(catalog.body) > 1024 * 1024
    facts = preflight.run_probe(
        _probe_config(tmp_path, auth_provider="none", catalog_url=base + "/models")
    )
    assert facts["catalog"]["status_class"] == "body_too_large"
    assert facts["catalog"]["model_listed"] is False
    assert facts["catalog"]["catalog_count"] == 0
    closed = preflight.run_probe(
        _probe_config(
            tmp_path, auth_provider="none", catalog_url="http://127.0.0.1:9/v1/models"
        )
    )
    assert closed["catalog"]["status_class"] == "transport_error"
    assert closed["catalog"]["model_listed"] is False


def test_probe_env_is_scrubbed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    class _Completed:
        returncode = 0
        stdout = json.dumps(
            {
                "credential_present": True,
                "expiry_ok": True,
                "expires_ms": 0,
                "endpoint_fixed": True,
                "catalog": None,
            }
        ).encode()

    def fake_run(argv: list[str], **kwargs: Any) -> _Completed:
        seen["argv"] = argv
        seen.update(kwargs)
        return _Completed()

    monkeypatch.setenv("XAI_API_KEY", "leak")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid")
    monkeypatch.setattr(preflight.subprocess, "run", fake_run)
    preflight.run_probe({"auth_provider": "none", "model": MODEL, "catalog_url": None})
    assert seen["argv"][:3] == [sys.executable, "-I", "-B"]
    assert seen["argv"][3] == str(preflight._PROBE_PATH)
    assert "XAI_API_KEY" not in seen["env"]
    assert "HTTPS_PROXY" not in seen["env"]
    assert seen["env"]["PYTHONDONTWRITEBYTECODE"] == "1"
    assert seen["stdin"] is preflight.subprocess.DEVNULL
    assert seen["timeout"] == 5.0
    assert seen["start_new_session"] is True
    assert os.environ["XAI_API_KEY"] == "leak"

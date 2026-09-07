"""Adversarial custody and bounded transport tests; fixtures stay offline."""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from test_program_foundry_closure_check import ENTRY, invoke

import test_program_foundry_closure_check as shared

pure = shared.pure
saved = shared.saved


def small_request(pure, root: Path) -> dict:
    raw = b"{}"
    (root / "value.json").write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    ref = {"original_path": "/original/value.json", "sha256": digest}
    return {
        "schema_version": pure.REQUEST_SCHEMA,
        "phase": "after_jury",
        "verifier_profile_sha256": "0" * 64,
        "subject": {
            "schema_version": "misegraph-evidence-package-v1",
            "package_sha256": digest,
            "manifest_sha256": digest,
        },
        "expected": {role: dict(ref) for role in pure.EXPECTED},
        "roots": [str(root)],
        "locators": [
            {
                "sha256": digest,
                "bytes": 2,
                "root": 0,
                "path": "value.json",
                "aliases": [ref["original_path"]],
            }
        ],
        "limits": dict(pure.LIMITS),
    }


@pytest.mark.parametrize(
    "kind", ["symlink", "directory_symlink", "fifo", "writable", "changed", "missing"]
)
def test_descriptor_reads_fail_closed(tmp_path, pure, kind):
    request = small_request(pure, tmp_path)
    value = tmp_path / "value.json"
    if kind == "changed":
        value.write_bytes(b"[]")
    elif kind == "writable":
        value.chmod(0o666)
    elif kind == "missing":
        value.unlink()
    elif kind == "directory_symlink":
        (tmp_path / "link").symlink_to(tmp_path, target_is_directory=True)
        request["locators"][0]["path"] = "link/value.json"
    else:
        value.unlink()
        if kind == "symlink":
            value.symlink_to(ENTRY)
        else:
            os.mkfifo(value)
    s = pure.Snapshot(request)
    try:
        with pytest.raises(pure.Rejected):
            s.read("/original/value.json")
    finally:
        s.close()


@pytest.mark.parametrize(
    "kind",
    [
        "unknown",
        "duplicate",
        "absolute",
        "traversal",
        "file_count",
        "integer_bool",
        "limits",
        "depth",
    ],
)
def test_request_is_closed_and_bounded(tmp_path, pure, kind):
    request = small_request(pure, tmp_path)
    row = request["locators"][0]
    if kind == "unknown":
        request["profile_path"] = str(tmp_path)
    elif kind == "duplicate":
        request["locators"].append(dict(row))
    elif kind == "absolute":
        row["path"] = "/outside/value.json"
    elif kind == "traversal":
        row["path"] = "../value.json"
    elif kind == "file_count":
        request["locators"] = [row] * 257
    elif kind == "integer_bool":
        row["root"] = False
    elif kind == "limits":
        request["limits"]["files"] += 1
    else:
        row["path"] = "/".join(["x"] * 17)
    with pytest.raises(pure.Rejected):
        pure.Snapshot(request)


def test_snapshot_uses_once_captured_bytes_and_rejects_hardlink_alias(tmp_path, pure):
    request = small_request(pure, tmp_path)
    os.link(tmp_path / "value.json", tmp_path / "other.json")
    request["locators"].append(
        {
            **request["locators"][0],
            "path": "other.json",
            "aliases": ["/original/other.json"],
        }
    )
    s = pure.Snapshot(request)
    try:
        assert s.read("/original/value.json") == b"{}"
        with pytest.raises(pure.Rejected, match="duplicate_physical_file"):
            s.read("/original/other.json")
        (tmp_path / "value.json").write_bytes(b"[]")
        assert s.read("/original/value.json") == b"{}"
    finally:
        s.close()


def test_strict_json_bounds_and_boolean_equality(pure):
    for raw in (b"[" * 66 + b"0" + b"]" * 66, b'{"\\ud800":1}'):
        with pytest.raises(pure.Rejected):
            pure.decode(raw)
    with pytest.raises(pure.Rejected):
        pure.equal(True, 1)


@pytest.mark.parametrize(
    "relative",
    [
        "import/intent.json",
        "import/inputs.json",
        "foundry/runtime/runtime_episode.json",
        "foundry/candidate/manifest.json",
        "foundry/gepa-experiment/candidate-comparison.json",
        "foundry/gepa-experiment/comparison-jury-results.json",
    ],
)
def test_rehashed_leaf_substitution_is_not_a_closure(saved, tmp_path, relative):
    root, original = saved
    request = copy.deepcopy(original)
    copy_root = tmp_path / "snapshot"
    copy_root.mkdir(mode=0o700)
    for row in request["locators"]:
        dest = copy_root / row["path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / row["path"], dest)
    request["roots"] = [str(copy_root)]
    row = next(x for x in request["locators"] if x["path"] == relative)
    dest = copy_root / relative
    payload = json.loads(dest.read_bytes())
    payload["substituted_unknown_field"] = "rehashed"
    raw = json.dumps(payload).encode()
    dest.write_bytes(raw)
    row.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    result = invoke(json.dumps(request).encode())
    assert result.returncode == 0
    assert json.loads(result.stdout)["status"] == "invalid"
    assert hashlib.sha256((root / relative).read_bytes()).hexdigest() != row["sha256"]


def test_all_failed_and_duplicate_model_names_never_become_live(pure):
    jury = importlib.import_module("program_foundry_closure_jury")
    with pytest.raises(pure.Rejected, match="all_jurors_failed"):
        jury.aggregate([{"status": "failed"}])
    from dspx.services.program_foundry_provider_evidence import (
        provider_evidence_kind_for_model,
        provider_evidence_kind_for_provider,
    )

    for name in (
        "foundry-dspy-lm-auth-local-vllm",
        "foundry-dspy-lm-auth-test-double",
        "openai-compatible",
    ):
        assert provider_evidence_kind_for_provider(name) is None
    assert provider_evidence_kind_for_model("local/live-sounding") is None


def test_stream_overflow_is_killed_without_communicate(monkeypatch):
    from dspx.services.program_foundry_bounded_child import (
        ChildOutputLimit,
        run_bounded_child,
    )

    monkeypatch.setattr(
        subprocess.Popen,
        "communicate",
        lambda *a, **k: pytest.fail("unbounded communicate"),
    )
    with pytest.raises(ChildOutputLimit):
        run_bounded_child(
            [
                sys.executable,
                "-I",
                "-S",
                "-B",
                "-c",
                "import os\nwhile True: os.write(1,b'x'*65536)",
            ],
            payload=b"x" * 262144,
            env={},
            timeout=5,
            max_output=4096,
        )
    result = run_bounded_child(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            "-c",
            "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())",
        ],
        payload=b"test",
        env={},
        timeout=5,
        max_output=4,
    )
    assert result.stdout == b"test" and result.returncode == 0


def test_unprobed_preflight_does_not_claim_credentials_or_reachability(
    tmp_path, monkeypatch
):
    from test_program_foundry_gepa_comparison_jury_preflight import (
        _task_local_env,
        _revalidator_capture,
    )
    from dspx.services import (
        program_foundry_gepa_comparison_jury_preflight as preflight,
    )
    from dspx.services.program_foundry_gepa_comparison_jury_runtime import (
        execution_request,
    )

    owner = tmp_path / "owner"
    owner.mkdir()
    experiment = tmp_path / "experiment"
    experiment.mkdir(mode=0o700)
    _task_local_env(monkeypatch, tmp_path, owner)
    _revalidator_capture(monkeypatch, [])
    monkeypatch.setattr(
        preflight,
        "probe_credential_and_catalog",
        lambda *a, **k: (
            {
                "probed": False,
                "credential_present": False,
                "expiry_ok": False,
                "expires_ms": 0,
                "endpoint_fixed": True,
            },
            {
                "checked": False,
                "status_class": None,
                "catalog_count": None,
                "catalog_ids_sha256": None,
                "model_listed": None,
            },
        ),
    )
    request = execution_request(
        provider="foundry-dspy-lm-auth-local-vllm",
        adjudicator_id="unit",
        adjudicator_kind="unit",
        adjudicator_repo=None,
        max_jurors=1,
        owner_source_root=owner,
        execution_task_id=6000,
        execution_claimant="pi:unit",
        model="local/unit",
        execution_repo_root=tmp_path,
    )
    facts = preflight.run_task_local_preflight(
        request, experiment_root=experiment, expected_juror_count=1, repo_root=tmp_path
    )
    assert facts["proves"] == []
    assert facts["checks"] == {
        "credential": "not_applicable",
        "catalog": "not_applicable",
        "reachability": "not_checked",
    }
    assert "capacity_at_completion" in facts["cannot_prove"]


def test_relocated_independent_stdlib_installation(saved, tmp_path):
    from test_program_foundry_closure_check import SERVICES, profile

    _, request = saved
    installation = tmp_path / "installed"
    installation.mkdir(mode=0o700)
    for row in profile()["modules"]:
        raw = (SERVICES / row["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == row["sha256"]
        (installation / row["path"]).write_bytes(raw)
    # Neither an unreviewed sibling nor a changed current execution-policy module
    # participates in historical verification or shadows the trusted stdlib.
    for name in ("math.py", "program_foundry_gepa_comparison_jury_owner.py"):
        (installation / name).write_text(
            "OWNER_COMMIT = 'unreviewed'\nraise RuntimeError('must not be imported')\n"
        )
    result = invoke(json.dumps(request).encode(), installation / ENTRY.name)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "verified", report
    assert report["verifier_profile_sha256"] == request["verifier_profile_sha256"]
    assert report["review_eligible"] is False
    assert not (installation / "__pycache__").exists()


def test_execution_context_is_explicit_not_package_layout(tmp_path, monkeypatch):
    from dspx.services import program_foundry_gepa_comparison_jury_runtime as runtime

    monkeypatch.setattr(runtime, "__file__", "/wheel/site-packages/dspx/runtime.py")
    with pytest.raises(runtime.ProgramFoundryGepaComparisonJuryError, match="explicit"):
        runtime.execution_repository({})
    assert (
        runtime.execution_repository({"execution_repo_root": str(tmp_path)}) == tmp_path
    )

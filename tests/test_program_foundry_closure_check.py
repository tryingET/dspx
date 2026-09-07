"""Offline protocol and immutable saved-closure tests; no model/owner execution."""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

SERVICES = Path(__file__).resolve().parents[1] / "packages/dspx-core/src/dspx/services"
ENTRY = SERVICES / "program_foundry_closure_check.py"


@pytest.fixture
def pure():
    sys.path.insert(0, str(SERVICES))
    try:
        yield importlib.import_module("program_foundry_closure_io")
    finally:
        sys.path.remove(str(SERVICES))


def invoke(raw: bytes, entry: Path = ENTRY) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(entry)],
        input=raw,
        capture_output=True,
        timeout=15,
        env={"LANG": "C.UTF-8"},
    )


def profile() -> dict:
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(ENTRY), "--profile"],
        capture_output=True,
        timeout=10,
        env={},
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def saved_request(root: Path, limits: dict) -> dict:
    names = {
        "package_manifest": "package/manifest.json",
        "import_binding": "import/misegraph-evidence-binding.json",
        "import_provenance": "import/misegraph-import-provenance.json",
        "imported_intent": "import/intent.json",
        "imported_inputs": "import/inputs.json",
        "jury_receipt": "foundry/gepa-experiment/comparison-jury-receipt.json",
        "adjudication": "foundry/gepa-experiment/comparison-adjudication.json",
    }
    paths = []
    for directory in ("package", "import", "foundry"):
        for path in sorted((root / directory).rglob("*")):
            assert not path.is_symlink()
            if path.is_file():
                paths.append(path)
    paths.append(root / "quality-proposal.json")
    if (root / "answers.json").is_file():
        paths.append(root / "answers.json")
    locators = []
    for path in paths:
        assert path.stat().st_size <= limits["artifact_bytes"]
        raw = path.read_bytes()
        locators.append(
            {
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
                "root": 0,
                "path": str(path.relative_to(root)),
                "aliases": [str(path)],
            }
        )
    by_alias = {x["aliases"][0]: x for x in locators}
    expected = {
        role: {
            "original_path": str(root / name),
            "sha256": by_alias[str(root / name)]["sha256"],
        }
        for role, name in names.items()
    }
    manifest = json.loads((root / names["package_manifest"]).read_bytes())
    return {
        "schema_version": "dspx-foundry-closure-check-request-v1",
        "phase": "after_jury",
        "verifier_profile_sha256": profile()["verifier_profile_sha256"],
        "subject": {
            "schema_version": "misegraph-evidence-package-v1",
            "manifest_sha256": expected["package_manifest"]["sha256"],
            "package_sha256": manifest["package_sha256"],
        },
        "expected": expected,
        "roots": [str(root)],
        "locators": locators,
        "limits": limits,
    }


@pytest.fixture
def saved(pure):
    raw = os.environ.get("DSPX_CLOSURE_SAVED_ROOT")
    if not raw:
        pytest.skip("requires explicitly selected immutable saved closure")
    root = Path(raw)
    request = saved_request(root, pure.LIMITS)
    return root, request


@pytest.mark.parametrize(
    "raw", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":1e999}', b'"\\ud800"', b"{} {}"]
)
def test_strict_json(pure, raw):
    with pytest.raises(pure.Rejected):
        pure.decode(raw)


def test_installed_profile_is_independently_recomputable():
    data = profile()
    for item in data["modules"]:
        assert (
            hashlib.sha256((SERVICES / item["path"]).read_bytes()).hexdigest()
            == item["sha256"]
        )
    raw = json.dumps(
        data["modules"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    assert (
        hashlib.sha256(b"dspx-foundry-verifier-profile-v1\0" + raw).hexdigest()
        == data["verifier_profile_sha256"]
    )


def test_invocation_requires_isolation():
    result = subprocess.run(
        [sys.executable, "-B", str(ENTRY)], input=b"{}", capture_output=True, timeout=5
    )
    assert result.returncode == 2
    assert result.stdout == b""


def test_bad_request_exits_nonzero():
    result = invoke(b"{}")
    assert result.returncode == 2
    assert result.stdout == b""


def test_saved_complete_closure_limited_and_originals_unchanged(saved, pure):
    root, request = saved
    before = {x["path"]: x["sha256"] for x in request["locators"]}
    raw = json.dumps(request).encode() + b"\n"
    result = invoke(raw)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "verified", report
    assert report["request_sha256"] == hashlib.sha256(raw).hexdigest()
    assert report["verifier_profile_sha256"] == request["verifier_profile_sha256"]
    assert all(report["identities"].values())
    assert report["quality"] == {
        "origin": "injected_test_double",
        "acceptance": "unknown",
    }
    assert report["review_eligible"] is False
    assert report["claim_ceiling"] == "historical_bytes_only"
    assert report["origins"]["jury"] == "historical_owner_journal"
    assert report["historical_authority"] == "unknown"
    assert {
        p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in before
    } == before


def test_saved_detailed_closure_contracts(saved, pure):
    # Deliberately calls only the stdlib pure modules for precise assertion tracebacks.
    _, request = saved
    core = importlib.import_module("program_foundry_closure_core")
    gepa = importlib.import_module("program_foundry_closure_gepa")
    jury = importlib.import_module("program_foundry_closure_jury")
    s = pure.Snapshot(request)
    report = {"quality": {}, "origins": {}, "identities": {}}
    try:
        state = core.source_closure(s, report)
        state = gepa.verify_gepa(s, state, report)
        jury.verify_jury(s, state, report)
    finally:
        s.close()


@pytest.mark.parametrize(
    "change,status",
    [("profile", "unsupported"), ("package", "invalid"), ("missing", "incomplete")],
)
def test_saved_request_substitutions(saved, change, status):
    _, request = saved
    request = copy.deepcopy(request)
    if change == "profile":
        request["verifier_profile_sha256"] = "0" * 64
    elif change == "package":
        request["subject"]["package_sha256"] = "0" * 64
    else:
        request["locators"] = [
            x
            for x in request["locators"]
            if x["path"] != "foundry/candidate/program.py"
        ]
    result = invoke(json.dumps(request).encode())
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["status"] == status, report
    assert report["review_eligible"] is False

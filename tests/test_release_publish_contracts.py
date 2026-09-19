"""Offline release contracts: real archive bytes, synthetic authority, no publication."""

from __future__ import annotations

import hashlib
import hmac
import importlib.util
import io
import json
import re
import subprocess
import sys
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "a" * 40
VERSION = "0.3.0"
PACKAGES = ("dspx-core", "dspx-forge")
LICENSE_EXPRESSION = "LicenseRef-Apache-2.0-with-AI-Rider"
# Deliberately synthetic: exercises the byte/rider validator, not legal sufficiency.
LICENSE_BYTES = (
    b"Synthetic license\nADDITIONAL RIDER / RESTRICTION\nno rights are granted\n"
)
CI_JOBS = {
    "Quality and contracts",
    "Runtime invariants",
    "Coverage ratchet",
    "Build and package smoke",
    *(
        f"Tests ({shard})"
        for shard in ("core-0", "core-1", "core-2", "core-3", "forge", "slow")
    ),
}


def load_script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        f"release_contract_{name}", ROOT / "scripts/release" / f"{name}.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def scripts(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    artifacts = load_script("artifacts")
    monkeypatch.setitem(sys.modules, "artifacts", artifacts)
    # Never contact GitHub or start package installers, including on regressions.
    monkeypatch.setattr(
        subprocess, "run", Mock(side_effect=AssertionError("unmocked subprocess"))
    )
    monkeypatch.setattr(
        subprocess,
        "check_output",
        Mock(side_effect=AssertionError("unmocked subprocess")),
    )
    return SimpleNamespace(
        artifacts=artifacts, ci=load_script("ci"), install=load_script("install")
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metadata(package: str) -> bytes:
    text = (
        f"Metadata-Version: 2.4\nName: {package}\nVersion: {VERSION}\n"
        f"License-Expression: {LICENSE_EXPRESSION}\nLicense-File: LICENSE\n"
        "Requires-Python: >=3.13,<3.15\n"
    )
    if package == "dspx-forge":
        text += f"Requires-Dist: dspx-core>={VERSION},<0.4.0\n"
    return (text + "\nSynthetic release fixture.\n").encode()


def archive(path: Path, row: dict[str, Any], raw: bytes, license_bytes: bytes) -> None:
    stem = f"{row['package'].replace('-', '_')}-{row['version']}"
    if row["kind"] == "wheel":
        with zipfile.ZipFile(path, "w") as wheel:
            wheel.writestr(f"{stem}.dist-info/METADATA", raw)
            wheel.writestr(f"{stem}.dist-info/licenses/LICENSE", license_bytes)
            wheel.writestr(
                f"{stem}.dist-info/WHEEL",
                "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
            )
    else:
        with tarfile.open(path, "w:gz") as sdist:
            for name, content in (("PKG-INFO", raw), ("LICENSE", license_bytes)):
                member = tarfile.TarInfo(f"{stem}/{name}")
                member.size = len(content)
                sdist.addfile(member, io.BytesIO(content))


@dataclass
class Candidate:
    dist: Path
    data: dict[str, Any]

    def save(self) -> str:
        path = self.dist / "release-manifest.json"
        path.write_text(json.dumps(self.data), encoding="utf-8")
        return digest(path)

    def replace(
        self, row: dict[str, Any], raw: bytes, license_bytes: bytes = LICENSE_BYTES
    ) -> None:
        path = self.dist / row["filename"]
        archive(path, row, raw, license_bytes)
        row.update(sha256=digest(path), bytes=path.stat().st_size)

    def verify(self, scripts: SimpleNamespace) -> dict[str, Any]:
        return scripts.artifacts.load_and_verify(self.dist, COMMIT, self.save())


@pytest.fixture
def candidate(tmp_path: Path) -> Candidate:
    dist = tmp_path / "dist"
    dist.mkdir()
    data: dict[str, Any] = {
        "schema": "dspx-package-release-v1",
        "commit": COMMIT,
        "ak_scope_evidence": "AK-evidence:5785",
        "versions": dict.fromkeys(PACKAGES, VERSION),
        "license_sha256": hashlib.sha256(LICENSE_BYTES).hexdigest(),
        "files": [],
    }
    result = Candidate(dist, data)
    for package in PACKAGES:
        for kind, suffix in (("wheel", "-py3-none-any.whl"), ("sdist", ".tar.gz")):
            row = {
                "filename": f"{package.replace('-', '_')}-{VERSION}{suffix}",
                "package": package,
                "version": VERSION,
                "kind": kind,
            }
            result.replace(row, metadata(package))
            data["files"].append(row)
    result.save()
    return result


def test_real_archive_pair_validates(
    candidate: Candidate, scripts: SimpleNamespace
) -> None:
    assert candidate.verify(scripts) == candidate.data
    assert {row["kind"] for row in candidate.data["files"]} == {"wheel", "sdist"}


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("commit", "b" * 40, "source mismatch"),
        ("schema", "other", "source mismatch"),
        ("ak_scope_evidence", "fixture-only", "scope evidence"),
        ("license_sha256", "0" * 64, "packaged license bytes differ"),
    ],
)
def test_manifest_identity_rejected(
    candidate: Candidate, scripts: SimpleNamespace, field: str, value: str, message: str
) -> None:
    candidate.data[field] = value
    with pytest.raises(scripts.artifacts.ArtifactError, match=message):
        candidate.verify(scripts)


@pytest.mark.parametrize(
    ("commit", "manifest_hash", "message"),
    [
        ("bad", None, "invalid expected commit"),
        (COMMIT, "bad", "invalid expected manifest digest"),
        (COMMIT, "0" * 64, "manifest digest mismatch"),
        ("b" * 40, None, "source mismatch"),
    ],
)
def test_expected_identity_is_not_self_authorizing(
    candidate: Candidate,
    scripts: SimpleNamespace,
    commit: str,
    manifest_hash: str | None,
    message: str,
) -> None:
    actual = candidate.save()
    with pytest.raises(scripts.artifacts.ArtifactError, match=message):
        scripts.artifacts.load_and_verify(
            candidate.dist, commit, manifest_hash or actual
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("sha256", "0" * 64, "file digest mismatch"),
        ("bytes", 1, "file size mismatch"),
        ("bytes", True, "file size mismatch"),
        ("package", "foreign", "file identity mismatch"),
        ("version", "0.4.0", "file identity mismatch"),
        ("kind", "sdist", "file identity mismatch"),
    ],
)
def test_manifest_file_binding(
    candidate: Candidate, scripts: SimpleNamespace, field: str, value: Any, message: str
) -> None:
    candidate.data["files"][0][field] = value
    with pytest.raises(scripts.artifacts.ArtifactError, match=message):
        candidate.verify(scripts)


@pytest.mark.parametrize(
    "mutation",
    ["extra", "missing", "duplicate-row", "reordered", "symlink", "tampered"],
)
def test_exact_distribution_inventory(
    candidate: Candidate, scripts: SimpleNamespace, mutation: str
) -> None:
    row = candidate.data["files"][0]
    path = candidate.dist / row["filename"]
    message = "unexpected or missing distribution files"
    if mutation == "extra":
        (candidate.dist / "unapproved.whl").write_bytes(b"unexpected")
    elif mutation == "missing":
        path.unlink()
    elif mutation == "duplicate-row":
        candidate.data["files"][1] = row.copy()
        message = "file identity mismatch"
    elif mutation == "reordered":
        candidate.data["files"].reverse()
        message = "file identity mismatch"
    elif mutation == "symlink":
        target = candidate.dist.parent / "original.whl"
        path.rename(target)
        path.symlink_to(target)
        message = "not a regular artifact"
    else:
        payload = path.read_bytes()
        path.write_bytes(bytes([payload[0] ^ 1]) + payload[1:])
        message = "file digest mismatch"
    with pytest.raises(scripts.artifacts.ArtifactError, match=message):
        candidate.verify(scripts)


@pytest.mark.parametrize("version", ["0.3.0rc1", "v0.3.0", "0.3", "01.3.0"])
def test_unstable_or_malformed_versions(
    candidate: Candidate, scripts: SimpleNamespace, version: str
) -> None:
    candidate.data["versions"] = dict.fromkeys(PACKAGES, version)
    with pytest.raises(
        scripts.artifacts.ArtifactError, match="stable numeric version required"
    ):
        candidate.verify(scripts)


def test_uncoordinated_versions(candidate: Candidate, scripts: SimpleNamespace) -> None:
    candidate.data["versions"]["dspx-forge"] = "0.4.0"
    with pytest.raises(scripts.artifacts.ArtifactError, match="coordinated pair"):
        candidate.verify(scripts)


@pytest.mark.parametrize("kind", ["wheel", "sdist"])
@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (b"Name: dspx-forge", b"Name: foreign", "metadata mismatch: Name"),
        (b"Version: 0.3.0", b"Version: 0.4.0", "metadata mismatch: Version"),
        (
            b"Version: 0.3.0",
            b"Version: 0.3.0\nVersion: 0.3.0",
            "metadata mismatch: Version",
        ),
        (
            LICENSE_EXPRESSION.encode(),
            b"Apache-2.0",
            "metadata mismatch: License-Expression",
        ),
        (
            b"License-File: LICENSE",
            b"License-File: NOTICE",
            "license inventory mismatch",
        ),
        (b">=3.13,<3.15", b">=3.12", "Python support drift"),
        (
            b"dspx-core>=0.3.0,<0.4.0",
            b"dspx-core>=0.2.0,<0.4.0",
            "compatibility mismatch",
        ),
        (
            b"dspx-core>=0.3.0,<0.4.0",
            b"dspx-core>=0.3.0,<1.0.0",
            "compatibility mismatch",
        ),
        (b"Requires-Dist: dspx-core>=0.3.0,<0.4.0\n", b"", "compatibility mismatch"),
        (
            b"Requires-Dist: dspx-core>=0.3.0,<0.4.0",
            b"Requires-Dist: dspx-core>=0.3.0,<0.4.0\nRequires-Dist: dspx-core>=0.3.0,<0.4.0",
            "compatibility mismatch",
        ),
    ],
)
def test_archive_metadata_rejected_with_fresh_hashes(
    candidate: Candidate,
    scripts: SimpleNamespace,
    kind: str,
    old: bytes,
    new: bytes,
    message: str,
) -> None:
    row = next(
        r
        for r in candidate.data["files"]
        if r["package"] == "dspx-forge" and r["kind"] == kind
    )
    candidate.replace(row, metadata("dspx-forge").replace(old, new))
    with pytest.raises(scripts.artifacts.ArtifactError, match=message):
        candidate.verify(scripts)


@pytest.mark.parametrize("kind", ["wheel", "sdist"])
def test_license_bytes_bound_in_each_archive(
    candidate: Candidate, scripts: SimpleNamespace, kind: str
) -> None:
    row = next(r for r in candidate.data["files"] if r["kind"] == kind)
    candidate.replace(row, metadata(row["package"]), LICENSE_BYTES + b"changed")
    with pytest.raises(
        scripts.artifacts.ArtifactError, match="packaged license bytes differ"
    ):
        candidate.verify(scripts)


@pytest.mark.parametrize(
    "missing", [b"ADDITIONAL RIDER / RESTRICTION", b"no rights are granted"]
)
def test_license_rider_required_even_with_matching_hash(
    candidate: Candidate, scripts: SimpleNamespace, missing: bytes
) -> None:
    license_bytes = LICENSE_BYTES.replace(missing, b"")
    candidate.data["license_sha256"] = hashlib.sha256(license_bytes).hexdigest()
    for row in candidate.data["files"]:
        candidate.replace(row, metadata(row["package"]), license_bytes)
    with pytest.raises(scripts.artifacts.ArtifactError, match="binding rider missing"):
        candidate.verify(scripts)


@pytest.mark.parametrize("nested", [False, True])
def test_duplicate_manifest_keys_rejected(
    candidate: Candidate, scripts: SimpleNamespace, nested: bool
) -> None:
    path = candidate.dist / "release-manifest.json"
    text = path.read_text()
    key, value = ("dspx-core", VERSION) if nested else ("commit", COMMIT)
    original = json.dumps(key) + ": " + json.dumps(value)
    path.write_text(text.replace(original, original + ", " + original, 1))
    with pytest.raises(scripts.artifacts.ArtifactError, match="duplicate manifest key"):
        scripts.artifacts.load_and_verify(candidate.dist, COMMIT, digest(path))


def test_create_binds_clean_source_and_real_bytes(
    candidate: Candidate,
    scripts: SimpleNamespace,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "source"
    repo.mkdir()
    (repo / "LICENSE").write_bytes(LICENSE_BYTES)
    for package, relative in (
        ("dspx-core", "packages/dspx-core"),
        ("dspx-forge", "apps/forge"),
    ):
        directory = repo / relative
        directory.mkdir(parents=True)
        (directory / "LICENSE").write_bytes(LICENSE_BYTES)
        (directory / "pyproject.toml").write_text(
            f'[project]\nname = "{package}"\nversion = "{VERSION}"\nlicense = "{LICENSE_EXPRESSION}"\n'
        )
    candidate_manifest = candidate.dist / "release-manifest.json"
    candidate_manifest.unlink()
    git = Mock(side_effect=[COMMIT + "\n", ""])
    monkeypatch.setattr(subprocess, "check_output", git)
    actual = scripts.artifacts.create(candidate.dist, repo, COMMIT, "AK-evidence:5785")
    assert hmac.compare_digest(actual, digest(candidate_manifest))
    assert (
        scripts.artifacts.load_and_verify(candidate.dist, COMMIT, actual)
        == candidate.data
    )
    assert [call.args[0] for call in git.call_args_list] == [
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        ["git", "-C", str(repo), "status", "--porcelain"],
    ]


@pytest.mark.parametrize(
    ("responses", "message"),
    [
        (["b" * 40], "wrong source checkout"),
        ([COMMIT, " M source.py"], "clean committed source"),
    ],
)
def test_create_rejects_wrong_or_dirty_source(
    candidate: Candidate,
    scripts: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    responses: list[str],
    message: str,
) -> None:
    monkeypatch.setattr(subprocess, "check_output", Mock(side_effect=responses))
    with pytest.raises(scripts.artifacts.ArtifactError, match=message):
        scripts.artifacts.create(
            candidate.dist, candidate.dist.parent, COMMIT, "AK-evidence:5785"
        )


@pytest.fixture
def ci_run() -> dict[str, Any]:
    return {
        "head_sha": COMMIT,
        "head_branch": "main",
        "path": ".github/workflows/ci.yml",
        "event": "push",
        "head_repository": {"full_name": "tryingET/dspx"},
        "conclusion": "success",
        "status": "completed",
        "run_attempt": 1,
    }


def successful_jobs() -> list[dict[str, str]]:
    return [{"name": name, "conclusion": "success"} for name in sorted(CI_JOBS)]


def test_ci_first_attempt_exact_source_and_inventory(
    scripts: SimpleNamespace, ci_run: dict[str, Any]
) -> None:
    scripts.ci.validate_run(ci_run, successful_jobs(), COMMIT)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("head_sha", "b" * 40),
        ("head_branch", "topic"),
        ("path", ".github/workflows/other.yml"),
        ("event", "pull_request"),
        ("head_repository", {"full_name": "foreign/dspx"}),
        ("conclusion", "failure"),
        ("status", "in_progress"),
        ("run_attempt", 2),
        ("run_attempt", None),
    ],
)
def test_ci_rejects_wrong_source_or_attempt(
    scripts: SimpleNamespace, ci_run: dict[str, Any], field: str, value: Any
) -> None:
    ci_run[field] = value
    with pytest.raises(ValueError):
        scripts.ci.validate_run(ci_run, successful_jobs(), COMMIT)


@pytest.mark.parametrize(
    "mutation", ["missing", "extra", "duplicate", "failed", "skipped"]
)
def test_ci_rejects_nonexact_jobs(
    scripts: SimpleNamespace, ci_run: dict[str, Any], mutation: str
) -> None:
    jobs = successful_jobs()
    if mutation == "missing":
        jobs.pop()
    elif mutation == "extra":
        jobs.append({"name": "unexpected", "conclusion": "success"})
    elif mutation == "duplicate":
        jobs[-1] = jobs[0].copy()
    else:
        jobs[0]["conclusion"] = "failure" if mutation == "failed" else "skipped"
    with pytest.raises(ValueError, match="CI job"):
        scripts.ci.validate_run(ci_run, jobs, COMMIT)


@pytest.fixture
def protected_environment() -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        {
            "name": "pypi",
            "can_admins_bypass": False,
            "protection_rules": [
                {
                    "type": "required_reviewers",
                    "reviewers": [{"type": "User", "reviewer": {"id": 260287438}}],
                }
            ],
            "deployment_branch_policy": {
                "protected_branches": False,
                "custom_branch_policies": True,
            },
        },
        {"branch_policies": [{"name": "main", "type": "branch"}]},
    )


def test_environment_requires_owner_and_main_only(
    scripts: SimpleNamespace,
    protected_environment: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    scripts.ci.validate_environment(*protected_environment)


@pytest.mark.parametrize(
    "mutation",
    [
        "name",
        "no-reviewer",
        "admin-bypass",
        "missing-bypass",
        "extra-rule",
        "wrong-owner",
        "team",
        "extra-reviewer",
        "policy",
        "no-branch",
        "extra-branch",
        "tag",
        "branch",
    ],
)
def test_environment_rejects_weaker_protection(
    scripts: SimpleNamespace,
    protected_environment: tuple[dict[str, Any], dict[str, Any]],
    mutation: str,
) -> None:
    environment, branches = protected_environment
    rule = environment["protection_rules"][0]
    reviewer = rule["reviewers"][0]
    if mutation == "name":
        environment["name"] = "staging"
    elif mutation == "admin-bypass":
        environment["can_admins_bypass"] = True
    elif mutation == "missing-bypass":
        del environment["can_admins_bypass"]
    elif mutation == "no-reviewer":
        environment["protection_rules"] = []
    elif mutation == "extra-rule":
        environment["protection_rules"].append(rule.copy())
    elif mutation == "wrong-owner":
        reviewer["reviewer"]["id"] = 1
    elif mutation == "team":
        reviewer["type"] = "Team"
    elif mutation == "extra-reviewer":
        rule["reviewers"].append({"type": "User", "reviewer": {"id": 1}})
    elif mutation == "policy":
        environment["deployment_branch_policy"]["protected_branches"] = True
    elif mutation == "no-branch":
        branches["branch_policies"] = []
    elif mutation == "extra-branch":
        branches["branch_policies"].append({"name": "topic", "type": "branch"})
    elif mutation == "tag":
        branches["branch_policies"][0]["type"] = "tag"
    else:
        branches["branch_policies"][0]["name"] = "*"
    with pytest.raises(ValueError):
        scripts.ci.validate_environment(environment, branches)


@pytest.mark.parametrize("registry", [False, True])
@pytest.mark.parametrize("python", ["3.13", "3.14"])
def test_install_commands_use_fresh_environments_and_exact_targets(
    candidate: Candidate,
    scripts: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    registry: bool,
    python: str,
) -> None:
    calls = Mock()
    monkeypatch.setattr(subprocess, "run", calls)
    # Keep even the temporary environment scaffolding inside pytest-owned scratch.
    monkeypatch.setattr(scripts.install.tempfile, "tempdir", str(tmp_path))
    monkeypatch.setenv("PYTHONPATH", "/untrusted")
    monkeypatch.setenv("PIP_INDEX_URL", "https://invalid.example")
    monkeypatch.setenv("UV_INDEX", "https://invalid.example")
    monkeypatch.setenv("DSPX_SECRET", "synthetic")
    scripts.install.prove(candidate.dist, COMMIT, candidate.save(), python, registry)
    kinds = ("wheel",) if registry else ("wheel", "sdist")
    assert calls.call_count == len(kinds) * 2 * 5
    environments = set()
    for index, (kind, package) in enumerate((k, p) for k in kinds for p in PACKAGES):
        group = calls.call_args_list[index * 5 : (index + 1) * 5]
        commands = [call.args[0] for call in group]
        root = group[0].kwargs["cwd"]
        assert root.parent == tmp_path
        environment = root / f"{kind}-{package}"
        assert environment not in environments
        environments.add(environment)
        executable = str(environment / "bin/python")
        assert commands[0] == ["uv", "venv", "--python", python, str(environment)]
        expected = [
            "uv",
            "pip",
            "install",
            "--python",
            executable,
            "--index-url",
            "https://pypi.org/simple",
            "--no-sources",
        ]
        if registry:
            # Forge alone must resolve its published Core dependency: no independent Core pin/file.
            expected += [f"{package}=={VERSION}"]
        else:
            if kind == "sdist":
                expected += ["--no-binary", "dspx-core,dspx-forge"]
            targets = PACKAGES if package == "dspx-forge" else ("dspx-core",)
            expected += [
                str(candidate.dist / row["filename"])
                for row in candidate.data["files"]
                if row["kind"] == kind and row["package"] in targets
            ]
        assert commands[1] == expected
        assert commands[2] == ["uv", "pip", "check", "--python", executable]
        assert commands[3][:3] == [executable, "-I", "-c"]
        assert f"assert m.version('dspx-core') == {VERSION!r}" in commands[3][3]
        if package == "dspx-forge":
            assert f"assert m.version('dspx-forge') == {VERSION!r}" in commands[3][3]
        else:
            assert "assert not any(d.metadata['Name']=='dspx-forge'" in commands[3][3]
        command = "dspx-forge" if package == "dspx-forge" else "dspx"
        assert commands[4] == [str(environment / "bin" / command), "--help"]
        for call in group:
            assert call.kwargs["check"] is True
            assert call.kwargs["cwd"] == root
            env = call.kwargs["env"]
            assert {
                key
                for key in env
                if key.startswith(("PYTHONPATH", "PYTHONHOME", "PIP_", "UV_", "DSPX_"))
            } == {"UV_NO_CONFIG", "UV_NO_PROGRESS"}
            assert env["UV_NO_CONFIG"] == "true"
            assert env["MLFLOW_TRACKING_URI"] == "file:./mlruns"
    report = json.loads(capsys.readouterr().out)
    assert report == {
        "commit": COMMIT,
        "versions": candidate.data["versions"],
        "python": python,
        "registry_install": registry,
        "status": "pass",
        "live_provider_claim": False,
    }


def test_install_verifies_before_any_subprocess(
    candidate: Candidate, scripts: SimpleNamespace
) -> None:
    with pytest.raises(
        scripts.artifacts.ArtifactError, match="manifest digest mismatch"
    ):
        scripts.install.prove(candidate.dist, COMMIT, "0" * 64, "3.13", False)
    assert isinstance(subprocess.run, Mock)
    subprocess.run.assert_not_called()


def test_install_failure_never_reports_pass(
    candidate: Candidate,
    scripts: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    calls = Mock(side_effect=subprocess.CalledProcessError(1, ["uv"]))
    monkeypatch.setattr(subprocess, "run", calls)
    monkeypatch.setattr(scripts.install.tempfile, "tempdir", str(tmp_path))
    with pytest.raises(subprocess.CalledProcessError):
        scripts.install.prove(candidate.dist, COMMIT, candidate.save(), "3.13", False)
    assert calls.call_count == 1
    assert capsys.readouterr().out == ""


@pytest.fixture
def workflow() -> dict[str, Any]:
    # BaseLoader preserves GitHub's YAML 1.2 `on` key rather than interpreting it as True.
    return yaml.load(
        (ROOT / ".github/workflows/release.yml").read_text(), Loader=yaml.BaseLoader
    )


def test_workflow_manual_main_only_and_pinned_actions(workflow: dict[str, Any]) -> None:
    assert set(workflow["on"]) == {"workflow_dispatch"}
    assert workflow["permissions"] == {"contents": "read", "actions": "read"}
    assert workflow["concurrency"]["cancel-in-progress"] == "false"
    condition = workflow["jobs"]["candidate"]["if"]
    assert (
        condition
        == "github.ref == 'refs/heads/main' && github.repository == 'tryingET/dspx'"
    )
    for job in workflow["jobs"].values():
        for step in job["steps"]:
            if "uses" in step:
                assert re.fullmatch(r"[\w.-]+/[\w./-]+@[a-f0-9]{40}", step["uses"])
            if step.get("uses", "").startswith("actions/checkout@"):
                # Public configuration flag, not a credential comparison.
                assert step["with"]["persist-credentials"] in ("false",)


def test_workflow_writer_permissions_and_no_candidate_installation(
    workflow: dict[str, Any],
) -> None:
    jobs = workflow["jobs"]
    writers = {
        name
        for name, job in jobs.items()
        if "write" in job.get("permissions", workflow["permissions"]).values()
    }
    assert writers == {"publish-pypi", "github-release"}
    assert jobs["publish-pypi"]["permissions"] == {
        "contents": "read",
        "actions": "read",
        "id-token": "write",
    }
    assert jobs["github-release"]["permissions"] == {
        "contents": "write",
        "actions": "read",
    }
    assert jobs["publish-pypi"]["environment"]["name"] == "pypi"
    for name in writers:
        for step in jobs[name]["steps"]:
            if "uses" in step:
                assert step["uses"].split("@")[0] in {
                    "actions/checkout",
                    "actions/setup-python",
                    "actions/download-artifact",
                    "pypa/gh-action-pypi-publish",
                }
            command = step.get("run", "")
            assert not re.search(
                r"\b(?:uv|pip|pip3)\s+(?:pip\s+)?(?:install|sync|run|build)\b", command
            )
            assert "scripts/release/install.py" not in command
            assert "package-check.sh" not in command
            assert "setup.py" not in command


def test_workflow_dependency_gates_and_exact_artifact_binding(
    workflow: dict[str, Any],
) -> None:
    jobs = workflow["jobs"]
    assert jobs["install-candidate"]["needs"] == "candidate"
    assert set(jobs["publish-pypi"]["needs"]) == {"candidate", "install-candidate"}
    assert set(jobs["install-pypi"]["needs"]) == {"candidate", "publish-pypi"}
    assert set(jobs["github-release"]["needs"]) == {
        "candidate",
        "publish-pypi",
        "install-pypi",
    }
    for name, job in jobs.items():
        if name == "candidate":
            continue
        assert (
            "if" not in job
        )  # Do not bypass dependency success with always()/cancelled().
        downloads = [
            step
            for step in job["steps"]
            if step.get("uses", "").startswith("actions/download-artifact@")
        ]
        assert len(downloads) == 1
        assert (
            downloads[0]["with"]["artifact-ids"]
            == "${{ needs.candidate.outputs.artifact }}"
        )
        assert "name" not in downloads[0]["with"]
        for step in job["steps"]:
            command = step.get("run", "")
            if "--dist" in command:
                assert '--commit "$GITHUB_SHA"' in command
                assert '--manifest-sha256 "$MANIFEST"' in command
                assert (
                    step["env"]["MANIFEST"] == "${{ needs.candidate.outputs.manifest }}"
                )
    for name in ("install-candidate", "install-pypi"):
        assert jobs[name]["strategy"]["matrix"]["python"] == ["3.13", "3.14"]
        command = "\n".join(step.get("run", "") for step in jobs[name]["steps"])
        assert ("--registry" in command) == (name == "install-pypi")


def test_workflow_core_verification_precedes_forge_publication(
    workflow: dict[str, Any],
) -> None:
    steps = workflow["jobs"]["publish-pypi"]["steps"]
    publishers = [
        (index, step)
        for index, step in enumerate(steps)
        if step.get("uses", "").startswith("pypa/gh-action-pypi-publish@")
    ]
    assert len(publishers) == 2
    (core_index, core), (forge_index, forge) = publishers
    assert core["if"] == "steps.core.outputs.needed == 'true'"
    assert forge["if"] == "steps.forge.outputs.needed == 'true'"
    assert core["with"] == {"packages-dir": "${{ runner.temp }}/core-upload/"}
    assert forge["with"] == {"packages-dir": "${{ runner.temp }}/forge-upload/"}
    verifications = [
        index
        for index, step in enumerate(steps)
        if "registry.py verify --package dspx-core" in step.get("run", "")
    ]
    assert len(verifications) == 1
    assert core_index < verifications[0] < forge_index


@pytest.mark.parametrize("job_name", ["publish-pypi", "github-release"])
@pytest.mark.parametrize("package", PACKAGES)
def test_workflow_registry_verification_pipelines_fail_closed(
    workflow: dict[str, Any],
    job_name: str,
    package: str,
) -> None:
    job = workflow["jobs"][job_name]
    verifications = [
        step
        for step in job["steps"]
        if f"registry.py verify --package {package}" in step.get("run", "")
    ]
    assert len(verifications) == 1
    step = verifications[0]
    command = step["run"]
    if "|" not in command:
        return
    shell = step.get(
        "shell",
        job.get("defaults", workflow.get("defaults", {})).get("run", {}).get("shell"),
    )
    # GitHub's implicit bash uses -e only; explicit `shell: bash` also enables pipefail.
    assert shell == "bash" or "set -euo pipefail" in command, step["name"]

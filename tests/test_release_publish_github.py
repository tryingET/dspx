"""Offline state-machine checks: every gh subprocess, API, and byte download is fake."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/release/github.py"
COMMIT = "a" * 40
OTHER = "b" * 40
VERSION = "0.2.1"
CORE = f"dspx-core-v{VERSION}"
FORGE = f"dspx-forge-v{VERSION}"
ROOT = "repos/tryingET/dspx"


@pytest.fixture
def candidate(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    rows = []
    for package in ("dspx-core", "dspx-forge"):
        for kind, suffix in (("wheel", "-py3-none-any.whl"), ("sdist", ".tar.gz")):
            name = f"{package.replace('-', '_')}-{VERSION}{suffix}"
            data = f"inert bytes: {name}".encode()
            (dist / name).write_bytes(data)
            rows.append(
                dict(
                    filename=name,
                    package=package,
                    version=VERSION,
                    kind=kind,
                    bytes=len(data),
                    sha256=hashlib.sha256(data).hexdigest(),
                )
            )
    manifest = dict(
        schema="dspx-package-release-v1",
        commit=COMMIT,
        ak_scope_evidence="AK-evidence:1",
        license_sha256="c" * 64,
        versions={p: VERSION for p in ("dspx-core", "dspx-forge")},
        files=rows,
    )
    (dist / "release-manifest.json").write_text(json.dumps(manifest))
    digest = hashlib.sha256((dist / "release-manifest.json").read_bytes()).hexdigest()
    artifacts = ModuleType("artifacts")
    artifacts.__dict__["load_and_verify"] = Mock(return_value=manifest)
    monkeypatch.setitem(sys.modules, "artifacts", artifacts)
    return SimpleNamespace(
        dist=dist, manifest=manifest, digest=digest, loader=artifacts.load_and_verify
    )


class GitHub:
    def __init__(self, candidate):
        self.candidate = candidate
        self.releases = []
        self.tags = {}
        self.annotations = {}
        self.bodies = {}
        self.calls = []
        self.writes = []
        self.downloads = []
        self.failure = None
        self.corrupt_after = None
        self.read_error = None
        self.config = {"full_name": "tryingET/dspx"}

    def seed(self, tag, draft=True, names=None):
        row = dict(
            id=len(self.releases) + 1,
            tag_name=tag,
            draft=draft,
            prerelease=False,
            target_commitish=COMMIT,
            assets=[],
        )
        self.releases.append(row)
        if not draft:
            self.tags[tag] = dict(type="commit", sha=COMMIT)
        if names is None:
            package = tag.rsplit("-v", 1)[0]
            names = [
                r["filename"]
                for r in self.candidate.manifest["files"]
                if r["package"] == package
            ] + ["release-manifest.json"]
        self.upload(row, names)
        return row

    def upload(self, row, names):
        for name in names:
            data = (self.candidate.dist / name).read_bytes()
            identity = max(self.bodies, default=0) + 1
            self.bodies[identity] = data
            row["assets"].append(
                dict(id=identity, name=name, size=len(data), state="uploaded")
            )

    def get(self, path):
        if self.read_error and self.read_error in path:
            return None, 1, b"gh: request denied (HTTP 403)"
        if path == ROOT:
            return self.config, 0, b""
        base, _, query = path.partition("?")
        if base == f"{ROOT}/releases":
            page = int(query.split("page=")[-1])
            return self.releases[(page - 1) * 100 : page * 100], 0, b""
        if base.startswith(f"{ROOT}/git/ref/tags/"):
            tag = base.rsplit("/", 1)[-1]
            if tag not in self.tags:
                return None, 1, b"gh: Not Found (HTTP 404)"
            return {"ref": f"refs/tags/{tag}", "object": self.tags[tag]}, 0, b""
        if base.startswith(f"{ROOT}/git/tags/"):
            sha = base.rsplit("/", 1)[-1]
            return {"sha": sha, "object": self.annotations[sha]}, 0, b""
        if base.endswith("/assets"):
            identity = int(base.split("/")[-2])
            row = next(r for r in self.releases if r["id"] == identity)
            page = int(query.split("page=")[-1])
            return row["assets"][(page - 1) * 100 : page * 100], 0, b""
        raise AssertionError(f"unexpected API {path}")

    def run(self, cmd, *, stderr, timeout, check, stdout):
        assert cmd[0] == "gh" and timeout == 300 and not check
        self.calls.append(cmd)
        if cmd[1] == "api":
            assert cmd[2:6] == ["--hostname", "github.com", "--method", "GET"]
            path = cmd[6]
            if "/releases/assets/" in path:
                assert cmd[7:] == ["-H", "Accept: application/octet-stream"]
                identity = int(path.rsplit("/", 1)[-1])
                stdout.write(self.bodies[identity])
                self.downloads.append(identity)
                return subprocess.CompletedProcess(cmd, 0, b"", b"")
            data, code, error = self.get(path)
            return subprocess.CompletedProcess(
                cmd, code, json.dumps(data).encode(), error
            )
        assert cmd[1] == "release" and cmd[-2:] == [
            "--repo",
            "github.com/tryingET/dspx",
        ]
        assert not any(x in cmd for x in ("--clobber", "--force", "delete"))
        action, tag = cmd[2:4]
        self.writes.append(cmd)
        failure = self.failure if self.failure and self.failure[0] == action else None
        if not failure or failure[1] != "before":
            if action == "create":
                assert "--draft" in cmd and "--latest=false" in cmd
                assert cmd[cmd.index("--target") + 1] == COMMIT
                assert cmd[cmd.index("--title") + 1] == tag
                names = [Path(p).name for p in cmd[4 : cmd.index("--draft")]]
                row = self.seed(tag, names=names)
            else:
                row = next(r for r in self.releases if r["tag_name"] == tag)
                assert row["draft"], "no mutation of published release"
                if action == "upload":
                    names = [Path(p).name for p in cmd[4:-2]]
                    assert not set(names) & {a["name"] for a in row["assets"]}
                    self.upload(row, names)
                else:
                    assert action == "edit" and "--draft=false" in cmd
                    assert {a["id"] for a in row["assets"]} <= set(self.downloads)
                    assert len(row["assets"]) == 3
                    row["draft"] = False
                    self.tags.setdefault(tag, dict(type="commit", sha=COMMIT))
            if self.corrupt_after:
                self.corrupt_after(action, row)
        if failure:
            if failure[2] == "timeout":
                raise subprocess.TimeoutExpired(cmd, timeout)
            return subprocess.CompletedProcess(cmd, 1, b"", b"lost write response")
        return subprocess.CompletedProcess(cmd, 0, b"ok", b"")


@pytest.fixture
def env(candidate, monkeypatch):
    spec = importlib.util.spec_from_file_location("release_github_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    github = GitHub(candidate)
    monkeypatch.setattr(module.subprocess, "run", github.run)
    return SimpleNamespace(module=module, gh=github, candidate=candidate)


def execute(env):
    c = env.candidate
    return env.module.main(
        ["--dist", str(c.dist), "--commit", COMMIT, "--manifest-sha256", c.digest]
    )


def test_absent_draft_first_exact_assets_and_latest(env, capsys):
    assert execute(env) == 0
    assert [c[2] for c in env.gh.writes] == ["create", "edit", "create", "edit"]
    assert "--latest=true" in env.gh.writes[1]
    assert "--latest=false" in env.gh.writes[3]
    for release in env.gh.releases:
        assert not release["draft"]
        assert len(release["assets"]) == 3
        assert env.gh.tags[release["tag_name"]]["sha"] == COMMIT
        for asset in release["assets"]:
            assert env.gh.downloads.count(asset["id"]) == 2
    output = capsys.readouterr().out
    assert '"release_immutability": "unknown"' in output
    assert output.count("verified_published") == 2
    env.candidate.loader.assert_called_once_with(
        env.candidate.dist, COMMIT, env.candidate.digest
    )


@pytest.mark.parametrize("draft", [True, False])
def test_existing_complete_release(env, capsys, draft):
    env.gh.seed(CORE, draft=draft)
    env.gh.seed(FORGE, draft=draft)
    assert execute(env) == 0
    assert [c[2] for c in env.gh.writes] == (["edit", "edit"] if draft else [])
    assert capsys.readouterr().out.count("verified_noop") == (0 if draft else 2)


@pytest.mark.parametrize("keep", [0, 1, 2])
def test_partial_exact_draft_uploads_only_missing(env, keep):
    row = env.gh.seed(CORE)
    row["assets"] = row["assets"][:keep]
    missing = {
        r["filename"]
        for r in env.candidate.manifest["files"]
        if r["package"] == "dspx-core"
    }
    missing.add("release-manifest.json")
    missing -= {a["name"] for a in row["assets"]}
    env.gh.seed(FORGE, draft=False)
    assert execute(env) == 0
    assert [c[2] for c in env.gh.writes] == ["upload", "edit"]
    assert {Path(p).name for p in env.gh.writes[0][4:-2]} == missing


@pytest.mark.parametrize("annotated", [False, True])
def test_existing_tag_is_dereferenced(env, annotated):
    env.gh.tags[CORE] = dict(
        type="tag" if annotated else "commit", sha=OTHER if annotated else COMMIT
    )
    env.gh.annotations[OTHER] = dict(type="commit", sha=COMMIT)
    assert execute(env) == 0


@pytest.mark.parametrize(
    "case",
    [
        "wrong_tag",
        "wrong_annotation",
        "cycle",
        "unknown_type",
        "wrong_target",
        "branch_target",
        "missing_target",
        "no_tag",
        "duplicate",
        "extra",
        "missing",
        "checksum",
        "size",
        "download_size",
        "incomplete",
        "duplicate_id",
        "prerelease",
        "duplicate_release",
        "unknown_draft",
    ],
)
def test_conflicts_block_before_any_write(env, capsys, case):
    # Forge conflict must be found before otherwise-absent Core can be created.
    row = env.gh.seed(FORGE, draft=case not in ("no_tag", "missing"))
    asset = row["assets"][0]
    if case == "wrong_tag":
        env.gh.tags[FORGE] = dict(type="commit", sha=OTHER)
    elif case in ("wrong_annotation", "cycle", "unknown_type"):
        env.gh.tags[FORGE] = dict(type="tag", sha=OTHER)
        env.gh.annotations[OTHER] = dict(
            type={"cycle": "tag", "unknown_type": "tree"}.get(case, "commit"), sha=OTHER
        )
    elif case in ("wrong_target", "branch_target", "missing_target"):
        row["target_commitish"] = {
            "wrong_target": OTHER,
            "branch_target": "main",
            "missing_target": None,
        }[case]
    elif case == "no_tag":
        env.gh.tags.clear()
    elif case in ("duplicate", "extra", "duplicate_id"):
        extra = copy.deepcopy(asset)
        if case == "extra":
            extra["name"] = "extra.txt"
        if case == "duplicate_id":
            row["assets"][1]["id"] = asset["id"]
        else:
            row["assets"].append(extra)
    elif case == "missing":
        row["assets"].pop()
    elif case == "checksum":
        env.gh.bodies[asset["id"]] = b"x" * asset["size"]
    elif case == "size":
        asset["size"] += 1
    elif case == "download_size":
        env.gh.bodies[asset["id"]] += b"x"
    elif case == "incomplete":
        asset["state"] = "starter"
    elif case == "prerelease":
        row["prerelease"] = True
    elif case == "duplicate_release":
        env.gh.releases.append(copy.deepcopy(row))
    else:
        row["draft"] = None
    assert execute(env) == 1
    assert not env.gh.writes
    assert "blocked_or_unverified" in capsys.readouterr().err


@pytest.mark.parametrize("action", ["create", "upload", "edit"])
@pytest.mark.parametrize("timing", ["before", "after"])
@pytest.mark.parametrize("failure", ["nonzero", "timeout"])
def test_failed_mutation_reconciles_once_never_retries(
    env, capsys, action, timing, failure
):
    if action != "create":
        row = env.gh.seed(CORE)
        if action == "upload":
            row["assets"].pop()
    env.gh.failure = (action, timing, failure)
    assert execute(env) == 1
    assert len(env.gh.writes) == 1
    index = env.gh.calls.index(env.gh.writes[0])
    reads = env.gh.calls[index + 1 :]
    assert sum(c[6] == f"{ROOT}/releases?per_page=100&page=1" for c in reads) == 1
    assert all(c[1] == "api" for c in reads)
    assert "effect_indeterminate" in capsys.readouterr().err


@pytest.mark.parametrize(
    "corruption", ["tag", "bytes", "identity", "missing", "still_draft"]
)
def test_success_response_needs_final_readback(env, capsys, corruption):
    def corrupt(action, row):
        if action != "edit":
            return
        if corruption == "tag":
            env.gh.tags[CORE]["sha"] = OTHER
        elif corruption == "bytes":
            asset = row["assets"][0]
            env.gh.bodies[asset["id"]] = b"x" * asset["size"]
        elif corruption == "identity":
            row["id"] += 100
        elif corruption == "missing":
            row["assets"].pop()
        else:
            row["draft"] = True

    env.gh.corrupt_after = corrupt
    assert execute(env) == 1
    assert [c[2] for c in env.gh.writes] == ["create", "edit"]
    assert "effect_indeterminate" in capsys.readouterr().err


@pytest.mark.parametrize(
    "value,expected",
    [(True, "enabled"), (False, "disabled"), (None, "unknown"), ("true", "unknown")],
)
def test_immutability_only_claims_observed_boolean(env, capsys, value, expected):
    env.gh.config["immutable_releases_enabled"] = value
    assert execute(env) == 0
    assert (
        json.loads(capsys.readouterr().out.splitlines()[0])["release_immutability"]
        == expected
    )


def test_unavailable_configuration_is_unknown(env, capsys):
    env.gh.read_error = ROOT
    assert (
        execute(env) == 1
    )  # Config unavailable is advisory; inventory unavailable blocks.
    assert '"release_immutability": "unknown"' in capsys.readouterr().out
    assert not env.gh.writes


def test_manifest_rejection_precedes_all_gh_calls(env):
    env.candidate.loader.side_effect = ValueError("manifest digest mismatch")
    assert execute(env) == 1
    assert not env.gh.calls


def test_real_sibling_validator_rejects_inert_archives_before_network(env, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "artifacts", SCRIPT.with_name("artifacts.py")
    )
    assert spec is not None and spec.loader is not None
    artifacts = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(artifacts)
    monkeypatch.setitem(sys.modules, "artifacts", artifacts)
    assert execute(env) == 1
    assert not env.gh.calls


def test_release_inventory_paginates_for_drafts(env):
    for i in range(100):
        env.gh.releases.append(dict(id=1000 + i, tag_name=f"irrelevant-{i}"))
    env.gh.seed(CORE)
    env.gh.seed(FORGE, draft=False)
    assert execute(env) == 0
    assert [c[2] for c in env.gh.writes] == ["edit"]
    assert any(
        "releases?per_page=100&page=2" in c[6] for c in env.gh.calls if c[1] == "api"
    )


@pytest.mark.parametrize("draft", [False, True])
@pytest.mark.parametrize("corruption", ["checksum", "extra", "duplicate"])
def test_exact_asset_validation_applies_to_published_and_draft(env, draft, corruption):
    row = env.gh.seed(CORE, draft=draft)
    asset = row["assets"][0]
    if corruption == "checksum":
        env.gh.bodies[asset["id"]] = b"x" * asset["size"]
    else:
        extra = copy.deepcopy(asset)
        if corruption == "extra":
            extra["name"] = "extra.txt"
        row["assets"].append(extra)
    assert execute(env) == 1
    assert not env.gh.writes


@pytest.mark.parametrize("action", ["create", "upload"])
def test_draft_readback_failure_never_publishes(env, action):
    if action == "upload":
        env.gh.seed(CORE)["assets"].pop()

    def corrupt(observed_action, row):
        if observed_action == action:
            row["target_commitish"] = None

    env.gh.corrupt_after = corrupt
    assert execute(env) == 1
    assert [c[2] for c in env.gh.writes] == [action]


def test_tag_api_denial_is_not_absence(env):
    env.gh.read_error = "/git/ref/tags/"
    assert execute(env) == 1
    assert not env.gh.writes


def test_partial_pair_reports_core_success_before_forge_failure(env, capsys):
    def corrupt(action, row):
        if action == "create" and row["tag_name"] == FORGE:
            row["target_commitish"] = OTHER

    env.gh.corrupt_after = corrupt
    assert execute(env) == 1
    output = capsys.readouterr()
    assert CORE in output.out and output.out.count("verified_published") == 1
    assert "effect_indeterminate" in output.err
    assert [c[2] for c in env.gh.writes] == ["create", "edit", "create"]


def test_unknown_release_inventory_blocks(env):
    env.gh.releases.append({"id": 99})
    assert execute(env) == 1
    assert not env.gh.writes


def test_unavailable_repository_config_does_not_claim_enabled(env, capsys, monkeypatch):
    original = env.gh.get

    def get(path):
        if path == ROOT:
            return None, 1, b"gh: Not Found (HTTP 404)"
        return original(path)

    monkeypatch.setattr(env.gh, "get", get)
    assert execute(env) == 0
    assert '"release_immutability": "unknown"' in capsys.readouterr().out

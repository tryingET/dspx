"""UNIT Docker/dispatch simulations; no Docker or native G execution."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ci"))
import verify_full_isolation as gate


def test_unit_closed_environment_has_no_ambient_provider_keys(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "unit-secret")
    monkeypatch.setenv("DSPX_POLICY_BYPASS", "1")
    env = gate.fixture_environment()
    assert "OPENAI_API_KEY" not in env and "DSPX_POLICY_BYPASS" not in env
    assert env["DSPX_PROVIDER"] == "stub"
    assert env["DSPX_ORACLE_EMBEDDING_BACKEND"] == "none"


def container(docker, cid, mounts):
    return {
        "Id": cid,
        "Image": docker.review["image"],
        "Config": {"Labels": {"dspx.verify-full": docker.label}, "User": "1000:1000"},
        "HostConfig": {
            "ReadonlyRootfs": True,
            "Privileged": False,
            "NetworkMode": "none",
            "Runtime": "runc",
            "CapAdd": [],
            "CapDrop": ["ALL"],
            "IpcMode": "private",
            "CgroupnsMode": "private",
            "SecurityOpt": ["no-new-privileges"],
        },
        "Mounts": [
            {"Type": "bind", "Source": str(a), "Destination": str(b), "RW": not ro}
            for a, b, ro in mounts
        ],
    }


@pytest.mark.parametrize(
    "mutation",
    [None, "network", "gpu", "caps", "root", "namespace", "mount", "identity"],
)
def test_unit_container_inspection_rejects_exposure(tmp_path, mutation):
    docker = gate.Docker(None, {"image": "sha256:" + "1" * 64}, tmp_path, tmp_path)
    mounts = [(tmp_path / "private", gate.R, False)]
    data = container(docker, "2" * 64, mounts)
    if mutation == "network":
        data["HostConfig"]["NetworkMode"] = "host"
    elif mutation == "gpu":
        data["HostConfig"]["DeviceRequests"] = ["gpu"]
    elif mutation == "caps":
        data["HostConfig"]["CapAdd"] = ["SYS_ADMIN"]
    elif mutation == "root":
        data["Config"]["User"] = "0"
    elif mutation == "namespace":
        data["HostConfig"]["PidMode"] = "host"
    elif mutation == "mount":
        data["Mounts"].append(
            {"Type": "bind", "Source": "/home", "Destination": "/home", "RW": True}
        )
    elif mutation == "identity":
        data["Image"] = "other"
    if mutation:
        with pytest.raises(ValueError):
            docker.check_container(data, "2" * 64, mounts)
    else:
        docker.check_container(data, "2" * 64, mounts)


def test_unit_exact_owned_cleanup_stop_wait_remove(tmp_path, monkeypatch):
    calls = []
    docker = gate.Docker(None, {"image": "unit"}, tmp_path, tmp_path)
    cid = "a" * 64
    docker.cids[cid] = "unit"
    docker.intents["unit"] = {
        "name": "unit",
        "attempt": "unit",
        "image": "unit",
        "label": docker.label,
        "command": ["unit"],
        "mounts": [],
    }
    docker.started.add("unit")
    running = True

    def command(label, args, **kwargs):
        nonlocal running
        calls.append(args)
        if args[0] == "inspect":
            return json.dumps(
                [
                    {
                        "Id": cid,
                        "Name": "/unit",
                        "Image": "unit",
                        "Mounts": [],
                        "Config": {
                            "Labels": {
                                "dspx.verify-full": docker.label,
                                "dspx.verify-full.attempt": "unit",
                            },
                            "Cmd": ["unit"],
                            "Entrypoint": ["/usr/bin/env"],
                        },
                        "State": {"Running": running},
                    }
                ]
            )
        if args[0] == "stop":
            running = False
        return "0"

    monkeypatch.setattr(docker, "command", command)
    docker.close()
    assert calls == [
        ["inspect", cid],
        ["stop", "--time=2", cid],
        ["inspect", cid],
        ["wait", cid],
        ["rm", cid],
    ]
    assert docker.settled and not docker.cids


def test_unit_cleanup_never_removes_unknown_identity(tmp_path, monkeypatch):
    docker = gate.Docker(None, {"image": "unit"}, tmp_path, tmp_path)
    docker.cids["a" * 64] = "unit"
    monkeypatch.setattr(
        docker, "command", lambda *a, **k: json.dumps([{"Id": "unrelated"}])
    )
    with pytest.raises(RuntimeError, match="unsettled"):
        docker.close()
    assert docker.cids


def test_unit_host_early_denial_creates_no_container(tmp_path, monkeypatch):
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    review = {"head": "unit", "source": {}, "closure": []}
    (prepared / "prepared.json").write_text(json.dumps({"review": gate.digest(review)}))
    monkeypatch.setattr(gate, "source_check", lambda *a, **k: None)
    monkeypatch.setattr(gate, "source_names", lambda *a: ["unit"])
    monkeypatch.setattr(gate, "index_check", lambda *a, **k: None)
    monkeypatch.setattr(gate, "source_index", lambda *a: {})

    def deny(*a):
        raise RuntimeError("host-denial")

    monkeypatch.setattr(gate, "canonical_claim", deny)
    monkeypatch.setattr(
        gate, "Docker", lambda *a: pytest.fail("container path reached")
    )
    with pytest.raises(RuntimeError, match="host-denial"):
        gate.execute(
            SimpleNamespace(run=None), review, prepared, tmp_path / "job", "unit", 5511
        )
    assert not (tmp_path / "job").exists()


@pytest.mark.parametrize(
    "case",
    [
        "pass",
        "hook-rewrite",
        "hook-new-link",
        "hook-delete-new-link",
        "hook-retarget-link",
        "native-failure",
        "container-failure",
        "membership-failure",
    ],
)
def test_unit_complete_dispatch_graph_and_failure_seal(tmp_path, monkeypatch, case):
    import threading

    prepared = tmp_path / "prepared"
    (prepared / "source").mkdir(parents=True)
    (prepared / "source/unit").write_text("immutable")
    review = {
        "head": "unit",
        "index": {},
        "source": {},
        "closure": [],
        "environment": {},
        "fixtures": {"AK5456_REVIEW_PROBES": None},
        "skips": {},
        "collection": {"nodes": ["unit"], "skips": {}},
    }
    (prepared / "prepared.json").write_text(json.dumps({"review": gate.digest(review)}))
    logs = tmp_path / "logs"
    logs.mkdir()
    events = []

    def run(label, *args, **kwargs):
        assert label == "source-names"
        return "unit\0"

    monkeypatch.setattr(gate, "source_check", lambda *a, **k: None)
    monkeypatch.setattr(gate, "source_names", lambda *a: ["unit"])
    monkeypatch.setattr(gate, "index_check", lambda *a, **k: None)
    monkeypatch.setattr(gate, "source_index", lambda *a: {})
    monkeypatch.setattr(
        gate, "canonical_claim", lambda *a: events.append("early-claim")
    )
    monkeypatch.setattr(
        gate, "host_scope", lambda *a: events.append("hostscope") or {"unit": True}
    )

    def native(*a):
        events.append("host-task5061")
        if case == "native-failure":
            raise RuntimeError("unit native denial")
        return {"unit": True}

    monkeypatch.setattr(gate, "native_task5061", native)

    class FakeDocker:
        def __init__(self, *a, **k):
            pass

        def preflight(self):
            events.append("preflight")

        def close(self):
            events.append("settled")

        def stage(self, name, argv, tree, state, **kwargs):
            events.append(name)
            assert argv[:4] == [gate.PYTHON, "-I", "-S", "-B"]
            if name == "hooks" and case == "hook-rewrite":
                (tree / "unit").write_text("changed")
            if name == "hooks" and case in {
                "hook-new-link",
                "hook-delete-new-link",
                "hook-retarget-link",
            }:
                link = tree / (
                    "unit" if case == "hook-delete-new-link" else "ignored-link"
                )
                if case == "hook-delete-new-link":
                    link.unlink()
                link.symlink_to("/fixture/missing-before")
                if case == "hook-retarget-link":
                    link.unlink()
                    link.symlink_to("/fixture/missing-after")
            if name == "replay" and case == "container-failure":
                raise RuntimeError("unit container failure")
            if name == "offline":
                assert argv[-4:] == ["-n", "16", "--dist", "load"]
                assert gate.OFFLINE in argv
            if name == "residual":
                assert gate.RESIDUAL in argv

    monkeypatch.setattr(gate, "Docker", FakeDocker)
    monkeypatch.setattr(gate, "merge_reports", lambda *a: {})

    def membership(*a):
        if case == "membership-failure":
            raise ValueError("unit missing nodes")
        return {"unit": True}

    monkeypatch.setattr(gate, "validate_membership", membership)
    processes = SimpleNamespace(
        run=run, logs=logs, groups={}, cancelled=threading.Event()
    )
    if case == "pass":
        result = gate.execute(
            processes, review, prepared, tmp_path / "job", "unit", 5511
        )
        assert result["status"] == "passed"
        assert set(result["stages"]) == set(gate.STAGES)
    else:
        with pytest.raises((RuntimeError, ValueError)):
            gate.execute(processes, review, prepared, tmp_path / "job", "unit", 5511)
        assert json.loads((logs / "receipt.json").read_text())["status"] == "incomplete"
    assert events[:6] == [
        "early-claim",
        "preflight",
        "workflow",
        "direction-static",
        "governance",
        "hostscope",
    ]
    if case.startswith("hook-"):
        assert "host-task5061" not in events and "replay" not in events
    if case == "native-failure":
        assert "replay" not in events
    if case == "container-failure":
        assert "residual" in events
    assert (prepared / "source/unit").read_text() == "immutable"


@pytest.mark.parametrize("deleted_kind", ["file", "link"])
@pytest.mark.parametrize("staged_deletion", [False, True])
def test_real_tiny_fixture_prepare_preserves_dirty_inventory_not_just_head(
    tmp_path, monkeypatch, staged_deletion, deleted_kind
):
    # A few bytes in synthetic Git/venv fixtures, NOT real closure provisioning.
    from verify_full_authority import Processes

    repo = tmp_path / "unit-repo"
    repo.mkdir()
    process = Processes(tmp_path / "logs")
    run = process.run
    run("init", ["/usr/bin/git", "init"], cwd=repo, env=gate.GIT_ENV)
    (repo / ".gitignore").write_text(".venv/\n")
    (repo / "uv.lock").write_text("package = []\n")
    (repo / "unit").write_text("committed")
    if deleted_kind == "link":
        (repo / "deleted").symlink_to("/fixture/unreviewed-head-link")
    else:
        (repo / "deleted").write_text("intentional deletion")
    run("add", ["/usr/bin/git", "add", "."], cwd=repo, env=gate.GIT_ENV)
    run(
        "commit",
        [
            "/usr/bin/git",
            "-c",
            "user.name=Unit",
            "-c",
            "user.email=unit@invalid",
            "-c",
            "core.hooksPath=/dev/null",
            "commit",
            "-m",
            "synthetic fixture",
        ],
        cwd=repo,
        env=gate.GIT_ENV,
    )
    (repo / "deleted").unlink()
    if staged_deletion:
        run(
            "stage-delete",
            ["/usr/bin/git", "add", "--update"],
            cwd=repo,
            env=gate.GIT_ENV,
        )
    (repo / "unit").write_text("reviewed dirty bytes")
    (repo / "new").write_text("reviewed untracked bytes")
    (repo / ".venv").mkdir()
    (repo / ".venv/tool").write_text("synthetic tool bytes; never executed")
    review = {
        "head": run(
            "head", ["/usr/bin/git", "rev-parse", "HEAD"], cwd=repo, env=gate.GIT_ENV
        ).strip(),
        "source": gate.source_inventory(repo, gate.source_names(run, repo)),
        "index": gate.source_index(repo),
        "closure": [
            {
                "source": str(repo / ".venv"),
                "target": str(repo / ".venv"),
                "role": "venv",
                "members": gate.inventory(repo / ".venv"),
            }
        ],
        "pth_imports": {},
    }
    original_check = gate.source_check
    monkeypatch.setattr(gate, "R", repo)
    monkeypatch.setattr(
        gate,
        "source_check",
        lambda run, review, root=None, **kw: original_check(
            run, review, root or repo, **kw
        ),
    )
    destination = tmp_path / "prepared"
    gate.prepare(run, review, destination)
    assert (destination / "source/unit").read_text() == "reviewed dirty bytes"
    assert (destination / "source/new").read_text() == "reviewed untracked bytes"
    assert (destination / "source/.git").is_dir()
    assert review["source"]["deleted"] == {"deleted": True}
    assert "deleted" in gate.source_names(run, destination / "source")
    assert not (destination / "source/deleted").exists()
    changed = review["source"] | {"deleted": {"sha256": "unreviewed resurrection"}}
    assert gate.digest(changed) != gate.digest(review["source"])
    assert (destination / "closure-0/tool").stat().st_ino != (
        repo / ".venv/tool"
    ).stat().st_ino
    (repo / "unit").write_text("unreviewed drift")
    with pytest.raises(ValueError, match="drift"):
        original_check(run, review, repo)


@pytest.mark.parametrize(
    "failure",
    [
        None,
        "create",
        "command-drift",
        "container-exit",
        "attach-cancel",
        "lost-response",
        "lost-ambiguous",
        "lost-race",
        "lost-protected",
        "lost-none",
        "lost-image",
    ],
)
@pytest.mark.parametrize("python_pair", [False, True])
def test_unit_real_docker_dispatch_methods_with_fake_command_results(
    tmp_path, monkeypatch, failure, python_pair
):
    cid = "c" * 64
    image = "sha256:" + "d" * 64
    docker = gate.Docker(
        None,
        {"image": image, "closure": []},
        tmp_path,
        tmp_path,
        environment=gate.fixture_environment(),
    )
    calls = []
    command = []
    source = tmp_path / "source"
    source.mkdir()
    (source / ".git").mkdir()
    state = tmp_path / "state"
    mounts = [
        (source, gate.R, False),
        (source / ".git", gate.R / ".git", True),
        (state, Path("/fixture"), False),
        (state / "prek", Path("/home/tryinget/.cache/prek"), False),
    ]
    if python_pair:
        from verify_full_closure import PYTHON_PHYSICAL, PYTHON_MINOR

        private = tmp_path / "closure-0"
        (private / "bin").mkdir(parents=True)
        (private / "bin/python3.13").write_bytes(b"UNIT ONLY")
        docker.review["closure"] = [
            {
                "source": str(private),
                "target": str(PYTHON_PHYSICAL),
                "role": "python",
                "aliases": [str(PYTHON_MINOR)],
                "members": gate.inventory(private),
            }
        ]
        mounts.extend([(private, PYTHON_PHYSICAL, True), (private, PYTHON_MINOR, True)])
    started = False
    daemon_created = False

    def fake(label, args, **kwargs):
        nonlocal command, started, daemon_created
        calls.append(args)
        if args[0] == "create":
            intent_records = (tmp_path / "unit.intent.jsonl").read_text().splitlines()
            assert json.loads(intent_records[0])["event"] == "intent"
            daemon_created = (
                True  # Simulated daemon effect BEFORE client loses response.
            )
            if failure is None or not failure.startswith("lost-"):
                Path(args[args.index("--cidfile") + 1]).write_text(cid)
            command = args[args.index(image) + 1 :]
            assert (
                "--pull=never" in args
                and "--network=none" in args
                and "--cap-drop=ALL" in args
            )
            if (
                failure == "create"
                or failure is not None
                and failure.startswith("lost-")
            ):
                raise RuntimeError("unit indeterminate create with known CID")
            return cid
        if args[0] == "ps":
            assert daemon_created
            assert f"name=^/{docker.intents['unit']['name']}$" in args
            assert (
                f"label=dspx.verify-full.attempt={docker.intents['unit']['attempt']}"
                in args
            )
            if failure == "lost-ambiguous":
                return cid + "\n" + "e" * 64 + "\n"
            return "" if failure == "lost-none" else cid + "\n"
        if args[0] == "inspect":
            data = container(docker, cid, mounts)
            intent = docker.intents["unit"]
            data["Name"] = "/" + intent["name"]
            data["Config"]["Labels"]["dspx.verify-full.attempt"] = intent["attempt"]
            data["Config"].update(
                {
                    "Entrypoint": ["/usr/bin/env"],
                    "Cmd": command if failure != "command-drift" else ["wrong"],
                }
            )
            data["HostConfig"].update(
                {"Memory": 12 * 1024**3, "NanoCpus": 16 * 10**9, "PidsLimit": 1024}
            )
            data["State"] = {
                "Running": False,
                "Status": "exited" if started else "created",
                "ExitCode": 7 if started and failure == "container-exit" else 0,
                "OOMKilled": False,
                "Error": "",
            }
            if failure == "lost-race":
                data["Name"] = "/renamed-by-another-actor"
            if failure == "lost-image":
                data["Image"] = "sha256:" + "e" * 64
            if failure == "lost-protected":
                data["State"].update({"Running": True, "Status": "running"})
            return json.dumps([data])
        if args[0] == "start":
            started = True
            if failure == "attach-cancel":
                raise RuntimeError("unit cancellation")
        return "0"

    monkeypatch.setattr(docker, "command", fake)
    if failure:
        with pytest.raises((RuntimeError, ValueError)):
            docker.stage("unit", ["unit-not-executed"], source, state)
        if failure in {
            "command-drift",
            "lost-ambiguous",
            "lost-race",
            "lost-protected",
            "lost-none",
            "lost-image",
        }:
            with pytest.raises(RuntimeError, match="unsettled"):
                docker.close()
            assert not any(call[0] == "rm" for call in calls)
            assert sum(call[0] == "create" for call in calls) == 1
            records = [
                json.loads(line)
                for line in (tmp_path / "unit.intent.jsonl").read_text().splitlines()
            ]
            assert records[-1]["event"] == "unsettled"
            assert any(row["event"] == "observed-candidates" for row in records)
            return
        docker.close()
    else:
        docker.stage("unit", ["unit-not-executed"], source, state)
    assert docker.settled and not docker.cids
    assert ["wait", cid] in calls and ["rm", cid] in calls
    assert not any("--force" in call or "prune" in call for call in calls)
    assert sum(call[0] == "create" for call in calls) == 1
    if failure in {"create", "command-drift", "lost-response"}:
        assert not started


@pytest.mark.parametrize("kind", ["current", "private"])
def test_real_local_git_execution_configuration_never_runs_on_host(tmp_path, kind):
    from verify_full_git import read_git, clone_source
    from verify_full_processes import Processes

    repo = tmp_path / kind
    repo.mkdir()
    runner = Processes(tmp_path / "logs")
    run = runner.run
    run("init", ["/usr/bin/git", "init"], cwd=repo, env=gate.GIT_ENV)
    (repo / "tracked.txt").write_text("before")
    (repo / "deleted.txt").write_text("delete me")
    (repo / ".gitignore").write_text("ignored.txt\ntracked.txt\n")
    run("add", ["/usr/bin/git", "add", "--force", "."], cwd=repo, env=gate.GIT_ENV)
    run(
        "commit",
        [
            "/usr/bin/git",
            "-c",
            "user.name=Unit",
            "-c",
            "user.email=unit@invalid",
            "commit",
            "-m",
            "fixture",
        ],
        cwd=repo,
        env=gate.GIT_ENV,
    )
    head = read_git(run, "head", ["rev-parse", "HEAD"], repo).strip()
    marker = tmp_path / "HOST-ESCAPE"
    evil = tmp_path / "evil.sh"
    evil.write_text(f"#!/bin/sh\necho escaped > {marker}\n")
    evil.chmod(0o755)
    included = tmp_path / "included.config"
    included.write_text(
        f'[core]\nfsmonitor = {evil}\n[filter "evil"]\nclean = {evil}\nsmudge = {evil}\nprocess = {evil}\nrequired = true\n[diff "evil"]\ncommand = {evil}\ntextconv = {evil}\n'
    )
    with (repo / ".git/config").open("a") as stream:
        stream.write(
            f"\n[core]\nfsmonitor = {evil}\nhooksPath = {tmp_path}\n[include]\npath = {included}\n"
        )
    (repo / ".git/info/exclude").write_text("info-ignored.txt\n")
    (repo / ".gitattributes").write_text("*.txt filter=evil diff=evil\n")
    (repo / "tracked.txt").write_text("dirty")
    (repo / "deleted.txt").unlink()
    (repo / "a space.txt").write_text("untracked")
    (repo / "ignored.txt").write_text("ignored")
    (repo / "info-ignored.txt").write_text("ignored")
    assert gate.source_names(run, repo) == [
        ".gitattributes",
        ".gitignore",
        "a space.txt",
        "deleted.txt",
        "tracked.txt",
    ]
    changed = read_git(run, "diff", ["diff", "--name-only", "HEAD"], repo)
    assert "tracked.txt" in changed and "deleted.txt" in changed
    clone = tmp_path / "clone"
    clone_source(run, repo, clone, head)
    assert {path.name for path in clone.iterdir()} == {".git"}
    with (clone / ".git/config").open("a") as stream:
        stream.write(f"\n[core]\nfsmonitor = {evil}\n")
    assert "tracked.txt" in read_git(
        run, "private-index", ["ls-files", "--stage"], clone
    )
    assert not marker.exists()
    assert not runner.groups


def test_real_host_scope_uses_config_free_git_reads(tmp_path, monkeypatch):
    import shutil
    import verify_full_authority as authority
    from verify_full_processes import Processes

    repo = tmp_path / "repo"
    repo.mkdir()
    processes = Processes(tmp_path / "logs")
    run = processes.run
    run("init", ["/usr/bin/git", "init"], cwd=repo, env=gate.GIT_ENV)
    (repo / "README").write_text("baseline")
    run("add", ["/usr/bin/git", "add", "."], cwd=repo, env=gate.GIT_ENV)
    run(
        "commit",
        [
            "/usr/bin/git",
            "-c",
            "user.name=Unit",
            "-c",
            "user.email=unit@invalid",
            "commit",
            "-m",
            "fixture",
        ],
        cwd=repo,
        env=gate.GIT_ENV,
    )
    target = repo / "packages/dspx-core/src/dspx/task_scope.py"
    target.parent.mkdir(parents=True)
    shutil.copy2(Path(__file__).resolve().parents[1] / target.relative_to(repo), target)
    manifest = repo / "governance/task-scopes/AK-266.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps({"task_id": 266, "description": "UNIT", "allowed_paths": ["**"]})
    )
    marker = tmp_path / "host-marker"
    helper = tmp_path / "fsmonitor"
    helper.write_text(f"#!/bin/sh\ntouch {marker}\n")
    helper.chmod(0o755)
    with (repo / ".git/config").open("a") as stream:
        stream.write(f"\n[core]\nfsmonitor = {helper}\n")
    monkeypatch.setattr(authority, "canonical_claim", lambda *args: 266)
    assert authority.host_scope(run, repo, "unit", 266)["task_id"] == 266
    assert not marker.exists()


def test_unit_closed_mount_roles_keep_logical_source_view(tmp_path):
    from verify_full_closure import validate_mount_targets

    repo = gate.R
    source, tools = tmp_path / "source", tmp_path / "tools"
    (source / "tests").mkdir(parents=True)
    (source / "tests/test_bound.py").write_text("reviewed source")
    tools.mkdir()
    (tools / "test_bound.py").write_text("replacement")
    for target, role in (
        (repo / "tests", "fixture"),
        (repo / "scripts", "tool"),
        (repo / ".git", "docs"),
        (repo, "venv"),
        (repo / "generated", "hooks"),
    ):
        with pytest.raises(ValueError, match="role cannot mount"):
            validate_mount_targets([{"target": str(target), "role": role}], repo)
    entries = [{"target": str(repo / ".venv"), "role": "venv"}]
    validate_mount_targets(entries, repo)
    mounts = [(source, repo), (tools, repo / ".venv")]
    requested = repo / "tests/test_bound.py"
    origin, destination = max(
        (pair for pair in mounts if requested.is_relative_to(pair[1])),
        key=lambda pair: len(pair[1].parts),
    )
    assert (
        origin / requested.relative_to(destination)
    ).read_text() == "reviewed source"
    with pytest.raises(ValueError, match="duplicate/nested"):
        validate_mount_targets(entries * 2, repo)


def test_real_gitlink_rejected_without_recursing_into_local_config(tmp_path):
    from verify_full_processes import Processes
    from verify_full_git import read_git

    repo = tmp_path / "repo"
    repo.mkdir()
    run = Processes(tmp_path / "logs").run
    run("init", ["/usr/bin/git", "init"], cwd=repo, env=gate.GIT_ENV)
    (repo / "file").write_text("content")
    run("add", ["/usr/bin/git", "add", "."], cwd=repo, env=gate.GIT_ENV)
    run(
        "commit",
        [
            "/usr/bin/git",
            "-c",
            "user.name=Unit",
            "-c",
            "user.email=unit@invalid",
            "commit",
            "-m",
            "fixture",
        ],
        cwd=repo,
        env=gate.GIT_ENV,
    )
    head = read_git(run, "head", ["rev-parse", "HEAD"], repo).strip()
    run(
        "gitlink",
        [
            "/usr/bin/git",
            "update-index",
            "--add",
            "--cacheinfo",
            f"160000,{head},nested",
        ],
        cwd=repo,
        env=gate.GIT_ENV,
    )
    with pytest.raises(ValueError, match="submodule Git metadata.*no silent omission"):
        gate.source_names(run, repo)


@pytest.fixture
def tiny_source(tmp_path):
    from verify_full_processes import Processes

    repo = tmp_path / "repo"
    repo.mkdir()
    runner = Processes(tmp_path / "logs")
    runner.run("init", ["/usr/bin/git", "init"], cwd=repo, env=gate.GIT_ENV)
    (repo / "file").write_text("original bytes")
    return repo, runner


def commit_tiny(repo, runner):
    runner.run("add", ["/usr/bin/git", "add", "."], cwd=repo, env=gate.GIT_ENV)
    runner.run(
        "commit",
        [
            "/usr/bin/git",
            "-c",
            "user.name=Unit",
            "-c",
            "user.email=unit@invalid",
            "-c",
            "core.hooksPath=/dev/null",
            "commit",
            "-m",
            "synthetic",
        ],
        cwd=repo,
        env=gate.GIT_ENV,
    )
    return gate.read_git(runner.run, "head", ["rev-parse", "HEAD"], repo).strip()


def test_real_committed_dangling_link_rejected_before_clone_and_after_retarget(
    tiny_source, tmp_path
):
    import os
    import shutil

    repo, runner = tiny_source
    link = repo / "link"
    link.symlink_to("/fixture/not-present-on-host.py")
    head = commit_tiny(repo, runner)
    marker = tmp_path / "outside-marker"
    evil = tmp_path / "fsmonitor"
    evil.write_text(f"#!/bin/sh\ntouch {marker}\n")
    evil.chmod(0o755)
    with (repo / ".git/config").open("a") as stream:
        stream.write(f"\n[core]\nfsmonitor = {evil}\n")
    # The previous exists()/is_file() inventories omitted this actually committed link.
    review = {"head": head, "source": gate.inventory(repo, ["file"])}
    assert "120000" in gate.read_git(runner.run, "index", ["ls-files", "--stage"], repo)
    assert "link" in gate.source_names(runner.run, repo)
    with pytest.raises(ValueError, match="source link"):
        gate.source_check(runner.run, review, repo)
    destination = tmp_path / "clone"
    with pytest.raises(ValueError, match="source link"):
        gate.clone_source(runner.run, repo, destination, head)
    assert not destination.exists()
    # Reproduce an old private checkout with the committed link still present.
    shutil.copytree(repo, destination, symlinks=True)
    legacy_before = gate.inventory(destination, ["file"])
    link_before = gate.inventory(destination, ["link"])
    copied = destination / "link"
    copied.unlink()
    copied.symlink_to("/fixture/changed-by-hook.py")
    assert gate.inventory(destination, ["file"]) == legacy_before
    assert gate.inventory(destination, ["link"]) != link_before
    for check in (
        lambda: gate.source_inventory(destination),
        lambda: gate.source_check(runner.run, review, destination),
    ):
        with pytest.raises(ValueError, match="source link"):
            check()
    assert os.readlink(link) == "/fixture/not-present-on-host.py"
    assert not marker.exists() and not runner.groups


@pytest.mark.parametrize("change", ["link", "dangling", "ancestor", "root", "fifo"])
def test_real_source_entry_and_ancestry_rejection(tmp_path, change):
    root = tmp_path / "source"
    (root / "dir").mkdir(parents=True)
    (root / "dir/file").write_text("bound")
    names = ["dir/file"]
    if change == "root":
        alias = tmp_path / "alias"
        alias.symlink_to(root, target_is_directory=True)
        root = alias
    elif change == "ancestor":
        (root / "dir/file").unlink()
        (root / "dir").rmdir()
        (root / "dir").symlink_to(tmp_path / "missing", target_is_directory=True)
    else:
        (root / "dir/file").unlink()
        if change == "fifo":
            import os

            os.mkfifo(root / "dir/file")
        else:
            (root / "dir/file").symlink_to(
                root if change == "link" else tmp_path / "missing"
            )
    with pytest.raises(ValueError, match="source|special file"):
        gate.source_inventory(root, names)


def test_real_hook_inventory_binds_empty_directory_and_deleted_entry(tmp_path):
    (tmp_path / "empty").mkdir()
    (tmp_path / "file").write_text("bound")
    before = gate.source_inventory(tmp_path)
    (tmp_path / "file").unlink()
    assert gate.source_inventory(tmp_path) != before
    assert gate.source_inventory(tmp_path, ["file"])["file"] == {"deleted": True}
    (tmp_path / "empty").rmdir()
    (tmp_path / "empty").symlink_to("missing", target_is_directory=True)
    with pytest.raises(ValueError, match="source link"):
        gate.source_inventory(tmp_path)


def test_real_parallel_git_view_cleanup_is_per_invocation(
    tiny_source, tmp_path, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor
    import time

    repo, runner = tiny_source
    head = commit_tiny(repo, runner)
    views = tmp_path / "views"
    views.mkdir()
    monkeypatch.setenv("TMPDIR", str(views))
    foreign = views / "dspx-git-view-foreign"
    foreign.mkdir()
    (foreign / "keep").write_text("foreign")
    ready, release = tmp_path / "ready", tmp_path / "release"
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            runner.run,
            "parallel",
            [
                sys.executable,
                "-I",
                "-S",
                "-B",
                "-c",
                f"from pathlib import Path; import time; Path({str(ready)!r}).touch()\nwhile not Path({str(release)!r}).exists(): time.sleep(.01)",
            ],
            cwd=repo,
            timeout=5,
        )
        try:
            deadline = time.monotonic() + 3
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert ready.exists() and runner.groups
            assert (
                gate.read_git(runner.run, "head", ["rev-parse", "HEAD"], repo).strip()
                == head
            )
            assert list(views.iterdir()) == [foreign] and runner.groups
        finally:
            release.touch()
            future.result(timeout=5)
    assert not runner.groups and (foreign / "keep").read_text() == "foreign"


@pytest.mark.parametrize(
    "failure", ["construction", "arguments", "clone", "unverified"]
)
def test_real_git_view_failure_cleanup_or_explicit_retention(
    tiny_source, tmp_path, monkeypatch, failure
):
    from verify_full_git import metadata_view

    repo, runner = tiny_source
    head = commit_tiny(repo, runner)
    views = tmp_path / "views"
    views.mkdir()
    monkeypatch.setenv("TMPDIR", str(views))
    foreign = tmp_path / "foreign"
    foreign.write_text("preserve")
    if failure == "construction":
        (repo / ".git/refs/heads/unsafe").symlink_to(foreign)
        with pytest.raises(ValueError, match="unsafe Git metadata"):
            metadata_view(repo)
    elif failure == "arguments":
        with pytest.raises(ValueError, match="unsupported host Git"):
            gate.read_git(runner.run, "bad", ["config", "--list"], repo)
    else:

        def run(label, argv, **kwargs):
            if failure == "unverified":
                kwargs.pop("settlement")  # Unknown adapter supplies no custody proof.
            if label == "private-clone":
                argv = [*argv, "--invalid-unit-argument"]
            return runner.run(label, argv, **kwargs)

        if failure == "clone":
            with pytest.raises(RuntimeError, match="private-clone"):
                gate.clone_source(run, repo, tmp_path / "destination", head)
        else:
            assert (
                gate.read_git(run, "head", ["rev-parse", "HEAD"], repo).strip() == head
            )
    retained = list(views.iterdir())
    if failure == "unverified":
        assert len(retained) == 1
        receipt = json.loads((retained[0] / "retained.json").read_text())
        assert receipt["status"] == "retained-unsettled-or-unverified"
        assert all(not row["settled"] for row in receipt["invocations"])
    else:
        assert retained == []
    assert foreign.read_text() == "preserve" and not runner.groups

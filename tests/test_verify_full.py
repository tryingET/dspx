"""Provider-free dispatch/process tests, not a full-gate or native proof."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ci"))
import verify_full_isolation as gate
from verify_full_authority import Processes

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("runtime_exit,tests_exit", [(0, 0), (7, 0), (0, 8), (7, 8)])
def test_unit_both_parallel_branches_are_waited(runtime_exit, tests_exit):
    observed = []

    def branch(name, code):
        time.sleep(0.01)
        observed.append(name)
        if code:
            raise RuntimeError(f"{name} exit={code}")

    if runtime_exit or tests_exit:
        with pytest.raises(RuntimeError, match="parallel branches failed"):
            gate.branches(
                lambda: branch("runtime", runtime_exit),
                lambda: branch("tests", tests_exit),
            )
    else:
        gate.branches(lambda: branch("runtime", 0), lambda: branch("tests", 0))
    assert sorted(observed) == ["runtime", "tests"]


def test_real_dispatch_plan_has_closed_startup_and_no_effect(tmp_path):
    marker = tmp_path / "startup-ran"
    (tmp_path / "sitecustomize.py").write_text(
        f"open({str(marker)!r}, 'w').write('bad')"
    )
    (tmp_path / ".env").write_text("DSPX_PROVIDER=live\n")
    env = {
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(tmp_path),
        "PYTHONSTARTUP": str(tmp_path / "sitecustomize.py"),
        "DSPX_PROVIDER": "live",
    }
    result = subprocess.run(
        ["/bin/sh", str(ROOT / "scripts/ci/verify-full.sh"), "--plan"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert '"status": "plan-only"' in result.stdout
    assert '"DSPX_PROVIDER": "stub"' in result.stdout
    assert not marker.exists()
    assert "set dotenv-load := false" in (ROOT / "Justfile").read_text()


def test_default_is_not_a_full_gate_success(tmp_path):
    result = subprocess.run(
        ["/bin/sh", str(ROOT / "scripts/ci/verify-full.sh")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "ok: verify-full" not in result.stdout


@pytest.mark.parametrize("mode", ["--execute", "--prepare"])
def test_execution_and_preparation_require_separate_admission(mode):
    with pytest.raises(SystemExit) as error:
        gate.main([mode])
    assert error.value.code == 2


def test_real_process_failure_retains_more_than_probe_cap(tmp_path):
    processes = Processes(tmp_path / "logs", limit=65536)
    with pytest.raises(RuntimeError, match="exit=7"):
        processes.run(
            "unit-failure",
            [sys.executable, "-I", "-S", "-c", "print('x'*20000); raise SystemExit(7)"],
            cwd=tmp_path,
        )
    assert not processes.groups
    assert next(processes.logs.glob("*.log")).stat().st_size > 8192


@pytest.mark.parametrize("kind", ["timeout", "overflow", "cancel"])
def test_real_process_bounds_and_reaping(tmp_path, kind):
    processes = Processes(tmp_path / "logs", limit=1024, grace=0.2)
    code = "import time; time.sleep(10)" if kind != "overflow" else "print('x'*8192)"
    timer = None
    if kind == "cancel":
        timer = threading.Timer(0.1, processes.cancel)
        timer.start()
    with pytest.raises(RuntimeError):
        processes.run(
            "unit-bounds",
            [sys.executable, "-I", "-S", "-c", code],
            cwd=tmp_path,
            timeout=0.3,
        )
    if timer:
        timer.join()
    assert not processes.groups
    assert next(processes.logs.glob("*.log")).stat().st_size <= 1024


def test_real_process_terminates_child_group(tmp_path):
    gate.enable_subreaper()
    pidfile = tmp_path / "child"
    code = f"import os,time; p=os.fork(); open({str(pidfile)!r},'w').write(str(p)) if p else time.sleep(10); time.sleep(10)"
    processes = Processes(tmp_path / "logs", grace=0.2)
    with pytest.raises(RuntimeError):
        processes.run(
            "unit-child",
            [sys.executable, "-I", "-S", "-c", code],
            cwd=tmp_path,
            timeout=0.4,
        )
    pid = int(pidfile.read_text())
    # Exact group children are dead AND reaped, not merely zombie/nonexecuting.
    proc = Path(f"/proc/{pid}/stat")
    assert not proc.exists()
    assert not processes.groups


@pytest.mark.workstation
def test_real_just_cleans_environment_before_recipe_shell_startup(tmp_path):
    import shutil

    (tmp_path / "scripts/ci").mkdir(parents=True)
    for name in (
        "verify-full.sh",
        "verify_full_authority.py",
        "verify_full_isolation.py",
        "verify_full_membership.py",
        "verify_full_processes.py",
        "verify_full_closure.py",
        "verify_full_git.py",
    ):
        shutil.copy2(ROOT / "scripts/ci" / name, tmp_path / "scripts/ci" / name)
    shutil.copy2(ROOT / "Justfile", tmp_path / "Justfile")
    marker = tmp_path / "shell-startup-ran"
    evil = tmp_path / "evil.sh"
    evil.write_text(f"echo bad > {marker}\n")
    (tmp_path / ".env").write_text(f"BASH_ENV={evil}\nDSPX_PROVIDER=live\n")
    result = subprocess.run(
        ["/usr/bin/just", "verify-full", "--plan"],
        cwd=tmp_path,
        env={
            "PATH": "/usr/bin:/bin",
            "TMPDIR": str(tmp_path),
            "BASH_ENV": str(evil),
            "ENV": str(evil),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"status": "plan-only"' in result.stdout
    assert not marker.exists()


def test_real_cancellation_after_eof_escalates_term_resistant_child(tmp_path):
    processes = Processes(tmp_path / "logs", grace=0.1)
    ready = tmp_path / "ready"
    code = (
        "import os,signal,time; from pathlib import Path; signal.signal(signal.SIGTERM, signal.SIG_IGN); os.close(1); os.close(2); Path("
        + repr(str(ready))
        + ").write_text('ready'); time.sleep(2)"
    )

    def cancel_when_ready():
        deadline = time.monotonic() + 2
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        processes.cancel()

    cancel = threading.Thread(target=cancel_when_ready)
    cancel.start()
    started = time.monotonic()
    with pytest.raises(RuntimeError, match="cancellation"):
        processes.run(
            "closed-pipes",
            [sys.executable, "-I", "-S", "-c", code],
            cwd=tmp_path,
            timeout=20,
        )
    cancel.join()
    assert time.monotonic() - started < 1.0
    assert not processes.groups
    import json

    receipt = json.loads(next(processes.logs.glob("*.json")).read_text())
    assert receipt["status"] != "exit=0"


@pytest.fixture
def index_fixture(tmp_path, monkeypatch):
    """Real tiny Git and inert tool bytes, no installed closure provisioning."""
    from test_verify_full_isolation import commit_tiny

    repo = tmp_path / "repo"
    repo.mkdir()
    runner = Processes(tmp_path / "logs")
    runner.run("init", ["/usr/bin/git", "init"], cwd=repo, env=gate.GIT_ENV)
    (repo / ".gitignore").write_text(".venv/\n")
    (repo / "uv.lock").write_text("package = []\n")
    (repo / "file").write_text("committed bytes")
    commit_tiny(repo, runner)
    (repo / ".venv").mkdir()
    (repo / ".venv/tool").write_text("INERT FIXTURE")
    original_check = gate.source_check
    monkeypatch.setattr(gate, "R", repo)
    monkeypatch.setattr(
        gate,
        "source_check",
        lambda run, review, root=None, **kw: original_check(
            run, review, root or repo, **kw
        ),
    )
    return repo, runner


def fixture_git(runner, repo, *args, input_bytes=None):
    return runner.run(
        "fixture-git",
        [
            "/usr/bin/git",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.hooksPath=/dev/null",
            *args,
        ],
        cwd=repo,
        env=gate.GIT_ENV,
        input_bytes=input_bytes,
    )


def index_review(repo, runner):
    return {
        "head": gate.read_git(runner.run, "head", ["rev-parse", "HEAD"], repo).strip(),
        "source": gate.source_inventory(repo, gate.source_names(runner.run, repo)),
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


def local_hook(repo, code, pattern):
    import json
    import shlex

    entry = "/usr/bin/python3 -I -S -c " + shlex.quote(
        "from pathlib import Path; assert {row.split(':')[0].strip() for row in Path('/proc/net/dev').read_text().splitlines()[2:]} <= {'lo'}; "
        + code
    )
    (repo / ".pre-commit-config.yaml").write_text(
        "repos:\n- repo: local\n  hooks:\n  - id: index-obligation\n"
        "    name: index-obligation\n    language: system\n"
        f"    entry: {json.dumps(entry)}\n    files: {json.dumps(pattern)}\n"
    )


def run_local_prek(repo, runner, home):
    status = []
    output = runner.run(
        "local-prek",
        [gate.PREK, "--log-file", str(home / "prek.log"), "run", "--all-files"],
        cwd=repo,
        env=gate.GIT_ENV | {"HOME": str(home), "PREK_HOME": str(home / "cache")},
        check=False,
        status=status,
    )
    return status[0], output


@pytest.mark.workstation
@pytest.mark.parametrize(
    "membership",
    ["addition", "deletion", "unstaged-deletion", "recreated-deletion", "untracked"],
)
def test_real_offline_prek_preserves_index_obligation(
    index_fixture, tmp_path, membership
):
    from test_verify_full_isolation import commit_tiny

    # This real hook fixture is never permitted outside a network namespace.
    assert {
        row.split(":")[0].strip()
        for row in Path("/proc/net/dev").read_text().splitlines()[2:]
    } <= {"lo"}
    repo, runner = index_fixture
    local_hook(repo, "raise SystemExit(7)", r"^stage_only\.py$")
    stage_only = repo / "stage_only.py"
    if "deletion" in membership:
        stage_only.write_text("committed then staged deletion")
    commit_tiny(repo, runner)
    if membership == "unstaged-deletion":
        stage_only.unlink()
    elif "deletion" in membership:
        fixture_git(runner, repo, "rm", "stage_only.py")
        if membership == "recreated-deletion":
            stage_only.write_text("untracked resurrection; not hook eligible")
    else:
        stage_only.write_text("staged bytes")
        if membership == "addition":
            fixture_git(runner, repo, "add", "stage_only.py")
            # Stage membership/OID must remain independent of these unstaged bytes.
            stage_only.write_text("unstaged bytes differ from staged blob")
            stage_only.chmod(0o755)
    (repo / "file").write_text("dirty tracked bytes")
    (repo / "untracked.py").write_text("not implicitly added")
    # NUL protocol must preserve valid spaces, tabs, newlines and option-looking paths.
    odd = "--odd \t\n.py"
    (repo / odd).write_bytes(b"\xff\0binary staged object")
    fixture_git(runner, repo, "add", "--", odd)
    review = index_review(repo, runner)
    original_code, original_output = run_local_prek(
        repo, runner, tmp_path / "original-home"
    )
    # Prek may refresh metadata; admission is intentionally taken after that run.
    review = index_review(repo, runner)
    before = gate.inventory(repo / ".git")
    prepared = tmp_path / "prepared"
    gate.prepare(runner.run, review, prepared)
    private = prepared / "source"
    assert gate.source_index(repo) == review["index"]
    assert gate.source_index(private)["entries"] == review["index"]["entries"]
    assert gate.inventory(repo / ".git") == before
    assert (private / "file").read_text() == "dirty tracked bytes"
    assert (private / odd).read_bytes() == (repo / odd).read_bytes()
    assert "untracked.py" not in fixture_git(runner, private, "ls-files", "-z").split(
        "\0"
    )
    if membership in {"deletion", "unstaged-deletion"}:
        assert not (private / "stage_only.py").exists()
    elif membership == "recreated-deletion":
        assert (private / "stage_only.py").read_bytes() == stage_only.read_bytes()
    elif membership == "addition":
        assert (private / "stage_only.py").read_bytes() == stage_only.read_bytes()
        assert fixture_git(runner, private, "show", ":stage_only.py") == "staged bytes"
        # Includes unreachable staged objects, copied privately rather than alternates.
        assert not (private / ".git/objects/info/alternates").exists()
    fixture_git(runner, private, "fsck", "--no-reflogs")
    code, output = run_local_prek(private, runner, tmp_path / "private-home")
    expected = 1 if membership == "addition" else 0
    assert original_code == code == expected, (original_output, output)
    for text in (original_output, output):
        assert ("exit code: 7" in text) == (membership == "addition")
        assert ("no files to check" in text) == (membership != "addition")
    gate.source_check(runner.run, review)
    gate.source_check(runner.run, review, private, private=True)
    assert gate.inventory(repo / ".git") == before
    assert not runner.groups


@pytest.mark.parametrize(
    "when",
    [
        "before",
        "copy",
        "stages",
        pytest.param("private-hook", marks=pytest.mark.workstation),
    ],
)
def test_real_index_only_drift_invalidates_custody(
    index_fixture, tmp_path, monkeypatch, when
):
    import json

    repo, runner = index_fixture
    local_hook(
        repo,
        "import subprocess; subprocess.run(['/usr/bin/git', 'update-index', '--force-remove', 'file'], check=True)",
        "^file$",
    )
    review = index_review(repo, runner)
    bytes_before = review["source"]
    if when == "before":
        fixture_git(runner, repo, "update-index", "--force-remove", "file")
        assert (
            gate.source_inventory(repo, gate.source_names(runner.run, repo))
            == bytes_before
        )
        with pytest.raises(ValueError, match="index drift"):
            gate.prepare(runner.run, review, tmp_path / "prepared")
        assert not (tmp_path / "prepared").exists()
        return
    if when == "copy":
        original_copy = gate.shutil.copy2

        def copy(*args, **kwargs):
            result = original_copy(*args, **kwargs)
            fixture_git(runner, repo, "update-index", "--force-remove", "file")
            return result

        monkeypatch.setattr(gate.shutil, "copy2", copy)
        with pytest.raises(ValueError, match="index drift"):
            gate.prepare(runner.run, review, tmp_path / "prepared")
        assert not (tmp_path / "prepared/prepared.json").exists()
        assert (
            gate.source_inventory(repo, gate.source_names(runner.run, repo))
            == bytes_before
        )
        return
    review.update(environment={}, fixtures={}, collection={}, skips={})
    prepared = tmp_path / "prepared"
    gate.prepare(runner.run, review, prepared)
    events = []
    original_index = gate.source_index(repo)
    monkeypatch.setattr(gate, "canonical_claim", lambda *a: None)
    monkeypatch.setattr(gate, "host_scope", lambda *a: {})
    monkeypatch.setattr(
        gate, "native_task5061", lambda *a: pytest.fail("native stage reached")
    )

    class LocalOnlyStage:
        # Simulation of stage placement; only the tiny local hook is a real process.
        def __init__(self, *a, **kw):
            pass

        def preflight(self):
            pass

        def close(self):
            pass

        def stage(self, name, argv, tree, state, **kw):
            events.append(name)
            if name == "hooks":
                if when == "stages":
                    fixture_git(runner, repo, "update-index", "--force-remove", "file")
                else:
                    code, output = run_local_prek(tree, runner, tmp_path / "hook-home")
                    assert code == 0, output

    monkeypatch.setattr(gate, "Docker", LocalOnlyStage)
    with pytest.raises(ValueError, match="index drift"):
        gate.execute(runner, review, prepared, tmp_path / "job", "unit", 5511)
    assert events[-1] == "hooks"
    assert (
        json.loads((runner.logs / "receipt.json").read_text())["status"] == "incomplete"
    )
    assert (
        gate.source_inventory(repo, gate.source_names(runner.run, repo)) == bytes_before
    )
    if when == "private-hook":
        assert gate.source_index(repo) == original_index


@pytest.mark.parametrize(
    "feature",
    [
        "assume-unchanged",
        "skip-worktree",
        "intent-to-add",
        "split",
        "v4",
        "unmerged",
        "nonblob",
        "missing-blob",
    ],
)
def test_real_unsupported_index_features_fail_closed(index_fixture, tmp_path, feature):
    repo, runner = index_fixture
    if feature in {"assume-unchanged", "skip-worktree"}:
        fixture_git(runner, repo, "update-index", "--" + feature, "file")
    elif feature == "intent-to-add":
        (repo / "new").write_text("not staged")
        fixture_git(runner, repo, "add", "--intent-to-add", "new")
    elif feature == "split":
        fixture_git(runner, repo, "update-index", "--split-index")
    elif feature == "v4":
        fixture_git(runner, repo, "update-index", "--index-version=4")
    else:
        oid = fixture_git(
            runner, repo, "rev-parse", "HEAD" if feature == "nonblob" else "HEAD:file"
        ).strip()
        if feature == "missing-blob":
            oid = "1" * 40
        stage = 1 if feature == "unmerged" else 0
        fixture_git(
            runner,
            repo,
            "update-index",
            "-z",
            "--index-info",
            input_bytes=f"100644 {oid} {stage}\tfile\0".encode(),
        )
    before = gate.inventory(repo / ".git")
    head = fixture_git(runner, repo, "rev-parse", "HEAD").strip()
    with pytest.raises((ValueError, RuntimeError), match="index|blob"):
        gate.clone_source(runner.run, repo, tmp_path / "private", head)
    assert gate.inventory(repo / ".git") == before
    assert not runner.groups


@pytest.mark.workstation
def test_real_bounded_stdin_is_exact_and_receipted(tmp_path):
    import hashlib
    import json

    runner = Processes(tmp_path / "logs")
    data = b"\0\xff\n" * 100000
    result = runner.run(
        "stdin",
        [
            sys.executable,
            "-I",
            "-S",
            "-c",
            "import sys,hashlib; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())",
        ],
        cwd=tmp_path,
        input_bytes=data,
    )
    assert result.strip() == hashlib.sha256(data).hexdigest()
    receipt = json.loads(next(runner.logs.glob("*.json")).read_text())
    assert receipt["stdin_sha256"] == result.strip()
    with pytest.raises(ValueError, match="stdin budget"):
        runner.run(
            "too-large",
            ["/usr/bin/false"],
            cwd=tmp_path,
            input_bytes=b"x" * (1024 * 1024 + 1),
        )
    assert len(list(runner.logs.glob("*.json"))) == 1


@pytest.mark.parametrize(
    "damage",
    [
        "checksum",
        "version",
        "mode",
        "zero-oid",
        "flags",
        "extension",
        "path",
        "padding",
    ],
)
def test_binary_index_admission_rejects_unsupported_metadata(index_fixture, damage):
    import hashlib
    import struct
    from verify_full_git import index_data

    repo, _ = index_fixture
    path = repo / ".git/index"
    data = bytearray(path.read_bytes()[:-20])
    if damage == "checksum":
        path.write_bytes(data + b"0" * 20)
    else:
        if damage == "version":
            data[4:8] = struct.pack("!I", 3)
        elif damage == "mode":
            data[36:40] = struct.pack("!I", 0o100600)
        elif damage == "zero-oid":
            data[52:72] = b"\0" * 20
        elif damage == "flags":
            data[72] |= 0x80
        elif damage == "extension":
            data.extend(b"XBAD" + struct.pack("!I", 0))
        elif damage == "path":
            data[74:78] = b"../x"
        else:
            end = data.index(0, 74)
            data[end + 1] = 1
        path.write_bytes(data + hashlib.sha1(data).digest())
    with pytest.raises(ValueError, match="index"):
        index_data(path)


def test_real_stat_only_index_drift_is_not_byte_or_membership_identity(index_fixture):
    import hashlib

    repo, runner = index_fixture
    review = index_review(repo, runner)
    path = repo / ".git/index"
    data = bytearray(path.read_bytes()[:-20])
    data[12] ^= 1  # ctime only: identical paths, stage OIDs, modes and source bytes.
    path.write_bytes(data + hashlib.sha1(data).digest())
    assert gate.source_index(repo)["entries"] == review["index"]["entries"]
    assert (
        gate.source_inventory(repo, gate.source_names(runner.run, repo))
        == review["source"]
    )
    with pytest.raises(ValueError, match="index drift"):
        gate.source_check(runner.run, review)


def test_review_requires_index_custody_and_refuses_old_unbound_schema(tmp_path):
    import json

    review = {
        "schema": "dspx-full-local-custody-v3",
        "head": "0" * 40,
        "source": {},
        "index": {"sha256": "0" * 64, "entries": ""},
        "closure": [],
        "pth_imports": {},
        "image": "sha256:" + "0" * 64,
        "skips": {},
        "fixtures": {"AK5456_REVIEW_PROBES": None, "host_interpreter": None},
        "environment": {},
        "collection": {"nodes": ["unit"], "skips": {}},
    }
    path = tmp_path / "review.json"

    def check():
        import hashlib

        path.write_text(json.dumps(review))
        return gate.read_review(path, hashlib.sha256(path.read_bytes()).hexdigest(), {})

    assert check()["index"] == review["index"]
    review["schema"] = "dspx-full-local-custody-v2"
    with pytest.raises(ValueError, match="schema"):
        check()
    review["schema"] = "dspx-full-local-custody-v3"
    review["index"]["sha256"] = "unbound"
    with pytest.raises(ValueError, match="index custody"):
        check()
    del review["index"]
    with pytest.raises(ValueError, match="schema"):
        check()


def test_real_empty_index_is_not_reset_to_head(index_fixture, tmp_path):
    repo, runner = index_fixture
    fixture_git(runner, repo, "read-tree", "--empty")
    review = index_review(repo, runner)
    assert review["index"]["entries"] == ""
    before = gate.inventory(repo / ".git")
    gate.prepare(runner.run, review, tmp_path / "prepared")
    private = tmp_path / "prepared/source"
    assert fixture_git(runner, private, "ls-files", "-z") == ""
    assert (private / "file").read_text() == "committed bytes"
    assert gate.inventory(repo / ".git") == before
    gate.source_check(runner.run, review, private, private=True)

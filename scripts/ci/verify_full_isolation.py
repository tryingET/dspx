"""Single fail-closed full-gate dispatcher; preparation is a separate heavy job.

Execution opt-in is NOT authority proof. See the manual owner applicability
boundary in docs/project/2026-09-07-evidence-integrity-design.md.
"""

from __future__ import annotations

import argparse
import ctypes
from concurrent.futures import ThreadPoolExecutor
import hmac
import json
from pathlib import Path
import shutil
import signal
import sys

# -I -S startup: add only these reviewed stdlib-only sibling modules, not site.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_full_authority import (
    Docker,
    Processes,
    canonical_claim,
    host_scope,
    native_task5061,
    strict_json,
)
from verify_full_membership import (
    OFFLINE,
    RESIDUAL,
    assert_inventory,
    digest,
    inventory as inventory,
    merge_reports,
    read_review,
    validate_closure,
    validate_membership,
)

from verify_full_git import (
    GIT_ENV as GIT_ENV,
    source_names as source_names,
    source_inventory as source_inventory,
    read_git,
    clone_source,
    source_index,
)

R = Path("/home/tryinget/ai-society/softwareco/owned/dspx")
H = Path("/home/tryinget")
PYTHON = str(R / ".venv/bin/python")
PREK = str(H / ".local/bin/prek")

DOCS = str(H / "ai-society/core/agent-scripts/scripts/docs-list.mjs")
STAGES = (
    "workflow",
    "direction-static",
    "governance",
    "hostscope",
    "hooks",
    "host-task5061",
    "replay",
    "monorepo",
    "module-corpus",
    "strict-docs",
    "package-ty",
    "test-ty",
    "offline",
    "residual",
    "membership",
)


# Executed with -I -S before any site/.pth hook or target command in every stage.
STARTUP = """import os, pathlib, sys
status = pathlib.Path('/proc/self/status').read_text()
assert os.getuid() == os.geteuid() == os.getgid() == 1000, 'native UID1000 required'
assert pathlib.Path('/').stat().st_uid == 0, 'root0 ancestors required'
fields = dict(line.split(':', 1) for line in status.splitlines() if ':' in line)
assert int(fields['CapEff'].strip(), 16) == 0, 'capabilities exposed'
assert fields['NoNewPrivs'].strip() == '1', 'no-new-privileges absent'
assert set(os.listdir('/sys/class/net')) <= {'lo'}, 'external network exposed'
assert not pathlib.Path('/var/run/docker.sock').exists(), 'host Docker socket exposed'
os.execvpe(sys.argv[1], sys.argv[1:], dict(os.environ))
"""


def fixture_environment():
    return {
        "PATH": f"{R}/.venv/bin:{H}/.local/bin:/usr/bin:/bin",
        "HOME": "/fixture/home",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TMPDIR": "/fixture/tmp",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "UV_OFFLINE": "1",
        "UV_NO_SYNC": "1",
        "UV_PYTHON_DOWNLOADS": "never",
        "UV_CACHE_DIR": "/fixture/uv",
        "PREK_HOME": str(H / ".cache/prek"),
        "XDG_CACHE_HOME": "/fixture/cache",
        "XDG_CONFIG_HOME": "/fixture/config",
        "XDG_DATA_HOME": "/fixture/data",
        "DSPX_PROVIDER": "stub",
        "MLFLOW_ENABLE": "0",
        "DSPX_ORACLE_EMBEDDING_BACKEND": "none",
        "DSPX_ORACLE_INDEX_PATH": "/fixture/oracle/index.db",
        "DSPX_CACHE_DIR": "/fixture/dspx-cache",
        "DSPX_MODULE_SYNTHESIS_EVIDENCE_ORACLE_INDEX_PATH": "/fixture/oracle/module.db",
        "DSPX_TEST_MODULE_SYNTHESIS_EVIDENCE_ROOT": "/fixture/evidence",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_HOME": "/fixture/hf",
        "DSPX_VERIFY_FULL_FIXTURE": "1",
        "PYTHONPATH": str(R / "scripts/ci"),
        # Thread pools follow the host core count, not --cpus, and threads count
        # against --pids-limit: 16 workers x 64 threads exhausted it at startup.
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
    }


def source_check(run, review, repo=R, *, private=False):
    head = read_git(run, "head", ["rev-parse", "HEAD"], repo).strip()
    if head != review["head"]:
        raise ValueError("HEAD differs from reviewed source")
    if source_inventory(repo, source_names(run, repo)) != review["source"]:
        raise ValueError("custody/source drift")
    index_check(review, repo, private=private)


def index_check(review, repo, *, private=False):
    observed = source_index(repo)
    expected = review["index"]
    if (
        observed["entries"] != expected["entries"]
        or not private
        and observed["sha256"] != expected["sha256"]
    ):
        raise ValueError("custody/index drift")


def prepare(run, review, target: Path):
    """Offline copy only. Caller separately admits heavy-job provisioning."""
    source_check(run, review)
    validate_closure(review, R)
    target.mkdir(mode=0o700, parents=False, exist_ok=False)
    source = target / "source"
    clone_source(run, R, source, review["head"])
    private_index = source_index(source)
    # No unchecked HEAD files are materialized. Deletions stay explicit in the receipt.
    for name, state in sorted(review["source"].items()):
        if state == {"deleted": True}:
            continue
        if source_inventory(R, [name])[name] != state:
            raise ValueError("source changed before copy")
        destination = source / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if state.get("directory") is True:
            destination.mkdir(exist_ok=True)
            shutil.copystat(R / name, destination)
        else:
            shutil.copy2(R / name, destination)
    for index, row in enumerate(review["closure"]):
        destination = target / f"closure-{index}"
        original = Path(row["source"])
        if original.is_dir() and not original.is_symlink():
            shutil.copytree(original, destination, symlinks=True)
        else:
            shutil.copy2(original, destination, follow_symlinks=False)
        assert_inventory(destination, row["members"])
    source_check(run, review)
    source_check(run, review, source, private=True)
    if source_index(source) != private_index:
        raise ValueError("private index drift during copy")
    (target / "prepared.json").write_text(
        json.dumps(
            {
                "review": digest(review),
                "custody": "local-copy-not-fresh-upstream-authentication",
            }
        )
        + "\n"
    )


def branches(runtime, tests):
    # Preserve normal semantics: one branch failure does not skip the other.
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(runtime), pool.submit(tests)]
        errors = []
        for future in futures:
            try:
                future.result()
            except Exception as exc:
                errors.append(str(exc))
    if errors:
        raise RuntimeError("parallel branches failed: " + "; ".join(errors))


def execute(processes, review, prepared: Path, job: Path, claimant: str, expected: int):
    run = processes.run
    source_check(run, review)
    prepared_review = strict_json((prepared / "prepared.json").read_text())["review"]
    if not hmac.compare_digest(str(prepared_review), digest(review)):
        raise ValueError("preparation/review mismatch")
    source_check(run, review, prepared / "source", private=True)
    for i, row in enumerate(review["closure"]):
        assert_inventory(prepared / f"closure-{i}", row["members"])
    # Early native admission denial => NO container creation. Not the ordered scope stage.
    canonical_claim(run, R, claimant, expected)
    job.mkdir(mode=0o700, exist_ok=False)
    docker = Docker(run, review, prepared, job, environment=fixture_environment())
    receipt: dict = {
        "review": digest(review),
        "collection_baseline": digest(review["collection"]),
        "head": review["head"],
        "source": digest({"bytes": review["source"], "index": review["index"]}),
        "tools": digest(review["closure"]),
        "environment": digest(
            {"base": review["environment"], "fixtures": review["fixtures"]}
        ),
        "stages": {},
        "status": "incomplete",
    }
    private_index = source_index(prepared / "source")
    source = job / "source"
    shutil.copytree(prepared / "source", source, symlinks=True)
    index_check(review, source, private=True)
    baseline = source_inventory(source, source_names(run, source))

    def private_unchanged(tree):
        index_check(review, tree, private=True)
        if source_index(tree) != private_index:
            raise ValueError("private index drift during stages")

    def unchanged():
        source_check(run, review)
        private_unchanged(source)
        if source_inventory(source, source_names(run, source)) != baseline:
            raise ValueError("custody/source drift")
        for i, row in enumerate(review["closure"]):
            assert_inventory(prepared / f"closure-{i}", row["members"])

    def stage(name, argv, *, tree=source, extra_env=None):
        unchanged()
        private_unchanged(tree)
        docker.stage(
            name,
            [PYTHON, "-I", "-S", "-B", "-c", STARTUP, *argv],
            tree,
            job / name,
            extra_env=extra_env,
        )
        unchanged()
        private_unchanged(tree)
        if source_inventory(tree, source_names(run, tree)) != baseline:
            raise ValueError("custody/source drift")
        receipt["stages"][name] = {
            "status": "passed",
            "identity": digest(
                {k: receipt[k] for k in ("head", "source", "tools", "environment")}
            ),
        }

    try:
        docker.preflight()
        stage("workflow", [PYTHON, "scripts/check_workflow_contracts.py"])
        stage("direction-static", [PYTHON, "scripts/check_direction_to_execution.py"])
        stage("governance", ["/usr/bin/just", "governance-check"])
        receipt["stages"]["hostscope"] = host_scope(run, R, claimant, expected)
        # Hooks may write only this disposable source, and any rewrite is fatal.
        hook_baseline = source_inventory(source)
        stage("hooks", [PREK, "--log-file", "/fixture/prek.log", "run", "--all-files"])
        hook_after = source_inventory(source)
        if hook_after != hook_baseline:
            raise ValueError("hook rewrote source bytes; no further stages")
        receipt["stages"]["host-task5061"] = native_task5061(run, R)
        test_source = job / "test-source"
        shutil.copytree(source, test_source, symlinks=True)

        def runtime():
            for name, argv in (
                ("replay", [PYTHON, "scripts/check_replay_provenance.py"]),
                ("monorepo", [PYTHON, "scripts/check_monorepo_boundaries.py"]),
                (
                    "module-corpus",
                    [PYTHON, "scripts/build_module_synthesis_quality_log.py"],
                ),
                ("strict-docs", ["/usr/bin/node", DOCS, "--docs", ".", "--strict"]),
            ):
                stage(name, argv)

        def tests():
            stage(
                "package-ty",
                [
                    str(R / ".venv/bin/ty"),
                    "check",
                    "packages/dspx-core/src",
                    "apps/forge/src",
                ],
                tree=test_source,
            )
            stage(
                "test-ty",
                [
                    str(R / ".venv/bin/ty"),
                    "check",
                    "tests",
                    "--extra-search-path",
                    "apps/forge/src",
                ],
                tree=test_source,
            )
            extra = {}
            if review["fixtures"]["AK5456_REVIEW_PROBES"] is not None:
                extra["AK5456_REVIEW_PROBES"] = review["fixtures"][
                    "AK5456_REVIEW_PROBES"
                ]
            for name, marker, workers in (
                ("offline", OFFLINE, ["-n", "16", "--dist", "load"]),
                ("residual", RESIDUAL, []),
            ):
                stage(
                    name,
                    [
                        PYTHON,
                        "-m",
                        "pytest",
                        "-p",
                        "verify_full_membership",
                        "-q",
                        "tests",
                        "-m",
                        marker,
                        *workers,
                    ],
                    tree=test_source,
                    extra_env=extra | {"DSPX_VERIFY_FULL_REPORTS": "/fixture/reports"},
                )

        branches(runtime, tests)
        receipt["stages"]["membership"] = validate_membership(
            merge_reports(job / "offline/reports"),
            merge_reports(job / "residual/reports"),
            review["skips"],
            review["collection"],
        )
        unchanged()
        private_unchanged(test_source)
        if source_inventory(test_source, source_names(run, test_source)) != baseline:
            raise ValueError("custody/source drift")
        if set(receipt["stages"]) != set(STAGES):
            raise RuntimeError("missing full-gate stage")
        docker.close()
        if processes.groups or processes.cancelled.is_set():
            raise RuntimeError("unsettled/cancelled host effects")
        binding = digest(
            {key: receipt[key] for key in ("head", "source", "tools", "environment")}
        )
        for record in receipt["stages"].values():
            record["identity"] = binding
        receipt["status"] = "passed"
    finally:
        try:
            docker.close()
        finally:
            (processes.logs / "receipt.json").write_text(
                json.dumps(receipt, indent=2) + "\n"
            )
    return receipt


def enable_subreaper():
    # Reap only adopted children in our exact owned process groups.
    if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) != 0:
        raise RuntimeError("Linux child-subreaper unavailable")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--review", type=Path)
    parser.add_argument("--review-sha256")
    parser.add_argument("--prepared", type=Path)
    parser.add_argument("--job", type=Path)
    parser.add_argument("--logs", type=Path)
    parser.add_argument("--expected-task", type=int)
    parser.add_argument("--claimant")
    parser.add_argument(
        "--owner-admitted",
        action="store_true",
        help="manual execution opt-in, NOT authority proof",
    )
    parser.add_argument("--heavy-job-admitted", action="store_true")
    args = parser.parse_args(argv)
    if not args.prepare and not args.execute:
        print(
            json.dumps(
                {
                    "status": "plan-only",
                    "stages": STAGES,
                    "environment": fixture_environment(),
                    "boundary": "LIVE blocked pending parent owner applicability determination + independent review; opt-in is not authority proof",
                },
                indent=2,
            )
        )
        return 0 if args.plan else 2
    if not args.owner_admitted or (args.prepare and not args.heavy_job_admitted):
        parser.error(
            "manual owner admission required; preparation also requires separately admitted heavy-job"
        )
    if not all((args.review, args.review_sha256, args.prepared, args.logs)) or (
        args.execute and not all((args.job, args.expected_task, args.claimant))
    ):
        parser.error(
            "exact review/hash/preparation/logs and execution claim/job required"
        )
    for path in (args.prepared, args.logs, args.job):
        if path is not None and (
            path.resolve() != path
            or not path.is_absolute()
            or path.is_relative_to(R)
            or path.is_relative_to(Path("/tmp"))
        ):
            parser.error(
                "private absolute TMPDIR-aware paths outside source and /tmp required"
            )
    roots = [p for p in (args.prepared, args.logs, args.job) if p is not None]
    if any(
        a != b and (a.is_relative_to(b) or b.is_relative_to(a))
        for a in roots
        for b in roots
    ) or len(set(roots)) != len(roots):
        parser.error("logs, prepared closure and disposable job must be disjoint")
    review = read_review(args.review, args.review_sha256, fixture_environment())
    enable_subreaper()
    processes = Processes(args.logs)
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: processes.cancel())
    try:
        if args.prepare:
            prepare(processes.run, review, args.prepared)
        else:
            execute(
                processes,
                review,
                args.prepared,
                args.job,
                args.claimant,
                args.expected_task,
            )
    except Exception as exc:
        print(
            f"verify-full FAIL/incomplete: {exc}; retained logs: {args.logs}",
            file=sys.stderr,
        )
        return 1
    print("prepared (not validation)" if args.prepare else "ok: verify-full")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

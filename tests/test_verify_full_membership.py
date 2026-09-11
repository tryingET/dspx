"""Synthetic inventory/pytest algorithm tests; no native authority/provider."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ci"))
import verify_full_membership as membership


BASELINE = {"nodes": ["a", "b"], "skips": {}}


def report(selected, *, skipped=False):
    return {
        "exit": 0,
        "errors": [],
        "collectors": [],
        "all": ["a", "b"],
        "selected": selected,
        "outcomes": {
            node: [
                {"when": "setup", "outcome": "passed", "reason": None},
                {
                    "when": "call",
                    "outcome": "skipped" if skipped else "passed",
                    "reason": "old skip" if skipped else None,
                },
                {"when": "teardown", "outcome": "passed", "reason": None},
            ]
            for node in selected
        },
    }


def test_unit_actual_partition_and_preserved_skip():
    assert membership.validate_membership(
        report(["a"]), report(["b"], skipped=True), {"b": "old skip"}, BASELINE
    ) == {"collected": 2, "offline": 1, "residual": 1, "skips": 1, "collector_skips": 0}


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate",
        "missing",
        "overlap",
        "collection-error",
        "collection-drift",
        "failed",
        "no-call",
        "duplicate-phase",
        "teardown",
        "new-skip",
        "changed-skip",
        "disappeared-skip",
    ],
)
def test_unit_membership_rejects_false_coverage(mutation):
    a, b, skips = report(["a"]), report(["b"]), {}
    if mutation == "duplicate":
        a["selected"] *= 2
    elif mutation == "missing":
        del a["outcomes"]["a"]
    elif mutation == "overlap":
        b = report(["a", "b"])
    elif mutation == "collection-error":
        a["errors"] = ["failure"]
    elif mutation == "collection-drift":
        b["all"] = ["b"]
    elif mutation == "failed":
        a["exit"] = 1
    elif mutation == "no-call":
        a["outcomes"]["a"].pop(1)
    elif mutation == "duplicate-phase":
        a["outcomes"]["a"].append(a["outcomes"]["a"][0])
    elif mutation == "teardown":
        a["outcomes"]["a"][-1]["outcome"] = "failed"
    elif mutation in {"new-skip", "changed-skip"}:
        a = report(["a"], skipped=True)
        skips = {} if mutation == "new-skip" else {"a": "different"}
    else:
        skips = {"a": "old skip"}
    with pytest.raises(ValueError):
        membership.validate_membership(a, b, skips, BASELINE)


def test_real_file_inventory_detects_bytes_mode_extra_and_symlinks(tmp_path):
    path = tmp_path / "member"
    path.write_text("bound")
    expected = membership.inventory(tmp_path)
    membership.assert_inventory(tmp_path, expected)
    path.chmod(0o700)
    with pytest.raises(ValueError):
        membership.assert_inventory(tmp_path, expected)
    path.chmod(expected["member"]["mode"])
    path.write_text("drift")
    with pytest.raises(ValueError):
        membership.assert_inventory(tmp_path, expected)
    path.write_text("bound")
    (tmp_path / "extra").symlink_to("member")
    with pytest.raises(ValueError):
        membership.assert_inventory(tmp_path, expected)
    assert membership.inventory(tmp_path)["extra"] == {"link": "member"}


@pytest.mark.parametrize(
    "event,args",
    [
        ("open", ("/some/society.v2.db",)),
        ("subprocess.Popen", ("ak", ["ak", "task"], None, {"PATH": "/bin"})),
        ("subprocess.Popen", ("/repo/ak.sh", ["/repo/ak.sh"], None, {})),
    ],
)
def test_unit_unexpected_authority_access_is_diagnostic(event, args):
    with pytest.raises(PermissionError, match="unexpected native authority"):
        membership.authority_audit(event, args)


def test_unit_empty_path_is_only_missing_executable_branch():
    membership.authority_audit(
        "subprocess.Popen", ("ak", ["ak", "task"], None, {"PATH": ""})
    )


@pytest.mark.parametrize(
    "workers", [[], ["-p", "xdist.plugin", "-n", "2", "--dist", "load"]]
)
def test_real_synthetic_pytest_collects_outcomes_before_marker_deselection(
    tmp_path, workers
):
    # Runs only this tiny generated, provider-free fixture file, never repo tests.
    test = tmp_path / "test_synthetic.py"
    test.write_text(
        "import pytest\ndef test_offline(): pass\n@pytest.mark.network\ndef test_residual(): pass\n"
    )
    results = []
    for lane, marker in (
        ("offline", membership.OFFLINE),
        ("residual", membership.RESIDUAL),
    ):
        output = tmp_path / lane
        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(tmp_path),
            "TMPDIR": str(tmp_path),
            "PYTHONPATH": str(Path(membership.__file__).parent),
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "DSPX_VERIFY_FULL_REPORTS": str(output),
            "DSPX_VERIFY_FULL_FIXTURE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-p",
                "verify_full_membership",
                "-q",
                str(test),
                "-m",
                marker,
                *workers,
            ],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        results.append(membership.merge_reports(output))
    assert (
        membership.validate_membership(
            results[0],
            results[1],
            {},
            {
                "nodes": [
                    "test_synthetic.py::test_offline",
                    "test_synthetic.py::test_residual",
                ],
                "skips": {},
            },
        )["collected"]
        == 2
    )


def test_unit_closure_rejects_unreviewed_pth_and_preserves_all_members(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "uv.lock").write_text("version = 1\npackage = []\n")
    venv = repo / ".venv"
    venv.mkdir()
    pth = venv / "unsafe.pth"
    pth.write_text("import unsafe\n")
    review = {
        "closure": [
            {
                "source": str(venv),
                "target": str(venv),
                "role": "venv",
                "members": membership.inventory(venv),
            }
        ],
        "pth_imports": {},
    }
    with pytest.raises(ValueError, match="unreviewed executable"):
        membership.validate_closure(review, repo)
    review["pth_imports"][str(pth)] = membership.file_hash(pth)
    membership.validate_closure(review, repo)
    (venv / "unused-package").write_text("must not be pruned")
    with pytest.raises(ValueError, match="drift"):
        membership.validate_closure(review, repo)
    assert (venv / "unused-package").exists()


@pytest.mark.parametrize(
    "case",
    [
        "valid",
        "record-drift",
        "unlocked",
        "private-key",
        "escaping-alias",
        "cycle",
        "fixture-unbound",
    ],
)
def test_unit_lock_record_alias_and_asset_boundaries(tmp_path, case):
    import base64

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "uv.lock").write_text(
        'version = 1\n[[package]]\nname = "unit"\nversion = "1.0"\n'
    )
    venv = repo / ".venv"
    site = venv / "lib/python3.13/site-packages"
    metadata = site / "unit-1.0.dist-info"
    metadata.mkdir(parents=True)
    (metadata / "METADATA").write_text("Name: unit\nVersion: 1.0\n")
    (site / "unit.py").write_text("VALUE = 1\n")
    rows = []
    for path in (metadata / "METADATA", site / "unit.py"):
        sha = (
            base64.urlsafe_b64encode(bytes.fromhex(membership.file_hash(path)))
            .decode()
            .rstrip("=")
        )
        rows.append(f"{path.relative_to(site)},sha256={sha},{path.stat().st_size}")
    (metadata / "RECORD").write_text(
        "\n".join([*rows, "unit-1.0.dist-info/RECORD,,"]) + "\n"
    )
    if case == "record-drift":
        (site / "unit.py").write_text("VALUE = 2\n")
    if case == "unlocked":
        (repo / "uv.lock").write_text("package = []\n")
    if case == "private-key":
        (venv / "credential.pem").write_text("-----BEGIN PRIVATE KEY-----")
    if case == "escaping-alias":
        (venv / "alias").symlink_to("/outside/binary")
    if case == "cycle":
        (venv / "alias-a").symlink_to("alias-b")
        (venv / "alias-b").symlink_to("alias-a")
    review = {
        "closure": [
            {
                "source": str(venv),
                "target": str(venv),
                "role": "venv",
                "members": membership.inventory(venv),
            }
        ],
        "pth_imports": {},
        "fixtures": {
            "host_interpreter": "/unbound" if case == "fixture-unbound" else None
        },
    }
    if case == "valid":
        membership.validate_closure(review, repo)
    else:
        with pytest.raises(ValueError):
            membership.validate_closure(review, repo)


@pytest.mark.parametrize(
    "workers", [[], ["-p", "xdist.plugin", "-n", "2", "--dist", "load"]]
)
def test_real_collection_skip_cannot_disappear_from_both_partitions(tmp_path, workers):
    tests = tmp_path / "test_present.py"
    tests.write_text(
        "import pytest\ndef test_a(): pass\n@pytest.mark.network\ndef test_b(): pass\n"
    )
    missing = tmp_path / "test_missing.py"
    missing.write_text(
        "import pytest\npytest.skip('optional fixture absent', allow_module_level=True)\ndef test_c(): pass\n"
    )
    results = []
    for lane, expression in (
        ("offline", membership.OFFLINE),
        ("residual", membership.RESIDUAL),
    ):
        directory = tmp_path / lane
        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(tmp_path),
            "TMPDIR": str(tmp_path),
            "PYTHONPATH": str(Path(membership.__file__).parent),
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "DSPX_VERIFY_FULL_FIXTURE": "1",
            "DSPX_VERIFY_FULL_REPORTS": str(directory),
        }
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-p",
                "verify_full_membership",
                "--rootdir",
                str(tmp_path),
                "-q",
                str(tests),
                str(missing),
                "-m",
                expression,
                *workers,
            ],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        report = membership.merge_reports(directory)
        assert any(
            row["outcome"] == "skipped" and "optional fixture absent" in row["reason"]
            for row in report["collectors"]
        )
        results.append(report)
    expected = [
        "test_present.py::test_a",
        "test_present.py::test_b",
        "test_missing.py::test_c",
    ]
    with pytest.raises(ValueError, match="collection skip"):
        membership.validate_membership(
            results[0], results[1], {}, {"nodes": expected, "skips": {}}
        )
    # Even deriving a matching but incomplete universe from those partitions fails.
    with pytest.raises(ValueError, match="collection skip"):
        membership.validate_membership(
            results[0], results[1], {}, {"nodes": expected[:2], "skips": {}}
        )
    # UNIT independently known source location/reason, not a hash copied from reports.
    reason = str((str(missing), 2, "Skipped: optional fixture absent"))
    baseline = {
        "nodes": expected[:2],
        "skips": {"test_missing.py": membership.digest(reason)},
    }
    assert (
        membership.validate_membership(results[0], results[1], {}, baseline)[
            "collector_skips"
        ]
        == 1
    )


def test_unit_independent_node_baseline_rejects_matching_incomplete_partitions():
    with pytest.raises(ValueError, match="complete disjoint union"):
        membership.validate_membership(
            report(["a"]),
            report(["b"]),
            {},
            {"nodes": ["a", "b", "missing"], "skips": {}},
        )


def test_real_venv_lib64_directory_alias_is_preserved_and_bound(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "uv.lock").write_text("package = []\n")
    venv = repo / ".venv"
    (venv / "lib/python3.13/site-packages").mkdir(parents=True)
    module = venv / "lib/python3.13/site-packages/unit.py"
    module.write_text("VALUE = 1\n")
    (venv / "lib64").symlink_to("lib", target_is_directory=True)
    members = membership.inventory(venv)
    assert members["lib"]["directory"] is True
    assert members["lib64"] == {"link": "lib"}
    review = {
        "closure": [
            {
                "source": str(venv),
                "target": str(venv),
                "role": "venv",
                "members": members,
            }
        ],
        "pth_imports": {},
    }
    membership.validate_closure(review, repo)
    assert (
        venv / "lib64/python3.13/site-packages/unit.py"
    ).read_bytes() == module.read_bytes()
    (venv / "lib").chmod(members["lib"]["mode"] ^ 0o040)
    with pytest.raises(ValueError, match="drift"):
        membership.assert_inventory(venv, members)


def test_unit_directory_alias_cannot_redirect_dependency_to_source(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "uv.lock").write_text("package = []\n")
    tests = repo / "tests"
    tests.mkdir()
    venv = repo / ".venv"
    venv.mkdir()
    (venv / "lib").symlink_to(tests, target_is_directory=True)
    review = {
        "source": {"tests": {"directory": True, "mode": 0o755}},
        "closure": [
            {
                "source": str(venv),
                "target": str(venv),
                "role": "venv",
                "members": membership.inventory(venv),
            }
        ],
        "pth_imports": {},
    }
    with pytest.raises(ValueError, match="cannot shadow source"):
        membership.validate_closure(review, repo)


def test_unit_review_requires_independent_collection_baseline_and_v2(tmp_path):
    import json

    review = {
        "schema": "dspx-full-local-custody-v3",
        "index": {"sha256": "0" * 64, "entries": ""},
        "head": "unit",
        "source": {},
        "closure": [],
        "pth_imports": {},
        "image": "sha256:" + "a" * 64,
        "skips": {},
        "fixtures": {"AK5456_REVIEW_PROBES": None, "host_interpreter": None},
        "environment": {},
        "collection": {"nodes": ["unit::test"], "skips": {}},
    }
    path = tmp_path / "review.json"

    def load():
        path.write_text(json.dumps(review))
        return membership.read_review(path, membership.file_hash(path), {})

    assert load()["collection"]["nodes"] == ["unit::test"]
    review["schema"] = "dspx-full-local-custody-v1"
    with pytest.raises(ValueError, match="schema"):
        load()
    review["schema"] = "dspx-full-local-custody-v3"
    del review["collection"]
    with pytest.raises(ValueError, match="schema"):
        load()


def test_unit_root_alias_cannot_make_docker_follow_live_host_source():
    from verify_full_closure import validate_mount_targets

    entries = [
        {
            "role": "fixture",
            "target": "/fixtures/alias",
            "members": {".": {"link": "/fixtures/binary"}},
        }
    ]
    with pytest.raises(ValueError, match="symlink mount root"):
        validate_mount_targets(entries, Path("/repo"))


@pytest.fixture
def paired_python(tmp_path) -> tuple[Path, dict]:
    """Observed UV metadata layout, synthetic bytes only; no host runtime reads."""
    import base64
    from verify_full_closure import PYTHON_MINOR, PYTHON_PHYSICAL

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "uv.lock").write_text(
        'version = 1\n[[package]]\nname = "alpha"\nversion = "1.0"\n[[package]]\nname = "beta"\nversion = "1.0"\n'
    )
    venv = repo / ".venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin/python").symlink_to(PYTHON_MINOR / "bin/python3.13")
    (venv / "bin/python3").symlink_to("python")
    (venv / "bin/python3.13").symlink_to("python")
    (venv / "pyvenv.cfg").write_text(
        f"home = {PYTHON_MINOR}/bin\nimplementation = CPython\nuv = 0.11.8\nversion_info = 3.13.12\ninclude-system-site-packages = false\nprompt = dspx\n"
    )
    site = venv / "lib/python3.13/site-packages"
    for package in ("alpha", "beta"):
        metadata = site / f"{package}-1.0.dist-info"
        metadata.mkdir(parents=True)
        (metadata / "METADATA").write_text(f"Name: {package}\nVersion: 1.0\n")
        (site / f"{package}.py").write_text("VALUE = 1\n")
        records = []
        for path in (metadata / "METADATA", site / f"{package}.py"):
            sha = (
                base64.urlsafe_b64encode(bytes.fromhex(membership.file_hash(path)))
                .decode()
                .rstrip("=")
            )
            records.append(
                f"{path.relative_to(site)},sha256={sha},{path.stat().st_size}"
            )
        (metadata / "RECORD").write_text(
            "\n".join([*records, f"{package}-1.0.dist-info/RECORD,,"]) + "\n"
        )
    (venv / "lib64").symlink_to("lib", target_is_directory=True)
    (site / "runtime.pth").write_text(str(PYTHON_MINOR / "lib/python3.13") + "\n")
    runtime = tmp_path / PYTHON_PHYSICAL.name
    (runtime / "bin").mkdir(parents=True)
    executable = runtime / "bin/python3.13"
    executable.write_bytes(b"SYNTHETIC INTERPRETER BYTES; NEVER EXECUTED")
    executable.chmod(0o755)
    (runtime / "lib/python3.13").mkdir(parents=True)
    (runtime / "lib/python3.13/unit.py").write_text("UNIT = True\n")
    return repo, {
        "schema": "dspx-full-local-custody-v3",
        "index": {"sha256": "0" * 64, "entries": ""},
        "head": "0" * 40,
        "source": membership.inventory(repo, ["uv.lock"]),
        "closure": [
            {
                "source": str(venv),
                "target": str(venv),
                "role": "venv",
                "members": membership.inventory(venv),
            },
            {
                "source": str(runtime),
                "target": str(PYTHON_PHYSICAL),
                "role": "python",
                "aliases": [str(PYTHON_MINOR)],
                "members": membership.inventory(runtime),
            },
        ],
        "pth_imports": {},
        "image": "sha256:" + "a" * 64,
        "skips": {},
        "fixtures": {"AK5456_REVIEW_PROBES": None, "host_interpreter": None},
        "environment": {},
        "collection": {"nodes": ["unit::test"], "skips": {}},
    }


def test_real_metadata_shape_validates_and_maps_both_aliases_to_same_private_bytes(
    paired_python, tmp_path
):
    import json
    import shutil
    from verify_full_closure import (
        PYTHON_MINOR,
        PYTHON_PHYSICAL,
        closure_mounts,
        bound_destination,
        target_paths,
    )

    repo, review = paired_python
    document = tmp_path / "review.json"
    document.write_text(json.dumps(review))
    checked = membership.read_review(document, membership.file_hash(document), {})
    membership.validate_closure(checked, repo)
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    for index, row in enumerate(checked["closure"]):
        shutil.copytree(row["source"], prepared / f"closure-{index}", symlinks=True)
        membership.assert_inventory(prepared / f"closure-{index}", row["members"])
    mounts = closure_mounts(prepared, checked["closure"], repo)
    assert mounts == [
        (prepared / "closure-0", repo / ".venv", True),
        (prepared / "closure-1", PYTHON_PHYSICAL, True),
        (prepared / "closure-1", PYTHON_MINOR, True),
    ]
    assert all(
        origin.resolve() == origin and not origin.is_symlink()
        for origin, _, _ in mounts
    )
    bound = {
        str(target / name): member
        for row in checked["closure"]
        for target in target_paths(row)
        for name, member in row["members"].items()
    }
    resolved = Path(bound_destination(bound, str(repo / ".venv/bin/python")))
    assert resolved == PYTHON_MINOR / "bin/python3.13"
    origin, target, _ = next(m for m in mounts if resolved.is_relative_to(m[1]))
    assert (
        origin / resolved.relative_to(target)
    ).read_bytes() == b"SYNTHETIC INTERPRETER BYTES; NEVER EXECUTED"
    # The unchanged home and .pth targets resolve to bound directories at both names.
    for logical in (
        PYTHON_MINOR / "bin",
        PYTHON_MINOR / "lib/python3.13",
        PYTHON_PHYSICAL / "bin",
    ):
        assert bound[bound_destination(bound, str(logical))]["directory"] is True
    for row in checked["closure"]:
        membership.assert_inventory(Path(row["source"]), row["members"])
    assert (
        len(
            list(
                (prepared / "closure-0/lib/python3.13/site-packages").glob(
                    "*.dist-info"
                )
            )
        )
        == 2
    )
    assert (prepared / "closure-0/pyvenv.cfg").read_bytes() == (
        repo / ".venv/pyvenv.cfg"
    ).read_bytes()


@pytest.mark.parametrize(
    "failure",
    [
        "wrong-alias",
        "missing-alias",
        "duplicate-alias",
        "new-mount",
        "nested-mount",
        "root-alias",
        "escape",
        "cycle",
        "runtime-drift",
        "venv-drift",
        "home",
        "version",
        "host-site",
        "venv-alias",
        "pth-escape",
        "alias-on-venv",
        "pth-deleted-source",
    ],
)
def test_real_python_pair_whole_validator_rejects_unbound_shapes(
    paired_python, tmp_path, failure
):
    from verify_full_closure import PYTHON_PHYSICAL, PYTHON_MINOR

    repo, review = paired_python
    venv, runtime = review["closure"]
    physical = Path(runtime["source"])
    if failure == "wrong-alias":
        runtime["aliases"] = [str(PYTHON_MINOR).replace("3.13-", "3.12-")]
    elif failure == "missing-alias":
        del runtime["aliases"]
    elif failure == "duplicate-alias":
        runtime["aliases"] *= 2
    elif failure in {"new-mount", "nested-mount"}:
        review["closure"].append(
            runtime
            | {
                "target": str(PYTHON_PHYSICAL).replace("3.13.12-", "3.13.13-")
                if failure == "new-mount"
                else str(PYTHON_MINOR / "bin")
            }
        )
    elif failure == "root-alias":
        alias = tmp_path / "host-root-alias"
        alias.symlink_to(physical, target_is_directory=True)
        runtime["source"] = str(alias)
    elif failure in {"escape", "cycle"}:
        executable = physical / "bin/python3.13"
        executable.unlink()
        executable.symlink_to(
            "/unbound/host-python" if failure == "escape" else "python3.13"
        )
        runtime["members"] = membership.inventory(physical)
    elif failure == "runtime-drift":
        (physical / "bin/python3.13").write_bytes(b"unreviewed")
    elif failure == "venv-drift":
        (repo / ".venv/extra-installed-dependency").write_text("must not prune")
    elif failure in {"home", "version", "host-site"}:
        cfg = repo / ".venv/pyvenv.cfg"
        before, after = {
            "home": (str(PYTHON_MINOR), "/unbound/python"),
            "version": ("3.13.12", "3.13.13"),
            "host-site": ("false", "true"),
        }[failure]
        cfg.write_text(cfg.read_text().replace(before, after))
        venv["members"] = membership.inventory(repo / ".venv")
    elif failure == "venv-alias":
        executable = repo / ".venv/bin/python"
        executable.unlink()
        executable.symlink_to(PYTHON_PHYSICAL / "bin/python3.13")
        venv["members"] = membership.inventory(repo / ".venv")
    elif failure in {"pth-escape", "pth-deleted-source"}:
        (repo / ".venv/lib/python3.13/site-packages/runtime.pth").write_text(
            "/unbound/python\n"
        )
        venv["members"] = membership.inventory(repo / ".venv")
    else:
        venv["aliases"] = [str(repo / "tests")]
    with pytest.raises(ValueError):
        membership.validate_closure(review, repo)
    # Rejection never edits/prunes either installed package.
    assert (repo / ".venv/lib/python3.13/site-packages/alpha.py").is_file()
    assert (repo / ".venv/lib/python3.13/site-packages/beta.py").is_file()

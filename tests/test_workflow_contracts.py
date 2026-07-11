# summary: "Tests repository workflow-contract alignment, stale guidance detection, standardized recipe bodies, and side-effect-free commands."
# read_when:
#   - "Changing workflow contract checks, Just recipes, engineering-lane policy, contributor guidance, or standardized command behavior."

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def _load_module():
    root = Path(__file__).resolve().parents[1]
    script_path = root / "scripts" / "check_workflow_contracts.py"
    spec = importlib.util.spec_from_file_location("workflow_contracts", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = _load_module()


def _write(root: Path, relpath: str, content: str) -> None:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_collect_issues_accepts_aligned_contract(tmp_path: Path) -> None:
    _write(tmp_path, ".gitignore", "__pycache__/\n*.py[cod]\n")
    _write(
        tmp_path,
        ".pre-commit-config.yaml",
        "repos:\n"
        "  - repo: https://github.com/astral-sh/ruff-pre-commit\n"
        "    rev: v0.15.4\n"
        "    hooks:\n"
        "      - id: ruff-format\n"
        "      - id: ruff\n"
        "  - repo: local\n"
        "    hooks:\n"
        "      - id: verify-pre-push\n"
        "        entry: just verify-pre-push\n"
        "        stages: [pre-push]\n",
    )
    _write(
        tmp_path,
        "docs/project/developer_workflow.md",
        "just help\n"
        "just check\n"
        "just ci\n"
        "just doctor\n"
        "just run\n"
        "just task-scope-check task_id=<AK-ID> mode=working-tree\n"
        "just verify-impact-plan\n"
        "just verify-impact\n"
        'just hooks-run files="path/one.py path/two.py"\n'
        "just verify-impact-receipt\n"
        "an active AK claim, or changed task-scope snapshot/legacy-scope-file paths\n"
        "brownfield legacy scope file\n"
        "AK task ready/list/show is the live execution source of truth\n"
        "uv run --no-sync\n",
    )
    _write(tmp_path, "scripts/ci/verify-full.sh", "#!/bin/sh\nexit 0\n")
    _write(
        tmp_path,
        "AGENTS.md",
        "See docs/project/developer_workflow.md and run just hooks-install.\n"
        "Canonical reads: docs/project/vision.md docs/project/product-posture.md; active direction uses AK direction runtime\n",
    )
    _write(
        tmp_path,
        "CONTRIBUTING.md",
        "docs/project/developer_workflow.md\n"
        "just install\n"
        "just hooks-install\n"
        "just help\n"
        "just doctor\n"
        "just run\n"
        "just task-scope-check task_id=<AK-ID> mode=working-tree\n"
        "just verify-pre-push\n"
        "just verify-full\n",
    )
    _write(
        tmp_path,
        "README.md",
        "docs/project/developer_workflow.md\n"
        "just help\n"
        "just check\n"
        "just ci\n"
        "just doctor\n"
        "just run\n"
        "just hooks-install\n"
        "just task-scope-check task_id=<AK-ID> mode=working-tree\n"
        "just verify-pre-push\n"
        "just verify-full\n"
        "uv run --no-sync\n",
    )
    _write(
        tmp_path,
        "docs/engineering.local.md",
        "docs/project/developer_workflow.md\n"
        "just hooks-install\n"
        "just task-scope-check task_id=<AK-ID> mode=working-tree\n"
        "just verify-pre-push\n"
        "just verify-full\n"
        "just help\n"
        "just check\n"
        "just ci\n"
        "just doctor\n"
        "just run ...\n"
        "No `just dev` target\n"
        "fails closed\n"
        "parallel\n",
    )
    _write(
        tmp_path,
        "Justfile",
        "# Contract: /home/tryinget/ai-society/softwareco/owned/docs/project/standardized-justfile-contract.md\n"
        "help:\n"
        "  just --list\n"
        "hooks-install:\n"
        "  uvx prek install --hook-type pre-commit --hook-type pre-push\n"
        'hooks-run files="":\n'
        "  uvx prek run --files $paths\n"
        "workflow-contract-check:\n"
        "  python3 scripts/check_workflow_contracts.py\n"
        "direction-contract-check:\n"
        "  python3 scripts/check_direction_to_execution.py\n"
        "governance-check:\n"
        '  @echo "ok: AK DB is canonical; work-items projection is compatibility-only"\n'
        "check:\n"
        "  just verify-fast\n"
        "fmt:\n"
        "  echo fmt\n"
        "lint:\n"
        "  echo lint\n"
        "test:\n"
        "  uv run --no-sync -m pytest -q tests\n"
        'test-parallel jobs="auto":\n'
        '  workers="{{jobs}}"; workers="${workers#jobs=}"; uv run --no-sync -m pytest -q tests -n "$workers" --dist loadfile -m "not slow and not live and not network and not model and not gpu and not postgres"\n'
        'test-slow-parallel jobs="auto":\n'
        '  workers="{{jobs}}"; workers="${workers#jobs=}"; uv run --no-sync -m pytest -q tests -n "$workers" --dist load -m "slow and not live and not network and not model and not gpu and not postgres"\n'
        "test-residual-serial:\n"
        '  uv run --no-sync -m pytest -q tests -m "live or network or model or gpu or postgres"\n'
        "build:\n"
        "  echo build\n"
        "# working tree when the repo is dirty\n"
        "# active AK claim or changed task-scope artifact paths\n"
        'task-scope-check task_id="" mode="auto" rev_range="auto":\n'
        '  if [ -n "{{task_id}}" ]; then uv run -q python scripts/check_task_scope.py --task-id {{task_id}} --mode {{mode}} --range {{rev_range}}; else uv run -q python scripts/check_task_scope.py --mode {{mode}} --range {{rev_range}}; fi\n'
        "verify-fast:\n"
        "  uvx prek run --all-files\n"
        "replay-provenance-check:\n"
        "  uv run --no-sync -q python scripts/check_replay_provenance.py\n"
        "module-synthesis-quality-check:\n"
        "  uv run --no-sync -q python scripts/build_module_synthesis_quality_log.py\n"
        "boundary-contract-check:\n"
        "  echo boundary\n"
        "verify-runtime-replay:\n"
        "  just replay-provenance-check\n"
        "verify-runtime-monorepo:\n"
        "  just monorepo-check\n"
        "verify-runtime-module-synthesis:\n"
        "  just module-synthesis-quality-check\n"
        "verify-runtime-boundary:\n"
        "  just boundary-contract-check\n"
        "verify-runtime:\n"
        "  just verify-runtime-replay\n"
        "  just verify-runtime-monorepo\n"
        "  just verify-runtime-module-synthesis\n"
        "  just verify-runtime-boundary\n"
        'verify-impact-plan base="auto":\n'
        "  uv run --no-sync python scripts/ci/verify_changed.py --base {{base}} --plan-only\n"
        'verify-impact base="auto":\n'
        "  uv run --no-sync python scripts/ci/verify_changed.py --base {{base}} --run\n"
        'verify-impact-receipt base="auto" out="generated/ci/verify-impact-result.json":\n'
        "  uv run --no-sync python scripts/ci/verify_changed.py --base {{base}} --run --result-out {{out}}\n"
        "loop-doctor:\n"
        "  just scope-doctor\n"
        "loop-verify-fast:\n"
        "  just verify-boundary-hardening\n"
        "loop-impact-plan:\n"
        "  just verify-impact-plan\n"
        "loop-impact-run:\n"
        "  just verify-impact\n"
        "loop-impact-wide:\n"
        "  just verify-impact-wide\n"
        "loop-landing-check:\n"
        "  just check\n"
        "typecheck-tests:\n"
        "  uvx ty check tests\n"
        "verify-tests:\n"
        "  just typecheck\n"
        "  just typecheck-tests\n"
        "  just test-parallel jobs=16\n"
        "  just test-slow-parallel jobs=16\n"
        "  just test-residual-serial\n"
        "verify-pre-push:\n"
        "  just verify-fast\n"
        "verify-full:\n"
        "  bash scripts/ci/verify-full.sh\n"
        "ci:\n"
        "  just verify-full\n"
        "doctor:\n"
        "  uv run --no-sync --package dspx-core -q python -m dspx.cli.dspx --help >/dev/null\n"
        "  uv run --no-sync --package dspx-forge -q python -m dspx_forge.cli --help >/dev/null\n"
        "monorepo-check:\n"
        "  uv run --no-sync -q python scripts/check_monorepo_boundaries.py\n"
        "run *args:\n"
        '  bash -lc \'if [ "$#" -eq 0 ]; then set -- --help; fi; uv run --no-sync --package dspx-core -q python -m dspx.cli.dspx "$@"\' -- {{args}}\n',
    )
    _write(
        tmp_path,
        "scripts/ci/smoke.sh",
        "need_cmd python3\nneed_cmd ak\npython3 scripts/check_workflow_contracts.py\npython3 scripts/check_direction_to_execution.py\n",
    )
    _write(
        tmp_path,
        "governance/README.md",
        "AK DB is canonical for live task/work-item truth.\n"
        "governance/work-items.json is a legacy compatibility projection and not a landing gate.\n",
    )
    _write(
        tmp_path,
        "policy/engineering-lane.json",
        '{"engineering_core":{"loop_validation":{"version":"repo-loop-validation-v1","contract_doc":"docs/engineering.local.md#repo-loop-validation","commands":{"loop-doctor":"just loop-doctor","loop-verify-fast":"just loop-verify-fast","loop-impact-plan":"just loop-impact-plan","loop-impact-run":"just loop-impact-run","loop-impact-wide":"just loop-impact-wide","loop-landing-check":"just loop-landing-check"}}}}\n',
    )

    issues = MODULE.collect_issues(tmp_path)
    assert issues == []


def test_collect_issues_flags_stale_contracts(tmp_path: Path) -> None:
    _write(tmp_path, ".gitignore", "")
    _write(tmp_path, "AGENTS.md", "Run ./scripts/install-hooks.sh after cloning.\n")
    _write(tmp_path, "CONTRIBUTING.md", "uv pip install -e .\n")
    _write(
        tmp_path,
        "docs/_core/README.md",
        'Invoke: "Read `~/steve/prompts/triggers/nexus.md`, apply to context"\n',
    )
    _write(
        tmp_path,
        "README.md",
        "changed manifest path, or next_session checkpoint\n",
    )
    _write(tmp_path, "docs/engineering.local.md", "")
    _write(tmp_path, "next_session_prompt.md", "Active/deferred work contract\n")
    _write(
        tmp_path,
        "Justfile",
        "pre-commit install --hook-type pre-commit --hook-type pre-push\n"
        "next_session_prompt checkpoint before failing closed\n",
    )
    _write(tmp_path, "scripts/ci/smoke.sh", "")
    _write(tmp_path, "governance/README.md", "")

    issues = MODULE.collect_issues(tmp_path)
    messages = {f"{issue.path}: {issue.message}" for issue in issues}

    assert ".pre-commit-config.yaml: missing required file" in messages
    assert "docs/project/developer_workflow.md: missing required file" in messages
    assert (
        "AGENTS.md: contains forbidden stale text: './scripts/install-hooks.sh'"
        in messages
    )
    assert (
        "CONTRIBUTING.md: contains forbidden stale text: 'uv pip install -e .'"
        in messages
    )
    assert (
        "docs/_core/README.md: contains forbidden stale text: '~/steve/prompts'"
        in messages
    )
    assert (
        "docs/_core/README.md: contains forbidden stale text: 'prompts/triggers'"
        in messages
    )
    assert (
        "README.md: contains forbidden stale text: 'changed manifest path, or next_session checkpoint'"
        in messages
    )
    assert (
        "next_session_prompt.md: retired AK-native workflow file still exists"
        in messages
    )
    assert (
        "Justfile: contains forbidden stale text: 'next_session_prompt checkpoint before failing closed'"
        in messages
    )


def test_collect_issues_rejects_loop_policy_commands_without_recipes(
    tmp_path: Path,
) -> None:
    _write(tmp_path, ".gitignore", "__pycache__/\n*.py[cod]\n")
    _write(tmp_path, "Justfile", "loop-doctor:\n  echo ok\n")
    _write(
        tmp_path,
        "policy/engineering-lane.json",
        '{"engineering_core":{"loop_validation":{"version":"repo-loop-validation-v1","contract_doc":"docs/engineering.local.md#repo-loop-validation","commands":{"loop-doctor":"just loop-doctor","loop-verify-fast":"just missing-loop","loop-impact-plan":"just loop-impact-plan","loop-impact-run":"just loop-impact-run","loop-impact-wide":"just loop-impact-wide","loop-landing-check":"just loop-landing-check"}}}}\n',
    )

    messages = {
        f"{issue.path}: {issue.message}" for issue in MODULE.collect_issues(tmp_path)
    }

    assert (
        "policy/engineering-lane.json: loop command 'loop-verify-fast' targets missing Just recipe: missing-loop"
        in messages
    )


def test_collect_issues_rejects_broken_standardized_recipe_bodies(
    tmp_path: Path,
) -> None:
    _write(tmp_path, ".gitignore", "__pycache__/\n*.py[cod]\n")
    _write(
        tmp_path,
        ".pre-commit-config.yaml",
        "repos:\n"
        "  - repo: local\n"
        "    hooks:\n"
        "      - id: verify-pre-push\n"
        "        entry: just verify-pre-push\n"
        "        stages: [pre-push]\n",
    )
    _write(
        tmp_path,
        "docs/project/developer_workflow.md",
        "just help\n"
        "just check\n"
        "just ci\n"
        "just doctor\n"
        "just run\n"
        "just task-scope-check task_id=<AK-ID> mode=working-tree\n"
        "just verify-impact-plan\n"
        "just verify-impact\n"
        'just hooks-run files="path/one.py path/two.py"\n'
        "just verify-impact-receipt\n"
        "an active AK claim, or changed task-scope snapshot/legacy-scope-file paths\n"
        "brownfield legacy scope file\n"
        "uv run --no-sync\n",
    )
    _write(tmp_path, "scripts/ci/verify-full.sh", "#!/bin/sh\nexit 0\n")
    _write(
        tmp_path,
        "AGENTS.md",
        "See docs/project/developer_workflow.md and run just hooks-install.\n"
        "Canonical reads: docs/project/vision.md docs/project/product-posture.md; active direction uses AK direction runtime\n",
    )
    _write(
        tmp_path,
        "CONTRIBUTING.md",
        "docs/project/developer_workflow.md\n"
        "just install\n"
        "just hooks-install\n"
        "just help\n"
        "just doctor\n"
        "just run\n"
        "just task-scope-check task_id=<AK-ID> mode=working-tree\n"
        "just verify-pre-push\n"
        "just verify-full\n",
    )
    _write(
        tmp_path,
        "README.md",
        "docs/project/developer_workflow.md\n"
        "just help\n"
        "just check\n"
        "just ci\n"
        "just doctor\n"
        "just run\n"
        "just hooks-install\n"
        "just task-scope-check task_id=<AK-ID> mode=working-tree\n"
        "just verify-pre-push\n"
        "just verify-full\n"
        "uv run --no-sync\n",
    )
    _write(
        tmp_path,
        "docs/engineering.local.md",
        "docs/project/developer_workflow.md\n"
        "just hooks-install\n"
        "just task-scope-check task_id=<AK-ID> mode=working-tree\n"
        "just verify-pre-push\n"
        "just verify-full\n"
        "just help\n"
        "just check\n"
        "just ci\n"
        "just doctor\n"
        "just run ...\n"
        "No `just dev` target\n"
        "fails closed\n"
        "parallel\n",
    )
    _write(
        tmp_path,
        "next_session_prompt.md",
        "Planned active/deferred work map\n"
        "Choose one highest-leverage actionable slice from `governance/work-items.json` unless operator direction overrides it.\n",
    )
    _write(
        tmp_path,
        "Justfile",
        "# Contract: /home/tryinget/ai-society/softwareco/owned/docs/project/standardized-justfile-contract.md\n"
        "help:\n"
        "  just --list\n"
        "hooks-install:\n"
        "  uvx prek install --hook-type pre-commit --hook-type pre-push\n"
        'hooks-run files="":\n'
        "  uvx prek run --files $paths\n"
        "workflow-contract-check:\n"
        "  python3 scripts/check_workflow_contracts.py\n"
        "direction-contract-check:\n"
        "  python3 scripts/check_direction_to_execution.py\n"
        "governance-check:\n"
        "  cue vet governance/work-items.json governance/work-items.cue\n"
        "check:\n"
        "  just verify-fast\n"
        "fmt:\n"
        "  echo fmt\n"
        "lint:\n"
        "  echo lint\n"
        "test:\n"
        "  echo broken test\n"
        "build:\n"
        "  echo build\n"
        "# working tree when the repo is dirty\n"
        "# active AK claim or changed task-scope artifact paths\n"
        'task-scope-check task_id="" mode="auto" rev_range="auto":\n'
        '  if [ -n "{{task_id}}" ]; then uv run -q python scripts/check_task_scope.py --task-id {{task_id}} --mode {{mode}} --range {{rev_range}}; else uv run -q python scripts/check_task_scope.py --mode {{mode}} --range {{rev_range}}; fi\n'
        "verify-fast:\n"
        "  uvx prek run --all-files\n"
        "replay-provenance-check:\n"
        "  echo bad replay\n"
        "module-synthesis-quality-check:\n"
        "  echo bad quality\n"
        "verify-runtime:\n"
        "  echo runtime\n"
        'verify-impact-plan base="auto":\n'
        "  uv run --no-sync python scripts/ci/verify_changed.py --base {{base}} --plan-only\n"
        'verify-impact base="auto":\n'
        "  uv run --no-sync python scripts/ci/verify_changed.py --base {{base}} --run\n"
        'verify-impact-receipt base="auto" out="generated/ci/verify-impact-result.json":\n'
        "  uv run --no-sync python scripts/ci/verify_changed.py --base {{base}} --run --result-out {{out}}\n"
        "verify-tests:\n"
        "  echo tests\n"
        "verify-pre-push:\n"
        "  just verify-fast\n"
        "verify-full:\n"
        "  bash scripts/ci/verify-full.sh\n"
        "ci:\n"
        "  just verify-full\n"
        "doctor:\n"
        "  echo fake doctor\n"
        "monorepo-check:\n"
        "  echo fake monorepo\n"
        "_helper:\n"
        "  uv run --no-sync --package dspx-core -q python -m dspx.cli.dspx --help >/dev/null\n"
        "  uv run --no-sync --package dspx-forge -q python -m dspx_forge.cli --help >/dev/null\n"
        "  uv run --no-sync -q python scripts/check_replay_provenance.py\n"
        "  uv run --no-sync -q python scripts/build_module_synthesis_quality_log.py\n"
        "  uv run --no-sync -q python scripts/check_monorepo_boundaries.py\n"
        '  bash -lc \'if [ "$#" -eq 0 ]; then set -- --help; fi; uv run --no-sync --package dspx-core -q python -m dspx.cli.dspx "$@"\' -- {{args}}\n'
        "run *args:\n"
        "  echo broken run\n",
    )
    _write(
        tmp_path,
        "scripts/ci/smoke.sh",
        "need_cmd cue\nneed_cmd python3\nneed_cmd ak\ncue vet governance/work-items.json governance/work-items.cue\npython3 scripts/check_workflow_contracts.py\npython3 scripts/check_direction_to_execution.py\n",
    )
    _write(
        tmp_path,
        "governance/README.md",
        "Use it to choose the next slice; do not treat it as a scheduler or live execution state.\n"
        "Refresh with ak work-items export and verify with ak work-items check.\n",
    )

    issues = MODULE.collect_issues(tmp_path)
    messages = {f"{issue.path}: {issue.message}" for issue in issues}

    assert (
        "Justfile: recipe 'doctor:' missing required text in body: 'uv run --no-sync --package dspx-core -q python -m dspx.cli.dspx --help >/dev/null'"
        in messages
    )
    assert (
        "Justfile: recipe 'run *args:' missing required text in body: 'if [ \"$#\" -eq 0 ]; then set -- --help; fi;'"
        in messages
    )
    assert (
        "Justfile: recipe 'test:' missing required text in body: 'uv run --no-sync -m pytest -q tests'"
        in messages
    )
    assert (
        "Justfile: recipe 'replay-provenance-check:' missing required text in body: 'uv run --no-sync -q python scripts/check_replay_provenance.py'"
        in messages
    )
    assert (
        "Justfile: recipe 'monorepo-check:' missing required text in body: 'uv run --no-sync -q python scripts/check_monorepo_boundaries.py'"
        in messages
    )


def test_current_repo_standardized_targets_are_side_effect_free() -> None:
    if shutil.which("just") is None:
        pytest.skip("just is not installed")

    repo_root = Path(__file__).resolve().parents[1]
    uv_lock = repo_root / "uv.lock"
    before = uv_lock.read_bytes()

    try:
        for command in (
            ["just", "doctor"],
            ["just", "run"],
            ["just", "replay-provenance-check"],
            ["just", "monorepo-check"],
        ):
            result = subprocess.run(
                command,
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            assert result.returncode == 0, result.stderr
            assert uv_lock.read_bytes() == before

        run = subprocess.run(
            ["just", "run"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        assert run.returncode == 0, run.stderr
        assert "Usage: python -m dspx.cli.dspx" in run.stdout
        assert uv_lock.read_bytes() == before
    finally:
        if uv_lock.read_bytes() != before:
            uv_lock.write_bytes(before)


def test_collect_issues_passes_for_current_repo() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    assert MODULE.collect_issues(repo_root) == []

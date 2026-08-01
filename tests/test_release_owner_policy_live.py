# ---
# summary: "Tests immutable live owner-policy selection and anti-rollback."
# ---

from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/ci/core_release_owner_policy_live.py"
SELECTOR = ROOT / "governance/release-signing/release-owner-policy-selector-v002.json"
NOW = datetime(2026, 8, 1, 6, tzinfo=timezone.utc)


def _load() -> ModuleType:
    sys.path.insert(0, str(SCRIPT.parent))
    try:
        spec = importlib.util.spec_from_file_location(
            "core_release_owner_policy_live", SCRIPT
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPT.parent))


@pytest.fixture
def module() -> ModuleType:
    return _load()


def test_selector_binds_exact_immutable_owner_policy(module: ModuleType) -> None:
    selector = json.loads(SELECTOR.read_text(encoding="utf-8"))
    assert module.validate_selector(selector, repo_root=ROOT, now=NOW) == selector
    drifted = json.loads(json.dumps(selector))
    drifted["policy"]["file_sha256"] = "0" * 64
    with pytest.raises(module.CoreReleaseEvidenceError, match="digest drift"):
        module.validate_selector(drifted, repo_root=ROOT, now=NOW)


def test_selector_chain_requires_contiguous_supersession(module: ModuleType) -> None:
    first = json.loads(SELECTOR.read_text(encoding="utf-8"))
    second = json.loads(json.dumps(first))
    second["policy"]["version"] = 3
    second["supersession"] = {
        "supersedes_decision_id": 96,
        "supersedes_owner_policy_version": 2,
    }
    selected = module.resolve_selector_chain(
        [(96, first, "selector-v2"), (97, second, "selector-v3")]
    )
    assert selected[0] == 97
    second["supersession"]["supersedes_decision_id"] = 999
    with pytest.raises(module.CoreReleaseEvidenceError, match="inconsistent"):
        module.resolve_selector_chain(
            [(96, first, "selector-v2"), (97, second, "selector-v3")]
        )


def test_checkpoint_rejects_rollback_and_fork(
    module: ModuleType, tmp_path: Path
) -> None:
    checkpoint = tmp_path / "owner" / "checkpoint.json"
    module.advance_checkpoint(checkpoint, version=2, reference="owner-selector-v2")
    with pytest.raises(module.CoreReleaseEvidenceError, match="below highest"):
        module.advance_checkpoint(checkpoint, version=1, reference="owner-selector-v1")
    with pytest.raises(module.CoreReleaseEvidenceError, match="selector fork"):
        module.advance_checkpoint(checkpoint, version=2, reference="other-v2")


def test_live_resolution_rejects_review_pending_decision(
    module: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        module,
        "_run_machine",
        lambda _command, _surface: {
            "count": 1,
            "decisions": [
                {
                    "id": 96,
                    "scope": "repo",
                    "repo_scope": module.REPO_SCOPE,
                    "state": "review_pending",
                    "outcome": None,
                    "evidence_ref": "dspx-core-owner-policy-selector-v1:git:"
                    + "1" * 40,
                }
            ],
        },
    )
    with pytest.raises(module.CoreReleaseEvidenceError, match="state drift"):
        module.resolve_live_current_owner_policy(
            repo_root=ROOT, checkpoint_path=tmp_path / "checkpoint.json", now=NOW
        )

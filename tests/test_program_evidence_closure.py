from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from dspx.services.program_evidence_closure import (
    collect_candidate_artifact_declarations,
    validate_candidate_artifact_closure,
)
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_service import materialize_program_from_intent
from dspx.services.run_replay_service import check_run_receipt


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest(root: Path, surfaces: list[dict[str, object]]) -> tuple[dict, Path]:
    payload = {
        "schema_version": "program-candidate-assembly-v1",
        "candidate_assembly": {"surfaces": surfaces},
    }
    path = root / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload, path


def test_candidate_artifact_closure_validates_unknown_local_surface(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "future-evidence.json"
    artifact.write_text('{"status":"local"}\n', encoding="utf-8")
    manifest, manifest_path = _manifest(
        tmp_path,
        [
            {
                "kind": "future_local_evidence",
                "path": artifact.name,
                "content_hash": _sha256(artifact),
            }
        ],
    )

    declarations = collect_candidate_artifact_declarations(manifest)
    validated = validate_candidate_artifact_closure(
        manifest, manifest_path=manifest_path
    )

    assert declarations[0].kind == "future_local_evidence"
    assert validated[0].path == artifact


@pytest.mark.parametrize("mutation", ["change", "delete"])
def test_candidate_artifact_closure_rejects_stale_or_missing_surface(
    tmp_path: Path, mutation: str
) -> None:
    artifact = tmp_path / "behavior_episode.json"
    artifact.write_text('{"status":"passed"}\n', encoding="utf-8")
    manifest, manifest_path = _manifest(
        tmp_path,
        [
            {
                "kind": "behavior_episode",
                "path": artifact.name,
                "content_hash": _sha256(artifact),
            }
        ],
    )
    if mutation == "change":
        artifact.write_text('{"status":"failed"}\n', encoding="utf-8")
    else:
        artifact.unlink()

    with pytest.raises(ValueError, match="hash does not match|artifact is missing"):
        validate_candidate_artifact_closure(manifest, manifest_path=manifest_path)


def test_program_receipt_fails_after_behavior_episode_mutation_or_deletion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_STUB_RESPONSE_JSON", json.dumps({"answer": "safe"}))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "0")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    root = tmp_path / "candidate"
    materialize_program_from_intent(
        ProgramIntent(
            name="ReceiptClosureProgram",
            objective="Prove current behavior evidence.",
            inputs=["question"],
            outputs=["answer"],
            examples=[
                {
                    "inputs": {"question": "status?"},
                    "outputs": {"answer": "safe"},
                }
            ],
        ),
        outdir=root,
    )
    receipt = root / "manifest.json.meta.json"
    episode = root / "behavior_episode.json"
    assert check_run_receipt(receipt)["status"] == "ok"

    original = episode.read_text(encoding="utf-8")
    episode.write_text(original + " ", encoding="utf-8")
    changed = check_run_receipt(receipt)
    assert changed["status"] != "ok"
    assert changed["checks"]["program_candidate_artifact_closure_valid"] is False

    episode.unlink()
    missing = check_run_receipt(receipt)
    assert missing["status"] != "ok"
    assert missing["checks"]["program_candidate_artifact_closure_valid"] is False


def test_candidate_artifact_closure_rejects_duplicates_escape_and_symlink(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "evidence.json"
    artifact.write_text("{}\n", encoding="utf-8")
    digest = _sha256(artifact)
    duplicate, _ = _manifest(
        tmp_path,
        [
            {"kind": "one", "path": artifact.name, "content_hash": digest},
            {"kind": "two", "path": artifact.name, "content_hash": digest},
        ],
    )
    with pytest.raises(ValueError, match="path is duplicated"):
        collect_candidate_artifact_declarations(duplicate)

    second = tmp_path / "second.json"
    second.write_text("{}\n", encoding="utf-8")
    duplicate_kind, _ = _manifest(
        tmp_path,
        [
            {"kind": "same", "path": artifact.name, "content_hash": digest},
            {"kind": "same", "path": second.name, "content_hash": _sha256(second)},
        ],
    )
    with pytest.raises(ValueError, match="kind is duplicated"):
        collect_candidate_artifact_declarations(duplicate_kind)

    outside = tmp_path.parent / "outside-evidence.json"
    outside.write_text("{}\n", encoding="utf-8")
    escaped, manifest_path = _manifest(
        tmp_path,
        [
            {
                "kind": "escaped",
                "path": str(outside),
                "content_hash": _sha256(outside),
            }
        ],
    )
    with pytest.raises(ValueError, match="escapes candidate root"):
        validate_candidate_artifact_closure(escaped, manifest_path=manifest_path)

    link = tmp_path / "linked.json"
    link.symlink_to(artifact.name)
    symlinked, manifest_path = _manifest(
        tmp_path,
        [{"kind": "linked", "path": link.name, "content_hash": digest}],
    )
    with pytest.raises(ValueError, match="symlink component"):
        validate_candidate_artifact_closure(symlinked, manifest_path=manifest_path)

    real_root = tmp_path / "real-root"
    real_root.mkdir()
    real_artifact = real_root / "evidence.json"
    real_artifact.write_text("{}\n", encoding="utf-8")
    linked_root = tmp_path / "linked-root"
    linked_root.symlink_to(real_root, target_is_directory=True)
    linked_manifest, _ = _manifest(
        real_root,
        [
            {
                "kind": "root_link",
                "path": real_artifact.name,
                "content_hash": _sha256(real_artifact),
            }
        ],
    )
    with pytest.raises(ValueError, match="root contains a symlink component"):
        validate_candidate_artifact_closure(
            linked_manifest, manifest_path=linked_root / "manifest.json"
        )

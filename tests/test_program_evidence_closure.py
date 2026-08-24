# summary: "Tests candidate artifact closure snapshots, declaration completeness, and tamper-resistant receipt checks."
# read_when:
#   - "Changing candidate evidence closure, artifact declarations, path confinement, or behavior-episode replay validation."

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from dspx.services import program_evidence_closure as closure_service
from dspx.services.program_evidence_closure import (
    snapshot_candidate_artifact_closure,
    collect_candidate_artifact_declarations,
    validate_candidate_artifact_closure,
)
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_service import materialize_program_from_intent
from dspx.services.run_replay_service import (
    _missing_behavior_episode_declarations,
    check_run_receipt,
)


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


def test_candidate_snapshot_keeps_opened_ancestor_when_path_is_swapped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate_root = tmp_path / "candidate"
    nested = candidate_root / "nested"
    nested.mkdir(parents=True)
    artifact = nested / "evidence.json"
    artifact.write_text('{"source":"candidate"}\n', encoding="utf-8")
    manifest, manifest_path = _manifest(
        candidate_root,
        [
            {
                "kind": "future_local_evidence",
                "path": "nested/evidence.json",
                "content_hash": _sha256(artifact),
            }
        ],
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "evidence.json").write_text('{"source":"outside"}\n', encoding="utf-8")
    displaced = candidate_root / "nested-original"
    real_open = closure_service.os.open
    swapped = False

    def swapping_open(
        path: Any,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        if path == "evidence.json" and not swapped:
            swapped = True
            nested.rename(displaced)
            nested.symlink_to(outside, target_is_directory=True)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(closure_service.os, "open", swapping_open)

    snapshot = snapshot_candidate_artifact_closure(manifest_path)

    assert snapshot.manifest == manifest
    assert snapshot.artifacts[0].sha256 == _sha256(displaced / "evidence.json")
    assert snapshot.artifacts[0].sha256 != _sha256(outside / "evidence.json")


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


def test_behavior_episode_declaration_completeness_covers_every_source() -> None:
    manifest = {
        "behavior_episode_artifact": {
            "path": "behavior_episode.json",
            "content_hash": "a" * 64,
        },
        "candidate_assembly": {
            "surfaces": [
                {
                    "kind": "behavior_episode",
                    "path": "behavior_episode.json",
                    "content_hash": "a" * 64,
                }
            ]
        },
        "receipt_bundle": {
            "evidence": {
                "behavior_episode_path": "behavior_episode.json",
                "behavior_episode_hash": "a" * 64,
                "surface_hashes": {"behavior_episode.json": "a" * 64},
            }
        },
    }
    receipt = {
        "run_summary": {
            "behavior_episode_path": "behavior_episode.json",
            "behavior_episode_hash": "a" * 64,
        },
        "program_behavior_episode_artifact": {
            "path": "behavior_episode.json",
            "content_hash": "a" * 64,
        },
    }
    mutations = [
        lambda m, r: m["behavior_episode_artifact"].pop("content_hash"),
        lambda m, r: m["candidate_assembly"]["surfaces"][0].pop("content_hash"),
        lambda m, r: m["receipt_bundle"]["evidence"].pop("behavior_episode_hash"),
        lambda m, r: m["receipt_bundle"]["evidence"]["surface_hashes"].pop(
            "behavior_episode.json"
        ),
        lambda m, r: r["run_summary"].pop("behavior_episode_hash"),
        lambda m, r: r["program_behavior_episode_artifact"].pop("content_hash"),
    ]
    for mutate in mutations:
        current_manifest = json.loads(json.dumps(manifest))
        current_receipt = json.loads(json.dumps(receipt))
        mutate(current_manifest, current_receipt)
        assert _missing_behavior_episode_declarations(
            manifest=current_manifest, receipt=current_receipt
        )

    assert not _missing_behavior_episode_declarations(
        manifest={"candidate_assembly": {"surfaces": []}}, receipt={}
    )
    sole_indicators = [
        (
            {
                "behavior_episode_artifact": {
                    "path": "behavior_episode.json",
                    "content_hash": "a" * 64,
                },
                "candidate_assembly": {"surfaces": []},
            },
            {},
        ),
        (
            {
                "candidate_assembly": {
                    "surfaces": [
                        {
                            "kind": "behavior_episode",
                            "path": "behavior_episode.json",
                            "content_hash": "a" * 64,
                        }
                    ]
                }
            },
            {},
        ),
        (
            {
                "candidate_assembly": {"surfaces": []},
                "receipt_bundle": {
                    "evidence": {
                        "behavior_episode_path": "behavior_episode.json",
                        "behavior_episode_hash": "a" * 64,
                    }
                },
            },
            {},
        ),
        (
            {
                "candidate_assembly": {"surfaces": []},
                "receipt_bundle": {
                    "evidence": {"surface_hashes": {"behavior_episode.json": "a" * 64}}
                },
            },
            {},
        ),
        (
            {"candidate_assembly": {"surfaces": []}},
            {"run_summary": {"behavior_episode_hash": "a" * 64}},
        ),
        (
            {"candidate_assembly": {"surfaces": []}},
            {
                "program_behavior_episode_artifact": {
                    "path": "behavior_episode.json",
                    "content_hash": "a" * 64,
                }
            },
        ),
    ]
    for sole_manifest, sole_receipt in sole_indicators:
        assert _missing_behavior_episode_declarations(
            manifest=sole_manifest, receipt=sole_receipt
        )


def test_program_receipt_fails_after_behavior_episode_mutation_or_deletion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_REPLAY_FIXTURE_JSON", json.dumps({"answer": "safe"}))
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

    receipt_payload = json.loads(receipt.read_text(encoding="utf-8"))
    original_receipt = dict(receipt_payload)
    receipt_payload["program_behavior_episode_artifact"] = dict(
        receipt_payload["program_behavior_episode_artifact"]
    )
    receipt_payload["program_behavior_episode_artifact"]["content_hash"] = "f" * 64
    receipt.write_text(json.dumps(receipt_payload), encoding="utf-8")
    declaration_drift = check_run_receipt(receipt)
    assert declaration_drift["status"] != "ok"
    assert (
        declaration_drift["checks"]["program_behavior_episode_declaration_consistent"]
        is False
    )
    receipt.write_text(json.dumps(original_receipt), encoding="utf-8")
    assert check_run_receipt(receipt)["status"] == "ok"

    missing_receipt_declaration = json.loads(receipt.read_text(encoding="utf-8"))
    del missing_receipt_declaration["program_behavior_episode_artifact"]["content_hash"]
    receipt.write_text(json.dumps(missing_receipt_declaration), encoding="utf-8")
    incomplete = check_run_receipt(receipt)
    assert incomplete["status"] != "ok"
    assert (
        incomplete["checks"]["program_behavior_episode_declarations_complete"] is False
    )
    receipt.write_text(json.dumps(original_receipt), encoding="utf-8")

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

    normalized_alias, manifest_path = _manifest(
        tmp_path,
        [
            {"kind": "plain", "path": artifact.name, "content_hash": digest},
            {
                "kind": "dot_alias",
                "path": f"./{artifact.name}",
                "content_hash": digest,
            },
        ],
    )
    with pytest.raises(ValueError, match="duplicated after normalization"):
        validate_candidate_artifact_closure(
            normalized_alias,
            manifest_path=manifest_path,
        )

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

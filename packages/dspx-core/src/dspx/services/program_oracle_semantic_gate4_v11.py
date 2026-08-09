# summary: "Canonical AK-backed Gate-4 authority adapter for dormant semantic v11 execution."
from __future__ import annotations

import json
import os
import stat
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dspx.services.program_oracle_semantic_contract_v11 import (
    CONTRACT_SHA256,
    SemanticV11Error,
    assert_sha256,
    canonical,
    mapping,
    sha256,
)

from dspx.services.program_oracle_semantic_gate4_contract_v11 import (
    CANDIDATE_SOURCE_PATHS,
    EXACT_ROUTE,
    GATE4_DONE_CONTRACT,
    GATE4_GUARDRAILS,
    REQUIRED_LIVE_COMPLETION_KIND,
    REQUIRED_REVIEW_COMPLETION_KIND,
)

AK_EXECUTABLE = Path.home() / ".local/bin/ak"
_AUTHORITY_TOKEN = object()
_GIT_ID_LENGTH = 40


class Gate4AuthorityCapability:
    """Non-serializable, single-process capability minted from canonical AK reads."""

    __slots__ = (
        "live_task_id",
        "candidate_commit",
        "candidate_tree",
        "candidate_source_manifest_sha256",
        "contract_sha256",
        "candidate_review_sha256",
        "live_gate_sha256",
        "authority_snapshot_sha256",
        "task_entity_version",
        "_pid",
        "_claimed",
        "_sealed",
    )

    live_task_id: int
    candidate_commit: str
    candidate_tree: str
    candidate_source_manifest_sha256: str
    contract_sha256: str
    candidate_review_sha256: str
    live_gate_sha256: str
    authority_snapshot_sha256: str
    task_entity_version: int
    _pid: int
    _claimed: bool
    _sealed: bool

    def __init__(
        self,
        *,
        live_task_id: int,
        candidate_commit: str,
        candidate_tree: str,
        candidate_source_manifest_sha256: str,
        contract_sha256: str,
        candidate_review_sha256: str,
        live_gate_sha256: str,
        authority_snapshot_sha256: str,
        task_entity_version: int,
        token: object,
    ) -> None:
        if token is not _AUTHORITY_TOKEN:
            raise TypeError(
                "Gate4AuthorityCapability requires canonical AK authentication"
            )
        object.__setattr__(self, "live_task_id", live_task_id)
        object.__setattr__(self, "candidate_commit", candidate_commit)
        object.__setattr__(self, "candidate_tree", candidate_tree)
        object.__setattr__(
            self,
            "candidate_source_manifest_sha256",
            candidate_source_manifest_sha256,
        )
        object.__setattr__(self, "contract_sha256", contract_sha256)
        object.__setattr__(self, "candidate_review_sha256", candidate_review_sha256)
        object.__setattr__(self, "live_gate_sha256", live_gate_sha256)
        object.__setattr__(self, "authority_snapshot_sha256", authority_snapshot_sha256)
        object.__setattr__(self, "task_entity_version", task_entity_version)
        object.__setattr__(self, "_pid", os.getpid())
        object.__setattr__(self, "_claimed", False)
        object.__setattr__(self, "_sealed", True)
        self.require_current()

    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "_sealed", False):
            raise TypeError("Gate4AuthorityCapability is immutable")
        object.__setattr__(self, name, value)

    def require_current(self) -> None:
        if (
            type(self) is not Gate4AuthorityCapability
            or self.live_task_id <= 0
            or self.live_task_id == 4643
            or self._pid != os.getpid()
            or len(self.candidate_commit) != _GIT_ID_LENGTH
            or len(self.candidate_tree) != _GIT_ID_LENGTH
            or any(
                character not in "0123456789abcdef"
                for character in self.candidate_commit + self.candidate_tree
            )
            or self.contract_sha256 != CONTRACT_SHA256
            or self.task_entity_version <= 0
        ):
            raise SemanticV11Error("Gate-4 authority capability drift")
        for value, label in (
            (
                self.candidate_source_manifest_sha256,
                "candidate_source_manifest_sha256",
            ),
            (self.candidate_review_sha256, "candidate_review_sha256"),
            (self.live_gate_sha256, "live_gate_sha256"),
            (self.authority_snapshot_sha256, "authority_snapshot_sha256"),
        ):
            assert_sha256(value, label)

    def claim_for_entry(self) -> None:
        self.require_current()
        if self._claimed:
            raise SemanticV11Error("Gate-4 authority capability already consumed")
        object.__setattr__(self, "_claimed", True)

    def payload(self) -> dict[str, Any]:
        self.require_current()
        return {
            "live_task_id": self.live_task_id,
            "candidate_commit": self.candidate_commit,
            "candidate_tree": self.candidate_tree,
            "candidate_source_manifest_sha256": (self.candidate_source_manifest_sha256),
            "contract_sha256": self.contract_sha256,
            "candidate_review_sha256": self.candidate_review_sha256,
            "live_gate_sha256": self.live_gate_sha256,
            "authority_snapshot_sha256": self.authority_snapshot_sha256,
            "task_entity_version": self.task_entity_version,
        }


def candidate_source_manifest(repo_root: Path) -> dict[str, str]:
    """Hash the exact Gate-3-reviewed v11 candidate source set."""

    root = repo_root.expanduser().resolve(strict=True)
    manifest: dict[str, str] = {}
    for relative in CANDIDATE_SOURCE_PATHS:
        path = root / relative
        try:
            info = path.lstat()
            raw = path.read_bytes()
        except OSError as exc:
            raise SemanticV11Error("candidate source member unavailable") from exc
        if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise SemanticV11Error("candidate source member posture drift")
        manifest[relative] = sha256(raw)
    return manifest


def candidate_source_manifest_sha256(repo_root: Path) -> str:
    return sha256(canonical(candidate_source_manifest(repo_root)))


def _machine_payload(value: object, surface: str) -> dict[str, Any]:
    envelope = mapping(value, f"{surface} machine envelope")
    if (
        envelope.get("surface") != surface
        or envelope.get("ok") is not True
        or envelope.get("error") is not None
    ):
        raise SemanticV11Error("canonical AK machine envelope rejected")
    return mapping(envelope.get("payload"), f"{surface} payload")


def _evidence(value: object, expected_id: int) -> dict[str, Any]:
    payload = _machine_payload(value, "evidence.show")
    evidence = mapping(payload.get("evidence"), "AK evidence")
    if evidence.get("id") != expected_id or evidence.get("result") != "pass":
        raise SemanticV11Error("canonical AK evidence rejected")
    return evidence


def _resolved_repo(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise SemanticV11Error(f"{label} repo binding rejected")
    try:
        return Path(value).expanduser().resolve(strict=True)
    except OSError as exc:
        raise SemanticV11Error(f"{label} repo binding rejected") from exc


def _git_identity(repo_root: Path) -> tuple[str, str]:
    root = repo_root.expanduser().resolve(strict=True)
    commands = (
        ("commit", ["git", "-C", str(root), "rev-parse", "HEAD"]),
        ("tree", ["git", "-C", str(root), "rev-parse", "HEAD^{tree}"]),
        (
            "status",
            [
                "git",
                "-C",
                str(root),
                "status",
                "--porcelain=v1",
                "--untracked-files=normal",
            ],
        ),
    )
    values: dict[str, str] = {}
    for label, command in commands:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
            env={"HOME": str(Path.home()), "PATH": "/usr/bin:/bin"},
        )
        if completed.returncode != 0:
            raise SemanticV11Error("candidate Git identity unavailable")
        values[label] = completed.stdout.strip()
    status_lines = [line for line in values["status"].splitlines() if line]
    allowed_protected = {"?? .ontology/", "?? .ontology"}
    if set(status_lines) - allowed_protected:
        raise SemanticV11Error("candidate worktree is not review-clean")
    return values["commit"], values["tree"]


def validate_gate4_authority_documents(
    *,
    repo_root: Path,
    live_task_id: int,
    review_evidence_id: int,
    gate_evidence_id: int,
    task_document: Mapping[str, Any],
    contract_document: Mapping[str, Any],
    review_task_document: Mapping[str, Any],
    review_contract_document: Mapping[str, Any],
    review_evidence_document: Mapping[str, Any],
    gate_evidence_document: Mapping[str, Any],
) -> dict[str, Any]:
    """Pure provider-free validator; returns facts and never mints authority."""

    if (
        isinstance(live_task_id, bool)
        or not isinstance(live_task_id, int)
        or live_task_id <= 0
        or live_task_id == 4643
        or review_evidence_id <= 0
        or gate_evidence_id <= 0
        or review_evidence_id == gate_evidence_id
    ):
        raise SemanticV11Error("Gate-4 AK selector rejected")
    root = repo_root.expanduser().resolve(strict=True)
    task_payload = _machine_payload(task_document, "task.show")
    task = mapping(task_payload.get("task"), "AK task")
    if (
        task.get("id") != live_task_id
        or task.get("status") not in {"claimed", "running"}
        or _resolved_repo(task.get("repo"), "Gate-4 task") != root
        or not isinstance(task.get("entity_version"), int)
        or isinstance(task.get("entity_version"), bool)
        or task["entity_version"] <= 0
    ):
        raise SemanticV11Error("canonical Gate-4 task rejected")
    contract = dict(contract_document)
    done = mapping(contract.get("done_contract"), "Gate-4 done contract version")
    done_payload = mapping(done.get("contract"), "Gate-4 done contract")
    guardrail_version = mapping(contract.get("guardrails"), "Gate-4 guardrails version")
    guardrails = mapping(guardrail_version.get("guardrails"), "Gate-4 guardrails")
    if (
        contract.get("task_id") != live_task_id
        or _resolved_repo(contract.get("repo"), "Gate-4 contract") != root
        or contract.get("status") != task.get("status")
        or done.get("task_id") != live_task_id
        or guardrail_version.get("task_id") != live_task_id
        or done_payload != GATE4_DONE_CONTRACT
        or guardrails != GATE4_GUARDRAILS
    ):
        raise SemanticV11Error("canonical Gate-4 task contract rejected")
    review_evidence = _evidence(review_evidence_document, review_evidence_id)
    review_task_ref = review_evidence.get("task_ref")
    if (
        isinstance(review_task_ref, bool)
        or not isinstance(review_task_ref, int)
        or review_task_ref <= 0
        or review_task_ref == live_task_id
    ):
        raise SemanticV11Error("canonical Gate-3 task reference rejected")
    review_task_payload = _machine_payload(review_task_document, "task.show")
    review_task = mapping(review_task_payload.get("task"), "Gate-3 task")
    review_contract = dict(review_contract_document)
    review_done = mapping(
        review_contract.get("done_contract"), "Gate-3 done contract version"
    )
    review_done_payload = mapping(review_done.get("contract"), "Gate-3 done contract")
    if (
        review_task.get("id") != review_task_ref
        or review_task.get("status") != "done"
        or _resolved_repo(review_task.get("repo"), "Gate-3 task") != root
        or review_contract.get("task_id") != review_task_ref
        or review_contract.get("status") != "done"
        or _resolved_repo(review_contract.get("repo"), "Gate-3 contract") != root
        or review_done.get("task_id") != review_task_ref
        or review_done_payload.get("completion_kind") != REQUIRED_REVIEW_COMPLETION_KIND
    ):
        raise SemanticV11Error("canonical Gate-3 task lifecycle rejected")
    gate_evidence = _evidence(gate_evidence_document, gate_evidence_id)
    review = mapping(review_evidence.get("details"), "Gate-3 review details")
    gate = mapping(gate_evidence.get("details"), "Gate-4 authority details")
    commit, tree = _git_identity(root)
    source_manifest_digest = candidate_source_manifest_sha256(root)
    expected_review = {
        "schema_version": "dspx-oracle-semantic-v11-candidate-review-v1",
        "gate_2_task_id": 4691,
        "gate_3_task_id": review_task_ref,
        "decision": "ACCEPT_V11_CANDIDATE_FOR_SEPARATE_LIVE_GATE",
        "contract_sha256": CONTRACT_SHA256,
        "candidate_commit": commit,
        "candidate_tree": tree,
        "candidate_source_manifest_sha256": source_manifest_digest,
        "provider_free_gate": "passed",
    }
    if (
        review_evidence.get("check_type") != "oracle_semantic_v11_candidate_review"
        or review != expected_review
    ):
        raise SemanticV11Error("canonical Gate-3 acceptance rejected")
    review_digest = sha256(canonical(review))
    contract_digest = sha256(canonical(contract))
    expected_gate = {
        "schema_version": "dspx-oracle-semantic-v11-live-gate-v1",
        "live_task_id": live_task_id,
        "completion_kind": REQUIRED_LIVE_COMPLETION_KIND,
        "decision": "AUTHORIZE_EXACTLY_ONE_V11_CORPUS_PROCESS",
        "operator_authorization": (
            "OPERATOR_AUTHORIZED_EXACTLY_ONE_V11_CORPUS_PROCESS"
        ),
        "candidate_review_evidence_id": review_evidence_id,
        "candidate_review_sha256": review_digest,
        "contract_sha256": CONTRACT_SHA256,
        "candidate_commit": commit,
        "candidate_tree": tree,
        "candidate_source_manifest_sha256": source_manifest_digest,
        "task_entity_version": task["entity_version"],
        "task_contract_sha256": contract_digest,
        "route": EXACT_ROUTE,
        "maximum_corpus_processes": 1,
        "maximum_health_probes": 0,
        "maximum_dspx_managed_retries": 0,
        "fallback_allowed": False,
    }
    if (
        gate_evidence.get("task_ref") != live_task_id
        or gate_evidence.get("check_type") != "oracle_semantic_v11_live_gate"
        or gate != expected_gate
    ):
        raise SemanticV11Error("canonical Gate-4 authorization rejected")
    gate_digest = sha256(canonical(gate))
    snapshot = {
        "task_sha256": sha256(canonical(task)),
        "task_contract_sha256": contract_digest,
        "review_task_sha256": sha256(canonical(review_task)),
        "review_task_contract_sha256": sha256(canonical(review_contract)),
        "review_evidence_sha256": sha256(canonical(review_evidence)),
        "gate_evidence_sha256": sha256(canonical(gate_evidence)),
    }
    return {
        "live_task_id": live_task_id,
        "candidate_commit": commit,
        "candidate_tree": tree,
        "candidate_source_manifest_sha256": source_manifest_digest,
        "contract_sha256": CONTRACT_SHA256,
        "candidate_review_sha256": review_digest,
        "live_gate_sha256": gate_digest,
        "authority_snapshot_sha256": sha256(canonical(snapshot)),
        "task_entity_version": task["entity_version"],
    }


def _run_ak(*args: str) -> dict[str, Any]:
    try:
        info = AK_EXECUTABLE.resolve(strict=True).stat()
    except OSError as exc:
        raise SemanticV11Error("canonical AK executable unavailable") from exc
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or not info.st_mode & stat.S_IXUSR
    ):
        raise SemanticV11Error("canonical AK executable posture drift")
    environment = {
        "HOME": str(Path.home()),
        "PATH": "/usr/bin:/bin",
        "XDG_CONFIG_HOME": str(Path.home() / ".config"),
        "XDG_DATA_HOME": str(Path.home() / ".local/share"),
        "XDG_STATE_HOME": str(Path.home() / ".local/state"),
    }
    completed = subprocess.run(
        [str(AK_EXECUTABLE), *args],
        check=False,
        capture_output=True,
        timeout=30,
        env=environment,
    )
    if completed.returncode != 0 or completed.stderr:
        raise SemanticV11Error("canonical AK authority read failed")
    try:
        value = json.loads(completed.stdout)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SemanticV11Error("canonical AK authority output invalid") from exc
    return mapping(value, "canonical AK authority output")


def authenticate_gate4_authority(
    *,
    repo_root: Path,
    live_task_id: int,
    review_evidence_id: int,
    gate_evidence_id: int,
) -> Gate4AuthorityCapability:
    """Authenticate current AK task/evidence and mint one dormant-runner capability."""

    review_evidence_document = _run_ak(
        "evidence", "show", str(review_evidence_id), "--machine"
    )
    review_evidence = _evidence(review_evidence_document, review_evidence_id)
    review_task_id = review_evidence.get("task_ref")
    if isinstance(review_task_id, bool) or not isinstance(review_task_id, int):
        raise SemanticV11Error("canonical Gate-3 task reference rejected")
    documents = {
        "task_document": _run_ak("task", "show", str(live_task_id), "--machine"),
        "contract_document": _run_ak(
            "task", "contract", "show", str(live_task_id), "-F", "json"
        ),
        "review_task_document": _run_ak(
            "task", "show", str(review_task_id), "--machine"
        ),
        "review_contract_document": _run_ak(
            "task", "contract", "show", str(review_task_id), "-F", "json"
        ),
        "review_evidence_document": review_evidence_document,
        "gate_evidence_document": _run_ak(
            "evidence", "show", str(gate_evidence_id), "--machine"
        ),
    }
    payload = validate_gate4_authority_documents(
        repo_root=repo_root,
        live_task_id=live_task_id,
        review_evidence_id=review_evidence_id,
        gate_evidence_id=gate_evidence_id,
        **documents,
    )
    return Gate4AuthorityCapability(**payload, token=_AUTHORITY_TOKEN)

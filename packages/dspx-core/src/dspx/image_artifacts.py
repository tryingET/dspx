"""Private acyclic image artifacts and caller-anchored, read-only spent verification."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import TYPE_CHECKING, TypedDict, cast

from .image_admission import (
    canonical,
    closed,
    hash_value,
    parse_json,
    require,
    sha,
)
from .image_records import (
    _CLOSURE,
    list_root,
    private_root,
    publish,
    read_record,
    scan,
    read_image_artifact as _read,
    publish_image_output as _publish_output,
)
from .image_input_contract import reject_output
from .image_effects import image_effect_envelope

if TYPE_CHECKING:
    from .image_custody import ImageCustodySession

_NON_AUTHORITY = "promotion_authority activation_authority governance_mutated external_authority_mutated shared_oracle_mutated release_authority"
_REPLAY = {
    "receipt_integrity_check_supported": True,
    "execution_reproduction_supported": False,
    "semantic_reproduction_claim": False,
    "quality_reproduction_claim": False,
    "reason": "image_execution_replay_unsupported",
}
_SCHEMAS = {
    "image_source_package.json": "dspx-image-source-package-v1",
    "image_input_manifest.json": "dspx-image-input-manifest-v2",
    "runtime_image_inputs.json": "program-runtime-image-inputs-v1",
    "image_behavior_results.json": "program-image-behavior-results-v1",
    "image_program_runtime_traces.json": "program-image-traces-v1",
    "image_oracle_evidence.json": "program-image-oracle-evidence-v1",
    "runtime_image_episode.json": "program-runtime-image-episode-v1",
    "runtime_image_episode.json.meta.json": "dspx-image-run-receipt-v1",
    "direct_image_run_receipt.json": "generated-dspy-direct-image-v1",
    "image_content_artifacts.json": "dspx-image-artifacts-v1",
    "image_published_artifacts.json": "dspx-image-artifacts-v1",
}


@dataclass(frozen=True, slots=True, repr=False)
class ImageRunAnchor:
    custody_fd: int
    artifact_fd: int
    closure_sha256: str
    admission_raw: bytes
    source_raw: bytes
    manifest_raw: bytes
    output_slots: int


@dataclass(frozen=True, slots=True, repr=False)
class ImageArtifactBinding:
    root_fd: int
    root_dev: int
    root_ino: int
    caller_run_id: str
    admission_sha256: str
    input_manifest_sha256: str
    published_sha256: str
    output_slots: int


class ArtifactEntry(TypedDict):
    name: str
    schema_version: str
    sha256: str
    byte_count: int


class ArtifactManifest(TypedDict):
    schema_version: str
    caller_run_id: str
    artifacts: list[ArtifactEntry]


def _entry(fd: int, name: str) -> ArtifactEntry:
    raw = _read(fd, name)
    schema = _SCHEMAS.get(name, "program-image-output-v1")
    return {
        "name": name,
        "schema_version": schema,
        "sha256": sha(raw),
        "byte_count": len(raw),
    }


def _manifest(fd: int, caller: str, names: list[str], target: str) -> str:
    require(target not in names and len(set(names)) == len(names), "image_custody")
    return publish(
        fd,
        target,
        {
            "schema_version": "dspx-image-artifacts-v1",
            "caller_run_id": caller,
            "artifacts": [_entry(fd, name) for name in names],
        },
    )


def build_image_receipt(
    session, content_sha256: str, *, route: str, outcome: str
) -> dict[str, object]:
    require(
        route in {"episode", "direct"} and hash_value(content_sha256), "image_custody"
    )
    return {
        "schema_version": "dspx-image-run-receipt-v1"
        if route == "episode"
        else "generated-dspy-direct-image-v1",
        "run_kind": "program-runtime-image"
        if route == "episode"
        else "generated-direct-image",
        "caller_run_id": session.binding["caller_run_id"],
        "candidate_manifest_sha256": session.record["candidate_manifest_sha256"],
        "source_package_sha256": session.record["source_package_sha256"],
        "admission_sha256": session.admission.sha256,
        "input_manifest_sha256": session.manifest_sha256,
        "content_artifact_manifest_sha256": content_sha256,
        "effect_evidence": image_effect_envelope(session),
        "local_outcome": outcome,
        "replay_policy": dict(_REPLAY),
        "non_authority": dict.fromkeys(_NON_AUTHORITY.split(), False),
    }


def publish_image_run(
    session: ImageCustodySession,
    *,
    artifact_fd: int,
    outputs: dict[str, object],
    route: str,
) -> ImageArtifactBinding:
    from .image_custody import ImageCustodySession
    from .image_worker import require_clean_boundary

    require_clean_boundary()  # before any session attribute or artifact root is read
    require(type(session) is ImageCustodySession, "image_custody")
    root = private_root(artifact_fd)
    require(not list_root(artifact_fd), "image_spent")
    # Only a settled, all-success run publishes: refused before the first write.
    require(not session.poisoned and not session.closed, "image_spent")
    rows = session._scan()
    require(
        rows
        and len(rows) == len(session.record["request_plan"])
        and all(
            term is not None
            and term["provider_disposition"] == "completed_success"
            and term["typed_finalization_completed"] is True
            for _, term in rows
        ),
        "image_custody",
    )
    reject_output(outputs, session.context)
    from .image_privacy import require_privacy
    from .image_source_profile import ImageSourceProfile

    profile = require_privacy().profile
    require(
        type(profile) is ImageSourceProfile
        and tuple(outputs) == profile.snapshot.outputs,
        "image_custody",
    )
    caller = session.binding["caller_run_id"]
    source, manifest = session.context.source, session.manifest
    content_names = list(_SCHEMAS)[:5]
    publish(artifact_fd, content_names[0], source)
    publish(artifact_fd, content_names[1], manifest)
    publish(
        artifact_fd,
        content_names[2],
        {
            "schema_version": _SCHEMAS[content_names[2]],
            "source_package_sha256": session.context.source_sha256,
            "input_manifest_sha256": session.manifest_sha256,
            "input_shape_sha256": source["input_shape_sha256"],
            "plain_text_commitments": source["plain_text_slots"],
        },
    )
    import json

    records = [
        {
            "schema_version": "program-image-output-v1",
            "caller_run_id": caller,
            "field_slot": slot,
            "value": value,
        }
        for slot, value in enumerate(outputs.values())
    ]
    total = sum(
        len(
            json.dumps(
                record,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("ascii")
        )
        for record in records
    )
    require(
        total <= session.record["limits"]["max_output_artifact_bytes"], "image_budget"
    )
    commitments = []
    for slot, record in enumerate(records):
        name = f"image_output_{slot:06d}.json"
        value_sha = _publish_output(artifact_fd, name, record)
        size = len(_read(artifact_fd, name))
        content_names.append(name)
        commitments.append(
            {"field_slot": slot, "sha256": value_sha, "byte_count": size}
        )
    publish(
        artifact_fd,
        content_names[3],
        {
            "schema_version": _SCHEMAS[content_names[3]],
            "caller_run_id": caller,
            "candidate_manifest_sha256": session.record["candidate_manifest_sha256"],
            "source_package_sha256": session.context.source_sha256,
            "execution_status": "executed",
            "local_outcome": "completed",
            "output_commitments": commitments,
            "quality_status": "not_evaluated",
            "failure_code": None,
        },
    )
    publish(
        artifact_fd,
        content_names[4],
        {
            "schema_version": _SCHEMAS[content_names[4]],
            "caller_run_id": caller,
            "predictor_plan_ordinals": [intent["plan_ordinal"] for intent, _ in rows],
            "attempt_ids": [intent["attempt_id"] for intent, _ in rows],
        },
    )
    content_sha = _manifest(
        artifact_fd, caller, content_names, "image_content_artifacts.json"
    )
    publish(
        artifact_fd,
        "image_oracle_evidence.json",
        {
            "schema_version": "program-image-oracle-evidence-v1",
            "caller_run_id": caller,
            "source_package_sha256": session.context.source_sha256,
            "artifact_manifest_sha256": content_sha,
            "authority": "local_non_authoritative",
        },
    )
    receipt_name = (
        "runtime_image_episode.json.meta.json"
        if route == "episode"
        else "direct_image_run_receipt.json"
    )
    publish(
        artifact_fd,
        receipt_name,
        build_image_receipt(session, content_sha, route=route, outcome="completed"),
    )
    extras = ["image_oracle_evidence.json", receipt_name]
    if route == "episode":
        publish(
            artifact_fd,
            "runtime_image_episode.json",
            {
                "schema_version": "program-runtime-image-episode-v1",
                "caller_run_id": caller,
                "candidate_manifest_sha256": session.record[
                    "candidate_manifest_sha256"
                ],
                "source_package_sha256": session.context.source_sha256,
                "input_manifest_sha256": session.manifest_sha256,
                "admission_sha256": session.admission.sha256,
                "effect_evidence": image_effect_envelope(session),
                "artifact_manifest_sha256": content_sha,
                "local_outcome": "completed",
                "non_authority": dict.fromkeys(_NON_AUTHORITY.split(), False),
            },
        )
        extras.append("runtime_image_episode.json")
    published = _manifest(
        artifact_fd,
        caller,
        ["image_content_artifacts.json", *content_names, *extras],
        "image_published_artifacts.json",
    )
    return ImageArtifactBinding(
        artifact_fd,
        root.st_dev,
        root.st_ino,
        caller,
        session.admission.sha256,
        session.manifest_sha256,
        published,
        len(outputs),
    )


def verify_artifact_binding(binding: ImageArtifactBinding, session) -> None:
    from .image_worker import require_clean_boundary

    require_clean_boundary()
    require(type(binding) is ImageArtifactBinding, "image_custody")
    root = private_root(binding.root_fd)
    require(
        (root.st_dev, root.st_ino) == (binding.root_dev, binding.root_ino)
        and binding.caller_run_id == session.binding["caller_run_id"]
        and binding.admission_sha256 == session.admission.sha256
        and binding.input_manifest_sha256 == session.manifest_sha256,
        "image_custody",
    )
    from .image_record_validation import validate_artifact_chain

    validate_artifact_chain(
        binding.root_fd,
        binding.published_sha256,
        session,
        session.context.source_raw,
        canonical(session.manifest),
        binding.output_slots,
    )


def _check_manifest(fd: int, name: str, expected: str, caller: str) -> ArtifactManifest:
    raw = read_record(fd, name)
    require(sha(raw) == expected, "image_custody")
    row = closed(parse_json(raw), "schema_version caller_run_id artifacts")
    require(
        row["schema_version"] == "dspx-image-artifacts-v1"
        and row["caller_run_id"] == caller
        and type(row["artifacts"]) is list
        and row["artifacts"],
        "image_custody",
    )
    entries = row["artifacts"]
    names = set()
    for entry in entries:
        item = closed(entry, "name schema_version sha256 byte_count")
        target = item["name"]
        require(
            type(target) is str
            and target not in {name, "closure.json"}
            and target not in names
            and (
                target in _SCHEMAS
                or re.fullmatch(r"image_output_[0-9]{6}\.json", target) is not None
            ),
            "image_custody",
        )
        names.add(target)
        require(item == _entry(fd, target), "image_custody")
    return cast(ArtifactManifest, row)


def verify_image_run(anchor: ImageRunAnchor) -> dict[str, object]:
    # Parent-side integrity check over payload-free custody/artifact records only.
    require(type(anchor) is ImageRunAnchor, "image_custody")
    private_root(anchor.artifact_fd)
    from .image_record_validation import (
        read_only_custody,
        reconcile,
        validate_artifact_chain,
    )

    view = read_only_custody(
        anchor.custody_fd,
        admission_raw=anchor.admission_raw,
        source_raw=anchor.source_raw,
        manifest_raw=anchor.manifest_raw,
    )
    admission, record = view.admission, view.record
    state = reconcile(view)
    # An absent terminal, unsettled residue or missing closure is a burnt run.
    require(
        state["terminal_effect"] == "completed_success"
        and state["publication_residue"] == 0
        and state["closure_present"],
        "image_spent",
    )
    rows = scan(view, allow_closure=True)
    raw = read_record(anchor.custody_fd, "closure.json")
    require(sha(raw) == anchor.closure_sha256, "image_custody")
    closure = closed(parse_json(raw), _CLOSURE)
    commitments = [
        {
            "ordinal": intent["attempt_ordinal"],
            "attempt_id": intent["attempt_id"],
            "terminal_sha256": sha(
                read_record(
                    anchor.custody_fd, f"terminal-{intent['attempt_ordinal']}.json"
                )
            ),
        }
        for intent, _ in rows
    ]
    require(
        closure["schema_version"] == "dspx-image-run-closure-v1"
        and bool(rows)
        and len(rows) == len(record["request_plan"])
        and closure["consumed_dispatches"] == len(rows)
        and closure["terminal_commitments"] == commitments
        and all(
            term is not None and term["provider_disposition"] == "completed_success"
            for _, term in rows
        )
        and closure["local_outcome"] == "completed"
        and closure["admission_sha256"] == admission.sha256
        and closure["input_manifest_sha256"] == view.manifest_sha256
        and all(
            closure[key] == record["custody"][key]
            for key in ("custody_id", "caller_run_id")
        ),
        "image_custody",
    )
    caller = record["custody"]["caller_run_id"]
    validate_artifact_chain(
        anchor.artifact_fd,
        closure["artifact_manifest_sha256"],
        view,
        anchor.source_raw,
        anchor.manifest_raw,
        anchor.output_slots,
    )
    return {
        "status": "ok",
        "spent": True,
        "dispatch_available": False,
        "caller_run_id": caller,
        "closure_sha256": anchor.closure_sha256,
        "receipt_integrity": True,
        "execution_reproduction": False,
    }

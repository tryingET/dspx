"""Shared shipped image preparation/execution in the clean worker; synthetic fixture only.

Owner refinement 13975: the parent validates types, reserves its nominal authority and
names a declared entry; all payload reading, formatting and dispatch happen inside the
fresh `-I -S` worker. Live authority is never executed by this module.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import cast

import dspy
from dspy.core.types import LMImagePart, LMTextPart

from .image_admission import (
    CEILINGS,
    ImageAdmission,
    ImageContractError,
    SyntheticImageAuthority,
    canonical,
    closed,
    digest,
    parse_json,
    require,
    sha,
    validate_admission,
)
from .image_custody import ImageCustodySession, parent_initializer
from .image_decoder import FrozenImageDecoder
from .image_effects import SyntheticTransportFixture, fixture_transport
from .image_input_contract import ImageContext, materialize_image_inputs, reject_output
from .image_privacy import image_privacy, runtime_identity
from .image_records import list_root, private_root, publish, read_record
from .image_source_io import read_relative
from .image_source_profile import ImageSourceProfile, convert_value
from .image_supervision import supervise_image_worker
from .image_worker import worker_entry
from .provider_contract import (
    ProviderImagePart,
    ProviderPartsMessage,
    ProviderRequest,
    ProviderTextPart,
    image_payload,
)

_PREPARATION = "schema_version source markers plan model use_cot runtime_identity_sha256 output_slots"


@dataclass(frozen=True, slots=True, repr=False)
class ImagePreparation:
    raw: bytes

    def __post_init__(self) -> None:
        row = closed(parse_json(self.raw, limit=65_536), _PREPARATION)
        require(
            row["schema_version"] == "dspx-image-preparation-v1"
            and type(row["use_cot"]) is bool
            and canonical(row) == self.raw,
            "image_custody",
        )

    @property
    def record(self) -> dict[str, object]:
        return cast(dict[str, object], parse_json(self.raw, limit=65_536))


@dataclass(frozen=True, slots=True, repr=False)
class ImageExecutionRequest:
    candidate_fd: int
    input_fd: int
    input_name: str
    artifact_fd: int
    custody_fd: int
    preparation: ImagePreparation
    admission: ImageAdmission
    authority: object
    fixture: SyntheticTransportFixture

    def execute(self, *, route: str):
        return execute_image_program(
            candidate_fd=self.candidate_fd,
            input_fd=self.input_fd,
            input_name=self.input_name,
            artifact_fd=self.artifact_fd,
            custody_fd=self.custody_fd,
            preparation=self.preparation,
            admission=self.admission,
            authority=self.authority,
            fixture=self.fixture,
            route=route,
        )


@dataclass(frozen=True, slots=True)
class RequestPreview:
    record: dict[str, object]
    context: ImageContext


def _status(
    status: str, commitment: str, failure: str | None = None
) -> dict[str, object]:
    return {
        "status": status,
        "commitment_sha256": commitment,
        "fixture_evidence": True,
        "live_authorized": False,
        "failure_code": failure,
    }


def _prepare(
    active,
    *,
    candidate_fd: int,
    input_fd: int,
    input_name: str,
    model: str,
    use_cot: bool,
    limits: dict[str, int] | None = None,
):
    # This executes only inside the parent-owned privacy worker. Construction is
    # checked; Module/Predict/LM/provider invocation is absent from this path.
    profile = ImageSourceProfile(candidate_fd)
    root = profile.build(use_cot=use_cot)
    active.bind_graph(root, profile=profile)
    decoder = FrozenImageDecoder()
    from .image_admission import bounded_tree

    ceilings = dict(CEILINGS) if limits is None else limits
    raw = read_relative(input_fd, input_name, limit=ceilings["max_input_json_bytes"])
    bounded_tree(
        parse_json(raw),
        max_depth=ceilings["max_depth"],
        max_nodes=ceilings["max_nodes"],
    )
    context = materialize_image_inputs(
        raw,
        root_fd=input_fd,
        fields=profile.snapshot.inputs,
        candidate_manifest_sha256=profile.snapshot.manifest_sha256,
        candidate_source_sha256=profile.snapshot.sha256,
        decoder=decoder,
    )
    predictor = vars(root)["predict"]
    if type(predictor) is dspy.ChainOfThought:
        predictor = vars(predictor)["predict"]
    require(type(predictor) is dspy.Predict, "image_privacy")
    signature = predictor.signature
    values = context.materialized()
    converted = tuple(
        convert_value(signature.input_fields[name].annotation, values[name])
        for name in context.fields
    )
    context = ImageContext(
        context.fields,
        converted,
        context.occurrences,
        context.source_raw,
        context.input_raw,
    )
    active.context = context
    messages = active.formatter.format(signature, [], context.materialized())
    preview = RequestPreview({"model": model, "limits": ceilings}, context)
    ports = []
    cursor = 0
    for message in messages:
        parts: list[ProviderTextPart | ProviderImagePart] = []
        for part in message.parts:
            if type(part) is LMTextPart:
                parts.append(ProviderTextPart(part.text))
            else:
                require(
                    type(part) is LMImagePart and cursor < len(context.occurrences),
                    "image_marker_invalid",
                )
                item = context.occurrences[cursor]
                parts.append(
                    ProviderImagePart(
                        item.media_type,
                        item.data,
                        sha(item.data),
                        len(item.data),
                        item.width,
                        item.height,
                        item.occurrence_id,
                    )
                )
                cursor += 1
        ports.append(ProviderPartsMessage(message.role, tuple(parts)))
    _, shape, sequence = image_payload(
        ProviderRequest(model, tuple(ports), preview), preview
    )
    record = {
        "schema_version": "dspx-image-preparation-v1",
        "source": context.source,
        "markers": context.manifest("0" * 64)["marker_entries"],
        "plan": [
            {
                "plan_ordinal": 1,
                "predictor_slot": active.predictors[id(signature)],
                "request_shape_sha256": shape,
                "image_occurrence_sequence": sequence,
            }
        ],
        "model": model,
        "use_cot": use_cot,
        "runtime_identity_sha256": runtime_identity(),
        "output_slots": len(profile.snapshot.outputs),
    }
    return root, context, record


def prepare_image_execution(
    *,
    candidate_fd: int,
    input_fd: int,
    input_name: str,
    preparation_fd: int,
    model: str,
    use_cot: bool = False,
    wall_ms: int = 30_000,
) -> ImagePreparation:
    require(
        all(type(fd) is int for fd in (candidate_fd, input_fd, preparation_fd))
        and type(input_name) is str
        and type(model) is str
        and 0 < len(model) <= 200
        and type(use_cot) is bool
        and type(wall_ms) is int,
        "image_admission_invalid",
    )
    private_root(preparation_fd)
    require(not list_root(preparation_fd), "image_spent")
    params: dict[str, object] = {
        "candidate_fd": candidate_fd,
        "input_fd": input_fd,
        "input_name": input_name,
        "preparation_fd": preparation_fd,
        "model": model,
        "use_cot": use_cot,
    }
    result = supervise_image_worker(
        "dspx.image_execution:_prepare_entry",
        params,
        fds=(candidate_fd, input_fd, preparation_fd),
        wall_ms=wall_ms,
    )
    raw = read_record(preparation_fd, "preparation.json")
    require(result == _status("prepared", sha(raw)), "image_custody")
    return ImagePreparation(raw)


@worker_entry
def _prepare_entry(params: dict[str, object]) -> dict[str, object]:
    row = closed(
        params, "candidate_fd input_fd input_name preparation_fd model use_cot"
    )
    with image_privacy() as active:
        _, _, record = _prepare(
            active,
            candidate_fd=row["candidate_fd"],
            input_fd=row["input_fd"],
            input_name=row["input_name"],
            model=row["model"],
            use_cot=row["use_cot"],
        )
        return _status(
            "prepared", publish(row["preparation_fd"], "preparation.json", record)
        )


def execute_image_program(
    *,
    candidate_fd: int,
    input_fd: int,
    input_name: str,
    artifact_fd: int,
    custody_fd: int,
    preparation: ImagePreparation,
    admission: ImageAdmission,
    authority: object,
    fixture: SyntheticTransportFixture,
    route: str,
):
    """No configuration/env/raw JSON can mint the nominal parent capability."""
    from .image_artifacts import ImageRunAnchor, verify_image_run

    require(
        all(type(fd) is int for fd in (candidate_fd, input_fd, artifact_fd, custody_fd))
        and type(input_name) is str
        and type(preparation) is ImagePreparation
        and type(admission) is ImageAdmission
        and type(authority) is SyntheticImageAuthority
        and type(fixture) is SyntheticTransportFixture
        and type(route) is str
        and route in {"episode", "direct"},
        "image_admission_invalid",
    )
    authority = cast(SyntheticImageAuthority, authority)
    prepared = parse_json(preparation.raw, limit=65_536)
    validate_admission(
        admission.raw,
        source=prepared["source"],
        authority=authority,
        runtime_identity_sha256=runtime_identity(),
    )
    record = admission.record
    require(
        record["request_plan"] == prepared["plan"]
        # ubs:ignore -- public sha256 commitment, not a secret
        and record["source_package_sha256"] == digest("source-v1", prepared["source"])
        and record["runtime_identity_sha256"] == prepared["runtime_identity_sha256"]
        and record["model"] == prepared["model"],
        "image_admission_invalid",
    )
    artifact = private_root(artifact_fd)
    custody = private_root(custody_fd)
    require(
        (artifact.st_dev, artifact.st_ino) != (custody.st_dev, custody.st_ino)
        and not list_root(artifact_fd),
        "image_custody",
    )
    manifest = {
        "schema_version": "dspx-image-input-manifest-v2",
        "source_package_sha256": record["source_package_sha256"],
        "admission_sha256": admission.sha256,
        "marker_entries": prepared["markers"],
    }
    initialize = parent_initializer(
        custody_fd,
        authority,
        admission,
        source_sha256=record["source_package_sha256"],
        manifest_sha256=digest("manifest-v2", manifest),
    )
    observed = () if fixture.observation_fd is None else (fixture.observation_fd,)
    params: dict[str, object] = {
        "candidate_fd": candidate_fd,
        "input_fd": input_fd,
        "input_name": input_name,
        "artifact_fd": artifact_fd,
        "custody_fd": custody_fd,
        "preparation": preparation.raw.decode("ascii"),
        "admission": admission.raw.decode("ascii"),
        "authority": {
            "caller_expectation_sha256": authority.caller_expectation_sha256,
            "root_dev": authority.root_dev,
            "root_ino": authority.root_ino,
        },
        "fixture": fixture.record,
        "route": route,
    }
    result = supervise_image_worker(
        "dspx.image_execution:_execute_entry",
        params,
        fds=(candidate_fd, input_fd, artifact_fd, custody_fd, *observed),
        wall_ms=record["deadlines"]["total_wall_ms"],
        parent_action=initialize,
    )
    require(result["status"] == "completed", "image_custody")
    anchor = ImageRunAnchor(
        custody_fd,
        artifact_fd,
        cast(str, result["commitment_sha256"]),
        admission.raw,
        canonical(prepared["source"]),
        canonical(manifest),
        prepared["output_slots"],
    )
    verify_image_run(anchor)
    return anchor


_EXECUTION = "candidate_fd input_fd input_name artifact_fd custody_fd preparation admission authority fixture route"


@worker_entry
def _execute_entry(params: dict[str, object]) -> dict[str, object]:
    from .image_artifacts import publish_image_run
    from .provider_registry import create_image_lm

    row = closed(params, _EXECUTION)
    preparation = ImagePreparation(row["preparation"].encode("ascii"))
    admission_raw = row["admission"].encode("ascii")
    admission = ImageAdmission(
        admission_raw, digest("admission-v2", parse_json(admission_raw, limit=65_536))
    )
    bound = closed(row["authority"], "caller_expectation_sha256 root_dev root_ino")
    # Worker-local mirror of the parent's reserved nominal authority. It is usable
    # only through the parent handshake, which checks ready.json independently.
    authority = SyntheticImageAuthority(
        admission_raw,
        bound["caller_expectation_sha256"],
        bound["root_dev"],
        bound["root_ino"],
        _used=[False],
    )
    fixture = closed(row["fixture"], "completion observation_fd")
    prepared = preparation.record
    record = admission.record
    custody_fd, artifact_fd = row["custody_fd"], row["artifact_fd"]
    with image_privacy() as active:
        root, context, rederived = _prepare(
            active,
            candidate_fd=row["candidate_fd"],
            input_fd=row["input_fd"],
            input_name=row["input_name"],
            model=record["model"],
            use_cot=cast(bool, prepared["use_cot"]),
            limits=record["limits"],
        )
        require(canonical(rederived) == preparation.raw, "image_admission_invalid")
        session = ImageCustodySession(
            root_fd=custody_fd,
            admission=admission,
            authority=authority,
            context=context,
        )
        active.session = session
        lm = create_image_lm(
            session, transport=fixture_transport(fixture, record["model"])
        )
        active.lm = lm
        with dspy.context(lm=lm):
            prediction = root(**context.materialized())
        require(type(prediction) is dspy.Prediction, "image_finalization")
        values = prediction.toDict()
        reject_output(values, context)
        profile = cast(ImageSourceProfile, active.profile)
        require(set(profile.snapshot.outputs) <= set(values), "image_finalization")
        outputs = {name: values[name] for name in profile.snapshot.outputs}
        active.check()
        binding = publish_image_run(
            session, artifact_fd=artifact_fd, outputs=outputs, route=row["route"]
        )
        session.close_run(binding, outcome="completed")
        return _status("completed", sha(read_record(custody_fd, "closure.json")))


def run_image_episode(
    image_execution: object,
    *,
    manifest_path: Path,
    inputs_path: Path,
    outdir: Path,
    capture_replay_fixture: bool,
    plain: bool,
) -> dict[str, object]:
    """Episode route: bind caller paths to the held fds, then the shared execution."""
    from .image_artifacts import verify_image_run
    from .image_source_io import open_root

    if capture_replay_fixture:
        raise ImageContractError("image_replay_unsupported") from None
    require(
        type(image_execution) is ImageExecutionRequest and plain is True,
        "image_admission_invalid",
    )
    request = cast(ImageExecutionRequest, image_execution)
    for path, expected in (
        (manifest_path.absolute().parent, request.candidate_fd),
        (inputs_path.absolute().parent, request.input_fd),
        (outdir.absolute(), request.artifact_fd),
    ):
        fd = open_root(path)
        try:
            actual, bound = os.fstat(fd), os.fstat(expected)
            require(
                (actual.st_dev, actual.st_ino) == (bound.st_dev, bound.st_ino),
                "image_custody",
            )
        finally:
            os.close(fd)
    require(
        manifest_path.name == "manifest.json"
        and inputs_path.name == request.input_name,
        "image_custody",
    )
    anchor = request.execute(route="episode")
    return {**verify_image_run(anchor), "image_anchor": anchor}

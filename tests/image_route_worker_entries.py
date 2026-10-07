# summary: "Clean-worker test entries for the shipped image routes: prepare-only counters and envelope parity."
# read_when:
#   - "Changing the image prepare entry, the shared source membrane, or AK6756 S15/S25 proofs."

"""Declared test entries that run ONLY inside the clean `-I -S` image worker.

The pytest parent names them by string and reads only the counter names; importing
this module patches nothing. Counting wrappers around the DSPy SDK must exist before
`dspx.image_privacy` snapshots its method table, so the entry installs them first and
the production privacy checks still see one consistent table. Every wrapper calls
through; nothing is replaced.
"""

from __future__ import annotations

import functools
import sys

from dspx.image_admission import digest
from dspx.image_worker import worker_entry

SDK_COUNTERS = ("module_call", "predict_call", "predict_forward", "lm_init", "lm_call")
EFFECT_COUNTERS = (
    "provider_init",
    "stub_init",
    "image_lm_factory",
    "http_client",
    "http_send",
    "custody_session",
    "live_authority",
    "ready_publication",
)


def _counted(owner: type, name: str, label: str, counts: dict[str, int]) -> None:
    original = vars(owner)[name]

    @functools.wraps(original)
    def counted(*args, **kwargs):
        counts[label] += 1
        return original(*args, **kwargs)

    counts[label] = 0
    setattr(owner, name, counted)


@worker_entry
def counted_prepare_entry(params: dict[str, object]) -> dict[str, object]:
    """The exact production prepare entry, with invocation counters around it."""
    assert "dspx.image_privacy" not in sys.modules  # table not yet snapshotted
    import dspy

    counts: dict[str, int] = {}
    for owner, name, label in zip(
        (dspy.Module, dspy.Predict, dspy.Predict, dspy.BaseLM, dspy.BaseLM),
        ("__call__", "__call__", "forward", "__init__", "__call__"),
        SDK_COUNTERS,
        strict=True,
    ):
        _counted(owner, name, label, counts)
    import httpx

    from dspx import image_admission, image_custody, image_execution
    from dspx import image_supervision, provider_registry
    from dspx.openai_compatible_provider import OpenAICompatibleProvider
    from dspx.stub_provider import StubProvider

    for owner, name, label in zip(
        (
            OpenAICompatibleProvider,
            StubProvider,
            httpx.Client,
            httpx.Client,
            image_custody.ImageCustodySession,
            image_admission.LiveImageAuthority,
        ),
        ("__init__", "__init__", "__init__", "send", "__init__", "__init__"),
        ("provider_init", "stub_init", "http_client", "http_send")
        + ("custody_session", "live_authority"),
        strict=True,
    ):
        _counted(owner, name, label, counts)
    factory = provider_registry.create_image_lm
    counts["image_lm_factory"] = 0

    def counted_factory(*args, **kwargs):
        counts["image_lm_factory"] += 1
        return factory(*args, **kwargs)

    setattr(provider_registry, "create_image_lm", counted_factory)
    status = image_execution._prepare_entry(params)
    counts["ready_publication"] = int(
        getattr(image_supervision._LOCAL, "ready_sent", False)
    )
    assert set(counts) == set(SDK_COUNTERS + EFFECT_COUNTERS)
    observed = dict(counts)
    # Positive control after the snapshot: the wrappers privacy checked are live.
    try:
        dspy.Predict("question -> answer")(question="control")
    except Exception:
        pass  # no LM is configured; only the counted entry path matters
    assert counts["module_call"] > observed["module_call"]
    assert counts["predict_call"] > observed["predict_call"]
    counts = observed
    return {
        **status,
        "commitment_sha256": digest(
            "prepare-counters-v1",
            {"production": status["commitment_sha256"], "counts": counts},
        ),
    }


@worker_entry
def envelope_parity_entry(params: dict[str, object]) -> dict[str, object]:
    """One production membrane for a DesignMD envelope and an equivalent descriptor."""
    import base64

    from dspx.image_admission import ImageContractError
    from dspx.image_decoder import FrozenImageDecoder
    from dspx.image_input_contract import ImageOccurrence, materialize_image_inputs
    from dspx.image_privacy import image_privacy
    from dspx.image_source_io import read_relative

    root = params["root_fd"]
    assert type(root) is int
    observed: dict[str, object] = {}
    with image_privacy():
        contexts = {}
        for name, field in (
            ("descriptor", "visual"),
            ("envelope", "visual_image_inputs_json"),
        ):
            contexts[name] = materialize_image_inputs(
                read_relative(root, name + ".json", limit=1 << 20),
                root_fd=root,
                fields=(field,),
                candidate_manifest_sha256="1" * 64,
                candidate_source_sha256="2" * 64,
                decoder=FrozenImageDecoder(),
            )
        descriptor, envelope = contexts["descriptor"], contexts["envelope"]
        text = envelope.values[0]
        assert type(text) is str
        (item,) = envelope.occurrences
        encoded = base64.b64encode(item.data).decode("ascii")
        parts = envelope.split(text, slot=0)
        observed["parity"] = [
            descriptor.source["decoder_profile_sha256"]
            == envelope.source["decoder_profile_sha256"],
            descriptor.source["source_occurrences"]
            == envelope.source["source_occurrences"],
            descriptor.manifest("0" * 64)["marker_entries"]
            == envelope.manifest("0" * 64)["marker_entries"],
        ]
        observed["envelope_text"] = {
            "reserved_keys_left": [
                key
                for key in (
                    "imageDataBase64",
                    "imageDataMimeType",
                    "pixelInspectionInputStatus",
                    "available_bounded_inline_image_payload",
                )
                if key in text
            ],
            "payload_copies": text.count(encoded),
            "marker_copies": text.count(item.marker),
            "parts": [
                "image" if type(part) is ImageOccurrence else "text" for part in parts
            ],
        }
        refusals = []
        for name in params["malformed"]:  # type: ignore[union-attr]
            try:
                materialize_image_inputs(
                    read_relative(root, name, limit=1 << 20),
                    root_fd=root,
                    fields=("visual_image_inputs_json",),
                    candidate_manifest_sha256="1" * 64,
                    candidate_source_sha256="2" * 64,
                    decoder=FrozenImageDecoder(),
                )
            except ImageContractError as error:
                refusals.append(error.code)
            else:
                refusals.append(None)
        observed["malformed"] = refusals
    return {
        "status": "prepared",
        "commitment_sha256": digest("envelope-parity-v1", observed),
        "fixture_evidence": True,
        "live_authorized": False,
        "failure_code": None,
    }

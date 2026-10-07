# summary: "Tests direct-run template support for DesignMD visual image input materialization."
# read_when:
#   - "Changing generated direct-run image adapters or missing-image preflight behavior."

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Callable

import httpx
import pytest
from typer.testing import CliRunner

import dspx.cli.dspx as cli
from dspx.image_admission import digest, parse_json, sha
from dspx.image_records import list_root
from dspx.openai_compatible_provider import OpenAICompatibleProvider
from dspx.stub_provider import StubProvider
from dspx.services import program_service
from dspx.services.program_runtime_episode import run_program_runtime_episode
from test_image_execution import (
    _ENVELOPE_DEFECTS,
    _PRIVATE_ROOTS,
    _RefusalPoison,
    _envelope,
    _generated_runner,
    _payload_free,
    _png,
    _prepare_route,
    _route_fds,
    _run_shipped_route,
    _shipped_inputs,
    _single_field_inputs,
)


def test_production_direct_runner_denies_unadmitted_image_before_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import builtins
    import importlib.util
    import dspy
    from dspx.image_admission import ImageContractError
    from dspx.services.program_intent import ProgramIntent

    candidate = tmp_path / "candidate"
    program_service.materialize_program_from_intent(
        ProgramIntent(
            name="DirectDenial",
            objective="Inspect synthetic inputs.",
            inputs=["visual"],
            outputs=["answer"],
            options={"image_enabled": True},
        ),
        outdir=candidate,
    )
    spec = importlib.util.spec_from_file_location(
        "actual_direct_denial", candidate / "direct_run.py"
    )
    assert spec is not None and spec.loader is not None
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    path = tmp_path / "inputs.json"
    path.write_text(
        json.dumps(
            {
                "visual": {
                    "type": "image_base64",
                    "media_type": "image/png",
                    "data": "QUJD",
                }
            }
        )
    )
    output = tmp_path / "outputs"
    entries = []
    imports = []
    original = builtins.__import__

    def observe_import(name, *args, **kwargs):
        if name in {"program", "module", "signature"}:
            imports.append(name)
        return original(name, *args, **kwargs)

    def forbidden(*args, **kwargs):
        entries.append(True)
        raise AssertionError("unadmitted image boundary crossed")

    monkeypatch.setattr(builtins, "__import__", observe_import)
    monkeypatch.setattr(dspy.Image, "format", forbidden)
    monkeypatch.setattr(StubProvider, "invoke", forbidden)
    monkeypatch.setattr(OpenAICompatibleProvider, "invoke", forbidden)
    monkeypatch.setattr(httpx.Client, "__init__", forbidden)
    with pytest.raises(ImageContractError, match="image_generation_inputs_unsupported"):
        runner._single_run(path, output)
    assert not imports and not entries and not output.exists()


@pytest.fixture
def no_provider_effects(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    entered: list[bool] = []

    def deny(*args, **kwargs):
        entered.append(True)
        raise AssertionError("provider effects forbidden in ingress falsifier")

    monkeypatch.setattr(StubProvider, "invoke", deny)
    monkeypatch.setattr(OpenAICompatibleProvider, "invoke", deny)
    monkeypatch.setattr(httpx.Client, "send", deny)
    return entered


def _image_intent(examples_name: str) -> dict[str, object]:
    return {
        "objective": "Inspect explicitly supplied visual inputs.",
        "inputs": ["visual_image_inputs_json"],
        "outputs": ["assessment"],
        "examples_path": examples_name,
    }


def test_image_examples_path_refuses_read_before_first_renderer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    record_property: Callable[[str, object], None],
    no_provider_effects: list[bool],
) -> None:
    """Given image examples_path; When real loading runs; Then no example read.

    Inject the strongest proposed scoped renderer refusal, not a replacement loader.
    Real Path.read_text and load_program_intent still execute. The fixture contains
    only synthetic data; no image decoder, generated runtime or provider executes.
    """
    examples = tmp_path / "examples.json"
    examples.write_text(
        json.dumps(
            [
                {
                    "visual_image_inputs_json": {
                        "images": [
                            {
                                "imageDataBase64": "QUJD" * 40,
                                "imageDataMimeType": "image/png",
                                "pixelInspectionInputStatus": (
                                    "available_bounded_inline_image_payload"
                                ),
                            }
                        ]
                    }
                }
            ]
        ),
        encoding="utf-8",
    )
    intent = tmp_path / "intent.json"
    intent.write_text(json.dumps(_image_intent(examples.name)), encoding="utf-8")
    reads: list[bool] = []
    renderer_calls: list[bool] = []
    original_read = Path.read_text
    original_fd_read = os.read
    example_identity = examples.stat()

    def fd_read_spy(fd: int, count: int) -> bytes:
        current = os.fstat(fd)
        if (current.st_dev, current.st_ino) == (
            example_identity.st_dev,
            example_identity.st_ino,
        ):
            reads.append(True)
        return original_fd_read(fd, count)

    def read_spy(path: Path, *args, **kwargs) -> str:
        if path == examples:
            reads.append(True)
        return original_read(path, *args, **kwargs)

    def renderer_refusal(*args, **kwargs):
        renderer_calls.append(True)
        raise ValueError("image_generation_inputs_unsupported")

    monkeypatch.setattr(Path, "read_text", read_spy)
    monkeypatch.setattr(os, "read", fd_read_spy)
    monkeypatch.setattr(program_service, "render_signature_surface", renderer_refusal)
    candidate = tmp_path / "candidate"
    with pytest.raises(ValueError, match="^image_generation_inputs_unsupported$"):
        program_service.run_generate_from_intent_path(intent, outdir=candidate)
    record_property("example_reads_before_refusal", len(reads))
    record_property("renderer_refusals", len(renderer_calls))
    record_property("candidate_retained", candidate.exists())
    record_property("provider_or_send_entries", len(no_provider_effects))
    assert not no_provider_effects
    assert not renderer_calls
    assert not candidate.exists()
    # Falsifier: a renderer-only repair cannot meet bounded pre-ingress refusal.
    assert not reads, "image examples were read before the scoped refusal"


def test_malformed_image_examples_never_echo_payload_before_renderer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    record_property: Callable[[str, object], None],
    no_provider_effects: list[bool],
) -> None:
    """Given malformed image examples; When real CLI runs; Then fixed safe error.

    Observe actual Typer output, not exception repr. Keep only booleans in pytest
    diagnostics/JUnit; never print the deliberately echo-prone captured output.
    Config/tracing setup is excluded to avoid ambient host configuration effects.
    This exclusion does not replace the real loader or CLI exception rendering.
    """
    examples = tmp_path / "examples.yaml"
    data_uri = "data:image/png;base64," + "QUJD" * 40
    examples.write_text("[" + data_uri + "\n", encoding="utf-8")
    intent = tmp_path / "intent.json"
    intent.write_text(json.dumps(_image_intent(examples.name)), encoding="utf-8")
    renderer_calls: list[bool] = []

    def renderer_refusal(*args, **kwargs):
        renderer_calls.append(True)
        raise ValueError("image_generation_inputs_unsupported")

    monkeypatch.setattr(cli, "ensure_env", lambda *args, **kwargs: None)
    monkeypatch.setattr(program_service, "render_signature_surface", renderer_refusal)
    result = CliRunner().invoke(
        cli.app,
        [
            "program-gen",
            "--intent",
            str(intent),
            "--outdir",
            str(tmp_path / "candidate"),
        ],
    )
    uri_echoed = "data:image/png;base64," in result.output
    payload_echoed = "QUJDQUJD" in result.output
    path_echoed = str(examples) in result.output
    record_property("exit_code", result.exit_code)
    record_property("renderer_refusals", len(renderer_calls))
    record_property("data_uri_echoed", uri_echoed)
    record_property("base64_fragment_echoed", payload_echoed)
    record_property("absolute_example_path_echoed", path_echoed)
    record_property("provider_or_send_entries", len(no_provider_effects))
    assert not no_provider_effects
    assert result.exit_code == 2
    assert not renderer_calls
    assert not uri_echoed, "pre-render CLI error echoed an image data URI"
    assert not payload_echoed, "pre-render CLI error echoed image base64"
    assert not path_echoed, "pre-render CLI error echoed an absolute source path"


def test_legitimate_text_yaml_aliases_and_finite_numbers_survive_ingress(
    tmp_path: Path,
) -> None:
    from dspx.services.program_intent import load_program_intent

    source = tmp_path / "text.yaml"
    source.write_text(
        "objective: Classify ordinary text.\n"
        "inputs: [ticket_text]\noutputs: [urgency]\n"
        "options:\n  threshold: 0.75\n  labels: &labels [low, high]\n"
        "  copied_labels: *labels\n",
        encoding="utf-8",
    )
    loaded = load_program_intent(source)
    assert loaded.options["threshold"] == 0.75
    assert (
        loaded.options["labels"] == loaded.options["copied_labels"] == ["low", "high"]
    )


def test_image_loader_exception_has_no_payload_context_chain(tmp_path: Path) -> None:
    from dspx.image_admission import ImageContractError
    from dspx.services.program_intent import load_program_intent

    source = tmp_path / "intent.yaml"
    source.write_text("objective: [data:image/png;base64,QUJDQUJD\n", encoding="utf-8")
    with pytest.raises(ImageContractError) as failure:
        load_program_intent(source)
    assert str(failure.value) == "image_generation_inputs_unsupported"
    assert failure.value.__cause__ is None
    assert failure.value.__context__ is None


@pytest.mark.parametrize("suffix", ["json", "yaml"])
@pytest.mark.parametrize("role", ["inputs", "outputs"])
def test_ordinary_identifier_error_is_useful_without_payload_or_context(
    tmp_path: Path,
    suffix: str,
    role: str,
    no_provider_effects: list[bool],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Given invalid text IO; When loader/CLI runs; Then a safe useful diagnostic."""
    from dspx.services.program_intent import load_program_intent

    private_field = "private-field-token-123456"
    payload = {"objective": "Classify text", "inputs": ["text"], "outputs": ["answer"]}
    payload[role] = [private_field]
    source = tmp_path / f"intent.{suffix}"
    if suffix == "json":
        source.write_text(json.dumps(payload), encoding="utf-8")
    else:
        import yaml

        source.write_text(yaml.safe_dump(payload), encoding="utf-8")
    render_entries: list[bool] = []

    def forbidden_renderer(*args, **kwargs):
        render_entries.append(True)
        raise AssertionError("invalid intent reached renderer")

    monkeypatch.setattr(program_service, "render_signature_surface", forbidden_renderer)
    with pytest.raises(ValueError) as failure:
        load_program_intent(source)
    assert (
        str(failure.value) == "program intent fields must be valid Python identifiers"
    )
    assert failure.value.__cause__ is None and failure.value.__context__ is None
    candidate = tmp_path / "candidate"
    result = CliRunner().invoke(
        cli.app, ["program-gen", "--intent", str(source), "--outdir", str(candidate)]
    )
    assert result.exit_code == 2
    assert "valid Python identifiers" in result.output
    assert private_field not in result.output and str(source) not in result.output
    assert not candidate.exists() and not render_entries and not no_provider_effects


@pytest.mark.parametrize("shape", ["namespace", "foreign_model", "mapping"])
def test_every_data_bearing_intent_shape_reaches_the_image_preflight(
    shape: str,
) -> None:
    """Only data-less stand-ins are text-only; any intent carrying data is preflighted."""
    from types import SimpleNamespace

    from pydantic import BaseModel

    from dspx.image_admission import ImageContractError
    from dspx.image_input_contract import generation_intent_preflight
    from dspx.image_source_io import image_generation_profile

    image = {"type": "image_base64", "media_type": "image/png", "data": "AAAA"}

    class Foreign(BaseModel):
        examples: list[dict[str, str]]

    intent: object = {
        "namespace": SimpleNamespace(examples=[image]),
        "foreign_model": Foreign(examples=[image]),
        "mapping": {"examples": [image]},
    }[shape]
    for check in (generation_intent_preflight, image_generation_profile):
        with pytest.raises(ImageContractError):
            check(intent)
    assert image_generation_profile(object()) is False
    generation_intent_preflight(object())


# AK6756 S15: generated-run and episode materializers share one membrane.
def test_s15_designmd_envelope_and_descriptor_share_one_membrane_in_both_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """S15: equivalent envelope and descriptor inputs yield identical commitments."""
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_POLICY_ALLOW_NETWORK_MUTATE", "1")
    pixels = _png()
    descriptor = {
        "type": "image_base64",
        "media_type": "image/png",
        "data": base64.b64encode(pixels).decode("ascii"),
    }
    _single_field_inputs(tmp_path / "descriptor", "visual", descriptor)
    with _route_fds(tmp_path / "descriptor") as fds:
        expected = parse_json(_prepare_route(fds, use_cot=False).raw)
    for route in ("episode", "direct"):
        root = tmp_path / route
        _single_field_inputs(root, "visual_image_inputs_json", _envelope(pixels))
        run = _run_shipped_route(root, media="image/png", use_cot=False, route=route)
        assert run.verified["status"] == "ok" and run.verified["spent"] is True
        # One send, the envelope image exactly once as an image block, never as text.
        assert [
            (row["image_sha256"], row["message_block_kinds"]) for row in run.wire
        ] == [([sha(pixels)], [["text"], ["text", "image_url", "text"]])]
        artifacts = root / "artifacts"
        source = parse_json((artifacts / "image_source_package.json").read_bytes())
        manifest = parse_json((artifacts / "image_input_manifest.json").read_bytes())
        assert (
            source["decoder_profile_sha256"]
            == expected["source"]["decoder_profile_sha256"]
        )
        assert source["source_occurrences"] == expected["source"]["source_occurrences"]
        assert manifest["marker_entries"] == expected["markers"]
        assert _payload_free([root / name for name in _PRIVATE_ROOTS], pixels) == []


def test_s15_envelope_materializer_parity_inside_the_clean_worker(tmp_path: Path):
    """S15: the production membrane, run in the worker, drops the raw envelope field."""
    from dspx.image_source_io import open_root
    from dspx.image_supervision import supervise_image_worker

    pixels = _png()
    root = tmp_path / "parity"
    root.mkdir(mode=0o700)
    descriptor = {
        "type": "image_base64",
        "media_type": "image/png",
        "data": base64.b64encode(pixels).decode("ascii"),
    }
    (root / "descriptor.json").write_text(json.dumps({"visual": descriptor}))
    (root / "envelope.json").write_text(
        json.dumps({"visual_image_inputs_json": _envelope(pixels)})
    )
    malformed = []
    for kind, override in sorted(_ENVELOPE_DEFECTS.items()):
        malformed.append(f"malformed-{kind}.json")
        (root / malformed[-1]).write_text(
            json.dumps({"visual_image_inputs_json": _envelope(pixels, **override)})
        )
    fd = open_root(root)
    try:
        status = supervise_image_worker(
            "image_route_worker_entries:envelope_parity_entry",
            {"root_fd": fd, "malformed": malformed},
            fds=(fd,),
            wall_ms=30_000,
        )
    finally:
        os.close(fd)
    observed = {
        "parity": [True, True, True],
        "envelope_text": {
            "reserved_keys_left": [],
            "payload_copies": 1,  # only inside the one source-issued marker
            "marker_copies": 1,
            "parts": ["text", "image"],
        },
        "malformed": ["image_input_invalid"] * len(malformed),
    }
    assert status == {
        "status": "prepared",
        "commitment_sha256": digest("envelope-parity-v1", observed),
        "fixture_evidence": True,
        "live_authorized": False,
        "failure_code": None,
    }


@pytest.mark.parametrize("kind", sorted(_ENVELOPE_DEFECTS))
@pytest.mark.parametrize("path", ["library-prepare", "generated-prepare"])
def test_s15_malformed_envelope_rejects_in_both_preparation_paths(
    tmp_path: Path, kind: str, path: str
):
    from dspx.image_admission import ImageContractError

    _single_field_inputs(
        tmp_path,
        "visual_image_inputs_json",
        _envelope(_png(), **_ENVELOPE_DEFECTS[kind]),
    )
    with _route_fds(tmp_path) as fds:
        with pytest.raises(ImageContractError) as caught:
            if path == "library-prepare":
                _prepare_route(fds, use_cot=False)
            else:
                _generated_runner(tmp_path).prepare_image(
                    candidate_fd=fds["candidate"],
                    input_fd=fds["inputs"],
                    input_name="inputs.json",
                    preparation_fd=fds["preparation"],
                    model="synthetic-vision-fixture",
                )
        assert caught.value.code == "image_input_invalid"
        assert caught.value.__cause__ is None and caught.value.__suppress_context__
        assert [list_root(fds[name]) for name in _PRIVATE_ROOTS] == [[]] * 4


@pytest.mark.parametrize("entry", ["episode", "generated-prepare", "generated-run"])
def test_s15_missing_image_helper_import_never_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, entry: str
):
    """S15: without the shared helper there is no old materialization fallback."""
    import sys

    from dspx.services import program_runtime_episode as episode

    _shipped_inputs(tmp_path, media="image/png")
    runner = _generated_runner(tmp_path)
    entries: list[str] = []

    def forbidden(*args: object, **kwargs: object) -> None:
        entries.append("fallback")
        raise AssertionError("missing helper fell back to old materialization")

    for owner, names in (
        (
            episode,
            (
                "_load_inputs",
                "_materialize_runtime_inputs",
                "_generated_program_module",
                "_configure_provider",
            ),
        ),
        (runner, ("_load_inputs", "_single_run")),
    ):
        for name in names:
            monkeypatch.setattr(owner, name, forbidden)
    monkeypatch.setitem(sys.modules, "dspx.image_execution", None)
    poison = _RefusalPoison()
    calls = {
        "episode": lambda: run_program_runtime_episode(
            manifest_path=tmp_path / "candidate" / "manifest.json",
            inputs_path=tmp_path / "inputs" / "inputs.json",
            outdir=tmp_path / "artifacts",
            image_execution=poison,
        ),
        "generated-prepare": lambda: runner.prepare_image(candidate_fd=poison),
        "generated-run": lambda: runner.run_image(candidate_fd=poison),
    }
    with pytest.raises(ImportError):
        calls[entry]()
    assert entries == []
    assert [sorted((tmp_path / name).iterdir()) for name in _PRIVATE_ROOTS] == [[]] * 4


# AK6756 S50: image generation inputs are refused before raw payload persistence.
_GENERATION_PAYLOADS: dict[str, dict[str, object]] = {
    "inline-examples": {
        "examples": [{"visual": "plain synthetic text", "answer": "ok"}]
    },
    "inline-image-example": {
        "examples": [
            {
                "visual": {
                    "type": "image_base64",
                    "media_type": "image/png",
                    "data": "QUJD",
                },
                "answer": "ok",
            }
        ]
    },
    "dataset": {"dataset": {"train": [{"visual": "x", "answer": "y"}]}},
    "datasets": {"datasets": {"train": {"path": "train.jsonl"}}},
    "examples-path": {"examples_path": "examples.json"},
    "reserved-key": {"options": {"image_enabled": True, "imageDataBase64": "QUJD"}},
    "reserved-marker-text": {"constraints": ["<<CUSTOM-TYPE-START-IDENTIFIER>>"]},
}
_GUARDED_RENDERERS = (
    "render_signature_surface",
    "render_module_surface",
    "render_program_code",
    "render_direct_run_code",
    "render_eval_smoke",
    "render_eval_examples",
    "render_eval_behavior",
)


def _image_generation_intent(payload: str):
    from dspx.services.program_intent import ProgramIntent

    fields: dict[str, object] = {"options": {"image_enabled": True}}
    fields.update(_GENERATION_PAYLOADS[payload])
    return ProgramIntent(
        objective="Describe bounded synthetic pixels.",
        inputs=["visual"],
        outputs=["answer"],
        **fields,  # type: ignore[arg-type]
    )


def _effect_spies(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    """Every file write, created directory and tree removal, at the real call sites."""
    import builtins
    import io
    import shutil

    effects: dict[str, list[str]] = {"writes": [], "mkdirs": [], "removals": []}
    real_os_open, passthrough = os.open, {"open": io.open}
    real_os_mkdir, real_rmtree = os.mkdir, shutil.rmtree
    write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC

    def os_open_spy(path, flags, *args, **kwargs):
        if flags & write_flags:
            effects["writes"].append(os.fspath(path))
        return real_os_open(path, flags, *args, **kwargs)

    def open_spy(file, mode="r", *args, **kwargs):
        if set(str(mode)) & set("wax+"):
            effects["writes"].append(str(file))
        return passthrough["open"](file, mode, *args, **kwargs)  # caller closes it

    def os_mkdir_spy(path, *args, **kwargs):  # Path.mkdir lands here too
        real_os_mkdir(path, *args, **kwargs)
        effects["mkdirs"].append(os.fspath(path))  # only directories actually created

    def rmtree_spy(path, *args, **kwargs):
        effects["removals"].append(os.fspath(path))
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", os_open_spy)
    monkeypatch.setattr(io, "open", open_spy)
    monkeypatch.setattr(builtins, "open", open_spy)
    monkeypatch.setattr(os, "mkdir", os_mkdir_spy)
    monkeypatch.setattr(shutil, "rmtree", rmtree_spy)
    return effects


@pytest.mark.parametrize("payload", sorted(_GENERATION_PAYLOADS))
def test_s50_whole_materialization_refuses_before_any_surface_or_harness_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    no_provider_effects: list[bool],
    payload: str,
) -> None:
    from dspx.image_admission import ImageContractError

    intent = _image_generation_intent(payload)
    downstream: list[str] = []

    def forbidden(label: str) -> Callable[..., object]:
        def refuse(*args: object, **kwargs: object) -> object:
            downstream.append(label)
            raise AssertionError("image generation reached " + label)

        return refuse

    for name in (*_GUARDED_RENDERERS, "resolve_program_retriever_snapshots"):
        monkeypatch.setattr(program_service, name, forbidden(name))
    candidate = tmp_path / "candidate"
    effects = _effect_spies(monkeypatch)
    with pytest.raises(ImageContractError) as caught:
        program_service.materialize_program_from_intent(intent, outdir=candidate)
    assert str(caught.value) == "image_generation_inputs_unsupported"
    assert caught.value.__cause__ is None and caught.value.__suppress_context__
    # Pre-render effects are accounted for, not reported as zero: the empty candidate
    # root was created and then removed; nothing was written; no retriever resolved.
    root = str(candidate.resolve())
    assert effects == {"writes": [], "mkdirs": [root], "removals": [root]}
    assert downstream == [] and no_provider_effects == []
    assert not candidate.exists() and list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("payload", sorted(_GENERATION_PAYLOADS))
@pytest.mark.parametrize("renderer", _GUARDED_RENDERERS)
def test_s50_direct_renderer_guard_refuses_with_no_writes_or_generation(
    monkeypatch: pytest.MonkeyPatch,
    no_provider_effects: list[bool],
    payload: str,
    renderer: str,
) -> None:
    from dspx import image_source_io, image_source_profile
    from dspx.image_admission import ImageContractError
    from dspx.services import module_service, program_surfaces, signatures_service

    intent = _image_generation_intent(payload)
    downstream: list[str] = []
    for owner, name in (
        (signatures_service, "run_generate_dto"),
        (module_service, "run_generate"),
        (image_source_io, "image_surface_sources"),
        (image_source_profile, "image_program_code"),
    ):

        def refuse(*args: object, _name: str = name, **kwargs: object) -> object:
            downstream.append(_name)
            raise AssertionError("renderer started generation: " + _name)

        monkeypatch.setattr(owner, name, refuse)
    effects = _effect_spies(monkeypatch)
    with pytest.raises(ImageContractError) as caught:
        getattr(program_surfaces, renderer)(intent)
    assert str(caught.value) == "image_generation_inputs_unsupported"
    assert effects == {"writes": [], "mkdirs": [], "removals": []}
    assert downstream == [] and no_provider_effects == []

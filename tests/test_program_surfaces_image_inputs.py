# summary: "Tests direct-run template support for DesignMD visual image input materialization."
# read_when:
#   - "Changing generated direct-run image adapters or missing-image preflight behavior."

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable

import httpx
import pytest
from typer.testing import CliRunner

import dspx.cli.dspx as cli
from dspx.openai_compatible_provider import OpenAICompatibleProvider
from dspx.stub_provider import StubProvider
from dspx.services import program_service


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

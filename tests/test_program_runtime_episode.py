from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.coordinates import CoordinateIndex, reset_embedding_engine
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_runtime_episode import (
    _generated_program_module,
    _materialize_runtime_inputs,
    run_program_runtime_episode,
)
from dspx.services.program_service import (
    materialize_program_from_intent,
    run_generate_from_intent_path,
)

runner = CliRunner()


def _write_intent(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "name: TicketProgram",
                "objective: Classify support ticket urgency.",
                "inputs:",
                "  - ticket_text",
                "outputs:",
                "  - urgency",
                "metric: exact_match",
                "constraints:",
                "  - use only the supplied ticket text",
                "examples:",
                "  - inputs:",
                "      ticket_text: Server is down for all users",
                "    outputs:",
                "      urgency: high",
            ]
        ),
        encoding="utf-8",
    )


def _env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    reset_embedding_engine()


def _generated_candidate(tmp_path: Path) -> Path:
    intent = tmp_path / "intent.yaml"
    outdir = tmp_path / "candidate"
    _write_intent(intent)
    run_generate_from_intent_path(intent, outdir=outdir)
    return outdir


def _explicit_pipeline_candidate(tmp_path: Path) -> Path:
    artifact = materialize_program_from_intent(
        ProgramIntent(
            name="SupportRouterProgram",
            objective="Route support tickets and draft a response.",
            inputs=["ticket_text"],
            outputs=["response"],
            metric="exact_match",
            constraints=["preserve the original ticket facts"],
            topology={
                "kind": "pipeline",
                "execution_status": "declared_not_materialized",
                "modules": [
                    {
                        "id": "classify_ticket",
                        "primitive": "Predict",
                        "signature": {
                            "name": "ClassifyTicket",
                            "inputs": ["ticket_text"],
                            "outputs": ["route"],
                        },
                    },
                    {
                        "id": "draft_response",
                        "primitive": "chain_of_thought",
                        "signature": {
                            "name": "DraftResponse",
                            "inputs": ["ticket_text", "route"],
                            "outputs": ["response"],
                        },
                    },
                ],
                "edges": [
                    {"from": "input", "to": "classify_ticket"},
                    {"from": "classify_ticket", "to": "draft_response"},
                    {"from": "draft_response", "to": "output"},
                ],
            },
            examples=[
                {
                    "inputs": {"ticket_text": "Billing invoice is wrong"},
                    "outputs": {"response": "We will help review the billing invoice."},
                }
            ],
        ),
        outdir=tmp_path / "pipeline-candidate",
    )
    return Path(artifact.root_path)


def test_program_runtime_episode_runs_existing_candidate_without_mutating_manifest(
    tmp_path: Path, monkeypatch
) -> None:
    _env(tmp_path, monkeypatch)
    candidate = _generated_candidate(tmp_path)
    source_manifest_hash = (candidate / "manifest.json").read_bytes()
    inputs = tmp_path / "runtime-inputs.json"
    inputs.write_text(
        json.dumps({"inputs": {"ticket_text": "Server is down for all users"}}),
        encoding="utf-8",
    )
    outdir = tmp_path / "runtime-episode"

    payload = run_program_runtime_episode(
        manifest_path=candidate / "manifest.json",
        inputs_path=inputs,
        outdir=outdir,
    )

    assert payload["schema_version"] == "program-runtime-episode-workflow-v1"
    assert payload["status"] == "ok"
    assert payload["effect"]["candidate_manifest_mutated"] is False
    assert payload["effect"]["shared_oracle_mutated"] is False
    assert payload["steps"]["runtime_execution"]["status"] == "executed"
    assert (candidate / "manifest.json").read_bytes() == source_manifest_hash

    behavior = json.loads((outdir / "behavior_results.json").read_text())
    assert behavior["schema_version"] == "program-behavior-results-v1"
    assert behavior["summary"]["status"] == "executed"
    assert behavior["examples"][0]["observed_outputs"]["urgency"]

    oracle_evidence = json.loads((outdir / "oracle_evidence.json").read_text())
    runtime_manifest = json.loads((outdir / "manifest.json").read_text())
    assert oracle_evidence["schema_version"] == "program-oracle-evidence-v1"
    assert (
        oracle_evidence["identity"]["candidate_id"]
        == runtime_manifest["candidate_assembly"]["candidate_id"]
    )
    assert (
        oracle_evidence["identity"]["episode_id"]
        == runtime_manifest["receipt_bundle"]["episode_id"]
    )
    assert (
        oracle_evidence["identity"]["runtime_episode_id"]
        == payload["runtime_episode_id"]
    )
    assert runtime_manifest["oracle_readability"]["path"] == "oracle_evidence.json"

    report = json.loads((outdir / "program_oracle_report.json").read_text())
    assert report["schema_version"] == "program-oracle-evidence-report-v1"
    assert report["status"] == "ok"
    assert report["total_records"] == 1
    index = CoordinateIndex(db_path=outdir / "oracle" / "coordinates.db")
    stats = index.stats()
    assert stats["total"] == 1
    assert stats["by_run_kind"]["program-oracle-evidence"] == 1
    with sqlite3.connect(outdir / "oracle" / "coordinates.db") as conn:
        run_id = conn.execute("SELECT run_id FROM coordinates").fetchone()[0]
    assert run_id == f"program-oracle-evidence:{payload['runtime_episode_id']}"


def test_program_runtime_episode_round_trips_explicit_pipeline_candidate(
    tmp_path: Path, monkeypatch
) -> None:
    _env(tmp_path, monkeypatch)
    candidate = _explicit_pipeline_candidate(tmp_path)
    inputs = tmp_path / "pipeline-runtime-inputs.json"
    inputs.write_text(
        json.dumps({"inputs": {"ticket_text": "Billing invoice is wrong"}}),
        encoding="utf-8",
    )

    payload = run_program_runtime_episode(
        manifest_path=candidate / "manifest.json",
        inputs_path=inputs,
        outdir=tmp_path / "pipeline-runtime-episode",
        skip_oracle_index=True,
    )

    assert payload["status"] == "ok"
    assert payload["steps"]["runtime_execution"]["status"] == "executed"
    behavior = json.loads(
        (tmp_path / "pipeline-runtime-episode" / "behavior_results.json").read_text(
            encoding="utf-8"
        )
    )
    assert behavior["summary"]["status"] == "executed"
    assert behavior["examples"][0]["observed_outputs"]["response"]


def test_program_runtime_episode_can_write_shared_publication_preflight(
    tmp_path: Path, monkeypatch
) -> None:
    _env(tmp_path, monkeypatch)
    candidate = _generated_candidate(tmp_path)
    inputs = tmp_path / "runtime-inputs.json"
    inputs.write_text(
        json.dumps({"ticket_text": "Server is down for all users"}), encoding="utf-8"
    )
    preflight = tmp_path / "runtime-episode" / "publication-preflight.json"

    payload = run_program_runtime_episode(
        manifest_path=candidate / "manifest.json",
        inputs_path=inputs,
        outdir=tmp_path / "runtime-episode",
        publication_preflight_out=preflight,
        publication_target="shared-postgres",
        publication_label="retained",
        publisher_id="pi-test",
        publisher_role="operator",
        publisher_assertion="share checked runtime behavior evidence for future Oracle retrieval",
        redaction_status="checked",
        retention_class="retained_behavior_memory",
    )

    assert payload["effect"]["oracle_publication_preflight_written"] is True
    packet = json.loads(preflight.read_text())
    assert packet["schema_version"] == "program-oracle-shared-publication-preflight-v1"
    assert packet["status"] == "ready_not_published"
    assert packet["preflight"]["identity_matches_manifest"] is True
    assert packet["effect"]["shared_oracle_mutated"] is False


def test_program_runtime_episode_preflight_args_fail_before_writing_artifacts(
    tmp_path: Path, monkeypatch
) -> None:
    _env(tmp_path, monkeypatch)
    candidate = _generated_candidate(tmp_path)
    inputs = tmp_path / "runtime-inputs.json"
    inputs.write_text(
        json.dumps({"ticket_text": "Server is down for all users"}), encoding="utf-8"
    )
    runtime_dir = tmp_path / "runtime-episode"

    with pytest.raises(ValueError, match="publication preflight requires"):
        run_program_runtime_episode(
            manifest_path=candidate / "manifest.json",
            inputs_path=inputs,
            outdir=runtime_dir,
            publication_preflight_out=runtime_dir / "publication-preflight.json",
        )

    assert not runtime_dir.exists()


def test_program_runtime_episode_rejects_tampered_candidate_surface(
    tmp_path: Path, monkeypatch
) -> None:
    _env(tmp_path, monkeypatch)
    candidate = _generated_candidate(tmp_path)
    program_path = candidate / "program.py"
    program_path.write_text(
        program_path.read_text(encoding="utf-8")
        + "\n# tampered after manifest write\n",
        encoding="utf-8",
    )
    inputs = tmp_path / "runtime-inputs.json"
    inputs.write_text(
        json.dumps({"inputs": {"ticket_text": "Server is down for all users"}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="program.py"):
        run_program_runtime_episode(
            manifest_path=candidate / "manifest.json",
            inputs_path=inputs,
            outdir=tmp_path / "runtime-episode",
        )


def test_generated_program_module_rejects_program_class_body_side_effects(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "marker.txt"
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "program.py").write_text(
        "from pathlib import Path\n"
        "import dspy\n"
        "class UnsafeProgram(dspy.Module):\n"
        f"    marker = Path({str(marker)!r}).touch()\n"
        "def io_spec():\n"
        "    return {'inputs': [], 'outputs': []}\n"
        "def intent_summary():\n"
        "    return {}\n"
        "def build_program():\n"
        "    return UnsafeProgram()\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="program.py"):
        with _generated_program_module(candidate):
            pass

    assert not marker.exists()


def test_generated_program_module_rejects_program_class_method_side_effects(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "marker.txt"
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "program.py").write_text(
        "from pathlib import Path\n"
        "import dspy\n"
        "class UnsafeProgram(dspy.Module):\n"
        "    def __init__(self):\n"
        f"        Path({str(marker)!r}).touch()\n"
        "def io_spec():\n"
        "    return {'inputs': [], 'outputs': []}\n"
        "def intent_summary():\n"
        "    return {}\n"
        "def build_program():\n"
        "    return UnsafeProgram()\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="touch"):
        with _generated_program_module(candidate):
            pass

    assert not marker.exists()


@pytest.mark.parametrize("method_expr", ["'touch'", "method"])
def test_generated_program_module_rejects_dynamic_lookup_side_effects(
    tmp_path: Path, method_expr: str
) -> None:
    marker = tmp_path / "marker.txt"
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "program.py").write_text(
        "from pathlib import Path\n"
        "import dspy\n"
        "def io_spec():\n"
        "    return {'inputs': [], 'outputs': []}\n"
        "def intent_summary():\n"
        "    return {}\n"
        "def build_program():\n"
        "    method = 'touch'\n"
        f"    f = getattr(Path({str(marker)!r}), {method_expr})\n"
        "    f()\n"
        "    return lambda **kwargs: {}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="getattr"):
        with _generated_program_module(candidate):
            pass

    assert not marker.exists()


def test_runtime_observed_output_files_reject_path_escape(tmp_path: Path) -> None:
    from dspx.services.program_runtime_episode import _write_observed_output_files

    outdir = tmp_path / "out"
    outdir.mkdir()

    with pytest.raises(ValueError, match="unsafe path component|escapes"):
        _write_observed_output_files(outdir, {"../escape.json": {"ok": True}})

    assert not (tmp_path / "escape.json").exists()


@pytest.mark.parametrize(
    "field_name",
    ["behavior_results.json", "nested/manifest.json", "runtime_episode.json"],
)
def test_runtime_observed_output_files_reject_protected_artifact_names(
    tmp_path: Path, field_name: str
) -> None:
    from dspx.services.program_runtime_episode import _write_observed_output_files

    outdir = tmp_path / "out"
    outdir.mkdir()

    with pytest.raises(ValueError, match="protected artifact"):
        _write_observed_output_files(outdir, {field_name: {"spoofed": True}})

    assert not (outdir / field_name).exists()


def test_generated_program_module_rejects_import_time_side_effects(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "marker.txt"
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "program.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('ran')\n"
        "def io_spec():\n"
        "    return {'inputs': [], 'outputs': []}\n"
        "def intent_summary():\n"
        "    return {}\n"
        "def build_program():\n"
        "    return lambda **kwargs: {}\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError, match="generated program surface safety policy failed"
    ):
        with _generated_program_module(candidate):
            pass

    assert not marker.exists()


def test_generated_program_module_rejects_sibling_import_time_side_effects(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "marker.txt"
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "program.py").write_text(
        "from module import io_spec\n"
        "def intent_summary():\n"
        "    return {}\n"
        "def build_program():\n"
        "    return lambda **kwargs: {}\n",
        encoding="utf-8",
    )
    (candidate / "module.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('ran')\n"
        "def io_spec():\n"
        "    return {'inputs': [], 'outputs': []}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="module.py"):
        with _generated_program_module(candidate):
            pass

    assert not marker.exists()


def test_generated_program_module_rejects_class_body_side_effects(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "marker.txt"
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "program.py").write_text(
        "from module import io_spec\n"
        "def intent_summary():\n"
        "    return {}\n"
        "def build_program():\n"
        "    return lambda **kwargs: {}\n",
        encoding="utf-8",
    )
    (candidate / "module.py").write_text(
        "from pathlib import Path\n"
        "class Unsafe:\n"
        f"    marker = Path({str(marker)!r}).touch()\n"
        "def io_spec():\n"
        "    return {'inputs': [], 'outputs': []}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="class body"):
        with _generated_program_module(candidate):
            pass

    assert not marker.exists()


def test_generated_program_module_rejects_import_time_assignment_targets(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "marker.txt"
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "program.py").write_text(
        "from module import io_spec\n"
        "def intent_summary():\n"
        "    return {}\n"
        "def build_program():\n"
        "    return lambda **kwargs: {}\n",
        encoding="utf-8",
    )
    (candidate / "module.py").write_text(
        "from pathlib import Path\n"
        "x = {}\n"
        f"x[Path({str(marker)!r}).touch()] = 1\n"
        "def io_spec():\n"
        "    return {'inputs': [], 'outputs': []}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="assignment target is not import-safe"):
        with _generated_program_module(candidate):
            pass

    assert not marker.exists()


def test_generated_program_module_rejects_import_time_header_expressions(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "marker.txt"
    cases = {
        "decorator": "@Path({marker!r}).touch()\ndef io_spec():\n    return {{'inputs': [], 'outputs': []}}\n",
        "default": "def io_spec(x=Path({marker!r}).touch()):\n    return {{'inputs': [], 'outputs': []}}\n",
        "annotation": "def io_spec(x: Path({marker!r}).touch()):\n    return {{'inputs': [], 'outputs': []}}\n",
        "string_annotation": "def io_spec(x: \"Path({marker!r}).touch()\"):\n    return {{'inputs': [], 'outputs': []}}\n",
        "base": "class Unsafe(Path({marker!r}).touch()):\n    pass\ndef io_spec():\n    return {{'inputs': [], 'outputs': []}}\n",
    }
    for name, module_template in cases.items():
        candidate = tmp_path / name
        candidate.mkdir()
        (candidate / "program.py").write_text(
            "from module import io_spec\n"
            "def intent_summary():\n"
            "    return {}\n"
            "def build_program():\n"
            "    return lambda **kwargs: {}\n",
            encoding="utf-8",
        )
        (candidate / "module.py").write_text(
            "from pathlib import Path\n" + module_template.format(marker=str(marker)),
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="import-safe|literal|class bases"):
            with _generated_program_module(candidate):
                pass

    assert not marker.exists()


def test_generated_program_module_rejects_missing_sibling_import(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "program.py").write_text(
        "from module import io_spec\n"
        "def intent_summary():\n"
        "    return {}\n"
        "def build_program():\n"
        "    return lambda **kwargs: {}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="module.py is missing"):
        with _generated_program_module(candidate):
            pass


def test_generated_program_module_rejects_sibling_package_shadowing(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "marker.txt"
    candidate = tmp_path / "candidate"
    module_dir = candidate / "module"
    module_dir.mkdir(parents=True)
    (module_dir / "__init__.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n",
        encoding="utf-8",
    )
    (candidate / "program.py").write_text(
        "from module import io_spec\n"
        "def intent_summary():\n"
        "    return {}\n"
        "def build_program():\n"
        "    return lambda **kwargs: {}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="shadows generated sibling module file"):
        with _generated_program_module(candidate):
            pass

    assert not marker.exists()


def test_generated_program_module_rejects_external_import_shadowing(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "marker.txt"
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "dspy.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n",
        encoding="utf-8",
    )
    (candidate / "program.py").write_text(
        "import dspy\n"
        "def io_spec():\n"
        "    return {'inputs': [], 'outputs': []}\n"
        "def intent_summary():\n"
        "    return {}\n"
        "def build_program():\n"
        "    return lambda **kwargs: {}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="shadows allowed external import root"):
        with _generated_program_module(candidate):
            pass

    assert not marker.exists()


def test_generated_program_module_allows_signature_sibling_import(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "signature.py").write_text(
        "import dspy\n"
        "class DemoSignature(dspy.Signature):\n"
        "    text: str = dspy.InputField()\n"
        "    answer: str = dspy.OutputField()\n",
        encoding="utf-8",
    )
    (candidate / "module.py").write_text(
        "from signature import DemoSignature\n"
        "def io_spec():\n"
        "    return {'inputs': ['text'], 'outputs': ['answer']}\n",
        encoding="utf-8",
    )
    (candidate / "program.py").write_text(
        "from module import io_spec\n"
        "def intent_summary():\n"
        "    return {}\n"
        "def build_program():\n"
        "    return lambda **kwargs: {}\n",
        encoding="utf-8",
    )

    with _generated_program_module(candidate) as module:
        assert module.io_spec()["outputs"] == ["answer"]


def test_runtime_input_materialization_converts_image_file_descriptors(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "ref.png"
    image_path.write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de0000000c49444154789c63f8cfc00000030101c9fe92ef0000000049454e44ae426082"
        )
    )
    inputs_path = tmp_path / "runtime-inputs.json"
    inputs_path.write_text("{}\n", encoding="utf-8")

    materialized = _materialize_runtime_inputs(
        {
            "visual_image_blocks": [
                {"type": "image_file", "path": "ref.png"},
                {
                    "type": "image_url",
                    "url": "data:image/png;base64,iVBORw0KGgo=",
                },
            ],
            "text": "unchanged",
        },
        inputs_path=inputs_path,
    )

    assert materialized["text"] == "unchanged"
    visual_image_blocks = materialized["visual_image_blocks"]
    assert isinstance(visual_image_blocks, str)
    assert visual_image_blocks.count("CUSTOM-TYPE-START-IDENTIFIER") == 2
    assert "image_url" in visual_image_blocks


def test_runtime_input_materialization_rejects_remote_image_url(
    tmp_path: Path,
) -> None:
    inputs_path = tmp_path / "runtime-inputs.json"
    inputs_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="only accepts data:image"):
        _materialize_runtime_inputs(
            {
                "visual_image_blocks": [
                    {
                        "type": "image_url",
                        "url": "http://169.254.169.254/latest/meta-data/",
                    }
                ]
            },
            inputs_path=inputs_path,
        )


def test_runtime_input_materialization_rejects_absolute_image_path_outside_inputs(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    image_path = outside / "ref.png"
    image_path.write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de0000000c49444154789c63f8cfc00000030101c9fe92ef0000000049454e44ae426082"
        )
    )
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    inputs_path = input_dir / "runtime-inputs.json"
    inputs_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Path escapes confinement root"):
        _materialize_runtime_inputs(
            {"image": {"type": "image_file", "path": str(image_path)}},
            inputs_path=inputs_path,
        )


def test_program_run_cli(tmp_path: Path, monkeypatch) -> None:
    _env(tmp_path, monkeypatch)
    candidate = _generated_candidate(tmp_path)
    inputs = tmp_path / "runtime-inputs.json"
    inputs.write_text(
        json.dumps({"inputs": {"ticket_text": "Server is down for all users"}}),
        encoding="utf-8",
    )
    outdir = tmp_path / "runtime-cli"

    result = runner.invoke(
        app,
        [
            "program-run",
            "--manifest",
            str(candidate / "manifest.json"),
            "--inputs",
            str(inputs),
            "--outdir",
            str(outdir),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["runtime_root"] == str(outdir)
    assert payload["steps"]["runtime_execution"]["status"] == "executed"
    assert (outdir / "oracle" / "coordinates.db").exists()

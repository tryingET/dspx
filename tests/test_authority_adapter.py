from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dspx.adapters.authority import build_agent_kernel_export_plan
from dspx.cli.dspx import app
from dspx.services.program_service import ProgramIntent, materialize_program_from_intent

runner = CliRunner()


def _materialize_program_with_ak_ref(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    intent = ProgramIntent(
        name="AuthorityAdapterProgram",
        objective="Answer with portable evidence for later authority export.",
        inputs=["question"],
        outputs=["answer"],
        promotion={
            "adjudicator": {"kind": "human_operator", "id": "local_operator"},
            "external_authority": {
                "refs": [
                    {
                        "system": "agent_kernel",
                        "ref": "AK-1234",
                        "role": "optional_authority_export_target",
                    }
                ]
            },
        },
    )
    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    return Path(artifact.root_path) / "manifest.json"


def test_agent_kernel_authority_adapter_builds_non_mutating_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _materialize_program_with_ak_ref(tmp_path, monkeypatch)

    plan = build_agent_kernel_export_plan(manifest)

    assert plan["schema_version"] == "dspx-agent-kernel-authority-export-plan-v1"
    assert plan["adapter"] == "agent_kernel"
    assert plan["status"] == "planned_not_exported"
    assert plan["mutation"] == "none"
    assert plan["non_authority"] == {
        "external_mutation": False,
        "ak_command_invoked": False,
        "program_promoted": False,
        "oracle_authority": False,
    }
    assert plan["candidate"]["artifact_kind"] == "program"
    assert plan["candidate"]["promotion_state"] == "not_promoted"
    assert plan["promotion"]["adjudicator"] == {
        "kind": "human_operator",
        "id": "local_operator",
        "authority": "required_for_promotion",
        "status": "pending",
    }
    assert plan["external_refs"] == [
        {
            "system": "agent_kernel",
            "ref": "AK-1234",
            "role": "optional_authority_export_target",
            "status": "not_exported",
            "source": "promotion.external_authority.refs",
        }
    ]
    assert "supported_adapters" not in plan
    assert plan["evidence_packet"]["promotion_review_hash"]


def test_agent_kernel_authority_adapter_cli_writes_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _materialize_program_with_ak_ref(tmp_path, monkeypatch)
    out = tmp_path / "ak-export-plan.json"

    result = runner.invoke(
        app,
        [
            "adapters",
            "authority",
            "agent-kernel-plan",
            "--manifest",
            str(manifest),
            "--external-ref",
            "AK-9999",
            "--out",
            str(out),
        ],
    )

    assert result.exit_code == 0, result.output
    stdout_payload = json.loads(result.stdout)
    file_payload = json.loads(out.read_text(encoding="utf-8"))
    assert stdout_payload == file_payload
    assert file_payload["status"] == "planned_not_exported"
    assert file_payload["external_refs"][0]["ref"] == "AK-9999"
    assert file_payload["external_refs"][0]["source"] == "adapter.argument.external_ref"
    assert file_payload["non_authority"]["ak_command_invoked"] is False
    receipt_path = tmp_path / "ak-export-plan.json.meta.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["schema_version"] == "dspx-authority-export-plan-receipt-v1"
    assert receipt["adapter"] == "agent_kernel"
    assert receipt["plan_status"] == "planned_not_exported"
    assert receipt["mutation"] == "none"
    assert receipt["plan_hash"] == hashlib.sha256(out.read_bytes()).hexdigest()
    assert receipt["non_authority"]["external_mutation"] is False
    assert receipt["non_authority"]["ak_command_invoked"] is False


def test_agent_kernel_authority_adapter_rejects_non_program_manifest(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"schema_version": "not-program", "candidate_assembly": {}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="not a program-gen"):
        build_agent_kernel_export_plan(manifest)

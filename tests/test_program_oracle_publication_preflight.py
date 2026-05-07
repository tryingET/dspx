from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.coordinates import reset_embedding_engine
from dspx.services.program_intent import ProgramIntent
from dspx.services.program_oracle_publication_preflight import (
    ProgramOraclePublicationPreflightError,
    build_program_oracle_publication_preflight,
)
from dspx.services.program_service import materialize_program_from_intent

runner = CliRunner()


def _materialize_example_program(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")
    reset_embedding_engine()
    intent = ProgramIntent(
        name="TicketProgram",
        objective="Classify support ticket urgency.",
        inputs=["ticket_text"],
        outputs=["urgency"],
        metric="exact_match",
        constraints=["use only the supplied ticket text"],
        examples=[
            {
                "inputs": {"ticket_text": "Server is down for all users"},
                "outputs": {"urgency": "high"},
            }
        ],
    )
    artifact = materialize_program_from_intent(intent, outdir=tmp_path / "program")
    return Path(artifact.root_path)


def _base_kwargs(root: Path) -> dict[str, object]:
    return {
        "manifest_path": root / "manifest.json",
        "target": "shared-postgres",
        "publication_label": "retained",
        "publisher_id": "pi-session-test",
        "publisher_role": "operator",
        "publisher_assertion": "share synthetic behavior evidence for future Oracle retrieval",
        "redaction_status": "checked",
        "retention_class": "retained_behavior_memory",
    }


def test_program_oracle_publication_preflight_cli_writes_local_packet_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _materialize_example_program(tmp_path, monkeypatch)
    monkeypatch.setenv("DSPX_ORACLE_STORE", "postgres_pgvector")
    monkeypatch.setenv(
        "DSPX_ORACLE_DATABASE_URL",
        "postgresql://dspx_oracle:super-secret-password@ds1621:55432/dspx_oracle",
    )
    out = tmp_path / "publication" / "preflight.json"

    result = runner.invoke(
        app,
        [
            "oracle",
            "program-evidence",
            "publish-preflight",
            "--manifest",
            str(root / "manifest.json"),
            "--target",
            "shared-postgres",
            "--publication-label",
            "retained",
            "--publisher-id",
            "pi-session-test",
            "--publisher-role",
            "operator",
            "--publisher-assertion",
            "share synthetic behavior evidence for future Oracle retrieval",
            "--redaction-status",
            "checked",
            "--retention-class",
            "retained_behavior_memory",
            "--out",
            str(out),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "super-secret-password" not in result.stdout
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "program-oracle-shared-publication-preflight-v1"
    assert payload["status"] == "ready_not_published"
    assert payload["target"]["database_url_present"] is True
    assert payload["target"]["database_url_redacted"] == "<redacted>"
    assert payload["preflight"]["ready_for_shared_publication"] is False
    assert payload["preflight"]["blocking_reasons"] == [
        "shared_publication_not_implemented"
    ]
    assert payload["publication"]["publication_label_class"] == "empirical"
    assert payload["publication"]["publisher_identity_kind"] == (
        "declared_not_authenticated"
    )
    assert payload["effect"] == {
        "local_preflight_written": True,
        "oracle_index_mutated": False,
        "shared_oracle_mutated": False,
        "ak_called": False,
        "governance_mutated": False,
        "mlflow_mutated": False,
        "program_files_mutated": False,
        "promotion_state_changed": False,
    }
    assert payload["non_authority"]["preflight_only"] is True
    assert payload["non_authority"]["oracle_authority"] is False
    assert out.exists()
    assert "super-secret-password" not in out.read_text(encoding="utf-8")


def test_program_oracle_publication_preflight_idempotency_is_stable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _materialize_example_program(tmp_path, monkeypatch)

    first = build_program_oracle_publication_preflight(**_base_kwargs(root))
    second = build_program_oracle_publication_preflight(**_base_kwargs(root))

    assert first["publication_id"] == second["publication_id"]
    assert first["idempotency"]["same_inputs_same_publication_id"] is True


def test_program_oracle_publication_preflight_requires_oracle_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _materialize_example_program(tmp_path, monkeypatch)
    (root / "oracle_evidence.json").unlink()

    with pytest.raises(ProgramOraclePublicationPreflightError, match="not found"):
        build_program_oracle_publication_preflight(**_base_kwargs(root))


def test_program_oracle_publication_preflight_rejects_widened_non_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _materialize_example_program(tmp_path, monkeypatch)
    evidence_path = root / "oracle_evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["non_authority"]["oracle_promotion"] = True
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(
        ProgramOraclePublicationPreflightError, match="oracle_promotion"
    ):
        build_program_oracle_publication_preflight(**_base_kwargs(root))


@pytest.mark.parametrize(
    ("override", "match"),
    [
        ({"publication_label": "winner"}, "unknown publication_label"),
        ({"publication_label": "activated"}, "authority_ref is required"),
        ({"redaction_status": "unknown"}, "redaction_status is not eligible"),
        (
            {"redaction_status": "contains_sensitive_material"},
            "redaction_status is not eligible",
        ),
        ({"retention_class": "do_not_publish"}, "not eligible"),
        ({"publisher_id": ""}, "publisher_id is required"),
    ],
)
def test_program_oracle_publication_preflight_fails_closed_on_invalid_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    override: dict[str, object],
    match: str,
) -> None:
    root = _materialize_example_program(tmp_path, monkeypatch)
    kwargs = _base_kwargs(root)
    kwargs.update(override)

    with pytest.raises(ProgramOraclePublicationPreflightError, match=match):
        build_program_oracle_publication_preflight(**kwargs)


def test_program_oracle_publication_preflight_accepts_authority_mirror_with_ref(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _materialize_example_program(tmp_path, monkeypatch)
    kwargs = _base_kwargs(root)
    kwargs.update(
        {
            "publication_label": "activated",
            "authority_ref": "AK-1234",
            "retention_class": "activation_evidence_reference",
        }
    )

    payload = build_program_oracle_publication_preflight(**kwargs)

    assert payload["publication"]["publication_label_class"] == "authority_mirror"
    assert payload["publication"]["authority_ref_required"] is True
    assert payload["publication"]["authority_ref"] == "AK-1234"
    assert payload["planned_record"]["authority_ref_kind"] == "opaque_reference_only"

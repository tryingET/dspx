from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.services.program_oracle_autoresearch import (
    AutoresearchOraclePublicationPreflightError,
    build_autoresearch_oracle_publication_preflight,
)

runner = CliRunner()


def _write_packet(
    path: Path, *, record_override: dict[str, object] | None = None
) -> Path:
    record = {
        "recordKind": "autoresearch.campaign_run.oracle_evidence.v1",
        "recordId": "ar-oracle-001",
        "campaign": "latency-campaign",
        "metricName": "latency_ms",
        "metricUnit": "ms",
        "direction": "lower",
        "runStatus": "candidate",
        "runKind": "ordinary",
        "empiricalDecisionClass": "candidate_improvement",
        "metric": 42.5,
        "timestamp": 1778123593,
        "description": "candidate improved latency",
        "checks": "passed",
        "hypothesisId": "hyp-1",
        "hypothesis": "cache the hot path",
        "interventionSummary": "added bounded cache",
        "candidate": {
            "source": "manual",
            "worktreePath": None,
            "branch": "candidate/cache-hot-path",
            "baseRef": "main",
            "diffSummary": "cache hot path",
            "filesChanged": ["src/cache.py"],
        },
        "oracleText": "metric=42.5ms\nstatus=candidate\nhypothesis=cache hot path",
        "sourceRefs": {
            "receiptPath": "/tmp/autoresearch/autoresearch.jsonl",
            "closeoutPacketKind": "autoresearch.closeout.v1",
            "runIteration": 1,
            "runTimestamp": 1778123593,
        },
        "nonAuthority": True,
    }
    if record_override:
        record.update(record_override)
    packet = {
        "packetKind": "autoresearch.oracle_evidence.v1",
        "adapterContractVersion": 1,
        "targetKinds": [
            "dspx_oracle",
            "empirical_memory",
            "evidence",
            "adapter_source",
        ],
        "cwd": "/tmp/autoresearch",
        "campaign": "latency-campaign",
        "sourceArtifacts": {
            "closeoutPacketKind": "autoresearch.closeout.v1",
            "receiptPath": "/tmp/autoresearch/autoresearch.jsonl",
        },
        "records": [record],
        "publicationPreflight": {
            "status": "ready_for_dspx_owner_review",
            "target": "dspx_oracle_postgres_pgvector",
            "publicationLabel": "retained_behavior_memory_candidate",
            "sharedOracleMutated": False,
            "localCoordinatesDbMigrated": False,
            "canonicalAuthorityMutated": False,
            "blockedReasons": [],
            "suggestedDspxOwnerAction": "run DSPx owner preflight",
            "suggestedDspxPreflightCommandTemplate": "dspx oracle ...",
        },
        "adapterBoundary": "non-mutating adapter packet",
        "evidenceBoundary": "empirical memory input only",
        "authorityBoundary": "not authority",
    }
    path.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
    return path


def _base_kwargs(packet: Path) -> dict[str, Any]:
    return {
        "packet_path": packet,
        "target": "shared-postgres",
        "publication_label": "retained",
        "publisher_id": "pi-session-test",
        "publisher_role": "operator",
        "publisher_assertion": "share autoresearch behavior evidence for future Oracle retrieval",
        "redaction_status": "checked",
        "retention_class": "retained_behavior_memory",
    }


def test_autoresearch_oracle_publication_preflight_cli_writes_local_packet_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    packet = _write_packet(tmp_path / "autoresearch_oracle_evidence.json")
    monkeypatch.setenv("DSPX_ORACLE_STORE", "postgres_pgvector")
    monkeypatch.setenv(
        "DSPX_ORACLE_DATABASE_URL",
        "postgresql://dspx_oracle:super-secret-password@ds1621:55432/dspx_oracle",
    )
    out = tmp_path / "publication" / "autoresearch_preflight.json"

    result = runner.invoke(
        app,
        [
            "oracle",
            "autoresearch-evidence",
            "publish-preflight",
            "--packet",
            str(packet),
            "--target",
            "shared-postgres",
            "--publication-label",
            "retained",
            "--publisher-id",
            "pi-session-test",
            "--publisher-role",
            "operator",
            "--publisher-assertion",
            "share autoresearch behavior evidence for future Oracle retrieval",
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
    assert payload["schema_version"] == (
        "autoresearch-oracle-shared-publication-preflight-v1"
    )
    assert payload["status"] == "ready_not_published"
    assert payload["created_from"]["packet_kind"] == "autoresearch.oracle_evidence.v1"
    assert payload["target"]["database_url_present"] is True
    assert payload["target"]["database_url_redacted"] == "<redacted>"
    assert payload["records"]["record_count"] == 1
    assert payload["records"]["record_ids"] == ["ar-oracle-001"]
    assert payload["preflight"]["ready_for_shared_publication"] is False
    assert payload["preflight"]["blocking_reasons"] == [
        "autoresearch_adapter_preflight_only"
    ]
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
    assert payload["non_authority"]["oracle_authority"] is False
    assert out.exists()
    assert "super-secret-password" not in out.read_text(encoding="utf-8")


def test_autoresearch_oracle_publication_preflight_idempotency_is_stable(
    tmp_path: Path,
) -> None:
    packet = _write_packet(tmp_path / "autoresearch_oracle_evidence.json")

    first = build_autoresearch_oracle_publication_preflight(**_base_kwargs(packet))
    second = build_autoresearch_oracle_publication_preflight(**_base_kwargs(packet))

    assert first["publication_id"] == second["publication_id"]
    assert first["idempotency"]["same_inputs_same_publication_id"] is True


@pytest.mark.parametrize(
    ("record_override", "match"),
    [
        ({"nonAuthority": False}, "nonAuthority must be true"),
        ({"recordKind": "wrong"}, "recordKind"),
        ({"oracleText": ""}, "oracleText is required"),
        ({"sourceRefs": {"receiptPath": "x"}}, "closeoutPacketKind"),
    ],
)
def test_autoresearch_oracle_publication_preflight_rejects_invalid_records(
    tmp_path: Path, record_override: dict[str, object], match: str
) -> None:
    packet = _write_packet(
        tmp_path / "autoresearch_oracle_evidence.json",
        record_override=record_override,
    )

    with pytest.raises(AutoresearchOraclePublicationPreflightError, match=match):
        build_autoresearch_oracle_publication_preflight(**_base_kwargs(packet))


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
        ({"retention_class": "do_not_publish"}, "retention_class is not eligible"),
        ({"publisher_id": ""}, "publisher_id is required"),
    ],
)
def test_autoresearch_oracle_publication_preflight_fails_closed_on_invalid_inputs(
    tmp_path: Path, override: dict[str, object], match: str
) -> None:
    packet = _write_packet(tmp_path / "autoresearch_oracle_evidence.json")
    kwargs = _base_kwargs(packet)
    kwargs.update(override)

    with pytest.raises(AutoresearchOraclePublicationPreflightError, match=match):
        build_autoresearch_oracle_publication_preflight(**kwargs)


def test_autoresearch_oracle_publication_preflight_accepts_authority_ref(
    tmp_path: Path,
) -> None:
    packet = _write_packet(tmp_path / "autoresearch_oracle_evidence.json")
    kwargs = _base_kwargs(packet)
    kwargs.update(
        {
            "publication_label": "activated",
            "authority_ref": "AK-1234",
            "retention_class": "activation_evidence_reference",
        }
    )

    payload = build_autoresearch_oracle_publication_preflight(**kwargs)

    assert payload["publication"]["publication_label_class"] == "authority_mirror"
    assert payload["publication"]["authority_ref_required"] is True
    assert payload["publication"]["authority_ref"] == "AK-1234"
    assert payload["planned_record"]["authority_ref_kind"] == "opaque_reference_only"


def test_autoresearch_oracle_publication_preflight_rejects_blocked_source_packet(
    tmp_path: Path,
) -> None:
    packet = _write_packet(tmp_path / "autoresearch_oracle_evidence.json")
    payload = json.loads(packet.read_text(encoding="utf-8"))
    payload["publicationPreflight"]["status"] = "blocked_no_campaign_evidence"
    payload["publicationPreflight"]["blockedReasons"] = ["missing_closeout"]
    packet.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(AutoresearchOraclePublicationPreflightError, match="status"):
        build_autoresearch_oracle_publication_preflight(**_base_kwargs(packet))


def test_autoresearch_oracle_publication_preflight_rejects_duplicate_record_ids(
    tmp_path: Path,
) -> None:
    packet = _write_packet(tmp_path / "autoresearch_oracle_evidence.json")
    payload = json.loads(packet.read_text(encoding="utf-8"))
    duplicate = dict(payload["records"][0])
    duplicate["oracleText"] = "different evidence with duplicate id"
    payload["records"].append(duplicate)
    packet.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(AutoresearchOraclePublicationPreflightError, match="duplicated"):
        build_autoresearch_oracle_publication_preflight(**_base_kwargs(packet))


def test_autoresearch_oracle_publication_preflight_rejects_missing_boundary_fields(
    tmp_path: Path,
) -> None:
    packet = _write_packet(tmp_path / "autoresearch_oracle_evidence.json")
    payload = json.loads(packet.read_text(encoding="utf-8"))
    payload.pop("authorityBoundary")
    packet.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(
        AutoresearchOraclePublicationPreflightError, match="authorityBoundary"
    ):
        build_autoresearch_oracle_publication_preflight(**_base_kwargs(packet))


def test_autoresearch_oracle_publication_preflight_rejects_missing_run_fields(
    tmp_path: Path,
) -> None:
    packet = _write_packet(tmp_path / "autoresearch_oracle_evidence.json")
    payload = json.loads(packet.read_text(encoding="utf-8"))
    payload["records"][0].pop("runStatus")
    packet.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(AutoresearchOraclePublicationPreflightError, match="runStatus"):
        build_autoresearch_oracle_publication_preflight(**_base_kwargs(packet))

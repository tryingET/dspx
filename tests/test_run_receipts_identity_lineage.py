from __future__ import annotations

import json
from pathlib import Path

import pytest

from dspx.cli.dspx import app
from dspx.run_receipts import (
    build_run_receipt,
    current_receipt_lineage,
    normalize_receipt_provenance,
    resolve_receipt_provenance,
    resolve_receipt_run_id,
    resolve_run_identity,
)
from run_receipts_helpers import (
    runner,
)


def test_run_receipt_phase_c_causal_chain(tmp_path: Path) -> None:
    """Test causal chain for Time Travel behavioral lineage."""
    from dspx.run_receipts import build_causal_chain, extend_causal_chain

    out = tmp_path / "artifact.py"
    out.write_text("print('ok')\n", encoding="utf-8")

    # Build receipt with causal chain
    receipt = build_run_receipt(
        run_kind="module-gen",
        output_path=out,
        output_hash="abc123",
        template_version="simple-v1",
        cache_key="k1",
        cache_file=None,
        cache_enabled=False,
        causal_chain=["sig-run-001", "refine-run-002"],
        parent_run_id="sig-run-001",
        branch="feature-x",
    )

    assert receipt["causal_chain"] == ["sig-run-001", "refine-run-002"]
    assert receipt["parent_run_id"] == "sig-run-001"
    assert receipt["branch"] == "feature-x"

    # Test helper functions
    chain = build_causal_chain("a", "b", "a", "c")  # dedup
    assert chain == ["a", "b", "c"]

    extended = extend_causal_chain(["x", "y"], "z")
    assert extended == ["x", "y", "z"]

    # Test max depth
    long_chain = extend_causal_chain(
        list("abcdefghijklmnopqrstuvwxyz"), "new", max_depth=10
    )
    assert len(long_chain) == 10
    assert long_chain[-1] == "new"


def test_run_receipt_phase_c_dreaming_fields(tmp_path: Path) -> None:
    """Test outcome/latency/tokens fields for Dreaming simulation."""
    out = tmp_path / "artifact.py"
    out.write_text("print('ok')\n", encoding="utf-8")

    receipt = build_run_receipt(
        run_kind="module-gen",
        output_path=out,
        output_hash="abc123",
        template_version="simple-v1",
        cache_key="k1",
        cache_file=None,
        cache_enabled=False,
        outcome="success",
        latency_ms=1234.5,
        tokens_used=1500,
        tokens_prompt=1000,
        tokens_completion=500,
    )

    assert receipt["outcome"] == "success"
    assert receipt["latency_ms"] == 1234.5
    assert receipt["tokens_used"] == 1500
    assert receipt["tokens_prompt"] == 1000
    assert receipt["tokens_completion"] == 500


def test_run_receipt_phase_c_execution_context(tmp_path: Path) -> None:
    """Test execution context capture for Consciousness."""
    out = tmp_path / "artifact.py"
    out.write_text("print('ok')\n", encoding="utf-8")

    # With context capture (default)
    receipt = build_run_receipt(
        run_kind="module-gen",
        output_path=out,
        output_hash="abc123",
        template_version="simple-v1",
        cache_key="k1",
        cache_file=None,
        cache_enabled=False,
        capture_context=True,
    )

    assert "execution_context" in receipt
    ctx = receipt["execution_context"]
    assert "python_version" in ctx
    assert "platform" in ctx
    # git_commit may or may not be present depending on environment

    # Without context capture
    receipt_no_ctx = build_run_receipt(
        run_kind="module-gen",
        output_path=out,
        output_hash="abc123",
        template_version="simple-v1",
        cache_key="k1",
        cache_file=None,
        cache_enabled=False,
        capture_context=False,
    )

    assert "execution_context" not in receipt_no_ctx


def test_run_receipt_execution_context_hash_tracks_env_value_changes(
    tmp_path: Path, monkeypatch
) -> None:
    out = tmp_path / "artifact.py"
    out.write_text("print('ok')\n", encoding="utf-8")

    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    receipt_a = build_run_receipt(
        run_kind="module-gen",
        output_path=out,
        output_hash="abc123",
        template_version="simple-v1",
        cache_key="k1",
        cache_file=None,
        cache_enabled=False,
        capture_context=True,
    )

    monkeypatch.setenv("DSPX_PROVIDER", "pi-rpc")
    receipt_b = build_run_receipt(
        run_kind="module-gen",
        output_path=out,
        output_hash="abc123",
        template_version="simple-v1",
        cache_key="k1",
        cache_file=None,
        cache_enabled=False,
        capture_context=True,
    )

    assert (
        receipt_a["execution_context"]["env_hash"]
        != receipt_b["execution_context"]["env_hash"]
    )


def test_run_receipt_execution_context_hash_redacts_secret_env_values(
    tmp_path: Path, monkeypatch
) -> None:
    out = tmp_path / "artifact.py"
    out.write_text("print('ok')\n", encoding="utf-8")

    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_OPENAI_COMPAT_API_KEY", "secret-a")
    receipt_a = build_run_receipt(
        run_kind="module-gen",
        output_path=out,
        output_hash="abc123",
        template_version="simple-v1",
        cache_key="k1",
        cache_file=None,
        cache_enabled=False,
        capture_context=True,
    )

    monkeypatch.setenv("DSPX_OPENAI_COMPAT_API_KEY", "secret-b")
    receipt_b = build_run_receipt(
        run_kind="module-gen",
        output_path=out,
        output_hash="abc123",
        template_version="simple-v1",
        cache_key="k1",
        cache_file=None,
        cache_enabled=False,
        capture_context=True,
    )

    assert (
        receipt_a["execution_context"]["env_hash"]
        == receipt_b["execution_context"]["env_hash"]
    )


def test_resolve_run_identity_exposes_contract_facets() -> None:
    receipt = {
        "execution_id": "exec-123",
        "run_id": "mlflow-456",
        "cache_key": "cache-789",
        "hash": "hash-abc",
        "output_path": "/tmp/out.py",
    }

    identity = resolve_run_identity(receipt)

    assert identity.canonical_id == "exec-123"
    assert identity.canonical_source == "execution_id"
    assert identity.behavioral_id == "mlflow-456"
    assert identity.behavioral_source == "run_id"
    assert identity.storage_id == "exec-123"
    assert identity.storage_source == "execution_id"
    assert identity.alias_ids == (
        "exec-123",
        "mlflow-456",
        "cache-789",
        "hash-abc",
        "/tmp/out.py",
    )


def test_normalize_receipt_provenance_prefers_canonical_identity_fields() -> None:
    receipt = {
        "execution_id": "exec-123",
        "run_id": "mlflow-456",
        "cache_key": "cache-789",
        "hash": "hash-abc",
        "output_path": "/tmp/out.py",
        "branch": "feature-a",
        "parent_run_id": "parent-1",
        "causal_chain": ["root-1", "parent-1", "root-1"],
    }

    provenance = normalize_receipt_provenance(receipt)

    assert provenance["run_id"] == "exec-123"
    assert provenance["branch"] == "feature-a"
    assert provenance["parent_run_id"] == "parent-1"
    assert provenance["causal_chain"] == ["root-1", "parent-1"]
    assert provenance["lineage_ids"] == ["root-1", "parent-1"]
    assert provenance["identity"]["canonical_source"] == "execution_id"
    assert provenance["warnings"] == ["causal_chain:deduplicated_items=1"]


def test_resolve_receipt_provenance_ignores_non_string_lineage_items() -> None:
    receipt = {
        "execution_id": "exec-123",
        "parent_run_id": 42,
        "causal_chain": ["root-1", None, 123, "", "root-1"],
    }

    provenance = resolve_receipt_provenance(receipt)

    assert provenance.run_id == "exec-123"
    assert provenance.parent_run_id is None
    assert provenance.causal_chain == ("root-1",)
    assert provenance.lineage_ids == ("root-1",)
    assert provenance.warnings == (
        "parent_run_id:ignored_invalid_value",
        "causal_chain:ignored_non_string_items=2",
        "causal_chain:ignored_blank_items=1",
        "causal_chain:deduplicated_items=1",
    )


def test_resolve_receipt_run_id_prefers_legacy_ids_before_output_path() -> None:
    receipt = {
        "output_path": "/repo/generated/same.py",
        "cache_key": "cache-left",
        "hash": "hash-left",
    }

    assert resolve_receipt_run_id(receipt) == "cache-left"


def test_current_receipt_lineage_appends_parent_to_causal_chain(monkeypatch) -> None:
    monkeypatch.setenv("DSPX_CAUSAL_CHAIN", '["root-1"]')

    lineage = current_receipt_lineage(parent_run_id="parent-1", branch="feature-a")

    assert lineage == {
        "branch": "feature-a",
        "parent_run_id": "parent-1",
        "causal_chain": ["root-1", "parent-1"],
    }


def test_current_receipt_lineage_allows_explicit_empty_chain_override(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DSPX_CAUSAL_CHAIN", '["root-1"]')

    lineage = current_receipt_lineage(causal_chain=[], branch="feature-a")

    assert lineage == {"branch": "feature-a"}


@pytest.mark.slow
def test_cli_generated_receipt_includes_execution_id_and_branch(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_RECEIPT_BRANCH", "feature-receipt")

    out = tmp_path / "sig.py"
    result = runner.invoke(
        app,
        [
            "signature",
            "gen",
            "Extract names from text",
            "--template-version",
            "simple-v1",
            "--outfile",
            str(out),
        ],
    )
    assert result.exit_code == 0

    receipt = json.loads((tmp_path / "sig.py.meta.json").read_text(encoding="utf-8"))
    assert receipt["branch"] == "feature-receipt"
    assert isinstance(receipt.get("execution_id"), str)
    assert receipt["execution_id"]


@pytest.mark.slow
def test_run_receipt_phase_c_defaults_omit_empty_fields(tmp_path: Path) -> None:
    """Test that default/empty Phase C+ fields are omitted from receipt."""
    out = tmp_path / "artifact.py"
    out.write_text("print('ok')\n", encoding="utf-8")

    receipt = build_run_receipt(
        run_kind="module-gen",
        output_path=out,
        output_hash="abc123",
        template_version="simple-v1",
        cache_key="k1",
        cache_file=None,
        cache_enabled=False,
        # All Phase C+ fields left as defaults
    )

    # These should NOT be in the receipt when using defaults
    assert "causal_chain" not in receipt
    assert "parent_run_id" not in receipt
    assert "branch" not in receipt
    assert "outcome" not in receipt  # "unknown" is default, omitted
    assert "latency_ms" not in receipt
    assert "tokens_used" not in receipt
    assert "tokens_prompt" not in receipt
    assert "tokens_completion" not in receipt

    # But execution_context IS captured by default
    assert "execution_context" in receipt

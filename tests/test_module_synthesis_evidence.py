from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from dspx.cli.dspx import app
from dspx.coordinates import CoordinateIndex, get_embedding_engine
from dspx.dtos import ModuleSpec
from dspx.run_receipts import load_run_receipt
from dspx.services.module_synthesis_evidence import retrieve_module_synthesis_evidence


runner = CliRunner()


def _configure_generation_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    monkeypatch.setenv("DSPX_PROVIDER", "stub")
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DSPX_MODULE_SYNTHESIS_QUALITY_ENABLE", "0")
    monkeypatch.setenv("DSPX_ORACLE_EMBEDDING_BACKEND", "mock")


def _generate_module_receipt(
    tmp_path: Path,
    monkeypatch,
    *,
    output_name: str,
    name: str = "Summarizer",
    description: str = "Summarizes text",
    inputs: tuple[str, ...] = ("text",),
    outputs: tuple[str, ...] = ("summary",),
    use_signature: bool = False,
) -> Path:
    _configure_generation_env(tmp_path, monkeypatch)

    out = tmp_path / output_name
    args = [
        "module-gen",
        "--name",
        name,
        "--description",
        description,
        "--template-version",
        "simple-v1",
        "--outfile",
        str(out),
    ]
    for item in inputs:
        args.extend(["--input", item])
    for item in outputs:
        args.extend(["--output", item])
    if use_signature:
        args.append("--use-signature")

    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.stdout
    return tmp_path / f"{output_name}.meta.json"


def _generate_signature_receipt(
    tmp_path: Path,
    monkeypatch,
    *,
    output_name: str,
) -> Path:
    _configure_generation_env(tmp_path, monkeypatch)

    out = tmp_path / output_name
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
    assert result.exit_code == 0, result.stdout
    return tmp_path / f"{output_name}.meta.json"


def _index_receipt(meta_path: Path, *, index_path: Path) -> None:
    receipt = load_run_receipt(meta_path)
    assert isinstance(receipt, dict)
    engine = get_embedding_engine()
    embedding = engine.embed_receipt(receipt, receipt_path=meta_path)
    assert embedding is not None
    index = CoordinateIndex(db_path=index_path)
    assert index.upsert(embedding) is True


def test_retrieve_module_synthesis_evidence_collects_exact_match_receipts_and_oracle_neighbors(
    tmp_path: Path, monkeypatch
) -> None:
    exact_ok = _generate_module_receipt(
        tmp_path,
        monkeypatch,
        output_name="exact-ok.py",
    )
    exact_drift = _generate_module_receipt(
        tmp_path,
        monkeypatch,
        output_name="exact-drift.py",
    )
    non_match = _generate_module_receipt(
        tmp_path,
        monkeypatch,
        output_name="other.py",
        name="Classifier",
        description="Classifies text",
        outputs=("label",),
    )
    signature_meta = _generate_signature_receipt(
        tmp_path,
        monkeypatch,
        output_name="sig.py",
    )

    (tmp_path / "exact-drift.py").write_text(
        "print('drifted output')\n", encoding="utf-8"
    )

    index_path = tmp_path / "oracle" / "coordinates.db"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    for meta_path in (exact_ok, exact_drift, non_match, signature_meta):
        _index_receipt(meta_path, index_path=index_path)

    spec = ModuleSpec(
        name="Summarizer",
        description="Summarizes text",
        inputs=["text"],
        outputs=["summary"],
        options={"template_version": "simple-v1"},
    )
    bundle = retrieve_module_synthesis_evidence(
        spec,
        use_signature=False,
        receipts_path=tmp_path,
        oracle_index_path=index_path,
        oracle_top_k=10,
    )

    assert bundle.request.to_dict() == {
        "name": "Summarizer",
        "description": "Summarizes text",
        "inputs": ["text"],
        "outputs": ["summary"],
        "use_signature": False,
        "template_version": "simple-v1",
    }
    assert bundle.retrieval_order == (
        "exact_match_receipts",
        "replay_verification",
        "oracle_neighbors",
    )
    assert bundle.receipts_scanned == 4
    assert bundle.oracle_index_available is True
    assert bundle.oracle_query_text == (
        "name: Summarizer\n"
        "description: Summarizes text\n"
        "inputs: ['text']\n"
        "outputs: ['summary']"
    )

    matches = bundle.exact_match_receipts
    assert len(matches) == 2
    assert bundle.positive_evidence_count == 1

    receipt_paths = {Path(item.receipt.receipt_path).name for item in matches}
    assert receipt_paths == {"exact-ok.py.meta.json", "exact-drift.py.meta.json"}

    healthy_by_receipt = {
        Path(item.receipt.receipt_path).name: item.positive_evidence for item in matches
    }
    assert healthy_by_receipt["exact-ok.py.meta.json"] is True
    assert healthy_by_receipt["exact-drift.py.meta.json"] is False

    drift_match = next(
        item
        for item in matches
        if Path(item.receipt.receipt_path).name == "exact-drift.py.meta.json"
    )
    assert drift_match.replay.replay_status == "failed"
    assert "output_hash_mismatch" in drift_match.replay.replay_error_codes
    assert drift_match.replay.local_facts["failed_replay_checks"] == [
        "output_hash_match"
    ]
    assert drift_match.receipt.selected_candidate_rank == 1
    assert drift_match.receipt.ranking_policy_id == "module.v7.multi-candidate-ranked"
    assert drift_match.receipt.synthesis is not None
    assert drift_match.receipt.synthesis_selection_policy is not None
    assert drift_match.receipt.synthesis_ranked_candidates

    assert bundle.oracle_neighbors
    assert all(item.run_kind == "module-gen" for item in bundle.oracle_neighbors)
    assert all(item.receipt_identity for item in bundle.oracle_neighbors)

    payload = bundle.to_dict()
    assert payload["positive_evidence_count"] == 1
    assert len(payload["exact_match_receipts"]) == 2
    assert (
        payload["exact_match_receipts"][0]["receipt"]["replay_inputs"]["name"]
        == "Summarizer"
    )
    assert all(item["run_kind"] == "module-gen" for item in payload["oracle_neighbors"])


def test_retrieve_module_synthesis_evidence_handles_missing_oracle_index(
    tmp_path: Path, monkeypatch
) -> None:
    _generate_module_receipt(
        tmp_path,
        monkeypatch,
        output_name="single.py",
    )

    spec = ModuleSpec(
        name="Summarizer",
        description="Summarizes text",
        inputs=["text"],
        outputs=["summary"],
        options={"template_version": "simple-v1"},
    )
    bundle = retrieve_module_synthesis_evidence(
        spec,
        use_signature=False,
        receipts_path=tmp_path,
        oracle_index_path=tmp_path / "missing" / "coordinates.db",
    )

    assert len(bundle.exact_match_receipts) == 1
    assert bundle.oracle_index_available is False
    assert bundle.oracle_neighbors == ()
    assert bundle.positive_evidence_count == 1


def test_retrieve_module_synthesis_evidence_respects_use_signature_in_exact_match(
    tmp_path: Path, monkeypatch
) -> None:
    plain = _generate_module_receipt(
        tmp_path,
        monkeypatch,
        output_name="plain.py",
        use_signature=False,
    )
    signed = _generate_module_receipt(
        tmp_path,
        monkeypatch,
        output_name="signed.py",
        use_signature=True,
    )

    spec = ModuleSpec(
        name="Summarizer",
        description="Summarizes text",
        inputs=["text"],
        outputs=["summary"],
        options={"template_version": "simple-v1"},
    )
    plain_bundle = retrieve_module_synthesis_evidence(
        spec,
        use_signature=False,
        receipts_path=tmp_path,
    )
    signed_bundle = retrieve_module_synthesis_evidence(
        spec,
        use_signature=True,
        receipts_path=tmp_path,
    )

    assert len(plain_bundle.exact_match_receipts) == 1
    assert Path(plain_bundle.exact_match_receipts[0].receipt.receipt_path) == plain
    assert len(signed_bundle.exact_match_receipts) == 1
    assert Path(signed_bundle.exact_match_receipts[0].receipt.receipt_path) == signed

    signed_receipt = json.loads(signed.read_text(encoding="utf-8"))
    assert signed_receipt["replay_inputs"]["use_signature"] is True

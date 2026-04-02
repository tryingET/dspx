from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

import dspx.server.app as server_app
from dspx.server.app import create_app


def _artifact_path(root: Path, rel_path: str | None) -> Path | None:
    if rel_path is None:
        return None
    path = Path(rel_path)
    assert not path.is_absolute()
    return root / path


def test_server_signature_and_module_and_mermaid(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    output_root = tmp_path / "server-output"
    monkeypatch.setenv("DSPX_SERVER_OUTPUT_DIR", str(output_root))
    monkeypatch.setenv("DSPX_SYNTHESIS_DIR", str(tmp_path / "synthesis"))
    monkeypatch.setenv(
        "DSPX_MODULE_SYNTHESIS_EVIDENCE_RECEIPTS_PATH",
        str(tmp_path / "receipts"),
    )
    monkeypatch.setenv(
        "DSPX_MODULE_SYNTHESIS_EVIDENCE_ORACLE_INDEX_PATH",
        str(tmp_path / "oracle" / "coordinates.db"),
    )
    app = create_app()
    client = TestClient(app)

    r = client.post(
        "/signature",
        json={
            "prompt": "Extract names",
            "template_version": "simple-v1",
            "class_name": "Sig",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert "class Sig(dspy.Signature)" in data["code"]
    signature_path = _artifact_path(output_root, data["output_path"])
    receipt_path = _artifact_path(output_root, data["receipt_path"])
    assert signature_path is not None and signature_path.exists()
    assert receipt_path is not None and receipt_path.exists()
    signature_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert signature_receipt["run_kind"] == "signature-gen"
    assert signature_receipt["hash"] == data["output_hash"]
    assert str(signature_receipt["output_path"]).endswith(signature_path.name)

    r2 = client.post(
        "/module",
        json={
            "name": "Summarizer",
            "description": "Summarizes text",
            "inputs": ["text"],
            "outputs": ["summary"],
            "template_version": "simple-v1",
        },
    )
    assert r2.status_code == 200
    data2 = r2.json()
    assert "class Summarizer(dspy.Module)" in data2["code"]
    module_path = _artifact_path(output_root, data2["output_path"])
    module_receipt_path = _artifact_path(output_root, data2["receipt_path"])
    assert module_path is not None and module_path.exists()
    assert module_receipt_path is not None and module_receipt_path.exists()
    module_receipt = json.loads(module_receipt_path.read_text(encoding="utf-8"))
    assert module_receipt["run_kind"] == "module-gen"
    assert module_receipt["hash"] == data2["output_hash"]
    assert str(module_receipt["output_path"]).endswith(module_path.name)
    assert module_receipt["run_summary"]["backend"] == "synthesis_runtime"

    mermaid = "\n".join(["graph TD", "  A[Start] --> B{Done}"])
    r3 = client.post(
        "/mermaid",
        json={"mermaid": mermaid, "name": "t1", "variants": ["predict"]},
    )
    assert r3.status_code == 200
    data3 = r3.json()
    assert data3["name"] == "t1"
    assert any("program_" in p for p in data3["produced"])
    assert data3["output_dir"]
    mermaid_output_dir = _artifact_path(output_root, data3["output_dir"])
    assert mermaid_output_dir is not None and mermaid_output_dir.exists()
    assert all(
        artifact_path is not None and artifact_path.exists()
        for artifact_path in (
            _artifact_path(output_root, path) for path in data3["produced"]
        )
    )
    manifest_path = _artifact_path(output_root, data3["manifest_path"])
    assert manifest_path is None or manifest_path.exists()


def test_server_module_rejects_invalid_field_names(monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/module",
        json={
            "name": "Summarizer",
            "description": "Summarizes text",
            "inputs": ["first-name"],
            "outputs": ["summary"],
            "template_version": "simple-v1",
        },
    )

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"


def test_server_signature_and_module_degrade_when_artifact_persistence_fails(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    bad_output_root = tmp_path / "not-a-dir"
    bad_output_root.write_text("x", encoding="utf-8")
    monkeypatch.setenv("DSPX_SERVER_OUTPUT_DIR", str(bad_output_root))
    monkeypatch.setenv("DSPX_SYNTHESIS_DIR", str(tmp_path / "synthesis"))
    monkeypatch.setenv(
        "DSPX_MODULE_SYNTHESIS_EVIDENCE_RECEIPTS_PATH",
        str(tmp_path / "receipts"),
    )
    monkeypatch.setenv(
        "DSPX_MODULE_SYNTHESIS_EVIDENCE_ORACLE_INDEX_PATH",
        str(tmp_path / "oracle" / "coordinates.db"),
    )
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)

    signature = client.post("/signature", json={"prompt": "Extract names"})
    assert signature.status_code == 200
    signature_payload = signature.json()
    assert signature_payload["output_path"] is None
    assert signature_payload["receipt_path"] is None
    assert signature_payload["output_hash"]

    module = client.post(
        "/module",
        json={
            "name": "Summarizer",
            "description": "Summarizes text",
            "inputs": ["text"],
            "outputs": ["summary"],
        },
    )
    assert module.status_code == 200
    module_payload = module.json()
    assert module_payload["output_path"] is None
    assert module_payload["receipt_path"] is None
    assert module_payload["output_hash"]


def test_code_output_path_uses_unique_suffix_when_timestamp_collides(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DSPX_SERVER_OUTPUT_DIR", str(tmp_path / "server-output"))
    monkeypatch.setattr(server_app, "_timestamp_token", lambda: "fixed-ts")

    left = server_app._code_output_path("signature", "Sig")
    right = server_app._code_output_path("signature", "Sig")

    assert left != right
    assert left.name != right.name


def test_server_mermaid_reports_artifact_persistence_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
    bad_output_root = tmp_path / "not-a-dir"
    bad_output_root.write_text("x", encoding="utf-8")
    monkeypatch.setenv("DSPX_SERVER_OUTPUT_DIR", str(bad_output_root))
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/mermaid",
        json={
            "mermaid": "\n".join(["graph TD", "  A[Start] --> B{Done}"]),
            "name": "broken",
            "variants": ["predict"],
        },
    )

    assert response.status_code == 500
    payload = response.json()
    assert payload["error"] == "artifact_persistence_failed"
    assert "failed to persist mermaid artifacts" in payload["detail"]

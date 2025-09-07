from __future__ import annotations

from fastapi.testclient import TestClient

from dspx.server.app import create_app


def test_server_signature_and_module_and_mermaid(monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_ENABLE", "0")
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

    mermaid = "\n".join(["graph TD", "  A[Start] --> B{Done}"])
    r3 = client.post(
        "/mermaid",
        json={"mermaid": mermaid, "name": "t1", "variants": ["predict"]},
    )
    assert r3.status_code == 200
    data3 = r3.json()
    assert data3["name"] == "t1"
    assert any("program_" in p for p in data3["produced"])  # program_predict.py

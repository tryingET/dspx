# summary: "Tests cache materialization for signature, codegen, and module service calls."
# read_when:
#   - "You are changing service-level cache controls, cache directories, or generated artifact persistence."

from __future__ import annotations

from pathlib import Path

from dspx.dtos import SignatureGenRequest, CodegenRequest, ModuleSpec
from dspx.services.signatures_service import run_generate_dto as sig_run
from dspx.services.codegen_service import run_dto as codegen_run
from dspx.services.module_service import run_generate as module_run


def test_signature_service_caches(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    req = SignatureGenRequest(
        prompt="Echo", template_version="simple-v1", options={"class_name": "Sig_Echo"}
    )
    res = sig_run(req)
    assert "class Sig_Echo(dspy.Signature):" in res.code
    # Cache file should exist under cache/signature
    sig_cache_dir = tmp_path / "cache" / "signature"
    assert any(p.suffix == ".json" for p in sig_cache_dir.glob("*.json"))


def test_codegen_service_caches(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    req = CodegenRequest(
        spec='A CLI that prints "ok"', language="python", template_version="simple-v1"
    )
    res = codegen_run(req)
    assert 'if __name__ == "__main__"' in res.code
    cg_cache_dir = tmp_path / "cache" / "codegen"
    assert any(p.suffix == ".json" for p in cg_cache_dir.glob("*.json"))


def test_module_service_caches(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DSPX_CACHE_ENABLE", "1")
    monkeypatch.setenv("DSPX_CACHE_DIR", str(tmp_path / "cache"))
    spec = ModuleSpec(
        name="ModA",
        description="desc",
        inputs=["context"],
        outputs=["output"],
        options={"template_version": "simple-v1"},
    )
    art = module_run(spec, use_signature=True)
    assert "class ModA(dspy.Module):" in art.code
    m_cache = tmp_path / "cache" / "module"
    assert any(p.suffix == ".json" for p in m_cache.glob("*.json"))

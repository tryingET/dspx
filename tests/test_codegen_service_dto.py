# summary: "Tests template-only Python code generation through the codegen service DTO boundary."
# read_when:
#   - "You are changing CodegenRequest handling or deterministic Python template generation."

from __future__ import annotations

from dspx.dtos import CodegenRequest
from dspx.services.codegen_service import run_dto


def test_codegen_service_dto_template_only_python() -> None:
    req = CodegenRequest(
        spec='A CLI that prints "smoke ok"',
        language="python",
        template_version="simple-v1",
        options={},
    )
    res = run_dto(req)
    assert 'if __name__ == "__main__"' in res.code
    assert "smoke ok" in res.code

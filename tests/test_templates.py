# summary: "Tests minimal DSPy signature rendering and signature-generation prompt formatting."
# read_when:
#   - "Changing simple signature templates, their default fields, or signature prompt wording."

from __future__ import annotations

from dspx.templates import render_simple_signature, format_signature_prompt


def test_render_simple_signature_minimal() -> None:
    code = render_simple_signature("Sig_Test", "Do a thing")
    assert "class Sig_Test(dspy.Signature):" in code
    assert "Do a thing" in code
    assert "context: str" in code and "output: str" in code


def test_format_signature_prompt_v1_wraps() -> None:
    p = format_signature_prompt("Extract names")
    assert "You are generating a DSPy Signature class" in p
    assert "Task: Extract names" in p

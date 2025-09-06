from __future__ import annotations

from dspx.dtos import ModuleSpec
from dspx.services.module_service import run_generate


def test_module_service_simple_no_signature() -> None:
    spec = ModuleSpec(
        name="Summarizer",
        description="Summarizes text",
        inputs=["text"],
        outputs=["summary"],
        options={"template_version": "simple-v1"},
    )
    art = run_generate(spec, use_signature=False)
    assert "class Summarizer(dspy.Module):" in art.code
    assert "self.predict = dspy.Predict('text -> summary')" in art.code
    assert "def forward(self, text: str)" in art.code


def test_module_service_simple_with_signature() -> None:
    spec = ModuleSpec(
        name="Intent",
        description="Extracts intent from context",
        inputs=["context"],
        outputs=["output"],
        options={"template_version": "simple-v1"},
    )
    art = run_generate(spec, use_signature=True)
    assert "class Sig_Intent(dspy.Signature):" in art.code
    assert "self.predict = dspy.Predict(Sig_Intent)" in art.code
    assert "def forward(self, context: str)" in art.code

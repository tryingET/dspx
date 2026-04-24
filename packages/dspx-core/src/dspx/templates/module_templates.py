from __future__ import annotations

from typing import Iterable, List, Optional


def _sanitize_ident(name: str, fallback: str = "Module") -> str:
    import re

    s = re.sub(r"\W+", "_", name.strip()) or fallback
    if s[0].isdigit():
        s = f"_{s}"
    return s


def render_module_skeleton(
    name: str,
    inputs: Iterable[str],
    outputs: Iterable[str],
    description: Optional[str] = None,
    *,
    signature_code: Optional[str] = None,
    signature_class_name: Optional[str] = None,
    signature_import: Optional[str] = None,
) -> str:
    """Render a minimal deterministic dspy.Module skeleton.

    - If `signature_class_name` and `signature_import` are provided, imports the
      signature and uses `dspy.Predict(Signature)` in the module.
    - If `signature_class_name` and `signature_code` are provided, embeds the signature
      and uses `dspy.Predict(Signature)` in the module.
    - Otherwise, uses a prompt string like "a, b -> x, y".
    """
    cls = _sanitize_ident(name or "Module")
    ins: List[str] = [i for i in inputs]
    outs: List[str] = [o for o in outputs]
    ins = ins or ["context"]
    outs = outs or ["output"]
    weights = {k: 1.0 for k in outs}

    header: List[str] = []
    header.append("import dspy")
    if signature_import and signature_class_name:
        header.append(signature_import)
        header.append("")
    else:
        header.append("")
        if signature_code and signature_class_name:
            header.append(signature_code.strip())
            header.append("")

    body: List[str] = []
    doc = (description or f"Auto-generated module {cls}").replace("\n", " ")
    body.append(f"class {cls}(dspy.Module):")
    body.append(f'    """{doc}"""')
    body.append("")
    body.append("    def __init__(self, use_cot: bool = False) -> None:")
    body.append("        super().__init__()")
    if signature_class_name:
        body.append(f"        self.predict = dspy.Predict({signature_class_name})")
    else:
        io_sig = ", ".join(ins) + " -> " + ", ".join(outs)
        body.append(f"        self.predict = dspy.Predict({io_sig!r})")
    body.append("")

    # Build forward
    args_sig = ", ".join(f"{x}: str" for x in ins)
    body.append(f"    def forward(self, {args_sig}) -> dspy.Prediction:")
    call_args = ", ".join(f"{x}={x}" for x in ins)
    if call_args:
        body.append(f"        pred = self.predict({call_args})")
    else:
        body.append("        pred = self.predict()")
    body.append("        return pred")

    body.append("")
    body.append("")
    body.append("def build_student(*, use_cot: bool = False) -> dspy.Module:")
    body.append(f"    return {cls}(use_cot=use_cot)")
    body.append("")
    body.append("def io_spec() -> dict[str, list[str]]:")
    body.append(f"    return {{'inputs': {ins!r}, 'outputs': {outs!r}}}")
    body.append("")
    body.append("def output_weights() -> dict[str, float]:")
    body.append(f"    return {weights!r}")
    body.append("")
    body.append(
        "def normalize_output("
        "key: str, gold: str, pred: str, pred_name: str | None = None, pred_trace: object | None = None"
        ") -> tuple[str, str]:"
    )
    body.append("    return gold, pred")

    code = "\n".join(header + [""] + body)
    return code if code.endswith("\n") else code + "\n"

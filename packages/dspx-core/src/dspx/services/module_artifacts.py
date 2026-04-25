from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
import keyword
import re

from dspx.cache import make_key
from dspx.dtos import ModuleSpec
from dspx.templates.module_templates import render_module_skeleton
from dspx.templates.signature_templates import render_simple_signature

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def sig_class_name(module_name: str) -> str:
    s = re.sub(r"\W+", "_", module_name.strip() or "Module")
    if s[0].isdigit():
        s = f"_{s}"
    return f"Sig_{s}"


def _invalid_identifier(name: str) -> bool:
    return not _IDENTIFIER_RE.match(name) or keyword.iskeyword(name)


def validate_module_spec_identifiers(spec: ModuleSpec) -> None:
    invalid: list[str] = []
    module_name = str(spec.name).strip()
    if not module_name or _invalid_identifier(module_name):
        invalid.append(f"module:{module_name or '<empty>'}")

    seen_inputs: set[str] = set()
    seen_outputs: set[str] = set()

    for role, values, seen in (
        ("input", spec.inputs or [], seen_inputs),
        ("output", spec.outputs or [], seen_outputs),
    ):
        for raw in values:
            name = str(raw).strip()
            if not name:
                invalid.append(f"{role}:<empty>")
                continue
            if _invalid_identifier(name):
                invalid.append(f"{role}:{name}")
                continue
            if name in seen:
                invalid.append(f"duplicate_{role}:{name}")
                continue
            seen.add(name)

    overlap = seen_inputs & seen_outputs
    for name in sorted(overlap):
        invalid.append(f"input_output_overlap:{name}")

    if invalid:
        detail = ", ".join(invalid)
        raise ValueError(
            "Module name and inputs/outputs must be unique Python identifiers; "
            f"invalid entries: {detail}"
        )


def template_version(spec: ModuleSpec) -> Optional[str]:
    value = (
        (spec.options or {}).get("template_version")
        if hasattr(spec, "options")
        else None
    )
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


def module_cache_key(
    spec: ModuleSpec,
    *,
    use_signature: bool,
    template_version: Optional[str],
) -> str:
    payload: dict[str, Any] = {
        "kind": "module",
        "name": spec.name,
        "description": spec.description or "",
        "inputs": list(spec.inputs or []),
        "outputs": list(spec.outputs or []),
        "use_signature": bool(use_signature),
        "template_version": template_version or "v1",
    }
    options = spec.options or {}
    if options.get("signature_class_name"):
        payload["signature_class_name"] = options["signature_class_name"]
    if options.get("signature_import"):
        payload["signature_import"] = options["signature_import"]
    return make_key(payload)


def _insert_after_first_blank_line(code: str, block: str) -> str:
    lines = code.splitlines()
    if not lines:
        return block if block.endswith("\n") else block + "\n"
    if len(lines) > 1 and lines[0].startswith("import ") and lines[1] == "":
        new_lines = [lines[0], "", *block.splitlines(), *lines[2:]]
    else:
        new_lines = [*block.splitlines(), *lines]
    rendered = "\n".join(new_lines)
    return rendered if rendered.endswith("\n") else rendered + "\n"


def with_trace_comment(code: str) -> str:
    return _insert_after_first_blank_line(
        code,
        "# Ranked synthesis candidate variant\nMODULE_VARIANT = 'traceable'",
    )


def with_helper_docstrings(code: str) -> str:
    replacements = {
        "def build_student(*, use_cot: bool = False) -> dspy.Module:\n": (
            "def build_student(*, use_cot: bool = False) -> dspy.Module:\n"
            '    """Construct the generated module for runtime selection."""\n'
        ),
        "def io_spec() -> dict[str, list[str]]:\n": (
            "def io_spec() -> dict[str, list[str]]:\n"
            '    """Return the declared module IO contract."""\n'
        ),
        "def output_weights() -> dict[str, float]:\n": (
            "def output_weights() -> dict[str, float]:\n"
            '    """Provide deterministic output weighting for evaluation."""\n'
        ),
        "def normalize_output(\n": ("def normalize_output(\n"),
    }
    updated = code
    for old, new in replacements.items():
        if old in updated and new not in updated:
            updated = updated.replace(old, new, 1)
    needle = ") -> tuple[str, str]:\n"
    doc = (
        ") -> tuple[str, str]:\n"
        '    """Normalize gold/pred pairs for deterministic checks."""\n'
    )
    if needle in updated and doc not in updated:
        updated = updated.replace(needle, doc, 1)
    return updated


def _signature_code_for_embedding(code: str) -> str:
    lines = code.splitlines()
    if lines and lines[0] == "import dspy":
        lines = lines[1:]
        if lines and lines[0] == "":
            lines = lines[1:]
    return "\n".join(lines).strip()


def render_seed_module_code(
    spec: ModuleSpec,
    *,
    base_code: str | None = None,
    use_signature: bool,
    template_version: Optional[str],
) -> str:
    simple = isinstance(template_version, str) and template_version.startswith("simple")
    if base_code is not None and not simple:
        return base_code

    desc = spec.description or ""
    inputs = list(spec.inputs or [])
    outputs = list(spec.outputs or [])
    sig_code = None
    sig_name = None
    sig_import = None
    options = spec.options or {}
    if use_signature:
        sig_name = str(options.get("signature_class_name") or sig_class_name(spec.name))
        sig_import_raw = options.get("signature_import")
        sig_import = str(sig_import_raw) if sig_import_raw else None
        if not sig_import:
            sig_code = _signature_code_for_embedding(
                render_simple_signature(
                    sig_name,
                    desc or f"Signature for {spec.name}",
                    inputs=inputs,
                    outputs=outputs,
                )
            )
    return render_module_skeleton(
        spec.name,
        inputs,
        outputs,
        desc,
        signature_code=sig_code,
        signature_class_name=sig_name,
        signature_import=sig_import,
    )


def candidate_sources(
    spec: ModuleSpec,
    *,
    code: str,
    use_signature: bool,
    template_version: Optional[str],
) -> list[dict[str, Any]]:
    seed_code = render_seed_module_code(
        spec,
        base_code=code,
        use_signature=use_signature,
        template_version=template_version,
    )
    raw_variants = [
        (
            "baseline",
            "Baseline deterministic scaffold",
            seed_code,
            1.0,
            "Preserve the compact baseline render as the control candidate.",
        ),
        (
            "traceable",
            "Traceable scaffold",
            with_trace_comment(seed_code),
            2.0,
            "Prefer candidates that expose an explicit trace marker for receipts and replay.",
        ),
        (
            "explainable_helpers",
            "Explainable helper scaffold",
            with_helper_docstrings(seed_code),
            3.0,
            "Prefer candidates that make helper intent explicit for replay and inspection.",
        ),
    ]

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for variant_id, label, variant_code, bonus, basis in raw_variants:
        if variant_code in seen:
            continue
        seen.add(variant_code)
        deduped.append(
            {
                "code": variant_code,
                "artifact_metadata": {
                    "variant_id": variant_id,
                    "variant_label": label,
                },
                "candidate_metadata": {
                    "variant_id": variant_id,
                    "variant_label": label,
                    "selection_bonus": bonus,
                    "selection_basis": basis,
                },
                "lineage": {
                    "variant_id": variant_id,
                    "variant_origin": "deterministic_template_variant",
                },
            }
        )
    return deduped


def selected_candidate_code(bundle: Any, fallback: str) -> str:
    selected_candidate_id = (
        bundle.promotion_shell.selected_candidate_id
        if bundle.promotion_shell is not None
        else bundle.promotion_decision.candidate_id
    )
    if selected_candidate_id is None:
        return fallback
    for workspace in bundle.candidate_workspaces:
        if workspace.candidate_id == selected_candidate_id:
            path = Path(workspace.artifact_path)
            if path.exists():
                return path.read_text(encoding="utf-8")
    return fallback

# summary: "Generates, normalizes, validates, scores, caches, and observes DSPy signature source from templates or language models."
# read_when:
#   - "Changing signature generation strategies, validation/scoring, caching, provider use, or quality telemetry."

from __future__ import annotations

import ast
import json
import keyword
import os as _os
import re
from dataclasses import dataclass
from typing import Any, Optional

import dspy

from dspx.cache import cache_enabled, make_key, read as cache_read, write as cache_write
from dspx.config_loader import load_config_env
from dspx.dtos import SignatureGenRequest, SignatureGenResult
from dspx.lm_base import LMBase
from dspx.provider_registry import (
    capabilities as provider_capabilities,
    create_from_env,
    ensure_default_providers,
)
from dspx.templates import (
    format_signature_spec_prompt,
    render_signature_from_spec,
    render_simple_signature,
)
from dspx.tracing import enable_mlflow_from_env
from dspx.generated_code_guard import smoke_signature_code
from dspx.services.signature_quality import append_quality_event

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_python_identifier(name: str, *, role: str) -> None:
    value = str(name or "").strip()
    if not value or not _IDENTIFIER_RE.match(value) or keyword.iskeyword(value):
        raise ValueError(f"invalid_{role}_identifier:{name}")


def _validate_simple_signature_contract(
    *, class_name: str, inputs: list[str] | None, outputs: list[str] | None
) -> None:
    _validate_python_identifier(class_name, role="class_name")
    input_names = [str(item) for item in (inputs or []) if str(item).strip()]
    output_names = [str(item) for item in (outputs or []) if str(item).strip()]
    for name in input_names:
        _validate_python_identifier(name, role="input")
    for name in output_names:
        _validate_python_identifier(name, role="output")

    duplicate_inputs = sorted(
        {name for name in input_names if input_names.count(name) > 1}
    )
    duplicate_outputs = sorted(
        {name for name in output_names if output_names.count(name) > 1}
    )
    overlap = sorted(set(input_names).intersection(output_names))
    if duplicate_inputs:
        raise ValueError(f"duplicate_input_fields:{','.join(duplicate_inputs)}")
    if duplicate_outputs:
        raise ValueError(f"duplicate_output_fields:{','.join(duplicate_outputs)}")
    if overlap:
        raise ValueError(f"input_output_field_overlap:{','.join(overlap)}")


@dataclass
class _SignatureCandidate:
    attempt: int
    source: str
    raw_text: str
    code: str
    signature_name: str | None
    score: float
    valid: bool
    ast_valid: bool
    smoke_valid: bool
    errors: list[str]


def _extract_code_block(text: str) -> str:
    fence = re.compile(r"```[\w+-]*\n([\s\S]*?)\n```", re.MULTILINE)
    m = fence.search(text or "")
    if m:
        return m.group(1).strip()
    return (text or "").strip()


def _extract_signature_name(code: str) -> str | None:
    m = re.search(
        r"^class\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*dspy\.Signature\s*\)\s*:",
        code or "",
        re.M,
    )
    if m:
        return m.group(1)
    return None


def _extract_json_blob(text: str) -> str | None:
    src = (text or "").strip()
    if not src:
        return None

    # 1) fenced json block
    m = re.search(r"```json\s*\n([\s\S]*?)\n```", src, re.I)
    if m:
        return m.group(1).strip()

    # 2) generic fence body
    m = re.search(r"```[\w+-]*\s*\n([\s\S]*?)\n```", src)
    if m:
        body = m.group(1).strip()
        if body.startswith("{") and body.endswith("}"):
            return body

    # 3) raw json-ish body
    if src.startswith("{") and src.endswith("}"):
        return src

    # 4) heuristic: first brace to last brace
    i = src.find("{")
    j = src.rfind("}")
    if i >= 0 and j > i:
        return src[i : j + 1].strip()

    return None


def _sanitize_identifier(name: str, default: str, *, class_name: bool = False) -> str:
    cleaned = re.sub(r"\W+", "_", (name or "").strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned:
        cleaned = default
    if cleaned and cleaned[0].isdigit():
        cleaned = f"_{cleaned}"
    if class_name:
        parts = [p for p in cleaned.split("_") if p]
        cleaned = "".join(p[:1].upper() + p[1:] for p in parts) or default
    return cleaned


def _sanitize_type_hint(type_hint: str | None) -> str:
    t = (type_hint or "str").strip()
    if not t:
        return "str"

    if t.startswith("Optional[") and t.endswith("]"):
        inner = _sanitize_type_hint(t[len("Optional[") : -1])
        return f"Optional[{inner}]"

    if t.startswith("Literal[") and t.endswith("]"):
        body = t[len("Literal[") : -1].strip()
        vals = re.findall(r"'([^']+)'|\"([^\"]+)\"", body)
        flat = [a or b for a, b in vals if (a or b)]
        if not flat:
            return "str"
        encoded = ", ".join(repr(v) for v in flat)
        return f"Literal[{encoded}]"

    if t.startswith("list[") and t.endswith("]"):
        inner = _sanitize_type_hint(t[len("list[") : -1])
        return f"list[{inner}]"

    if t.startswith("dict[") and t.endswith("]"):
        return "dict[str, Any]"

    if t in {"str", "int", "float", "bool", "Any"}:
        return t

    return "str"


def _force_class_name(code: str, expected: str) -> str:
    src = code or ""
    m = re.search(
        r"^class\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*dspy\.Signature\s*\)\s*:",
        src,
        re.M,
    )
    if not m:
        return src
    current = m.group(1)
    if current == expected:
        return src
    return src.replace(
        f"class {current}(dspy.Signature):", f"class {expected}(dspy.Signature):", 1
    )


def _normalize_field_entry(
    raw: Any,
    *,
    role: str,
    index: int,
    default_prefix: str,
) -> dict[str, str]:
    if isinstance(raw, str):
        name = _sanitize_identifier(raw, f"{default_prefix}_{index}")
        return {
            "name": name,
            "type": "str",
            "desc": f"{name.replace('_', ' ')} ({role})",
        }

    if not isinstance(raw, dict):
        name = f"{default_prefix}_{index}"
        return {
            "name": name,
            "type": "str",
            "desc": f"{name.replace('_', ' ')} ({role})",
        }

    name_raw = str(raw.get("name") or raw.get("field") or f"{default_prefix}_{index}")
    name = _sanitize_identifier(name_raw, f"{default_prefix}_{index}")
    desc = str(raw.get("desc") or raw.get("description") or "").strip()
    if not desc:
        desc = f"{name.replace('_', ' ')} ({role})"

    return {
        "name": name,
        "type": _sanitize_type_hint(str(raw.get("type") or "str")),
        "desc": desc,
    }


def _dedupe_fields(fields: list[dict[str, str]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for f in fields:
        name = f.get("name") or "field"
        if name not in seen:
            seen.add(name)
            out.append(f)
            continue
        suffix = 2
        while f"{name}_{suffix}" in seen:
            suffix += 1
        cloned = dict(f)
        cloned["name"] = f"{name}_{suffix}"
        seen.add(cloned["name"])
        out.append(cloned)
    return out


def _normalize_signature_spec(
    raw: dict[str, Any],
    *,
    class_name_hint: str,
    fallback_description: str,
    enforce_class_name: bool,
) -> dict[str, Any]:
    raw_name = str(raw.get("class_name") or raw.get("name") or class_name_hint)
    class_name = _sanitize_identifier(
        class_name_hint if enforce_class_name else raw_name,
        class_name_hint,
        class_name=True,
    )

    description = str(
        raw.get("description") or raw.get("docstring") or fallback_description or ""
    ).strip()
    if not description:
        description = "Auto-generated Signature"

    inputs_raw = raw.get("inputs") or raw.get("input_fields") or []
    outputs_raw = raw.get("outputs") or raw.get("output_fields") or []

    # compatibility: single fields list with role tags
    if not inputs_raw and not outputs_raw and isinstance(raw.get("fields"), list):
        in_acc: list[Any] = []
        out_acc: list[Any] = []
        for item in raw.get("fields") or []:
            if (
                isinstance(item, dict)
                and str(item.get("role") or "").lower() == "output"
            ):
                out_acc.append(item)
            else:
                in_acc.append(item)
        inputs_raw = in_acc
        outputs_raw = out_acc

    inputs = [
        _normalize_field_entry(it, role="input", index=i + 1, default_prefix="context")
        for i, it in enumerate(inputs_raw if isinstance(inputs_raw, list) else [])
    ]
    outputs = [
        _normalize_field_entry(it, role="output", index=i + 1, default_prefix="output")
        for i, it in enumerate(outputs_raw if isinstance(outputs_raw, list) else [])
    ]

    inputs = _dedupe_fields(inputs)
    outputs = _dedupe_fields(outputs)

    if not inputs:
        inputs = [
            {
                "name": "context",
                "type": "str",
                "desc": "Upstream context for this step",
            }
        ]
    if not outputs:
        outputs = [
            {
                "name": "output",
                "type": "str",
                "desc": "Result of this step",
            }
        ]

    return {
        "class_name": class_name,
        "description": description,
        "inputs": inputs,
        "outputs": outputs,
    }


def _parse_signature_spec(raw_text: str) -> dict[str, Any] | None:
    blob = _extract_json_blob(raw_text)
    if not blob:
        return None
    try:
        data = json.loads(blob)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return data


def build_signature_strategy_prompt(
    prompt: str,
    *,
    class_name_hint: str,
    template_version: str,
    json_mode: bool,
    constraints: list[str] | None = None,
    feedback: list[str] | None = None,
) -> str:
    version = "spec-v1"
    if template_version and template_version.startswith("spec-"):
        version = template_version
    return format_signature_spec_prompt(
        prompt,
        class_name_hint=class_name_hint,
        version=version,
        json_mode=json_mode,
        constraints=constraints,
        feedback=feedback,
    )


def validate_signature_code(
    code: str,
    *,
    expected_class_name: str | None = None,
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    src = (code or "").strip()
    if not src:
        return False, ["empty_code"]

    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return False, [f"syntax_error:{e.msg}"]

    sig_classes: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for base in node.bases:
            if isinstance(base, ast.Attribute) and base.attr == "Signature":
                sig_classes.append(node.name)
                break
            if isinstance(base, ast.Name) and base.id == "Signature":
                sig_classes.append(node.name)
                break

    if not sig_classes:
        errors.append("missing_signature_class")

    if expected_class_name and expected_class_name not in sig_classes:
        errors.append(f"expected_class_missing:{expected_class_name}")

    if "InputField" not in src:
        errors.append("missing_input_field")
    if "OutputField" not in src:
        errors.append("missing_output_field")

    try:
        compile(tree, "<generated_signature>", "exec")
    except Exception as e:
        errors.append(f"compile_error:{e}")

    return (len(errors) == 0), errors


def _smoke_signature_code(
    code: str,
    *,
    expected_class_name: str | None = None,
) -> tuple[bool, list[str]]:
    return smoke_signature_code(
        code,
        expected_class_name=expected_class_name or _extract_signature_name(code),
    )


def score_signature_code(
    code: str,
    *,
    expected_class_name: str | None = None,
) -> float:
    score = 0.0

    ok_ast, ast_errors = validate_signature_code(
        code,
        expected_class_name=expected_class_name,
    )
    if ok_ast:
        score += 60.0
    else:
        score -= float(len(ast_errors)) * 8.0

    sig_name = _extract_signature_name(code)
    if sig_name:
        score += 8.0
    if expected_class_name and sig_name == expected_class_name:
        score += 8.0

    if "InputField" in code:
        score += 6.0
    if "OutputField" in code:
        score += 6.0

    ok_smoke, _ = _smoke_signature_code(code, expected_class_name=expected_class_name)
    if ok_smoke:
        score += 12.0

    # Encourage non-trivial specs over fallback shape.
    if "context: str = dspy.InputField" not in code:
        score += 3.0
    if "output: str = dspy.OutputField" not in code:
        score += 3.0

    return score


def _autofix_signature_code(
    code: str,
    *,
    class_name_hint: str,
    fallback_description: str,
    enforce_class_name: bool,
) -> str:
    src = (code or "").strip()
    if not src:
        return render_simple_signature(class_name_hint, fallback_description)

    if _extract_signature_name(src) is None:
        return render_simple_signature(class_name_hint, fallback_description)

    if enforce_class_name:
        src = _force_class_name(src, class_name_hint)

    if "import dspy" not in src:
        src = "import dspy\n\n" + src

    expected = class_name_hint if enforce_class_name else None
    ok, _ = validate_signature_code(src, expected_class_name=expected)
    if not ok:
        return render_simple_signature(class_name_hint, fallback_description)

    return src


def _candidate_from_raw(
    raw_text: str,
    *,
    attempt: int,
    class_name_hint: str,
    fallback_description: str,
    enforce_class_name: bool,
) -> _SignatureCandidate:
    source = "spec"
    signature_name: str | None = None

    raw_spec = _parse_signature_spec(raw_text)
    if raw_spec is not None:
        norm = _normalize_signature_spec(
            raw_spec,
            class_name_hint=class_name_hint,
            fallback_description=fallback_description,
            enforce_class_name=enforce_class_name,
        )
        code = render_signature_from_spec(
            norm["class_name"],
            norm["description"],
            inputs=norm["inputs"],
            outputs=norm["outputs"],
        )
        signature_name = str(norm["class_name"])
    else:
        extracted = _extract_code_block(raw_text)
        parsed_name = _extract_signature_name(extracted)
        if parsed_name is None:
            source = "fallback"
            code = render_simple_signature(class_name_hint, fallback_description)
            signature_name = class_name_hint
        else:
            source = "code"
            code = extracted
            signature_name = parsed_name

    code = _autofix_signature_code(
        code,
        class_name_hint=class_name_hint,
        fallback_description=fallback_description,
        enforce_class_name=enforce_class_name,
    )
    signature_name = _extract_signature_name(code) or class_name_hint

    expected = class_name_hint if enforce_class_name else None
    ok_ast, ast_errors = validate_signature_code(code, expected_class_name=expected)
    ok_smoke, smoke_errors = _smoke_signature_code(code, expected_class_name=expected)
    errors = [*ast_errors, *smoke_errors]

    return _SignatureCandidate(
        attempt=attempt,
        source=source,
        raw_text=raw_text,
        code=code,
        signature_name=signature_name,
        score=score_signature_code(code, expected_class_name=expected),
        valid=ok_ast and ok_smoke,
        ast_valid=ok_ast,
        smoke_valid=ok_smoke,
        errors=errors,
    )


def _resolve_attempts(options: dict[str, Any] | None = None) -> int:
    raw = None
    if isinstance(options, dict):
        raw = options.get("max_attempts")
    if raw is None:
        raw = _os.getenv("DSPX_SIGNATURE_MAX_ATTEMPTS", "1")
    try:
        n = int(raw)
    except Exception:
        n = 1
    return max(1, min(6, n))


def _candidate_quality_summary(
    candidates: list[_SignatureCandidate],
    *,
    max_attempts: int,
    fallback_used: bool,
) -> dict[str, Any]:
    total = len(candidates)
    validation_pass_count = sum(1 for c in candidates if c.ast_valid)
    smoke_pass_count = sum(1 for c in candidates if c.smoke_valid)

    return {
        "attempts_used": int(total),
        "max_attempts": int(max_attempts),
        "attempts_exhausted": bool(total >= max(1, int(max_attempts))),
        "fallback_used": bool(fallback_used),
        "validation_pass_count": int(validation_pass_count),
        "validation_total": int(total),
        "validation_pass_rate": (
            float(validation_pass_count) / float(total) if total > 0 else 0.0
        ),
        "smoke_pass_count": int(smoke_pass_count),
        "smoke_total": int(total),
        "smoke_pass_rate": (
            float(smoke_pass_count) / float(total) if total > 0 else 0.0
        ),
    }


def _generate_native_payload(
    *,
    prompt_for_model: str,
    fallback_description: str,
    class_name_hint: str,
    json_mode: bool,
    max_attempts: int,
    enforce_class_name: bool,
) -> dict[str, Any]:
    predictor = dspy.Predict("task -> spec_json")
    candidates: list[_SignatureCandidate] = []

    for idx in range(max(1, int(max_attempts))):
        attempt_prompt = (
            prompt_for_model
            + f"\n# Attempt {idx + 1}/{max_attempts}: prioritize schema correctness, then completeness.\n"
        )
        result = predictor(task=attempt_prompt)
        if hasattr(result, "spec_json"):
            raw_text = str(getattr(result, "spec_json") or "")
        elif hasattr(result, "code"):
            raw_text = str(getattr(result, "code") or "")
        else:
            raw_text = str(result)

        cand = _candidate_from_raw(
            raw_text,
            attempt=idx + 1,
            class_name_hint=class_name_hint,
            fallback_description=fallback_description,
            enforce_class_name=enforce_class_name,
        )
        candidates.append(cand)

        # Early stop on high-quality non-fallback candidates.
        if cand.valid and cand.source != "fallback" and cand.score >= 88.0:
            break

    if not candidates:
        code = render_simple_signature(class_name_hint, fallback_description)
        quality = _candidate_quality_summary(
            candidates,
            max_attempts=max_attempts,
            fallback_used=True,
        )
        return {
            "code": code,
            "signature_name": class_name_hint,
            "task_description": fallback_description,
            "backend": "native",
            "strategy": "spec-first",
            "candidate_source": "fallback",
            "candidate_score": 0.0,
            "json_mode": bool(json_mode),
            "candidate_valid": False,
            **quality,
        }

    best = max(
        candidates,
        key=lambda c: (
            1 if c.valid else 0,
            c.score,
            1 if c.source == "spec" else (0 if c.source == "code" else -1),
            -c.attempt,
        ),
    )

    quality = _candidate_quality_summary(
        candidates,
        max_attempts=max_attempts,
        fallback_used=best.source == "fallback",
    )

    return {
        "code": best.code,
        "signature_name": best.signature_name,
        "task_description": fallback_description,
        "backend": "native",
        "strategy": "spec-first",
        "candidate_source": best.source,
        "candidate_score": float(best.score),
        "json_mode": bool(json_mode),
        "candidate_valid": bool(best.valid),
        "candidate_errors": list(best.errors),
        **quality,
    }


def run_generate(prompt: str, *, lm: Optional[LMBase] = None) -> str:
    """Generate a signature class code string from a natural-language prompt."""
    load_config_env()
    enable_mlflow_from_env()

    ensure_default_providers()
    active_lm = lm or create_from_env()
    dspy.configure(lm=active_lm)

    provider_name = _os.getenv("DSPX_PROVIDER", "pi-rpc")
    try:
        caps = getattr(active_lm, "capabilities", None) or provider_capabilities(
            provider_name
        )
        json_mode = bool(getattr(caps, "json_mode", False))
    except Exception:
        json_mode = False

    attempts = _resolve_attempts({})
    class_name_hint = "GeneratedSignature"
    payload = _generate_native_payload(
        prompt_for_model=build_signature_strategy_prompt(
            prompt,
            class_name_hint=class_name_hint,
            template_version="v1",
            json_mode=json_mode,
        ),
        fallback_description=prompt,
        class_name_hint=class_name_hint,
        json_mode=json_mode,
        max_attempts=attempts,
        enforce_class_name=False,
    )
    return str(payload.get("code") or "")


def run_generate_dto(
    req: SignatureGenRequest, *, lm: Optional[LMBase] = None
) -> SignatureGenResult:
    """DTO-oriented variant that returns structured result.

    If `req.template_version` starts with 'simple', a deterministic template is used
    (no LM calls). Otherwise, native generation is used via the configured provider.
    """
    import time as _time

    t0 = _time.time()
    # Fast path: template-only generation for deterministic tests
    if (req.template_version or "").startswith("simple"):
        cls_name = str(req.options.get("class_name") or "GeneratedSignature")
        run_kind = str(req.options.get("run_kind") or "signature-gen")
        input_names = req.options.get("inputs")
        output_names = req.options.get("outputs")
        input_fields = req.options.get("input_fields")
        output_fields = req.options.get("output_fields")
        inputs = (
            [str(item) for item in input_names]
            if isinstance(input_names, list)
            else None
        )
        outputs = (
            [str(item) for item in output_names]
            if isinstance(output_names, list)
            else None
        )
        _validate_simple_signature_contract(
            class_name=cls_name,
            inputs=inputs,
            outputs=outputs,
        )
        structured_inputs = input_fields if isinstance(input_fields, list) else None
        structured_outputs = output_fields if isinstance(output_fields, list) else None
        requested_input_names = inputs or []
        requested_output_names = outputs or []
        rendered_input_names = inputs or ["context"]
        rendered_output_names = outputs or ["output"]
        simple_metadata: dict[str, Any] = {
            "run_kind": run_kind,
            "provider": "template",
            "backend": "template",
            "strategy": "simple",
            "candidate_source": "template",
            "candidate_score": 100.0,
            "candidate_valid": True,
            "attempts_used": 1,
            "max_attempts": 1,
            "attempts_exhausted": True,
            "fallback_used": False,
            "validation_pass_count": 1,
            "validation_total": 1,
            "validation_pass_rate": 1.0,
            "smoke_pass_count": 1,
            "smoke_total": 1,
            "smoke_pass_rate": 1.0,
            "json_mode": False,
            "inputs": list(rendered_input_names),
            "outputs": list(rendered_output_names),
            "requested_inputs": list(requested_input_names),
            "requested_outputs": list(requested_output_names),
            "input_count": len(rendered_input_names),
            "output_count": len(rendered_output_names),
        }

        key = make_key(
            {
                "kind": "signature",
                "prompt": req.prompt,
                "template_version": req.template_version or "simple-v1",
                "class_name": cls_name,
                "options": req.options,
            }
        )
        if cache_enabled():
            cached = cache_read("signature", key)
            if cached and isinstance(cached.get("code"), str):
                return SignatureGenResult(
                    code=cached["code"],
                    signature_name=cls_name,
                    task_description=cached.get("task_description") or req.prompt,
                    metadata=simple_metadata,
                )
        if structured_inputs is not None or structured_outputs is not None:
            code = render_signature_from_spec(
                cls_name,
                req.prompt,
                inputs=structured_inputs,
                outputs=structured_outputs,
            )
        else:
            code = render_simple_signature(
                cls_name, req.prompt, inputs=inputs, outputs=outputs
            )
        if cache_enabled():
            cache_write(
                "signature",
                key,
                {
                    "code": code,
                    "task_description": req.prompt,
                    "backend": "template",
                    "strategy": "simple",
                    "candidate_source": "template",
                    "attempts_used": 1,
                    "fallback_used": False,
                    "validation_pass_rate": 1.0,
                    "smoke_pass_rate": 1.0,
                },
            )
        return SignatureGenResult(
            code=code,
            signature_name=cls_name,
            task_description=req.prompt,
            fields=None,
            reasoning=None,
            metadata=simple_metadata,
        )

    # LM path (native)
    load_config_env()
    enable_mlflow_from_env()

    # Budget: propagate provider timeouts if set, and log later
    budget_ms_env = _os.getenv("DSPX_BUDGET_SIGNATURE_MS")
    budget_ms = (
        int(budget_ms_env) if budget_ms_env and budget_ms_env.isdigit() else None
    )
    if budget_ms:
        # best-effort propagate to known providers
        secs = max(1, int((budget_ms + 999) // 1000))
        for name in (
            "CODEX_TIMEOUT",
            "CLAUDE_TIMEOUT",
            "GEMINI_TIMEOUT",
            "OPENROUTER_TIMEOUT",
            "DSPX_PI_TIMEOUT",
        ):
            _os.environ[name] = str(secs)

    ensure_default_providers()
    active_lm = lm or create_from_env()
    dspy.configure(lm=active_lm)

    provider_name = _os.getenv("DSPX_PROVIDER", "pi-rpc")
    try:
        caps = getattr(active_lm, "capabilities", None) or provider_capabilities(
            provider_name
        )
        json_mode = bool(getattr(caps, "json_mode", False))
    except Exception:
        json_mode = False

    class_name_opt = req.options.get("class_name")
    class_name_hint = str(class_name_opt or "GeneratedSignature")
    enforce_class_name = bool(class_name_opt)

    constraints = req.options.get("constraints")
    if not isinstance(constraints, list):
        constraints = []
    else:
        constraints = [str(item) for item in constraints]
    explicit_inputs = req.options.get("inputs")
    requested_inputs = (
        [str(item) for item in explicit_inputs]
        if isinstance(explicit_inputs, list)
        else []
    )
    if requested_inputs:
        constraints.append(
            "Use exactly these input fields: " + ", ".join(requested_inputs)
        )
    explicit_outputs = req.options.get("outputs")
    requested_outputs = (
        [str(item) for item in explicit_outputs]
        if isinstance(explicit_outputs, list)
        else []
    )
    if requested_outputs:
        constraints.append(
            "Use exactly these output fields: " + ", ".join(requested_outputs)
        )
    feedback = req.options.get("feedback")
    if not isinstance(feedback, list):
        feedback = []

    max_attempts = _resolve_attempts(req.options)

    payload = _generate_native_payload(
        prompt_for_model=build_signature_strategy_prompt(
            req.prompt,
            class_name_hint=class_name_hint,
            template_version=req.template_version or "v1",
            json_mode=json_mode,
            constraints=constraints,
            feedback=feedback,
        ),
        fallback_description=req.prompt,
        class_name_hint=class_name_hint,
        json_mode=json_mode,
        max_attempts=max_attempts,
        enforce_class_name=enforce_class_name,
    )

    backend = str(payload.get("backend") or "native")
    run_kind = str(req.options.get("run_kind") or "signature-gen")
    quality_metadata: dict[str, Any] = {
        "run_kind": run_kind,
        "provider": provider_name,
        "backend": backend,
        "strategy": str(payload.get("strategy") or "spec-first"),
        "candidate_source": str(payload.get("candidate_source") or "fallback"),
        "candidate_score": float(payload.get("candidate_score") or 0.0),
        "candidate_valid": bool(payload.get("candidate_valid")),
        "candidate_errors": list(payload.get("candidate_errors") or []),
        "attempts_used": int(payload.get("attempts_used") or 0),
        "max_attempts": int(payload.get("max_attempts") or max_attempts),
        "attempts_exhausted": bool(payload.get("attempts_exhausted", False)),
        "fallback_used": bool(
            payload.get("fallback_used")
            or str(payload.get("candidate_source") or "") == "fallback"
        ),
        "validation_pass_count": int(payload.get("validation_pass_count") or 0),
        "validation_total": int(payload.get("validation_total") or 0),
        "validation_pass_rate": float(payload.get("validation_pass_rate") or 0.0),
        "smoke_pass_count": int(payload.get("smoke_pass_count") or 0),
        "smoke_total": int(payload.get("smoke_total") or 0),
        "smoke_pass_rate": float(payload.get("smoke_pass_rate") or 0.0),
        "json_mode": bool(payload.get("json_mode")),
        "template_version": req.template_version or "v1",
        "prompt_len": len(req.prompt),
        "signature_name": str(payload.get("signature_name") or class_name_hint),
        "requested_inputs": list(requested_inputs),
        "requested_outputs": list(requested_outputs),
        "requested_input_count": len(requested_inputs),
        "requested_output_count": len(requested_outputs),
    }

    res = SignatureGenResult(
        code=str(payload.get("code") or ""),
        signature_name=payload.get("signature_name"),
        task_description=payload.get("task_description"),
        fields=None,
        reasoning=None,
        metadata=quality_metadata,
    )

    # Cache LM-backed result as well
    key = make_key(
        {
            "kind": "signature",
            "prompt": req.prompt,
            "template_version": req.template_version or "v1",
            "options": req.options,
        }
    )
    if cache_enabled() and res.code:
        cache_write(
            "signature",
            key,
            {
                "code": res.code,
                "task_description": res.task_description,
                "backend": backend,
                "strategy": payload.get("strategy") or "spec-first",
                "candidate_source": payload.get("candidate_source") or "fallback",
                "attempts_used": int(payload.get("attempts_used") or 1),
                "fallback_used": bool(quality_metadata.get("fallback_used", False)),
                "max_attempts": int(payload.get("max_attempts") or max_attempts),
                "validation_pass_rate": float(
                    payload.get("validation_pass_rate") or 0.0
                ),
                "smoke_pass_rate": float(payload.get("smoke_pass_rate") or 0.0),
            },
        )

    try:
        append_quality_event(quality_metadata)
    except Exception:
        pass

    # Optional MLflow logging (guarded)
    try:
        from dspx.tracing import ensure_run_with_standard_tags, get_mlflow

        mlflow = get_mlflow()
        if mlflow is not None:
            ensure_run_with_standard_tags(
                "signature",
                template_version=req.template_version or "v1",
                run_name=f"signature-{res.signature_name or ''}",
                run_kind=run_kind,
                extra={
                    "signature.backend": backend,
                    "signature.strategy": str(payload.get("strategy") or "spec-first"),
                },
            )
            from dspx.cache import sha256_text

            if mlflow.active_run() is not None:
                mlflow.log_params(
                    {
                        "signature.prompt_len": len(req.prompt),
                        "signature.class_name": res.signature_name or "",
                        "signature.backend": backend,
                        "signature.run_kind": run_kind,
                        "signature.json_mode": bool(json_mode),
                        "signature.attempts": int(payload.get("attempts_used") or 1),
                        "signature.max_attempts": int(
                            payload.get("max_attempts") or max_attempts
                        ),
                        "signature.candidate_source": str(
                            payload.get("candidate_source") or "fallback"
                        ),
                    }
                )
                # Prefer log_text if available; else log_dict
                try:
                    mlflow.log_text(res.code, "signature.py")
                except Exception:
                    mlflow.log_dict({"code": res.code}, "signature.json")
                # Attach a tiny manifest for reproducibility
                try:
                    manifest = {
                        "template_version": req.template_version or "v1",
                        "prompt_len": len(req.prompt),
                        "code_hash": sha256_text(res.code),
                        "provider": provider_name,
                        "run_kind": run_kind,
                        "backend": backend,
                        "strategy": payload.get("strategy") or "spec-first",
                        "candidate_source": payload.get("candidate_source")
                        or "fallback",
                        "fallback_used": bool(
                            quality_metadata.get("fallback_used", False)
                        ),
                        "attempts_used": int(payload.get("attempts_used") or 1),
                        "max_attempts": int(
                            payload.get("max_attempts") or max_attempts
                        ),
                        "validation_pass_rate": float(
                            payload.get("validation_pass_rate") or 0.0
                        ),
                        "smoke_pass_rate": float(payload.get("smoke_pass_rate") or 0.0),
                    }
                    mlflow.log_dict(manifest, "signature_manifest.json")
                except Exception:
                    pass
                duration_ms = (_time.time() - t0) * 1000.0
                metrics = {
                    "signature.code_hash_prefix": int(sha256_text(res.code)[:8], 16)
                    % 1_000_000,
                    "service.duration_ms": duration_ms,
                    "signature.candidate_score": float(
                        payload.get("candidate_score") or 0.0
                    ),
                    "signature.attempts_used": float(
                        payload.get("attempts_used") or 0.0
                    ),
                    "signature.fallback_used": float(
                        1.0 if quality_metadata.get("fallback_used") else 0.0
                    ),
                    "signature.validation_pass_rate": float(
                        payload.get("validation_pass_rate") or 0.0
                    ),
                    "signature.smoke_pass_rate": float(
                        payload.get("smoke_pass_rate") or 0.0
                    ),
                }
                if budget_ms is not None:
                    try:
                        mlflow.set_tag("service.budget_ms", str(budget_ms))
                    except Exception:
                        pass
                    metrics["service.budget_exceeded"] = (
                        1.0 if duration_ms > float(budget_ms) else 0.0
                    )
                mlflow.log_metrics(metrics)
    except Exception:
        pass
    return res

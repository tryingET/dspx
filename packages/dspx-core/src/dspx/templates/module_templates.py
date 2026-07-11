# summary: "Renders deterministic DSPy module source, demos, and focused JSON-bundle runtimes."
# read_when:
#   - "Changing generated module structure, demo wiring, or output normalization."

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
    inline_examples: Optional[list[dict[str, object]]] = None,
    demo_input_fields: Optional[list[str]] = None,
    focused_json_bundle_runtime: bool = False,
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
    focused_json_bundle = bool(
        focused_json_bundle_runtime and len(outs) > 1 and signature_class_name
    )
    focused_signature_class = f"Focused{cls}BundleSignature"

    header: List[str] = []
    header.append("import json")
    header.append("")
    header.append("import dspy")
    if signature_import and signature_class_name:
        header.append(signature_import)
        header.append("")
    else:
        header.append("")
        if signature_code and signature_class_name:
            header.append(signature_code.strip())
            header.append("")

    demos = list(inline_examples or [])
    demo_inputs = list(demo_input_fields or ins)
    if demos:
        header.extend(
            [
                f"DEMO_EXAMPLES = {demos!r}",
                f"DEMO_INPUT_FIELDS = {demo_inputs!r}",
                "",
                "def _mapping_for(example: dict[str, object], role: str) -> dict[str, object]:",
                "    nested = example.get(role)",
                "    if isinstance(nested, dict):",
                "        return dict(nested)",
                "    return example",
                "",
                "def _build_demos() -> list[dspy.Example]:",
                "    demos: list[dspy.Example] = []",
                "    for example in DEMO_EXAMPLES:",
                "        inputs_map = _mapping_for(example, 'inputs')",
                "        outputs_map = _mapping_for(example, 'outputs')",
                "        values = {**inputs_map, **outputs_map}",
                "        demos.append(dspy.Example(**values).with_inputs(*DEMO_INPUT_FIELDS))",
                "    return demos",
                "",
                "def _build_focused_demos() -> list[dspy.Example]:",
                "    demos: list[dspy.Example] = []",
                "    for example in DEMO_EXAMPLES:",
                "        inputs_map = _mapping_for(example, 'inputs')",
                "        outputs_map = _mapping_for(example, 'outputs')",
                "        values = {**inputs_map, 'note_bundle_json': json.dumps(outputs_map, ensure_ascii=False)}",
                "        demos.append(dspy.Example(**values).with_inputs(*DEMO_INPUT_FIELDS))",
                "    return demos",
                "",
            ]
        )

    if focused_json_bundle:
        header.extend(
            [
                f"class {focused_signature_class}(dspy.Signature):",
                '    """Create one focused JSON bundle, then expand it to the declared output files.\n\n    Return one valid JSON object. The object may use output-field names directly or\n    unwrapped names such as section_units, evidence_cards, wiki_note_drafts,\n    review_packet, and artifact_contract_manifest. Keep canonical mutation forbidden.\n    If relevant image/figure rows are supplied, preserve figure_id/page/image_path\n    and review_embed; if no figure is relevant, image_refs must be [].\n    """',
                "",
            ]
        )
        for field in ins:
            header.append(
                f"    {field}: str = dspy.InputField(desc='Input field for focused bundle runtime.')"
            )
        header.extend(
            [
                "    note_bundle_json: str = dspy.OutputField(desc='One valid JSON object containing the focused review-only output bundle.')",
                "",
                "def _json_loads_or_empty(value: object) -> object:",
                "    text = str(value or '{}').strip()",
                "    if text.startswith('```') and text.endswith('```'):",
                "        text = '\\n'.join(text.splitlines()[1:-1]).strip()",
                "    if not (text.startswith('{\\\"') or text.startswith('{\\n') or text == '{}'):",
                "        return {}",
                "    return json.loads(text or '{}')",
                "",
                "def _json_text(value: object) -> str:",
                "    if isinstance(value, str):",
                "        text = value.strip()",
                "        if _json_container_text(text):",
                "            return json.dumps(json.loads(text), ensure_ascii=False, indent=2, sort_keys=True)",
                "    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)",
                "",
                "def _first_key(bundle: dict[str, object], *keys: str, default: object) -> object:",
                "    for key in keys:",
                "        if key in bundle:",
                "            return bundle[key]",
                "    return default",
                "",
                "def _extract_embeds(markdown: str) -> list[str]:",
                "    embeds: list[str] = []",
                "    start = 0",
                "    while True:",
                "        idx = markdown.find('![[', start)",
                "        if idx < 0:",
                "            break",
                "        end = markdown.find(']]', idx)",
                "        if end < 0:",
                "            break",
                "        embed = markdown[idx : end + 2]",
                "        if embed not in embeds:",
                "            embeds.append(embed)",
                "        start = end + 2",
                "    return embeds",
                "",
                "def _collect_image_refs(bundle: dict[str, object]) -> list[dict[str, object]]:",
                "    refs: list[dict[str, object]] = []",
                "    for key in ('section_units', 'section_units_json', 'evidence_cards', 'evidence_cards_json', 'wiki_note_drafts', 'wiki_note_drafts_json', 'review_packet', 'review_packet_json'):",
                "        value = bundle.get(key)",
                "        containers = value if isinstance(value, list) else [value]",
                "        for container in containers:",
                "            if not isinstance(container, dict):",
                "                continue",
                "            image_refs = container.get('image_refs')",
                "            if isinstance(image_refs, list):",
                "                for ref in image_refs:",
                "                    if isinstance(ref, dict) and ref not in refs:",
                "                        refs.append(dict(ref))",
                "    return refs",
                "",
                "def _normalize_drafts(value: object, known_image_refs: list[dict[str, object]]) -> object:",
                "    if not isinstance(value, list):",
                "        return value",
                "    normalized: list[object] = []",
                "    for item in value:",
                "        if not isinstance(item, dict):",
                "            normalized.append(item)",
                "            continue",
                "        draft = dict(item)",
                "        content = draft.get('markdown') or draft.get('content') or ''",
                "        if isinstance(content, str) and content:",
                "            draft.setdefault('markdown', content)",
                "            draft.setdefault('content', content)",
                "        image_refs = draft.get('image_refs')",
                "        if (not isinstance(image_refs, list) or not image_refs) and isinstance(content, str):",
                "            derived_image_refs: list[dict[str, object]] = []",
                "            for embed in _extract_embeds(content):",
                "                ref: dict[str, object] = {'embed': embed}",
                "                for known in known_image_refs:",
                "                    known_embed = known.get('review_embed') or known.get('embed')",
                "                    if known_embed == embed:",
                "                        ref.update(known)",
                "                        ref.setdefault('embed', embed)",
                "                        break",
                "                derived_image_refs.append(ref)",
                "            image_refs = derived_image_refs",
                "        draft['image_refs'] = image_refs if isinstance(image_refs, list) else []",
                "        draft.setdefault('canonical_mutation_performed', False)",
                "        draft.setdefault('review_only', True)",
                "        normalized.append(draft)",
                "    return normalized",
                "",
            ]
        )

    body: List[str] = []
    doc = (description or f"Auto-generated module {cls}").replace("\n", " ")
    body.append(f"class {cls}(dspy.Module):")
    body.append(f'    """{doc}"""')
    body.append("")
    body.append("    def __init__(self, use_cot: bool = False) -> None:")
    body.append("        super().__init__()")
    if focused_json_bundle:
        body.append(f"        self.predict = dspy.Predict({signature_class_name})")
        body.append(
            f"        self.focused_predict = dspy.Predict({focused_signature_class})"
        )
    elif signature_class_name:
        body.append(f"        self.predict = dspy.Predict({signature_class_name})")
    else:
        io_sig = ", ".join(ins) + " -> " + ", ".join(outs)
        body.append(f"        self.predict = dspy.Predict({io_sig!r})")
    if focused_json_bundle:
        body.append("        self.predict._dspx_capture_predict = False")
    if demos and focused_json_bundle:
        body.append("        self.focused_predict.demos = _build_focused_demos()")
    elif demos:
        body.append("        self.predict.demos = _build_demos()")
    body.append("")

    # Build forward
    args_sig = ", ".join(f"{x}: str" for x in ins)
    body.append(f"    def forward(self, {args_sig}) -> dspy.Prediction:")
    default_pred_args = ""
    if focused_json_bundle:
        default_parts: list[str] = []
        for out in outs:
            base = out.removesuffix("_json") if out.endswith("_json") else out
            default_text = (
                "{}"
                if base
                in {"frontmatter_plans", "review_packet", "artifact_contract_manifest"}
                else "[]"
            )
            default_parts.append(f"{out}={default_text!r}")
        default_pred_args = ", ".join(default_parts)
    call_args = ", ".join(f"{x}={x}" for x in ins)
    if call_args:
        if focused_json_bundle:
            body.append(
                "        if hasattr(self.predict, '_dspx_capture_predict') and self.predict._dspx_capture_predict:"
            )
            body.append(f"            self.predict({call_args})")
            body.append(f"            return dspy.Prediction({default_pred_args})")
            body.append(f"        pred = self.focused_predict({call_args})")
        else:
            body.append(f"        pred = self.predict({call_args})")
    else:
        body.append("        pred = self.predict()")
    if focused_json_bundle:
        body.append("        bundle = _json_loads_or_empty(pred.note_bundle_json)")
        body.append("        if not isinstance(bundle, dict):")
        body.append(
            "            bundle = {'wiki_note_drafts': [], 'review_packet': {'state': 'needs_review', 'error': 'model_output_was_not_a_json_object'}}"
        )
        body.append("        known_image_refs = _collect_image_refs(bundle)")
        for out in outs:
            base = out.removesuffix("_json") if out.endswith("_json") else out
            default = (
                "{}"
                if base
                in {"frontmatter_plans", "review_packet", "artifact_contract_manifest"}
                else "[]"
            )
            if base == "wiki_note_drafts":
                body.append(
                    f"        {out} = _normalize_drafts(_first_key(bundle, {base!r}, {out!r}, default={default}), known_image_refs)"
                )
            elif base == "review_packet":
                body.append(
                    f"        {out} = _first_key(bundle, {base!r}, {out!r}, default={default})"
                )
                body.append(f"        if isinstance({out}, dict):")
                body.append(
                    f"            {out}.setdefault('canonical_mutation_performed', False)"
                )
            elif base == "artifact_contract_manifest":
                body.append(
                    f"        {out} = _first_key(bundle, {base!r}, {out!r}, default={default})"
                )
                body.append(f"        if isinstance({out}, dict):")
                body.append(
                    f"            {out}.setdefault('canonical_mutation_performed', False)"
                )
            else:
                body.append(
                    f"        {out} = _first_key(bundle, {base!r}, {out!r}, default={default})"
                )
        pred_args = ", ".join(f"{out}=_json_text({out})" for out in outs)
        body.append(f"        return dspy.Prediction({pred_args})")
    else:
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
    body.append("def _json_container_text(value: str) -> bool:")
    body.append("    text = value.strip()")
    body.append(
        "    return (text.startswith('{') and text.endswith('}')) or (text.startswith('[') and text.endswith(']'))"
    )
    body.append("")
    body.append("def _normalize_json_text(value: str) -> str:")
    body.append("    parsed = json.loads(value.strip())")
    body.append(
        "    return json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(',', ':'))"
    )
    body.append("")
    body.append(
        "def normalize_output("
        "key: str, gold: str, pred: str, pred_name: str | None = None, pred_trace: object | None = None"
        ") -> tuple[str, str]:"
    )
    body.append("    if _json_container_text(gold) and _json_container_text(pred):")
    body.append("        return _normalize_json_text(gold), _normalize_json_text(pred)")
    body.append("    return gold, pred")

    code = "\n".join(header + [""] + body)
    return code if code.endswith("\n") else code + "\n"

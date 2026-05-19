---
summary: "Discovery, design, and implementation plan for DesignMD multimodal DSPx program-run via dspy-lm-auth."
status: implemented
owner: dspx
read_when:
  - "You are running DesignMD visual-dossier generated programs with image files."
  - "You are changing DSPx dspy-lm-auth vision capabilities or program-run image descriptors."
---

# DesignMD multimodal program-run via dspy-lm-auth

## Discovery

`dspy-lm-auth` already carries Codex/Responses multimodal payloads when callers provide message content blocks. The accepted image shape is OpenAI chat-style:

```json
{"type":"image_url","image_url":{"url":"data:image/png;base64,..."}}
```

The Codex route converts that to Responses API input blocks:

```json
{"type":"input_image","image_url":"data:image/png;base64,..."}
```

Pi-mono uses the same conceptual contract at its public boundary: image attachments are base64 `ImageContent` blocks with a MIME type, then provider adapters translate them to the target API.

DSPx was missing the runtime bridge, not the auth/provider ability:

- `dspy-lm-auth` was not advertised as vision-capable in DSPx provider capabilities.
- `program-run` only loaded JSON inputs and passed plain values to generated programs.
- DesignMD visual-dossier generated intents only declared text JSON inputs, so there was no field for materialized image evidence.

## Design

DSPx keeps raw runtime inputs as review/evidence JSON and separately materializes explicit image descriptors only at execution time.

Supported descriptors:

```json
{"type":"image_file","path":"images/ref.png"}
{"type":"image_base64","media_type":"image/png","data":"..."}
{"type":"image_url","url":"data:image/png;base64,..."}
```

Relative `image_file.path` values resolve from the runtime input file directory. Materialization converts descriptors to serialized `dspy.Image` custom-type markers. A list of image descriptors becomes one newline-joined string, suitable for a generated DSPy `str` input field.

DesignMD visual-dossier program intents now include:

```text
visual_image_blocks
```

This field is optional by convention: use an empty string when no image blocks are supplied. It is review evidence only and does not grant product/design acceptance.

## Implementation plan executed

1. Declare `dspy-lm-auth` vision support for Codex-backed auth routes.
2. Preserve multimodal message content through DSPx `LMRequest`.
3. Add program-run image descriptor materialization while preserving raw input evidence.
4. Add `visual_image_blocks` to DesignMD visual-dossier generated intents.
5. Add regression tests in DSPx and dspy-lm-auth for image block conversion/preservation.

## Follow-up

DesignMD Foundry should regenerate its DSPx kit so target runtime inputs include all 15 uploaded image files as `visual_image_blocks` descriptors, then rerun with `DSPX_PROVIDER=dspy-lm-auth`.

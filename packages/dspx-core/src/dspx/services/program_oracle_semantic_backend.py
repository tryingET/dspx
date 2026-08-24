# summary: "Provides deterministic fixture replay and explicit live-provider unavailability for Oracle semantics."
# read_when:
#   - "Changing program Oracle semantic preflight, fixture replay, or provider support posture."

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dspx.model_roles import (
    ORACLE_SEMANTIC_ROLE,
    ModelRole,
    resolve_model_role,
)
from dspx.redaction import sanitize_diagnostic_text
from dspx.services.program_oracle_semantic_contract import (
    ORACLE_SEMANTIC_FIXTURE_SCHEMA,
    REQUIRED_ANALYSIS_FIELDS,
    OracleSemanticAnalysis,
    OracleSemanticPreflight,
    OracleSemanticRequest,
    OracleSemanticResult,
    ProgramOracleSemanticBackend,
    ProgramOracleSemanticBackendError,
    canonical_json,
)

_ALLOWED_BACKENDS = frozenset({"live", "fixture-replay"})
_MAX_FIXTURE_BYTES = 1_000_000


def _evidence_ref_values(value: object) -> tuple[str, ...]:
    refs: list[str] = []

    def visit(item: object) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                if (
                    key == "ref"
                    and isinstance(child, str)
                    and child.strip()
                    and child not in refs
                ):
                    refs.append(child)
                visit(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                visit(child)

    visit(value)
    return tuple(refs)


def _analysis_response_format(
    request: OracleSemanticRequest | None = None,
) -> dict[str, Any]:
    quality = request.quality_contract if request is not None else None
    codebook = (
        quality.get("analysis_codebook") if isinstance(quality, Mapping) else None
    )
    evidence_refs = (
        _evidence_ref_values(request.evidence) if request is not None else ()
    )
    properties: dict[str, dict[str, Any]] = {}
    for field in REQUIRED_ANALYSIS_FIELDS:
        items: dict[str, Any] = {"type": "string"}
        allowed = codebook.get(field) if isinstance(codebook, Mapping) else None
        if (
            isinstance(allowed, (list, tuple))
            and allowed
            and all(isinstance(code, str) and code.strip() for code in allowed)
        ):
            items["enum"] = list(dict.fromkeys(allowed))
        elif field == "evidence_refs" and evidence_refs:
            items["enum"] = list(evidence_refs)
        properties[field] = {
            "type": "array",
            "items": items,
            "uniqueItems": True,
        }
    properties["confidence"] = {
        "type": "number",
        "minimum": 0.0,
        "maximum": 1.0,
    }
    return {
        "type": "json_schema",
        "name": "dspx_oracle_semantic_analysis",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": properties,
            "required": [*REQUIRED_ANALYSIS_FIELDS, "confidence"],
            "additionalProperties": False,
        },
    }


def _analysis_prompt(request: OracleSemanticRequest) -> str:
    schema = {
        **{field: ["string"] for field in REQUIRED_ANALYSIS_FIELDS},
        "confidence": 0.0,
    }
    quality = request.quality_contract
    codebook_mode = isinstance(quality, Mapping) and isinstance(
        quality.get("analysis_codebook"), Mapping
    )
    item_contract = (
        "For observations, failure_attractors, quality_contract_violations, "
        "hypotheses, and recommended_experiments, return only exact codes from "
        "the field-specific REQUEST.quality_contract.analysis_codebook; each "
        "array item must be one code with no prose. Follow any "
        "REQUEST.quality_contract.analysis_field_rubric exactly. When present, "
        "REQUEST.quality_contract.analysis_code_semantics is the authoritative, "
        "case-independent denotation of every code: apply its selection_rules and "
        "each code's select_when and exclude_when conditions, but return only code "
        "identifiers. Observations are literal target-subject facts: require the "
        "same proposition, subject, and state in the evidence, and do not infer an "
        "unmentioned workflow entity or status from absent effects. Quality-contract "
        "violations are literal criterion outcomes despite the legacy wire name: "
        "require an explicit criterion plus evidence that establishes its breach or "
        "satisfaction; a regression alone does not prove a minimum threshold "
        "violation. Hypotheses are explicit causal or mechanism epistemic states "
        "despite the legacy wire name; never infer uncertainty merely from absence "
        "of causal proof. Failure attractors and recommended experiments are "
        "prospective fields: infer at most the one narrowest risk or next supported "
        "action matching the explicit subject, workflow stage, and authority "
        "boundary, even though the risk or action need not appear verbatim. Never "
        "invent the subject of a prospective code. Follow any analysis_evidence_ref_rubric "
        "and analysis_confidence_rubric exactly. Use an empty array when a field's "
        "rules support no code. Exclude merely possible, related, generic, "
        "precautionary, alternative, opposite, or downstream codes. Return the "
        "minimum exact code set justified by the evidence, not every plausible "
        "code. "
        if codebook_mode
        else "Put exactly one factual assertion in each array item; do not join "
        "separate or contrary assertions in one item. "
    )
    return (
        "You are DSPx Oracle semantic analysis. Analyze only the receipt-bound "
        "evidence supplied below. Return exactly one JSON object matching the "
        "output shape. "
        f"{item_contract}"
        "Never infer, grant, or manufacture deployment or transition authority; "
        "select an authority-dependent action only when supplied evidence explicitly "
        "establishes that authority. In evidence_refs, cite all and only exact ref "
        "values from supplied records that directly support the selected codes or "
        "the objective-specific reason for an empty field; exclude unrelated or "
        "distractor records.\n\n"
        f"OUTPUT_SHAPE={canonical_json(schema)}\n"
        f"REQUEST={canonical_json(request.payload())}"
    )


class FixtureReplayOracleSemanticBackend:
    def __init__(self, *, fixture_path: Path, preferred_model: str):
        # Preserve the final path component so symlinks can be rejected before read.
        self.fixture_path = fixture_path.expanduser().absolute()
        self.preferred_model = preferred_model

    def _load(self) -> tuple[dict[str, Any], str]:
        path = self.fixture_path
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags)
        except OSError as exc:
            raise ProgramOracleSemanticBackendError(
                f"Oracle semantic fixture must be an existing regular non-symlink file: {path}"
            ) from exc
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise ProgramOracleSemanticBackendError(
                    f"Oracle semantic fixture must be a regular file: {path}"
                )
            with os.fdopen(descriptor, "rb") as stream:
                descriptor = -1
                raw = stream.read(_MAX_FIXTURE_BYTES + 1)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        if len(raw) > _MAX_FIXTURE_BYTES:
            raise ProgramOracleSemanticBackendError(
                f"Oracle semantic fixture exceeds the {_MAX_FIXTURE_BYTES}-byte safety bound"
            )
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProgramOracleSemanticBackendError(
                f"Oracle semantic fixture must be valid UTF-8 JSON: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise ProgramOracleSemanticBackendError(
                "Oracle semantic fixture must contain one JSON object"
            )
        if payload.get("schema_version") != ORACLE_SEMANTIC_FIXTURE_SCHEMA:
            raise ProgramOracleSemanticBackendError(
                f"Oracle semantic fixture schema_version must be {ORACLE_SEMANTIC_FIXTURE_SCHEMA!r}"
            )
        entries = payload.get("entries")
        if not isinstance(entries, dict):
            raise ProgramOracleSemanticBackendError(
                "Oracle semantic fixture entries must be an object keyed by request_sha256"
            )
        for request_sha256, entry in entries.items():
            if not isinstance(request_sha256, str) or len(request_sha256) != 64:
                raise ProgramOracleSemanticBackendError(
                    "Oracle semantic fixture entry key must be a SHA-256 hex digest"
                )
            try:
                int(request_sha256, 16)
            except ValueError as exc:
                raise ProgramOracleSemanticBackendError(
                    "Oracle semantic fixture entry key must be a SHA-256 hex digest"
                ) from exc
            if not isinstance(entry, dict):
                raise ProgramOracleSemanticBackendError(
                    "Oracle semantic fixture entry must be an object"
                )
            if entry.get("request_sha256") != request_sha256:
                raise ProgramOracleSemanticBackendError(
                    "Oracle semantic fixture entry request_sha256 mismatch"
                )
            analysis = entry.get("analysis")
            if not isinstance(analysis, dict):
                raise ProgramOracleSemanticBackendError(
                    "Oracle semantic fixture entry.analysis must be an object"
                )
            OracleSemanticAnalysis.from_mapping(analysis)
        return payload, hashlib.sha256(raw).hexdigest()

    def preflight(self) -> str:
        _, fixture_sha256 = self._load()
        return fixture_sha256

    def analyze(self, request: OracleSemanticRequest) -> OracleSemanticResult:
        payload, fixture_sha256 = self._load()
        entries = payload.get("entries")
        if not isinstance(entries, dict):
            raise ProgramOracleSemanticBackendError(
                "Oracle semantic fixture entries must be an object keyed by request_sha256"
            )
        entry = entries.get(request.request_sha256)
        if not isinstance(entry, dict):
            raise ProgramOracleSemanticBackendError(
                "Oracle semantic fixture has no entry for request_sha256 "
                f"{request.request_sha256}"
            )
        recorded_hash = entry.get("request_sha256")
        if recorded_hash != request.request_sha256:
            raise ProgramOracleSemanticBackendError(
                "Oracle semantic fixture entry request_sha256 mismatch"
            )
        analysis_raw = entry.get("analysis")
        if not isinstance(analysis_raw, dict):
            raise ProgramOracleSemanticBackendError(
                "Oracle semantic fixture entry.analysis must be an object"
            )
        analysis = OracleSemanticAnalysis.from_mapping(analysis_raw)
        return OracleSemanticResult(
            request_sha256=request.request_sha256,
            backend_kind="fixture-replay",
            preferred_model=self.preferred_model,
            configured_provider=None,
            configured_model=None,
            executed_provider=None,
            executed_model=None,
            execution_status="replayed_fixture",
            live_call_succeeded=False,
            analysis=analysis,
            fixture_sha256=fixture_sha256,
        )


def _settings(
    environ: Mapping[str, str] | None = None,
) -> tuple[str, ModelRole, str, str | None]:
    env = os.environ if environ is None else environ
    backend_kind = str(env.get("DSPX_ORACLE_SEMANTIC_BACKEND", "live")).strip().lower()
    if backend_kind not in _ALLOWED_BACKENDS:
        raise ProgramOracleSemanticBackendError(
            "DSPX_ORACLE_SEMANTIC_BACKEND must be one of: "
            + ", ".join(sorted(_ALLOWED_BACKENDS))
        )
    role = resolve_model_role("oracle_semantic", environ=env)
    provider_name = str(env.get("DSPX_ORACLE_SEMANTIC_PROVIDER", "stub")).strip()
    fixture_path = str(env.get("DSPX_ORACLE_SEMANTIC_FIXTURE_PATH", "")).strip() or None
    return backend_kind, role, provider_name, fixture_path


def resolve_program_oracle_semantic_backend(
    *, environ: Mapping[str, str] | None = None
) -> ProgramOracleSemanticBackend:
    backend_kind, role, provider_name, fixture_path = _settings(environ)
    preferred_model = role.model
    if backend_kind == "fixture-replay":
        if fixture_path is None:
            raise ProgramOracleSemanticBackendError(
                "DSPX_ORACLE_SEMANTIC_FIXTURE_PATH is required for fixture-replay"
            )
        return FixtureReplayOracleSemanticBackend(
            fixture_path=Path(fixture_path), preferred_model=preferred_model
        )

    raise ProgramOracleSemanticBackendError(
        "live Oracle semantic providers are unsupported after the typed hard cutover; "
        "use fixture-replay"
    )


def preflight_program_oracle_semantic_backend(
    *, environ: Mapping[str, str] | None = None
) -> OracleSemanticPreflight:
    try:
        backend_kind, role, provider_name, fixture_path = _settings(environ)
        preferred_model = role.model
    except Exception as exc:
        return OracleSemanticPreflight(
            ready=False,
            backend_kind="invalid",
            preferred_model=ORACLE_SEMANTIC_ROLE.model,
            configured_provider=None,
            configured_model=None,
            fixture_path=None,
            checks=(
                {
                    "name": "configuration",
                    "ok": False,
                    "detail": sanitize_diagnostic_text(str(exc)),
                },
            ),
        )

    if backend_kind == "fixture-replay":
        if fixture_path is None:
            return OracleSemanticPreflight(
                ready=False,
                backend_kind=backend_kind,
                preferred_model=preferred_model,
                configured_provider=None,
                configured_model=None,
                fixture_path=None,
                checks=(
                    {
                        "name": "fixture",
                        "ok": False,
                        "detail": "DSPX_ORACLE_SEMANTIC_FIXTURE_PATH is required",
                    },
                ),
            )
        backend = FixtureReplayOracleSemanticBackend(
            fixture_path=Path(fixture_path), preferred_model=preferred_model
        )
        try:
            fixture_sha256 = backend.preflight()
        except Exception as exc:
            return OracleSemanticPreflight(
                ready=False,
                backend_kind=backend_kind,
                preferred_model=preferred_model,
                configured_provider=None,
                configured_model=None,
                fixture_path=str(Path(fixture_path).expanduser().resolve()),
                checks=(
                    {
                        "name": "fixture",
                        "ok": False,
                        "detail": sanitize_diagnostic_text(str(exc)),
                    },
                ),
            )
        return OracleSemanticPreflight(
            ready=True,
            backend_kind=backend_kind,
            preferred_model=preferred_model,
            configured_provider=None,
            configured_model=None,
            fixture_path=str(Path(fixture_path).expanduser().resolve()),
            checks=(
                {
                    "name": "fixture",
                    "ok": True,
                    "fixture_sha256": fixture_sha256,
                },
            ),
        )

    return OracleSemanticPreflight(
        ready=False,
        backend_kind=backend_kind,
        preferred_model=preferred_model,
        configured_provider=provider_name,
        configured_model=None,
        fixture_path=None,
        checks=(
            {
                "name": "provider_configuration",
                "ok": False,
                "detail": "live Oracle semantic providers are unsupported after the typed hard cutover; use fixture-replay",
            },
        ),
    )

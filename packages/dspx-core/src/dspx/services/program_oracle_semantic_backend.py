# summary: "Provides the typed loopback live Oracle semantic backend and deterministic fixture replay."
# read_when:
#   - "Changing program Oracle semantic preflight, live typed-provider execution, fixture replay, or provider support posture."

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dspx import provider_registry
from dspx.dspy_typed_lm import DSPyTypedLMAdapter
from dspx.model_roles import (
    ORACLE_SEMANTIC_ROLE,
    ModelRole,
    resolve_model_role,
)
from dspx.openai_compatible_provider import (
    OpenAICompatibleProvider,
    _validated_endpoint,
    _validated_model,
    _validated_timeout,
)
from dspx.policy import check_provider_allowed
from dspx.provider_contract import EffectDisposition
from dspx.redaction import redact_url, sanitize_diagnostic_text
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
# The live backend is deliberately narrower than the provider registry: only the
# credential-free loopback typed port may carry receipt-bound evidence to a model.
_LIVE_PROVIDERS = frozenset({"openai-compatible"})
_DEFAULT_LIVE_PROVIDER = "openai-compatible"
_MAX_FIXTURE_BYTES = 1_000_000
_MAX_LIVE_OUTPUT_CHARS = 200_000


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


def _strip_json_fence(raw: str) -> str:
    text = str(raw or "").strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()
    return text


def _parse_analysis_text(
    raw: str, *, response_format: Mapping[str, Any] | None = None
) -> OracleSemanticAnalysis:
    """Parse one strict analysis object and enforce the response-format enums.

    A model may only return codes and evidence refs that the request offered:
    every ``items.enum`` in ``response_format`` (codebook fields and the
    request-derived ``evidence_refs``) is a closed set, and arrays must not repeat.
    """

    text = _strip_json_fence(raw)
    if len(text) > _MAX_LIVE_OUTPUT_CHARS:
        raise ProgramOracleSemanticBackendError(
            "Oracle semantic provider output exceeds the safety bound"
        )
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProgramOracleSemanticBackendError(
            f"Oracle semantic extracted output was not valid JSON: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ProgramOracleSemanticBackendError(
            "Oracle semantic provider must return one JSON object"
        )
    analysis = OracleSemanticAnalysis.from_mapping(payload)
    if response_format is None:
        return analysis
    schema = response_format.get("schema")
    properties = schema.get("properties") if isinstance(schema, Mapping) else None
    if not isinstance(properties, Mapping):
        return analysis
    for field in REQUIRED_ANALYSIS_FIELDS:
        values = list(getattr(analysis, field))
        declared = properties.get(field)
        if not isinstance(declared, Mapping):
            continue
        if declared.get("uniqueItems") is True and len(set(values)) != len(values):
            raise ProgramOracleSemanticBackendError(
                f"Oracle semantic analysis.{field} repeats an item"
            )
        items = declared.get("items")
        allowed = items.get("enum") if isinstance(items, Mapping) else None
        if not isinstance(allowed, list):
            continue
        outside = [value for value in values if value not in allowed]
        if outside:
            preview = ", ".join(
                sanitize_diagnostic_text(value, limit=80) for value in outside[:5]
            )
            raise ProgramOracleSemanticBackendError(
                f"Oracle semantic analysis.{field} cites values outside the request "
                f"enum: {preview}"
            )
    return analysis


@dataclass(frozen=True)
class _LiveSettings:
    """Validated pre-effect configuration for the typed loopback live backend."""

    provider_name: str
    model: str
    model_override: bool
    base_url: str
    endpoint_redacted: str
    timeout: float


def _live_settings(env: Mapping[str, str], *, role: ModelRole) -> _LiveSettings:
    provider_name = (
        str(env.get("DSPX_ORACLE_SEMANTIC_PROVIDER", _DEFAULT_LIVE_PROVIDER))
        .strip()
        .lower()
    )
    if provider_name not in _LIVE_PROVIDERS:
        raise ProgramOracleSemanticBackendError(
            "DSPX_ORACLE_SEMANTIC_PROVIDER must be one of: "
            + ", ".join(sorted(_LIVE_PROVIDERS))
            + " for the live Oracle semantic backend"
        )
    if provider_name not in provider_registry.supported_provider_names():
        raise ProgramOracleSemanticBackendError(
            f"provider {provider_name!r} is outside the typed provider support matrix"
        )
    try:
        check_provider_allowed(provider_name)
    except PermissionError as exc:
        raise ProgramOracleSemanticBackendError(
            f"provider {provider_name!r} is not allowed by policy"
        ) from exc
    if env.get("DSPX_OPENAI_COMPAT_API_KEY") is not None:
        raise ProgramOracleSemanticBackendError(
            "openai-compatible credentials are unsupported; the Oracle live backend is credential-free"
        )
    override = str(env.get("DSPX_ORACLE_SEMANTIC_MODEL", "")).strip()
    raw_model = override or str(env.get("DSPX_OPENAI_COMPAT_MODEL", "")).strip()
    if not raw_model:
        raise ProgramOracleSemanticBackendError(
            "DSPX_OPENAI_COMPAT_MODEL (or DSPX_ORACLE_SEMANTIC_MODEL) is required for the live Oracle semantic backend"
        )
    if override and role.model != override:
        raise ProgramOracleSemanticBackendError(
            "DSPX_ORACLE_SEMANTIC_MODEL drifted from the resolved oracle_semantic role"
        )
    if override and not role.is_local_route:
        raise ProgramOracleSemanticBackendError(
            "DSPX_ORACLE_SEMANTIC_MODEL must use the local/ route for the "
            "openai-compatible live Oracle semantic backend"
        )
    try:
        model = _validated_model(raw_model)
    except (TypeError, ValueError) as exc:
        raise ProgramOracleSemanticBackendError(
            f"Oracle semantic model id is invalid: {exc}"
        ) from exc
    raw_base_url = str(env.get("DSPX_OPENAI_COMPAT_API_BASE", "")).strip()
    if not raw_base_url:
        raise ProgramOracleSemanticBackendError(
            "DSPX_OPENAI_COMPAT_API_BASE is required for the live Oracle semantic backend"
        )
    try:
        base_url, endpoint = _validated_endpoint(raw_base_url)
    except (TypeError, ValueError) as exc:
        raise ProgramOracleSemanticBackendError(
            f"Oracle semantic provider endpoint is invalid: {exc}"
        ) from exc
    raw_timeout = str(env.get("DSPX_OPENAI_COMPAT_TIMEOUT", "30")).strip()
    try:
        timeout = _validated_timeout(float(raw_timeout))
    except (TypeError, ValueError) as exc:
        raise ProgramOracleSemanticBackendError(
            "DSPX_OPENAI_COMPAT_TIMEOUT must be a positive finite number"
        ) from exc
    return _LiveSettings(
        provider_name=provider_name,
        model=model,
        model_override=bool(override),
        base_url=base_url,
        endpoint_redacted=redact_url(endpoint),
        timeout=timeout,
    )


def _create_live_adapter(settings: _LiveSettings) -> DSPyTypedLMAdapter:
    try:
        return provider_registry.create(
            settings.provider_name,
            model=settings.model,
            base_url=settings.base_url,
            timeout=settings.timeout,
        )
    except ProgramOracleSemanticBackendError:
        raise
    except Exception as exc:
        raise ProgramOracleSemanticBackendError(
            "live Oracle semantic provider construction failed: "
            + sanitize_diagnostic_text(str(exc))
        ) from exc


def _observed_attempt(lm: DSPyTypedLMAdapter) -> dict[str, Any]:
    from dspx.provider_runtime import provider_effect_evidence_from_instance

    evidence = provider_effect_evidence_from_instance(lm)
    attempts = evidence.get("attempts")
    latest = attempts[-1] if isinstance(attempts, list) and attempts else {}
    return {
        "terminal_effect": evidence.get("terminal_effect"),
        "attempt_total": evidence.get("attempt_total"),
        "provider_kind": latest.get("provider_kind"),
        "observed_model": latest.get("observed_model"),
        "effect_disposition": latest.get("effect_disposition"),
    }


class TypedProviderOracleSemanticBackend:
    """One-shot live Oracle semantics over the typed ``openai-compatible`` port.

    Exactly one invocation flows through ``DSPyTypedLMAdapter``; the result is
    parsed strictly against the request's response format. An indeterminate
    provider effect is terminal: the backend latches and refuses further work.
    """

    backend_kind = "live"

    def __init__(
        self,
        *,
        provider_name: str,
        preferred_model: str,
        lm: DSPyTypedLMAdapter,
    ):
        if provider_name not in _LIVE_PROVIDERS:
            raise ProgramOracleSemanticBackendError(
                "TypedProviderOracleSemanticBackend accepts only the openai-compatible port"
            )
        if type(lm) is not DSPyTypedLMAdapter or (
            type(lm.provider) is not OpenAICompatibleProvider
        ):
            raise ProgramOracleSemanticBackendError(
                "TypedProviderOracleSemanticBackend requires a typed openai-compatible adapter"
            )
        self.provider_name = provider_name
        self.preferred_model = preferred_model
        self.lm = lm
        self.configured_model = str(lm.model)
        self._invoked = False
        self._indeterminate = False

    def close(self) -> None:
        provider = self.lm.provider
        if type(provider) is OpenAICompatibleProvider:
            provider.close()

    def _result(
        self,
        request: OracleSemanticRequest,
        *,
        execution_status: str,
        live_call_succeeded: bool,
        executed_provider: str | None,
        executed_model: str | None,
        analysis: OracleSemanticAnalysis | None = None,
        error: str | None = None,
    ) -> OracleSemanticResult:
        return OracleSemanticResult(
            request_sha256=request.request_sha256,
            backend_kind=self.backend_kind,
            preferred_model=self.preferred_model,
            configured_provider=self.provider_name,
            configured_model=self.configured_model,
            executed_provider=executed_provider,
            executed_model=executed_model,
            execution_status=execution_status,
            live_call_succeeded=live_call_succeeded,
            analysis=analysis,
            error=error,
        )

    def analyze(self, request: OracleSemanticRequest) -> OracleSemanticResult:
        from dspy import LMRequest, LMResponse, LMTransportError
        from dspy.core.types import LMMessage, LMTextPart

        if self._indeterminate:
            raise ProgramOracleSemanticBackendError(
                "live Oracle semantic backend effect is indeterminate; a new backend is required"
            )
        if self._invoked:
            raise ProgramOracleSemanticBackendError(
                "live Oracle semantic backend is one-shot; a new backend is required"
            )
        self._invoked = True
        prompt = _analysis_prompt(request)
        response_format = _analysis_response_format(request)
        try:
            typed_request = LMRequest(
                model=self.lm.model,
                messages=[LMMessage(role="user", parts=[LMTextPart(text=prompt)])],
            )
            response = self.lm(request=typed_request)
        except LMTransportError as exc:
            code = str(getattr(exc, "code", "") or "")
            observed = _observed_attempt(self.lm)
            if code == EffectDisposition.EFFECT_INDETERMINATE.value or (
                observed.get("terminal_effect")
                == EffectDisposition.EFFECT_INDETERMINATE.value
            ):
                self._indeterminate = True
                raise ProgramOracleSemanticBackendError(
                    "live Oracle semantic provider effect is indeterminate "
                    f"(code={code or 'unknown'}); no retry or fallback is permitted"
                ) from None
            return self._result(
                request,
                execution_status="failed_before_live_success",
                live_call_succeeded=False,
                executed_provider=None,
                executed_model=observed.get("observed_model"),
                error=f"provider invocation failed before live success (code={code or 'unknown'})",
            )
        except Exception as exc:
            observed = _observed_attempt(self.lm)
            if (
                observed.get("terminal_effect")
                == EffectDisposition.EFFECT_INDETERMINATE.value
            ):
                self._indeterminate = True
                raise ProgramOracleSemanticBackendError(
                    "live Oracle semantic provider effect is indeterminate; no retry or fallback is permitted"
                ) from None
            return self._result(
                request,
                execution_status="failed_before_live_success",
                live_call_succeeded=False,
                executed_provider=None,
                executed_model=None,
                error=sanitize_diagnostic_text(f"{type(exc).__name__}: {exc}"),
            )
        finally:
            self.close()

        observed = _observed_attempt(self.lm)
        executed_provider = str(observed.get("provider_kind") or "") or None
        executed_model = str(observed.get("observed_model") or "") or None
        if (
            observed.get("effect_disposition")
            != EffectDisposition.COMPLETED_SUCCESS.value
            or executed_provider is None
            or executed_model is None
        ):
            return self._result(
                request,
                execution_status="failed_after_live_response",
                live_call_succeeded=True,
                executed_provider=executed_provider,
                executed_model=executed_model,
                error="successful typed response omitted executed provider or model identity",
            )
        try:
            if not isinstance(response, LMResponse) or not isinstance(
                response.text, str
            ):
                raise ProgramOracleSemanticBackendError(
                    "typed provider returned an invalid DSPy response"
                )
            analysis = _parse_analysis_text(
                response.text, response_format=response_format
            )
        except Exception as exc:
            return self._result(
                request,
                execution_status="failed_after_live_response",
                live_call_succeeded=True,
                executed_provider=executed_provider,
                executed_model=executed_model,
                error=sanitize_diagnostic_text(str(exc)),
            )
        return self._result(
            request,
            execution_status="succeeded",
            live_call_succeeded=True,
            executed_provider=executed_provider,
            executed_model=executed_model,
            analysis=analysis,
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
    provider_name = (
        str(env.get("DSPX_ORACLE_SEMANTIC_PROVIDER", _DEFAULT_LIVE_PROVIDER))
        .strip()
        .lower()
    )
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

    env = os.environ if environ is None else environ
    settings = _live_settings(env, role=role)
    lm = _create_live_adapter(settings)
    return TypedProviderOracleSemanticBackend(
        provider_name=settings.provider_name,
        preferred_model=preferred_model,
        lm=lm,
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

    env = os.environ if environ is None else environ
    try:
        settings = _live_settings(env, role=role)
    except ProgramOracleSemanticBackendError as exc:
        return OracleSemanticPreflight(
            ready=False,
            backend_kind=backend_kind,
            preferred_model=preferred_model,
            configured_provider=provider_name or None,
            configured_model=None,
            fixture_path=None,
            checks=(
                {
                    "name": "provider_configuration",
                    "ok": False,
                    "detail": sanitize_diagnostic_text(str(exc)),
                },
            ),
        )
    # Preflight validates configuration only; no provider is constructed and no
    # request is dispatched, so ``live_verified`` stays false by contract.
    return OracleSemanticPreflight(
        ready=True,
        backend_kind=backend_kind,
        preferred_model=preferred_model,
        configured_provider=settings.provider_name,
        configured_model=settings.model,
        fixture_path=None,
        checks=(
            {
                "name": "provider_configuration",
                "ok": True,
                "provider": settings.provider_name,
                "model": settings.model,
                "model_override": settings.model_override,
                "endpoint": settings.endpoint_redacted,
                "timeout": settings.timeout,
                "credential_free": True,
                "dispatched": False,
            },
        ),
    )

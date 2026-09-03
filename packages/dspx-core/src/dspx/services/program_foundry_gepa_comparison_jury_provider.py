"""Foundry-only task-local providers over the maintained dspy-lm-auth backends."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import dspy

from dspx.dspy_typed_lm import DSPyTypedLMAdapter
from dspx.provider_contract import (
    EffectDisposition,
    ProviderInvocationError,
    ProviderRequest,
    ProviderResult,
)
from dspx.services.program_foundry_gepa_comparison_jury_owner import (
    OWNER_COMMIT,
    OWNER_TREE,
    OWNER_VERSION,
    VerifiedFoundryJuryOwner,
    verify_loaded_foundry_jury_owner,
)
from dspx.services.program_foundry_gepa_comparison_jury_provider_custody import (
    ALLOWED_REASONING_EFFORTS,
    AUTH_PROVIDER,
    CODEX_FAMILY,
    COPILOT_FAMILY,
    CREDENTIAL_MODE,
    DEFAULT_CODEX_MODEL,
    DEFAULT_REASONING_EFFORT,
    DEFAULT_TIMEOUT_SECONDS,
    MODEL_RE,
    PROVIDER_NAME,
    FoundryJuryCallCustodian,
    FoundryJuryProviderConfigurationError,
    FoundryJuryProviderFamily,
    canonical_ak_task_revalidator,
    closed_failure,
)
from dspx.services.program_foundry_gepa_comparison_jury_provider_metadata import (
    provider_metadata,
    validate_foundry_jury_provider_metadata,
)
from dspx.services.program_model_jury_judgment import (
    JUDGMENT_FIELD,
    judgment_field_text_from_completion,
)


class _FoundryJuryFormattingProvider:
    """Non-effectful provider used only to construct DSPx's sole LM adapter."""

    def __init__(self, model: str, provider_name: str = PROVIDER_NAME) -> None:
        self.model = model
        self.provider_name = provider_name

    def invoke(self, request: ProviderRequest) -> ProviderResult:
        del request
        raise ProviderInvocationError(
            "foundry jury calls require the receipt-bound JSON adapter",
            disposition=EffectDisposition.PREFLIGHT_REJECTED,
            provider=self.provider_name,
        )

    def dump_state(self) -> dict[str, object]:
        raise ProviderInvocationError(
            "foundry jury formatting provider has no persistent state",
            disposition=EffectDisposition.PREFLIGHT_REJECTED,
            provider=self.provider_name,
        )


def _message_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        closed_failure("adapter_message_content_invalid")
    parts: list[str] = []
    for block in content:
        if not isinstance(block, Mapping):
            closed_failure("adapter_message_content_invalid")
        typed_block = cast(Mapping[str, object], block)
        if typed_block.get("type") not in {"text", "input_text", "output_text"}:
            closed_failure("adapter_message_content_invalid")
        text = typed_block.get("text")
        if not isinstance(text, str):
            closed_failure("adapter_message_content_invalid")
        parts.append(text)
    return "".join(parts)


class FoundryJuryJSONAdapter(dspy.JSONAdapter):
    """DSPx-owned JSON formatting around one provider-neutral backend."""

    def __init__(
        self,
        *,
        owner: VerifiedFoundryJuryOwner,
        lm: DSPyTypedLMAdapter,
        backend: Any,
        custodian: FoundryJuryCallCustodian,
        model: str,
        reasoning_effort: str | None,
        timeout_seconds: float,
        family: FoundryJuryProviderFamily = CODEX_FAMILY,
    ) -> None:
        super().__init__(callbacks=None, use_native_function_calling=False)
        self._owner = owner
        self._lm = lm
        self._backend = backend
        self._custodian = custodian
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._timeout_seconds = timeout_seconds
        self._family = family
        self._local_terminal = False

    def __call__(
        self,
        lm: Any,
        lm_kwargs: dict[str, Any],
        signature: type[Any],
        demos: list[dict[str, Any]],
        inputs: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if self._local_terminal:
            # A completed provider call whose local post-processing failed latches
            # this adapter closed; later jurors fail without a provider call.
            closed_failure("adapter_session_terminal")
        if lm is not self._lm:
            closed_failure("adapter_lm_identity_drift")
        self._owner.revalidate()
        configured = dict(lm_kwargs)
        forbidden = {
            "tools",
            "tool_choice",
            "parallel_tool_calls",
            "stream",
            "n",
            "num_retries",
            "cache",
            "timeout",
            "reasoning_effort",
        }.intersection(configured)
        if forbidden:
            closed_failure("adapter_call_configuration_drift")
        try:
            juror = json.loads(str(inputs.get("juror_json") or ""))
        except json.JSONDecodeError:
            closed_failure("adapter_juror_identity_invalid")
        juror_id = (
            str(juror.get("id") or juror.get("perspective") or "")
            if isinstance(juror, Mapping)
            else ""
        )
        configured["response_format"] = {"type": "json_object"}
        processed = self._call_preprocess(lm, configured, signature, inputs)
        messages = self.format(processed, demos, inputs)
        request = self._render_request(lm, configured, cast(list[Any], messages))
        call_data = self._legacy_call_kwargs(request)
        raw_messages = call_data.pop("messages", None)
        for key in ("cache", "rollout_id", "response_format"):
            call_data.pop(key, None)
        if call_data or not isinstance(raw_messages, list):
            closed_failure("adapter_call_configuration_drift")
        backend_messages = []
        for message in raw_messages:
            if not isinstance(message, Mapping):
                closed_failure("adapter_message_invalid")
            typed_message = cast(Mapping[str, object], message)
            role = typed_message.get("role")
            if role not in self._family.allowed_roles:
                closed_failure("adapter_message_invalid")
            backend_messages.append(
                self._owner.message_type(
                    role=role,
                    content=_message_text(typed_message.get("content")),
                )
            )
        # Text transport for every family: DSPy's JSON instructions stay in the
        # prompt and DSPx parses the judgment locally, so no response_format or
        # reasoning controls reach a backend whose contract lacks them.
        prepared = self._backend.prepare(
            self._family.build_backend_request(
                self._owner,
                model=self._model,
                messages=tuple(backend_messages),
                reasoning_effort=self._reasoning_effort,
                timeout_seconds=self._timeout_seconds,
            )
        )
        semantic_hash = getattr(prepared, "semantic_request_sha256", None)
        if not isinstance(semantic_hash, str):
            closed_failure("owner_semantic_request_api_drift")

        def invoke(receipt: object) -> str:
            self._owner.revalidate()
            response = self._backend.invoke(prepared, outcome_receipt=receipt)
            if (
                type(response) is not self._owner.response_type
                or response.semantic_request_sha256 != semantic_hash
                or not isinstance(response.output_text, str)
            ):
                closed_failure("owner_backend_response_shape_drift")
            return response.output_text

        try:
            output_text = self._custodian.invoke(
                juror_id=juror_id,
                semantic_request_sha256=semantic_hash,
                invoke=invoke,
            )
        except BaseException:
            self._local_terminal = True
            raise
        try:
            return self._call_postprocess(
                processed,
                signature,
                [cast(str, output_text)],
                lm,
                configured,
            )
        except BaseException:
            self._custodian.latch_closed_after_completed_call()
            self._local_terminal = True
            raise

    def parse(self, signature: type[Any], completion: str) -> dict[str, Any]:
        """Parse the single `judgment_json` field with a closed shape tolerance.

        Some served models return the judgment object itself instead of wrapping
        it under `judgment_json`. Only a bare object whose key set equals the
        judgment contract exactly is re-wrapped; every other shape, and every
        value, is still judged by DSPy's parser and the closed judgment parser.
        """

        if set(signature.output_fields) == {JUDGMENT_FIELD}:
            field_text = judgment_field_text_from_completion(completion)
            if field_text is not None:
                completion = json.dumps({JUDGMENT_FIELD: field_text})
        return super().parse(signature, completion)

    async def acall(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        del args, kwargs
        closed_failure("async_call_forbidden")


class FoundryJuryConfiguredProvider:
    """Task-local provider runtime, deliberately outside the generic registry."""

    def __init__(
        self,
        *,
        owner: VerifiedFoundryJuryOwner,
        custodian: FoundryJuryCallCustodian,
        previous_lm: object | None,
        previous_adapter: object | None,
        execution_task_id: int,
        execution_claimant: str,
        model: str,
        reasoning_effort: str | None,
        timeout_seconds: float,
        previous_cost_map: str | None,
        family: FoundryJuryProviderFamily = CODEX_FAMILY,
    ) -> None:
        self._owner = owner
        self._custodian = custodian
        self._previous_lm = previous_lm
        self._previous_adapter = previous_adapter
        self._execution_task_id = execution_task_id
        self._execution_claimant = execution_claimant
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._timeout_seconds = timeout_seconds
        self._previous_cost_map = previous_cost_map
        self._family = family
        self._closed = False

    def metadata(self) -> Mapping[str, Any]:
        self._owner.revalidate()
        return provider_metadata(
            family=self._family,
            model=self._model,
            reasoning_effort=self._reasoning_effort,
            timeout_seconds=self._timeout_seconds,
            execution_task_id=self._execution_task_id,
            execution_claimant=self._execution_claimant,
            source_identity=self._owner.artifact.source_identity,
            dependency_identity=self._owner.artifact.dependency_identity,
        )

    def finalize(self) -> Mapping[str, Any]:
        return self._custodian.finalize()

    def close(self) -> None:
        if self._closed:
            return
        dspy.configure(lm=self._previous_lm, adapter=self._previous_adapter)
        if self._previous_cost_map is None:
            os.environ.pop("LITELLM_LOCAL_MODEL_COST_MAP", None)
        else:
            os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = self._previous_cost_map
        self._closed = True


def _assert_exact_runtime(
    owner: VerifiedFoundryJuryOwner,
    backend: Any,
    lm: DSPyTypedLMAdapter,
    *,
    model: str,
) -> None:
    owner.revalidate()
    provider = getattr(lm, "provider", None)
    if (
        type(backend) is not owner.backend_type
        or type(lm) is not DSPyTypedLMAdapter
        or type(provider) is not _FoundryJuryFormattingProvider
        or provider.model != model
        or lm.model != model
        or lm.cache is not False
        or lm.num_retries != 0
        or lm.callbacks != []
    ):
        raise FoundryJuryProviderConfigurationError(
            "owner backend or DSPx LM adapter configuration drifted"
        )


def configure_foundry_jury_provider(
    *,
    owner_source_root: Path,
    journal_parent: Path,
    execution_task_id: int,
    execution_claimant: str,
    repo_root: Path,
    contract_sha256: str,
    expected_juror_ids: Sequence[str],
    model: str | None = None,
    reasoning_effort: str | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    family: FoundryJuryProviderFamily = CODEX_FAMILY,
) -> FoundryJuryConfiguredProvider:
    """Configure one exact foundry-only provider after an outer attempt exists."""

    label = family.auth_provider
    model = family.resolve_model(model)
    reasoning_effort = family.resolve_reasoning_effort(reasoning_effort)
    if not family.model_allowed(model):
        raise FoundryJuryProviderConfigurationError(f"{label} model is not allowed")
    if not family.reasoning_effort_allowed(reasoning_effort):
        raise FoundryJuryProviderConfigurationError(
            f"{label} reasoning effort is not allowed"
        )
    if timeout_seconds != DEFAULT_TIMEOUT_SECONDS:
        raise FoundryJuryProviderConfigurationError(
            f"{label} timeout must match the reviewed custody contract"
        )
    previous_cost_map = os.environ.get("LITELLM_LOCAL_MODEL_COST_MAP")
    os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    previous_lm = getattr(dspy.settings, "lm", None)
    previous_adapter = getattr(dspy.settings, "adapter", None)
    configured: FoundryJuryConfiguredProvider | None = None
    try:
        owner = verify_loaded_foundry_jury_owner(owner_source_root, family)
        backend = family.construct_backend(owner)
        lm = DSPyTypedLMAdapter(
            _FoundryJuryFormattingProvider(model, family.provider_name),
            cache=False,
            callbacks=[],
        )
        _assert_exact_runtime(owner, backend, lm, model=model)
        revalidator = canonical_ak_task_revalidator(
            execution_task_id=execution_task_id,
            execution_claimant=execution_claimant,
            repo_root=repo_root,
            minimum_lease_seconds=timeout_seconds + 30.0,
            family=family,
        )
        revalidator()
        custodian = FoundryJuryCallCustodian(
            journal_parent=journal_parent,
            owner=owner,
            execution_task_id=execution_task_id,
            contract_sha256=contract_sha256,
            expected_juror_ids=expected_juror_ids,
            requested_route=family.requested_route(model),
            resolved_route=family.resolved_route(model),
            authority_revalidator=revalidator,
            family=family,
        )
        adapter = FoundryJuryJSONAdapter(
            owner=owner,
            lm=lm,
            backend=backend,
            custodian=custodian,
            model=model,
            reasoning_effort=reasoning_effort,
            timeout_seconds=timeout_seconds,
            family=family,
        )
        configured = FoundryJuryConfiguredProvider(
            owner=owner,
            custodian=custodian,
            previous_lm=previous_lm,
            previous_adapter=previous_adapter,
            execution_task_id=execution_task_id,
            execution_claimant=execution_claimant,
            model=model,
            reasoning_effort=reasoning_effort,
            timeout_seconds=timeout_seconds,
            previous_cost_map=previous_cost_map,
            family=family,
        )
        dspy.configure(lm=lm, adapter=adapter)
        configured.metadata()
        return configured
    except BaseException:
        if configured is not None:
            configured.close()
        else:
            dspy.configure(lm=previous_lm, adapter=previous_adapter)
            if previous_cost_map is None:
                os.environ.pop("LITELLM_LOCAL_MODEL_COST_MAP", None)
            else:
                os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = previous_cost_map
        raise


__all__ = [
    "ALLOWED_REASONING_EFFORTS",
    "AUTH_PROVIDER",
    "CODEX_FAMILY",
    "COPILOT_FAMILY",
    "CREDENTIAL_MODE",
    "DEFAULT_CODEX_MODEL",
    "DEFAULT_REASONING_EFFORT",
    "DEFAULT_TIMEOUT_SECONDS",
    "MODEL_RE",
    "OWNER_COMMIT",
    "OWNER_TREE",
    "OWNER_VERSION",
    "PROVIDER_NAME",
    "FoundryJuryConfiguredProvider",
    "FoundryJuryJSONAdapter",
    "FoundryJuryProviderConfigurationError",
    "FoundryJuryProviderFamily",
    "configure_foundry_jury_provider",
    "validate_foundry_jury_provider_metadata",
]

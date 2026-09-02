"""Foundry-only Codex provider over the maintained dspy-lm-auth backend."""

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
    expected_foundry_jury_dependency_identity,
    expected_foundry_jury_source_identity,
    verify_loaded_foundry_jury_owner,
)
from dspx.services.program_foundry_gepa_comparison_jury_provider_custody import (
    ALLOWED_REASONING_EFFORTS,
    AUTH_PROVIDER,
    CREDENTIAL_MODE,
    DEFAULT_CODEX_MODEL,
    DEFAULT_REASONING_EFFORT,
    DEFAULT_TIMEOUT_SECONDS,
    MODEL_RE,
    PROVIDER_NAME,
    FoundryJuryCallCustodian,
    FoundryJuryProviderConfigurationError,
    canonical_ak_task_revalidator,
    closed_failure,
)
from dspx.services.soomfon_provider_outcome_receipt_contract import (
    canonical_json,
    sha256,
)


class _FoundryJuryFormattingProvider:
    """Non-effectful provider used only to construct DSPx's sole LM adapter."""

    def __init__(self, model: str) -> None:
        self.model = model

    def invoke(self, request: ProviderRequest) -> ProviderResult:
        del request
        raise ProviderInvocationError(
            "foundry jury calls require the receipt-bound JSON adapter",
            disposition=EffectDisposition.PREFLIGHT_REJECTED,
            provider=PROVIDER_NAME,
        )

    def dump_state(self) -> dict[str, object]:
        raise ProviderInvocationError(
            "foundry jury formatting provider has no persistent state",
            disposition=EffectDisposition.PREFLIGHT_REJECTED,
            provider=PROVIDER_NAME,
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
        reasoning_effort: str,
        timeout_seconds: float,
    ) -> None:
        super().__init__(callbacks=None, use_native_function_calling=False)
        self._owner = owner
        self._lm = lm
        self._backend = backend
        self._custodian = custodian
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._timeout_seconds = timeout_seconds
        self._local_terminal = False

    def __call__(
        self,
        lm: Any,
        lm_kwargs: dict[str, Any],
        signature: type[Any],
        demos: list[dict[str, Any]],
        inputs: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if self._local_terminal or lm is not self._lm:
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
            if role not in {"system", "developer", "user", "assistant"}:
                closed_failure("adapter_message_invalid")
            backend_messages.append(
                self._owner.message_type(
                    role=role,
                    content=_message_text(typed_message.get("content")),
                )
            )
        prepared = self._backend.prepare(
            self._owner.request_type(
                model=self._model,
                messages=tuple(backend_messages),
                reasoning_effort=self._reasoning_effort,
                response_format="json_object",
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
        reasoning_effort: str,
        timeout_seconds: float,
        previous_cost_map: str | None,
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
        self._closed = False

    def metadata(self) -> Mapping[str, Any]:
        self._owner.revalidate()
        return {
            "status": "configured",
            "provider": PROVIDER_NAME,
            "model": self._model,
            "requested_route": f"dspy-lm-auth:codex:{self._model}",
            "resolved_route": f"openai:{self._model}:responses",
            "auth_provider": AUTH_PROVIDER,
            "credential_mode": CREDENTIAL_MODE,
            "reasoning_effort": self._reasoning_effort,
            "num_retries": 0,
            "cache": False,
            "timeout_seconds": self._timeout_seconds,
            "sync_only": True,
            "fallback_allowed": False,
            "health_probe_allowed": False,
            "execution_task_id": self._execution_task_id,
            "execution_claimant": self._execution_claimant,
            "owner_commit": OWNER_COMMIT,
            "owner_tree": OWNER_TREE,
            "owner_version": OWNER_VERSION,
            "source_identity_sha256": sha256(
                canonical_json(self._owner.artifact.source_identity)
            ),
            "dependency_identity_sha256": sha256(
                canonical_json(self._owner.artifact.dependency_identity)
            ),
        }

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


def validate_foundry_jury_provider_metadata(
    value: Mapping[str, Any],
    *,
    execution_task_id: int,
    execution_claimant: str,
    model: str,
    reasoning_effort: str,
) -> dict[str, Any]:
    expected = {
        "status": "configured",
        "provider": PROVIDER_NAME,
        "model": model,
        "requested_route": f"dspy-lm-auth:codex:{model}",
        "resolved_route": f"openai:{model}:responses",
        "auth_provider": AUTH_PROVIDER,
        "credential_mode": CREDENTIAL_MODE,
        "reasoning_effort": reasoning_effort,
        "num_retries": 0,
        "cache": False,
        "timeout_seconds": DEFAULT_TIMEOUT_SECONDS,
        "sync_only": True,
        "fallback_allowed": False,
        "health_probe_allowed": False,
        "execution_task_id": execution_task_id,
        "execution_claimant": execution_claimant,
        "owner_commit": OWNER_COMMIT,
        "owner_tree": OWNER_TREE,
        "owner_version": OWNER_VERSION,
        "source_identity_sha256": sha256(
            canonical_json(expected_foundry_jury_source_identity())
        ),
        "dependency_identity_sha256": sha256(
            canonical_json(expected_foundry_jury_dependency_identity())
        ),
    }
    if dict(value) != expected:
        raise FoundryJuryProviderConfigurationError(
            "task-local provider metadata drifted"
        )
    return expected


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
    model: str = DEFAULT_CODEX_MODEL,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> FoundryJuryConfiguredProvider:
    """Configure one exact foundry-only provider after an outer attempt exists."""

    if MODEL_RE.fullmatch(model) is None:
        raise FoundryJuryProviderConfigurationError("Codex model is not allowed")
    if reasoning_effort not in ALLOWED_REASONING_EFFORTS:
        raise FoundryJuryProviderConfigurationError(
            "Codex reasoning effort is not allowed"
        )
    if timeout_seconds != DEFAULT_TIMEOUT_SECONDS:
        raise FoundryJuryProviderConfigurationError(
            "Codex timeout must match the reviewed custody contract"
        )
    previous_cost_map = os.environ.get("LITELLM_LOCAL_MODEL_COST_MAP")
    os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    previous_lm = getattr(dspy.settings, "lm", None)
    previous_adapter = getattr(dspy.settings, "adapter", None)
    configured: FoundryJuryConfiguredProvider | None = None
    try:
        owner = verify_loaded_foundry_jury_owner(owner_source_root)
        backend = owner.backend_type()
        lm = DSPyTypedLMAdapter(
            _FoundryJuryFormattingProvider(model),
            cache=False,
            callbacks=[],
        )
        _assert_exact_runtime(owner, backend, lm, model=model)
        revalidator = canonical_ak_task_revalidator(
            execution_task_id=execution_task_id,
            execution_claimant=execution_claimant,
            repo_root=repo_root,
            minimum_lease_seconds=timeout_seconds + 30.0,
        )
        revalidator()
        custodian = FoundryJuryCallCustodian(
            journal_parent=journal_parent,
            owner=owner,
            execution_task_id=execution_task_id,
            contract_sha256=contract_sha256,
            expected_juror_ids=expected_juror_ids,
            requested_route=f"dspy-lm-auth:codex:{model}",
            resolved_route=f"openai:{model}:responses",
            authority_revalidator=revalidator,
        )
        adapter = FoundryJuryJSONAdapter(
            owner=owner,
            lm=lm,
            backend=backend,
            custodian=custodian,
            model=model,
            reasoning_effort=reasoning_effort,
            timeout_seconds=timeout_seconds,
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

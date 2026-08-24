"""Exact external LM and JSON adapter for validated Soomfon custody only."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, cast

import dspy
from dspy.adapters.base import legacy_outputs_from_lm_response

from dspx.services.provider_outcome_receipt_contract import canonical_json, sha256
from dspx.services.soomfon_evaluation_provider import (
    AUTH_PROVIDER,
    CREDENTIAL_MODE,
    REASONING_EFFORT,
    REQUESTED_MODEL,
    REQUESTED_ROUTE,
    RESOLVED_MODEL,
    RESOLVED_ROUTE,
    TIMEOUT_SECONDS,
    SoomfonCallCustodian,
    SoomfonProviderError,
    VerifiedSoomfonOwner,
    logical_signature_name,
    validate_soomfon_provider_evidence,
    verify_loaded_soomfon_owner,
)


class SoomfonJSONAdapter(dspy.JSONAdapter):
    """One-invocation JSON adapter with no ChatAdapter fallback path."""

    def __init__(
        self,
        *,
        owner: VerifiedSoomfonOwner,
        lm: Any,
        custodian: SoomfonCallCustodian,
        mode: str,
    ) -> None:
        super().__init__(callbacks=None, use_native_function_calling=False)
        self._owner = owner
        self._lm = lm
        self._custodian = custodian
        self._mode = mode
        self._local_terminal = False

    def _exact_semantic_request(
        self, *, messages: list[dict[str, Any]], call_kwargs: Mapping[str, Any]
    ) -> tuple[str, dict[str, Any]]:
        self._owner.revalidate()
        merged = {**self._lm.kwargs, **dict(call_kwargs)}
        merged.pop("cache", None)
        merged.pop("rollout_id", None)
        merged.pop("outcome_receipt", None)
        request = {
            "model": self._lm.model,
            "messages": messages,
            **merged,
        }
        builder = getattr(self._owner.lm_module, "_build_codex_responses_request", None)
        hasher = getattr(self._owner.receipt_module, "semantic_request_sha256", None)
        if not callable(builder) or not callable(hasher):
            raise SoomfonProviderError("owner_semantic_request_api_drift")
        semantic = builder(request)
        digest = hasher(semantic)
        if not isinstance(digest, str):
            raise SoomfonProviderError("semantic_request_hash_drift")
        return digest, dict(call_kwargs)

    def __call__(
        self,
        lm: Any,
        lm_kwargs: dict[str, Any],
        signature: type[Any],
        demos: list[dict[str, Any]],
        inputs: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if self._local_terminal or lm is not self._lm:
            raise SoomfonProviderError("adapter_lm_identity_drift")
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
            raise SoomfonProviderError("adapter_call_configuration_drift")
        configured["response_format"] = {"type": "json_object"}
        processed = self._call_preprocess(lm, configured, signature, inputs)
        messages = self.format(processed, demos, inputs)
        request = self._render_request(lm, configured, cast(list[Any], messages))
        call_data = self._legacy_call_kwargs(request)
        raw_messages = cast(list[dict[str, Any]], call_data.pop("messages"))
        semantic_hash, call_data = self._exact_semantic_request(
            messages=raw_messages,
            call_kwargs=call_data,
        )

        def invoke(receipt: object) -> object:
            self._owner.revalidate()
            return lm(
                messages=raw_messages,
                outcome_receipt=receipt,
                **call_data,
            )

        try:
            raw_response = self._custodian.invoke(
                signature_name=logical_signature_name(signature, mode=self._mode),
                semantic_request_sha256=semantic_hash,
                invoke=invoke,
            )
            legacy_response = cast(list[dict[str, Any] | str | None], raw_response)
            normalized = self._normalize_legacy_outputs(legacy_response, request)
            maybe_outputs = legacy_outputs_from_lm_response(normalized)
            if any(item is None for item in maybe_outputs):
                raise SoomfonProviderError("owner_lm_response_shape_drift")
            outputs = cast(list[dict[str, Any] | str], maybe_outputs)
            return self._call_postprocess(processed, signature, outputs, lm, configured)
        except BaseException:
            self._local_terminal = True
            raise

    async def acall(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        del args, kwargs
        raise SoomfonProviderError("async_call_forbidden")

    def evidence(self) -> dict[str, object]:
        return self._custodian.evidence()

    def finalize(self) -> dict[str, object]:
        if self._local_terminal:
            raise SoomfonProviderError("adapter_terminal")
        return self._custodian.finalize()


class SoomfonConfiguredProvider:
    """Task-local configuration holder; not a DSPy LM or DSPx provider."""

    def __init__(
        self,
        *,
        owner: VerifiedSoomfonOwner,
        lm: Any,
        adapter: SoomfonJSONAdapter,
        previous_lm: object | None,
        previous_adapter: object | None,
        contract_sha256: str,
        mode: str,
    ) -> None:
        self.owner = owner
        self.lm = lm
        self.adapter = adapter
        self.previous_lm = previous_lm
        self.previous_adapter = previous_adapter
        self.contract_sha256 = contract_sha256
        self.mode = mode

    def metadata(self) -> dict[str, object]:
        self.owner.revalidate()
        return {
            "schema_version": "soomfon-dspy-lm-auth-runtime-v1",
            "provider": "soomfon-dspy-lm-auth",
            "model": REQUESTED_MODEL,
            "requested_route": REQUESTED_ROUTE,
            "resolved_route": RESOLVED_ROUTE,
            "auth_provider": AUTH_PROVIDER,
            "credential_mode": CREDENTIAL_MODE,
            "reasoning_effort": REASONING_EFFORT,
            "num_retries": 0,
            "cache": False,
            "timeout_seconds": TIMEOUT_SECONDS,
            "sync_only": True,
            "fallback_allowed": False,
            "health_probe_allowed": False,
            "contract_sha256": self.contract_sha256,
            "mode": self.mode,
            "source_identity_sha256": sha256(
                canonical_json(self.owner.artifact.source_identity)
            ),
            "dependency_identity_sha256": sha256(
                canonical_json(self.owner.artifact.dependency_identity)
            ),
        }

    def evidence(self) -> dict[str, object]:
        return self.adapter.evidence()

    def finalize(self) -> dict[str, object]:
        return self.adapter.finalize()

    def close(self) -> None:
        dspy.configure(lm=self.previous_lm, adapter=self.previous_adapter)


def _assert_exact_lm(owner: VerifiedSoomfonOwner, lm: Any) -> None:
    owner.revalidate()
    if (
        type(lm) is not owner.lm_type
        or getattr(lm, "original_model_string", None) != REQUESTED_MODEL
        or getattr(lm, "resolved_model_string", None) != RESOLVED_MODEL
        or getattr(lm, "model", None) != RESOLVED_MODEL
        or getattr(lm, "model_type", None) != "responses"
        or getattr(lm, "auth_provider", None) != AUTH_PROVIDER
        or getattr(lm, "credential_mode", None) != CREDENTIAL_MODE
        or getattr(lm, "auth_storage", "drift") is not None
        or getattr(lm, "_uses_codex_route", None) is not True
        or getattr(lm, "num_retries", None) != 0
        or getattr(lm, "cache", None) is not False
        or getattr(lm, "callbacks", None) != []
    ):
        raise SoomfonProviderError("owner_lm_configuration_drift")
    kwargs = getattr(lm, "kwargs", None)
    if (
        not isinstance(kwargs, Mapping)
        or kwargs.get("reasoning_effort") != REASONING_EFFORT
        or kwargs.get("timeout") != TIMEOUT_SECONDS
        or kwargs.get("api_base") != "https://chatgpt.com/backend-api/codex"
        or kwargs.get("temperature", "drift") is not None
        or kwargs.get("max_tokens", "drift") is not None
        or set(kwargs)
        != {"reasoning_effort", "timeout", "api_base", "temperature", "max_tokens"}
    ):
        raise SoomfonProviderError("owner_lm_kwargs_drift")


def _call_authority_revalidator(custody: Any) -> None:
    from dspx.services.soomfon_evaluation_authorization import (
        validate_execution_authorization,
    )

    validated = validate_execution_authorization(
        path=custody.authorization_path,
        expected_sha256=custody.authorization_sha256,
        repo_root=custody.repo_root,
        contract_sha256=custody.contract_sha256,
        minimum_lease_seconds=90.0,
    )
    if (
        validated.execution_task_id != custody.execution_task_id
        or validated.authorization_sha256 != custody.authorization_sha256
        or validated.ak_reconciliation_sha256 != custody.ak_reconciliation_sha256
        or validated.contract_sha256 != custody.contract_sha256
        or validated.repo != str(custody.repo_root)
    ):
        raise SoomfonProviderError("canonical_authority_identity_drift")


def configure_soomfon_provider(
    custody: Any,
) -> tuple[dict[str, object], SoomfonConfiguredProvider, object | None]:
    """Configure only from an exact validated SoomfonRuntimeCustody object."""

    from dspx.services.soomfon_evaluation_contract import (
        CONTRACT_PREPARATION_TASK_ID,
        REVIEWED_CONTRACT_SHA256,
    )
    from dspx.services.soomfon_evaluation_custody import (
        SoomfonRuntimeCustody,
        marker_sha256,
    )

    if (
        type(custody) is not SoomfonRuntimeCustody
        or custody.contract_sha256 != REVIEWED_CONTRACT_SHA256
        or custody.execution_task_id <= CONTRACT_PREPARATION_TASK_ID
    ):
        raise SoomfonProviderError("runtime_custody_identity_drift")
    journal_parent = Path(f"/proc/self/fd/{custody.provider_journal_fd}").resolve(
        strict=True
    )
    owner = verify_loaded_soomfon_owner(custody.owner_source_root)
    owner.revalidate()
    lm = owner.lm_type(
        REQUESTED_MODEL,
        auth_provider=AUTH_PROVIDER,
        credential_mode=CREDENTIAL_MODE,
        reasoning_effort=REASONING_EFFORT,
        num_retries=0,
        cache=False,
        timeout=TIMEOUT_SECONDS,
    )
    _assert_exact_lm(owner, lm)
    custodian = SoomfonCallCustodian(
        journal_parent=journal_parent,
        artifact=owner.artifact,
        execution_task_id=custody.execution_task_id,
        contract_sha256=custody.contract_sha256,
        mode=custody.mode,
        ledger_sha256=marker_sha256(custody.marker_fd),
        authority_revalidator=lambda: _call_authority_revalidator(custody),
    )
    adapter = SoomfonJSONAdapter(
        owner=owner, lm=lm, custodian=custodian, mode=custody.mode
    )
    previous_lm = getattr(dspy.settings, "lm", None)
    previous_adapter = getattr(dspy.settings, "adapter", None)
    configured = SoomfonConfiguredProvider(
        owner=owner,
        lm=lm,
        adapter=adapter,
        previous_lm=previous_lm,
        previous_adapter=previous_adapter,
        contract_sha256=custody.contract_sha256,
        mode=custody.mode,
    )
    dspy.configure(lm=lm, adapter=adapter)
    try:
        evidence = configured.evidence()
        validate_soomfon_provider_evidence(evidence, mode=custody.mode)
        metadata = configured.metadata()
    except BaseException:
        configured.close()
        raise
    return (
        {
            "status": "configured",
            "metadata": metadata,
            "effect_evidence": evidence,
        },
        configured,
        previous_lm,
    )

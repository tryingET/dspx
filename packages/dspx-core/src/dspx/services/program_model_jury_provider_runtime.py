"""Task-local provider runtime and process-slot support for program juries."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Callable, Mapping, Protocol, Sequence

from dspx.services.program_foundry_gepa_comparison_jury_provider_family import (
    TASK_LOCAL_PROVIDER_NAMES,
)
from dspx.services.program_model_jury_execution import ProgramModelJuryExecutionError

_TASK_LOCAL_PROVIDER_RUNTIME_NAMES = TASK_LOCAL_PROVIDER_NAMES
_PROVIDER_RUNTIME_BINDING_TOKEN = object()
_MODEL_JURY_PROCESS_LOCK = threading.Lock()
_MODEL_JURY_SLOT_TOKEN = object()


class ProgramModelJuryProviderExecutionError(RuntimeError):
    """Closed provider-runtime failure with an explicit effect disposition."""

    def __init__(self, reason: str, *, effect_indeterminate: bool) -> None:
        super().__init__("program model jury provider execution failed")
        self.reason = reason
        self.effect_indeterminate = effect_indeterminate


class ProgramModelJuryProviderRuntime(Protocol):
    def metadata(self) -> Mapping[str, Any]: ...

    def finalize(self) -> Mapping[str, Any]: ...

    def close(self) -> None: ...


ProgramModelJuryProviderRuntimeFactory = Callable[
    [Sequence[Mapping[str, Any]]], ProgramModelJuryProviderRuntime
]


class ProgramModelJuryProviderRuntimeBinding:
    """Internal binding used only by the receipt-owning foundry path."""

    __slots__ = ("_factory",)

    def __init__(
        self,
        factory: ProgramModelJuryProviderRuntimeFactory,
        *,
        token: object,
    ) -> None:
        if token is not _PROVIDER_RUNTIME_BINDING_TOKEN or not callable(factory):
            raise TypeError("provider runtime binding is created by the foundry owner")
        self._factory = factory

    @property
    def factory(self) -> ProgramModelJuryProviderRuntimeFactory:
        return self._factory


def _bind_program_model_jury_provider_runtime(
    factory: ProgramModelJuryProviderRuntimeFactory,
) -> ProgramModelJuryProviderRuntimeBinding:
    return ProgramModelJuryProviderRuntimeBinding(
        factory, token=_PROVIDER_RUNTIME_BINDING_TOKEN
    )


class ProgramModelJuryProcessSlot:
    """Active ownership of the process-global DSPy configuration boundary."""

    __slots__ = ("_active", "_token")

    def __init__(self, *, token: object) -> None:
        if token is not _MODEL_JURY_SLOT_TOKEN:
            raise TypeError("model jury process slot is internally owned")
        self._token = token
        self._active = True


@contextmanager
def _model_jury_process_slot() -> Iterator[ProgramModelJuryProcessSlot]:
    if not _MODEL_JURY_PROCESS_LOCK.acquire(blocking=False):
        raise ProgramModelJuryExecutionError(
            "another process-global model jury runtime is already active"
        )
    slot = ProgramModelJuryProcessSlot(token=_MODEL_JURY_SLOT_TOKEN)
    try:
        yield slot
    finally:
        slot._active = False
        _MODEL_JURY_PROCESS_LOCK.release()


def validate_model_jury_process_slot(slot: ProgramModelJuryProcessSlot) -> None:
    if (
        type(slot) is not ProgramModelJuryProcessSlot
        or slot._token is not _MODEL_JURY_SLOT_TOKEN
        or slot._active is not True
        or not _MODEL_JURY_PROCESS_LOCK.locked()
    ):
        raise ProgramModelJuryExecutionError("model jury process slot is inactive")


def run_program_model_jurors(
    *,
    selected: Sequence[Mapping[str, Any]],
    rubrics: Mapping[str, Mapping[str, Any]],
    candidate_identity: Mapping[str, Any],
    evidence_json: str,
    adjudicator: Mapping[str, Any],
    provider: str | None,
    configure_provider: Callable[[str | None], Mapping[str, Any]],
    run_juror: Callable[..., dict[str, Any]],
    sanitize_diagnostic: Callable[[BaseException], str],
    provider_runtime_binding: ProgramModelJuryProviderRuntimeBinding | None,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any] | None]:
    """Execute selected jurors and close an optional foundry-owned runtime."""

    if (
        provider_runtime_binding is not None
        and provider not in _TASK_LOCAL_PROVIDER_RUNTIME_NAMES
    ):
        raise ProgramModelJuryExecutionError(
            "task-local provider runtime binding is restricted to the foundry provider"
        )
    provider_runtime: ProgramModelJuryProviderRuntime | None = None
    if provider_runtime_binding is None:
        provider_config = dict(configure_provider(provider))
    else:
        try:
            provider_runtime = provider_runtime_binding.factory(selected)
            provider_config = dict(provider_runtime.metadata())
        except ProgramModelJuryProviderExecutionError:
            raise
        except Exception as exc:
            diagnostic = sanitize_diagnostic(exc)
            raise ProgramModelJuryExecutionError(
                "task-local model jury provider configuration failed: "
                f"{type(exc).__name__}: {diagnostic}"
            ) from exc

    juror_results: list[dict[str, Any]] = []
    provider_outcome_evidence: dict[str, Any] | None = None
    try:
        for juror in selected:
            juror_id = str(juror.get("id") or juror.get("perspective") or "unknown")
            try:
                judgment = run_juror(
                    juror=juror,
                    rubric=rubrics.get(juror_id, {"juror_id": juror_id}),
                    candidate_identity=candidate_identity,
                    evidence_json=evidence_json,
                    adjudicator=adjudicator,
                )
                juror_results.append(
                    {
                        "juror_id": juror_id,
                        "perspective": juror.get("perspective"),
                        "provider": provider_config.get("provider")
                        if provider_runtime is not None
                        else juror.get("provider") or provider_config.get("provider"),
                        "model": provider_config.get("model")
                        if provider_runtime is not None
                        else juror.get("model") or provider_config.get("provider"),
                        "execution_mode": "provider_backed_model",
                        "status": "judged",
                        "judgment": judgment,
                    }
                )
            except ProgramModelJuryProviderExecutionError as exc:
                if exc.effect_indeterminate:
                    raise
                juror_results.append(
                    {
                        "juror_id": juror_id,
                        "perspective": juror.get("perspective"),
                        "provider": provider_config.get("provider"),
                        "model": provider_config.get("model"),
                        "execution_mode": "provider_backed_model",
                        "status": "failed",
                        "error": {
                            "type": type(exc).__name__,
                            "message": exc.reason,
                        },
                    }
                )
            except Exception as exc:
                juror_results.append(
                    {
                        "juror_id": juror_id,
                        "perspective": juror.get("perspective"),
                        "provider": juror.get("provider")
                        or provider_config.get("provider"),
                        "model": juror.get("model") or provider_config.get("provider"),
                        "execution_mode": "provider_backed_model",
                        "status": "failed",
                        "error": {
                            "type": type(exc).__name__,
                            "message": sanitize_diagnostic(exc),
                        },
                    }
                )
        if provider_runtime is not None:
            provider_outcome_evidence = dict(provider_runtime.finalize())
    finally:
        if provider_runtime is not None:
            provider_runtime.close()
    return provider_config, juror_results, provider_outcome_evidence


__all__ = [
    "ProgramModelJuryExecutionError",
    "ProgramModelJuryProcessSlot",
    "ProgramModelJuryProviderExecutionError",
    "ProgramModelJuryProviderRuntime",
    "ProgramModelJuryProviderRuntimeBinding",
]

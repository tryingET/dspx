# summary: "Receipt-bound semantic v11 request execution and fail-closed reduction."
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, cast

from dspx.dtos import LMRequest
from dspx.services.program_oracle_semantic_adapter_v11 import (
    ReceiptSafeDspyLMAuthLM,
)
from dspx.services.program_oracle_semantic_artifacts_v11 import load_case_custody
from dspx.services.program_oracle_semantic_backend import (
    _analysis_prompt,
    _analysis_response_format,
)
from dspx.services.program_oracle_semantic_contract_v11 import (
    CASE_ORDER,
    SemanticV11Error,
    semantic_request_sha256,
)
from dspx.services.program_oracle_semantic_identity_v11 import PreparedReceipt
from dspx.services.program_oracle_semantic_result_v11 import (
    evaluate_semantic_response,
    semantic_error_result,
)
from dspx.services.provider_outcome_receipt_contract import (
    ProviderOutcomeConsumerError,
    ReceiptProjection,
    SemanticOutcome,
)
from dspx.services.provider_outcome_receipt_reducer import (
    reduce_verified_chain,
    verify_receipt_chain,
)

DEFAULT_CODEX_INSTRUCTIONS = "You are a helpful assistant."
RESOLVED_MODEL = "openai/gpt-5.6-sol"
_EVALUATED_CASE_TOKEN = object()
CorpusDisposition = Literal["effect_indeterminate", "error", "failed", "passed"]


class EvaluatedCase:
    """Opaque current-process case reduction derived from retained custody."""

    __slots__ = (
        "case_id",
        "semantic_outcome",
        "score",
        "projection",
        "observed_model",
        "_sealed",
    )

    case_id: str
    semantic_outcome: SemanticOutcome
    score: Mapping[str, Any] | None
    projection: ReceiptProjection
    observed_model: str | None
    _sealed: bool

    def __init__(
        self,
        *,
        case_id: str,
        semantic_outcome: SemanticOutcome,
        score: Mapping[str, Any] | None,
        projection: ReceiptProjection,
        observed_model: str | None,
        token: object,
    ) -> None:
        if token is not _EVALUATED_CASE_TOKEN:
            raise TypeError("EvaluatedCase is derived from retained case custody")
        object.__setattr__(self, "case_id", case_id)
        object.__setattr__(self, "semantic_outcome", semantic_outcome)
        object.__setattr__(self, "score", dict(score) if score is not None else None)
        object.__setattr__(self, "projection", projection)
        object.__setattr__(self, "observed_model", observed_model)
        object.__setattr__(self, "_sealed", True)

    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "_sealed", False):
            raise TypeError("EvaluatedCase is immutable")
        object.__setattr__(self, name, value)

    def payload(self) -> dict[str, Any]:
        if type(self) is not EvaluatedCase:
            raise SemanticV11Error("evaluated case type drift")
        return {
            "case_id": self.case_id,
            "semantic_outcome": self.semantic_outcome,
            "score": dict(self.score) if self.score is not None else None,
            "provider_outcome": self.projection.payload(),
            "observed_model": self.observed_model,
        }


def normalized_semantic_request(request: Any) -> dict[str, Any]:
    """Build the exact seven-key owner Responses projection before effect."""

    response_format = _analysis_response_format(request)
    return {
        "input": [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": _analysis_prompt(request)}],
            }
        ],
        "instructions": DEFAULT_CODEX_INSTRUCTIONS,
        "model": RESOLVED_MODEL,
        "reasoning": {"effort": "max", "summary": "auto"},
        "store": False,
        "stream": True,
        "text": {"format": response_format},
    }


def invoke_with_lm(
    lm: ReceiptSafeDspyLMAuthLM, prepared: PreparedReceipt
) -> tuple[str, str]:
    """Gate-4 call surface; the exact request derives from the bound case."""

    if type(lm) is not ReceiptSafeDspyLMAuthLM or type(prepared) is not PreparedReceipt:
        raise SemanticV11Error("prepared semantic request/capability drift")
    request = prepared._case.materialized_request()
    semantic = normalized_semantic_request(request)
    if (
        semantic != prepared.semantic_request
        or semantic_request_sha256(semantic)
        != prepared.reservation.semantic_request_sha256
    ):
        raise SemanticV11Error("prepared semantic request/capability drift")
    prepared.require_effect_capability()
    response = lm.generate(
        LMRequest(prompt=_analysis_prompt(request)),
        response_format=_analysis_response_format(request),
        prepared_receipt=prepared,
        cache=False,
        num_retries=0,
    )
    outputs = response.outputs
    if (
        not isinstance(outputs, list)
        or len(outputs) != 1
        or not isinstance(outputs[0], str)
    ):
        raise SemanticV11Error(
            "receipt-bound provider returned invalid output cardinality"
        )
    observed = response.model
    if (
        not isinstance(observed, str)
        or not observed
        or len(observed.encode("utf-8")) > 128
        or any(ord(char) < 32 or ord(char) == 127 for char in observed)
    ):
        raise SemanticV11Error("observed model label is not bounded")
    return outputs[0], observed


def _projection_from_error(exc: ProviderOutcomeConsumerError) -> ReceiptProjection:
    return ReceiptProjection(
        provider_outcome_receipt="rejected",
        request_acknowledged=None,
        external_effect_possible=exc.effect_possible,
        producer_terminal=None,
        empirical_disposition=(
            "effect_indeterminate" if exc.effect_possible else "error"
        ),
        reason=exc.reason,
    )


def reduce_prepared_fixture(prepared: PreparedReceipt) -> dict[str, Any]:
    """Authority-false diagnostic projection; never supplies v11 lifecycle facts."""

    if type(prepared) is not PreparedReceipt:
        raise SemanticV11Error("prepared receipt capability type drift")
    try:
        journal = prepared.journal.load_verified()
        chain = verify_receipt_chain(journal)
        reduced = reduce_verified_chain(chain, semantic_outcome="not_evaluated")
        projection = ReceiptProjection(
            provider_outcome_receipt="accepted",
            request_acknowledged=reduced.request_acknowledged,
            external_effect_possible=reduced.external_effect_possible,
            producer_terminal=reduced.terminal,
            empirical_disposition=reduced.empirical_disposition,
            reason=reduced.reason,
        )
    except ProviderOutcomeConsumerError as exc:
        projection = _projection_from_error(exc)
    return projection.payload()


def execute_case(
    prepared: PreparedReceipt, *, lm: ReceiptSafeDspyLMAuthLM
) -> EvaluatedCase:
    """Execute one exact bound case through only the receipt-safe adapter."""

    if (
        type(prepared) is not PreparedReceipt
        or not prepared.attempt.live_authorized
        or semantic_request_sha256(prepared.semantic_request)
        != prepared.reservation.semantic_request_sha256
        or type(lm) is not ReceiptSafeDspyLMAuthLM
    ):
        raise SemanticV11Error("receipt/case/live binding drift")
    case = prepared._case
    case.require_canonical()
    try:
        output_text, _ = invoke_with_lm(lm, prepared)
        semantic_result = evaluate_semantic_response(case, output_text)
        projection = prepared.record_terminal(semantic_result)
        records = load_case_custody(prepared.attempt)
        terminal = records.get(f"{case.case_ordinal:02d}-terminal.json")
        if terminal is None:
            raise SemanticV11Error("retained case terminal missing")
        raw_outcome = terminal.get("semantic_outcome")
        if raw_outcome not in {
            "not_evaluated",
            "semantic_error",
            "score_miss",
            "score_pass",
        }:
            raise SemanticV11Error("retained semantic outcome drift")
        semantic_outcome = cast(SemanticOutcome, raw_outcome)
        retained_semantic = terminal.get("semantic_result")
        score = (
            retained_semantic.get("score")
            if isinstance(retained_semantic, Mapping)
            else None
        )
        observed_model = terminal.get("observed_model")
        if projection.producer_terminal != "provider_response_completed":
            score = None
            semantic_outcome = "not_evaluated"
        return EvaluatedCase(
            case_id=case.case_id,
            semantic_outcome=semantic_outcome,
            score=score if isinstance(score, Mapping) else None,
            projection=projection,
            observed_model=(
                observed_model if isinstance(observed_model, str) else None
            ),
            token=_EVALUATED_CASE_TOKEN,
        )
    except BaseException as original:
        try:
            records = load_case_custody(prepared.attempt)
            terminal_name = f"{case.case_ordinal:02d}-terminal.json"
            if terminal_name not in records:
                prepared.record_terminal(semantic_error_result(case))
        except BaseException as custody_error:
            raise original.with_traceback(original.__traceback__) from custody_error
        raise


def corpus_disposition(cases: list[EvaluatedCase]) -> CorpusDisposition:
    """Reduce only opaque case results created by this execution path."""

    if any(type(case) is not EvaluatedCase for case in cases):
        raise SemanticV11Error("caller-authored corpus case rejected")
    dispositions = [case.projection.empirical_disposition for case in cases]
    if not dispositions or any(
        value == "effect_indeterminate" for value in dispositions
    ):
        return "effect_indeterminate"
    if any(value in {"error", "not_evaluated"} for value in dispositions):
        return "error"
    if any(value == "failed" for value in dispositions):
        return "failed"
    observed_models = [case.observed_model for case in cases]
    if (
        tuple(case.case_id for case in cases) != CASE_ORDER
        or any(value != "passed" for value in dispositions)
        or any(not isinstance(model, str) or not model for model in observed_models)
        or len(set(observed_models)) != 1
    ):
        return "error"
    return "passed"

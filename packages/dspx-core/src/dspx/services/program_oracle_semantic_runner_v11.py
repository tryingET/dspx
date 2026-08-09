# summary: "Dormant exact Gate-4 corpus runner for receipt-bound semantic v11."
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from dspx.services.program_oracle_semantic_artifacts_v11 import (
    _record_case_pre_effect_failure,
    _write_pre_effect_setup_terminal,
    consume_attempt,
    load_case_custody,
)
from dspx.services.program_oracle_semantic_contract_v11 import (
    SemanticV11Error,
    canonical,
    sha256,
)
from dspx.services.program_oracle_semantic_gate4_v11 import Gate4AuthorityCapability
from dspx.services.program_oracle_semantic_gate4_contract_v11 import (
    EXPECTED_ENDPOINT_ORIGIN_SHA256,
)

_ENDPOINT_ORIGIN_DOMAIN = b"dspx-oracle-semantic-v11-endpoint-origin-v1\0"


def run_corpus(
    *,
    repo_root: Path,
    state_root: Path,
    owner_source_root: Path,
    authority: Gate4AuthorityCapability,
) -> dict[str, object]:
    """Consume the ledger first, then execute at most one fixed four-case process."""

    if type(authority) is not Gate4AuthorityCapability:
        raise SemanticV11Error("canonical Gate-4 capability required")
    # This durable write is intentionally before owner/backend imports or request work.
    attempt = consume_attempt(state_root, authority)

    try:
        from dspx.services.program_oracle_semantic_result_artifact_v11 import (
            write_evaluation_result,
            write_pre_effect_setup_result,
        )

        from dspy_lm_auth import (  # ty: ignore[unresolved-import]
            OutcomeReceiptEvent,
            ProviderOutcomeReceipt,
        )
        from dspy_lm_auth.lm import (  # ty: ignore[unresolved-import]
            DEFAULT_CODEX_API_BASE,
            LM as OwnerLM,
        )

        from dspx.services.program_oracle_semantic_adapter_v11 import (
            ReceiptSafeDspyLMAuthLM,
        )
        from dspx.services.program_oracle_semantic_contract_v11 import load_bound_cases
        from dspx.services.program_oracle_semantic_evaluation_v11 import (
            execute_case,
            normalized_semantic_request,
        )
        from dspx.services.program_oracle_semantic_identity_v11 import (
            prepare_receipt,
            verify_exact_owner,
        )
        from dspx.services.program_oracle_semantic_result_v11 import (
            semantic_error_result,
        )

        owner = verify_exact_owner(
            owner_source_root,
            OutcomeReceiptEvent,
            ProviderOutcomeReceipt,
            OwnerLM,
        )
        cases = load_bound_cases(repo_root)
        requests = tuple(
            (case, normalized_semantic_request(case.materialized_request()))
            for case in cases
        )
        lm = ReceiptSafeDspyLMAuthLM()
        parsed = urlsplit(DEFAULT_CODEX_API_BASE)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise SemanticV11Error("owner endpoint origin drift")
        endpoint_origin_sha256 = sha256(
            _ENDPOINT_ORIGIN_DOMAIN
            + canonical({"scheme": parsed.scheme, "hostname": parsed.hostname})
        )
        if endpoint_origin_sha256 != EXPECTED_ENDPOINT_ORIGIN_SHA256:
            raise SemanticV11Error("owner endpoint origin identity drift")
    except BaseException as original:
        try:
            _write_pre_effect_setup_terminal(attempt)
            write_pre_effect_setup_result(attempt)
        except BaseException as custody_error:
            raise original.with_traceback(original.__traceback__) from custody_error
        raise

    for case, semantic_request in requests:
        try:
            prepared = prepare_receipt(
                attempt,
                case=case,
                semantic_request=semantic_request,
                endpoint_origin_sha256=endpoint_origin_sha256,
                artifact=owner,
            )
        except BaseException as original:
            try:
                records = load_case_custody(attempt)
                reserved_name = f"{case.case_ordinal:02d}-reserved.json"
                if reserved_name in records:
                    _record_case_pre_effect_failure(attempt, case)
                else:
                    _write_pre_effect_setup_terminal(attempt, case)
                write_evaluation_result(attempt, cases, owner.artifact)
            except BaseException as custody_error:
                raise original.with_traceback(original.__traceback__) from custody_error
            raise
        try:
            evaluated = execute_case(prepared, lm=lm)
        except BaseException as original:
            try:
                records = load_case_custody(attempt)
                terminal_name = f"{case.case_ordinal:02d}-terminal.json"
                if terminal_name not in records:
                    prepared.record_terminal(semantic_error_result(case))
                write_evaluation_result(attempt, cases, owner.artifact)
            except BaseException as custody_error:
                raise original.with_traceback(original.__traceback__) from custody_error
            raise
        if evaluated.projection.empirical_disposition != "passed":
            break
    return write_evaluation_result(attempt, cases, owner.artifact)

from __future__ import annotations

from typing import Any

from dspx.services.program_intent import ProgramIntent


PIPELINE_TOPOLOGY: dict[str, Any] = {
    "kind": "pipeline",
    "execution_status": "declared_not_materialized",
    "modules": [
        {
            "id": "classify_ticket",
            "primitive": "Predict",
            "signature": {
                "name": "ClassifyTicket",
                "inputs": ["ticket_text"],
                "outputs": ["route"],
            },
            "role": "Classify ticket route.",
        },
        {
            "id": "draft_response",
            "primitive": "chain_of_thought",
            "signature": {
                "name": "DraftResponse",
                "inputs": ["ticket_text", "route"],
                "outputs": ["response"],
            },
            "role": "Draft a response for the selected route.",
        },
    ],
    "edges": [
        {"from": "input", "to": "classify_ticket"},
        {"from": "classify_ticket", "to": "draft_response"},
        {"from": "draft_response", "to": "output"},
    ],
}


def _explicit_topology_intent() -> ProgramIntent:
    return ProgramIntent(
        name="SupportRouterProgram",
        objective="Route support tickets and draft a response.",
        inputs=["ticket_text"],
        outputs=["response"],
        metric="exact_match",
        constraints=["preserve the original ticket facts"],
        topology=PIPELINE_TOPOLOGY,
        examples=[
            {
                "inputs": {"ticket_text": "Billing invoice is wrong"},
                "outputs": {"response": "We will help review the billing invoice."},
            }
        ],
    )


def _react_v2_intent(*, opt_in: bool = False) -> ProgramIntent:
    return ProgramIntent(
        name="ReActV2PipelineProgram",
        objective="Use explicitly enabled experimental ReActV2 reasoning to answer.",
        inputs=["question"],
        outputs=["answer"],
        options={"enable_react_v2_materialization": opt_in},
        topology={
            "kind": "pipeline",
            "execution_status": "declared_not_materialized",
            "modules": [
                {
                    "id": "reason_answer",
                    "primitive": "react_v2",
                    "signature": {
                        "name": "ReasonAnswer",
                        "inputs": ["question"],
                        "outputs": ["answer"],
                    },
                    "tools": [],
                    "max_iters": 2,
                }
            ],
            "edges": [
                {"from": "input", "to": "reason_answer"},
                {"from": "reason_answer", "to": "output"},
            ],
        },
    )

"""Generated DSPy direction-controller candidate program.

This file is a bounded DSPx candidate artifact for IW27. It is intentionally
read-only: it proposes transition JSON that must be verified by AK's
`ak direction-controller verify` / `plan` surfaces before any operator action.
It does not apply AK transitions, dispatch owner routes, or promote itself to
production.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:  # pragma: no cover - candidate may be inspected without DSPy installed.
    import dspy
except ImportError:  # pragma: no cover
    dspy = None  # type: ignore[assignment]


if dspy is not None:

    class ExtractLayer12PolicyFacts(dspy.Signature):
        """Extract direction-to-execution policy facts and non-authorizations."""

        operator_intent: str = dspy.InputField()
        direction_controller_status: str = dspy.InputField()
        policy_facts: str = dspy.OutputField()
        non_authorizations: str = dspy.OutputField()

    class DeriveLayer12StateVector(dspy.Signature):
        """Derive a compact state vector from AK direction-controller status."""

        direction_controller_status: str = dspy.InputField()
        state_vector: str = dspy.OutputField()
        missing_facts: str = dspy.OutputField()

    class ProposeLayer12Transition(dspy.Signature):
        """Propose one advisory transition for deterministic AK verification."""

        operator_intent: str = dspy.InputField()
        state_vector: str = dspy.InputField()
        legal_controls: str = dspy.InputField()
        blocked_controls: str = dspy.InputField()
        transition: str = dspy.OutputField()
        rationale: str = dspy.OutputField()

    class CritiqueAuthorityDrift(dspy.Signature):
        """Find false authority claims in a proposed transition."""

        proposed_transition: str = dspy.InputField()
        non_authorizations: str = dspy.InputField()
        authority_drift_risk: str = dspy.OutputField()
        required_repair: str = dspy.OutputField()

    class CritiqueTheaterTraps(dspy.Signature):
        """Find route/lifecycle/owner/evidence theater in a proposal."""

        proposed_transition: str = dspy.InputField()
        direction_controller_status: str = dspy.InputField()
        theater_risk: str = dspy.OutputField()
        required_repair: str = dspy.OutputField()

    class RepairLayer12IR(dspy.Signature):
        """Repair proposal JSON before deterministic AK verification."""

        proposed_transition: str = dspy.InputField()
        authority_drift_risk: str = dspy.InputField()
        theater_risk: str = dspy.InputField()
        repaired_transition: str = dspy.OutputField()
        verifier_expectation: str = dspy.OutputField()


@dataclass(frozen=True)
class DirectionControllerProgramCandidate:
    """Read-only generated-program candidate wrapper.

    The candidate is deliberately conservative: it returns a verifier-compatible
    transition proposal and requires AK verification before any downstream plan.
    """

    program_id: str = "dspx.generated.direction_controller.v1"
    generated_by: str = "dspx_generated_dspy_candidate"

    def propose(
        self,
        *,
        operator_intent: str,
        direction_controller_status: dict[str, Any],
    ) -> dict[str, Any]:
        transition = str(
            direction_controller_status.get(
                "recommended_transition", "inspect_status_before_proceeding"
            )
        )
        return {
            "schema_version": 1,
            "surface": "dspx.generated_direction_controller.proposal",
            "read_only": True,
            "apply_performed": False,
            "program_id": self.program_id,
            "generated_by": self.generated_by,
            "intent": operator_intent,
            "proposal_role": "advisory_input_only",
            "transition": transition,
            "rationale": (
                "Generated DSPy candidate defers legality to AK "
                "direction-controller verifier and follows the status readback's "
                "recommended transition."
            ),
            "expected_verifier_command": (
                "ak direction-controller verify --repo . "
                "--proposal <saved-proposal.json> -F json"
            ),
            "non_authorizations": direction_controller_status.get(
                "non_authorizations", []
            ),
        }

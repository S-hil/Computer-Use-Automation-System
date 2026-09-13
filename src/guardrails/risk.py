"""
Risk Classification Engine.
Distinguishes safe/reversible actions from risky/irreversible ones.
Handles risky operations conservatively under banking dual-control compliance.
"""

from typing import Optional
from src.schema.capability import ActionType, RiskClassification

IRREVERSIBLE_KEYWORDS = [
    "transfer", "wire", "release", "freeze", "delete", "close", "purge", "payout", "debit"
]

MUTATION_KEYWORDS = [
    "submit", "save", "update", "apply", "execute"
]


class RiskEvaluator:
    def __init__(self, require_supervisor_for_irreversible: bool = True):
        self.require_supervisor_for_irreversible = require_supervisor_for_irreversible

    def evaluate_action(
        self,
        action: ActionType,
        target_name: Optional[str] = None,
        context_hint: Optional[str] = None
    ) -> RiskClassification:
        combined = f"{target_name or ''} {context_hint or ''}".lower()

        if action in (ActionType.NAVIGATE, ActionType.WAIT_FOR, ActionType.EXTRACT, ActionType.ASSERT):
            return RiskClassification.SAFE_REVERSIBLE

        # Check for irreversible financial triggers
        if any(kw in combined for kw in IRREVERSIBLE_KEYWORDS):
            return RiskClassification.RISKY_IRREVERSIBLE

        # Form typing / non-final button clicks
        if action == ActionType.FILL:
            return RiskClassification.SAFE_REVERSIBLE

        if any(kw in combined for kw in MUTATION_KEYWORDS):
            return RiskClassification.RISKY_MUTATION

        return RiskClassification.SAFE_REVERSIBLE

    def requires_escalation(self, risk: RiskClassification) -> bool:
        """
        Under banking dual-control rules, irreversible actions require human supervisor authorization.
        """
        if risk == RiskClassification.RISKY_IRREVERSIBLE and self.require_supervisor_for_irreversible:
            return True
        return False

"""
Safety & Policy Guardrails Engine.
Enforces explicit, configurable allowlists:
- Permitted hostnames, ports, and route patterns
- Permitted action types
- Reversible vs irreversible boundary enforcement
"""

import re
import urllib.parse
from typing import List, Optional
from src.schema.capability import ActionType, RiskClassification
from src.guardrails.risk import RiskEvaluator


class PolicyViolation(Exception):
    """Raised when an agent or replay attempts an action violating safety policy."""
    pass


class PolicyEngine:
    def __init__(
        self,
        allowed_domains: Optional[List[str]] = None,
        allowed_actions: Optional[List[ActionType]] = None,
        enforce_risk_gates: bool = True
    ):
        self.allowed_domains = allowed_domains or [
            r"^127\.0\.0\.1(:\d+)?$",
            r"^localhost(:\d+)?$",
            r"^.*\.internal\.creditunion\.local$"
        ]
        self.domain_patterns = [re.compile(p) for p in self.allowed_domains]
        self.allowed_actions = allowed_actions or list(ActionType)
        self.risk_evaluator = RiskEvaluator(require_supervisor_for_irreversible=enforce_risk_gates)

    def validate_url(self, url: str):
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise PolicyViolation(f"Disallowed URL scheme: '{parsed.scheme}'. Only http/https permitted.")

        host_netloc = parsed.netloc.lower()
        allowed = any(pattern.match(host_netloc) for pattern in self.domain_patterns)
        if not allowed:
            raise PolicyViolation(
                f"Navigation blocked by safety guardrails: Host '{host_netloc}' is not on the institutional allowlist."
            )

    def validate_action(
        self,
        action: ActionType,
        target_name: Optional[str] = None,
        context_hint: Optional[str] = None
    ) -> RiskClassification:
        if action not in self.allowed_actions:
            raise PolicyViolation(f"Action '{action}' is prohibited by safety policy.")

        risk = self.risk_evaluator.evaluate_action(action, target_name, context_hint)
        return risk

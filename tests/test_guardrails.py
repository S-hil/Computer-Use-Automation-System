"""
Tests for Policy Guardrails, Risk Evaluation, and PII Redaction.
"""

import pytest
from src.guardrails.policy import PolicyEngine, PolicyViolation
from src.guardrails.risk import RiskEvaluator
from src.guardrails.redaction import redact_text, sanitize_data
from src.schema.capability import ActionType, RiskClassification


def test_domain_allowlist_enforcement():
    engine = PolicyEngine(allowed_domains=[r"^localhost(:\d+)?$", r"^127\.0\.0\.1(:\d+)?$"])

    # Allowed URLs
    engine.validate_url("http://localhost:8088/apexcore")
    engine.validate_url("http://127.0.0.1:8088/apexcore/member/detail?id=MEM-7701")

    # Blocked external URLs
    with pytest.raises(PolicyViolation) as exc:
        engine.validate_url("https://malicious-external-site.com/steal-data")
    assert "not on the institutional allowlist" in str(exc.value)


def test_risk_classification():
    evaluator = RiskEvaluator(require_supervisor_for_irreversible=True)

    # Safe read
    risk_read = evaluator.evaluate_action(ActionType.NAVIGATE, "Search Page")
    assert risk_read == RiskClassification.SAFE_REVERSIBLE
    assert not evaluator.requires_escalation(risk_read)

    # Safe fill
    risk_fill = evaluator.evaluate_action(ActionType.FILL, "Member ID", "Entering lookup query")
    assert risk_fill == RiskClassification.SAFE_REVERSIBLE

    # Risky irreversible (fund transfer / wire release)
    risk_wire = evaluator.evaluate_action(ActionType.CLICK, "Execute High-Risk Operation", "Wire Transfer Release")
    assert risk_wire == RiskClassification.RISKY_IRREVERSIBLE
    assert evaluator.requires_escalation(risk_wire)


def test_pii_redaction():
    text_with_pii = "Member Alice Smith with SSN 123-45-6789 deposited funds into account SAV-4091-88 using card 4111-2222-3333-4444."
    redacted = redact_text(text_with_pii)

    # SSN masked
    assert "123-45-6789" not in redacted
    assert "***-**-6789" in redacted

    # Account masked
    assert "SAV-4091-88" not in redacted
    assert "SAV-****-88" in redacted

    # Card masked
    assert "4111-2222-3333-4444" not in redacted
    assert "****-****-****-4444" in redacted


def test_sanitize_dict_with_secrets():
    data = {
        "user": "Alice",
        "ssn": "123-45-6789",
        "pin": "902104",
        "account_token": "secret_token_abc123"
    }
    sanitized = sanitize_data(data)
    assert sanitized["pin"] == "[REDACTED_SECRET]"
    assert sanitized["account_token"] == "[REDACTED_SECRET]"
    assert sanitized["ssn"] == "***-**-6789"
    assert sanitized["user"] == "Alice"

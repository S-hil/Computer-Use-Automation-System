"""
Regulated Financial Data Redaction Engine.
Ensures zero leaks of credentials, full PII, or raw account data in logs or capability artifacts:
- Masks Social Security Numbers (SSN) -> ***-**-1234
- Masks Account Numbers -> ***-****-12
- Masks Credit Card Numbers -> ****-****-****-1234
- Redacts Passwords, PINs, and Authorization Tokens
"""

import re
from typing import Any, Dict, List, Union

SSN_PATTERN = re.compile(r"\b(\d{3})-(\d{2})-(\d{4})\b")
CARD_PATTERN = re.compile(r"\b(?:\d[ -]?){13,16}\b")
ACCOUNT_PATTERN = re.compile(r"\b([A-Z]{2,4})-(\d{4})-(\d{2})\b")
SECRET_KEYWORD_PATTERN = re.compile(r"(pin|password|token|secret|cvv|auth)", re.IGNORECASE)


def mask_ssn(match: re.Match) -> str:
    return f"***-**-{match.group(3)}"


def mask_account(match: re.Match) -> str:
    return f"{match.group(1)}-****-{match.group(3)}"


def mask_card(match: re.Match) -> str:
    raw = match.group(0).replace(" ", "").replace("-", "")
    if len(raw) >= 12:
        return f"****-****-****-{raw[-4:]}"
    return "[MASKED_CARD]"


def redact_text(text: str) -> str:
    if not isinstance(text, str):
        return text
    text = SSN_PATTERN.sub(mask_ssn, text)
    text = ACCOUNT_PATTERN.sub(mask_account, text)
    # Mask cards if valid length
    for m in list(CARD_PATTERN.finditer(text)):
        val = m.group(0).replace(" ", "").replace("-", "")
        if 13 <= len(val) <= 19 and not val.startswith("00000"):
            text = text.replace(m.group(0), mask_card(m))
    return text


def sanitize_data(data: Any) -> Any:
    """
    Recursively sanitize dictionaries, lists, and primitives.
    Keys matching sensitive secrets have their values redacted.
    PII text values are masked according to regulatory standards.
    """
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            if SECRET_KEYWORD_PATTERN.search(str(k)):
                sanitized[k] = "[REDACTED_SECRET]"
            else:
                sanitized[k] = sanitize_data(v)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_data(item) for item in data]
    elif isinstance(data, str):
        return redact_text(data)
    else:
        return data

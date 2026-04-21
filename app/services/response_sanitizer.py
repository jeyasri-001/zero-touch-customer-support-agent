"""
Response Sanitizer - Ensures customer-facing messages are in plain language.
Strips internal error codes, technical IDs, and jargon before delivery.
"""

import re
from typing import Optional


# Patterns that must never appear in a customer-facing message
_INTERNAL_PATTERNS = [
    # Bank codes
    (r'\bcode\s+51\b', "a temporary funds issue"),
    (r'\bcode\s+54\b', "a mandate issue"),
    (r'\bcode\s+91\b', "a temporary bank issue"),
    (r'\b(bank\s+)?rejection\s+code\s+\d+\b', "a payment issue"),
    # Transaction / mandate IDs
    (r'\bTXN[A-Z0-9]{8,}\b', "[transaction reference]"),
    (r'\bMAN[A-Z0-9]{6,}\b', "[mandate reference]"),
    (r'\bLOG[A-Z0-9]{6,}\b', "[log reference]"),
    # PAN numbers
    (r'\b[A-Z]{5}\d{4}[A-Z]\b', "[customer ID]"),
    # Internal action names
    (r'\bRETRY_EXECUTED\b', "retried"),
    (r'\bRETRIGGER_EXECUTED\b', "re-initiated"),
    (r'\bESCALATE_TO_HUMAN\b', "being reviewed by our team"),
    (r'\bWAIT_FOR_AMC\b', "pending with the fund house"),
    (r'\bNOTIFY_CUSTOMER\b', "noted"),
    # Root cause labels
    (r'\bBANK_REJECTION\b', "a bank-side issue"),
    (r'\bMANDATE_EXPIRY\b', "an expired mandate"),
    (r'\bSIP_PAUSED\b', "a paused SIP plan"),
    (r'\bACCOUNT_VALIDATION_ERROR\b', "an account verification issue"),
    (r'\bAMC_DELAY\b', "a processing delay at the fund house"),
    (r'\bSYSTEM_ERROR\b', "a technical issue"),
    # Internal status names
    (r'\bPENDING_FOLLOW_UP\b', "under review"),
    # editSystematicPlanSip and similar API names
    (r'\beditSystematicPlanSip\b', "plan modification"),
    (r'\bpauseMonth:\d+\b', "pause instruction"),
    # BSE StAR MF
    (r'\bBSE StAR MF\b', "the exchange platform"),
]

_MIN_RESPONSE_LENGTH = 30  # Responses shorter than this are probably malformed


def sanitize_customer_response(response: str) -> str:
    """
    Strip internal codes and labels from a customer-facing message.
    Returns a clean, plain-language string.
    """
    if not response or not response.strip():
        return (
            "We have reviewed your request and our team is working on a resolution. "
            "We will update you shortly."
        )

    cleaned = response
    for pattern, replacement in _INTERNAL_PATTERNS:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

    # Collapse multiple spaces/newlines left by substitutions
    cleaned = re.sub(r' {2,}', ' ', cleaned).strip()

    if len(cleaned) < _MIN_RESPONSE_LENGTH:
        return (
            "We have reviewed your account and are working to resolve the issue. "
            "Our support team will follow up with you shortly."
        )

    return cleaned


def validate_response_quality(response: str) -> tuple[bool, Optional[str]]:
    """
    Check if a customer response meets quality criteria.
    Returns (is_acceptable, reason_if_not).
    """
    if not response or len(response.strip()) < _MIN_RESPONSE_LENGTH:
        return False, "Response too short or empty"

    for pattern, _ in _INTERNAL_PATTERNS:
        if re.search(pattern, response, flags=re.IGNORECASE):
            matched = re.search(pattern, response, flags=re.IGNORECASE).group(0)
            return False, f"Contains internal term: '{matched}'"

    return True, None

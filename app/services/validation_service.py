"""
Validation Service - Prevents false positives before auto-resolution
Based on McKinsey's validation-before-action approach
"""

from typing import Dict, Any, Tuple, List


class ValidationService:
    """
    Decision-tree validation layer that runs AFTER LLM diagnosis
    but BEFORE any auto-resolution actions are executed.
    """
    
    # Retry-eligible bank codes (per hackathon plan)
    RETRYABLE_CODES = ["51", "91"]
    NON_RETRYABLE_CODES = ["54"]  # Expired mandate - customer must renew
    
    # Minimum evidence sources for confident diagnosis
    MIN_EVIDENCE_SOURCES = 2
    
    # Confidence threshold for auto-actions
    MIN_CONFIDENCE_AUTO_RESOLVE = 0.75
    MIN_CONFIDENCE_ESCALATE = 0.50
    
    @classmethod
    def validate_diagnosis(cls, diagnosis: Dict[str, Any], tool_calls: List[Dict]) -> Tuple[bool, str, Dict]:
        """
        Validate LLM diagnosis before taking action.
        
        Returns:
            (is_valid, reason, suggested_action)
        """
        root_cause = diagnosis.get("root_cause", "UNKNOWN")
        confidence = float(diagnosis.get("confidence", 0))
        evidence = diagnosis.get("evidence", [])
        action = diagnosis.get("action_taken", "")
        
        validation = {
            "checks_passed": [],
            "checks_failed": [],
            "recommendation": None,
            "original_action": action
        }
        
        # Check 1: Minimum evidence sources (McKinsey best practice)
        if len(evidence) >= cls.MIN_EVIDENCE_SOURCES:
            validation["checks_passed"].append(f"Evidence sources: {len(evidence)} >= {cls.MIN_EVIDENCE_SOURCES}")
        else:
            validation["checks_failed"].append(f"Insufficient evidence: {len(evidence)} < {cls.MIN_EVIDENCE_SOURCES}")
            validation["recommendation"] = "ESCALATE_TO_HUMAN"
            return False, "Insufficient evidence sources", validation
        
        # Check 2: Confidence threshold
        if confidence < cls.MIN_CONFIDENCE_ESCALATE:
            validation["checks_failed"].append(f"Confidence too low: {confidence:.2f} < {cls.MIN_CONFIDENCE_ESCALATE}")
            validation["recommendation"] = "ESCALATE_TO_HUMAN"
            return False, f"Confidence {confidence:.0%} below escalation threshold", validation
        
        validation["checks_passed"].append(f"Confidence: {confidence:.0%}")
        
        # Check 3: Verify tools were actually called (prevent hallucination)
        expected_tools = {"get_customer_transactions", "query_event_logs"}
        called_tool_names = {tc.get("tool") for tc in tool_calls}
        
        if not (expected_tools & called_tool_names):
            validation["checks_failed"].append("Agent didn't query critical tools")
            validation["recommendation"] = "ESCALATE_TO_HUMAN"
            return False, "Missing critical tool calls (transactions or logs)", validation
        
        validation["checks_passed"].append(f"Critical tools called: {called_tool_names & expected_tools}")
        
        # Check 4a: Retry action must be on retryable bank code
        if "RETRY_EXECUTED" in action.upper():
            bank_code = cls._extract_bank_code(tool_calls)

            if bank_code in cls.NON_RETRYABLE_CODES:
                validation["checks_failed"].append(f"Retry blocked: code {bank_code} is not retryable")
                validation["recommendation"] = "ESCALATE_TO_HUMAN"
                return False, f"Cannot retry code {bank_code} (not retryable)", validation

            if bank_code and bank_code not in cls.RETRYABLE_CODES:
                validation["checks_failed"].append(f"Retry blocked: unknown bank code {bank_code}")
                validation["recommendation"] = "ESCALATE_TO_HUMAN"
                return False, f"Unknown bank code {bank_code} - escalating for safety", validation

            validation["checks_passed"].append(f"Retry allowed for bank code {bank_code}")

        # Check 4b: Retrigger action requires check_sip_pause_status was called and confirmed eligible
        if "RETRIGGER_EXECUTED" in action.upper():
            called_tool_names = {tc.get("tool") for tc in tool_calls}
            if "check_sip_pause_status" not in called_tool_names:
                validation["checks_failed"].append("Retrigger requires check_sip_pause_status to be called first")
                validation["recommendation"] = "ESCALATE_TO_HUMAN"
                return False, "Retrigger blocked: pause status was not verified", validation

            retrigger_eligible = cls._extract_retrigger_eligible(tool_calls)
            if retrigger_eligible is False:
                validation["checks_failed"].append("Retrigger blocked: SIP is not retrigger_eligible")
                validation["recommendation"] = "ESCALATE_TO_HUMAN"
                return False, "SIP is not eligible for retrigger", validation

            validation["checks_passed"].append("Retrigger eligible confirmed")

        # Check 5: Auto-resolve (retry or retrigger) requires high confidence
        if any(k in action.upper() for k in ("RETRY_EXECUTED", "RETRIGGER_EXECUTED")):
            if confidence < cls.MIN_CONFIDENCE_AUTO_RESOLVE:
                validation["checks_failed"].append(f"Auto-resolve needs {cls.MIN_CONFIDENCE_AUTO_RESOLVE:.0%}+ confidence")
                validation["recommendation"] = "ESCALATE_TO_HUMAN"
                return False, f"Confidence {confidence:.0%} too low for auto-resolve", validation
        
        # All checks passed
        validation["checks_passed"].append("All validation checks passed")
        validation["recommendation"] = "PROCEED"
        return True, "Validated", validation
    
    @staticmethod
    def _extract_retrigger_eligible(tool_calls: List[Dict]):
        """Return True/False from check_sip_pause_status result, or None if not found."""
        import json
        for tc in tool_calls:
            if tc.get("tool") == "check_sip_pause_status":
                try:
                    result = json.loads(tc.get("result_preview", "{}"))
                    return result.get("retrigger_eligible")
                except Exception:
                    pass
        return None

    @staticmethod
    def _extract_bank_code(tool_calls: List[Dict]) -> str:
        """Extract bank code from tool call results.

        Prefers the explicit 'bank_code' field stored by the agent at call time.
        Falls back to regex on result_preview only if the explicit field is absent.
        """
        import re
        for tc in tool_calls:
            if tc.get("tool") == "get_bank_rejection_code":
                # Explicit field stored by agent loop — never truncated
                if tc.get("bank_code") is not None:
                    return str(tc["bank_code"])
                # Fallback: regex on preview (may be truncated at 200 chars)
                result = tc.get("result_preview", "")
                match = re.search(r'"code"\s*:\s*"(\d+)"', result)
                if match:
                    return match.group(1)
        return None

"""
Mock Database for Zero-Touch Agent
Based on real Jira ticket patterns from NOC-21854, NOC-1346, NOC-11734
"""

import json
import random
from datetime import datetime, timedelta
from pathlib import Path


# Deterministic mapping: PAN → issue_type the agent should diagnose.
# Covers all 50 evaluation tickets (NOC-5001 – NOC-5047 + 3 real Jira tickets).
CUSTOMER_PROFILES = {
    # BANK_REJECTION — code 51 (insufficient funds)
    "BKJPS1234A": "SIP_FAILURE",
    "CKTRS5678B": "SIP_FAILURE",
    "DFGTR9012C": "SIP_FAILURE",
    "EHJKL3456D": "SIP_FAILURE",
    "FIJKM7890E": "SIP_FAILURE",
    # BANK_REJECTION — code 91 (bank temp unavailable)
    "PLRTX8823B": "PAYMENT_FAILURE",
    "QRSMN1209D": "PAYMENT_FAILURE",
    "WKRTP5567G": "PAYMENT_FAILURE",
    "BMNQZ4401T": "PAYMENT_FAILURE",
    "ZXCVB7891L": "PAYMENT_FAILURE",
    # MANDATE_EXPIRY — code 54
    "GKLMN2345F": "MANDATE_EXPIRY",
    "HLMNO6789G": "MANDATE_EXPIRY",
    "IMNOP0123H": "MANDATE_EXPIRY",
    "HNMRQ3312S": "MANDATE_EXPIRY",
    "FQLKM8890V": "MANDATE_EXPIRY",
    "KPRTZ2201X": "MANDATE_EXPIRY",
    "DVNWQ6678Y": "MANDATE_EXPIRY",
    # SIP_PAUSED
    "JNOPQ4567I": "SIP_PAUSED",
    "KOPQR8901J": "SIP_PAUSED",
    "LPQRS2345K": "SIP_PAUSED",
    "LMNOP3456Q": "SIP_PAUSED",
    "RSTVW7890E": "SIP_PAUSED",
    "GHIJK2345M": "SIP_PAUSED",
    "UVWXY6789N": "SIP_PAUSED",
    # ACCOUNT_VALIDATION_ERROR
    "MQRST6789L": "ACCOUNT_VALIDATION_ERROR",
    "NRSTU0123M": "ACCOUNT_VALIDATION_ERROR",
    "OSTUV4567N": "ACCOUNT_VALIDATION_ERROR",
    "BCDEF4567H": "ACCOUNT_VALIDATION_ERROR",
    "IJKLM8901P": "ACCOUNT_VALIDATION_ERROR",
    "NOPQR2345C": "ACCOUNT_VALIDATION_ERROR",
    # AMC_DELAY
    "PTUVW8901O": "AMC_DELAY",
    "QUVWX2345P": "AMC_DELAY",
    "RVWXY6789Q": "AMC_DELAY",
    "STUVW6789J": "AMC_DELAY",
    "XYZAB1234K": "AMC_DELAY",
    "CDEFG5678L": "AMC_DELAY",
    # SYSTEM_ERROR
    "SWXYZ0123R": "SYSTEM_ERROR",
    "TXYZA4567S": "SYSTEM_ERROR",
    "UYZAB8901T": "SYSTEM_ERROR",
    "HIJKL9012M": "SYSTEM_ERROR",
    "MNOPQ3456N": "SYSTEM_ERROR",
    # KYC_SYNC_DELAY — no financial transaction; agent should detect portal sync issue
    "ABYPS2412H": "KYC_SYNC_DELAY",
    "CRPLM7823K": "KYC_SYNC_DELAY",
    "HRTNK4567F": "KYC_SYNC_DELAY",
    "MJLPQ9034R": "KYC_SYNC_DELAY",
    "TNVSR6621W": "KYC_SYNC_DELAY",
    # UNKNOWN — real Jira tickets with sparse descriptions
    "AHYPR8658L": "SIP_PAUSED",   # real: NOC-21854 (SIP not processed)
    "ATUPN0386P": "SIP_FAILURE",  # real: NOC-1346 (payment failure)
    "AKCPS3067R": "MANDATE_EXPIRY",  # real: NOC-11734 (mandate issue)
    "VZABC2345U": "SIP_FAILURE",  # NOC-5021 (sparse — any failure)
}


class MockDatabase:
    """Mock database with realistic fintech data"""

    def __init__(self):
        self.transactions = []
        self.mandates = []
        self.event_logs = []
        self._seed_data()

    def _seed_data(self):
        """Seed one deterministic transaction + mandate + logs per customer PAN."""
        for i, (pan, issue_type) in enumerate(CUSTOMER_PROFILES.items()):
            txn = self._generate_transaction(customer_id=pan, index=i, issue_type=issue_type)
            self.transactions.append(txn)

            mandate = self._generate_mandate(customer_id=pan, transaction=txn)
            if mandate:
                self.mandates.append(mandate)

            self.event_logs.extend(self._generate_event_logs(txn))
    
    def _generate_transaction(self, customer_id, index, issue_type=None):
        """Generate a realistic transaction with a deterministic issue_type."""
        if issue_type is None:
            issue_type = "SIP_FAILURE"

        if issue_type == "KYC_SYNC_DELAY":
            # No financial transaction for KYC issues — create a minimal placeholder
            # so get_customer_transactions returns something, but logs will reveal the real cause.
            txn_id = f"TXN{datetime.now().strftime('%Y%m%d')}{index:06d}"
            txn_date = datetime.now() - timedelta(days=random.randint(1, 10))
            return {
                "transaction_id": txn_id,
                "customer_id": customer_id,
                "mandate_id": None,
                "amount": 0.0,
                "status": "NOT_APPLICABLE",
                "bank_code": None,
                "rejection_reason": "KYC_PORTAL_SYNC_PENDING",
                "retry_eligible": False,
                "created_at": txn_date.isoformat(),
                "updated_at": txn_date.isoformat(),
                "sip_date": txn_date.strftime("%Y-%m-%d"),
                "issue_type": "KYC_SYNC_DELAY",
                "notes": "KYC activated at registrar but portal status not yet synced",
            }

        if issue_type == "SYSTEM_ERROR":
            txn_id = f"TXN{datetime.now().strftime('%Y%m%d')}{index:06d}"
            txn_date = datetime.now() - timedelta(days=random.randint(1, 10))
            return {
                "transaction_id": txn_id,
                "customer_id": customer_id,
                "mandate_id": f"MAN{customer_id[-4:]}{index:03d}",
                "amount": random.choice([1000, 2000, 5000]),
                "status": "FAILED",
                "bank_code": "99",
                "rejection_reason": "INTERNAL_SYSTEM_ERROR",
                "retry_eligible": False,
                "created_at": txn_date.isoformat(),
                "updated_at": txn_date.isoformat(),
                "sip_date": txn_date.strftime("%Y-%m-%d"),
                "issue_type": "SYSTEM_ERROR",
            }

        if issue_type == "SIP_FAILURE":
            bank_code = "51"
            rejection_reason = "INSUFFICIENT_FUNDS"
            status = "FAILED"
            retry_eligible = True
        elif issue_type == "MANDATE_EXPIRY":
            bank_code = "54"
            rejection_reason = "MANDATE_EXPIRED"
            status = "FAILED"
            retry_eligible = False
        elif issue_type == "PAYMENT_FAILURE":
            bank_code = "91"
            rejection_reason = "BANK_TEMP_UNAVAILABLE"
            status = "FAILED"
            retry_eligible = True
        elif issue_type == "SIP_PAUSED":
            bank_code = None
            rejection_reason = "SIP_PAUSED_BY_SYSTEM"
            status = "NOT_SUBMITTED"
            retry_eligible = False
        elif issue_type == "ACCOUNT_VALIDATION_ERROR":
            bank_code = None
            rejection_reason = "ACCOUNT_VALIDATION_FAILED"
            status = "FAILED"
            retry_eligible = False
        elif issue_type == "AMC_DELAY":
            bank_code = None
            rejection_reason = "AMC_PROCESSING_DELAYED"
            status = "PENDING"
            retry_eligible = False
        else:  # SUCCESS
            bank_code = None
            rejection_reason = None
            status = "SUCCESS"
            retry_eligible = False

        txn_id = f"TXN{datetime.now().strftime('%Y%m%d')}{index:06d}"
        mandate_id = f"MAN{customer_id[-4:]}{index:03d}"
        amount = random.choice([500, 1000, 2000, 5000, 10000, 25000])
        txn_date = datetime.now() - timedelta(days=random.randint(1, 30))

        return {
            "transaction_id": txn_id,
            "customer_id": customer_id,
            "mandate_id": mandate_id,
            "amount": float(amount),
            "status": status,
            "bank_code": bank_code,
            "rejection_reason": rejection_reason,
            "retry_eligible": retry_eligible,
            "created_at": txn_date.isoformat(),
            "updated_at": txn_date.isoformat(),
            "sip_date": txn_date.strftime("%Y-%m-%d"),
            "issue_type": issue_type
        }
    
    def _generate_mandate(self, customer_id, transaction):
        """Generate a mandate record"""
        
        if not transaction.get("mandate_id"):
            return None
        
        # Determine mandate status based on transaction
        if transaction.get("rejection_reason") == "MANDATE_EXPIRED":
            status = "EXPIRED"
            expiry_date = (datetime.now() - timedelta(days=random.randint(1, 90))).strftime("%Y-%m-%d")
        else:
            status = random.choice(["ACTIVE", "ACTIVE", "ACTIVE", "PENDING"])  # 75% active
            expiry_date = (datetime.now() + timedelta(days=random.randint(365, 1095))).strftime("%Y-%m-%d")
        
        return {
            "mandate_id": transaction["mandate_id"],
            "customer_id": customer_id,
            "status": status,
            "expiry_date": expiry_date,
            "created_at": (datetime.now() - timedelta(days=random.randint(365, 1095))).isoformat(),
            "bank_name": random.choice(["HDFC Bank", "ICICI Bank", "SBI", "Axis Bank", "Kotak"]),
            "account_number": f"XXXX{random.randint(1000, 9999)}"
        }
    
    def _generate_event_logs(self, transaction):
        """Generate event logs for a transaction"""
        
        logs = []
        txn_id = transaction["transaction_id"]
        created_at = datetime.fromisoformat(transaction["created_at"])
        
        # Log 1: Transaction initiated
        logs.append({
            "log_id": f"LOG{txn_id}01",
            "transaction_id": txn_id,
            "log_type": "transaction_initiated",
            "timestamp": (created_at - timedelta(seconds=30)).isoformat(),
            "message": f"SIP transaction initiated for customer {transaction['customer_id']}",
            "level": "INFO"
        })
        
        # Log 2: Mandate validation
        if transaction.get("mandate_id"):
            if transaction.get("rejection_reason") == "MANDATE_EXPIRED":
                logs.append({
                    "log_id": f"LOG{txn_id}02",
                    "transaction_id": txn_id,
                    "log_type": "mandate_validation",
                    "timestamp": (created_at - timedelta(seconds=20)).isoformat(),
                    "message": f"Mandate {transaction['mandate_id']} validation FAILED - EXPIRED",
                    "level": "ERROR"
                })
            else:
                logs.append({
                    "log_id": f"LOG{txn_id}02",
                    "transaction_id": txn_id,
                    "log_type": "mandate_validation",
                    "timestamp": (created_at - timedelta(seconds=20)).isoformat(),
                    "message": f"Mandate {transaction['mandate_id']} validated successfully",
                    "level": "INFO"
                })
        
        # Log 3: Payment gateway request
        logs.append({
            "log_id": f"LOG{txn_id}03",
            "transaction_id": txn_id,
            "log_type": "payment_gateway_request",
            "timestamp": (created_at - timedelta(seconds=10)).isoformat(),
            "message": f"Sending debit request to bank for amount {transaction['amount']}",
            "level": "INFO"
        })
        
        # Log 4: Bank response (varies by issue type)
        issue_type = transaction.get("issue_type", "")
        if issue_type == "KYC_SYNC_DELAY":
            logs.append({
                "log_id": f"LOG{txn_id}04",
                "transaction_id": txn_id,
                "log_type": "kyc_portal_sync_pending",
                "timestamp": created_at.isoformat(),
                "message": (
                    "KYC status ACTIVE at CAMS/CDSL registrar but portal DB shows KYC_PENDING. "
                    "Sync job missed this PAN. Manual portal activation required."
                ),
                "level": "WARN"
            })
        elif issue_type == "SYSTEM_ERROR":
            logs.append({
                "log_id": f"LOG{txn_id}04",
                "transaction_id": txn_id,
                "log_type": "internal_system_error",
                "timestamp": created_at.isoformat(),
                "message": "Internal system error during transaction processing — code 99. Ops team notified.",
                "level": "ERROR"
            })
        elif issue_type == "SIP_PAUSED":
            logs.append({
                "log_id": f"LOG{txn_id}04",
                "transaction_id": txn_id,
                "log_type": "sip_submission_skipped",
                "timestamp": created_at.isoformat(),
                "message": "SIP not submitted to exchange — plan paused via editSystematicPlanSip (pauseMonth:1)",
                "level": "WARN"
            })
        elif issue_type == "ACCOUNT_VALIDATION_ERROR":
            logs.append({
                "log_id": f"LOG{txn_id}04",
                "transaction_id": txn_id,
                "log_type": "mandate_registration_failed",
                "timestamp": created_at.isoformat(),
                "message": "Account validation failed — bank account number length mismatch (expected 15-16 digits, got 10)",
                "level": "ERROR"
            })
        elif issue_type == "AMC_DELAY":
            logs.append({
                "log_id": f"LOG{txn_id}04",
                "transaction_id": txn_id,
                "log_type": "amc_processing_queued",
                "timestamp": created_at.isoformat(),
                "message": "Payment accepted by bank. NAV allocation pending at AMC — processing delayed beyond SLA",
                "level": "WARN"
            })
        elif transaction["status"] == "FAILED":
            logs.append({
                "log_id": f"LOG{txn_id}04",
                "transaction_id": txn_id,
                "log_type": "payment_gateway_response",
                "timestamp": created_at.isoformat(),
                "message": f"Bank rejection - Code {transaction['bank_code']}: {transaction['rejection_reason']}",
                "level": "ERROR"
            })
        else:
            logs.append({
                "log_id": f"LOG{txn_id}04",
                "transaction_id": txn_id,
                "log_type": "payment_gateway_response",
                "timestamp": created_at.isoformat(),
                "message": "Bank approval received - Transaction successful",
                "level": "INFO"
            })
        
        # Log 5: Settlement
        logs.append({
            "log_id": f"LOG{txn_id}05",
            "transaction_id": txn_id,
            "log_type": "transaction_settlement",
            "timestamp": (created_at + timedelta(seconds=5)).isoformat(),
            "message": f"Transaction settled with status: {transaction['status']}",
            "level": "INFO" if transaction["status"] == "SUCCESS" else "WARN"
        })
        
        return logs
    
    def get_transaction(self, transaction_id):
        """Get transaction by ID"""
        for txn in self.transactions:
            if txn["transaction_id"] == transaction_id:
                return txn
        return None
    
    def get_transactions_by_customer(self, customer_id, limit=10):
        """Get transactions for a customer"""
        return [t for t in self.transactions if t["customer_id"] == customer_id][:limit]
    
    def get_mandate(self, mandate_id):
        """Get mandate by ID"""
        for m in self.mandates:
            if m["mandate_id"] == mandate_id:
                return m
        return None
    
    def get_mandate_by_customer(self, customer_id):
        """Get mandate for a customer"""
        for m in self.mandates:
            if m["customer_id"] == customer_id:
                return m
        return None
    
    def get_event_logs(self, transaction_id):
        """Get event logs for a transaction"""
        return [l for l in self.event_logs if l["transaction_id"] == transaction_id]
    
    def get_bank_rejection_code(self, transaction_id):
        """Get bank rejection code for a transaction"""
        txn = self.get_transaction(transaction_id)
        if txn and txn["status"] == "FAILED":
            return {
                "code": txn["bank_code"],
                "reason": txn["rejection_reason"],
                "retry_eligible": txn["retry_eligible"]
            }
        return None
    
    def get_sip_schedule(self, customer_id):
        """Get SIP schedule details for a customer"""
        txns = self.get_transactions_by_customer(customer_id, limit=20)
        if not txns:
            return None
        
        # Group transactions to derive SIP schedule
        mandate = self.get_mandate_by_customer(customer_id)
        return {
            "customer_id": customer_id,
            "mandate_id": mandate["mandate_id"] if mandate else None,
            "sip_frequency": "MONTHLY",
            "next_sip_date": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
            "sip_amount": txns[0]["amount"] if txns else 0,
            "total_installments": len(txns),
            "successful_installments": len([t for t in txns if t["status"] == "SUCCESS"]),
            "failed_installments": len([t for t in txns if t["status"] == "FAILED"]),
            "fund_name": random.choice(["Axis ELSS Tax Saver", "HDFC Flexi Cap", "SBI Bluechip", "ICICI Bluechip"])
        }
    
    def get_customer_contact_history(self, customer_id):
        """Get past support tickets for a customer (simulated)"""
        # Simulate past tickets based on customer's transaction history
        txns = self.get_transactions_by_customer(customer_id, limit=5)
        failed = [t for t in txns if t["status"] == "FAILED"]
        
        past_tickets = []
        for i, t in enumerate(failed[:3]):
            past_tickets.append({
                "ticket_id": f"NOC-{random.randint(1000, 9999)}",
                "date": t["created_at"][:10],
                "issue": f"{t['rejection_reason']} for transaction {t['transaction_id']}",
                "resolution": "Retry successful" if t.get("retry_eligible") else "Customer renewed mandate",
                "status": "Done"
            })
        
        return {
            "customer_id": customer_id,
            "total_past_tickets": len(past_tickets),
            "recent_tickets": past_tickets,
            "is_repeat_customer": len(past_tickets) > 1
        }
    
    def get_sip_pause_status(self, customer_id):
        """Return SIP pause details for a customer, if any SIPs are paused."""
        txns = self.get_transactions_by_customer(customer_id, limit=20)
        paused = [t for t in txns if t.get("issue_type") == "SIP_PAUSED"]
        if not paused:
            return {"customer_id": customer_id, "sip_paused": False}

        t = paused[0]
        pause_date = (datetime.fromisoformat(t["created_at"]) - timedelta(days=2)).strftime("%Y-%m-%d")
        resume_date = (datetime.now() + timedelta(days=random.randint(15, 45))).strftime("%Y-%m-%d")
        return {
            "customer_id": customer_id,
            "sip_paused": True,
            "paused_transaction_id": t["transaction_id"],
            "pause_reason": "Investor requested pause via support / ops team action",
            "paused_by": "ops-team@fundsindia.com",
            "pause_date": pause_date,
            "expected_resume_date": resume_date,
            "api_action": "editSystematicPlanSip with pauseMonth:1",
            "retrigger_eligible": True,
        }

    def get_account_validation_history(self, customer_id):
        """Return account number validation errors for a customer."""
        txns = self.get_transactions_by_customer(customer_id, limit=20)
        errors = [t for t in txns if t.get("issue_type") == "ACCOUNT_VALIDATION_ERROR"]
        if not errors:
            return {"customer_id": customer_id, "validation_errors": []}

        bank_names = ["Axis Bank Ltd", "HDFC Bank", "ICICI Bank", "Kotak Mahindra Bank"]
        bank = random.choice(bank_names)
        expected_len = 15 if "Axis" in bank else 16
        actual_len = random.choice([10, 11, 12])
        return {
            "customer_id": customer_id,
            "validation_errors": [
                {
                    "transaction_id": errors[0]["transaction_id"],
                    "bank_name": bank,
                    "error_type": "ACCOUNT_NUMBER_LENGTH_MISMATCH",
                    "expected_length": expected_len,
                    "actual_length": actual_len,
                    "error_message": (
                        f"Bank account number for {bank} must be {expected_len} digits. "
                        f"Received {actual_len} digits. Leading zeros may have been stripped."
                    ),
                    "recommended_fix": "Pad account number with leading zeros to reach required length",
                }
            ],
            "total_errors": len(errors),
        }

    def get_amc_processing_status(self, transaction_id):
        """Return AMC processing status for a transaction."""
        txn = self.get_transaction(transaction_id)
        if not txn:
            return {"error": f"Transaction {transaction_id} not found"}
        if txn.get("issue_type") != "AMC_DELAY":
            return {
                "transaction_id": transaction_id,
                "amc_status": "NOT_APPLICABLE",
                "message": "Transaction is not in AMC processing queue",
            }
        submitted_at = datetime.fromisoformat(txn["created_at"])
        expected_by = submitted_at + timedelta(hours=4)
        delay_hours = random.randint(6, 48)
        return {
            "transaction_id": transaction_id,
            "amc_status": "DELAYED",
            "payment_received": True,
            "nav_allocated": False,
            "submitted_to_amc_at": submitted_at.isoformat(),
            "expected_nav_by": expected_by.isoformat(),
            "current_delay_hours": delay_hours,
            "delay_reason": random.choice([
                "High volume during month-end processing",
                "AMC system maintenance window",
                "BSE StAR MF platform intermittent issue",
            ]),
            "estimated_resolution": (datetime.now() + timedelta(hours=random.randint(2, 8))).isoformat(),
            "action_required": "Wait for AMC to process — no retry needed",
        }

    def execute_sip_retrigger(self, customer_id):
        """Re-trigger a paused SIP for a customer."""
        pause_info = self.get_sip_pause_status(customer_id)
        if not pause_info.get("sip_paused"):
            return {"success": False, "error": "No paused SIP found for this customer"}
        if not pause_info.get("retrigger_eligible"):
            return {"success": False, "error": "SIP is not eligible for retrigger at this time"}

        txn_id = pause_info["paused_transaction_id"]
        txn = self.get_transaction(txn_id)
        if txn:
            txn["status"] = "PENDING"
            txn["rejection_reason"] = None
            txn["issue_type"] = "SUCCESS"
        return {
            "success": True,
            "message": "SIP retriggered successfully — submitted to exchange queue",
            "transaction_id": txn_id,
            "new_status": "PENDING",
        }

    def execute_retry(self, transaction_id):
        """Simulate a retry operation"""
        txn = self.get_transaction(transaction_id)
        if not txn:
            return {"success": False, "error": "Transaction not found"}
        
        if not txn["retry_eligible"]:
            return {
                "success": False, 
                "error": f"Transaction not eligible for retry - {txn['rejection_reason']}"
            }
        
        # 80% chance of success on retry for eligible transactions
        if random.random() < 0.8:
            txn["status"] = "SUCCESS"
            txn["retry_eligible"] = False
            return {"success": True, "message": "Retry successful", "new_status": "SUCCESS"}
        else:
            return {"success": False, "message": "Retry failed - bank still rejecting", "new_status": "FAILED"}
    
    def save_to_file(self, filepath):
        """Save database to JSON file"""
        data = {
            "transactions": self.transactions,
            "mandates": self.mandates,
            "event_logs": self.event_logs,
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "count": {
                    "transactions": len(self.transactions),
                    "mandates": len(self.mandates),
                    "logs": len(self.event_logs)
                }
            }
        }
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        return filepath


# Global instance
db = MockDatabase()


def get_db():
    """Get database instance"""
    return db


if __name__ == "__main__":
    # Save to file for inspection
    output_path = Path(__file__).parent / "mock_db.json"
    db.save_to_file(output_path)
    print(f"✅ Mock database saved to: {output_path}")
    print(f"   - {len(db.transactions)} transactions")
    print(f"   - {len(db.mandates)} mandates")
    print(f"   - {len(db.event_logs)} event logs")
    
    # Show sample data
    print("\n📊 Sample Transaction:")
    print(json.dumps(db.transactions[0], indent=2))

"""
Mock Database for Zero-Touch Agent
Based on real Jira ticket patterns from NOC-21854, NOC-1346, NOC-11734
"""

import json
import random
from datetime import datetime, timedelta
from pathlib import Path


class MockDatabase:
    """Mock database with realistic fintech data"""
    
    def __init__(self):
        self.transactions = []
        self.mandates = []
        self.event_logs = []
        self._seed_data()
    
    def _seed_data(self):
        """Seed database with realistic patterns based on real tickets"""
        
        # Real customer IDs from fetched tickets
        real_customers = [
            {"id": "AHYPR8658L", "name": "Rajesh Kumar", "email": "rajesh.k@email.com"},
            {"id": "ATUPN0386P", "name": "Priya Sharma", "email": "priya.s@email.com"},
            {"id": "AKCPS3067R", "name": "Vikram Patel", "email": "vikram.p@email.com"},
        ]
        
        # Generate 50 realistic transactions
        for i in range(50):
            customer = random.choice(real_customers)
            
            # Create transaction with realistic patterns
            txn = self._generate_transaction(
                customer_id=customer["id"],
                index=i
            )
            self.transactions.append(txn)
            
            # Create corresponding mandate
            mandate = self._generate_mandate(
                customer_id=customer["id"],
                transaction=txn
            )
            if mandate:
                self.mandates.append(mandate)
            
            # Create event logs
            logs = self._generate_event_logs(txn)
            self.event_logs.extend(logs)
    
    def _generate_transaction(self, customer_id, index):
        """Generate a realistic transaction"""
        
        # Distribution based on real ticket analysis
        issue_types = [
            ("SIP_FAILURE", 0.4),      # 40% - Bank code 51
            ("MANDATE_EXPIRY", 0.3),   # 30% - Bank code 54  
            ("PAYMENT_FAILURE", 0.2),  # 20% - Bank code 91
            ("SUCCESS", 0.1),          # 10% - Success
        ]
        
        issue_type = random.choices(
            [t[0] for t in issue_types],
            weights=[t[1] for t in issue_types]
        )[0]
        
        # Bank codes based on issue type
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
        else:  # SUCCESS
            bank_code = None
            rejection_reason = None
            status = "SUCCESS"
            retry_eligible = False
        
        # Generate transaction ID
        txn_id = f"TXN{datetime.now().strftime('%Y%m%d')}{index:06d}"
        
        # Generate mandate ID
        mandate_id = f"MAN{customer_id[-4:]}{index:03d}"
        
        # Random amount (SIP amounts)
        amount = random.choice([500, 1000, 2000, 5000, 10000, 25000])
        
        # Random date in last 30 days
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
        
        # Log 4: Bank response
        if transaction["status"] == "FAILED":
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

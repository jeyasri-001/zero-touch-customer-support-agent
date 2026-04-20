"""
Agent Tools - Functions the LLM can call to investigate tickets
These are the 'actions' the agent can take to diagnose issues
"""

from typing import Dict, Any, List, Optional
import json


class AgentTools:
    """Tools available to the agent for investigation"""
    
    def __init__(self, db, rag_service=None):
        self.db = db
        self.rag = rag_service
    
    def get_transaction_details(self, transaction_id: str) -> str:
        """
        Tool 1: Get details of a specific transaction
        Args: transaction_id (str) - The transaction ID to look up
        Returns: JSON string with transaction details
        """
        txn = self.db.get_transaction(transaction_id)
        if not txn:
            return json.dumps({"error": f"Transaction {transaction_id} not found"})
        return json.dumps(txn)
    
    def get_customer_transactions(self, customer_id: str) -> str:
        """
        Tool 2: Get all recent transactions for a customer
        Args: customer_id (str) - Customer PAN/ID
        Returns: JSON string with list of transactions
        """
        txns = self.db.get_transactions_by_customer(customer_id, limit=10)
        if not txns:
            return json.dumps({"error": f"No transactions found for customer {customer_id}"})
        return json.dumps({"customer_id": customer_id, "transactions": txns, "count": len(txns)})
    
    def query_event_logs(self, transaction_id: str) -> str:
        """
        Tool 3: Query system event logs for a transaction (CRITICAL for diagnosis)
        Args: transaction_id (str) - Transaction to get logs for
        Returns: JSON string with event logs
        """
        logs = self.db.get_event_logs(transaction_id)
        if not logs:
            return json.dumps({"error": f"No logs found for transaction {transaction_id}"})
        return json.dumps({"transaction_id": transaction_id, "logs": logs, "count": len(logs)})
    
    def check_mandate_status(self, customer_id: str) -> str:
        """
        Tool 4: Check ECS mandate status for a customer
        Args: customer_id (str) - Customer PAN/ID
        Returns: JSON string with mandate details
        """
        mandate = self.db.get_mandate_by_customer(customer_id)
        if not mandate:
            return json.dumps({"error": f"No mandate found for customer {customer_id}"})
        return json.dumps(mandate)
    
    def get_bank_rejection_code(self, transaction_id: str) -> str:
        """
        Tool 5: Get specific bank rejection code and reason
        Args: transaction_id (str) - Failed transaction ID
        Returns: JSON string with rejection details
        """
        rejection = self.db.get_bank_rejection_code(transaction_id)
        if not rejection:
            return json.dumps({"error": "No rejection info - transaction may be successful"})
        return json.dumps(rejection)
    
    def execute_payment_retry(self, transaction_id: str) -> str:
        """
        Tool 6: Execute automatic retry of a failed payment (AUTO-RESOLUTION)
        Args: transaction_id (str) - Transaction to retry
        Returns: JSON string with retry result
        """
        result = self.db.execute_retry(transaction_id)
        return json.dumps(result)
    
    def check_sip_schedule(self, customer_id: str) -> str:
        """
        Tool 7: Get SIP schedule and history for a customer
        Args: customer_id (str) - Customer PAN/ID
        Returns: JSON string with SIP schedule info
        """
        schedule = self.db.get_sip_schedule(customer_id)
        if not schedule:
            return json.dumps({"error": f"No SIP schedule found for {customer_id}"})
        return json.dumps(schedule)
    
    def get_customer_contact_history(self, customer_id: str) -> str:
        """
        Tool 8: Get past support tickets (RAG - learn from resolved cases)
        Args: customer_id (str) - Customer PAN/ID
        Returns: JSON string with past tickets and their resolutions
        """
        history = self.db.get_customer_contact_history(customer_id)
        return json.dumps(history)
    
    def search_similar_past_tickets(self, issue_description: str) -> str:
        """
        Tool 9: RAG - Search semantically similar Done tickets from ChromaDB
        Args: issue_description (str) - The current issue description
        Returns: JSON string with similar past tickets and their resolutions
        """
        if not self.rag:
            return json.dumps({"error": "RAG service not available"})
        
        similar = self.rag.find_similar_tickets(issue_description, n_results=3)
        if not similar:
            return json.dumps({"similar_tickets": [], "message": "No similar past tickets found"})
        
        return json.dumps({
            "similar_tickets": similar,
            "count": len(similar),
            "top_match_score": similar[0].get("similarity_score", 0) if similar else 0
        })
    
    def get_tool_definitions(self) -> List[Dict]:
        """Return OpenAI-format tool definitions for Groq"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_transaction_details",
                    "description": "Get details of a specific transaction by ID. Use when you have a transaction ID and need full details.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "transaction_id": {"type": "string", "description": "The transaction ID (format: TXNxxxxxxxxxxx)"}
                        },
                        "required": ["transaction_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_customer_transactions",
                    "description": "Get recent transactions for a customer by their PAN/customer ID. Use this FIRST when investigating a customer's issue.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "customer_id": {"type": "string", "description": "Customer PAN or ID (format: XXXXX####X)"}
                        },
                        "required": ["customer_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "query_event_logs",
                    "description": "Query system event logs for a transaction. CRITICAL for root cause analysis - shows exactly what happened during processing.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "transaction_id": {"type": "string", "description": "The transaction ID to get logs for"}
                        },
                        "required": ["transaction_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_mandate_status",
                    "description": "Check if customer's ECS mandate is active, expired, or pending. Use for mandate-related issues.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "customer_id": {"type": "string", "description": "Customer PAN or ID"}
                        },
                        "required": ["customer_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_bank_rejection_code",
                    "description": "Get specific bank rejection code and reason for a failed transaction. Code 51=Insufficient Funds, 54=Expired Mandate, 91=Bank Temp Unavailable.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "transaction_id": {"type": "string", "description": "The failed transaction ID"}
                        },
                        "required": ["transaction_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "execute_payment_retry",
                    "description": "AUTO-RESOLUTION: Execute an automatic retry for a failed payment. Only use if bank rejection was temporary (code 51 or 91).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "transaction_id": {"type": "string", "description": "The transaction ID to retry"}
                        },
                        "required": ["transaction_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_sip_schedule",
                    "description": "Get customer's SIP schedule, installment history, and success/failure rates.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "customer_id": {"type": "string", "description": "Customer PAN or ID"}
                        },
                        "required": ["customer_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_customer_contact_history",
                    "description": "Get past support tickets for this customer and how they were resolved. Use to identify patterns and apply learned resolutions.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "customer_id": {"type": "string", "description": "Customer PAN or ID"}
                        },
                        "required": ["customer_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_similar_past_tickets",
                    "description": "RAG search: Find semantically similar PAST RESOLVED tickets (from all customers) using vector search. Use to learn from how similar issues were resolved before.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "issue_description": {"type": "string", "description": "Description of the current issue to search for similar past cases"}
                        },
                        "required": ["issue_description"]
                    }
                }
            }
        ]
    
    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Execute a tool by name with given arguments"""
        tool_map = {
            "get_transaction_details": self.get_transaction_details,
            "get_customer_transactions": self.get_customer_transactions,
            "query_event_logs": self.query_event_logs,
            "check_mandate_status": self.check_mandate_status,
            "get_bank_rejection_code": self.get_bank_rejection_code,
            "execute_payment_retry": self.execute_payment_retry,
            "check_sip_schedule": self.check_sip_schedule,
            "get_customer_contact_history": self.get_customer_contact_history,
            "search_similar_past_tickets": self.search_similar_past_tickets,
        }
        
        if tool_name not in tool_map:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
        
        try:
            return tool_map[tool_name](**arguments)
        except Exception as e:
            return json.dumps({"error": f"Tool execution failed: {str(e)}"})

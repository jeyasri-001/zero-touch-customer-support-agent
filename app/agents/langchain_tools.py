"""
LangChain Tool Wrappers for the Support Agent
Wraps our AgentTools methods as LangChain Tools for ReAct pattern
"""

from langchain_core.tools import tool
from typing import Callable
import json


def build_langchain_tools(agent_tools):
    """
    Convert our AgentTools methods into LangChain Tool objects.
    These will be used by the LangChain ReAct agent.
    """
    
    @tool
    def get_customer_transactions(customer_id: str) -> str:
        """Get recent transactions for a customer by their PAN/customer ID. Use this FIRST when investigating a customer's issue. Customer ID format: XXXXX####X"""
        return agent_tools.get_customer_transactions(customer_id)
    
    @tool
    def get_transaction_details(transaction_id: str) -> str:
        """Get details of a specific transaction by ID. Transaction ID format: TXNxxxxxxxxxxx"""
        return agent_tools.get_transaction_details(transaction_id)
    
    @tool
    def query_event_logs(transaction_id: str) -> str:
        """Query system event logs for a transaction. CRITICAL for root cause analysis - shows what happened during processing."""
        return agent_tools.query_event_logs(transaction_id)
    
    @tool
    def check_mandate_status(customer_id: str) -> str:
        """Check if customer's ECS mandate is active, expired, or pending."""
        return agent_tools.check_mandate_status(customer_id)
    
    @tool
    def get_bank_rejection_code(transaction_id: str) -> str:
        """Get specific bank rejection code and reason for a failed transaction. Code 51=Insufficient Funds, 54=Expired Mandate, 91=Bank Temp Unavailable."""
        return agent_tools.get_bank_rejection_code(transaction_id)
    
    @tool
    def execute_payment_retry(transaction_id: str) -> str:
        """AUTO-RESOLUTION: Execute an automatic retry for a failed payment. Only use if bank rejection was temporary (code 51 or 91)."""
        return agent_tools.execute_payment_retry(transaction_id)
    
    @tool
    def check_sip_schedule(customer_id: str) -> str:
        """Get customer's SIP schedule, installment history, and success/failure rates."""
        return agent_tools.check_sip_schedule(customer_id)
    
    @tool
    def get_customer_contact_history(customer_id: str) -> str:
        """Get past support tickets for this customer and how they were resolved."""
        return agent_tools.get_customer_contact_history(customer_id)
    
    @tool
    def search_similar_past_tickets(issue_description: str) -> str:
        """RAG search: Find semantically similar PAST RESOLVED tickets using vector search. Use to learn from how similar issues were resolved before."""
        return agent_tools.search_similar_past_tickets(issue_description)
    
    return [
        get_customer_transactions,
        get_transaction_details,
        query_event_logs,
        check_mandate_status,
        get_bank_rejection_code,
        execute_payment_retry,
        check_sip_schedule,
        get_customer_contact_history,
        search_similar_past_tickets,
    ]

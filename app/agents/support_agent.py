"""
Support Agent - Real LLM-based agent using Groq Llama 3.3 70B
Uses ReAct pattern with tool calling for dynamic reasoning
"""

import os
import json
import re
import asyncio
from typing import Dict, Any, List
from groq import Groq

from app.agents.tools import AgentTools
from app.agents.prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from app.services.validation_service import ValidationService
from app.services.rag_service import get_rag_service


class SupportAgent:
    """LLM-powered agent for diagnosing and resolving support tickets"""
    
    def __init__(self, db, enable_rag: bool = True):
        self.db = db
        
        # Initialize RAG (ChromaDB) for past ticket retrieval
        self.rag = None
        if enable_rag:
            try:
                self.rag = get_rag_service()
                indexed = self.rag.index_past_tickets()
                if indexed > 0:
                    print(f"📚 RAG: Indexed {indexed} past tickets")
                else:
                    print(f"📚 RAG: {self.rag.collection.count()} tickets already indexed")
            except Exception as e:
                print(f"⚠️ RAG init failed (continuing without): {e}")
        
        self.tools = AgentTools(db, rag_service=self.rag)
        
        # Initialize Groq client
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not set in environment")
        
        self.client = Groq(api_key=api_key)
        self.model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.max_iterations = 10  # Max tool-calling rounds
    
    async def process_ticket(self, ticket_key: str, summary: str, description: str = "", customer_id: str = None) -> Dict[str, Any]:
        """
        Process a ticket using LLM reasoning with tool calls.
        The LLM dynamically decides which tools to call and in what order.
        """
        
        # Build initial conversation
        user_message = USER_PROMPT_TEMPLATE.format(
            ticket_key=ticket_key,
            summary=summary,
            description=description or "No description provided"
        )
        
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ]
        
        tool_definitions = self.tools.get_tool_definitions()
        
        # Track investigation
        tool_calls_made = []
        
        # Agent loop: LLM reasons, calls tools, observes results, repeats
        for iteration in range(self.max_iterations):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=tool_definitions,
                    tool_choice="auto",
                    temperature=0.1,  # Low temp for deterministic tool calling
                    max_tokens=2048
                )
                
                message = response.choices[0].message
                
                # Append assistant message to conversation
                messages.append({
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        } for tc in (message.tool_calls or [])
                    ] if message.tool_calls else None
                })
                
                # If LLM made tool calls, execute them
                if message.tool_calls:
                    for tool_call in message.tool_calls:
                        tool_name = tool_call.function.name
                        try:
                            tool_args = json.loads(tool_call.function.arguments)
                        except json.JSONDecodeError:
                            tool_args = {}
                        
                        print(f"  🔧 [{iteration+1}] Calling tool: {tool_name}({tool_args})")
                        
                        # Execute tool
                        tool_result = self.tools.execute_tool(tool_name, tool_args)
                        
                        tool_calls_made.append({
                            "tool": tool_name,
                            "args": tool_args,
                            "result_preview": tool_result[:200]
                        })
                        
                        # Add tool result to conversation
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": tool_result
                        })
                    
                    # Continue loop - let LLM process tool results
                    continue
                
                # No more tool calls - LLM should have final answer
                final_content = message.content or ""
                print(f"  ✅ Agent finished after {iteration+1} iteration(s)")
                
                # Parse LLM's final JSON response
                result = self._parse_final_response(final_content)
                result["tool_calls_made"] = tool_calls_made
                result["iterations"] = iteration + 1
                result["ticket_key"] = ticket_key
                
                # VALIDATION LAYER: Check diagnosis before action
                is_valid, reason, validation_details = ValidationService.validate_diagnosis(
                    result, tool_calls_made
                )
                
                result["validation"] = {
                    "passed": is_valid,
                    "reason": reason,
                    "details": validation_details
                }
                
                # Override action if validation failed
                if not is_valid:
                    result["action_taken"] = "ESCALATE_TO_HUMAN"
                    result["status"] = "ESCALATED"
                    result["action_result"] = f"Validation blocked: {reason}"
                
                return result
                
            except Exception as e:
                error_msg = str(e)
                # Handle Groq rate limit - wait and retry
                if "rate_limit_exceeded" in error_msg or "429" in error_msg:
                    match = re.search(r'try again in ([\d.]+)s', error_msg)
                    wait_time = float(match.group(1)) + 1 if match else 10
                    print(f"  ⏳ Rate limited - waiting {wait_time:.1f}s and retrying...")
                    await asyncio.sleep(wait_time)
                    continue  # Retry same iteration
                
                print(f"  ❌ Error in agent loop: {e}")
                return self._error_response(ticket_key, str(e), tool_calls_made)
        
        # Max iterations reached
        return self._error_response(ticket_key, "Max iterations reached", tool_calls_made)
    
    def _parse_final_response(self, content: str) -> Dict[str, Any]:
        """Parse LLM's final response to extract structured data"""
        
        # Try to extract JSON from the response
        try:
            # Look for JSON block in response
            if "```json" in content:
                json_start = content.find("```json") + 7
                json_end = content.find("```", json_start)
                json_str = content[json_start:json_end].strip()
            elif "{" in content and "}" in content:
                json_start = content.find("{")
                json_end = content.rfind("}") + 1
                json_str = content[json_start:json_end]
            else:
                json_str = content
            
            data = json.loads(json_str)
            
            # Normalize response
            return {
                "diagnosis": data.get("diagnosis", "No diagnosis provided"),
                "root_cause": data.get("root_cause", "UNKNOWN"),
                "confidence": float(data.get("confidence", 0.5)),
                "evidence": data.get("evidence", []),
                "action_taken": data.get("action_taken", "ESCALATE_TO_HUMAN"),
                "action_result": data.get("action_result", ""),
                "customer_response": data.get("customer_response", "We are looking into your issue."),
                "status": "RESOLVED" if "RETRY_EXECUTED" in str(data.get("action_taken", "")) and "success" in str(data.get("action_result", "")).lower() else "ESCALATED",
                "raw_response": content
            }
            
        except (json.JSONDecodeError, ValueError) as e:
            # Fallback: return raw content
            return {
                "diagnosis": content[:500],
                "root_cause": "UNKNOWN",
                "confidence": 0.3,
                "evidence": [],
                "action_taken": "ESCALATE_TO_HUMAN",
                "action_result": "Could not parse LLM response",
                "customer_response": "We are investigating your issue and will update you shortly.",
                "status": "ESCALATED",
                "parse_error": str(e),
                "raw_response": content
            }
    
    def _error_response(self, ticket_key: str, error: str, tool_calls: List) -> Dict[str, Any]:
        """Return error response"""
        return {
            "ticket_key": ticket_key,
            "diagnosis": f"Agent error: {error}",
            "root_cause": "SYSTEM_ERROR",
            "confidence": 0.0,
            "evidence": [],
            "action_taken": "ESCALATE_TO_HUMAN",
            "action_result": "Agent failed",
            "customer_response": "We are experiencing technical difficulties. Our team will reach out to you shortly.",
            "status": "ERROR",
            "tool_calls_made": tool_calls,
            "error": error
        }

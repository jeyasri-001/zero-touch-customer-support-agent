"""
LangChain-based Support Agent with LangSmith observability
Uses tool-calling agent pattern with Groq Llama 3.3 70B
"""

import os
import json
import asyncio
from typing import Dict, Any, List

from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.agents.tools import AgentTools
from app.agents.langchain_tools import build_langchain_tools
from app.agents.prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from app.services.validation_service import ValidationService
from app.services.rag_service import get_rag_service


class LangChainSupportAgent:
    """
    Production-grade support agent built with LangChain framework.
    - Uses ChatGroq with native tool calling
    - LangSmith tracing automatically enabled if LANGSMITH_API_KEY is set
    - ReAct-style reasoning with validation layer
    """
    
    def __init__(self, db, enable_rag: bool = True):
        self.db = db
        
        # Setup LangSmith tracing (automatic if env vars set)
        self._setup_langsmith()
        
        # Initialize RAG
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
                print(f"⚠️ RAG init failed: {e}")
        
        # Build tools
        self.agent_tools = AgentTools(db, rag_service=self.rag)
        self.tools = build_langchain_tools(self.agent_tools)
        
        # Initialize LangChain LLM (auto-traced by LangSmith)
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not set")
        
        model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        
        self.llm = ChatGroq(
            api_key=api_key,
            model=model,
            temperature=0.1,
            max_tokens=2048,
        )
        
        # Bind tools to LLM (enables native tool calling)
        self.llm_with_tools = self.llm.bind_tools(self.tools)
        self.tool_map = {t.name: t for t in self.tools}
        self.max_iterations = 10
        
        print(f"🤖 LangChain Agent ready (model: {model}, tools: {len(self.tools)})")
    
    def _setup_langsmith(self):
        """Enable LangSmith tracing if API key is set"""
        if os.getenv("LANGSMITH_API_KEY"):
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGSMITH_API_KEY")
            os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGSMITH_PROJECT", "zero-touch-agent")
            print(f"📊 LangSmith tracing enabled → project: {os.environ['LANGCHAIN_PROJECT']}")
        else:
            print("⚠️ LangSmith not enabled (set LANGSMITH_API_KEY to enable)")
    
    async def process_ticket(self, ticket_key: str, summary: str, description: str = "", customer_id: str = None) -> Dict[str, Any]:
        """Process a ticket using LangChain agent with tool calling"""
        
        user_message = USER_PROMPT_TEMPLATE.format(
            ticket_key=ticket_key,
            summary=summary,
            description=description or "No description provided"
        )
        
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_message)
        ]
        
        tool_calls_made = []
        iteration = 0
        rate_limit_retries = 0
        max_rate_limit_retries = 5
        
        # Agent loop: LLM reasons, calls tools, observes, repeats
        while iteration < self.max_iterations:
            try:
                # Invoke LLM with tools (traced by LangSmith)
                response = await self.llm_with_tools.ainvoke(messages)
                messages.append(response)
                
                # Successful call - increment iteration
                iteration += 1
                
                # Check if LLM wants to call tools
                if response.tool_calls:
                    for tool_call in response.tool_calls:
                        tool_name = tool_call["name"]
                        tool_args = tool_call["args"]
                        
                        print(f"  🔧 [{iteration+1}] {tool_name}({tool_args})")
                        
                        # Execute tool
                        if tool_name in self.tool_map:
                            tool_result = self.tool_map[tool_name].invoke(tool_args)
                        else:
                            tool_result = json.dumps({"error": f"Unknown tool: {tool_name}"})
                        
                        tool_calls_made.append({
                            "tool": tool_name,
                            "args": tool_args,
                            "result_preview": str(tool_result)[:200]
                        })
                        
                        # Add tool result to messages
                        messages.append(ToolMessage(
                            content=str(tool_result),
                            tool_call_id=tool_call["id"]
                        ))
                    
                    continue  # Let LLM process results
                
                # No more tool calls - we have final answer
                final_content = response.content or ""
                print(f"  ✅ Agent finished after {iteration+1} iteration(s)")
                
                # Parse response
                result = self._parse_response(final_content)
                result["tool_calls_made"] = tool_calls_made
                result["iterations"] = iteration + 1
                result["ticket_key"] = ticket_key
                
                # Validation layer
                is_valid, reason, validation_details = ValidationService.validate_diagnosis(
                    result, tool_calls_made
                )
                result["validation"] = {
                    "passed": is_valid,
                    "reason": reason,
                    "details": validation_details
                }
                
                if not is_valid:
                    result["action_taken"] = "ESCALATE_TO_HUMAN"
                    result["status"] = "ESCALATED"
                    result["action_result"] = f"Validation blocked: {reason}"
                
                return result
                
            except Exception as e:
                error_msg = str(e)
                # Handle Groq rate limit - simple retry with backoff
                if "rate_limit" in error_msg.lower() or "429" in error_msg:
                    rate_limit_retries += 1
                    if rate_limit_retries > max_rate_limit_retries:
                        print(f"  ❌ Rate limit retries exhausted")
                        return self._error_response(ticket_key, "Rate limit exhausted", tool_calls_made)
                    
                    wait_time = 5 * rate_limit_retries  # 5s, 10s, 15s, 20s, 25s
                    print(f"  ⏳ Rate limited (retry {rate_limit_retries}/{max_rate_limit_retries}) - waiting {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue  # Don't increment iteration
                
                print(f"  ❌ Error: {e}")
                return self._error_response(ticket_key, str(e), tool_calls_made)
        
        return self._error_response(ticket_key, "Max iterations reached", tool_calls_made)
    
    def _parse_response(self, content: str) -> Dict[str, Any]:
        """Parse LLM's final response to extract diagnosis JSON"""
        try:
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
            action_taken = str(data.get("action_taken", ""))
            action_result = str(data.get("action_result", ""))
            
            return {
                "diagnosis": data.get("diagnosis", "No diagnosis"),
                "root_cause": data.get("root_cause", "UNKNOWN"),
                "confidence": float(data.get("confidence", 0.5)),
                "evidence": data.get("evidence", []),
                "action_taken": action_taken,
                "action_result": action_result,
                "customer_response": data.get("customer_response", "We are investigating."),
                "status": "RESOLVED" if "RETRY_EXECUTED" in action_taken.upper() and "success" in action_result.lower() else "ESCALATED",
                "raw_response": content
            }
        except (json.JSONDecodeError, ValueError) as e:
            return {
                "diagnosis": content[:500],
                "root_cause": "UNKNOWN",
                "confidence": 0.3,
                "evidence": [],
                "action_taken": "ESCALATE_TO_HUMAN",
                "action_result": "Parse error",
                "customer_response": "We are investigating your issue.",
                "status": "ESCALATED",
                "parse_error": str(e),
                "raw_response": content
            }
    
    def _error_response(self, ticket_key: str, error: str, tool_calls: List) -> Dict[str, Any]:
        return {
            "ticket_key": ticket_key,
            "diagnosis": f"Agent error: {error}",
            "root_cause": "SYSTEM_ERROR",
            "confidence": 0.0,
            "evidence": [],
            "action_taken": "ESCALATE_TO_HUMAN",
            "action_result": "Agent failed",
            "customer_response": "We are experiencing technical difficulties.",
            "status": "ERROR",
            "tool_calls_made": tool_calls,
            "error": error
        }


# Alias so existing code works
SupportAgent = LangChainSupportAgent

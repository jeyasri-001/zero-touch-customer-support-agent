"""
LangChain-based Support Agent with LangSmith observability
Uses tool-calling agent pattern with model fallback chain for Groq free tier.
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
from app.services.response_sanitizer import sanitize_customer_response

# Maps a triage category to the minimal tool subset needed.
# Avoids sending all 13 schemas on every call — saves ~800-1000 tokens/call.
_TRIAGE_TOOL_MAP = {
    "bank_rejection": [
        "get_customer_transactions", "query_event_logs",
        "get_bank_rejection_code", "execute_payment_retry",
        "search_similar_past_tickets",
    ],
    "mandate": [
        "get_customer_transactions", "query_event_logs",
        "check_mandate_status", "get_bank_rejection_code",
        "search_similar_past_tickets",
    ],
    "sip_paused": [
        "get_customer_transactions", "query_event_logs",
        "check_sip_schedule", "check_sip_pause_status",
        "execute_sip_retrigger", "search_similar_past_tickets",
    ],
    "account_validation": [
        "get_customer_transactions", "query_event_logs",
        "check_account_validation_history", "check_mandate_status",
        "search_similar_past_tickets",
    ],
    "amc_delay": [
        "get_customer_transactions", "query_event_logs",
        "check_amc_processing_status", "search_similar_past_tickets",
    ],
    "kyc_onboarding": [
        "get_customer_transactions", "query_event_logs",
        "check_mandate_status", "search_similar_past_tickets",
    ],
    "general": [
        "get_customer_transactions", "query_event_logs",
        "get_bank_rejection_code", "check_mandate_status",
        "check_sip_pause_status", "check_account_validation_history",
        "check_amc_processing_status", "search_similar_past_tickets",
    ],
}

_TRIAGE_PROMPT = """\
Classify this support ticket into exactly ONE category. Reply with only the category word.

Categories:
- bank_rejection  (SIP failed, payment failed, bank returned error, insufficient funds, bank temp down)
- mandate         (mandate expired, ECS issue, NACH problem, code 54)
- sip_paused      (SIP skipped, SIP not processed, SIP paused, units not submitted)
- account_validation  (invalid account number, mandate registration error, account mismatch)
- amc_delay       (money deducted but units not showing, NAV not allocated, portfolio not updated)
- kyc_onboarding  (KYC activated but portal not updated, account not showing after KYC, client onboarding, activation not reflecting)
- general         (unclear, other, unrelated to above)

Ticket summary: {summary}
Ticket description: {description}
"""

# How many chars of a tool result to keep in message history.
# Full result goes to the LLM on the call it's returned; truncated on re-sends.
_TOOL_RESULT_HISTORY_LIMIT = 300

# Model fallback chain — all support function calling on Groq free tier.
# Each model has its own independent rate-limit bucket, so rotating gives
# combined capacity across all three.
# Primary → best quality for tool use (Llama 4 Scout, explicitly listed under
# "FUNCTION CALLING / TOOL USE" in Groq free tier console).
# llama-3.3-70b-versatile is TEXT TO TEXT only on free tier — kept as last resort.
MODEL_CHAIN = [
    "qwen/qwen3-32b",                              # Primary: strong reasoning
    "openai/gpt-oss-20b",                          # Fallback 1: lighter, different bucket
    "llama-3.3-70b-versatile",                     # Fallback 2: text-to-text tier
]


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
        self.tool_map = {t.name: t for t in self.tools}

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not set")

        # Build one ChatGroq instance per model in the fallback chain.
        # Each model has an independent rate-limit bucket on Groq free tier.
        # If GROQ_MODEL is set explicitly, it becomes the primary (prepended).
        override = os.getenv("GROQ_MODEL")
        chain = MODEL_CHAIN.copy()
        if override and override not in chain:
            chain.insert(0, override)
        elif override and override in chain:
            chain.remove(override)
            chain.insert(0, override)

        self._model_chain: List[str] = chain
        self._model_index: int = 0  # index of currently active model

        self._llm_instances: Dict[str, Any] = {
            m: ChatGroq(api_key=api_key, model=m, temperature=0.1, max_tokens=2048)
            for m in self._model_chain
        }

        # Convenience: the current active LLM
        self.llm = self._llm_instances[self._model_chain[0]]
        self.llm_with_tools = self.llm.bind_tools(self.tools)  # kept for triage

        self.max_iterations = 6

        print(f"🤖 LangChain Agent ready — model chain: {' → '.join(self._model_chain)}")
        print(f"   Active model: {self._model_chain[0]} | tools: {len(self.tools)}")
    
    def _setup_langsmith(self):
        """Enable LangSmith tracing if API key is set"""
        if os.getenv("LANGSMITH_API_KEY"):
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGSMITH_API_KEY")
            os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGSMITH_PROJECT", "zero-touch-agent")
            print(f"📊 LangSmith tracing enabled → project: {os.environ['LANGCHAIN_PROJECT']}")
        else:
            print("⚠️ LangSmith not enabled (set LANGSMITH_API_KEY to enable)")
    
    def _current_model(self) -> str:
        return self._model_chain[self._model_index]

    def _rotate_model(self) -> bool:
        """Advance to the next model in the chain. Returns False if chain exhausted."""
        if self._model_index < len(self._model_chain) - 1:
            self._model_index += 1
            print(f"  🔄 Rotating to fallback model: {self._current_model()}")
            return True
        return False

    def _reset_model(self):
        """Reset back to primary model after a ticket completes."""
        self._model_index = 0

    def _get_llm(self) -> Any:
        return self._llm_instances[self._current_model()]

    @staticmethod
    def _is_rate_limit(error_msg: str) -> bool:
        return "rate_limit" in error_msg.lower() or "429" in error_msg

    async def _triage(self, summary: str, description: str) -> str:
        """
        Fast single-call classifier (~300 tokens) that picks the ticket category.
        Tries each model in chain on rate limit.
        """
        prompt = _TRIAGE_PROMPT.format(
            summary=summary[:300],
            description=(description or "")[:300],
        )
        for model_id, llm in self._llm_instances.items():
            try:
                response = await llm.ainvoke([HumanMessage(content=prompt)])
                category = response.content.strip().lower().split()[0]
                return category if category in _TRIAGE_TOOL_MAP else "general"
            except Exception as e:
                if self._is_rate_limit(str(e)):
                    print(f"  ⏳ Triage rate-limited on {model_id}, trying next model")
                    continue
                return "general"
        return "general"

    async def process_ticket(self, ticket_key: str, summary: str, description: str = "", customer_id: str = None) -> Dict[str, Any]:
        """Process a ticket using LangChain agent with tool calling"""

        # Reset to primary model for each new ticket
        self._reset_model()

        # Stage 1: lightweight triage to pick relevant tools only
        category = await self._triage(summary, description or "")
        active_tool_names = set(_TRIAGE_TOOL_MAP.get(category, _TRIAGE_TOOL_MAP["general"]))
        active_tools = [t for t in self.tools if t.name in active_tool_names]
        active_tool_map = {t.name: t for t in active_tools}
        print(f"  🗂️ Triage: {category} → {len(active_tools)} tools | model: {self._current_model()}")

        def _build_llm_for_ticket():
            """Bind current active model to the pruned tool set."""
            return self._get_llm().bind_tools(active_tools)

        llm_for_ticket = _build_llm_for_ticket()

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

        # Agent loop: LLM reasons, calls tools, observes, repeats
        while iteration < self.max_iterations:
            try:
                # Invoke pruned LLM (only category-relevant tools)
                response = await llm_for_ticket.ainvoke(messages)
                messages.append(response)

                # Successful call - increment iteration
                iteration += 1

                # Check if LLM wants to call tools
                if response.tool_calls:
                    for tool_call in response.tool_calls:
                        tool_name = tool_call["name"]
                        tool_args = tool_call["args"]

                        print(f"  🔧 [{iteration}] {tool_name}({list(tool_args.values())})")

                        # Execute tool
                        if tool_name in active_tool_map:
                            tool_result = active_tool_map[tool_name].invoke(tool_args)
                        else:
                            tool_result = json.dumps({"error": f"Unknown tool: {tool_name}"})

                        # Extract bank code explicitly so validation never relies on truncated preview
                        bank_code = None
                        if tool_name == "get_bank_rejection_code":
                            try:
                                parsed = json.loads(str(tool_result))
                                bank_code = parsed.get("code")
                            except Exception:
                                pass

                        tool_calls_made.append({
                            "tool": tool_name,
                            "args": tool_args,
                            "result_preview": str(tool_result)[:200],
                            **({"bank_code": bank_code} if bank_code is not None else {})
                        })

                        # Truncate result in history to limit tokens re-sent on next iteration.
                        # The LLM sees the full result now; future iterations only need the summary.
                        history_content = str(tool_result)[:_TOOL_RESULT_HISTORY_LIMIT]
                        messages.append(ToolMessage(
                            content=history_content,
                            tool_call_id=tool_call["id"]
                        ))
                    
                    continue  # Let LLM process results
                
                # If model responded with text but hasn't called any tools yet,
                # it drifted — push it back with an explicit nudge instead of accepting
                # a non-diagnosis as the final answer.
                if not tool_calls_made and iteration < self.max_iterations - 1:
                    print(f"  ⚠️ Model drifted (no tools called yet) — nudging")
                    messages.append(HumanMessage(
                        content=(
                            "You must investigate using tools before concluding. "
                            "Call get_customer_transactions with the customer ID right now. "
                            "Do not respond with text until you have called at least one tool."
                        )
                    ))
                    continue

                # No more tool calls - we have final answer
                final_content = response.content or ""
                print(f"  ✅ Agent finished after {iteration} iteration(s)")
                
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
                if self._is_rate_limit(error_msg):
                    # Rotate to next model — each has its own independent rate bucket
                    rotated = self._rotate_model()
                    if rotated:
                        llm_for_ticket = _build_llm_for_ticket()
                        # Small fixed wait to let the new model's bucket stabilise
                        await asyncio.sleep(5)
                        continue  # retry same iteration on new model
                    else:
                        # All models exhausted — wait 60s on primary then retry once
                        print(f"  ⏳ All models rate-limited — waiting 60s before final attempt")
                        self._reset_model()
                        llm_for_ticket = _build_llm_for_ticket()
                        await asyncio.sleep(60)
                        continue

                # Groq 400 tool_use_failed: model output its final JSON but the
                # tool-calling layer rejected it as a malformed tool call.
                # The partial diagnosis is recoverable from failed_generation.
                if "tool_use_failed" in error_msg or "failed_generation" in error_msg:
                    rescued = self._rescue_failed_generation(error_msg)
                    if rescued:
                        print(f"  ♻️ Rescued diagnosis from failed_generation")
                        rescued["tool_calls_made"] = tool_calls_made
                        rescued["iterations"] = iteration
                        rescued["ticket_key"] = ticket_key
                        is_valid, reason, validation_details = ValidationService.validate_diagnosis(
                            rescued, tool_calls_made
                        )
                        rescued["validation"] = {"passed": is_valid, "reason": reason, "details": validation_details}
                        if not is_valid:
                            rescued["action_taken"] = "ESCALATE_TO_HUMAN"
                            rescued["status"] = "ESCALATED"
                            rescued["action_result"] = f"Validation blocked: {reason}"
                        return rescued

                    # Fallback: rotate to next model and retry
                    rotated = self._rotate_model()
                    if rotated:
                        llm_for_ticket = _build_llm_for_ticket()
                        print(f"  🔄 tool_use_failed — retrying on {self._current_model()}")
                        continue

                print(f"  ❌ Error on {self._current_model()}: {e}")
                return self._error_response(ticket_key, str(e), tool_calls_made)

        return self._error_response(ticket_key, "Max iterations reached", tool_calls_made)
    
    def _rescue_failed_generation(self, error_msg: str) -> Dict[str, Any]:
        """
        Groq's tool_use_failed error contains 'failed_generation' with the partial
        JSON the model produced. Extract and complete it so the result isn't lost.
        """
        try:
            # error_msg is the str() of the exception which includes the full JSON body
            import re
            # Extract failed_generation value
            match = re.search(r"'failed_generation':\s*'(.*?)'(?:,|\})", error_msg, re.DOTALL)
            if not match:
                # Try double-quote variant
                match = re.search(r'"failed_generation":\s*"(.*?)"(?:,|\})', error_msg, re.DOTALL)
            if not match:
                # Try to find raw JSON block inside the error message directly
                start = error_msg.find('"failed_generation"')
                if start == -1:
                    return None
                # Grab everything after the colon
                snippet = error_msg[start + len('"failed_generation"'):].lstrip(': "\'')
                partial_json = snippet
            else:
                partial_json = match.group(1).replace("\\n", "\n").replace('\\"', '"')

            # The JSON may be cut off — close any open arrays/objects
            open_braces = partial_json.count("{") - partial_json.count("}")
            open_brackets = partial_json.count("[") - partial_json.count("]")
            if open_brackets > 0:
                partial_json += "]" * open_brackets
            if open_braces > 0:
                partial_json += "}" * open_braces

            data = json.loads(partial_json)

            action_taken = str(data.get("action_taken", "ESCALATE_TO_HUMAN"))
            action_result = str(data.get("action_result", ""))
            action_upper = action_taken.upper()
            result_lower = action_result.lower()
            if any(k in action_upper for k in ("RETRY_EXECUTED", "RETRIGGER_EXECUTED")) and "success" in result_lower:
                ticket_status = "RESOLVED"
            elif action_upper in ("WAIT_FOR_AMC", "NOTIFY_CUSTOMER"):
                ticket_status = "PENDING_FOLLOW_UP"
            else:
                ticket_status = "ESCALATED"

            return {
                "diagnosis": data.get("diagnosis", "Partial diagnosis recovered"),
                "root_cause": data.get("root_cause", "UNKNOWN"),
                "confidence": float(data.get("confidence", 0.4)),
                "evidence": data.get("evidence", []),
                "action_taken": action_taken,
                "action_result": action_result,
                "customer_response": sanitize_customer_response(
                    data.get("customer_response", "We are reviewing your issue and will update you shortly.")
                ),
                "status": ticket_status,
            }
        except Exception as ex:
            print(f"  ⚠️ Rescue attempt failed: {ex}")
            return None

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
            
            action_upper = action_taken.upper()
            result_lower = action_result.lower()
            if any(k in action_upper for k in ("RETRY_EXECUTED", "RETRIGGER_EXECUTED")) and "success" in result_lower:
                ticket_status = "RESOLVED"
            elif action_upper in ("WAIT_FOR_AMC", "NOTIFY_CUSTOMER"):
                ticket_status = "PENDING_FOLLOW_UP"
            else:
                ticket_status = "ESCALATED"

            return {
                "diagnosis": data.get("diagnosis", "No diagnosis"),
                "root_cause": data.get("root_cause", "UNKNOWN"),
                "confidence": float(data.get("confidence", 0.5)),
                "evidence": data.get("evidence", []),
                "action_taken": action_taken,
                "action_result": action_result,
                "customer_response": sanitize_customer_response(
                    data.get("customer_response", "We are investigating.")
                ),
                "status": ticket_status,
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
                "customer_response": sanitize_customer_response(
                    "We are investigating your issue and will get back to you shortly."
                ),
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

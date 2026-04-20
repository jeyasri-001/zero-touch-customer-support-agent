#!/usr/bin/env python3
"""
Test the LLM-based agent with the 3 real NOC tickets
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from data.mock_database import get_db
from app.agents.langchain_agent import SupportAgent


async def test_ticket(agent, ticket_key, summary, description, customer_id):
    """Test a single ticket through the LLM agent"""
    print(f"\n{'=' * 80}")
    print(f"🎫 {ticket_key}: {summary}")
    print(f"{'=' * 80}")
    print(f"Customer: {customer_id}")
    print(f"Description: {description[:150]}...")
    print(f"\n🤖 Agent investigating (using Groq Llama 3.3 70B)...\n")
    
    result = await agent.process_ticket(
        ticket_key=ticket_key,
        summary=summary,
        description=description,
        customer_id=customer_id
    )
    
    print(f"\n📊 DIAGNOSIS:")
    print(f"   Root Cause: {result['root_cause']}")
    print(f"   Confidence: {result['confidence']:.0%}")
    print(f"   Evidence: {', '.join(result.get('evidence', []))}")
    print(f"   Iterations: {result.get('iterations', 0)}")
    print(f"   Tool Calls: {len(result.get('tool_calls_made', []))}")
    
    print(f"\n🔧 ACTION:")
    print(f"   Action: {result['action_taken']}")
    print(f"   Result: {result.get('action_result', 'N/A')}")
    print(f"   Status: {result['status']}")
    
    print(f"\n💬 CUSTOMER RESPONSE:")
    response_text = result['customer_response']
    print(f"   {response_text[:300]}{'...' if len(response_text) > 300 else ''}")
    
    print(f"\n📋 DIAGNOSIS EXPLANATION:")
    diagnosis = result['diagnosis']
    print(f"   {diagnosis[:300]}{'...' if len(diagnosis) > 300 else ''}")
    
    return result


async def main():
    print("=" * 80)
    print("🤖 LLM AGENT TEST - Real Groq Llama 3.3 70B")
    print("=" * 80)
    print("Testing 3 real NOC tickets with LLM-powered dynamic reasoning")
    print("No rule-based logic - Pure AI investigation\n")
    
    # Initialize
    db = get_db()
    agent = SupportAgent(db)
    
    # The 3 real tickets
    tickets = [
        {
            "key": "NOC-21854",
            "summary": "AHYPR8658L- SIP failure reason",
            "description": "Hi team, The investor has two active SIPs for Axis ELSS Tax Saver Fund-Reg(G), which did not process for the month of June. Kindly confirm us the reason for the SIP failure.",
            "customer_id": "AHYPR8658L"
        },
        {
            "key": "NOC-1346",
            "summary": "Payment failure",
            "description": "Investor not able to transaction in all alert SIP. Name: Himani Negi, PAN: ATUPN0386P, Mail: himani.negi59@gmail.com",
            "customer_id": "ATUPN0386P"
        },
        {
            "key": "NOC-11734",
            "summary": "AKCPS3067R - Mandate issue",
            "description": "Mandate issue reported for customer AKCPS3067R - SIP installments failing due to mandate problem",
            "customer_id": "AKCPS3067R"
        }
    ]
    
    results = []
    
    for ticket in tickets:
        try:
            result = await test_ticket(
                agent,
                ticket["key"],
                ticket["summary"],
                ticket["description"],
                ticket["customer_id"]
            )
            results.append(result)
        except Exception as e:
            print(f"\n❌ Error processing {ticket['key']}: {e}")
            import traceback
            traceback.print_exc()
    
    # Summary
    print("\n" + "=" * 80)
    print("📊 SUMMARY - LLM Agent Performance")
    print("=" * 80)
    
    if results:
        for r in results:
            print(f"\n   {r['ticket_key']}:")
            print(f"      Diagnosis: {r['root_cause']} ({r['confidence']:.0%})")
            print(f"      Action: {r['action_taken']}")
            print(f"      Status: {r['status']}")
            print(f"      Tools Used: {len(r.get('tool_calls_made', []))}")
        
        # Accuracy
        correct = sum(1 for r in results if r['confidence'] > 0.7)
        total = len(results)
        accuracy = correct / total if total > 0 else 0
        
        print(f"\n🎯 ACCURACY: {accuracy:.0%} ({correct}/{total} with >70% confidence)")
        
        avg_iterations = sum(r.get('iterations', 0) for r in results) / len(results)
        avg_tools = sum(len(r.get('tool_calls_made', [])) for r in results) / len(results)
        
        print(f"📈 Avg Iterations: {avg_iterations:.1f}")
        print(f"🔧 Avg Tool Calls: {avg_tools:.1f}")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(main())

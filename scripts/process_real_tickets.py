#!/usr/bin/env python3
"""
Process the 3 real Jira tickets through the AI agent
Tickets: NOC-21854, NOC-1346, NOC-11734
"""

import json
import requests
import sys
from pathlib import Path

API_URL = "http://localhost:8000"

# Load ticket data from fetched JSON files
TICKETS_DIR = Path(__file__).parent.parent / "data" / "tickets"

TICKETS = [
    {
        "key": "NOC-21854",
        "summary": "AHYPR8658L- SIP failure reason",
        "description": "Hi team\nThe investor has two active SIPs for Axis ELSS Tax Saver Fund-Reg(G), which did not process for the month of June. Kindly confirm us the reason for the SIP failure.",
        "customer_id": "AHYPR8658L",
        "issue_type": "SIP_FAILURE"
    },
    {
        "key": "NOC-1346", 
        "summary": "Payment failure",
        "description": "Investor not able to transaction in all alert SIP. Name: Himani Negi, PAN: ATUPN0386P, Mail: himani.negi59@gmail.com",
        "customer_id": "ATUPN0386P",
        "issue_type": "PAYMENT_FAILURE"
    },
    {
        "key": "NOC-11734",
        "summary": "AKCPS3067R - Mandate issue", 
        "description": "Mandate issue reported for customer AKCPS3067R",
        "customer_id": "AKCPS3067R",
        "issue_type": "MANDATE_ISSUE"
    }
]


def check_api():
    """Check if API is running"""
    try:
        response = requests.get(f"{API_URL}/health", timeout=5)
        return response.status_code == 200
    except:
        return False


def process_ticket(ticket):
    """Process a single ticket through the API"""
    payload = {
        "ticket_key": ticket["key"],
        "summary": ticket["summary"],
        "description": ticket["description"],
        "customer_id": ticket["customer_id"],
        "status": "Open"
    }
    
    try:
        response = requests.post(
            f"{API_URL}/api/process-ticket",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ Error processing {ticket['key']}: {response.status_code}")
            print(f"   {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Exception processing {ticket['key']}: {e}")
        return None


def main():
    print("=" * 70)
    print("🎫 Processing Real Jira Tickets Through AI Agent")
    print("=" * 70)
    
    # Check API
    print("\n🔍 Checking API status...")
    if not check_api():
        print("❌ API not running! Start it first:")
        print("   python3 start_server.py")
        sys.exit(1)
    
    print("✅ API is running")
    
    # Process each ticket
    results = []
    
    print("\n" + "=" * 70)
    print("🚀 Processing Tickets")
    print("=" * 70)
    
    for ticket in TICKETS:
        print(f"\n📋 {ticket['key']}: {ticket['summary']}")
        print(f"   Customer: {ticket['customer_id']}")
        print(f"   Type: {ticket['issue_type']}")
        
        result = process_ticket(ticket)
        
        if result:
            print(f"\n   📊 DIAGNOSIS:")
            print(f"      Root Cause: {result['root_cause']}")
            print(f"      Confidence: {result['confidence']:.0%}")
            print(f"      Status: {result['status']}")
            print(f"\n   🔧 ACTION:")
            print(f"      {result['action_taken']}")
            print(f"\n   💬 CUSTOMER RESPONSE:")
            print(f"      {result['customer_response'][:150]}...")
            
            results.append({
                "ticket": ticket["key"],
                "success": True,
                "diagnosis": result['root_cause'],
                "confidence": result['confidence'],
                "status": result['status']
            })
        else:
            results.append({
                "ticket": ticket["key"],
                "success": False
            })
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 PROCESSING SUMMARY")
    print("=" * 70)
    
    successful = [r for r in results if r['success']]
    
    print(f"\n✅ Successfully processed: {len(successful)}/{len(TICKETS)} tickets")
    
    if successful:
        avg_confidence = sum(r['confidence'] for r in successful) / len(successful)
        print(f"📈 Average confidence: {avg_confidence:.0%}")
        
        print(f"\n📋 Results:")
        for r in successful:
            print(f"   - {r['ticket']}: {r['diagnosis']} ({r['confidence']:.0%} confidence) → {r['status']}")
    
    print("\n" + "=" * 70)
    print("💡 NEXT: Check the Streamlit dashboard!")
    print("   http://localhost:8501")
    print("=" * 70)


if __name__ == "__main__":
    main()

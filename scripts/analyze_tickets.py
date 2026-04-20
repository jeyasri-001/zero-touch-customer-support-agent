#!/usr/bin/env python3
"""
Analyze fetched Jira tickets to extract resolution patterns
Usage: python scripts/analyze_tickets.py
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

TICKETS_DIR = Path(__file__).parent.parent / "data" / "tickets"


def load_ticket(ticket_key):
    """Load a ticket from JSON file"""
    ticket_file = TICKETS_DIR / f"{ticket_key}.json"
    
    if not ticket_file.exists():
        print(f"❌ Ticket file not found: {ticket_file}")
        return None
    
    with open(ticket_file) as f:
        return json.load(f)


def classify_issue(summary, description):
    """Classify the issue type from summary/description"""
    text = f"{summary} {description}".lower()
    
    if "sip" in text or "investment" in text:
        return "SIP_FAILURE"
    elif "mandate" in text or "ecs" in text:
        return "MANDATE_ISSUE"
    elif "payment" in text or "transaction" in text:
        return "PAYMENT_FAILURE"
    elif "bank" in text:
        return "BANK_REJECTION"
    elif "amc" in text:
        return "AMC_DELAY"
    else:
        return "UNKNOWN"


def extract_customer_id(text):
    """Extract customer ID from text (format: XXXXXX####X)"""
    import re
    match = re.search(r'[A-Z]{5}\d{4}[A-Z]', text.upper())
    return match.group(0) if match else None


def analyze_ticket(ticket_key, ticket_data):
    """Analyze a single ticket"""
    analysis = ticket_data.get("analysis", {})
    comments = ticket_data.get("comments", {})
    
    summary = analysis.get("summary", "")
    description = analysis.get("description", "")
    
    # Classify issue
    issue_type = classify_issue(summary, description)
    
    # Extract customer ID
    customer_id = extract_customer_id(f"{summary} {description}")
    
    # Look for resolution patterns in comments
    resolution_patterns = []
    for comment in comments.get("comments", []):
        body = comment.get("body", "").lower()
        
        if any(word in body for word in ["retry", "retried", "success"]):
            resolution_patterns.append("RETRY_SUCCESS")
        if any(word in body for word in ["mandate", "expired", "renew"]):
            resolution_patterns.append("MANDATE_RENEWAL")
        if any(word in body for word in ["bank", "rejection", "code"]):
            resolution_patterns.append("BANK_REJECTION")
        if any(word in body for word in ["escalated", "manual"]):
            resolution_patterns.append("ESCALATED")
    
    return {
        "key": ticket_key,
        "issue_type": issue_type,
        "customer_id": customer_id,
        "summary": summary[:100] + "..." if len(summary) > 100 else summary,
        "status": analysis.get("status"),
        "created": analysis.get("created"),
        "resolved": analysis.get("resolved"),
        "comments_count": analysis.get("comments_count"),
        "resolution_patterns": resolution_patterns,
        "description": description[:200] + "..." if description and len(description) > 200 else description
    }


def generate_mock_data_pattern(tickets_analysis):
    """Generate mock data patterns based on real tickets"""
    patterns = []
    
    for analysis in tickets_analysis:
        issue_type = analysis["issue_type"]
        customer_id = analysis["customer_id"]
        
        if issue_type == "SIP_FAILURE":
            patterns.append({
                "type": "SIP_FAILURE",
                "customer_id": customer_id or "C12345",
                "mandate_id": f"MAN{hash(customer_id) % 10000 if customer_id else 1234}",
                "transaction_id": f"TXN{hash(analysis['key']) % 1000000}",
                "amount": 5000.00,
                "bank_code": "51",  # Insufficient funds
                "rejection_reason": "INSUFFICIENT_FUNDS",
                "resolution": "RETRY_NEXT_DAY"
            })
        
        elif issue_type == "MANDATE_ISSUE":
            patterns.append({
                "type": "MANDATE_EXPIRY",
                "customer_id": customer_id or "C67890",
                "mandate_id": f"MAN{hash(customer_id) % 10000 if customer_id else 5678}",
                "transaction_id": f"TXN{hash(analysis['key']) % 1000000}",
                "amount": 10000.00,
                "bank_code": "54",  # Expired card/mandate
                "rejection_reason": "MANDATE_EXPIRED",
                "resolution": "RENEW_MANDATE"
            })
        
        elif issue_type == "PAYMENT_FAILURE":
            patterns.append({
                "type": "PAYMENT_FAILURE",
                "customer_id": customer_id or "C11111",
                "mandate_id": None,
                "transaction_id": f"TXN{hash(analysis['key']) % 1000000}",
                "amount": 25000.00,
                "bank_code": "91",  # Temporary failure
                "rejection_reason": "BANK_TEMP_UNAVAILABLE",
                "resolution": "RETRY_IMMEDIATE"
            })
    
    return patterns


def main():
    print("=" * 70)
    print("📊 Jira Ticket Analysis - Extracting Resolution Patterns")
    print("=" * 70)
    
    # Find all ticket files
    ticket_files = list(TICKETS_DIR.glob("NOC-*.json"))
    
    if not ticket_files:
        print("\n❌ No ticket files found in data/tickets/")
        print("   Run: python scripts/fetch_jira_tickets.py")
        sys.exit(1)
    
    print(f"\n🔍 Analyzing {len(ticket_files)} tickets...\n")
    
    analyses = []
    issue_type_counts = defaultdict(int)
    
    for ticket_file in sorted(ticket_files):
        ticket_key = ticket_file.stem
        ticket_data = load_ticket(ticket_key)
        
        if ticket_data:
            analysis = analyze_ticket(ticket_key, ticket_data)
            analyses.append(analysis)
            issue_type_counts[analysis["issue_type"]] += 1
            
            # Print summary
            print(f"\n🎫 {analysis['key']}")
            print(f"   Type: {analysis['issue_type']}")
            print(f"   Customer: {analysis['customer_id'] or 'Not found'}")
            print(f"   Summary: {analysis['summary']}")
            print(f"   Status: {analysis['status']}")
            
            if analysis['resolution_patterns']:
                print(f"   Patterns: {', '.join(analysis['resolution_patterns'])}")
    
    # Generate mock data patterns
    mock_patterns = generate_mock_data_pattern(analyses)
    
    # Statistics
    print("\n" + "=" * 70)
    print("📈 Issue Type Distribution")
    print("=" * 70)
    for issue_type, count in sorted(issue_type_counts.items(), key=lambda x: -x[1]):
        print(f"   {issue_type}: {count} tickets")
    
    # Mock data summary
    print("\n" + "=" * 70)
    print("🎨 Mock Data Patterns (for building realistic test scenarios)")
    print("=" * 70)
    for i, pattern in enumerate(mock_patterns, 1):
        print(f"\n{i}. {pattern['type']}")
        print(f"   Customer: {pattern['customer_id']}")
        print(f"   Bank Code: {pattern['bank_code']} ({pattern['rejection_reason']})")
        print(f"   Resolution: {pattern['resolution']}")
    
    # Save analysis
    output_file = Path(__file__).parent.parent / "data" / "ticket_analysis.json"
    with open(output_file, "w") as f:
        json.dump({
            "tickets": analyses,
            "issue_types": dict(issue_type_counts),
            "mock_patterns": mock_patterns
        }, f, indent=2)
    
    print(f"\n💾 Analysis saved to: {output_file}")
    print("\n🎯 NEXT STEPS:")
    print("   1. Review the mock data patterns above")
    print("   2. Create mock database with these patterns")
    print("   3. Build agent tools to query this data")
    print("=" * 70)


if __name__ == "__main__":
    main()

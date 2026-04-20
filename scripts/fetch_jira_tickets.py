#!/usr/bin/env python3
"""
Fetch Jira tickets for analysis
Usage: python scripts/fetch_jira_tickets.py
"""

import requests
from requests.auth import HTTPBasicAuth
import json
import os
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "https://fundsindia.atlassian.net")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
TICKETS_TO_FETCH = os.getenv("JIRA_TICKETS", "NOC-21854,NOC-1346,NOC-11734").split(",")

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "tickets"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def fetch_ticket(issue_key):
    """Fetch a single Jira ticket"""
    url = f"{JIRA_BASE_URL}/rest/api/2/issue/{issue_key}"
    auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
    headers = {"Accept": "application/json"}
    
    print(f"\n🔍 Fetching {issue_key}...")
    
    try:
        response = requests.get(url, auth=auth, headers=headers, timeout=30)
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 401:
            print(f"❌ Authentication failed for {issue_key}")
            return None
        elif response.status_code == 404:
            print(f"❌ Ticket {issue_key} not found")
            return None
        else:
            print(f"❌ Error fetching {issue_key}: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error fetching {issue_key}: {e}")
        return None


def analyze_ticket_structure(ticket):
    """Extract relevant fields for analysis"""
    fields = ticket.get("fields", {})
    
    return {
        "key": ticket.get("key"),
        "summary": fields.get("summary"),
        "description": fields.get("description", ""),
        "status": fields.get("status", {}).get("name", "Unknown"),
        "status_category": fields.get("status", {}).get("statusCategory", {}).get("name", "Unknown"),
        "created": fields.get("created"),
        "updated": fields.get("updated"),
        "resolved": fields.get("resolutiondate"),
        "reporter": fields.get("reporter", {}).get("displayName") if fields.get("reporter") else None,
        "assignee": fields.get("assignee", {}).get("displayName") if fields.get("assignee") else None,
        "labels": fields.get("labels", []),
        "issue_type": fields.get("issuetype", {}).get("name", "Unknown"),
        "priority": fields.get("priority", {}).get("name", "Unknown"),
        "comments_count": len(fields.get("comment", {}).get("comments", [])),
        "changelog": fields.get("changelog", {}).get("histories", []),
        # Extract custom fields if present
        "custom_fields": {
            k: v for k, v in fields.items() 
            if k.startswith("customfield_") and v is not None
        }
    }


def fetch_comments(issue_key):
    """Fetch comments for a ticket"""
    url = f"{JIRA_BASE_URL}/rest/api/2/issue/{issue_key}/comment"
    auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
    headers = {"Accept": "application/json"}
    
    try:
        response = requests.get(url, auth=auth, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            comments = data.get("comments", [])
            
            # Extract resolution-related comments
            resolution_comments = []
            for comment in comments:
                body = comment.get("body", "").lower()
                # Look for resolution keywords
                if any(keyword in body for keyword in [
                    "resolved", "fixed", "retry", "bank", "mandate", 
                    "success", "failed", "root cause", "diagnosis"
                ]):
                    resolution_comments.append({
                        "author": comment.get("author", {}).get("displayName", "Unknown"),
                        "body": comment.get("body", ""),
                        "created": comment.get("created"),
                        "is_resolution_related": True
                    })
            
            return {
                "total": data.get("total", 0),
                "comments": resolution_comments
            }
        else:
            print(f"⚠️  Could not fetch comments for {issue_key}: {response.status_code}")
            return {"total": 0, "comments": []}
            
    except requests.exceptions.RequestException as e:
        print(f"⚠️  Error fetching comments for {issue_key}: {e}")
        return {"total": 0, "comments": []}


def main():
    print("=" * 60)
    print("🔧 Zero-Touch Agent: Jira Ticket Fetcher")
    print("=" * 60)
    print(f"\n📁 Output directory: {OUTPUT_DIR}")
    print(f"🎫 Tickets to fetch: {', '.join(TICKETS_TO_FETCH)}")
    print(f"🔗 Jira URL: {JIRA_BASE_URL}")
    print(f"👤 Email: {JIRA_EMAIL}")
    
    if not JIRA_API_TOKEN:
        print("\n❌ Error: JIRA_API_TOKEN not found in .env file")
        sys.exit(1)
    
    if not JIRA_EMAIL:
        print("\n❌ Error: JIRA_EMAIL not found in .env file")
        sys.exit(1)
    
    # Track results
    fetched = []
    failed = []
    
    for ticket_key in TICKETS_TO_FETCH:
        ticket_key = ticket_key.strip()
        if not ticket_key:
            continue
            
        # Fetch ticket
        ticket_data = fetch_ticket(ticket_key)
        
        if ticket_data:
            # Analyze structure
            analysis = analyze_ticket_structure(ticket_data)
            
            # Fetch comments
            comments = fetch_comments(ticket_key)
            
            # Combine
            full_data = {
                "ticket": ticket_data,
                "analysis": analysis,
                "comments": comments
            }
            
            # Save to file
            output_file = OUTPUT_DIR / f"{ticket_key}.json"
            with open(output_file, "w") as f:
                json.dump(full_data, f, indent=2)
            
            print(f"✅ Saved to {output_file}")
            print(f"   Status: {analysis['status']}")
            print(f"   Comments: {comments['total']} total, {len(comments['comments'])} resolution-related")
            
            fetched.append({
                "key": ticket_key,
                "status": analysis['status'],
                "summary": analysis['summary'][:60] + "..." if analysis['summary'] and len(analysis['summary']) > 60 else analysis['summary']
            })
        else:
            failed.append(ticket_key)
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Fetch Summary")
    print("=" * 60)
    print(f"✅ Successfully fetched: {len(fetched)} tickets")
    for t in fetched:
        print(f"   - {t['key']}: {t['status']} - {t['summary']}")
    
    if failed:
        print(f"\n❌ Failed to fetch: {len(failed)} tickets")
        for t in failed:
            print(f"   - {t}")
    
    print(f"\n💡 Next step: Analyze these tickets to extract resolution patterns")
    print(f"   Run: python scripts/analyze_tickets.py")
    print("=" * 60)


if __name__ == "__main__":
    main()

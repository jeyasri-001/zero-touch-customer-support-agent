"""
Jira Service - Wrapper for Jira API interactions
"""

import os
import requests
from requests.auth import HTTPBasicAuth
from typing import Optional


class JiraService:
    """Service for interacting with Jira API"""

    def __init__(self):
        self.base_url = os.getenv("JIRA_BASE_URL", "https://fundsindia.atlassian.net")
        self.email = os.getenv("JIRA_EMAIL")
        self.api_token = os.getenv("JIRA_API_TOKEN")
        self.enabled = bool(self.email and self.api_token)

    def download_attachment(self, content_url: str) -> Optional[bytes]:
        """Download a Jira attachment by its content URL and return raw bytes."""
        if not self.enabled:
            return None
        try:
            response = requests.get(
                content_url,
                auth=HTTPBasicAuth(self.email, self.api_token),
                timeout=30
            )
            return response.content if response.status_code == 200 else None
        except Exception as e:
            print(f"⚠️ Failed to download attachment: {e}")
            return None
    
    async def add_comment(self, ticket_key: str, comment: str) -> bool:
        """Add a comment to a Jira ticket"""
        
        if not self.enabled:
            print(f"[MOCK] Would add comment to {ticket_key}:\n{comment[:100]}...")
            return True
        
        url = f"{self.base_url}/rest/api/2/issue/{ticket_key}/comment"
        auth = HTTPBasicAuth(self.email, self.api_token)
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        payload = {
            "body": comment
        }
        
        try:
            response = requests.post(url, auth=auth, headers=headers, json=payload, timeout=30)
            if response.status_code == 201:
                print(f"✅ Added comment to {ticket_key}")
                return True
            else:
                print(f"❌ Failed to add comment to {ticket_key}: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Error adding comment: {e}")
            return False
    
    async def get_issue(self, ticket_key: str) -> Optional[dict]:
        """Fetch a Jira issue by key. Returns dict with key, summary, description, status, customer_id."""
        if not self.enabled:
            print(f"[MOCK] Would fetch {ticket_key}")
            return None

        url = f"{self.base_url}/rest/api/2/issue/{ticket_key}"
        auth = HTTPBasicAuth(self.email, self.api_token)
        headers = {"Accept": "application/json"}

        try:
            response = requests.get(url, auth=auth, headers=headers, timeout=30)
            if response.status_code != 200:
                print(f"❌ Failed to fetch {ticket_key}: {response.status_code}")
                return None

            data = response.json()
            fields = data.get("fields", {})
            summary = fields.get("summary", "") or ""
            description = fields.get("description", "") or ""
            status = (fields.get("status") or {}).get("name", "Open")

            # Try to extract a PAN-like customer_id from summary/description
            import re
            pan_match = re.search(r"\b([A-Z]{5}\d{4}[A-Z])\b", f"{summary} {description}")
            customer_id = pan_match.group(1) if pan_match else None

            # Extract image attachments
            raw_attachments = fields.get("attachment", [])
            attachments = [
                {
                    "id": a["id"],
                    "filename": a["filename"],
                    "content_url": a["content"],
                    "mime_type": a.get("mimeType", ""),
                }
                for a in raw_attachments
                if a.get("mimeType", "").startswith("image/")
            ]

            return {
                "ticket_key": ticket_key,
                "summary": summary,
                "description": description,
                "status": status,
                "customer_id": customer_id,
                "attachments": attachments,
            }
        except Exception as e:
            print(f"❌ Error fetching issue {ticket_key}: {e}")
            return None

    async def transition_issue(self, ticket_key: str, transition_id: str) -> bool:
        """Transition a Jira issue to a new status"""
        
        if not self.enabled:
            print(f"[MOCK] Would transition {ticket_key} to status {transition_id}")
            return True
        
        url = f"{self.base_url}/rest/api/2/issue/{ticket_key}/transitions"
        auth = HTTPBasicAuth(self.email, self.api_token)
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        payload = {
            "transition": {
                "id": transition_id
            }
        }
        
        try:
            response = requests.post(url, auth=auth, headers=headers, json=payload, timeout=30)
            return response.status_code == 204
        except Exception as e:
            print(f"❌ Error transitioning issue: {e}")
            return False

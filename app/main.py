"""
FastAPI Application - Zero-Touch Customer Support Agent
"""

import os
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables FIRST
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import json
from datetime import datetime

from app.agents.langchain_agent import SupportAgent
from app.services.jira_service import JiraService
from data.mock_database import get_db

app = FastAPI(
    title="Zero-Touch Customer Support Agent",
    description="AI agent that diagnoses and resolves fintech support tickets",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
db = get_db()
agent = SupportAgent(db)
jira_service = JiraService()


# Pydantic models
class TicketRequest(BaseModel):
    ticket_key: str
    summary: str
    description: Optional[str] = ""
    customer_id: Optional[str] = None
    status: str = "Open"


class TicketResponse(BaseModel):
    ticket_key: str
    diagnosis: str
    root_cause: str
    confidence: float
    action_taken: str
    customer_response: str
    status: str


class MetricsResponse(BaseModel):
    total_processed: int
    correct_diagnoses: int
    accuracy: float
    auto_resolved: int
    escalated: int
    avg_time: float
    root_causes: Dict[str, int]
    recent_tickets: List[Dict[str, Any]]


# In-memory metrics storage (replace with DB in production)
metrics_store = {
    "processed": [],
    "start_time": datetime.now()
}


@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "Zero-Touch Customer Support Agent",
        "version": "1.0.0",
        "features": ["jira_webhook", "agent_processing", "metrics"]
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.post("/api/process-ticket", response_model=TicketResponse)
async def process_ticket(request: TicketRequest, update_jira: bool = True):
    """Process a support ticket through the AI agent"""
    
    start_time = datetime.now()
    
    try:
        # Process through agent
        result = await agent.process_ticket(
            ticket_key=request.ticket_key,
            summary=request.summary,
            description=request.description,
            customer_id=request.customer_id
        )
        
        # Calculate processing time
        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()
        
        # AUTO-UPDATE JIRA (per plan: add comment + change status)
        if update_jira and request.ticket_key.startswith("NOC-"):
            try:
                comment = _format_jira_comment(result)
                await jira_service.add_comment(request.ticket_key, comment)
                print(f"✅ Updated Jira ticket {request.ticket_key}")
            except Exception as e:
                print(f"⚠️ Jira update failed (non-blocking): {e}")
        
        # Store metrics
        metrics_store["processed"].append({
            "ticket_key": request.ticket_key,
            "root_cause": result["root_cause"],
            "confidence": result["confidence"],
            "processing_time": processing_time,
            "timestamp": end_time.isoformat(),
            "status": result["status"],
            "action_taken": result["action_taken"]
        })
        
        return TicketResponse(
            ticket_key=request.ticket_key,
            diagnosis=result["diagnosis"],
            root_cause=result["root_cause"],
            confidence=result["confidence"],
            action_taken=result["action_taken"],
            customer_response=result["customer_response"],
            status=result["status"]
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _format_jira_comment(result: dict) -> str:
    """Format agent result as a Jira comment"""
    confidence_pct = f"{result['confidence']:.0%}"
    validation = result.get("validation", {})
    validation_status = "✅ Validated" if validation.get("passed") else "⚠️ Validation Flagged"
    
    return f"""🤖 *Zero-Touch Agent Analysis*

*Root Cause:* {result['root_cause']}
*Confidence:* {confidence_pct}
*Status:* {result['status']}
*Validation:* {validation_status}

*Diagnosis:*
{result['diagnosis']}

*Action Taken:* {result['action_taken']}
*Result:* {result.get('action_result', 'N/A')}

*Customer Response Draft:*
{result['customer_response']}

---
_Processed by Zero-Touch Agent (Groq Llama 3.3 70B) - {len(result.get('tool_calls_made', []))} tool calls in {result.get('iterations', 0)} iterations_"""


@app.post("/api/process-by-key/{ticket_key}", response_model=TicketResponse)
async def process_by_key(ticket_key: str, update_jira: bool = True):
    """Fetch ticket from Jira by key, run agent, and update Jira. Takes only the ticket key."""
    ticket_key = ticket_key.strip().upper()
    issue = await jira_service.get_issue(ticket_key)
    if not issue:
        raise HTTPException(status_code=404, detail=f"Could not fetch {ticket_key} from Jira")

    ticket_request = TicketRequest(
        ticket_key=issue["ticket_key"],
        summary=issue["summary"],
        description=issue["description"],
        customer_id=issue.get("customer_id"),
        status=issue.get("status", "Open"),
    )
    return await process_ticket(ticket_request, update_jira=update_jira)


@app.get("/api/jira/{ticket_key}")
async def fetch_jira_ticket(ticket_key: str):
    """Fetch a Jira ticket's details (for preview in dashboard)."""
    issue = await jira_service.get_issue(ticket_key.strip().upper())
    if not issue:
        raise HTTPException(status_code=404, detail=f"Could not fetch {ticket_key}")
    return issue


@app.post("/webhook/jira")
async def jira_webhook(request: Request):
    """Receive Jira webhook events"""
    
    try:
        payload = await request.json()
        
        # Extract relevant data from webhook
        issue = payload.get("issue", {})
        event_type = payload.get("webhookEvent", "")
        
        ticket_key = issue.get("key", "")
        fields = issue.get("fields", {})
        summary = fields.get("summary", "")
        description = fields.get("description", "")
        
        # Only process issue created events
        if "issue_created" in event_type:
            # Create ticket request
            ticket_request = TicketRequest(
                ticket_key=ticket_key,
                summary=summary,
                description=description,
                status="Open"
            )
            
            # Process ticket
            result = await process_ticket(ticket_request)
            
            # Update Jira ticket
            await jira_service.add_comment(
                ticket_key=ticket_key,
                comment=f"**AI Agent Diagnosis**\n\n{result.diagnosis}\n\n**Customer Response:**\n{result.customer_response}"
            )
            
            return {"status": "processed", "ticket": ticket_key}
        
        return {"status": "ignored", "reason": "not a creation event"}
        
    except Exception as e:
        print(f"Webhook error: {e}")
        return {"status": "error", "message": str(e)}


# =====================================================
# ASYNC BATCH PROCESSING (replaces Celery for simplicity)
# =====================================================

# Job tracking store
jobs_store: Dict[str, Dict[str, Any]] = {}


class BatchRequest(BaseModel):
    tickets: List[TicketRequest]


@app.post("/api/process-batch")
async def process_batch(batch: BatchRequest, background_tasks: BackgroundTasks):
    """Process multiple tickets asynchronously (replaces Celery worker)"""
    import uuid
    job_id = str(uuid.uuid4())[:8]
    
    jobs_store[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "total": len(batch.tickets),
        "completed": 0,
        "failed": 0,
        "results": [],
        "started_at": datetime.now().isoformat()
    }
    
    # Run in background
    background_tasks.add_task(_process_batch_background, job_id, batch.tickets)
    
    return {
        "job_id": job_id,
        "status": "queued",
        "total_tickets": len(batch.tickets),
        "check_status_url": f"/api/jobs/{job_id}"
    }


async def _process_batch_background(job_id: str, tickets: List[TicketRequest]):
    """Background task: process all tickets sequentially with rate limit spacing"""
    import asyncio
    jobs_store[job_id]["status"] = "running"
    
    for i, ticket in enumerate(tickets):
        try:
            # Space out requests to avoid rate limits (Groq free tier: 12K tokens/min)
            if i > 0:
                await asyncio.sleep(10)  # 10s between tickets
            
            result = await process_ticket(ticket)
            jobs_store[job_id]["results"].append({
                "ticket_key": ticket.ticket_key,
                "status": result.status,
                "root_cause": result.root_cause,
                "confidence": result.confidence
            })
            jobs_store[job_id]["completed"] += 1
        except Exception as e:
            jobs_store[job_id]["results"].append({
                "ticket_key": ticket.ticket_key,
                "status": "ERROR",
                "error": str(e)
            })
            jobs_store[job_id]["failed"] += 1
    
    jobs_store[job_id]["status"] = "completed"
    jobs_store[job_id]["completed_at"] = datetime.now().isoformat()


@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get status of an async batch job"""
    if job_id not in jobs_store:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs_store[job_id]


@app.get("/api/jobs")
async def list_jobs():
    """List all jobs"""
    return {"jobs": list(jobs_store.values())}


@app.post("/api/metrics/reset")
async def reset_metrics():
    """Reset metrics store (useful between demo runs)"""
    metrics_store["processed"].clear()
    jobs_store.clear()
    return {"status": "reset", "message": "Metrics cleared"}


# =====================================================
# METRICS
# =====================================================

@app.get("/api/metrics", response_model=MetricsResponse)
async def get_metrics():
    """Get current processing metrics for dashboard"""
    
    processed = metrics_store["processed"]
    total = len(processed)
    
    if total == 0:
        return MetricsResponse(
            total_processed=0,
            correct_diagnoses=0,
            accuracy=0.0,
            auto_resolved=0,
            escalated=0,
            avg_time=0.0,
            root_causes={},
            recent_tickets=[]
        )
    
    # Calculate root cause distribution
    root_causes = {}
    for p in processed:
        rc = p.get("root_cause", "UNKNOWN")
        root_causes[rc] = root_causes.get(rc, 0) + 1
    
    # Calculate metrics (simulate accuracy based on confidence > 0.7)
    correct = sum(1 for p in processed if p.get("confidence", 0) > 0.7)
    
    return MetricsResponse(
        total_processed=total,
        correct_diagnoses=correct,
        accuracy=correct / total if total > 0 else 0.0,
        auto_resolved=sum(1 for p in processed if "retry" in str(p.get("action_taken", "")).lower()),
        escalated=sum(1 for p in processed if "escalate" in str(p.get("action_taken", "")).lower()),
        avg_time=sum(p.get("processing_time", 0) for p in processed) / total if total > 0 else 0.0,
        root_causes=root_causes,
        recent_tickets=processed[-10:]  # Last 10 tickets
    )


@app.get("/api/transactions/{transaction_id}")
async def get_transaction(transaction_id: str):
    """Get transaction details (mock)"""
    txn = db.get_transaction(transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return txn


@app.get("/api/transactions/customer/{customer_id}")
async def get_customer_transactions(customer_id: str, limit: int = 10):
    """Get transactions for a customer"""
    return db.get_transactions_by_customer(customer_id, limit)


@app.get("/api/mandates/{mandate_id}")
async def get_mandate(mandate_id: str):
    """Get mandate details (mock)"""
    mandate = db.get_mandate(mandate_id)
    if not mandate:
        raise HTTPException(status_code=404, detail="Mandate not found")
    return mandate


@app.get("/api/logs/{transaction_id}")
async def get_event_logs(transaction_id: str):
    """Get event logs for a transaction"""
    return db.get_event_logs(transaction_id)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

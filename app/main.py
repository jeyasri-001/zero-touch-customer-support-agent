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
from app.services.vision_service import get_vision_service
from app.services.rag_service import get_rag_service
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
    ground_truth_root_cause: Optional[str] = None  # For evaluation: the known correct root cause


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
    accuracy_basis: str  # "ground_truth" or "confidence_proxy"
    evaluated_tickets: int  # how many had a ground_truth label
    auto_resolved: int
    escalated: int
    avg_time: float
    root_causes: Dict[str, int]
    per_root_cause_accuracy: Dict[str, Any]
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
        
        # RAG write-back: index successfully resolved tickets so future queries learn from them
        if result.get("status") == "RESOLVED":
            try:
                rag = get_rag_service()
                rag.index_resolved_ticket(
                    ticket_key=request.ticket_key,
                    summary=request.summary,
                    description=request.description or "",
                    root_cause=result["root_cause"],
                    action_taken=result["action_taken"],
                    action_result=result.get("action_result", ""),
                    diagnosis=result["diagnosis"],
                )
            except Exception as e:
                print(f"⚠️ RAG write-back failed (non-blocking): {e}")

        # AUTO-UPDATE JIRA (per plan: add comment + change status)
        if update_jira and request.ticket_key.startswith("NOC-"):
            try:
                comment = _format_jira_comment(result)
                await jira_service.add_comment(request.ticket_key, comment)
                print(f"✅ Updated Jira ticket {request.ticket_key}")
            except Exception as e:
                print(f"⚠️ Jira update failed (non-blocking): {e}")
        
        # Store metrics — include ground truth if provided for real accuracy calculation
        ground_truth = request.ground_truth_root_cause
        predicted = result["root_cause"]
        correct = (
            ground_truth is not None
            and predicted.upper() == ground_truth.upper()
        )
        metrics_store["processed"].append({
            "ticket_key": request.ticket_key,
            "root_cause": predicted,
            "ground_truth_root_cause": ground_truth,
            "correct": correct if ground_truth else None,
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
    """Format agent result as a clean Jira comment for ops team."""
    confidence_pct = f"{result['confidence']:.0%}"
    status = result['status']
    status_icon = {"RESOLVED": "✅", "PENDING_FOLLOW_UP": "🕐", "ESCALATED": "🔺", "ERROR": "❌"}.get(status, "ℹ️")

    tools_used = [tc["tool"] for tc in result.get("tool_calls_made", [])]
    tools_str = ", ".join(tools_used) if tools_used else "none"

    comment = f"""🤖 *Zero-Touch Agent Analysis*

*Root Cause:* {result['root_cause']}
*Confidence:* {confidence_pct}
*Status:* {status_icon} {status}

*Diagnosis:*
{result['diagnosis']}"""

    action = result.get('action_taken', '')
    action_result = result.get('action_result', '')
    if action and action != "ESCALATE_TO_HUMAN":
        comment += f"\n\n*Action Taken:* {action}"
    if action_result and "Validation blocked" not in action_result and action_result != "N/A":
        comment += f"\n*Result:* {action_result}"

    comment += f"""

*Customer Response Draft:*
{result['customer_response']}

---
_Zero-Touch Agent | Tools used: {tools_str}_"""

    return comment


@app.post("/api/process-by-key/{ticket_key}", response_model=TicketResponse)
async def process_by_key(ticket_key: str, update_jira: bool = True):
    """Fetch ticket from Jira by key, run agent, and update Jira. Takes only the ticket key."""
    ticket_key = ticket_key.strip().upper()
    issue = await jira_service.get_issue(ticket_key)
    if not issue:
        raise HTTPException(status_code=404, detail=f"Could not fetch {ticket_key} from Jira")

    description = issue.get("description") or ""

    # Enrich description with context extracted from image attachments
    attachments = issue.get("attachments", [])
    if attachments:
        vision = get_vision_service()
        if vision:
            image_context = vision.extract_context_from_attachments(
                attachments=attachments,
                download_fn=jira_service.download_attachment
            )
            if image_context:
                description = description + "\n\n" + image_context
                print(f"🖼️ Vision context added for {ticket_key} ({len(attachments)} image(s))")

    ticket_request = TicketRequest(
        ticket_key=issue["ticket_key"],
        summary=issue["summary"],
        description=description,
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
            # Space out requests to avoid rate limits.
            # Free tier: ~6K tokens/min, each ticket ~9K tokens → need ~90s gap.
            # Paid tier: set GROQ_BATCH_DELAY=5 in .env to run faster.
            if i > 0:
                batch_delay = int(os.getenv("GROQ_BATCH_DELAY", "90"))
                await asyncio.sleep(batch_delay)
            
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
            accuracy_basis="ground_truth",
            evaluated_tickets=0,
            auto_resolved=0,
            escalated=0,
            avg_time=0.0,
            root_causes={},
            per_root_cause_accuracy={},
            recent_tickets=[]
        )

    # Root cause distribution
    root_causes: Dict[str, int] = {}
    for p in processed:
        rc = p.get("root_cause", "UNKNOWN")
        root_causes[rc] = root_causes.get(rc, 0) + 1

    # Real accuracy from ground-truth labels where available
    evaluated = [p for p in processed if p.get("ground_truth_root_cause") is not None]
    evaluated_count = len(evaluated)

    if evaluated_count > 0:
        correct = sum(1 for p in evaluated if p.get("correct") is True)
        accuracy = correct / evaluated_count
        accuracy_basis = "ground_truth"

        # Per-root-cause breakdown
        per_rc: Dict[str, Any] = {}
        for p in evaluated:
            gt = p["ground_truth_root_cause"].upper()
            if gt not in per_rc:
                per_rc[gt] = {"total": 0, "correct": 0, "accuracy": 0.0}
            per_rc[gt]["total"] += 1
            if p.get("correct"):
                per_rc[gt]["correct"] += 1
        for rc_data in per_rc.values():
            rc_data["accuracy"] = rc_data["correct"] / rc_data["total"]
    else:
        # Fall back to confidence proxy — clearly labelled as such
        correct = sum(1 for p in processed if p.get("confidence", 0) > 0.7)
        accuracy = correct / total
        accuracy_basis = "confidence_proxy"
        per_rc = {}

    return MetricsResponse(
        total_processed=total,
        correct_diagnoses=correct,
        accuracy=accuracy,
        accuracy_basis=accuracy_basis,
        evaluated_tickets=evaluated_count,
        auto_resolved=sum(
            1 for p in processed
            if any(k in str(p.get("action_taken", "")).upper() for k in ("RETRY", "RETRIGGER"))
        ),
        escalated=sum(1 for p in processed if "ESCALATE" in str(p.get("action_taken", "")).upper()),
        avg_time=sum(p.get("processing_time", 0) for p in processed) / total,
        root_causes=root_causes,
        per_root_cause_accuracy=per_rc,
        recent_tickets=processed[-10:]
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

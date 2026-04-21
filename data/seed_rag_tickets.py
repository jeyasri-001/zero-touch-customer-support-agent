"""
Seed script: generates 21 resolved ticket JSON files for RAG indexing.
Covers all root cause categories — 3 tickets per category.
Run once: python data/seed_rag_tickets.py
"""

import json
from pathlib import Path

TICKETS_DIR = Path(__file__).parent / "tickets"
TICKETS_DIR.mkdir(exist_ok=True)

SEED_TICKETS = [
    # ── BANK_REJECTION (code 51 — Insufficient Funds) ─────────────────────────
    {
        "key": "NOC-5001",
        "summary": "BKJPS1234A - SIP failed insufficient funds",
        "description": "Customer SIP of Rs 5000 failed. Bank returned rejection.",
        "root_cause": "BANK_REJECTION",
        "resolution": (
            "Investigated transaction TXN20240601000001. Event log showed bank rejection code 51 "
            "(Insufficient Funds). Customer account balance was below SIP amount. "
            "Executed payment retry after customer confirmed funds added. Retry successful."
        ),
        "action_taken": "RETRY_EXECUTED",
        "status": "Done",
    },
    {
        "key": "NOC-5002",
        "summary": "CKTRS5678B - Monthly SIP deduction failed code 51",
        "description": "SIP Rs 2000 for HDFC Flexi Cap failed. Customer asking for reason.",
        "root_cause": "BANK_REJECTION",
        "resolution": (
            "Bank rejection code 51 confirmed via get_bank_rejection_code. "
            "Customer salary credited next day. Payment retried successfully on second attempt."
        ),
        "action_taken": "RETRY_EXECUTED",
        "status": "Done",
    },
    {
        "key": "NOC-5003",
        "summary": "DFGTR9012C - SIP bounce insufficient balance",
        "description": "Two consecutive SIP failures for same customer. Axis ELSS fund.",
        "root_cause": "BANK_REJECTION",
        "resolution": (
            "Bank rejection code 51 on both transactions. Customer notified to maintain "
            "minimum balance before SIP date. Next attempt succeeded."
        ),
        "action_taken": "RETRY_EXECUTED",
        "status": "Done",
    },
    # ── BANK_REJECTION (code 91 — Temp Bank Unavailable) ─────────────────────
    {
        "key": "NOC-5004",
        "summary": "EHJKL3456D - SIP failed bank temporarily unavailable",
        "description": "SIP failed despite sufficient balance. Bank system down.",
        "root_cause": "BANK_REJECTION",
        "resolution": (
            "Bank rejection code 91 (Bank Temporarily Unavailable). "
            "Retried 2 hours later. Transaction processed successfully."
        ),
        "action_taken": "RETRY_EXECUTED",
        "status": "Done",
    },
    {
        "key": "NOC-5005",
        "summary": "FIJKM7890E - Payment failure bank server error",
        "description": "SBI bank server error during SIP processing.",
        "root_cause": "BANK_REJECTION",
        "resolution": (
            "Event logs showed payment_gateway_response ERROR with code 91. "
            "Auto-retry triggered and succeeded after SBI server restored."
        ),
        "action_taken": "RETRY_EXECUTED",
        "status": "Done",
    },
    # ── MANDATE_EXPIRY ────────────────────────────────────────────────────────
    {
        "key": "NOC-5006",
        "summary": "GKLMN2345F - SIP failed mandate expired",
        "description": "Customer's SIP failing for 2 months. Mandate issue.",
        "root_cause": "MANDATE_EXPIRY",
        "resolution": (
            "check_mandate_status confirmed mandate status EXPIRED (expiry date 2024-01-15). "
            "Bank rejection code 54. Customer informed to register new mandate via net banking."
        ),
        "action_taken": "ESCALATE_TO_HUMAN",
        "status": "Done",
    },
    {
        "key": "NOC-5007",
        "summary": "HLMNO6789G - ECS mandate expired SIP not processing",
        "description": "All SIPs stopped. Mandate validation failing.",
        "root_cause": "MANDATE_EXPIRY",
        "resolution": (
            "Mandate expired 3 months ago (code 54). Customer guided to renew mandate "
            "through bank portal. SIPs resumed after new mandate registered."
        ),
        "action_taken": "ESCALATE_TO_HUMAN",
        "status": "Done",
    },
    {
        "key": "NOC-5008",
        "summary": "IMNOP0123H - NACH mandate not active SIP bounce",
        "description": "ICICI bank mandate expired. Customer unable to invest.",
        "root_cause": "MANDATE_EXPIRY",
        "resolution": (
            "Bank rejection code 54 confirmed. Mandate expired 2024-03-01. "
            "Escalated to customer to complete mandate renewal via net banking/UPI."
        ),
        "action_taken": "ESCALATE_TO_HUMAN",
        "status": "Done",
    },
    # ── SIP_PAUSED ────────────────────────────────────────────────────────────
    {
        "key": "NOC-5009",
        "summary": "JNOPQ4567I - SIP not processed for June customer complaint",
        "description": "Customer says June SIP did not process. Balance was sufficient.",
        "root_cause": "SIP_PAUSED",
        "resolution": (
            "check_sip_pause_status revealed SIP was paused via editSystematicPlanSip "
            "(pauseMonth:1) by ops team on customer request received 30th May. "
            "SIP retriggered and processed for next cycle."
        ),
        "action_taken": "RETRIGGER_EXECUTED",
        "status": "Done",
    },
    {
        "key": "NOC-5010",
        "summary": "KOPQR8901J - Two SIPs skipped Axis ELSS fund",
        "description": "Investor asking why SIP skipped for 2 months in a row.",
        "root_cause": "SIP_PAUSED",
        "resolution": (
            "Event logs showed sip_submission_skipped for both months. "
            "check_sip_pause_status confirmed pause was set by ops team. "
            "SIP retriggered successfully after customer confirmed resumption."
        ),
        "action_taken": "RETRIGGER_EXECUTED",
        "status": "Done",
    },
    {
        "key": "NOC-5011",
        "summary": "LPQRS2345K - SIP paused by system customer unaware",
        "description": "Customer did not request pause but SIP stopped processing.",
        "root_cause": "SIP_PAUSED",
        "resolution": (
            "System auto-paused SIP due to 3 consecutive failures as per policy. "
            "check_sip_pause_status confirmed retrigger_eligible: true. "
            "SIP retriggered after customer updated bank balance."
        ),
        "action_taken": "RETRIGGER_EXECUTED",
        "status": "Done",
    },
    # ── ACCOUNT_VALIDATION_ERROR ──────────────────────────────────────────────
    {
        "key": "NOC-5012",
        "summary": "MQRST6789L - Mandate activation failing invalid account",
        "description": "Customer unable to activate mandate. Error: Invalid Account No.",
        "root_cause": "ACCOUNT_VALIDATION_ERROR",
        "resolution": (
            "check_account_validation_history showed Axis Bank account number mismatch: "
            "expected 15-16 digits, received 10. Axis Bank requires leading zeros. "
            "Data team fixed account number by padding with leading zeros."
        ),
        "action_taken": "ESCALATE_TO_HUMAN",
        "status": "Done",
    },
    {
        "key": "NOC-5013",
        "summary": "NRSTU0123M - UPI mandate error account number mismatch",
        "description": "Mandate registration via net banking and UPI both failing.",
        "root_cause": "ACCOUNT_VALIDATION_ERROR",
        "resolution": (
            "Validation error: account number captured with 12 digits, "
            "Kotak Mahindra Bank requires 16 digits. Corrected in system after "
            "customer provided full account number via WhatsApp."
        ),
        "action_taken": "ESCALATE_TO_HUMAN",
        "status": "Done",
    },
    {
        "key": "NOC-5014",
        "summary": "OSTUV4567N - HDFC mandate invalid account number error",
        "description": "New customer cannot complete mandate. Account validation failing.",
        "root_cause": "ACCOUNT_VALIDATION_ERROR",
        "resolution": (
            "check_account_validation_history: HDFC account number had leading zeros "
            "stripped during data entry. Corrected to 16-digit format. Mandate activated."
        ),
        "action_taken": "ESCALATE_TO_HUMAN",
        "status": "Done",
    },
    # ── AMC_DELAY ─────────────────────────────────────────────────────────────
    {
        "key": "NOC-5015",
        "summary": "PTUVW8901O - SIP deducted but units not allocated",
        "description": "Money deducted from bank 3 days ago. No units shown in portfolio.",
        "root_cause": "AMC_DELAY",
        "resolution": (
            "check_amc_processing_status confirmed: bank debit successful, NAV allocation "
            "pending at AMC due to month-end high volume. Units allocated within 48 hours. "
            "Customer notified to wait."
        ),
        "action_taken": "WAIT_FOR_AMC",
        "status": "Done",
    },
    {
        "key": "NOC-5016",
        "summary": "QUVWX2345P - Payment processed portfolio not updated",
        "description": "SIP amount debited. BSE StAR MF showing pending status.",
        "root_cause": "AMC_DELAY",
        "resolution": (
            "AMC processing delayed due to BSE StAR MF platform intermittent issue. "
            "check_amc_processing_status showed delay of 18 hours beyond SLA. "
            "Resolved automatically once platform restored."
        ),
        "action_taken": "WAIT_FOR_AMC",
        "status": "Done",
    },
    {
        "key": "NOC-5017",
        "summary": "RVWXY6789Q - NAV not updated after successful payment",
        "description": "Customer panicking — money gone but investment not showing.",
        "root_cause": "AMC_DELAY",
        "resolution": (
            "AMC system maintenance window caused 24-hour delay in NAV allocation. "
            "Payment_received: true, nav_allocated: false in AMC status. "
            "Customer reassured. Units reflected after maintenance window."
        ),
        "action_taken": "WAIT_FOR_AMC",
        "status": "Done",
    },
    # ── SYSTEM_ERROR ──────────────────────────────────────────────────────────
    {
        "key": "NOC-5018",
        "summary": "SWXYZ0123R - Transaction stuck in processing state",
        "description": "Transaction showing processing for 5 days. Not failed not success.",
        "root_cause": "SYSTEM_ERROR",
        "resolution": (
            "Internal processing queue stuck. Event logs showed transaction_settlement "
            "never received response. Engineering team cleared the queue manually. "
            "Transaction reprocessed successfully."
        ),
        "action_taken": "ESCALATE_TO_HUMAN",
        "status": "Done",
    },
    {
        "key": "NOC-5019",
        "summary": "TXYZA4567S - Duplicate SIP deduction same month",
        "description": "SIP deducted twice in same month. Customer requesting refund.",
        "root_cause": "SYSTEM_ERROR",
        "resolution": (
            "Duplicate transaction detected in event logs — race condition in SIP scheduler. "
            "Second deduction reversed by ops team. Customer refunded within 3 working days."
        ),
        "action_taken": "ESCALATE_TO_HUMAN",
        "status": "Done",
    },
    {
        "key": "NOC-5020",
        "summary": "UYZAB8901T - SIP amount wrong different from registered amount",
        "description": "SIP of Rs 10000 deducted instead of Rs 5000.",
        "root_cause": "SYSTEM_ERROR",
        "resolution": (
            "System error caused incorrect amount field mapping in SIP instruction. "
            "Transaction reversed. SIP amount corrected in system to Rs 5000. "
            "Escalated to engineering for root fix."
        ),
        "action_taken": "ESCALATE_TO_HUMAN",
        "status": "Done",
    },
    # ── UNKNOWN / edge case ───────────────────────────────────────────────────
    {
        "key": "NOC-5021",
        "summary": "VZABC2345U - Customer reports SIP issue no further details",
        "description": "Customer called saying SIP is not working. No transaction ID provided.",
        "root_cause": "UNKNOWN",
        "resolution": (
            "Insufficient information to diagnose. No transaction found for reported date. "
            "Customer contacted for more details — PAN and transaction reference requested. "
            "Escalated for follow-up."
        ),
        "action_taken": "ESCALATE_TO_HUMAN",
        "status": "Done",
    },
]


def make_ticket_json(t: dict) -> dict:
    return {
        "ticket": {
            "key": t["key"],
            "fields": {
                "summary": t["summary"],
                "description": t["description"],
                "status": {"name": t["status"]},
                "attachment": [],
            }
        },
        "analysis": {
            "key": t["key"],
            "summary": t["summary"],
            "description": t["description"],
            "status": t["status"],
            "root_cause": t["root_cause"],
            "action_taken": t["action_taken"],
        },
        "comments": {
            "total": 1,
            "comments": [
                {
                    "id": f"comment_{t['key']}",
                    "body": t["resolution"],
                    "author": "support-agent@fundsindia.com",
                }
            ]
        }
    }


if __name__ == "__main__":
    written = 0
    for t in SEED_TICKETS:
        path = TICKETS_DIR / f"{t['key']}.json"
        if not path.exists():
            path.write_text(json.dumps(make_ticket_json(t), indent=2))
            print(f"  ✅ Written {path.name}")
            written += 1
        else:
            print(f"  ⏭️  Skipped {path.name} (already exists)")
    print(f"\nDone. {written} new seed tickets written to {TICKETS_DIR}")

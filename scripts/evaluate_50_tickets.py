#!/usr/bin/env python3
"""
Batch evaluation script — processes all 50 labelled tickets and reports
real accuracy (ground_truth_root_cause vs agent prediction).

Usage:
    python3 scripts/evaluate_50_tickets.py [--api http://localhost:8000] [--delay 5]

Options:
    --api         Base URL of the running FastAPI server  (default: http://localhost:8000)
    --delay       Seconds between tickets to avoid rate limits (default: 5 paid / 90 free)
    --update-jira Pass update_jira=true for every ticket (default: false — safe for demos)
    --jira-keys   Comma-separated ticket keys to update Jira for (e.g. NOC-5001,NOC-5002)
    --dry-run     Print ticket list without calling API
    --report-only Generate HTML report from last evaluation_results.json without re-running
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent
TICKETS_DIR = ROOT / "data" / "tickets"
API_DEFAULT = "http://localhost:8000"


def load_tickets() -> list[dict]:
    """Read all JSON files in data/tickets/ and return sorted list."""
    tickets = []
    for path in sorted(TICKETS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
            analysis = data.get("analysis", {})
            fields = data.get("ticket", {}).get("fields", {})
            tickets.append({
                "ticket_key": analysis.get("key") or data["ticket"]["key"],
                "summary": analysis.get("summary") or fields.get("summary", ""),
                "description": analysis.get("description") or fields.get("description", ""),
                "customer_id": _extract_pan(
                    analysis.get("summary", "") + " " + analysis.get("description", "")
                ),
                "status": analysis.get("status", "Done"),
                "ground_truth_root_cause": analysis.get("root_cause", "UNKNOWN"),
            })
        except Exception as e:
            print(f"  ⚠️  Could not parse {path.name}: {e}")
    return tickets


def _extract_pan(text: str) -> str | None:
    import re
    m = re.search(r"\b([A-Z]{5}\d{4}[A-Z])\b", text)
    return m.group(1) if m else None


def check_api(base_url: str) -> bool:
    try:
        r = requests.get(f"{base_url}/health", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def reset_metrics(base_url: str):
    try:
        requests.post(f"{base_url}/api/metrics/reset", timeout=5)
    except Exception:
        pass


def process_ticket(base_url: str, ticket: dict, update_jira: bool = False) -> dict | None:
    payload = {
        "ticket_key": ticket["ticket_key"],
        "summary": ticket["summary"],
        "description": ticket["description"],
        "customer_id": ticket.get("customer_id"),
        "status": ticket.get("status", "Open"),
        "ground_truth_root_cause": ticket["ground_truth_root_cause"],
    }
    try:
        r = requests.post(
            f"{base_url}/api/process-ticket?update_jira={'true' if update_jira else 'false'}",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=120,
        )
        if r.status_code == 200:
            return r.json()
        print(f"    ❌ HTTP {r.status_code}: {r.text[:200]}")
        return None
    except Exception as e:
        print(f"    ❌ Exception: {e}")
        return None


def fetch_metrics(base_url: str) -> dict | None:
    try:
        r = requests.get(f"{base_url}/api/metrics", timeout=10)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def print_summary(results: list[dict], metrics: dict | None):
    total = len(results)
    successful = [r for r in results if r.get("result")]
    failed = total - len(successful)

    correct = sum(
        1 for r in successful
        if r["result"]["root_cause"].upper() == r["ground_truth"].upper()
    )
    accuracy = correct / len(successful) if successful else 0.0

    auto_resolved = sum(
        1 for r in successful
        if any(k in r["result"].get("action_taken", "").upper() for k in ("RETRY", "RETRIGGER"))
    )
    escalated = sum(
        1 for r in successful
        if "ESCALATE" in r["result"].get("action_taken", "").upper()
    )

    # Per-category breakdown
    cats: dict[str, dict] = {}
    for r in successful:
        gt = r["ground_truth"].upper()
        pred = r["result"]["root_cause"].upper()
        if gt not in cats:
            cats[gt] = {"total": 0, "correct": 0}
        cats[gt]["total"] += 1
        if pred == gt:
            cats[gt]["correct"] += 1

    print("\n" + "=" * 65)
    print("  EVALUATION RESULTS — Zero-Touch Support Agent")
    print("=" * 65)
    print(f"  Tickets processed : {len(successful)} / {total}  (failed: {failed})")
    print(f"  Correct diagnoses : {correct} / {len(successful)}")
    print(f"  Accuracy          : {accuracy:.1%}   (target ≥ 60%)")
    target_met = "✅ PASS" if accuracy >= 0.60 else "❌ FAIL"
    print(f"  Target met        : {target_met}")
    print(f"  Auto-resolved     : {auto_resolved}  (retry / retrigger)")
    print(f"  Escalated         : {escalated}")
    print()
    print("  Per-category accuracy:")
    for cat, v in sorted(cats.items()):
        bar = "█" * v["correct"] + "░" * (v["total"] - v["correct"])
        pct = v["correct"] / v["total"] if v["total"] else 0
        print(f"    {cat:<28} {v['correct']:>2}/{v['total']:<2}  {pct:.0%}  {bar}")

    print()
    print("  Misdiagnosed tickets:")
    any_wrong = False
    for r in successful:
        gt = r["ground_truth"].upper()
        pred = r["result"]["root_cause"].upper()
        if pred != gt:
            any_wrong = True
            conf = r["result"].get("confidence", 0)
            print(f"    {r['ticket_key']:<12} gt={gt:<28} pred={pred}  conf={conf:.0%}")
    if not any_wrong:
        print("    (none)")

    print("=" * 65)

    # Save full results
    out_path = ROOT / "evaluation_results.json"
    payload = {
        "summary": {
            "total": total,
            "successful": len(successful),
            "correct": correct,
            "accuracy": round(accuracy, 4),
            "target_met": accuracy >= 0.60,
            "auto_resolved": auto_resolved,
            "escalated": escalated,
        },
        "per_category": {
            k: {"total": v["total"], "correct": v["correct"],
                "accuracy": round(v["correct"] / v["total"], 4) if v["total"] else 0}
            for k, v in cats.items()
        },
        "tickets": [
            {
                "ticket_key": r["ticket_key"],
                "ground_truth": r["ground_truth"],
                "predicted": r["result"]["root_cause"] if r.get("result") else None,
                "correct": (r["result"]["root_cause"].upper() == r["ground_truth"].upper())
                           if r.get("result") else False,
                "confidence": r["result"].get("confidence") if r.get("result") else None,
                "action_taken": r["result"].get("action_taken") if r.get("result") else None,
                "status": r["result"].get("status") if r.get("result") else "ERROR",
                "customer_response": r["result"].get("customer_response") if r.get("result") else None,
            }
            for r in results
        ],
    }
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"\n  Full results saved → {out_path.relative_to(ROOT)}")


def generate_html_report(results_path: Path) -> Path:
    """Generate a self-contained HTML report from evaluation_results.json."""
    data = json.loads(results_path.read_text())
    s = data["summary"]
    cats = data["per_category"]
    tickets = data["tickets"]

    accuracy_pct = f"{s['accuracy']:.1%}"
    target_color = "#22c55e" if s["target_met"] else "#ef4444"
    target_label = "PASS ✅" if s["target_met"] else "FAIL ❌"

    cat_rows = ""
    for cat, v in sorted(cats.items()):
        pct = v["accuracy"]
        bar_w = int(pct * 100)
        bar_color = "#22c55e" if pct >= 0.6 else "#f59e0b" if pct >= 0.4 else "#ef4444"
        cat_rows += f"""
        <tr>
          <td>{cat}</td>
          <td>{v['correct']}/{v['total']}</td>
          <td>
            <div style="background:#e5e7eb;border-radius:4px;height:14px;width:160px">
              <div style="background:{bar_color};width:{bar_w}%;height:14px;border-radius:4px"></div>
            </div>
          </td>
          <td><b>{pct:.0%}</b></td>
        </tr>"""

    ticket_rows = ""
    for t in tickets:
        correct = t.get("correct", False)
        icon = "✅" if correct else "❌"
        row_bg = "#f0fdf4" if correct else "#fff7f7"
        conf = f"{t['confidence']:.0%}" if t.get("confidence") is not None else "—"
        response = (t.get("customer_response") or "—")[:120] + ("…" if len(t.get("customer_response") or "") > 120 else "")
        ticket_rows += f"""
        <tr style="background:{row_bg}">
          <td>{icon}</td>
          <td><b>{t['ticket_key']}</b></td>
          <td>{t['ground_truth']}</td>
          <td>{t.get('predicted') or '—'}</td>
          <td>{conf}</td>
          <td>{t.get('action_taken') or '—'}</td>
          <td style="font-size:12px;color:#555">{response}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Zero-Touch Agent — Evaluation Report</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; background: #f8fafc; color: #1e293b; }}
  .header {{ background: linear-gradient(135deg,#1e293b,#334155); color: white; padding: 32px 40px; }}
  .header h1 {{ margin: 0 0 4px; font-size: 24px; }}
  .header p {{ margin: 0; opacity: .7; font-size: 14px; }}
  .body {{ padding: 32px 40px; }}
  .cards {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 32px; }}
  .card {{ background: white; border-radius: 10px; padding: 20px 24px; box-shadow: 0 1px 4px rgba(0,0,0,.08); min-width: 140px; }}
  .card .val {{ font-size: 32px; font-weight: 700; }}
  .card .lbl {{ font-size: 13px; color: #64748b; margin-top: 2px; }}
  .section {{ background: white; border-radius: 10px; padding: 24px; box-shadow: 0 1px 4px rgba(0,0,0,.08); margin-bottom: 24px; }}
  .section h2 {{ margin: 0 0 16px; font-size: 16px; color: #334155; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  th {{ text-align: left; padding: 8px 12px; background: #f1f5f9; color: #475569; font-weight: 600; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #f1f5f9; vertical-align: top; }}
  tr:last-child td {{ border-bottom: none; }}
</style>
</head>
<body>
<div class="header">
  <h1>Zero-Touch Customer Support Agent</h1>
  <p>Evaluation Report — {len(tickets)} tickets &nbsp;|&nbsp; Generated {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
</div>
<div class="body">
  <div class="cards">
    <div class="card">
      <div class="val">{len(tickets)}</div>
      <div class="lbl">Tickets processed</div>
    </div>
    <div class="card">
      <div class="val" style="color:{target_color}">{accuracy_pct}</div>
      <div class="lbl">Accuracy &nbsp;<span style="font-size:12px;background:{target_color};color:white;padding:2px 6px;border-radius:4px">{target_label}</span></div>
    </div>
    <div class="card">
      <div class="val" style="color:#22c55e">{s['auto_resolved']}</div>
      <div class="lbl">Auto-resolved</div>
    </div>
    <div class="card">
      <div class="val" style="color:#f59e0b">{s['escalated']}</div>
      <div class="lbl">Escalated to human</div>
    </div>
    <div class="card">
      <div class="val">{s['correct']}/{len(tickets)}</div>
      <div class="lbl">Correct diagnoses</div>
    </div>
  </div>

  <div class="section">
    <h2>Accuracy by Root Cause Category</h2>
    <table>
      <tr><th>Category</th><th>Correct</th><th>Bar</th><th>Accuracy</th></tr>
      {cat_rows}
    </table>
  </div>

  <div class="section">
    <h2>Per-Ticket Results</h2>
    <table>
      <tr><th></th><th>Ticket</th><th>Ground Truth</th><th>Predicted</th><th>Confidence</th><th>Action Taken</th><th>Customer Response</th></tr>
      {ticket_rows}
    </table>
  </div>
</div>
</body>
</html>"""

    out = results_path.parent / "evaluation_report.html"
    out.write_text(html)
    return out


def main():
    parser = argparse.ArgumentParser(description="Evaluate agent on 50 labelled tickets")
    parser.add_argument("--api", default=API_DEFAULT, help="FastAPI base URL")
    parser.add_argument(
        "--delay",
        type=int,
        default=int(os.getenv("GROQ_BATCH_DELAY", "5")),
        help="Seconds between tickets (default: $GROQ_BATCH_DELAY or 5)",
    )
    parser.add_argument("--update-jira", action="store_true",
                        help="Update Jira for ALL tickets (default: false)")
    parser.add_argument("--jira-keys", default="",
                        help="Comma-separated keys to update Jira for (e.g. NOC-5001,NOC-5029)")
    parser.add_argument("--dry-run", action="store_true", help="List tickets without calling API")
    parser.add_argument("--report-only", action="store_true",
                        help="Generate HTML report from existing evaluation_results.json")
    args = parser.parse_args()

    jira_keys_set = {k.strip().upper() for k in args.jira_keys.split(",") if k.strip()}

    if args.report_only:
        results_path = ROOT / "evaluation_results.json"
        if not results_path.exists():
            print("❌ evaluation_results.json not found. Run without --report-only first.")
            sys.exit(1)
        out = generate_html_report(results_path)
        print(f"✅ Report generated → {out}")
        return

    tickets = load_tickets()
    print(f"📋 Loaded {len(tickets)} tickets from {TICKETS_DIR.relative_to(ROOT)}")

    if args.dry_run:
        for t in tickets:
            print(f"  {t['ticket_key']:<12} gt={t['ground_truth_root_cause']}")
        return

    print(f"🔌 Checking API at {args.api} …")
    if not check_api(args.api):
        print(f"❌ API not reachable. Start the server first:\n   python3 start_server.py")
        sys.exit(1)
    print("✅ API online\n")

    jira_mode = "ALL" if args.update_jira else (f"only {jira_keys_set}" if jira_keys_set else "NONE")
    print(f"📝 Jira updates: {jira_mode}")
    reset_metrics(args.api)
    print(f"🚀 Processing {len(tickets)} tickets  (delay={args.delay}s between each)\n")

    results = []
    for i, ticket in enumerate(tickets):
        gt = ticket["ground_truth_root_cause"]
        key = ticket["ticket_key"]
        update_jira = args.update_jira or (key in jira_keys_set)
        jira_tag = " [+jira]" if update_jira else ""
        print(f"  [{i+1:>2}/{len(tickets)}] {key:<12}  gt={gt}{jira_tag}")

        result = process_ticket(args.api, ticket, update_jira=update_jira)
        if result:
            pred = result.get("root_cause", "?")
            conf = result.get("confidence", 0)
            ok = "✅" if pred.upper() == gt.upper() else "❌"
            print(f"          {ok} pred={pred}  conf={conf:.0%}  action={result.get('action_taken','?')}")
        else:
            print(f"          ⚠️  No result")

        results.append({
            "ticket_key": key,
            "ground_truth": gt,
            "result": result,
        })

        if i < len(tickets) - 1:
            time.sleep(args.delay)

    metrics = fetch_metrics(args.api)
    print_summary(results, metrics)

    # Auto-generate HTML report
    results_path = ROOT / "evaluation_results.json"
    if results_path.exists():
        out = generate_html_report(results_path)
        print(f"  HTML report  → {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

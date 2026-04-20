#!/usr/bin/env python3
"""
Zero-Touch Agent Dashboard - Key-only Flow
Enter a Jira ticket key (e.g. NOC-21854) -> agent fetches -> diagnoses -> updates Jira.
"""

import os
import streamlit as st
import requests
import pandas as pd
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

DEFAULT_API_URL = os.getenv("API_URL", "http://localhost:8000")

# ==============================================================
# PAGE CONFIG
# ==============================================================
st.set_page_config(
    page_title="Zero-Touch Agent",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ==============================================================
# STYLES
# ==============================================================
st.markdown(
    """
<style>
/* Hero */
.hero {
    background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 50%, #4f46e5 100%);
    color: white;
    padding: 36px 40px;
    border-radius: 16px;
    margin-bottom: 22px;
    box-shadow: 0 10px 30px rgba(30, 58, 138, 0.25);
}
.hero h1 { margin: 0; font-size: 2.2rem; font-weight: 700; }
.hero p  { margin: 6px 0 0 0; opacity: 0.9; font-size: 1.05rem; }
.hero .pill {
    display: inline-block; padding: 4px 12px; margin-right: 8px; margin-top: 12px;
    background: rgba(255,255,255,0.15); border-radius: 999px;
    font-size: 0.78rem; font-weight: 600; letter-spacing: 0.3px;
}

/* Stage cards */
.stage {
    border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px 18px;
    margin: 8px 0; background: #ffffff;
}
.stage.active { border-color: #4f46e5; box-shadow: 0 6px 18px rgba(79, 70, 229, 0.12); }
.stage.done   { border-color: #16a34a; background: #f0fdf4; }
.stage.err    { border-color: #dc2626; background: #fef2f2; }
.stage h4 { margin: 0; font-size: 1rem; }
.stage .sub { font-size: 0.85rem; color: #475569; margin-top: 4px; }

/* KPI tiles */
.kpi {
    background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
    border: 1px solid #e2e8f0; border-radius: 12px;
    padding: 18px; text-align: center;
}
.kpi .label { font-size: 0.8rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; }
.kpi .value { font-size: 1.8rem; font-weight: 700; color: #0f172a; margin-top: 6px; }
.kpi .delta { font-size: 0.8rem; margin-top: 4px; }

/* Pretty blocks — force dark text so they're readable on dark themes too */
.block-diagnosis {
    background: #eef2ff; border-left: 5px solid #4f46e5;
    padding: 16px 18px; border-radius: 10px; margin: 10px 0;
    color: #1e1b4b !important; font-size: 0.98rem; line-height: 1.5;
}
.block-diagnosis * { color: #1e1b4b !important; }
.block-customer {
    background: #fffbeb; border-left: 5px solid #f59e0b;
    padding: 16px 18px; border-radius: 10px; margin: 10px 0;
    color: #78350f !important; font-size: 0.98rem; line-height: 1.5;
}
.block-customer * { color: #78350f !important; }
.block-jira {
    background: #f1f5f9; border-left: 5px solid #64748b;
    padding: 14px 18px; border-radius: 10px; margin: 10px 0;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.88rem;
    color: #1e293b !important;
}
.block-jira * { color: #1e293b !important; }

/* History card */
.history-card {
    background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px;
    padding: 14px 16px; margin: 8px 0; color: #0f172a !important;
}
.history-card * { color: #0f172a !important; }
.history-card .hk { font-weight: 700; font-size: 1.05rem; }
.history-card .hsum { color: #475569 !important; font-size: 0.88rem; margin-top: 2px; }

/* Badges */
.badge {
    display: inline-block; padding: 4px 10px; border-radius: 999px;
    font-size: 0.78rem; font-weight: 600; margin-right: 6px;
}
.b-ok   { background: #dcfce7; color: #166534; }
.b-warn { background: #fef3c7; color: #92400e; }
.b-err  { background: #fee2e2; color: #991b1b; }
.b-info { background: #dbeafe; color: #1e40af; }

/* Tool call pill */
.tool-pill {
    display: inline-block; padding: 6px 10px; margin: 3px 4px 3px 0;
    background: #eef2ff; border: 1px solid #c7d2fe; border-radius: 8px;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.82rem; color: #3730a3;
}
</style>
""",
    unsafe_allow_html=True,
)

# ==============================================================
# HERO
# ==============================================================
st.markdown(
    """
<div class="hero">
  <h1>🤖 Zero-Touch Customer Support Agent</h1>
  <p>Enter a Jira ticket key &mdash; the AI agent fetches it, investigates with 9 tools, diagnoses the root cause, and updates Jira automatically.</p>
  <div>
    <span class="pill">⚡ Groq Llama 3.3 70B</span>
    <span class="pill">🔗 LangChain</span>
    <span class="pill">📚 RAG · ChromaDB</span>
    <span class="pill">✅ Validation Layer</span>
    <span class="pill">🎫 Jira Auto-Update</span>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

# ==============================================================
# SIDEBAR
# ==============================================================
API_URL = st.sidebar.text_input("API URL", DEFAULT_API_URL)


def check_health():
    try:
        r = requests.get(f"{API_URL}/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


api_ok = check_health()

st.sidebar.markdown("### 🔧 System Status")
st.sidebar.markdown(
    f"""
<span class="badge {'b-ok' if api_ok else 'b-err'}">{'🟢' if api_ok else '🔴'} API {'Online' if api_ok else 'Offline'}</span><br>
<span class="badge b-ok">🟢 Groq Llama 3.3 70B</span><br>
<span class="badge b-ok">🟢 LangChain Agent</span><br>
<span class="badge b-ok">🟢 LangSmith Tracing</span><br>
<span class="badge b-ok">🟢 ChromaDB RAG</span><br>
<span class="badge b-ok">🟢 Jira Integration</span>
""",
    unsafe_allow_html=True,
)

st.sidebar.markdown("---")
st.sidebar.markdown("### 🔗 Quick Links")
st.sidebar.markdown("[📊 LangSmith Traces](https://smith.langchain.com/)")
st.sidebar.markdown(f"[📚 API Docs]({API_URL}/docs)")
st.sidebar.markdown("[🎫 Jira Board](https://fundsindia.atlassian.net/)")

st.sidebar.markdown("---")
if st.sidebar.button("🗑️ Reset Metrics", use_container_width=True):
    try:
        requests.post(f"{API_URL}/api/metrics/reset")
        st.sidebar.success("Metrics reset!")
        st.rerun()
    except Exception as e:
        st.sidebar.error(f"Reset failed: {e}")

# ==============================================================
# TABS
# ==============================================================
tab_run, tab_overview = st.tabs(["🚀 Run Agent", "📊 Overview"])

# --------------------------------------------------------------
# TAB 1 — RUN AGENT (key-only input)
# --------------------------------------------------------------
with tab_run:
    st.markdown("### 🎯 Enter a Jira Ticket Key")
    st.caption("Format: `PROJECT-NUMBER` — single or multiple (comma/space separated). Tickets process **in parallel**. Max 50 per batch.")

    col_inp, col_btn = st.columns([4, 1])
    with col_inp:
        ticket_key = st.text_input(
            "Ticket Key",
            value=st.session_state.get("ticket_key", "NOC-21854"),
            placeholder="NOC-21854",
            label_visibility="collapsed",
        )
    with col_btn:
        run_clicked = st.button("🚀 Run Agent", type="primary", use_container_width=True)

    # Quick-select chips — seed examples (any PROJECT-NUMBER is accepted)
    QUICK_KEYS = ["NOC-21854", "NOC-1346", "NOC-11734"]
    st.markdown("**Quick examples:**")
    c1, c2, c3, c4 = st.columns(4)
    for c, k in zip([c1, c2, c3], QUICK_KEYS):
        with c:
            if st.button(k, use_container_width=True, key=f"qs_{k}"):
                st.session_state["ticket_key"] = k
                st.rerun()
    with c4:
        if st.button("🧪 All 3 (parallel)", use_container_width=True, key="qs_all"):
            st.session_state["ticket_key"] = ", ".join(QUICK_KEYS)
            st.rerun()

    update_jira = st.checkbox("📝 Update Jira ticket with diagnosis + customer response", value=True)

    st.markdown("---")

    # Parse one or more keys (comma / space / newline separated) — accept any PROJECT-NUMBER
    raw = (ticket_key or "").upper()
    requested_keys = [k.strip() for k in re.split(r"[,\s]+", raw) if k.strip()]
    requested_keys = list(dict.fromkeys(requested_keys))  # dedupe, preserve order
    bad_format = [k for k in requested_keys if not re.match(r"^[A-Z]+-\d+$", k)]

    MAX_BATCH = 50
    MAX_PARALLEL = 5  # concurrent API calls — respects Groq TPM

    if run_clicked:
        if not requested_keys:
            st.error("❌ Please enter at least one ticket key.")
        elif bad_format:
            st.error(f"❌ Invalid format: {', '.join(bad_format)}. Use `PROJECT-NUMBER` (e.g. `NOC-21854`).")
        elif len(requested_keys) > MAX_BATCH:
            st.error(f"❌ Too many tickets ({len(requested_keys)}). Max {MAX_BATCH} per batch.")
        else:
            if "history" not in st.session_state:
                st.session_state["history"] = []

            n = len(requested_keys)
            workers = min(MAX_PARALLEL, n)

            # Live progress UI
            overall = st.empty()
            progress = st.progress(0)
            live_grid = st.empty()  # shows status table that updates as tickets complete

            # Per-ticket state tracker
            tracker = {k: {"status": "queued", "elapsed": None, "result": None, "error": None}
                       for k in requested_keys}

            def render_grid():
                rows = []
                for k in requested_keys:
                    t = tracker[k]
                    if t["status"] == "queued":
                        icon, detail = "⏳", "Queued"
                    elif t["status"] == "running":
                        icon, detail = "🔄", "Running…"
                    elif t["status"] == "done":
                        r = t["result"] or {}
                        icon = "✅"
                        detail = (
                            f"{r.get('root_cause','?').replace('_',' ').title()} · "
                            f"{r.get('confidence',0)*100:.0f}% · {r.get('status','?')}"
                        )
                    else:
                        icon, detail = "❌", t["error"] or "Error"
                    elapsed = f"{t['elapsed']:.1f}s" if t["elapsed"] else "—"
                    rows.append({"": icon, "Ticket": k, "Result": detail, "Time": elapsed})
                return pd.DataFrame(rows)

            live_grid.dataframe(render_grid(), hide_index=True, use_container_width=True)
            overall.info(f"🚀 Processing **{n}** ticket(s) in parallel (up to **{workers}** concurrent)…")

            # Worker: fetch preview + run agent for one key
            def run_one(key: str):
                t0 = time.time()
                try:
                    pr = requests.get(f"{API_URL}/api/jira/{key}", timeout=30)
                    if pr.status_code != 200:
                        return {"key": key, "ok": False,
                                "error": f"Jira fetch failed ({pr.status_code})",
                                "elapsed": time.time() - t0}
                    preview = pr.json()

                    resp = requests.post(
                        f"{API_URL}/api/process-by-key/{key}",
                        params={"update_jira": str(update_jira).lower()},
                        timeout=300,
                    )
                    if resp.status_code != 200:
                        return {"key": key, "ok": False,
                                "error": f"API error {resp.status_code}: {resp.text[:120]}",
                                "elapsed": time.time() - t0}
                    return {"key": key, "ok": True, "result": resp.json(),
                            "preview": preview, "elapsed": time.time() - t0}
                except requests.Timeout:
                    return {"key": key, "ok": False, "error": "Timeout (>5 min)",
                            "elapsed": time.time() - t0}
                except Exception as e:
                    return {"key": key, "ok": False, "error": str(e)[:140],
                            "elapsed": time.time() - t0}

            # Mark all as running (they'll start being picked up by pool)
            for k in requested_keys:
                tracker[k]["status"] = "running"
            live_grid.dataframe(render_grid(), hide_index=True, use_container_width=True)

            completed = 0
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(run_one, k): k for k in requested_keys}
                for fut in as_completed(futures):
                    out = fut.result()
                    k = out["key"]
                    tracker[k]["elapsed"] = out["elapsed"]
                    if out["ok"]:
                        tracker[k]["status"] = "done"
                        tracker[k]["result"] = out["result"]
                        # Save to session history for detailed report below
                        st.session_state["history"].append({
                            "ticket_key": k,
                            "summary": out["preview"].get("summary", ""),
                            "timestamp": datetime.now().strftime("%H:%M:%S"),
                            "elapsed": out["elapsed"],
                            "result": out["result"],
                        })
                    else:
                        tracker[k]["status"] = "err"
                        tracker[k]["error"] = out["error"]
                    completed += 1
                    progress.progress(completed / n)
                    live_grid.dataframe(render_grid(), hide_index=True, use_container_width=True)

            ok_count = sum(1 for k in requested_keys if tracker[k]["status"] == "done")
            err_count = n - ok_count
            if err_count == 0:
                overall.success(f"🎉 All {n} ticket(s) processed successfully. See detailed reports below.")
            else:
                overall.warning(f"⚠️ Finished: {ok_count} succeeded, {err_count} failed. See details below.")

    # ==================================================
    # SESSION HISTORY — multiple reports
    # ==================================================
    history = st.session_state.get("history", [])
    if history:
        st.markdown("---")
        colh1, colh2 = st.columns([4, 1])
        with colh1:
            st.markdown(f"### 📚 Session Reports ({len(history)})")
        with colh2:
            if st.button("🗑️ Clear History", use_container_width=True):
                st.session_state["history"] = []
                st.rerun()

        for idx, item in enumerate(reversed(history)):
            r = item["result"]
            conf = r.get("confidence", 0) * 100
            status = r.get("status", "N/A")
            badge = "b-ok" if status == "RESOLVED" else ("b-warn" if status == "ESCALATED" else "b-info")
            with st.expander(
                f"🎫 {item['ticket_key']}  ·  {r.get('root_cause','N/A').replace('_',' ').title()}  ·  "
                f"{conf:.0f}%  ·  {status}  ·  {item['elapsed']:.1f}s  ·  {item['timestamp']}",
                expanded=(idx == 0),
            ):
                st.markdown(
                    f"<div class='history-card'>"
                    f"<div class='hk'>{item['ticket_key']}</div>"
                    f"<div class='hsum'>{item['summary']}</div></div>",
                    unsafe_allow_html=True,
                )
                cc1, cc2, cc3, cc4 = st.columns(4)
                for col, (lbl, val) in zip(
                    [cc1, cc2, cc3, cc4],
                    [
                        ("Root Cause", r.get("root_cause", "N/A").replace("_", " ").title()),
                        ("Confidence", f"{conf:.0f}%"),
                        ("Status", status),
                        ("Action", r.get("action_taken", "N/A").replace("_", " ").title()),
                    ],
                ):
                    with col:
                        st.markdown(
                            f"<div class='kpi'><div class='label'>{lbl}</div>"
                            f"<div class='value' style='font-size:1.2rem'>{val}</div></div>",
                            unsafe_allow_html=True,
                        )
                st.markdown("**🔍 Diagnosis**")
                st.markdown(
                    f"<div class='block-diagnosis'>{r.get('diagnosis','')}</div>",
                    unsafe_allow_html=True,
                )
                st.markdown("**💬 Customer Response**")
                st.markdown(
                    f"<div class='block-customer'>{r.get('customer_response','')}</div>",
                    unsafe_allow_html=True,
                )
                tools = r.get("tool_calls_made", [])
                if tools:
                    st.markdown(f"**🛠️ Tools Called ({len(tools)})**")
                    pills = "".join(
                        f"<span class='tool-pill'>{t.get('tool','?')}</span>" for t in tools
                    )
                    st.markdown(pills, unsafe_allow_html=True)
                with st.expander("Raw JSON"):
                    st.json(r)

# --------------------------------------------------------------
# TAB 2 — OVERVIEW
# --------------------------------------------------------------
with tab_overview:
    try:
        metrics = requests.get(f"{API_URL}/api/metrics", timeout=10).json()
    except Exception as e:
        st.error(f"Connection error: {e}")
        metrics = None

    if not metrics or metrics.get("total_processed", 0) == 0:
        st.info("👋 No tickets processed yet. Go to **🚀 Run Agent** and submit a ticket key.")
    else:
        st.markdown("### 📊 Key Performance Indicators")
        c1, c2, c3, c4 = st.columns(4)
        acc = metrics.get("accuracy", 0) * 100

        def tile(col, label, value, delta=""):
            with col:
                st.markdown(
                    f"<div class='kpi'><div class='label'>{label}</div>"
                    f"<div class='value'>{value}</div>"
                    f"<div class='delta'>{delta}</div></div>",
                    unsafe_allow_html=True,
                )

        tile(c1, "Tickets Processed", metrics.get("total_processed", 0))
        tile(c2, "Accuracy", f"{acc:.1f}%", "✅ Above target" if acc > 60 else "⚠️ Below target")
        tile(c3, "Auto-Resolved", metrics.get("auto_resolved", 0))
        tile(c4, "Avg Time", f"{metrics.get('avg_time', 0):.1f}s")

        st.markdown("---")

        # Root-cause distribution
        root_causes = metrics.get("root_causes", {})
        if root_causes:
            st.markdown("### 🔍 Root Cause Distribution")
            df = pd.DataFrame(
                [{"Root Cause": k.replace("_", " ").title(), "Count": v}
                 for k, v in sorted(root_causes.items(), key=lambda x: -x[1])]
            )
            col_chart, col_table = st.columns([2, 1])
            with col_chart:
                st.bar_chart(df.set_index("Root Cause"))
            with col_table:
                st.dataframe(df, hide_index=True, use_container_width=True)

        st.markdown("---")
        st.markdown("### 🎫 Recent Tickets")
        recent = metrics.get("recent_tickets", [])
        if recent:
            dfr = pd.DataFrame(
                [{
                    "Ticket": t.get("ticket_key", "N/A"),
                    "Root Cause": t.get("root_cause", "N/A").replace("_", " ").title(),
                    "Confidence": f"{t.get('confidence', 0)*100:.0f}%",
                    "Status": t.get("status", "N/A"),
                    "Action": t.get("action_taken", "N/A").replace("_", " ").title(),
                    "Time (s)": f"{t.get('processing_time', 0):.1f}",
                } for t in reversed(recent[-15:])]
            )
            st.dataframe(dfr, hide_index=True, use_container_width=True)

        st.caption(f"🔄 Last updated: {datetime.now().strftime('%H:%M:%S')}")

"""Campus Customs backend: the FastAPI routes the dashboard calls.

Agents only prepare payments. Money moves only when the owner calls
POST /api/approvals/{id}/approve, which re-checks the record and the cash first.

Run from backend/:
    ../.venv/bin/uvicorn main:app --reload --port 8000
"""

import asyncio
import calendar
import importlib.util
import json
import os
import shutil
import sqlite3
import uuid
from contextlib import closing
from datetime import date, datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import team
from audit import append_audit
from core import ROOT, said

ORIGINAL_DB = ROOT / "data" / "campus_customs.db"
# Same override as the MCP server, so tests can point both at a scratch copy.
WORKING_DB = os.getenv("CAMPUS_DB_PATH") or str(ROOT / "data" / "campus_customs_new.db")
OWNER = "owner (dashboard approval)"
CASH_ACCOUNT = "checking"

# The MCP server's log tables (customer_emails, inventory_changes), loaded from its own file.
_spec = importlib.util.spec_from_file_location("campus_mcp_server", ROOT / "mcp_server" / "server.py")
_server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_server)

APP_TABLES = """
CREATE TABLE IF NOT EXISTS agent_runs (
    run_id TEXT PRIMARY KEY,
    ticket_id INTEGER,
    stop_reason TEXT NOT NULL,
    stop_detail TEXT,
    message TEXT,
    decision TEXT,
    agents_used TEXT,
    agent_reports TEXT,
    tool_calls TEXT,
    loop_steps INTEGER,
    seconds REAL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    ticket_id INTEGER,
    kind TEXT NOT NULL,
    ref_id INTEGER,
    payee TEXT NOT NULL,
    amount REAL NOT NULL,
    reference TEXT,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    decided_by TEXT,
    decided_at TEXT,
    payment_id INTEGER,
    created_at TEXT NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(WORKING_DB)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_tables() -> None:
    with closing(connect()) as conn:
        conn.executescript(_server.LOG_TABLES + APP_TABLES)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def shop_date(conn: sqlite3.Connection) -> date:
    return date.fromisoformat(conn.execute("SELECT date_today FROM desk LIMIT 1").fetchone()[0])


def add_month(d: date) -> date:
    year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return d.replace(year=year, month=month, day=min(d.day, calendar.monthrange(year, month)[1]))


def checking_balance(conn: sqlite3.Connection) -> dict:
    row = conn.execute("SELECT name, balance, date FROM cash_accounts WHERE name = ?", (CASH_ACCOUNT,)).fetchone()
    if row is None:
        raise HTTPException(404, "No checking account in cash_accounts.")
    return dict(row)


def maybe_resolve(conn: sqlite3.Connection, ticket_id: int | None) -> None:
    """A ticket is resolved once its latest run completed and nothing waits on the owner."""
    if ticket_id is None:
        return
    last = conn.execute("SELECT stop_reason FROM agent_runs WHERE ticket_id = ? ORDER BY created_at DESC LIMIT 1",
                        (ticket_id,)).fetchone()
    pending = conn.execute("SELECT COUNT(*) FROM approvals WHERE ticket_id = ? AND status = 'pending'",
                           (ticket_id,)).fetchone()[0]
    if last and last["stop_reason"] == "completed" and pending == 0:
        conn.execute("UPDATE tickets SET status = 'resolved' WHERE id = ?", (ticket_id,))
    elif pending > 0:
        # A new run queued a payment, so the ticket is open again until the owner decides.
        conn.execute("UPDATE tickets SET status = 'open' WHERE id = ?", (ticket_id,))


app = FastAPI(title="Campus Customs agent backend")
app.add_middleware(
    CORSMiddleware,
    # The Vite board (http://localhost:5173), plus any other local port in case Vite moves.
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)
ensure_tables()


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "database": os.path.basename(WORKING_DB)}


# 1) Tickets with open/resolved status --------------------------------------------------------------

@app.get("/api/tickets")
def list_tickets() -> list[dict]:
    """Every ticket, marked open or resolved, with its latest run and pending approvals."""
    with closing(connect()) as conn:
        out = []
        for t in conn.execute("SELECT * FROM tickets ORDER BY id"):
            t = dict(t)
            last = conn.execute("SELECT run_id, stop_reason, message, created_at FROM agent_runs "
                                "WHERE ticket_id = ? ORDER BY created_at DESC LIMIT 1", (t["id"],)).fetchone()
            pending = conn.execute("SELECT COUNT(*) FROM approvals WHERE ticket_id = ? AND status = 'pending'",
                                   (t["id"],)).fetchone()[0]
            t["status"] = "resolved" if t["status"] == "resolved" else "open"
            t["last_run"] = dict(last) if last else None
            t["pending_approvals"] = pending
            out.append(t)
        return out


# 2) Run the agent team on one ticket ---------------------------------------------------------------

def _require_ticket(ticket_id: int) -> None:
    with closing(connect()) as conn:
        if conn.execute("SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)).fetchone() is None:
            raise HTTPException(404, f"Ticket {ticket_id} is not in the database.")


@app.post("/api/tickets/{ticket_id}/run")
async def run_ticket(ticket_id: int) -> dict:
    """The Boss works the ticket with the team and answers when it's done. Payments come back as pending approvals."""
    _require_ticket(ticket_id)
    return _save_run(ticket_id, await team.run_ticket(ticket_id))


# Runs the dashboard is watching: run_id -> {"ticket_id", "events", "result", "task"}.
LIVE: dict[str, dict] = {}


@app.post("/api/tickets/{ticket_id}/start")
async def start_ticket(ticket_id: int) -> dict:
    """Start the team in the background and return at once; poll GET /api/runs/{run_id}/live to watch."""
    _require_ticket(ticket_id)
    if any(r["ticket_id"] == ticket_id and r["result"] is None for r in LIVE.values()):
        raise HTTPException(409, f"The team is already working on ticket {ticket_id}.")
    run_id = uuid.uuid4().hex[:12]
    live = LIVE[run_id] = {"ticket_id": ticket_id, "events": [], "result": None}

    async def work() -> None:
        try:
            live["result"] = _save_run(ticket_id, await team.run_ticket(ticket_id, run_id=run_id,
                                                                         events=live["events"]))
        except Exception as err:  # noqa: BLE001 - shown on the board instead of hanging it
            live["result"] = {"run_id": run_id, "ticket_id": ticket_id, "stop_reason": "error",
                              "stop_detail": f"{type(err).__name__}: {err}"[:300], "pending_approvals": []}

    live["task"] = asyncio.create_task(work())
    return {"run_id": run_id, "ticket_id": ticket_id}


@app.get("/api/runs/{run_id}/live")
def live_run(run_id: str, after: int = 0) -> dict:
    """New events since `after`, and the final result once the team is done."""
    live = LIVE.get(run_id)
    if live is None:
        raise HTTPException(404, f"Run {run_id} isn't running in this server. Load it with GET /api/tickets/{{id}}/agents.")
    events = live["events"][after:]
    return {"run_id": run_id, "ticket_id": live["ticket_id"], "events": events, "next": after + len(events),
            "done": live["result"] is not None, "result": live["result"]}


def _save_run(ticket_id: int, result) -> dict:
    """Store a finished run, queue its prepared payments as pending approvals, and resolve the ticket if it's done."""
    with closing(connect()) as conn, conn:
        conn.execute(
            "INSERT INTO agent_runs (run_id, ticket_id, stop_reason, stop_detail, message, decision, agents_used, "
            "agent_reports, tool_calls, loop_steps, seconds, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (result.run_id, ticket_id, result.stop_reason, result.stop_detail, result.message,
             json.dumps(result.decision.model_dump() if result.decision else None),
             json.dumps(result.agents_used), json.dumps(result.agent_reports, default=str),
             json.dumps(result.tool_calls, default=str), result.loop_steps, result.seconds, now()),
        )
        created = []
        for p in (result.decision.approvals_needed if result.decision else []):
            # Don't queue the same payment twice if a ticket is run again.
            dup = conn.execute("SELECT id FROM approvals WHERE status = 'pending' AND kind = ? AND ref_id IS ? "
                               "AND ABS(amount - ?) < 0.005", (p.kind, p.ref_id, p.amount)).fetchone()
            if dup:
                continue
            cur = conn.execute(
                "INSERT INTO approvals (run_id, ticket_id, kind, ref_id, payee, amount, reference, reason, status, "
                "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
                (result.run_id, ticket_id, p.kind, p.ref_id, p.payee, p.amount, p.reference, p.reason, now()),
            )
            created.append(cur.lastrowid)
        maybe_resolve(conn, ticket_id)
        status = conn.execute("SELECT status FROM tickets WHERE id = ?", (ticket_id,)).fetchone()[0]
        approvals = [dict(r) for r in conn.execute("SELECT * FROM approvals WHERE ticket_id = ? AND status = 'pending'",
                                                   (ticket_id,))]
    return {
        "run_id": result.run_id,
        "ticket_id": ticket_id,
        "ticket_status": "resolved" if status == "resolved" else "open",
        "stop_reason": result.stop_reason,
        "stop_detail": result.stop_detail,
        "message": result.message,
        "decision": result.decision.model_dump() if result.decision else None,
        "loop_steps": result.loop_steps,
        "seconds": result.seconds,
        "new_approval_ids": created,
        "pending_approvals": approvals,
    }


# 3) What each agent said and which tools it used ---------------------------------------------------

@app.get("/api/tickets/{ticket_id}/agents")
def agent_activity(ticket_id: int, run_id: str | None = None) -> dict:
    """Per agent: what it reported and every tool it called, for the latest run (or a given run_id)."""
    with closing(connect()) as conn:
        if run_id:
            run = conn.execute("SELECT * FROM agent_runs WHERE run_id = ? AND ticket_id = ?",
                               (run_id, ticket_id)).fetchone()
        else:
            run = conn.execute("SELECT * FROM agent_runs WHERE ticket_id = ? ORDER BY created_at DESC LIMIT 1",
                               (ticket_id,)).fetchone()
    if run is None:
        raise HTTPException(404, f"Ticket {ticket_id} has no agent run yet. POST /api/tickets/{ticket_id}/run first.")
    reports, calls = json.loads(run["agent_reports"] or "[]"), json.loads(run["tool_calls"] or "[]")

    agents: dict[str, dict] = {}
    for name in json.loads(run["agents_used"] or "[]"):
        agents[name] = {"agent": name, "said": [], "reports": [], "tools_used": [], "tool_calls": [],
                        "delegated_to": []}
    for r in reports:
        a = agents.setdefault(r["agent"], {"agent": r["agent"], "said": [], "reports": [], "tools_used": [],
                                           "tool_calls": [], "delegated_to": []})
        a["said"].append(said(r["output"]))
        a["reports"].append({"chain": r["chain"], "loop_step": r["loop_step"], "output": r["output"]})
    for c in calls:
        a = agents[c["agent"]]
        a["tool_calls"].append(c)
        if c["tool"] == "delegate":
            a["delegated_to"].append(c["args"].get("agent"))
        elif c["tool"] not in a["tools_used"]:
            a["tools_used"].append(c["tool"])
    return {
        "run_id": run["run_id"],
        "ticket_id": ticket_id,
        "stop_reason": run["stop_reason"],
        "message": run["message"],
        "decision": json.loads(run["decision"]) if run["decision"] else None,
        "loop_steps": run["loop_steps"],
        "seconds": run["seconds"],
        "created_at": run["created_at"],
        "agents": list(agents.values()),
    }


# 4) Approvals: the agents prepare, the owner decides ----------------------------------------------

@app.get("/api/approvals")
def list_approvals(status: str = "pending") -> list[dict]:
    """Prepared payments, each with a plain-English explanation built from the database."""
    with closing(connect()) as conn:
        sql = "SELECT * FROM approvals" + ("" if status == "all" else " WHERE status = ?") + " ORDER BY id"
        rows = [dict(r) for r in conn.execute(sql, () if status == "all" else (status,))]
        for r in rows:
            r["explain"] = explain_approval(conn, r)
        return rows


def explain_approval(conn: sqlite3.Connection, a: dict) -> dict:
    """Who gets paid, what for, and how it connects to the ticket, so nobody mistakes a bill for a refund."""
    t = conn.execute("SELECT * FROM tickets WHERE id = ?", (a["ticket_id"],)).fetchone() if a["ticket_id"] else None
    lines: list[str] = []
    stock = None

    def customer_lines(sku_hint: str | None) -> None:
        nonlocal stock
        if not t or not t["sku"] or (sku_hint and t["sku"] not in sku_hint):
            return
        line = conn.execute("SELECT name, qty FROM inventory WHERE sku = ? AND size = ?", (t["sku"], t["size"])).fetchone()
        if not line:
            return
        need = t["qty"] or 0
        stock = {"name": line["name"], "sku": t["sku"], "size": t["size"], "on_hand": line["qty"], "needed": need,
                 "short": max(0, need - line["qty"])}
        lines.append(f"Ticket {t['id']}: {t['requester']} wants {need} × {line['name']} ({t['sku']}), size {t['size']}.")
        if line["qty"] < need:
            lines.append(f"We have {line['qty']} in stock, so we're short {need - line['qty']} and need more from our supplier.")
        else:
            lines.append(f"We have {line['qty']} in stock, enough for this order.")
        sold = -(conn.execute("SELECT COALESCE(SUM(change), 0) FROM inventory_changes WHERE ticket_id = ? "
                              "AND reason = 'sale'", (t["id"],)).fetchone()[0])
        lines.append(f"No refund is involved: {sold} of {need} units are recorded as sold to {t['requester']}, "
                     "and we don't pay customers through this approval.")

    if a["kind"] == "invoice":
        inv = conn.execute("SELECT i.*, v.name AS vendor FROM invoices i JOIN vendors v ON v.id = i.vendor_id "
                           "WHERE i.id = ?", (a["ref_id"],)).fetchone()
        headline = "Pay a supplier bill (not a customer refund)"
        customer_lines(inv["description"] if inv else None)
        if inv:
            overdue = (shop_date(conn) - date.fromisoformat(inv["due_date"])).days
            lines.append(f"Invoice {inv['id']} is {inv['vendor']}'s ${inv['amount']:,.2f} bill for "
                         f"“{inv['description']}”: the restock order for this product. It was due {inv['due_date']}"
                         + (f" ({overdue} days overdue)." if overdue > 0 else "."))
            lines.append("Paying it settles what we owe the supplier. Stock goes up only when the restock arrives "
                         "and Inventory records it.")
        payee_type = "supplier"
    elif a["kind"] == "purchase_order":
        headline = "Pay a supplier for new stock (not a customer refund)"
        customer_lines(None)
        lines.append(f"This pays {a['payee']} for a restock order. Stock goes up only when the delivery arrives "
                     "and Inventory records it.")
        payee_type = "supplier"
    else:
        lease = conn.execute("SELECT * FROM leases WHERE id = ?", (a["ref_id"],)).fetchone()
        headline = "Pay the shop's rent"
        if lease:
            lines.append(f"Rent for lease {lease['id']} ({lease['space_name']}) to our landlord, {lease['landlord']}: "
                         f"${lease['monthly_rent']:,.2f} due {lease['next_due']}.")
        lines.append("No customer is involved. Approving moves the lease to next month's due date.")
        payee_type = "landlord"
    return {"payee_type": payee_type, "headline": headline, "lines": lines, "stock": stock}


def _pending(conn: sqlite3.Connection, approval_id: int) -> sqlite3.Row:
    a = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
    if a is None:
        raise HTTPException(404, f"Approval {approval_id} not found.")
    if a["status"] != "pending":
        raise HTTPException(409, f"Approval {approval_id} is already {a['status']}.")
    return a


@app.post("/api/approvals/{approval_id}/approve")
def approve(approval_id: int) -> dict:
    """The owner approves a prepared payment or purchase. Only now is money recorded as paid."""
    with closing(connect()) as conn, conn:
        a = _pending(conn, approval_id)
        today = shop_date(conn)
        cash = checking_balance(conn)
        if a["amount"] > cash["balance"]:
            raise HTTPException(409, f"Not enough cash: ${a['amount']:,.2f} needed, ${cash['balance']:,.2f} in checking.")

        if a["kind"] == "invoice":
            inv = conn.execute("SELECT * FROM invoices WHERE id = ?", (a["ref_id"],)).fetchone()
            if inv is None or inv["status"] != "open":
                raise HTTPException(409, f"Invoice {a['ref_id']} is not open.")
            if abs(inv["amount"] - a["amount"]) >= 0.005:
                raise HTTPException(409, f"Invoice {inv['id']} is ${inv['amount']:,.2f}, not ${a['amount']:,.2f}.")
            conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (inv["id"],))
            effect = f"Invoice {inv['id']} marked paid."
        elif a["kind"] == "rent":
            lease = conn.execute("SELECT * FROM leases WHERE id = ?", (a["ref_id"],)).fetchone()
            if lease is None:
                raise HTTPException(409, f"Lease {a['ref_id']} not found.")
            if abs(lease["monthly_rent"] - a["amount"]) >= 0.005:
                raise HTTPException(409, f"Lease {lease['id']} rent is ${lease['monthly_rent']:,.2f}, "
                                         f"not ${a['amount']:,.2f}.")
            next_due = add_month(date.fromisoformat(lease["next_due"])).isoformat()
            conn.execute("UPDATE leases SET next_due = ? WHERE id = ?", (next_due, lease["id"]))
            effect = f"Rent for {lease['next_due']} paid; lease {lease['id']} next due {next_due}."
        elif a["kind"] == "purchase_order":
            vendor = conn.execute("SELECT * FROM vendors WHERE id = ?", (a["ref_id"],)).fetchone()
            if vendor is None:
                raise HTTPException(409, f"Vendor {a['ref_id']} not found.")
            effect = (f"Purchase order paid to {vendor['name']}. Stock goes up only when Inventory records "
                      "the delivery with update_inventory.")
        else:
            raise HTTPException(409, f"Unknown approval kind {a['kind']}.")

        pay = conn.execute(
            "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) VALUES (?, ?, ?, ?, ?, ?)",
            (a["kind"], a["ref_id"], a["amount"], CASH_ACCOUNT, today.isoformat(), OWNER),
        )
        conn.execute("UPDATE cash_accounts SET balance = balance - ?, date = ? WHERE name = ?",
                     (a["amount"], today.isoformat(), CASH_ACCOUNT))
        conn.execute("UPDATE approvals SET status = 'approved', decided_by = ?, decided_at = ?, payment_id = ? "
                     "WHERE id = ?", (OWNER, now(), pay.lastrowid, approval_id))
        maybe_resolve(conn, a["ticket_id"])
        balance = checking_balance(conn)
    append_audit({"event": "owner_decision", "decision": "approved", "run_id": a["run_id"], "ticket_id": a["ticket_id"],
                  "approval_id": approval_id, "kind": a["kind"], "ref_id": a["ref_id"], "payee": a["payee"],
                  "amount": a["amount"], "payment_id": pay.lastrowid, "checking_balance_after": balance["balance"],
                  "effect": effect})
    return {"approved": True, "approval_id": approval_id, "payment_id": pay.lastrowid, "kind": a["kind"],
            "payee": a["payee"], "amount": a["amount"], "effect": effect, "checking_balance": balance["balance"]}


@app.post("/api/approvals/{approval_id}/reject")
def reject(approval_id: int) -> dict:
    """The owner says no. Nothing is paid."""
    with closing(connect()) as conn, conn:
        a = _pending(conn, approval_id)
        conn.execute("UPDATE approvals SET status = 'rejected', decided_by = ?, decided_at = ? WHERE id = ?",
                     (OWNER, now(), approval_id))
        maybe_resolve(conn, a["ticket_id"])
    append_audit({"event": "owner_decision", "decision": "rejected", "run_id": a["run_id"], "ticket_id": a["ticket_id"],
                  "approval_id": approval_id, "kind": a["kind"], "ref_id": a["ref_id"], "payee": a["payee"],
                  "amount": a["amount"], "payment_id": None})
    return {"rejected": True, "approval_id": approval_id, "payee": a["payee"], "amount": a["amount"]}


# 5) Checking balance -------------------------------------------------------------------------------

@app.get("/api/cash")
def cash() -> dict:
    with closing(connect()) as conn:
        return checking_balance(conn)


# 6) Reset to the original data ---------------------------------------------------------------------

@app.post("/api/reset")
def reset() -> dict:
    """Copy the untouched original over the working database for a fresh run.

    Tickets, stock, invoices, cash, emails, runs and approvals all go back to the start.
    output/audit_trail.json is append-only and keeps its history.
    """
    if not ORIGINAL_DB.exists():
        raise HTTPException(500, "data/campus_customs.db (the original) is missing.")
    shutil.copyfile(ORIGINAL_DB, WORKING_DB)
    ensure_tables()
    with closing(connect()) as conn:
        open_tickets = conn.execute("SELECT COUNT(*) FROM tickets WHERE status = 'open'").fetchone()[0]
        balance = checking_balance(conn)
    return {"reset": True, "open_tickets": open_tickets, "checking_balance": balance["balance"],
            "note": "Audit trail kept: it is append-only."}

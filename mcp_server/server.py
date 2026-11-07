"""Campus Customs MCP server.

Gives the agent team tools over data/campus_customs_new.db: five that only read,
and two that write (send_customer_email, update_inventory), each with its own
checks and a log table. Every value returned comes from the database; anything
calculated from it (shortfall, margin, days overdue, arrival date) is labeled
as calculated.
"""

import os
import re
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastmcp import FastMCP

# CAMPUS_DB_PATH lets tests point the server at a scratch copy instead of the working database.
DB_PATH = Path(os.getenv("CAMPUS_DB_PATH") or Path(__file__).resolve().parent.parent / "data" / "campus_customs_new.db")

# Product words -> words to look for in vendors.specialty. The database has no
# SKU-to-vendor table, so matches made this way are reported as "inferred".
SPECIALTY_TERMS = {
    "hoodie": "apparel",
    "tee": "apparel",
    "cap": "apparel",
    "mug": "mug",
}

mcp = FastMCP(
    "Campus Customs",
    instructions=(
        "Tools over the Campus Customs shop database. Only use what the tools return. "
        "If a tool says data is missing, say so instead of guessing. Customer emails are "
        "simulated: they are saved, never sent."
    ),
)

# Log tables for the two write tools. Created once in the working database if missing.
LOG_TABLES = """
CREATE TABLE IF NOT EXISTS customer_emails (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER NOT NULL,
    to_name TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    order_status TEXT NOT NULL,
    delivery TEXT NOT NULL,
    shop_date TEXT NOT NULL,
    logged_at TEXT NOT NULL,
    FOREIGN KEY (ticket_id) REFERENCES tickets(id)
);
CREATE TABLE IF NOT EXISTS inventory_changes (
    id INTEGER PRIMARY KEY,
    sku TEXT NOT NULL,
    size TEXT NOT NULL,
    change INTEGER NOT NULL,
    qty_before INTEGER NOT NULL,
    qty_after INTEGER NOT NULL,
    reason TEXT NOT NULL,
    ticket_id INTEGER,
    note TEXT,
    shop_date TEXT NOT NULL,
    logged_at TEXT NOT NULL
);
"""


def _rows(sql: str, params: tuple = ()) -> list[dict]:
    # mode=ro: read tools can never change the database.
    with closing(sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(sql, params)]


def _writer() -> sqlite3.Connection:
    """A read-write connection, used only by the two write tools."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_log_tables() -> None:
    with closing(_writer()) as conn:
        conn.executescript(LOG_TABLES)


_ensure_log_tables()


def _shop_date() -> date:
    # The shop runs on desk.date_today, not the computer's clock.
    return date.fromisoformat(_rows("SELECT date_today FROM desk LIMIT 1")[0]["date_today"])


def _with_pricing(line: dict) -> dict:
    price = _rows("SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (line["sku"],))
    if not price:
        line["list_price"] = None
        line["internal"] = {"note": "No pricing row for this SKU."}
        return line
    cost, list_price = price[0]["unit_cost"], price[0]["list_price"]
    line["list_price"] = list_price
    line["internal"] = {
        "unit_cost": cost,
        "margin_per_unit_at_list (calculated)": round(list_price - cost, 2),
        "margin_pct_at_list (calculated)": round((list_price - cost) / list_price * 100, 1),
        "note": "Internal only. Never share unit cost or margin with customers.",
    }
    return line


@mcp.tool
def check_inventory(
    sku: str | None = None,
    size: str | None = None,
    qty_needed: int | None = None,
    out_of_stock_only: bool = False,
) -> dict:
    """Look up stock by SKU and size, with price, aisle, and any shortfall.

    Use it to answer customers about availability and price, to find how many
    units are short for an order, or (with no arguments) to see all stock.
    Set out_of_stock_only=True to list every line at zero units.
    """
    sql, params = "SELECT sku, name, size, qty, location FROM inventory WHERE 1=1", []
    if sku:
        sql += " AND UPPER(sku) = ?"
        params.append(sku.strip().upper())
    if size:
        sql += " AND UPPER(size) = ?"
        params.append(size.strip().upper())
    if out_of_stock_only:
        sql += " AND qty = 0"
    lines = _rows(sql + " ORDER BY sku, size", tuple(params))

    if not lines:
        known = _rows(
            "SELECT size, qty FROM inventory WHERE UPPER(sku) = ?",
            ((sku or "").strip().upper(),),
        )
        return {
            "found": False,
            "message": "No inventory line matches that request.",
            "sizes_on_file_for_sku": known,
        }

    for line in lines:
        if qty_needed is not None:
            short = max(0, qty_needed - line["qty"])
            line["qty_needed"] = qty_needed
            line["shortfall (calculated)"] = short
            line["status"] = "enough" if short == 0 else "short"
        else:
            line["status"] = "out_of_stock" if line["qty"] == 0 else "in_stock"
        _with_pricing(line)

    products = {}
    for row in _rows(
        "SELECT sku, name, size, qty FROM inventory WHERE sku IN (%s) ORDER BY sku, size"
        % ",".join("?" * len({l['sku'] for l in lines})),
        tuple({l["sku"] for l in lines}),
    ):
        p = products.setdefault(row["sku"], {"sku": row["sku"], "name": row["name"],
                                             "total_units": 0, "sizes_in_stock": [],
                                             "sizes_out_of_stock": []})
        p["total_units"] += row["qty"]
        (p["sizes_in_stock"] if row["qty"] else p["sizes_out_of_stock"]).append(row["size"])

    return {
        "found": True,
        "shop_date": _shop_date().isoformat(),
        "lines": lines,
        "product_totals": list(products.values()),
        "note": "The database has no reorder point, so 'low' is only judged against qty_needed.",
    }


def _vendor_matches(sku: str, product_name: str) -> list[dict]:
    matches = {}
    # Strongest evidence: an invoice that names this SKU.
    for row in _rows(
        """SELECT v.id, v.name, v.specialty, v.lead_days, i.id AS invoice_id
           FROM invoices i JOIN vendors v ON v.id = i.vendor_id
           WHERE UPPER(i.description) LIKE ?""",
        (f"%{sku.upper()}%",),
    ):
        m = matches.setdefault(row["id"], {**{k: row[k] for k in ("id", "name", "specialty", "lead_days")},
                                           "evidence": []})
        m["evidence"].append(f"past invoice {row['invoice_id']} names {sku}")
    # Weaker evidence: specialty fits the kind of product.
    terms = {t for word, t in SPECIALTY_TERMS.items() if word in product_name.lower()}
    for term in terms:
        for row in _rows("SELECT id, name, specialty, lead_days FROM vendors WHERE LOWER(specialty) LIKE ?",
                         (f"%{term}%",)):
            m = matches.setdefault(row["id"], {**row, "evidence": []})
            m["evidence"].append(f"specialty '{row['specialty']}' fits '{product_name}' (inferred)")
    # Past invoices first, then the fastest delivery.
    return sorted(matches.values(),
                  key=lambda m: (not any("invoice" in e for e in m["evidence"]), m["lead_days"]))


def _open_invoices(vendor_id: int, today: date) -> list[dict]:
    out = []
    for inv in _rows("SELECT id, amount, due_date, status, description FROM invoices "
                     "WHERE vendor_id = ? AND status = 'open'", (vendor_id,)):
        late = (today - date.fromisoformat(inv["due_date"])).days
        inv["days_overdue (calculated)"] = max(0, late)
        out.append(inv)
    return out


@mcp.tool
def find_vendors(
    sku: str | None = None,
    size: str | None = None,
    qty_needed: int | None = None,
    keyword: str | None = None,
) -> dict:
    """Find which vendor to restock from, checking the vendor list first.

    With a SKU (plus size and qty_needed), returns ranked vendors from the
    database, the shortfall, an estimated restock cost and an arrival date.
    With a keyword, searches vendor names and specialties.
    With no arguments, lists all vendors and every out-of-stock line.
    If the database has no fitting vendor, it returns web_search_needed=True
    and a search phrase; label any web result as coming from the web.
    """
    today = _shop_date()
    vendors = _rows("SELECT id, name, specialty, lead_days FROM vendors ORDER BY id")

    if not sku and not keyword:
        out = _rows("SELECT sku, name, size FROM inventory WHERE qty = 0 ORDER BY sku, size")
        for line in out:
            line["vendors"] = [v["name"] for v in _vendor_matches(line["sku"], line["name"])]
        return {"shop_date": today.isoformat(), "vendors": vendors, "out_of_stock_lines": out}

    if keyword:
        hits = _rows("SELECT id, name, specialty, lead_days FROM vendors "
                     "WHERE LOWER(name) LIKE ? OR LOWER(specialty) LIKE ?",
                     (f"%{keyword.lower()}%", f"%{keyword.lower()}%"))
        if hits:
            return {"source": "database", "vendors": hits}
        return {"source": "none_in_database", "web_search_needed": True,
                "suggested_search": f"{keyword} wholesale supplier New Haven CT",
                "vendors_on_file": vendors}

    product = _rows("SELECT DISTINCT name FROM inventory WHERE UPPER(sku) = ?", (sku.strip().upper(),))
    if not product:
        return {"found": False, "message": f"SKU {sku} is not in inventory."}
    sku, name = sku.strip().upper(), product[0]["name"]
    matches = _vendor_matches(sku, name)
    if not matches:
        return {"source": "none_in_database", "web_search_needed": True,
                "suggested_search": f"{name} wholesale supplier New Haven CT",
                "vendors_on_file": vendors}

    result = {"source": "database", "shop_date": today.isoformat(), "sku": sku, "product": name,
              "vendors": []}
    restock = None
    if size and qty_needed is not None:
        line = _rows("SELECT qty FROM inventory WHERE sku = ? AND UPPER(size) = ?", (sku, size.upper()))
        cost = _rows("SELECT unit_cost FROM pricing WHERE sku = ?", (sku,))
        if line:
            short = max(0, qty_needed - line[0]["qty"])
            restock = {"size": size.upper(), "on_hand": line[0]["qty"], "qty_needed": qty_needed,
                       "units_to_order (calculated)": short}
            if cost:
                restock["unit_cost"] = cost[0]["unit_cost"]
                restock["estimated_cost (calculated)"] = round(short * cost[0]["unit_cost"], 2)
                restock["cost_note"] = "Uses our pricing.unit_cost; no vendor quote is in the database."
            result["restock"] = restock

    for v in matches:
        v["expected_arrival_if_ordered_today (calculated)"] = (today + timedelta(days=v["lead_days"])).isoformat()
        v["open_invoices_with_vendor"] = _open_invoices(v["id"], today)
        result["vendors"].append(v)
    result["recommended"] = matches[0]["name"]
    return result


@mcp.tool
def get_tickets(
    status: str = "open",
    ticket_id: int | None = None,
    ticket_type: str | None = None,
) -> dict:
    """Get tickets with their linked lease or invoice, plus how past tickets were resolved.

    status is 'open' (default), 'resolved' (anything not open) or 'all'.
    Pass ticket_id for one ticket. For each ticket, prior_resolutions lists
    earlier tickets of the same type that are no longer open, so agents can
    follow how the shop handled them before.
    """
    today = _shop_date()
    sql, params = "SELECT * FROM tickets WHERE 1=1", []
    if ticket_id is not None:
        sql += " AND id = ?"
        params.append(ticket_id)
    elif status == "open":
        sql += " AND status = 'open'"
    elif status == "resolved":
        sql += " AND status != 'open'"
    if ticket_type:
        sql += " AND type = ?"
        params.append(ticket_type)
    tickets = _rows(sql + " ORDER BY created_at", tuple(params))
    if not tickets:
        return {"found": False, "message": "No tickets match that request."}

    for t in tickets:
        if t["lease_id"] is not None:
            lease = _rows("SELECT * FROM leases WHERE id = ?", (t["lease_id"],))
            if lease:
                lease[0]["days_until_due (calculated)"] = (date.fromisoformat(lease[0]["next_due"]) - today).days
            t["lease"] = lease[0] if lease else None
        if t["invoice_id"] is not None:
            inv = _rows("""SELECT i.*, v.name AS vendor_name, v.lead_days AS vendor_lead_days
                           FROM invoices i JOIN vendors v ON v.id = i.vendor_id WHERE i.id = ?""",
                        (t["invoice_id"],))
            if inv:
                inv[0]["days_overdue (calculated)"] = max(0, (today - date.fromisoformat(inv[0]["due_date"])).days)
            t["invoice"] = inv[0] if inv else None
        if t["sku"]:
            t["next_step_hint"] = "Call check_inventory with this sku, size and qty."
        # Payments already made against the same invoice or lease.
        t["payments_on_linked_items"] = _rows(
            "SELECT * FROM payments WHERE (kind = 'invoice' AND ref_id = ?) OR (kind IN ('lease','rent') AND ref_id = ?)",
            (t["invoice_id"], t["lease_id"]),
        )
        prior = _rows("SELECT id, subject, status, notes, created_at FROM tickets "
                      "WHERE type = ? AND status != 'open' AND id != ? ORDER BY created_at DESC",
                      (t["type"], t["id"]))
        t["prior_resolutions"] = prior or f"No resolved '{t['type']}' tickets in the database yet."
        t["emails_sent"] = _rows("SELECT id, subject, order_status, delivery, shop_date FROM customer_emails "
                                 "WHERE ticket_id = ? ORDER BY id", (t["id"],))

    return {"shop_date": today.isoformat(), "count": len(tickets), "tickets": tickets}


def _invoice_rows(today: date, sql_where: str = "", params: tuple = ()) -> list[dict]:
    rows = _rows("SELECT i.*, v.name AS vendor_name FROM invoices i JOIN vendors v ON v.id = i.vendor_id "
                 + sql_where + " ORDER BY i.due_date", params)
    for inv in rows:
        days = (date.fromisoformat(inv["due_date"]) - today).days
        inv["days_overdue (calculated)"] = max(0, -days)
        inv["days_until_due (calculated)"] = max(0, days)
    return rows


def _lease_rows(today: date, sql_where: str = "", params: tuple = ()) -> list[dict]:
    rows = _rows("SELECT * FROM leases " + sql_where + " ORDER BY next_due", params)
    for lease in rows:
        lease["days_until_due (calculated)"] = (date.fromisoformat(lease["next_due"]) - today).days
    return rows


@mcp.tool
def get_documents(
    doc_type: str = "all",
    doc_id: int | None = None,
    status: str | None = None,
) -> dict:
    """Read the shop's financial and property documents.

    doc_type is 'invoices', 'leases', 'payments', 'cash' or 'all' (default).
    doc_id picks one invoice, lease or payment. status filters invoices
    (for example 'open'). Each invoice and lease shows days overdue or days
    until due, measured from the shop date in desk.
    """
    today = _shop_date()
    kinds = {"invoices", "leases", "payments", "cash", "all"}
    if doc_type not in kinds:
        return {"found": False, "message": f"doc_type must be one of {sorted(kinds)}."}
    out: dict = {"shop_date": today.isoformat()}

    if doc_type in ("invoices", "all"):
        where, params = [], []
        if doc_id is not None and doc_type == "invoices":
            where.append("i.id = ?")
            params.append(doc_id)
        if status:
            where.append("i.status = ?")
            params.append(status)
        out["invoices"] = _invoice_rows(today, ("WHERE " + " AND ".join(where)) if where else "", tuple(params))
    if doc_type in ("leases", "all"):
        if doc_id is not None and doc_type == "leases":
            out["leases"] = _lease_rows(today, "WHERE id = ?", (doc_id,))
        else:
            out["leases"] = _lease_rows(today)
    if doc_type in ("payments", "all"):
        if doc_id is not None and doc_type == "payments":
            out["payments"] = _rows("SELECT * FROM payments WHERE id = ?", (doc_id,))
        else:
            out["payments"] = _rows("SELECT * FROM payments ORDER BY paid_at")
        if not out["payments"]:
            out["payments_note"] = "No payments are recorded in the database."
    if doc_type in ("cash", "all"):
        out["cash_accounts"] = _rows("SELECT * FROM cash_accounts")

    if doc_id is not None and doc_type != "all" and not any(out.get(k) for k in ("invoices", "leases", "payments")):
        return {"found": False, "message": f"No {doc_type} record with id {doc_id}."}
    return out


FORMULAS = {
    "gross_margin_per_unit": "list_price - unit_cost",
    "gross_margin_pct": "(price - unit_cost) / price x 100",
    "markup_pct": "(price - unit_cost) / unit_cost x 100",
    "discounted_price": "list_price x (1 - discount_pct / 100)",
    "revenue": "qty x price charged",
    "cost_of_goods_sold": "qty x unit_cost",
    "gross_profit": "revenue - cost_of_goods_sold",
    "max_discount_before_loss_pct": "(list_price - unit_cost) / list_price x 100",
    "restock_cost": "units_to_order x unit_cost",
    "cash_after_obligations": "cash balance - open invoices - rent due",
}


@mcp.tool
def get_financials(
    sku: str | None = None,
    qty: int | None = None,
    discount_pct: float | None = None,
) -> dict:
    """Accounting formulas plus the shop's prices, costs, stock value and cash position.

    With no arguments: margins for every SKU, stock value at cost and at list
    price, and cash after open invoices and rent. Add sku and qty to price an
    order (revenue, cost, gross profit, margin), and discount_pct (0-100) to
    see what a discount does to that order. Every number is calculated from
    pricing, inventory, invoices, leases and cash_accounts.
    """
    today = _shop_date()
    if discount_pct is not None and not 0 <= discount_pct <= 100:
        return {"found": False, "message": "discount_pct must be between 0 and 100."}

    products = _rows("""SELECT p.sku, MIN(i.name) AS name, p.unit_cost, p.list_price,
                               COALESCE(SUM(i.qty), 0) AS units_on_hand
                        FROM pricing p LEFT JOIN inventory i ON i.sku = p.sku
                        GROUP BY p.sku ORDER BY p.sku""")
    for p in products:
        m = p["list_price"] - p["unit_cost"]
        p["margin_per_unit (calculated)"] = round(m, 2)
        p["margin_pct (calculated)"] = round(m / p["list_price"] * 100, 1)
        p["markup_pct (calculated)"] = round(m / p["unit_cost"] * 100, 1)
        p["stock_value_at_cost (calculated)"] = round(p["units_on_hand"] * p["unit_cost"], 2)
        p["stock_value_at_list (calculated)"] = round(p["units_on_hand"] * p["list_price"], 2)

    cash = _rows("SELECT name, balance, date FROM cash_accounts")
    balance = sum(c["balance"] for c in cash)
    open_inv = _invoice_rows(today, "WHERE i.status = 'open'")
    leases = _lease_rows(today)
    owed_inv = sum(i["amount"] for i in open_inv)
    rent_next = sum(l["monthly_rent"] for l in leases)
    result = {
        "shop_date": today.isoformat(),
        "formulas": FORMULAS,
        "cash_position": {
            "accounts": cash,
            "open_invoices": [{k: i[k] for k in ("id", "vendor_name", "amount", "due_date",
                                                 "days_overdue (calculated)")} for i in open_inv],
            "next_rent": [{k: l[k] for k in ("id", "space_name", "monthly_rent", "next_due",
                                             "days_until_due (calculated)")} for l in leases],
            "total_cash (calculated)": round(balance, 2),
            "total_open_invoices (calculated)": round(owed_inv, 2),
            "total_next_rent (calculated)": round(rent_next, 2),
            "cash_after_obligations (calculated)": round(balance - owed_inv - rent_next, 2),
        },
        "revenue_history": "Not in the database: there is no sales table, so past revenue cannot be reported.",
    }

    if not sku:
        result["products"] = products
        result["stock_value_at_cost_total (calculated)"] = round(sum(p["stock_value_at_cost (calculated)"] for p in products), 2)
        result["stock_value_at_list_total (calculated)"] = round(sum(p["stock_value_at_list (calculated)"] for p in products), 2)
        return result

    match = [p for p in products if p["sku"] == sku.strip().upper()]
    if not match:
        return {"found": False, "message": f"SKU {sku} has no pricing row."}
    p = match[0]
    result["product"] = p
    if qty is not None:
        price = p["list_price"] * (1 - (discount_pct or 0) / 100)
        revenue, cogs = qty * price, qty * p["unit_cost"]
        result["order"] = {
            "qty": qty,
            "discount_pct": discount_pct or 0,
            "price_per_unit (calculated)": round(price, 2),
            "revenue (calculated)": round(revenue, 2),
            "revenue_at_list (calculated)": round(qty * p["list_price"], 2),
            "discount_given (calculated)": round(qty * p["list_price"] - revenue, 2),
            "cost_of_goods_sold (calculated)": round(cogs, 2),
            "gross_profit (calculated)": round(revenue - cogs, 2),
            "gross_margin_pct (calculated)": round((revenue - cogs) / revenue * 100, 1) if revenue else None,
            "max_discount_before_loss_pct (calculated)": p["margin_pct (calculated)"],
        }
    return result


CUSTOMER_TICKET_TYPES = {"customer_order", "price_override"}
ORDER_STATUSES = {
    "shipping": "We have it and it is being shipped",
    "ready_for_pickup": "We have it and it is ready at the shop",
    "backordered": "Out of stock or short; waiting on a restock",
    "awaiting_approval": "Waiting on an internal decision, such as a discount",
    "update": "General status update with no promise",
}
# Statuses that promise the item, so stock must cover the ticket first.
PROMISES_STOCK = {"shipping", "ready_for_pickup"}
_EMAIL_ADDRESS = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_LONG_NUMBER = re.compile(r"\b(?:\d[ -]?){9,}\b")
_PRIVATE = re.compile(
    r"\b(unit[ _]costs?|margins?|markup|cost of goods|our costs?|cash balance|checking account|invoices?|"
    r"rent|leases?|landlords?|vendors?|suppliers?|database|campus_customs)\b",
    re.IGNORECASE,
)


@mcp.tool
def send_customer_email(ticket_id: int, subject: str, body: str, order_status: str) -> dict:
    """Email a customer about their order. SIMULATED: saved to customer_emails, never really sent.

    order_status is one of: shipping, ready_for_pickup, backordered,
    awaiting_approval, update. 'shipping' and 'ready_for_pickup' are refused
    unless stock covers the ticket's SKU, size and quantity. The body must not
    contain private shop information or personal data. Sending the same
    message for the same ticket twice returns the first copy.
    """
    if order_status not in ORDER_STATUSES:
        return {"sent": False, "message": f"order_status must be one of {sorted(ORDER_STATUSES)}."}
    ticket = _rows("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
    if not ticket:
        return {"sent": False, "message": f"Ticket {ticket_id} is not in the database."}
    t = ticket[0]
    if t["type"] not in CUSTOMER_TICKET_TYPES:
        return {"sent": False, "message": f"Ticket {ticket_id} is a {t['type']}, not a customer ticket."}
    if not subject.strip() or not body.strip():
        return {"sent": False, "message": "Subject and body are both required."}
    leak = _PRIVATE.search(f"{subject} {body}")
    if leak:
        return {"sent": False, "message": f"Refused: mentions private shop information ('{leak.group(0)}')."}
    if _EMAIL_ADDRESS.search(body) or _LONG_NUMBER.search(body):
        return {"sent": False, "message": "Refused: the body contains an email address or long number."}
    if order_status in PROMISES_STOCK:
        # Units already sold for this ticket have left stock, so they count toward the order.
        line = _rows("SELECT qty FROM inventory WHERE sku = ? AND size = ?", (t["sku"], t["size"]))
        on_hand = line[0]["qty"] if line else 0
        sold = -sum(r["change"] for r in _rows(
            "SELECT change FROM inventory_changes WHERE ticket_id = ? AND reason = 'sale'", (ticket_id,)))
        if t["sku"] is None or on_hand + sold < (t["qty"] or 0):
            return {"sent": False, "message": (f"Refused: '{order_status}' promises the item, but {t['sku']} size "
                                               f"{t['size']} has {on_hand} on hand and {sold} already sold "
                                               f"for {t['qty']} ordered.")}

    previous = _rows("SELECT * FROM customer_emails WHERE ticket_id = ? AND subject = ? AND body = ?",
                     (ticket_id, subject, body))
    if previous:
        return {"sent": False, "duplicate": True, "message": "This exact email was already logged.",
                "email": previous[0]}
    delivery = "SIMULATED: saved to customer_emails, no real email sent"
    with closing(_writer()) as conn, conn:
        cur = conn.execute(
            "INSERT INTO customer_emails (ticket_id, to_name, subject, body, order_status, delivery, shop_date, "
            "logged_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (ticket_id, t["requester"], subject, body, order_status, delivery, _shop_date().isoformat(),
             datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
    return {"sent": False, "simulated": True, "delivery": delivery, "email_id": cur.lastrowid,
            "to": t["requester"], "to_address": "Not in the database (no customer contact details).",
            "ticket_id": ticket_id, "order_status": order_status, "subject": subject}


INVENTORY_REASONS = {"sale": -1, "restock_received": 1, "return": 1, "count_correction": 0}
MAX_CHANGE = 1000  # one call can't move more units than this


@mcp.tool
def update_inventory(sku: str, size: str, change: int, reason: str,
                     ticket_id: int | None = None, note: str | None = None) -> dict:
    """Change the units on hand for one SKU and size, and log it in inventory_changes.

    change is negative to remove stock (a sale) and positive to add it.
    reason is sale (change < 0), restock_received or return (change > 0),
    or count_correction (either way). Stock can never go below zero. A sale
    with a ticket_id must match that ticket's SKU and size, and can't sell
    more than the ticket's quantity in total.
    """
    if reason not in INVENTORY_REASONS:
        return {"updated": False, "message": f"reason must be one of {sorted(INVENTORY_REASONS)}."}
    if change == 0 or abs(change) > MAX_CHANGE:
        return {"updated": False, "message": f"change must be non-zero and at most {MAX_CHANGE} units."}
    direction = INVENTORY_REASONS[reason]
    if direction and (change > 0) != (direction > 0):
        sign = "negative" if direction < 0 else "positive"
        return {"updated": False, "message": f"A {reason} must have a {sign} change."}
    sku, size = sku.strip().upper(), size.strip().upper()

    if ticket_id is not None:
        ticket = _rows("SELECT sku, size, qty FROM tickets WHERE id = ?", (ticket_id,))
        if not ticket:
            return {"updated": False, "message": f"Ticket {ticket_id} is not in the database."}
        t = ticket[0]
        if reason == "sale":
            if (t["sku"], t["size"]) != (sku, size):
                return {"updated": False, "message": f"Ticket {ticket_id} is for {t['sku']} size {t['size']}, "
                                                     f"not {sku} size {size}."}
            sold = -sum(r["change"] for r in _rows(
                "SELECT change FROM inventory_changes WHERE ticket_id = ? AND reason = 'sale'", (ticket_id,)))
            if sold - change > (t["qty"] or 0):
                return {"updated": False, "message": f"Ticket {ticket_id} is for {t['qty']} units and {sold} are "
                                                     f"already recorded as sold."}

    with closing(_writer()) as conn, conn:
        line = conn.execute("SELECT qty FROM inventory WHERE sku = ? AND size = ?", (sku, size)).fetchone()
        if line is None:
            return {"updated": False, "message": f"No inventory line for {sku} size {size}."}
        before = line["qty"]
        if before + change < 0:
            return {"updated": False, "message": f"Refused: {sku} size {size} has {before} on hand; "
                                                 f"can't remove {-change}."}
        conn.execute("UPDATE inventory SET qty = ? WHERE sku = ? AND size = ?", (before + change, sku, size))
        cur = conn.execute(
            "INSERT INTO inventory_changes (sku, size, change, qty_before, qty_after, reason, ticket_id, note, "
            "shop_date, logged_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sku, size, change, before, before + change, reason, ticket_id, note, _shop_date().isoformat(),
             datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
    return {"updated": True, "change_id": cur.lastrowid, "sku": sku, "size": size, "change": change,
            "qty_before": before, "qty_after": before + change, "reason": reason, "ticket_id": ticket_id}


NO_SHIPMENT_TABLE = ("The database has no shipments or tracking table, so a physical shipment can't be "
                     "confirmed. The only evidence is a shipping or pickup email we sent.")
NO_SALES_HISTORY = ("Sales before the agent team started aren't in the database (there is no sales table). "
                    "Only sales recorded with update_inventory appear here.")


def _ticket_status(t: dict) -> dict:
    sales = _rows("SELECT id, change, qty_before, qty_after, note, shop_date, logged_at FROM inventory_changes "
                  "WHERE ticket_id = ? AND reason = 'sale' ORDER BY id", (t["id"],))
    returns = _rows("SELECT id, change, note, shop_date FROM inventory_changes "
                    "WHERE ticket_id = ? AND reason = 'return' ORDER BY id", (t["id"],))
    emails = _rows("SELECT id, order_status, subject, shop_date, logged_at, delivery FROM customer_emails "
                   "WHERE ticket_id = ? ORDER BY id", (t["id"],))
    sold = -sum(s["change"] for s in sales)
    returned = sum(r["change"] for r in returns)
    ordered = t["qty"] or 0
    if not sales:
        transaction = "no_sale_recorded"
    elif sold >= ordered:
        transaction = "completed"
    else:
        transaction = "partial"
    shipped = [e for e in emails if e["order_status"] in PROMISES_STOCK]
    return {
        "ticket_id": t["id"],
        "customer": t["requester"],
        "sku": t["sku"],
        "size": t["size"],
        "units_ordered": ordered,
        "units_sold_recorded": sold,
        "units_returned": returned,
        "transaction_status": transaction,
        "transaction_confirmed": transaction == "completed",
        "sales": sales,
        "shipment_status": (f"customer_told_{shipped[-1]['order_status']}" if shipped else "no_shipment_record"),
        "shipment_confirmed": False,
        "shipment_note": NO_SHIPMENT_TABLE,
        "emails_sent": emails,
        "ticket_status": t["status"],
    }


@mcp.tool
def check_order_status(ticket_id: int | None = None, sku: str | None = None, size: str | None = None) -> dict:
    """Confirm whether a customer's sale really happened and what we've told them about shipping.

    With ticket_id: units ordered vs. sales recorded (transaction_status is
    completed, partial or no_sale_recorded), returns, every email sent, and
    shipment_status. With sku (and size): every recorded sale and return of
    that product. With nothing: all recorded sales. Sales come from
    inventory_changes; shipping status comes from customer_emails, because the
    database has no shipments table. shipment_confirmed is never true without
    a shipment record.
    """
    today = _shop_date()
    if ticket_id is not None:
        ticket = _rows("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        if not ticket:
            return {"found": False, "message": f"Ticket {ticket_id} is not in the database."}
        t = ticket[0]
        if t["type"] not in CUSTOMER_TICKET_TYPES:
            return {"found": True, "shop_date": today.isoformat(), "ticket_id": ticket_id,
                    "message": f"Ticket {ticket_id} is a {t['type']}, not a customer order, so it has no sale or shipment."}
        return {"found": True, "shop_date": today.isoformat(), **_ticket_status(t),
                "sales_history_note": NO_SALES_HISTORY}

    sql, params = ("SELECT c.id, c.sku, c.size, c.change, c.reason, c.ticket_id, t.requester AS customer, "
                   "c.note, c.shop_date, c.logged_at FROM inventory_changes c "
                   "LEFT JOIN tickets t ON t.id = c.ticket_id WHERE c.reason IN ('sale', 'return')"), []
    if sku:
        sql += " AND c.sku = ?"
        params.append(sku.strip().upper())
    if size:
        sql += " AND c.size = ?"
        params.append(size.strip().upper())
    rows = _rows(sql + " ORDER BY c.id", tuple(params))
    units_sold = -sum(r["change"] for r in rows if r["reason"] == "sale")
    return {
        "found": True,
        "shop_date": today.isoformat(),
        "filter": {"sku": sku, "size": size},
        "records": rows,
        "units_sold_recorded": units_sold,
        "units_returned": sum(r["change"] for r in rows if r["reason"] == "return"),
        "message": None if rows else "No sales or returns are recorded for this filter.",
        "sales_history_note": NO_SALES_HISTORY,
        "shipment_note": NO_SHIPMENT_TABLE,
    }


def _payee(kind: str, ref_id: int | None) -> str | None:
    if kind == "invoice":
        row = _rows("SELECT v.name FROM invoices i JOIN vendors v ON v.id = i.vendor_id WHERE i.id = ?", (ref_id,))
    elif kind in ("rent", "lease"):
        row = _rows("SELECT landlord AS name FROM leases WHERE id = ?", (ref_id,))
    elif kind == "purchase_order":
        row = _rows("SELECT name FROM vendors WHERE id = ?", (ref_id,))
    else:
        row = []
    return row[0]["name"] if row else None


@mcp.tool
def get_checking_account(account: str = "checking") -> dict:
    """The checking account's current (ending) balance and every recorded payment out of it.

    Returns the ending balance from cash_accounts, each payment with its payee
    and who approved it, the opening balance before those payments, and any
    payments still waiting for the owner's approval with the balance after
    them. The database records no deposits or sales cash, so only money going
    out appears in the activity.
    """
    today = _shop_date()
    acct = _rows("SELECT name, balance, date FROM cash_accounts WHERE name = ?", (account,))
    if not acct:
        return {"found": False, "message": f"No cash account named '{account}'.",
                "accounts_on_file": [r["name"] for r in _rows("SELECT name FROM cash_accounts")]}
    ending = acct[0]["balance"]

    activity = _rows("SELECT id, kind, ref_id, amount, paid_at, approved_by FROM payments "
                     "WHERE account = ? ORDER BY paid_at, id", (account,))
    running = ending + sum(p["amount"] for p in activity)
    opening = running
    for p in activity:
        p["payee"] = _payee(p["kind"], p["ref_id"])
        p["direction"] = "out"
        running -= p["amount"]
        p["balance_after (calculated)"] = round(running, 2)

    pending = []
    if _rows("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'approvals'"):
        pending = _rows("SELECT id, ticket_id, kind, ref_id, payee, amount, reference FROM approvals "
                        "WHERE status = 'pending' ORDER BY id")
    pending_total = sum(p["amount"] for p in pending)
    return {
        "found": True,
        "shop_date": today.isoformat(),
        "account": account,
        "ending_balance": ending,
        "balance_as_of": acct[0]["date"],
        "opening_balance_before_recorded_payments (calculated)": round(opening, 2),
        "total_paid_out (calculated)": round(sum(p["amount"] for p in activity), 2),
        "activity": activity,
        "activity_note": None if activity else "No payments are recorded yet.",
        "pending_approvals": pending,
        "pending_total (calculated)": round(pending_total, 2),
        "balance_if_all_pending_approved (calculated)": round(ending - pending_total, 2),
        "deposits_note": "The database records no deposits or sales cash, so only payments out appear here.",
    }


if __name__ == "__main__":
    mcp.run()

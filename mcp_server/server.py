"""Campus Customs MCP server.

Every agent on the team uses these tools to read and update the shop database.
Tools only return what is stored in data/campus_customs_new.db; the only
derived values are date math against desk.date_today and arithmetic on stored
amounts (totals, cost x qty, margins).

Agent tools never move money. They file requests into the approvals queue.
Money only moves through the human tools (pay, place_purchase_order,
reject_request), which the backend calls when a person clicks approve on the
dashboard. The backend never hands those three tools to an agent.

Run (stdio):  python mcp_server/server.py
Run (HTTP):   python mcp_server/server.py --http
HTTP URL:     http://127.0.0.1:8001/mcp
"""

from __future__ import annotations

import argparse
import calendar
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DB_PATH = ROOT / "data" / "campus_customs_new.db"

mcp = FastMCP("campus-customs")

AGENT_NAMES = {"boss", "inventory", "accounting", "facilities", "customer_service"}
TICKET_STATUSES = ("open", "in_progress", "waiting_on_approval", "resolved")

# Workflow tables the agents write to. They only exist in the working copy and are
# created on first use, so resetting the working copy from the original clears them.
WORKFLOW_SCHEMA = """
CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,              -- invoice_payment | rent_payment | purchase_order
    ticket_id INTEGER,
    ref_id INTEGER,                  -- invoices.id, leases.id, or vendors.id for a PO
    vendor_id INTEGER,
    sku TEXT,
    size TEXT,
    qty INTEGER,
    amount REAL NOT NULL,
    reason TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    status TEXT NOT NULL,            -- pending | paid | ordered | rejected
    created_at TEXT NOT NULL,
    decided_by TEXT,
    decided_at TEXT,
    decision_note TEXT
);
CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER NOT NULL,
    recipient TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    drafted_by TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',  -- drafts are never sent
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ticket_log (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER NOT NULL,
    agent TEXT NOT NULL,
    old_status TEXT NOT NULL,
    new_status TEXT NOT NULL,
    note TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


# ---------- Database helpers ----------

@contextmanager
def _db() -> Iterator[sqlite3.Connection]:
    """Open the working copy, commit on success, roll back on error, always close.

    Never creates a new database file if the working copy is missing.
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Working database not found: {DB_PATH}")
    conn = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=rw", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(WORKFLOW_SCHEMA)
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def _today(conn: sqlite3.Connection) -> str:
    """The shop's "today" comes from desk.date_today, not the real clock."""
    row = conn.execute("SELECT date_today FROM desk LIMIT 1").fetchone()
    if row is None:
        raise ToolError("desk.date_today is not set in the database")
    return row["date_today"]


def _now() -> str:
    """Wall-clock timestamp for workflow logs (business dates use desk.date_today)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _days_between(start: str, end: str) -> int:
    return (date.fromisoformat(end[:10]) - date.fromisoformat(start[:10])).days


def _add_month(day: str) -> str:
    d = date.fromisoformat(day[:10])
    year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return d.replace(year=year, month=month, day=min(d.day, calendar.monthrange(year, month)[1])).isoformat()


def _require_agent(name: str) -> None:
    if name not in AGENT_NAMES:
        raise ToolError(f"'{name}' is not an agent on the team: {sorted(AGENT_NAMES)}")


def _require_human(name: str) -> str:
    name = (name or "").strip()
    if not name or name.lower() in AGENT_NAMES:
        raise ToolError("A named human must approve this. Agents cannot approve their own requests.")
    return name


def _ticket(conn: sqlite3.Connection, ticket_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if row is None:
        raise ToolError(f"No ticket with id {ticket_id}.")
    return row


def _unpaid_invoices(conn: sqlite3.Connection, vendor_id: int, today: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM invoices WHERE vendor_id = ? AND status != 'paid' ORDER BY due_date",
        (vendor_id,),
    ).fetchall()
    return [{**dict(r), "days_overdue": max(0, _days_between(r["due_date"], today))} for r in rows]


def _cash(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM cash_accounts ORDER BY name")]


def _pending_payment_total(conn: sqlite3.Connection) -> float:
    row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total FROM approvals "
        "WHERE status = 'pending' AND kind IN ('invoice_payment', 'rent_payment')"
    ).fetchone()
    return round(row["total"], 2)


def _approval(conn: sqlite3.Connection, approval_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
    if row is None:
        raise ToolError(f"No approval request with id {approval_id}.")
    return row


# ---------- Read tools (every agent) ----------

@mcp.tool
def list_tickets(status: str = "open") -> dict:
    """List tickets on the board with their linked lease and invoice records.

    Pass status="open" (default) for the work queue, another status such as
    "waiting_on_approval", or "all" for every ticket. Also returns the shop's
    date_today so agents can judge what is due.
    """
    with _db() as conn:
        today = _today(conn)
        if status == "all":
            rows = conn.execute("SELECT * FROM tickets ORDER BY id").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tickets WHERE status = ? ORDER BY id", (status,)
            ).fetchall()

        tickets = []
        for row in rows:
            ticket = dict(row)
            if ticket["lease_id"] is not None:
                lease = conn.execute(
                    "SELECT * FROM leases WHERE id = ?", (ticket["lease_id"],)
                ).fetchone()
                ticket["lease"] = dict(lease) if lease else None
            if ticket["invoice_id"] is not None:
                invoice = conn.execute(
                    "SELECT * FROM invoices WHERE id = ?", (ticket["invoice_id"],)
                ).fetchone()
                ticket["invoice"] = dict(invoice) if invoice else None
            tickets.append(ticket)

    return {"date_today": today, "status_filter": status, "tickets": tickets}


@mcp.tool
def check_stock(sku: str, size: str | None = None) -> dict:
    """Check on-hand stock for a SKU, optionally for one size.

    Returns each matching inventory row (size, qty, location) and the SKU's
    unit_cost and list_price from the pricing table. found=False if the SKU
    (or SKU + size) is not in inventory.
    """
    with _db() as conn:
        if size:
            rows = conn.execute(
                "SELECT * FROM inventory WHERE sku = ? AND size = ? ORDER BY size",
                (sku, size),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM inventory WHERE sku = ? ORDER BY size", (sku,)
            ).fetchall()
        price = conn.execute("SELECT * FROM pricing WHERE sku = ?", (sku,)).fetchone()

    if not rows:
        where = f"{sku} size {size}" if size else sku
        return {"found": False, "message": f"No inventory rows for {where}."}

    return {
        "found": True,
        "sku": sku,
        "name": rows[0]["name"],
        "stock": [
            {"size": r["size"], "qty": r["qty"], "location": r["location"]}
            for r in rows
        ],
        "pricing": dict(price) if price else None,
    }


@mcp.tool
def get_vendor_status(vendor_id: int | None = None) -> dict:
    """Show vendors, their lead times, and any unpaid invoices.

    Leave vendor_id empty to see every vendor (useful for picking who can
    restock an item by specialty). A vendor with an unpaid invoice will not
    ship new product, so can_ship is False whenever unpaid invoices exist.
    days_overdue is measured against desk.date_today.
    """
    with _db() as conn:
        today = _today(conn)
        if vendor_id is None:
            vendors = conn.execute("SELECT * FROM vendors ORDER BY id").fetchall()
        else:
            vendors = conn.execute(
                "SELECT * FROM vendors WHERE id = ?", (vendor_id,)
            ).fetchall()
            if not vendors:
                return {"found": False, "message": f"No vendor with id {vendor_id}."}

        results = []
        for v in vendors:
            unpaid = _unpaid_invoices(conn, v["id"], today)
            results.append(
                {
                    **dict(v),
                    "unpaid_invoices": unpaid,
                    "unpaid_total": round(sum(i["amount"] for i in unpaid), 2),
                    "can_ship": not unpaid,
                }
            )

    return {"found": True, "date_today": today, "vendors": results}


@mcp.tool
def get_cash_position() -> dict:
    """Cash on hand and everything waiting to be paid.

    Returns each cash account, every unpaid invoice (with days_overdue), every
    lease's next rent (with days_until_due), the total of payment requests
    already pending human approval, and cash_after_pending: the balance left if
    every pending payment request were approved. No money ever comes in.
    """
    with _db() as conn:
        today = _today(conn)
        accounts = _cash(conn)
        invoices = [
            {**dict(r), "days_overdue": max(0, _days_between(r["due_date"], today))}
            for r in conn.execute(
                "SELECT i.*, v.name AS vendor_name FROM invoices i "
                "JOIN vendors v ON v.id = i.vendor_id WHERE i.status != 'paid' ORDER BY i.due_date"
            )
        ]
        rent = [
            {**dict(r), "days_until_due": _days_between(today, r["next_due"])}
            for r in conn.execute("SELECT * FROM leases ORDER BY next_due")
        ]
        pending = _pending_payment_total(conn)

    total_cash = round(sum(a["balance"] for a in accounts), 2)
    return {
        "date_today": today,
        "cash_accounts": accounts,
        "total_cash": total_cash,
        "unpaid_invoices": invoices,
        "unpaid_invoice_total": round(sum(i["amount"] for i in invoices), 2),
        "upcoming_rent": rent,
        "pending_payment_requests_total": pending,
        "cash_after_pending": round(total_cash - pending, 2),
    }


@mcp.tool
def get_leases(lease_id: int | None = None) -> dict:
    """Show the shop's leases with rent amount, landlord, and when rent is next due.

    days_until_due is measured from desk.date_today (negative means overdue).
    Also lists any rent payments already recorded or requested for each lease.
    """
    with _db() as conn:
        today = _today(conn)
        if lease_id is None:
            rows = conn.execute("SELECT * FROM leases ORDER BY id").fetchall()
        else:
            rows = conn.execute("SELECT * FROM leases WHERE id = ?", (lease_id,)).fetchall()
            if not rows:
                return {"found": False, "message": f"No lease with id {lease_id}."}
        leases = []
        for r in rows:
            days = _days_between(today, r["next_due"])
            leases.append(
                {
                    **dict(r),
                    "days_until_due": days,
                    "overdue": days < 0,
                    "payments_made": [
                        dict(p) for p in conn.execute(
                            "SELECT * FROM payments WHERE kind = 'rent' AND ref_id = ? ORDER BY id", (r["id"],)
                        )
                    ],
                    "open_requests": [
                        dict(a) for a in conn.execute(
                            "SELECT id, amount, status, requested_by FROM approvals "
                            "WHERE kind = 'rent_payment' AND ref_id = ? AND status = 'pending'", (r["id"],)
                        )
                    ],
                }
            )
    return {"found": True, "date_today": today, "leases": leases}


@mcp.tool
def check_margin(sku: str, qty: int, unit_price: float | None = None) -> dict:
    """Work out the margin on selling qty units of a SKU at a given unit price.

    unit_price defaults to the list price. Uses unit_cost and list_price from
    the pricing table and returns the discount versus list, margin per unit,
    total revenue, total cost, total margin, and margin percent.
    """
    if qty <= 0:
        raise ToolError("qty must be a positive whole number.")
    with _db() as conn:
        row = conn.execute("SELECT * FROM pricing WHERE sku = ?", (sku,)).fetchone()
    if row is None:
        return {"found": False, "message": f"No pricing row for {sku}."}
    price = row["list_price"] if unit_price is None else unit_price
    if price <= 0:
        raise ToolError("unit_price must be positive.")
    margin_unit = price - row["unit_cost"]
    return {
        "found": True,
        "sku": sku,
        "qty": qty,
        "unit_cost": row["unit_cost"],
        "list_price": row["list_price"],
        "unit_price": round(price, 2),
        "discount_vs_list_pct": round((row["list_price"] - price) / row["list_price"] * 100, 2),
        "margin_per_unit": round(margin_unit, 2),
        "margin_pct": round(margin_unit / price * 100, 2),
        "total_revenue": round(price * qty, 2),
        "total_cost": round(row["unit_cost"] * qty, 2),
        "total_margin": round(margin_unit * qty, 2),
        "below_cost": margin_unit < 0,
    }


@mcp.tool
def list_approvals(status: str = "pending", ticket_id: int | None = None) -> dict:
    """List payment and purchase-order requests in the human approval queue.

    status: "pending" (default), "paid", "ordered", "rejected", or "all".
    Optionally filter to one ticket. Shows what is already requested so agents
    never file a duplicate.
    """
    sql, args = "SELECT * FROM approvals WHERE 1=1", []
    if status != "all":
        sql += " AND status = ?"
        args.append(status)
    if ticket_id is not None:
        sql += " AND ticket_id = ?"
        args.append(ticket_id)
    with _db() as conn:
        rows = [dict(r) for r in conn.execute(sql + " ORDER BY id", args)]
    return {"status_filter": status, "approvals": rows}


@mcp.tool
def list_drafts(ticket_id: int | None = None) -> dict:
    """List customer message drafts on the board (optionally for one ticket). Drafts are never sent."""
    with _db() as conn:
        if ticket_id is None:
            rows = conn.execute("SELECT * FROM drafts ORDER BY id").fetchall()
        else:
            rows = conn.execute("SELECT * FROM drafts WHERE ticket_id = ? ORDER BY id", (ticket_id,)).fetchall()
    return {"drafts": [dict(r) for r in rows]}


# ---------- Write tools (agents; nothing here moves money) ----------

@mcp.tool
def request_payment(
    kind: Literal["invoice", "rent"],
    ref_id: int,
    ticket_id: int,
    reason: str,
    requested_by: str,
) -> dict:
    """File a payment request for a human to approve. Does NOT pay anything.

    kind="invoice": ref_id is invoices.id; the amount is that invoice's amount.
    kind="rent": ref_id is leases.id; the amount is that lease's monthly_rent.
    The amount always comes from the database, never from the caller. Refuses
    duplicates and already-paid invoices. Reports whether cash would cover it.
    """
    _require_agent(requested_by)
    with _db() as conn:
        _ticket(conn, ticket_id)
        if kind == "invoice":
            inv = conn.execute("SELECT * FROM invoices WHERE id = ?", (ref_id,)).fetchone()
            if inv is None:
                raise ToolError(f"No invoice with id {ref_id}.")
            if inv["status"] == "paid":
                raise ToolError(f"Invoice {ref_id} is already paid.")
            amount, vendor_id, approval_kind = inv["amount"], inv["vendor_id"], "invoice_payment"
        else:
            lease = conn.execute("SELECT * FROM leases WHERE id = ?", (ref_id,)).fetchone()
            if lease is None:
                raise ToolError(f"No lease with id {ref_id}.")
            amount, vendor_id, approval_kind = lease["monthly_rent"], None, "rent_payment"

        dup = conn.execute(
            "SELECT id FROM approvals WHERE kind = ? AND ref_id = ? AND status = 'pending'",
            (approval_kind, ref_id),
        ).fetchone()
        if dup:
            raise ToolError(f"Approval request {dup['id']} for this {kind} is already pending. Do not file it twice.")
        # One ticket = one obligation: once this ticket's payment is made, a follow-up run must not
        # pay it again (rent's next_due moves forward after payment, so it would look due again).
        done = conn.execute(
            "SELECT id FROM approvals WHERE ticket_id = ? AND kind = ? AND ref_id = ? AND status = 'paid'",
            (ticket_id, approval_kind, ref_id),
        ).fetchone()
        if done:
            raise ToolError(f"Ticket {ticket_id}'s {kind} was already paid under approval {done['id']}. Nothing more to file.")

        total_cash = round(sum(a["balance"] for a in _cash(conn)), 2)
        pending_before = _pending_payment_total(conn)
        cur = conn.execute(
            "INSERT INTO approvals (kind, ticket_id, ref_id, vendor_id, amount, reason, requested_by, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
            (approval_kind, ticket_id, ref_id, vendor_id, amount, reason, requested_by, _now()),
        )
        approval_id = cur.lastrowid

    return {
        "approval_id": approval_id,
        "kind": approval_kind,
        "ref_id": ref_id,
        "amount": amount,
        "status": "pending",
        "total_cash": total_cash,
        "cash_after_this_and_other_pending": round(total_cash - pending_before - amount, 2),
        "covered_by_cash": total_cash - pending_before - amount >= 0,
        "note": "Waiting for a human to approve on the dashboard. No money has moved.",
    }


@mcp.tool
def request_purchase_order(
    vendor_id: int,
    sku: str,
    size: str,
    qty: int,
    ticket_id: int,
    reason: str,
    requested_by: str,
) -> dict:
    """Prepare a restock purchase order for a human to approve. Does NOT order anything.

    Cost is unit_cost x qty from the pricing table. The SKU and size must
    already exist in inventory. If the vendor has unpaid invoices it will not
    ship, so the PO is filed but blocked until those invoices are paid.
    expected_arrival is desk.date_today + the vendor's lead_days.
    """
    _require_agent(requested_by)
    if qty <= 0:
        raise ToolError("qty must be a positive whole number.")
    with _db() as conn:
        today = _today(conn)
        _ticket(conn, ticket_id)
        vendor = conn.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,)).fetchone()
        if vendor is None:
            raise ToolError(f"No vendor with id {vendor_id}.")
        if conn.execute("SELECT 1 FROM inventory WHERE sku = ? AND size = ?", (sku, size)).fetchone() is None:
            raise ToolError(f"{sku} size {size} is not in inventory.")
        price = conn.execute("SELECT unit_cost FROM pricing WHERE sku = ?", (sku,)).fetchone()
        if price is None:
            raise ToolError(f"No pricing row for {sku}, so the PO cost is unknown.")
        dup = conn.execute(
            "SELECT id FROM approvals WHERE kind = 'purchase_order' AND vendor_id = ? AND sku = ? "
            "AND size = ? AND status = 'pending'",
            (vendor_id, sku, size),
        ).fetchone()
        if dup:
            raise ToolError(f"PO request {dup['id']} for {sku} {size} from this vendor is already pending.")
        amount = round(price["unit_cost"] * qty, 2)
        blocked_by = _unpaid_invoices(conn, vendor_id, today)
        cur = conn.execute(
            "INSERT INTO approvals (kind, ticket_id, ref_id, vendor_id, sku, size, qty, amount, reason, "
            "requested_by, status, created_at) VALUES ('purchase_order', ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
            (ticket_id, vendor_id, vendor_id, sku, size, qty, amount, reason, requested_by, _now()),
        )
        approval_id = cur.lastrowid

    return {
        "approval_id": approval_id,
        "vendor": vendor["name"],
        "vendor_specialty": vendor["specialty"],
        "sku": sku,
        "size": size,
        "qty": qty,
        "unit_cost": price["unit_cost"],
        "amount": amount,
        "status": "pending",
        "blocked_by_unpaid_invoices": [i["id"] for i in blocked_by],
        "can_ship_now": not blocked_by,
        "expected_arrival_if_ordered_today": (date.fromisoformat(today) + timedelta(days=vendor["lead_days"])).isoformat(),
        "note": "Waiting for a human to approve. Nothing has been ordered.",
    }


@mcp.tool
def draft_customer_message(
    ticket_id: int,
    recipient: str,
    subject: str,
    body: str,
    drafted_by: str,
) -> dict:
    """Save a message draft on the board for a human to review. It is NEVER sent.

    Use for replies to customers, student orgs, landlords, or vendors.
    """
    _require_agent(drafted_by)
    if not body.strip() or not subject.strip():
        raise ToolError("subject and body must not be empty.")
    with _db() as conn:
        _ticket(conn, ticket_id)
        cur = conn.execute(
            "INSERT INTO drafts (ticket_id, recipient, subject, body, drafted_by, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'draft', ?)",
            (ticket_id, recipient, subject, body, drafted_by, _now()),
        )
    return {"draft_id": cur.lastrowid, "ticket_id": ticket_id, "status": "draft", "sent": False}


@mcp.tool
def update_ticket(
    ticket_id: int,
    status: Literal["open", "in_progress", "waiting_on_approval", "resolved"],
    note: str,
    updated_by: str,
) -> dict:
    """Change a ticket's status and log why (the original ticket notes are kept).

    A ticket cannot be marked resolved while it still has approval requests
    pending; use waiting_on_approval instead.
    """
    _require_agent(updated_by)
    if not note.strip():
        raise ToolError("note must explain the change.")
    with _db() as conn:
        ticket = _ticket(conn, ticket_id)
        if status == "resolved":
            pending = conn.execute(
                "SELECT id FROM approvals WHERE ticket_id = ? AND status = 'pending'", (ticket_id,)
            ).fetchall()
            if pending:
                raise ToolError(
                    f"Ticket {ticket_id} has pending approvals {[p['id'] for p in pending]}; "
                    "set status to waiting_on_approval instead."
                )
        conn.execute("UPDATE tickets SET status = ? WHERE id = ?", (status, ticket_id))
        conn.execute(
            "INSERT INTO ticket_log (ticket_id, agent, old_status, new_status, note, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (ticket_id, updated_by, ticket["status"], status, note, _now()),
        )
    return {"ticket_id": ticket_id, "old_status": ticket["status"], "new_status": status}


# ---------- Human-only tools (called by the backend's approval endpoints, never by agents) ----------

@mcp.tool
def pay(approval_id: int, approved_by: str, account: str = "checking") -> dict:
    """Pay an approved invoice or rent request. Human approval only.

    Refuses if the request is not a pending payment, if approved_by is not a
    named human, or if the account does not have enough cash (balances can
    never go negative). On success, in one transaction: inserts a payments
    row, lowers cash_accounts.balance, marks the invoice paid (or moves the
    lease's next_due forward one month), and marks the request paid.
    """
    human = _require_human(approved_by)
    with _db() as conn:
        today = _today(conn)
        req = _approval(conn, approval_id)
        if req["kind"] not in ("invoice_payment", "rent_payment"):
            raise ToolError(f"Request {approval_id} is a {req['kind']}, not a payment.")
        if req["status"] != "pending":
            raise ToolError(f"Request {approval_id} is already {req['status']}.")
        acct = conn.execute("SELECT * FROM cash_accounts WHERE name = ?", (account,)).fetchone()
        if acct is None:
            raise ToolError(f"No cash account named {account}.")
        amount = req["amount"]
        if acct["balance"] - amount < 0:
            return {
                "paid": False,
                "refused": True,
                "reason": f"Not enough cash: {account} has ${acct['balance']:.2f}, payment is ${amount:.2f}. "
                "Balances cannot go negative.",
                "approval_id": approval_id,
            }

        if req["kind"] == "invoice_payment":
            inv = conn.execute("SELECT * FROM invoices WHERE id = ?", (req["ref_id"],)).fetchone()
            if inv is None or inv["status"] == "paid":
                raise ToolError(f"Invoice {req['ref_id']} is missing or already paid.")
            conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (req["ref_id"],))
            pay_kind, updated = "invoice", {"invoices": {"id": req["ref_id"], "status": "paid"}}
        else:
            lease = conn.execute("SELECT * FROM leases WHERE id = ?", (req["ref_id"],)).fetchone()
            if lease is None:
                raise ToolError(f"Lease {req['ref_id']} not found.")
            new_due = _add_month(lease["next_due"])
            conn.execute("UPDATE leases SET next_due = ? WHERE id = ?", (new_due, req["ref_id"]))
            pay_kind = "rent"
            updated = {"leases": {"id": req["ref_id"], "next_due": {"from": lease["next_due"], "to": new_due}}}

        new_balance = round(acct["balance"] - amount, 2)
        cur = conn.execute(
            "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) VALUES (?, ?, ?, ?, ?, ?)",
            (pay_kind, req["ref_id"], amount, account, today, human),
        )
        conn.execute("UPDATE cash_accounts SET balance = ?, date = ? WHERE name = ?", (new_balance, today, account))
        conn.execute(
            "UPDATE approvals SET status = 'paid', decided_by = ?, decided_at = ? WHERE id = ?",
            (human, _now(), approval_id),
        )

    return {
        "paid": True,
        "payment_id": cur.lastrowid,
        "approval_id": approval_id,
        "kind": pay_kind,
        "ref_id": req["ref_id"],
        "amount": amount,
        "account": account,
        "balance_before": acct["balance"],
        "balance_after": new_balance,
        "paid_at": today,
        "approved_by": human,
        "updated": updated,
    }


@mcp.tool
def place_purchase_order(approval_id: int, approved_by: str) -> dict:
    """Approve a pending purchase order. Human approval only.

    Refuses while the vendor still has unpaid invoices (they will not ship).
    No cash moves here; the vendor bills later. Inventory is not changed
    until goods arrive.
    """
    human = _require_human(approved_by)
    with _db() as conn:
        today = _today(conn)
        req = _approval(conn, approval_id)
        if req["kind"] != "purchase_order":
            raise ToolError(f"Request {approval_id} is a {req['kind']}, not a purchase order.")
        if req["status"] != "pending":
            raise ToolError(f"Request {approval_id} is already {req['status']}.")
        blocked = _unpaid_invoices(conn, req["vendor_id"], today)
        if blocked:
            return {
                "ordered": False,
                "refused": True,
                "reason": f"Vendor {req['vendor_id']} has unpaid invoices {[b['id'] for b in blocked]} "
                "and will not ship. Pay those first.",
                "approval_id": approval_id,
            }
        lead = conn.execute("SELECT lead_days FROM vendors WHERE id = ?", (req["vendor_id"],)).fetchone()["lead_days"]
        conn.execute(
            "UPDATE approvals SET status = 'ordered', decided_by = ?, decided_at = ? WHERE id = ?",
            (human, _now(), approval_id),
        )
    return {
        "ordered": True,
        "approval_id": approval_id,
        "approved_by": human,
        "expected_arrival": (date.fromisoformat(today) + timedelta(days=lead)).isoformat(),
    }


@mcp.tool
def reject_request(approval_id: int, rejected_by: str, reason: str) -> dict:
    """Reject a pending payment or purchase-order request. Human only. Nothing moves."""
    human = _require_human(rejected_by)
    with _db() as conn:
        req = _approval(conn, approval_id)
        if req["status"] != "pending":
            raise ToolError(f"Request {approval_id} is already {req['status']}.")
        conn.execute(
            "UPDATE approvals SET status = 'rejected', decided_by = ?, decided_at = ?, decision_note = ? WHERE id = ?",
            (human, _now(), reason, approval_id),
        )
    return {"rejected": True, "approval_id": approval_id, "rejected_by": human}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Campus Customs MCP server")
    parser.add_argument("--http", action="store_true", help="serve over HTTP")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    if args.http:
        mcp.run(transport="http", host="127.0.0.1", port=args.port)
    else:
        mcp.run(show_banner=False)

# Campus Customs MCP Server

This MCP server is the shared toolbox for the Campus Customs agent team (boss, inventory, accounting, facilities, customer service). Agents read and update the shop database only through these tools; none of them writes SQL. The tools return only what is stored in the database. The only calculated values are date math against `desk.date_today` and arithmetic on stored amounts.

## Database

The server uses `data/campus_customs_new.db`, a working copy of `data/campus_customs.db`. The original is never modified. Shop "today" is `desk.date_today`. On first use the server adds three workflow tables to the working copy: `approvals`, `drafts` and `ticket_log`.

## Tools

**Read (every agent)**

| Tool | What it does |
|---|---|
| `list_tickets(status="open")` | Tickets (open, another status, or `"all"`) with any linked lease or invoice row, plus `date_today`. |
| `check_stock(sku, size=None)` | On-hand qty and location per size, plus `unit_cost` and `list_price`. |
| `get_vendor_status(vendor_id=None)` | Vendors with `specialty`, `lead_days`, unpaid invoices (with days overdue) and `can_ship`. |
| `get_cash_position()` | Cash balances, unpaid invoices, upcoming rent, pending payment requests, and cash left if they were all approved. |
| `get_leases(lease_id=None)` | Leases with rent, `next_due`, days until due, and payments made or requested. |
| `check_margin(sku, qty, unit_price=None)` | Margin per unit, margin %, totals and discount vs list for a proposed price. |
| `list_approvals(status="pending", ticket_id=None)` | The human approval queue. |
| `list_drafts(ticket_id=None)` | Message drafts on the board. |

**Write (one agent each; none of these moves money)**

| Tool | Agent | What it does |
|---|---|---|
| `request_payment(kind, ref_id, ticket_id, reason, requested_by)` | accounting | Files an invoice or rent payment request. The amount comes from the database. Refuses duplicates, and refuses anything this ticket has already paid. |
| `request_purchase_order(vendor_id, sku, size, qty, ticket_id, reason, requested_by)` | accounting | Files a restock PO request (cost = `unit_cost × qty`). It is flagged as blocked if the vendor has unpaid invoices. |
| `draft_customer_message(ticket_id, recipient, subject, body, drafted_by)` | customer_service | Saves a draft. It is never sent. |
| `update_ticket(ticket_id, status, note, updated_by)` | boss | Sets the ticket status and logs why. It can't be `resolved` while approvals are pending. |

**Human only (called by the backend's approve/reject routes, never given to an agent)**

| Tool | What it does |
|---|---|
| `pay(approval_id, approved_by, account="checking")` | Pays an approved invoice or rent request. Refuses if cash would go negative. Writes `payments`, lowers `cash_accounts.balance`, and marks the invoice paid (or moves the lease's `next_due` forward a month). |
| `place_purchase_order(approval_id, approved_by)` | Places a PO. Refuses while the vendor has unpaid invoices. |
| `reject_request(approval_id, rejected_by, reason)` | Rejects a request. Nothing moves. |

## Run

```
python mcp_server/server.py          # stdio (what .mcp.json and the backend use)
python mcp_server/server.py --http   # http://127.0.0.1:8001/mcp
```

Requires `fastmcp` (see `requirements.txt`).

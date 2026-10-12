# Campus Customs — Harness

This file covers the database tables, the MCP tools, the five agents, the API routes, the dashboard, the safety rules, the expected behavior per ticket, and the results of the full run.

Shop database: `data/campus_customs.db` (original, never modified).
Working copy used by the MCP server and backend: `data/campus_customs_new.db`.

## Tables

### desk
Fields: `date_today`, `notes`

Why it matters: `date_today` is "today" for the shop, so every agent uses it to decide what is overdue or coming due.

### tickets
Fields: `id`, `type`, `requester`, `subject`, `sku`, `size`, `qty`, `lease_id`, `invoice_id`, `status`, `notes`, `created_at`

Why it matters: These are the open requests on the board. The boss reads each one to decide who handles it, and the linked SKU, lease or invoice tells that agent where to look.

### inventory
Fields: `sku`, `name`, `size`, `qty`, `location` (primary key: `sku` + `size`)

Why it matters: The inventory agent checks stock by SKU and size here to see whether an order can be filled or is short.

### pricing
Fields: `sku`, `unit_cost`, `list_price`

Why it matters: Accounting uses cost against price to check margins before agreeing to a discount or a purchase order.

### vendors
Fields: `id`, `name`, `specialty`, `lead_days`

Why it matters: Inventory uses `specialty` to pick who can restock an item and `lead_days` to estimate when it would arrive.

### invoices
Fields: `id`, `vendor_id`, `amount`, `due_date`, `status`, `description`

Why it matters: These are what the shop owes vendors. A vendor with an open unpaid invoice won't ship new product, and comparing `due_date` to `desk.date_today` shows what is overdue.

### leases
Fields: `id`, `space_name`, `landlord`, `monthly_rent`, `next_due`, `notes`

Why it matters: Facilities uses this to track rent and when it is next due.

### cash_accounts
Fields: `name`, `balance`, `date`

Why it matters: This is the cash the shop has. The pay tool checks it and refuses any payment that would push the balance below zero.

### payments
Fields: `id`, `kind`, `ref_id`, `amount`, `account`, `paid_at`, `approved_by`

Why it matters: Every payment a human approves is recorded here, along with who approved it. It starts empty.

## First Three MCP Tools and the Tickets They Unlock

Server: `mcp_server/server.py` (FastMCP, name `campus-customs`), reading `data/campus_customs_new.db`. All three tools are read-only. The only values they calculate are days between dates, measured from `desk.date_today` (2026-08-31), and totals of amounts already in the database.

| Tool | Tables it reads | Ticket it unlocks |
|---|---|---|
| `list_tickets(status="open")` | `tickets`, `desk`, `leases`, `invoices` | 102 — Rent due (Elm City Properties) |
| `check_stock(sku, size=None)` | `inventory`, `pricing` | 103 — Bulk hoodie discount (Yale AI Club) |
| `get_vendor_status(vendor_id=None)` | `vendors`, `invoices`, `desk` | 101 — Bulldog tee (Tauhid Zaman) |

### `list_tickets` → Ticket 102 (Rent due)
Ticket 102 only says "Email: shop rent due in 2 days." and gives `lease_id` 1. `list_tickets` returns the ticket with its lease row attached (Chapel Street shop, landlord Elm City Properties, `monthly_rent` $2,400.00, `next_due` 2026-09-02) along with `date_today` 2026-08-31. Facilities can therefore confirm from the database, rather than from the email, that the $2,400 rent is due in 2 days and is not yet overdue. It is also the boss's starting point for every ticket, because it returns all three open tickets with their linked records.

### `check_stock` → Ticket 103 (Bulk hoodie discount)
The Yale AI Club wants 20 `CC-HOOD-NAVY` hoodies in size M. `check_stock("CC-HOOD-NAVY")` returns every size: S 4, M 8, L 14, XL 6, all in Aisle A. It also returns pricing: `unit_cost` $22.00 and `list_price` $58.00. Inventory can see that the order is 12 hoodies short in size M (8 of 20 on hand), and accounting can see the $36.00 per-unit margin at list price that any bulk discount would cut into. This is the only tool that puts stock and pricing together, and the ticket needs both.

### `get_vendor_status` → Ticket 101 (Bulldog tee)
Tauhid Zaman needs one `CC-TEE-WHITE` in size S. `check_stock` shows qty 0 in Aisle B, so the tee has to be reprinted. `get_vendor_status` shows that Bulldog Print Co (vendor 1, "apparel reprint", `lead_days` 5) is the only apparel vendor. It also shows invoice 501 to Bulldog Print Co ($840.00, "Rush reprint CC-TEE-WHITE S", due 2026-08-28) is still open and 3 days overdue as of 2026-08-31, so `can_ship` is false. The tool therefore tells the team that the tee cannot be restocked until a human approves paying invoice 501, and that the reprint would arrive 5 days after the vendor is cleared to ship.

## Agents

All five agents are PydanticAI agents in `backend/team.py`, and every one uses `gpt-6-luna`. Each gets the shared rules in `backend/prompts/team_rules.md` plus its own prompt file. Every agent has a `delegate(to, task)` tool, so any agent can hand work to any other one (full connectivity).

| Agent | Prompt | Job | MCP tools it can call |
|---|---|---|---|
| boss | `prompts/boss.md` | Reads each ticket, routes it, makes the final call, sets the ticket status | all read tools + `update_ticket` |
| inventory | `prompts/inventory.md` | Stock by SKU and size, shortfalls, restock vendor and lead time | all read tools |
| accounting | `prompts/accounting.md` | Cash, invoices, margins; files payment and PO requests for human approval | all read tools + `request_payment`, `request_purchase_order` |
| facilities | `prompts/facilities.md` | Leases, rent, landlord | all read tools |
| customer_service | `prompts/customer_service.md` | Drafts messages to customers, landlord and vendors (never sent) | all read tools + `draft_customer_message` |

Read tools: `list_tickets`, `check_stock`, `get_vendor_status`, `get_cash_position`, `get_leases`, `check_margin`, `list_approvals`, `list_drafts`.

## All MCP Tools and the Tables They Use

`approvals`, `drafts` and `ticket_log` are workflow tables. The MCP server creates them in the working copy the first time it is used, so a reset clears them.

| Tool | Who can call it | Tables read | Tables written |
|---|---|---|---|
| `list_tickets` | every agent | tickets, desk, leases, invoices | — |
| `check_stock` | every agent | inventory, pricing | — |
| `get_vendor_status` | every agent | vendors, invoices, desk | — |
| `get_cash_position` | every agent | cash_accounts, invoices, vendors, leases, approvals, desk | — |
| `get_leases` | every agent | leases, payments, approvals, desk | — |
| `check_margin` | every agent | pricing | — |
| `list_approvals` | every agent | approvals | — |
| `list_drafts` | every agent | drafts | — |
| `request_payment` | accounting | tickets, invoices or leases, cash_accounts, approvals | approvals |
| `request_purchase_order` | accounting | tickets, vendors, inventory, pricing, invoices, desk | approvals |
| `draft_customer_message` | customer_service | tickets | drafts |
| `update_ticket` | boss | tickets, approvals | tickets (status), ticket_log |
| `pay` | human only (dashboard approve) | approvals, cash_accounts, invoices or leases, desk | payments, cash_accounts, invoices or leases, approvals |
| `place_purchase_order` | human only (dashboard approve) | approvals, invoices, vendors, desk | approvals |
| `reject_request` | human only (dashboard reject) | approvals | approvals |

## Safety

**Guardrails for agents that touch real customers and money**
- **Agents can't move money.** Agents only file requests. `pay` and `place_purchase_order` are never given to an agent, and both refuse unless a named human (not an agent name) approves.
- **No negative cash.** `pay` checks the balance inside the same database transaction that writes the payment, and refuses any payment that would push cash below zero. Money only goes out.
- **Amounts come from the database.** Payment amounts are taken from the invoice or lease row, and PO cost is `unit_cost × qty`. An agent can't type in a dollar figure.
- **Vendor rule is enforced in code.** A PO can't be placed while that vendor has an unpaid invoice.
- **No outbound contact.** There is no email, phone or vendor API tool. Customer text exists only as drafts on the board.
- **No duplicates or premature closes.** Duplicate payment or PO requests are refused, and a ticket can't be marked resolved while it has pending approvals.
- **Invented ids are caught.** Output validators reject any report that cites approval or draft ids that don't exist, or a ticket status that doesn't match the database.
- **Audit everything.** Every agent loop is appended to `output/audit_trail.json`: task, delegation chain, every tool call with full arguments, results, retries, final output and token use. Payments also record `approved_by`.
- **One ticket, one obligation.** `request_payment` refuses to file a payment that a ticket has already paid. A close-out run therefore can't pay rent twice, even though the lease's `next_due` moves forward a month after payment.
- **Close-out runs only confirm.** When the boss re-runs a ticket that is `waiting_on_approval`, it reports what the human did and closes the ticket. It files nothing new for the same obligation.
- **Drafts never block a ticket.** Every draft is reviewed by a human by design, so an unsent draft doesn't keep a ticket open.
- **Protect the original.** `campus_customs.db` is only ever read. All writes go to `campus_customs_new.db`, which is reset from the original before full runs.

**Limits that keep token use in check (per ticket, shared by the whole team)**
- Delegation chains are at most 3 agents deep, and no agent can appear twice in one chain (no ping-pong loops).
- At most 8 delegations and 9 agent runs per ticket.
- At most 45 model requests, 80 tool calls and 400,000 total tokens per ticket. The run stops if any limit is hit, and the stop is recorded in the audit trail.
- At most 2 retries for bad output or tool errors.
- Each agent loop starts fresh, with no carried-over chat history. Tools return compact rows rather than whole tables.
- Each model call times out after 120 seconds, with 1 retry. In the full run, one call on ticket 103 hung for about 10 minutes under the SDK's 600-second default, which is why this limit was added.
- Tickets run one at a time in a full run, so each ticket sees the cash and approvals left by the previous one.

## Expected Behavior per Open Ticket

These are predictions of how the agents should work together, written before the full run. They describe what we expect; they are not instructions to the agents.

### Ticket 101 — Bulldog tee (customer_order)
Requester: Tauhid Zaman · CC-TEE-WHITE size S, qty 1 · linked invoice 501 · "Needs a tee in size S."

- **Boss calls first:** Inventory, because the customer ordered a T-shirt that is out of stock.
- **Other agents involved:**
  - Inventory checks whether the T-shirt is available and which vendor can restock it.
  - Accounting investigates the unpaid vendor invoice, checks available cash, and prepares a payment request if appropriate.
  - Customer Service drafts a message explaining the order status and any expected delay.
  - Boss determines how to proceed based on inventory availability, vendor restrictions, and payment approval.
- **MCP tools they should use:** `list_tickets`, `check_stock`, `get_vendor_status`, `get_cash_position`, `request_payment`, `draft_customer_message`, `update_ticket`. Human `pay` may be needed after approval.

### Ticket 102 — Rent due (rent_notice)
Requester: Elm City Properties · linked lease 1 · "Email: shop rent due in 2 days."

- **Boss calls first:** Facilities, because rent and leases fall under its responsibilities.
- **Other agents involved:**
  - Facilities checks the lease, rent amount, and due date.
  - Accounting checks available cash and prepares a payment request.
  - Boss determines whether the payment can proceed and ensures human approval is obtained.
- **MCP tools they should use:** `list_tickets`, `get_leases`, `get_cash_position`, `request_payment`, `list_approvals`, `update_ticket`. Human `pay` is needed to execute the payment.
- **Important:** Rent is due in two days, not overdue. The team should recognize that distinction.

### Ticket 103 — Bulk hoodie discount (price_override)
Requester: Yale AI Club · CC-HOOD-NAVY size M, qty 20 · "Student org wants 20 hoodies, size M, asking for a bulk discount."

- **Boss calls first:** Inventory, because the customer wants 20 hoodies and the store only has eight available.
- **Other agents involved:**
  - Inventory checks the stock shortfall and restocking options.
  - Accounting evaluates the profit margin and determines whether the requested discount would be financially reasonable. It also checks whether restocking requires a purchase order.
  - Customer Service drafts a response to the Yale AI Club explaining the proposed discount and availability.
  - Boss makes the final decision about the discount and fulfillment plan.
- **MCP tools they should use:** `list_tickets`, `check_stock`, `check_margin`, `get_vendor_status`, `get_cash_position`, `request_purchase_order` (if appropriate), `draft_customer_message`, `update_ticket`. Human `place_purchase_order` may be needed.

## Backend Routes

`backend/main.py` (FastAPI). Start from `backend/` with `uvicorn main:app --reload --port 8000`.

- `GET /api/tickets` — every ticket, with its raw status and whether it is `open` or `resolved`.
- `GET /api/tickets/{ticket_id}/summary` — what each agent did on the ticket since the last reset (read from the audit trail), plus the boss's latest decision.
- `POST /api/tickets/{ticket_id}/run` — starts the agent team (boss first) on that ticket in the background and returns a `run_id`.
- `GET /api/runs/{run_id}` — whether a run is still going, plus the boss's final decision when done.
- `GET /api/events?since=N` — recent agent events (what each agent said, which tool it called, delegations, approvals) for refreshing the board.
- `GET /api/approvals` — payment and purchase-order requests waiting on a human.
- `GET /api/drafts?ticket_id=N` — message drafts on the board (never sent).
- `POST /api/approvals/{id}/approve` — a human approves: pays the invoice or rent, or places the PO. Refuses with 409 if cash would go negative or the vendor is blocked.
- `POST /api/approvals/{id}/reject` — a human rejects a request; nothing moves.
- `GET /api/cash` — the current checking balance from `cash_accounts`.
- `POST /api/reset` — copies `campus_customs.db` over `campus_customs_new.db` for a fresh run (refused while agents are running) and appends a reset marker to the audit trail.

## Dashboard

The dashboard is a React + Vite + TypeScript app in `frontend/`. Start it with `npm run dev`; it calls the backend at `http://localhost:8000`. The full layout is in `output/design.md`.

| Part of the page | What it shows | Route(s) |
|---|---|---|
| Top bar | Shop date (`desk.date_today`), backend connection, **Reset database** | `/api/cash`, `POST /api/reset` |
| Four summary cards | Open tickets, resolved tickets, pending approvals (count and $), checking balance (flashes when it changes) | `/api/tickets`, `/api/approvals`, `/api/cash` |
| Ticket board (left) | One card per ticket with color-coded status and a **Run agents** button. `?ticket=N` preselects a ticket | `/api/tickets`, `POST /api/tickets/{id}/run` |
| Run summary (left) | The boss's final call, what each agent did (summary, tools, approval and draft ids), and drafts (never sent) | `/api/tickets/{id}/summary`, `/api/drafts` |
| Agent team (right) | Five agent cards with a Working / Done / Idle pill and each agent's latest action | `/api/events` |
| Live activity (right) | Delegations, tool calls, requests, drafts, status changes, final summaries and human approvals, polled every 1.2 s. Can be filtered to the selected ticket | `/api/events?since=N` |
| Human approvals (bottom) | Pending payment and PO cards with **Approve** and **Reject** (your name is required), plus a history of decided requests | `/api/approvals`, `POST /api/approvals/{id}/approve`, `/reject` |

The activity feed is held in memory. After a backend restart, it is rebuilt from the audit trail and the approvals table.

## Full Run (Problem 9)

The working database was reset first. Checking started at **$3,400.00** (`cash_accounts`, after the reset).

1. The team ran tickets 101, 102 and 103 one at a time from the dashboard API. Tickets 101 and 102 ended `waiting_on_approval`. Ticket 103 ended `open`, because the boss treated draft 3, which was awaiting review, as a blocker.
2. A human (Sam) approved on the dashboard:
   - approval 1: pay invoice 501, $840.00;
   - approval 2: PO for 1 × CC-TEE-WHITE size S, $8.00, ordered;
   - approval 3: pay lease 1 rent, $2,400.00.
3. The boss prompt was clarified so that drafts don't block a ticket. Each ticket was then run again. On 101 and 102, the boss confirmed the approvals and resolved the tickets. On 103, the team re-evaluated and resolved it. This time the boss declined the discount, offered the 8 in-stock hoodies at the $58.00 list price, and replaced the $50.00 offer in draft 3 with draft 4.
4. Checking ended at **$160.00** ($3,400.00 − $840.00 − $2,400.00), which matches `cash_accounts` in `campus_customs_new.db`.

**Results**
- `output/desk_tickets.html`: one tab per ticket (Expected vs Actual, outcome, approvals, drafts) and a Cash tab.
- `output/resolved_tickets.json`: each ticket's final status, outcome, agent contributions and human approvals.
- `output/resolved_board.html`: dashboard screenshots for each resolved ticket.
- `output/audit_trail.json`: 18 agent-loop records from these runs.

All three files are generated by `python backend/build_reports.py`, which refuses to write them if the cash ledger doesn't match `cash_accounts`.

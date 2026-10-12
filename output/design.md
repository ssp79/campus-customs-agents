# Campus Customs Dashboard Design

The dashboard is an operations command center. It lets a human manager watch the five-agent team work the ticket board and approve or reject every payment and purchase order the agents request. It is built with React + Vite + TypeScript in `frontend/`. All of its data comes from the FastAPI backend at `http://localhost:8000`; nothing is mocked.

## Look and feel

- **Colors:** navy (`#0b1f3a`), blue (`#2563eb`) and white, on a light blue-gray page (`#f4f7fb`). The top bar has a navy gradient.
- **Status colors:** each status has its own color.

  | Status | Color |
  |---|---|
  | Open | blue |
  | In progress / agents working | amber |
  | Awaiting approval | violet |
  | Resolved, paid or ordered | green |
  | Rejected, refused or error | red |

- **Shapes:** cards with 14px rounded corners and soft shadows, and pill-shaped badges.
- **Icons:** a small set of inline SVGs (ticket, shirt, home, tag, crown, box, dollar, building, message, shield, wallet, and so on), so there's no icon library.
- **Agent colors:** each agent has its own color and icon.

  | Agent | Color | Icon |
  |---|---|---|
  | Boss | navy | crown |
  | Inventory | sky blue | box |
  | Accounting | blue | dollar |
  | Facilities | indigo | building |
  | Customer Service | teal | message bubble |

- **Animations (subtle):**
  - Pulsing dots on anything that's running.
  - Cards lift slightly on hover.
  - New items slide into the activity feed.
  - The balance card flashes when checking changes.
  - The Run button's icon spins while a run is going.
  - Toast notifications rise in from the corner.

## Layout

```
┌──────────────────────────────────────────────────────────────────────┐
│ CC  Campus Customs · Operations Command Center   shop date · ● backend · Reset │
├──────────────┬──────────────┬──────────────────┬──────────────────────┤
│ Open tickets │ Resolved     │ Pending approvals│ Checking balance     │
├──────────────┴──────────────┼──────────────────┴──────────────────────┤
│ TICKET BOARD                │ AGENT TEAM                              │
│  #101 Bulldog tee   [Run]   │  Boss · Inventory · Accounting ·        │
│  #102 Rent due      [Run]   │  Facilities · Customer Service          │
│  #103 Hoodie disc.  [Run]   │  (status pill + latest action each)     │
│                             │                                         │
│ RUN SUMMARY (selected)      │ LIVE ACTIVITY FEED                      │
│  Boss's final call          │  time · agent · #ticket · what it did   │
│  What each agent did        │  (delegations, tool calls, requests,    │
│  Drafts (never sent)        │   drafts, status changes, approvals)    │
├─────────────────────────────┴─────────────────────────────────────────┤
│ HUMAN APPROVALS   [your name]                                         │
│  pending payment / PO cards with Approve · Reject; decided history    │
└──────────────────────────────────────────────────────────────────────┘
```

### Top bar
The top bar shows:
- The brand.
- The shop's date, from `desk.date_today`.
- A backend connection indicator.
- A **Reset database** button (with a confirmation prompt) that calls `POST /api/reset`.

### Four summary cards
- **Open tickets:** tickets the agent team hasn't finished.
- **Resolved tickets:** tickets the team has finished. These have status `resolved`, or `waiting_on_approval` (only a human step is left).
- **Pending approvals:** the number of requests and the dollars of payments waiting on a human.
- **Checking balance:** from `GET /api/cash`, with the `as of` date. It flashes when it changes, for example after an approved payment.

### Left column: ticket board and run summary
- **Ticket cards** (one per ticket, from `GET /api/tickets`). Each card shows:
  - an icon for the ticket type, the id, subject and requester;
  - the SKU, size and qty, or the lease or invoice;
  - the original note;
  - two badges: the open/resolved state, and the detailed status.
- **Picking and running a ticket:** clicking a card selects it. **Run agents** calls `POST /api/tickets/{id}/run`. While a run is going, the card turns amber and shows "Agents working".
- **Run summary** for the selected ticket, from `GET /api/tickets/{id}/summary`, which reads the audit trail. It shows:
  - the Boss's final decision, status, "Needs a human" steps and next steps;
  - one row per agent, with its summary, the tools it used, and any approval or draft ids;
  - drafts left on the board (`GET /api/drafts`), which open to show the full text and are marked "never sent".
- **When a run finishes:** the ticket is marked resolved, a toast appears, and the summary reloads.

### Right column: agent team and live activity
- **Five agent cards.** Each shows a Working / Done / Idle pill and the agent's latest action.
- **Live activity feed.** The feed polls `GET /api/events?since=N` every 1.2 seconds. Each line shows the time, agent, ticket and what happened:
  - the agent started;
  - a delegation, with the task text;
  - tool calls, with their arguments;
  - approvals filed;
  - drafts saved;
  - ticket status changes;
  - final summaries;
  - human approvals and rejections.
- **Filter:** a toggle shows only the selected ticket.

### Bottom: human approvals
- **Approver name.** A name field, remembered in the browser, is required before Approve or Reject is enabled. That name is stored as `approved_by` on the payment.
- **Pending request cards.** Each card shows:
  - the kind: invoice payment, rent payment or purchase order;
  - the amount;
  - the invoice, lease, or SKU/size/qty;
  - the requesting agent and the agent's reason.
- **Approve** calls `POST /api/approvals/{id}/approve`:
  - payments are paid, and checking drops right away;
  - purchase orders are placed.
- **Refusals** are shown as a red toast with the backend's reason. For example: not enough cash, or a vendor with an unpaid invoice.
- **Reject** calls `POST /api/approvals/{id}/reject`, and nothing moves.
- **History:** a table lists decided requests, with who decided each one.

## Data flow

| Need | Route | How often |
|---|---|---|
| Tickets, open/resolved, running | `GET /api/tickets` | every 4 s and after any change event |
| Checking balance | `GET /api/cash` | every 4 s and after approvals |
| Approval queue | `GET /api/approvals?status=all` | every 4 s and after any change event |
| Agent activity | `GET /api/events?since=N` | every 1.2 s |
| Per-agent summary and drafts | `GET /api/tickets/{id}/summary`, `GET /api/drafts?ticket_id=` | on select and when a run finishes |
| Start a run | `POST /api/tickets/{id}/run` | Run button |
| Approve / reject | `POST /api/approvals/{id}/approve` · `/reject` | buttons |
| Fresh start | `POST /api/reset` | Reset button |

## Running it

```
cd backend   &&  uvicorn main:app --reload --port 8000
cd frontend  &&  npm run dev        # then open the URL Vite prints (usually http://localhost:5173)
```

The backend's CORS settings allow the Vite page origin: `http://localhost:5173`, plus any other localhost port Vite moves to when 5173 is taken.

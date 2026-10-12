# Campus Customs — Multi-Agent Back Office

Campus Customs is a small campus apparel shop. Its open work arrives as tickets on a board: customer orders, rent notices, unpaid bills, discount requests. A team of five AI agents works each ticket, and a human watches them on a React dashboard and approves anything that involves money.

The project has three pieces that talk to each other:

| Piece | Folder | What it does |
|---|---|---|
| MCP server | `mcp_server/` | FastMCP tools that read and update the shop database |
| Backend | `backend/` | FastAPI app and the PydanticAI agent team: boss, inventory, accounting, facilities, customer_service |
| Dashboard | `frontend/` | React + Vite + TypeScript board for watching the agents and approving payments |

Every agent uses `gpt-6-luna`. Any agent can delegate to any other. Agents can only *request* payments and purchase orders; a human approves them on the dashboard, and the pay tool refuses anything that would make cash negative.

## Repository layout

```
data/campus_customs.db       original shop database (never modified)
data/campus_customs_new.db   working copy the MCP server and backend read and write
mcp_server/server.py         MCP tools (see mcp_server/README.md)
backend/main.py              FastAPI routes
backend/team.py              the five agents, delegation, limits
backend/prompts/             one prompt file per agent + shared team rules
backend/models.py            data types
backend/audit.py             append-only audit trail (output/audit_trail.json)
backend/run_team.py          command-line runner
backend/build_reports.py     builds the output/ reports from the database + audit trail
frontend/                    React dashboard
output/                      harness.md, design.md, audit trail, reports, screenshots
```

## Setup

You need Python 3.12+, Node 20+, and a Portkey API key that routes to OpenAI.

```bash
git clone <this repo>
cd <repo>

# Python environment
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# API key
cp .env.example .env                 # then put your key in .env

# Dashboard dependencies
cd frontend && npm install && cd ..
```

## 1. Copy the original database to the working copy (for a clean run)

`data/campus_customs.db` is the original and is never modified. Everything reads and writes `data/campus_customs_new.db`. To get a clean working copy, overwrite it with the original:

```bash
cp data/campus_customs.db data/campus_customs_new.db          # macOS / Linux / Git Bash
copy data\campus_customs.db data\campus_customs_new.db        # Windows cmd
```

Or let the project do it. This also checks the copy and records the reset in the audit trail:

```bash
python backend/run_team.py --reset
```

The working copy in this repo is in its post-run state: all three tickets are resolved and checking is at $160.00. Reset it before running anything yourself.

## 2. Start the MCP server

The backend starts the MCP server on its own (over stdio) whenever it needs it, so you don't have to run it separately to use the app. To run it on its own, for example to test the tools or connect another MCP client:

```bash
python mcp_server/server.py          # stdio
python mcp_server/server.py --http   # http://127.0.0.1:8001/mcp
```

`.mcp.json` at the repo root registers the same server for Claude Code (`.venv/Scripts/python.exe` is the Windows path; on macOS/Linux change it to `.venv/bin/python`).

## 3. Start the FastAPI backend

```bash
cd backend
uvicorn main:app --reload --port 8000
```

API docs: http://localhost:8000/docs. The routes are listed in `output/harness.md`.

## 4. Start the React board

In a second terminal:

```bash
cd frontend
npm run dev
```

Open the URL Vite prints (usually http://localhost:5173). The board calls the backend at `http://localhost:8000`, and the backend's CORS settings allow the Vite page.

## 5. Reset the database before a full three-ticket run

Always start a full run from the original data:

1. Reset the working copy. Use **Reset database** on the dashboard's top bar, `POST /api/reset`, or `python backend/run_team.py --reset`. Checking should read **$3,400.00**.
2. Press **Run agents** on tickets 101, 102 and 103, one at a time. Watch the agent cards and live activity feed.
3. In **Human approvals**, enter your name and approve or reject each request. Approve invoice 501 before the tee purchase order, because the vendor won't ship while it's unpaid. Checking drops after each approved payment.
4. Press **Run again** on each ticket so the boss confirms what you did and marks the ticket resolved.

You can also do a full run from the command line, with no dashboard. It resets first:

```bash
cd backend
python run_team.py --all
```

Rebuild the reports from the finished run:

```bash
python backend/build_reports.py
```

## Results of the submitted run

- `output/desk_tickets.html`: one tab per ticket (expected vs actual, outcome, approvals, drafts), a cash ledger, and reflections.
- `output/resolved_tickets.json` and `output/resolved_board.html` (screenshots of the board).
- `output/audit_trail.json`: every agent loop, with its tool calls, delegations and token use.
- `output/harness.md`: tables, MCP tools, agents, routes, dashboard, and safety rules.
- `ai_prompts.md`: the prompts used to build the project.

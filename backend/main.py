"""Campus Customs back office API.

Start from the backend/ folder:  uvicorn main:app --reload --port 8000

Routes
  GET  /api/tickets                     every ticket and whether it is open or resolved
  GET  /api/tickets/{ticket_id}/summary what each agent did on the ticket's latest run (from the audit trail)
  POST /api/tickets/{ticket_id}/run     start the agent team on one ticket (runs in the background)
  GET  /api/runs/{run_id}               a run's status and the boss's final decision
  GET  /api/events?since=N              recent agent events: who said what, which tool, delegations
  GET  /api/approvals                   payment / purchase-order requests waiting on a human
  GET  /api/drafts                      message drafts on the board (never sent)
  POST /api/approvals/{id}/approve      human approves: pays (payments) or places the order (POs)
  POST /api/approvals/{id}/reject       human rejects: nothing moves
  GET  /api/cash                        current checking balance from cash_accounts
  POST /api/reset                       copy the original database over the working copy

Agents only file requests. Money moves only through /approve, which calls the MCP
server's human-only tools (pay, place_purchase_order). Those tools refuse if cash
would go negative or the vendor still has unpaid invoices.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections import deque
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import db
import team
from models import TeamEvent, TicketRunResult

MAX_EVENTS = 2000  # in-memory ring buffer for the dashboard; the audit trail keeps everything
AGENT_DONE = {"resolved", "waiting_on_approval"}  # the team is finished; at most a human step remains


# ---------- Request / response bodies ----------

class TicketSummary(BaseModel):
    id: int
    type: str
    requester: str
    subject: str
    sku: str | None
    size: str | None
    qty: int | None
    lease_id: int | None
    invoice_id: int | None
    status: str = Field(description="Raw status: open, in_progress, waiting_on_approval, or resolved.")
    state: Literal["open", "resolved"] = Field(
        description="resolved once the agent team has finished the ticket (status resolved or "
        "waiting_on_approval, i.e. only a human step remains); otherwise open."
    )
    notes: str | None
    created_at: str
    running: bool = Field(description="True while the agent team is working this ticket.")


class RunStarted(BaseModel):
    run_id: str
    ticket_id: int
    status: Literal["running"]


class RunStatus(BaseModel):
    run_id: str
    ticket_id: int
    status: Literal["running", "done", "error"]
    result: TicketRunResult | None = None


class EventOut(TeamEvent):
    seq: int


class EventsPage(BaseModel):
    events: list[EventOut]
    last_seq: int = Field(description="Pass as ?since= on the next poll to get only newer events.")


class HumanDecision(BaseModel):
    approved_by: str = Field(min_length=1, max_length=80, description="Name of the person clicking approve.")
    note: str | None = Field(default=None, max_length=500)


class CashBalance(BaseModel):
    account: str
    balance: float
    as_of: str
    date_today: str


# ---------- In-memory state ----------

events: deque[EventOut] = deque(maxlen=MAX_EVENTS)
_seq = 0
runs: dict[str, RunStatus] = {}
running_tickets: dict[int, str] = {}  # ticket_id -> run_id


def record_event(event: TeamEvent) -> None:
    global _seq
    _seq += 1
    events.append(EventOut(seq=_seq, **event.model_dump()))


def system_event(kind: str, **detail) -> None:
    """Board-level events (approvals, resets) so the dashboard feed shows human actions too."""
    record_event(TeamEvent(
        time=team.audit.now(), run_id="system", agent_run_id="system", agent="boss",
        ticket_id=detail.pop("ticket_id", None), type="tool_result", detail={"tool": kind, "result": detail},
    ))


def rebuild_feed() -> None:
    """Refill the in-memory feed after a restart: agent steps from the audit trail and human
    decisions from the approvals table, since the last reset, in time order."""
    rebuilt: list[TeamEvent] = []
    for r in records_since_reset():
        base = dict(run_id=r["run_id"], agent_run_id=r["agent_run_id"], agent=r["agent"], ticket_id=r["ticket_id"])
        rebuilt.append(TeamEvent(time=r["started"], type="agent_start", detail={"task": r["task"], "chain": r["chain"]}, **base))
        for s in r.get("steps", []):
            detail = {k: v for k, v in s.items() if k not in ("time", "type")}
            if s["type"] in ("tool_call", "tool_result", "model_text", "retry", "delegate"):
                rebuilt.append(TeamEvent(time=s.get("time") or r["started"], type=s["type"], detail=detail, **base))
        rebuilt.append(TeamEvent(time=r["finished"], type="agent_end", detail={
            "stop_reason": r.get("stop_reason"), "output": r.get("output"), "usage": r.get("usage_this_agent")}, **base))
    try:
        conn = db.read_conn()
        try:
            decided = conn.execute("SELECT * FROM approvals WHERE decided_at IS NOT NULL").fetchall()
        finally:
            conn.close()
    except Exception:
        decided = []  # no workflow tables yet (fresh reset)
    for a in decided:
        if a["status"] == "rejected":
            kind, result = "human_reject", {"approval_id": a["id"], "rejected_by": a["decided_by"]}
        else:
            outcome = {"paid": a["status"] == "paid", "ordered": a["status"] == "ordered", "amount": a["amount"]}
            kind, result = "human_approve", {"approval_id": a["id"], "approved_by": a["decided_by"], "outcome": outcome}
        rebuilt.append(TeamEvent(time=a["decided_at"], run_id="system", agent_run_id="system", agent="boss",
                                 ticket_id=a["ticket_id"], type="tool_result", detail={"tool": kind, "result": result}))
    for e in sorted(rebuilt, key=lambda e: e.time):
        record_event(e)



# The MCP server process is only open while it is needed (an agent run or an approve/reject
# call), not for the app's whole lifetime: an idle stdio child process on Windows keeps
# `uvicorn --reload` from shutting the old worker down.
app = FastAPI(title="Campus Customs back office")
# Let the Vite dashboard (usually http://localhost:5173) call these routes from the browser.
# Any localhost port is allowed because Vite moves to 5174, 5175, ... when 5173 is taken.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)


async def call_mcp(tool: str, args: dict[str, Any]) -> dict:
    """Call an MCP tool directly (no agent involved). Tool errors become HTTP 409."""
    try:
        async with team.MCP:  # reuses the connection if an agent run already has it open
            result = await team.MCP.direct_call_tool(tool, args)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(result, str):
        result = json.loads(result)
    return result


# ---------- Tickets ----------

@app.get("/api/tickets", response_model=list[TicketSummary])
def list_tickets() -> list[TicketSummary]:
    conn = db.read_conn()
    try:
        rows = conn.execute("SELECT * FROM tickets ORDER BY id").fetchall()
    finally:
        conn.close()
    return [
        TicketSummary(**dict(r), state="resolved" if r["status"] in AGENT_DONE else "open",
                      running=r["id"] in running_tickets)
        for r in rows
    ]


def records_since_reset() -> list[dict]:
    """Audit records since the most recent database reset (resets leave a marker in the trail)."""
    if not team.audit.AUDIT_PATH.exists():
        return []
    records = json.loads(team.audit.AUDIT_PATH.read_text(encoding="utf-8"))
    last = max((i for i, r in enumerate(records) if r.get("type") == "reset"), default=-1)
    return [r for r in records[last + 1:] if "agent" in r]


@app.get("/api/tickets/{ticket_id}/summary")
def ticket_summary(ticket_id: int) -> dict:
    """What each agent did on this ticket across every run since the last reset (from the audit trail).

    `decision` is the boss's most recent final call.
    """
    records = [r for r in records_since_reset() if r.get("ticket_id") == ticket_id]
    owners = [r for r in records if r.get("role") == "ticket_owner"]
    if not owners:
        return {"ticket_id": ticket_id, "run_id": None, "agents": [], "decision": None}
    latest = owners[-1]
    agents: dict[str, dict] = {}
    for r in records:
        a = agents.setdefault(r["agent"], {"agent": r["agent"], "runs": 0, "tools": [], "delegated_to": [],
                                           "summaries": [], "approval_ids": [], "draft_ids": []})
        a["runs"] += 1
        for s in r.get("steps", []):
            if s["type"] == "tool_call" and s["tool"] not in a["tools"]:
                a["tools"].append(s["tool"])
            elif s["type"] == "delegate" and s.get("to"):
                a["delegated_to"].append(s["to"])
        out = r.get("output") or {}
        text = out.get("summary") or out.get("decision")
        if text:
            a["summaries"].append(text)
        a["approval_ids"] += [i for i in out.get("approval_ids", []) if i not in a["approval_ids"]]
        a["draft_ids"] += [i for i in out.get("draft_ids", []) if i not in a["draft_ids"]]
        if r.get("stop_reason") != "final_output":
            a["summaries"].append(f"Stopped: {r.get('stop_reason')}")
    return {"ticket_id": ticket_id, "run_id": latest["run_id"], "runs": len(owners),
            "finished": latest.get("finished"), "decision": latest.get("output"), "agents": list(agents.values())}


@app.post("/api/tickets/{ticket_id}/run", response_model=RunStarted, status_code=202)
async def run_ticket(ticket_id: int) -> RunStarted:
    if db.ticket_status(ticket_id) is None:
        raise HTTPException(status_code=404, detail=f"No ticket with id {ticket_id}.")
    if ticket_id in running_tickets:
        raise HTTPException(status_code=409, detail=f"Ticket {ticket_id} is already running ({running_tickets[ticket_id]}).")

    run_id = uuid.uuid4().hex[:12]
    runs[run_id] = RunStatus(run_id=run_id, ticket_id=ticket_id, status="running")
    running_tickets[ticket_id] = run_id

    async def work() -> None:
        try:
            result = await team.run_ticket(ticket_id, run_id=run_id, on_event=record_event)
            runs[run_id] = RunStatus(run_id=run_id, ticket_id=ticket_id,
                                     status="error" if result.error else "done", result=result)
        except Exception as exc:  # run_ticket already catches; this is a last resort
            runs[run_id] = RunStatus(run_id=run_id, ticket_id=ticket_id, status="error",
                                     result=TicketRunResult(run_id=run_id, ticket_id=ticket_id, error=str(exc)))
        finally:
            running_tickets.pop(ticket_id, None)

    asyncio.create_task(work())
    return RunStarted(run_id=run_id, ticket_id=ticket_id, status="running")


@app.get("/api/runs/{run_id}", response_model=RunStatus)
def get_run(run_id: str) -> RunStatus:
    if run_id not in runs:
        raise HTTPException(status_code=404, detail=f"No run {run_id}.")
    return runs[run_id]


# ---------- Agent events (dashboard feed) ----------

@app.get("/api/events", response_model=EventsPage)
def recent_events(
    since: int = Query(0, ge=0, description="Only events with seq greater than this."),
    ticket_id: int | None = None,
    limit: int = Query(200, ge=1, le=MAX_EVENTS),
) -> EventsPage:
    picked = [e for e in events if e.seq > since and (ticket_id is None or e.ticket_id == ticket_id)]
    return EventsPage(events=picked[-limit:], last_seq=_seq)


# ---------- Human approvals ----------

@app.get("/api/approvals")
async def list_approvals(status: str = "pending") -> dict:
    return await call_mcp("list_approvals", {"status": status})


@app.get("/api/drafts")
async def list_drafts(ticket_id: int | None = None) -> dict:
    """Message drafts on the board. They are never sent."""
    return await call_mcp("list_drafts", {"ticket_id": ticket_id})


@app.post("/api/approvals/{approval_id}/approve")
async def approve(approval_id: int, body: HumanDecision) -> dict:
    found = (await call_mcp("list_approvals", {"status": "all"}))["approvals"]
    req = next((a for a in found if a["id"] == approval_id), None)
    if req is None:
        raise HTTPException(status_code=404, detail=f"No approval request {approval_id}.")
    if req["kind"] == "purchase_order":
        result = await call_mcp("place_purchase_order", {"approval_id": approval_id, "approved_by": body.approved_by})
    else:
        result = await call_mcp("pay", {"approval_id": approval_id, "approved_by": body.approved_by})
    system_event("human_approve", ticket_id=req["ticket_id"], approval_id=approval_id,
                 approved_by=body.approved_by, outcome=result)
    if result.get("refused"):
        raise HTTPException(status_code=409, detail=result["reason"])
    return result


@app.post("/api/approvals/{approval_id}/reject")
async def reject(approval_id: int, body: HumanDecision) -> dict:
    result = await call_mcp("reject_request", {
        "approval_id": approval_id, "rejected_by": body.approved_by,
        "reason": body.note or "Rejected on the dashboard.",
    })
    system_event("human_reject", approval_id=approval_id, rejected_by=body.approved_by)
    return result


# ---------- Cash ----------

@app.get("/api/cash", response_model=CashBalance)
def cash() -> CashBalance:
    conn = db.read_conn()
    try:
        row = conn.execute("SELECT * FROM cash_accounts WHERE name = 'checking'").fetchone()
        today = conn.execute("SELECT date_today FROM desk LIMIT 1").fetchone()["date_today"]
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="No checking account in cash_accounts.")
    return CashBalance(account=row["name"], balance=row["balance"], as_of=row["date"], date_today=today)


# ---------- Reset ----------

@app.post("/api/reset")
def reset() -> dict:
    if running_tickets:
        raise HTTPException(status_code=409, detail=f"Agents are still running on tickets {sorted(running_tickets)}.")
    result = db.reset_database()
    system_event("reset_database", **result)
    return result


# Startup: show the agents' work since the last reset even after a backend restart.
rebuild_feed()

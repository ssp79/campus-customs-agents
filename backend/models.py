"""Data types shared by the agent team, the audit trail, and (later) the API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal

from pydantic import BaseModel, Field

AgentName = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]
AGENTS: tuple[AgentName, ...] = ("boss", "inventory", "accounting", "facilities", "customer_service")

TicketStatus = Literal["open", "in_progress", "waiting_on_approval", "resolved"]


# ---------- What agents return ----------

class Finding(BaseModel):
    """One fact an agent learned, with where it came from so a reviewer can check it."""

    fact: str = Field(description="A single fact, with exact numbers/dates/ids as the tool returned them.")
    source: str = Field(description='Tool and table it came from, e.g. "check_stock (inventory)".')


class AgentReport(BaseModel):
    """What every specialist (and the boss, when delegated to) hands back to the agent that asked."""

    agent: AgentName
    summary: str = Field(description="Two or three sentences answering the task you were given.")
    findings: list[Finding] = Field(default_factory=list)
    actions_taken: list[str] = Field(
        default_factory=list,
        description="Write tools you called and what they did, e.g. 'request_payment -> approval 1 ($840.00)'.",
    )
    approval_ids: list[int] = Field(default_factory=list, description="approvals.id values you created.")
    draft_ids: list[int] = Field(default_factory=list, description="drafts.id values you created.")
    blockers: list[str] = Field(default_factory=list, description="Anything stopping the ticket from closing.")
    recommendation: str = Field(description="What you think the boss should decide next.")


class TicketDecision(BaseModel):
    """The boss's final call on one ticket."""

    ticket_id: int
    decision: str = Field(description="The final call in plain English, with the key numbers.")
    final_status: TicketStatus = Field(description="Must equal the status you set with update_ticket.")
    assigned_to: list[AgentName] = Field(description="Agents that worked the ticket.")
    findings: list[Finding] = Field(default_factory=list)
    approval_ids: list[int] = Field(default_factory=list, description="Approval requests a human must act on.")
    draft_ids: list[int] = Field(default_factory=list, description="Drafts waiting on the board for review.")
    human_actions_needed: list[str] = Field(
        default_factory=list, description="Exactly what the human approver needs to do, in order."
    )
    next_steps: list[str] = Field(default_factory=list, description="What happens after the human acts.")


# ---------- Run bookkeeping ----------

class TeamEvent(BaseModel):
    """One live step from any agent loop. Streamed to the dashboard and written to the audit trail."""

    time: str
    run_id: str
    agent_run_id: str
    agent: AgentName
    ticket_id: int | None = None
    type: Literal[
        "agent_start", "model_text", "tool_call", "tool_result", "retry",
        "delegate", "delegate_refused", "agent_end", "error",
    ]
    detail: dict[str, Any] = Field(default_factory=dict)


class TicketRunResult(BaseModel):
    run_id: str
    ticket_id: int
    decision: TicketDecision | None = None
    error: str | None = None
    usage: dict[str, int] = Field(default_factory=dict)


@dataclass
class RunBudget:
    """Shared across every agent working the same ticket, so limits apply to the whole team."""

    delegations: int = 0
    agent_runs: int = 0


EventSink = Callable[[TeamEvent], Awaitable[None] | None]


@dataclass
class TeamDeps:
    """Per-agent-run context. A delegated run gets a copy with the chain extended by one."""

    run_id: str
    ticket_id: int | None
    agent: AgentName
    agent_run_id: str
    parent_agent_run_id: str | None = None
    chain: list[AgentName] = field(default_factory=list)
    budget: RunBudget = field(default_factory=RunBudget)
    on_event: EventSink | None = None

"""The Campus Customs agent team: five PydanticAI agents with full connectivity.

  boss              routes tickets, makes the final call, sets ticket status
  inventory         stock by SKU/size, shortfalls, restock vendor and lead time
  accounting        cash, invoices, margins; files payment / PO requests for humans
  facilities        leases and rent
  customer_service  drafts messages (never sent)

Every agent shares one MCP connection to mcp_server/server.py, filtered to the
tools its role needs. Every agent also has `delegate(to, task)`, which runs any
other agent as a nested agent loop and returns its AgentReport, so any agent
can ask any other for help. Loop guards: no agent can appear twice in one
delegation chain, chains are at most MAX_CHAIN deep, and the whole team shares
one per-ticket budget of delegations, model requests and tokens.

Each agent loop writes one record to output/audit_trail.json (see audit.py).
"""

from __future__ import annotations

import os
import sys
import uuid
from functools import lru_cache
from pathlib import Path

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from dotenv import load_dotenv
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from openai import AsyncOpenAI
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.messages import ModelResponse
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import RunUsage, UsageLimits

import audit
import db
from models import (
    AGENTS,
    AgentName,
    AgentReport,
    EventSink,
    RunBudget,
    TeamDeps,
    TeamEvent,
    TicketDecision,
    TicketRunResult,
)

HERE = Path(__file__).resolve().parent
HW_DIR = HERE.parent
PROMPTS = HERE / "prompts"

# The key lives in the AI Foundations root .env (a project-level .env is checked first).
load_dotenv(HW_DIR / ".env")
load_dotenv(HW_DIR.parent / ".env", override=False)

# Every agent uses this model. It is deliberately not read from the environment.
MODEL_NAME = "gpt-6-luna"

# ---------- Limits (token and loop control) ----------
MAX_CHAIN = 3                # boss -> specialist -> specialist; a 4th hop is refused
MAX_DELEGATIONS = 8          # per ticket, whole team
MAX_AGENT_RUNS = 9           # per ticket: the boss plus at most 8 delegated runs
TICKET_LIMITS = UsageLimits(  # shared by every agent loop on one ticket
    request_limit=45,
    tool_calls_limit=80,
    total_tokens_limit=400_000,
)
OUTPUT_RETRIES = 2           # retries for invalid structured output or tool errors


# ---------- Model ----------

@lru_cache(maxsize=1)
def make_model() -> OpenAIResponsesModel:
    key = (os.getenv("PORTKEY_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("PORTKEY_API_KEY is missing from the AI Foundations .env file")
    client = AsyncOpenAI(
        base_url="https://api.portkey.ai/v1",
        timeout=120,      # one hung model call must not stall a ticket (the SDK default is 600 s)
        max_retries=1,
        api_key=key,
        default_headers={"x-portkey-api-key": key, "x-portkey-provider": "openai"},
    )
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))


# ---------- MCP tools, split by role ----------

MCP_SERVER = HW_DIR / "mcp_server" / "server.py"
MCP = MCPToolset(
    # keep_alive=False: the server process exits when no run or approval is using it, so
    # nothing lingers to block `uvicorn --reload` on Windows.
    Client(StdioTransport(command=sys.executable, args=[str(MCP_SERVER)], cwd=str(HW_DIR), keep_alive=False)),
    max_retries=OUTPUT_RETRIES,
)

READ_TOOLS = {
    "list_tickets", "check_stock", "get_vendor_status", "get_cash_position",
    "get_leases", "check_margin", "list_approvals", "list_drafts",
}
AGENT_TOOLS: dict[AgentName, set[str]] = {
    "boss": READ_TOOLS | {"update_ticket"},
    "inventory": READ_TOOLS,
    "accounting": READ_TOOLS | {"request_payment", "request_purchase_order"},
    "facilities": READ_TOOLS,
    "customer_service": READ_TOOLS | {"draft_customer_message"},
}
# Money-moving tools exist on the server for the human approval endpoints only.
HUMAN_ONLY_TOOLS = {"pay", "place_purchase_order", "reject_request"}
assert not any(HUMAN_ONLY_TOOLS & tools for tools in AGENT_TOOLS.values())


def toolset_for(agent: AgentName):
    allowed = frozenset(AGENT_TOOLS[agent])
    return MCP.filtered(lambda ctx, tool_def: tool_def.name in allowed)


# ---------- Events ----------

async def emit(deps: TeamDeps, type_: str, **detail) -> None:
    if deps.on_event is None:
        return
    event = TeamEvent(
        time=audit.now(), run_id=deps.run_id, agent_run_id=deps.agent_run_id,
        agent=deps.agent, ticket_id=deps.ticket_id, type=type_, detail=detail,
    )
    maybe = deps.on_event(event)
    if hasattr(maybe, "__await__"):
        await maybe


# ---------- Delegation (full connectivity) ----------

async def delegate(ctx: RunContext[TeamDeps], to: AgentName, task: str) -> AgentReport | str:
    """Hand a task to another agent and wait for its report.

    to: boss, inventory, accounting, facilities, or customer_service (anyone but you).
    task: a complete, self-contained instruction. The other agent cannot see your
    conversation, so include the ticket id, every SKU/size/qty or invoice/lease/vendor
    id, what you need back, and any write action you want them to take.
    """
    d = ctx.deps
    refusal = None
    if to not in AGENTS:
        refusal = f"Unknown agent '{to}'. Choose from {list(AGENTS)}."
    elif to == d.agent:
        refusal = "You cannot delegate to yourself. Use your own tools."
    elif to in d.chain:
        refusal = (f"{to} is already part of this delegation chain ({' -> '.join(d.chain)}), "
                   "so it is waiting on you. Answer with what you have.")
    elif len(d.chain) >= MAX_CHAIN:
        refusal = (f"Delegation chain limit reached ({' -> '.join(d.chain)}). "
                   "Finish with your own tools and report back.")
    elif d.budget.delegations >= MAX_DELEGATIONS or d.budget.agent_runs >= MAX_AGENT_RUNS:
        refusal = "The team's delegation budget for this ticket is used up. Finish with what you have."
    if refusal:
        await emit(d, "delegate_refused", to=to, task=task, reason=refusal)
        return f"DELEGATION REFUSED: {refusal}"

    d.budget.delegations += 1
    await emit(d, "delegate", to=to, task=task)
    return await run_agent(to, task, run_id=d.run_id, ticket_id=d.ticket_id, parent=d,
                           budget=d.budget, usage=ctx.usage, on_event=d.on_event)


# ---------- Agents ----------

TEAM_RULES = (PROMPTS / "team_rules.md").read_text(encoding="utf-8")


def _instructions(agent: AgentName) -> str:
    return TEAM_RULES + "\n\n" + (PROMPTS / f"{agent}.md").read_text(encoding="utf-8")


def _check_ids(approval_ids: list[int], draft_ids: list[int]) -> None:
    bad_a, bad_d = db.missing_ids("approvals", approval_ids), db.missing_ids("drafts", draft_ids)
    if bad_a or bad_d:
        raise ModelRetry(
            f"These ids do not exist in the database: approvals {bad_a}, drafts {bad_d}. "
            "Only report ids that a tool returned (check list_approvals / list_drafts)."
        )


def _build(agent: AgentName, output_type):
    a = Agent(
        name=agent,
        model=make_model(),
        deps_type=TeamDeps,
        output_type=output_type,
        instructions=_instructions(agent),
        toolsets=[toolset_for(agent)],
        tools=[delegate],
        retries=OUTPUT_RETRIES,
    )

    @a.instructions
    def run_context(ctx: RunContext[TeamDeps]) -> str:
        chain = " -> ".join(ctx.deps.chain)
        others = ", ".join(n for n in AGENTS if n not in ctx.deps.chain)
        return (f"## This run\nYou are `{agent}`. Ticket: {ctx.deps.ticket_id}. "
                f"Delegation chain so far: {chain}. You can delegate to: {others or 'nobody (answer yourself)'}.")

    return a


REPORT_AGENTS: dict[AgentName, Agent] = {name: _build(name, AgentReport) for name in AGENTS}
BOSS = _build("boss", TicketDecision)  # the boss as ticket owner returns the final decision


for _agent in REPORT_AGENTS.values():
    @_agent.output_validator
    def _validate_report(ctx: RunContext[TeamDeps], output: AgentReport) -> AgentReport:
        _check_ids(output.approval_ids, output.draft_ids)
        return output.model_copy(update={"agent": ctx.deps.agent})


@BOSS.output_validator
def _validate_decision(ctx: RunContext[TeamDeps], output: TicketDecision) -> TicketDecision:
    if output.ticket_id != ctx.deps.ticket_id:
        raise ModelRetry(f"You were given ticket {ctx.deps.ticket_id}, not {output.ticket_id}.")
    actual = db.ticket_status(output.ticket_id)
    if actual != output.final_status:
        raise ModelRetry(
            f"final_status is '{output.final_status}' but the ticket's status in the database is "
            f"'{actual}'. Call update_ticket to set the status you decided on, then report it."
        )
    _check_ids(output.approval_ids, output.draft_ids)
    return output


# ---------- One agent loop ----------

async def run_agent(
    agent: AgentName,
    task: str,
    *,
    run_id: str,
    ticket_id: int | None,
    parent: TeamDeps | None,
    budget: RunBudget,
    usage: RunUsage,
    on_event: EventSink | None,
    as_ticket_owner: bool = False,
):
    """Run one agent's loop, stream its steps as events, and write its audit record."""
    deps = TeamDeps(
        run_id=run_id,
        ticket_id=ticket_id,
        agent=agent,
        agent_run_id=uuid.uuid4().hex[:12],
        parent_agent_run_id=parent.agent_run_id if parent else None,
        chain=(parent.chain if parent else []) + [agent],
        budget=budget,
        on_event=on_event,
    )
    budget.agent_runs += 1
    runner = BOSS if as_ticket_owner else REPORT_AGENTS[agent]
    record = {
        "run_id": run_id,
        "agent_run_id": deps.agent_run_id,
        "parent_agent_run_id": deps.parent_agent_run_id,
        "ticket_id": ticket_id,
        "agent": agent,
        "role": "ticket_owner" if as_ticket_owner else "delegate",
        "chain": deps.chain,
        "model": MODEL_NAME,
        "tools_available": sorted(AGENT_TOOLS[agent]) + ["delegate"],
        "task": task,
        "started": audit.now(),
    }
    await emit(deps, "agent_start", task=task, chain=deps.chain)
    steps: list[dict] = []
    output = None
    agent_run = None
    try:
        async with runner.iter(task, deps=deps, usage=usage, usage_limits=TICKET_LIMITS) as agent_run:
            seen = 0
            async for _node in agent_run:
                messages = agent_run.all_messages()
                for step in audit.steps_from_messages(messages[seen:]):
                    steps.append(step)
                    if step["type"] in ("model_text", "tool_call", "tool_result", "retry"):
                        await emit(deps, step["type"], **{k: v for k, v in step.items() if k not in ("time", "type")})
                seen = len(messages)
        output = agent_run.result.output
        record["stop_reason"] = "final_output"
    except UsageLimitExceeded as exc:
        record["stop_reason"] = f"usage_limit: {exc}"
        await emit(deps, "error", reason=record["stop_reason"])
        raise
    except Exception as exc:
        record["stop_reason"] = f"error: {type(exc).__name__}: {audit.clip(str(exc), 300)}"
        await emit(deps, "error", reason=record["stop_reason"])
        raise
    finally:
        if agent_run is not None and len(steps) == 0:
            steps = audit.steps_from_messages(agent_run.all_messages())
        record["steps"] = steps
        record["step_count"] = len(steps)
        record["output"] = output.model_dump(mode="json") if output is not None else None
        # Counted from this loop's own responses: the shared `usage` also grows from
        # delegated agents running in parallel, so a before/after diff would overcount.
        responses = [m for m in (agent_run.all_messages() if agent_run else []) if isinstance(m, ModelResponse)]
        record["usage_this_agent"] = {
            "requests": len(responses),
            "input_tokens": sum(m.usage.input_tokens for m in responses),
            "output_tokens": sum(m.usage.output_tokens for m in responses),
        }
        record["usage_ticket_so_far"] = {
            "requests": usage.requests, "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens, "delegations": budget.delegations,
            "agent_runs": budget.agent_runs,
        }
        record["finished"] = audit.now()
        audit.append_record(record)
        await emit(deps, "agent_end", stop_reason=record.get("stop_reason"),
                   output=record["output"], usage=record["usage_this_agent"])
    return output


# ---------- Tickets and the board ----------

async def run_ticket(ticket_id: int, *, run_id: str | None = None, on_event: EventSink | None = None) -> TicketRunResult:
    """The boss owns the ticket and delegates as needed. Returns the boss's final decision."""
    run_id = run_id or uuid.uuid4().hex[:12]
    usage = RunUsage()
    task = (f"Work ticket {ticket_id}. Start by reading it with list_tickets (status 'all'), "
            "route it to the right specialists, make the final call, set the ticket status with "
            "update_ticket, and return your TicketDecision.")
    result = TicketRunResult(run_id=run_id, ticket_id=ticket_id)
    try:
        async with MCP:
            result.decision = await run_agent(
                "boss", task, run_id=run_id, ticket_id=ticket_id, parent=None,
                budget=RunBudget(), usage=usage, on_event=on_event, as_ticket_owner=True,
            )
    except Exception as exc:
        result.error = f"{type(exc).__name__}: {exc}"
    result.usage = {"requests": usage.requests, "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens}
    return result


async def run_board(*, reset: bool = True, on_event: EventSink | None = None) -> list[TicketRunResult]:
    """Full run: reset the working copy to the original, then work every open ticket in order.

    Tickets run one at a time so each sees the cash and approval requests left by the last.
    """
    if reset:
        db.reset_database()
    run_id = uuid.uuid4().hex[:12]
    results = []
    async with MCP:
        for ticket_id in db.open_ticket_ids():
            results.append(await run_ticket(ticket_id, run_id=run_id, on_event=on_event))
    return results

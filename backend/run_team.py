"""Run the agent team from the command line.

  python backend/run_team.py --all              reset the working DB, then work every open ticket
  python backend/run_team.py --ticket 102       work one ticket (no reset)
  python backend/run_team.py --reset            only reset the working DB

Each agent step prints as it happens; every agent loop is also appended to
output/audit_trail.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json

import db
from models import TeamEvent


def print_event(event: TeamEvent) -> None:
    d = event.detail
    who = f"[{event.ticket_id}] {event.agent:<16}"
    if event.type == "agent_start":
        print(f"{who} START  chain={' -> '.join(d['chain'])}")
    elif event.type == "delegate":
        print(f"{who} DELEGATE -> {d['to']}: {d['task'][:140]}")
    elif event.type == "delegate_refused":
        print(f"{who} DELEGATE REFUSED -> {d['to']}: {d['reason']}")
    elif event.type == "tool_call":
        print(f"{who} call  {d['tool']}({json.dumps(d['args'])[:140]})")
    elif event.type == "tool_result":
        print(f"{who} result {d['tool']}: {str(d['result'])[:140]}")
    elif event.type == "retry":
        print(f"{who} RETRY {d.get('tool')}: {str(d['reason'])[:140]}")
    elif event.type == "agent_end":
        print(f"{who} END    {d['stop_reason']}  usage={d['usage']}")
    elif event.type == "error":
        print(f"{who} ERROR  {d['reason']}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Campus Customs agent team")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="reset the DB, then work every open ticket")
    group.add_argument("--ticket", type=int, help="work one ticket without resetting")
    group.add_argument("--reset", action="store_true", help="only reset the working DB")
    args = parser.parse_args()

    if args.reset:
        print(db.reset_database())
        return

    import team  # imported here so --reset works without an API key

    if args.all:
        results = await team.run_board(reset=True, on_event=print_event)
    else:
        results = [await team.run_ticket(args.ticket, on_event=print_event)]

    for r in results:
        print("\n" + "=" * 70)
        print(f"Ticket {r.ticket_id}  usage={r.usage}")
        print(r.error or json.dumps(r.decision.model_dump(), indent=2))


if __name__ == "__main__":
    asyncio.run(main())

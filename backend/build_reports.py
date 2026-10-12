"""Build the Problem 9 reports from the working database and the audit trail.

  python backend/build_reports.py

Writes (all from data, nothing typed by hand):
  output/desk_tickets.html     one tab per ticket (Expected from harness.md + Actual from the runs) and a Cash tab
  output/resolved_tickets.json per ticket: id, final status, outcome, each agent's contribution, human approvals
  output/resolved_board.html   the dashboard screenshots in output/screenshots/, embedded so the page opens offline

The cash math is checked against cash_accounts in data/campus_customs_new.db; the script
refuses to write anything if it does not match.
"""

from __future__ import annotations

import base64
import html
import json
import re
import sqlite3
from collections import Counter, OrderedDict
from pathlib import Path

HW = Path(__file__).resolve().parent.parent
OUT = HW / "output"
ORIGINAL_DB = HW / "data" / "campus_customs.db"
WORKING_DB = HW / "data" / "campus_customs_new.db"
AUDIT = OUT / "audit_trail.json"
HARNESS = OUT / "harness.md"
AGENT_LABEL = {"boss": "Boss", "inventory": "Inventory", "accounting": "Accounting",
               "facilities": "Facilities", "customer_service": "Customer Service"}


def esc(s) -> str:
    return html.escape(str(s))


def money(x: float) -> str:
    return f"-${abs(x):,.2f}" if x < 0 else f"${x:,.2f}"


def md_inline(s: str) -> str:
    s = esc(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    return re.sub(r"`(.+?)`", r"<code>\1</code>", s)


# ---------- Reflections (written by Sam after the full run; shown word for word) ----------

REFLECTIONS = [
    ("How would you evaluate the performance of the agents on each ticket, and why?",
     "Overall, I think the agents performed well, although there were some differences in how effectively they handled each ticket. For Ticket 101, the agents correctly identified that the T-shirt was out of stock and that an overdue $840 vendor invoice was preventing restocking. They coordinated between Inventory, Accounting, and Customer Service, considered the need to preserve enough cash for rent, and obtained human approval before paying the invoice and placing a purchase order. For Ticket 102, the agents correctly identified that rent was due in two days rather than overdue, confirmed sufficient cash was available, and requested human approval before making the payment. Ticket 103 was less successful initially. The agents correctly identified the inventory shortage and calculated the potential profit margin, but they initially proposed a $50 price without having received a specific discount request or approval. In the second run, they took a more cautious approach and declined to offer a discount without additional information. Overall, the agents were effective at gathering information and coordinating tasks, but the hoodie ticket showed some inconsistency in their decision-making."),
    ("For each ticket, how did Actual compare to the Expected plan you wrote earlier?",
     "The agents generally followed the workflows I expected, although they sometimes involved additional tools or agents. For Ticket 101, the Boss contacted Inventory first, as expected, and involved Accounting and Customer Service to address the unpaid invoice and customer communication. The agents also used additional tools, including checking existing approvals and drafts and requesting a purchase order. For Ticket 102, the Boss correctly contacted Facilities first, and Accounting verified the available cash and prepared the payment request. Customer Service was also involved in drafting an acknowledgment, which I hadn't anticipated. For Ticket 103, the Boss contacted Inventory first, while Accounting evaluated margins and Customer Service drafted a response. However, the agents did not request a purchase order, and their recommendation changed between the first and second runs. Overall, the agents followed the expected division of responsibilities, but the actual workflows involved more coordination and some decisions I hadn't predicted."),
    ("What would have been simpler as one agent with tools, and why?",
     "I think Ticket 102, the rent payment, would have been simpler to handle with a single agent rather than a multi-agent team. The task was relatively straightforward and involved checking the lease to confirm the rent amount and due date, verifying that sufficient cash was available, and preparing a payment request for human approval. A single agent with access to the lease, cash, and payment tools could have completed these steps without delegating between Facilities and Accounting. While having specialized agents helped separate responsibilities, it also added coordination that wasn't necessarily needed for such a routine task. The multi-agent approach was more valuable for tickets like the T-shirt order, where inventory availability, vendor restrictions, accounting, and customer communication were more interconnected."),
    ("Describe three new problems Campus Customs might face that this agent team could solve with the tools you built.",
     "One problem the team could handle is a situation where a vendor has multiple outstanding invoices that are preventing the shop from placing new orders. Accounting could review the invoices and available cash, while Inventory could identify which products are affected by the vendor's restrictions. A second example would be a customer requesting a large order of a different product. Inventory could check available stock and restocking options, Accounting could evaluate the profitability of the order, and Customer Service could draft a response explaining pricing and availability. A third example would be preparing for upcoming rent payments across multiple leases. Facilities could identify upcoming obligations, Accounting could assess whether sufficient cash is available, and the Boss could determine which payments should be prepared for human approval. All three situations could be handled using the existing tools because they rely on information already available in the shop's database."),
    ("Describe three new problems Campus Customs might face that this agent team could not solve with the tools you built, and explain the tools and agents you would need.",
     "One problem the team couldn't currently handle is a customer requesting a refund for a defective product. Although Customer Service could draft a response, the system doesn't have tools to verify past purchases, process returns, or issue refunds. This would require a Returns agent and additional tools for retrieving order histories, recording returns, and preparing refunds for human approval. A second problem would be a shipment that is delayed or lost in transit. Inventory can check vendor lead times, but it cannot track actual shipments or determine where an order is. A Shipping or Logistics agent with access to carrier tracking information would be needed. A third problem would be forecasting which products the shop should stock for the following month. While Inventory can check current stock levels, the existing tools don't provide historical sales trends or demand forecasts. A Sales Analytics agent with tools to retrieve historical sales data and forecast demand would allow the shop to make more informed purchasing decisions. These examples show that the effectiveness of the agent team depends not only on the agents themselves but also on the data and capabilities available through their tools."),
]

# The parts of the answers about each ticket, shown on that ticket's tab. (question number, excerpt)
TICKET_REFLECTIONS = {
    101: [
        (1, "For Ticket 101, the agents correctly identified that the T-shirt was out of stock and that an overdue $840 vendor invoice was preventing restocking. They coordinated between Inventory, Accounting, and Customer Service, considered the need to preserve enough cash for rent, and obtained human approval before paying the invoice and placing a purchase order."),
        (2, "For Ticket 101, the Boss contacted Inventory first, as expected, and involved Accounting and Customer Service to address the unpaid invoice and customer communication. The agents also used additional tools, including checking existing approvals and drafts and requesting a purchase order."),
    ],
    102: [
        (1, "For Ticket 102, the agents correctly identified that rent was due in two days rather than overdue, confirmed sufficient cash was available, and requested human approval before making the payment."),
        (2, "For Ticket 102, the Boss correctly contacted Facilities first, and Accounting verified the available cash and prepared the payment request. Customer Service was also involved in drafting an acknowledgment, which I hadn't anticipated."),
        (3, REFLECTIONS[2][1]),
    ],
    103: [
        (1, "Ticket 103 was less successful initially. The agents correctly identified the inventory shortage and calculated the potential profit margin, but they initially proposed a $50 price without having received a specific discount request or approval. In the second run, they took a more cautious approach and declined to offer a discount without additional information."),
        (2, "For Ticket 103, the Boss contacted Inventory first, while Accounting evaluated margins and Customer Service drafted a response. However, the agents did not request a purchase order, and their recommendation changed between the first and second runs."),
    ],
}
for _excerpts in TICKET_REFLECTIONS.values():
    for _q, _text in _excerpts:
        assert _text in REFLECTIONS[_q - 1][1], f"ticket excerpt is not word for word from answer {_q}"


# ---------- Load data ----------

def rows(db: Path, sql: str) -> list[dict]:
    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql)]
    finally:
        conn.close()


def audit_since_reset() -> list[dict]:
    records = json.loads(AUDIT.read_text(encoding="utf-8"))
    last = max((i for i, r in enumerate(records) if r.get("type") == "reset"), default=-1)
    return [r for r in records[last + 1:] if "agent" in r]


def expected_sections() -> dict[int, dict]:
    """Parse the Expected Behavior sections the user wrote into harness.md."""
    text = HARNESS.read_text(encoding="utf-8")
    block = text.split("## Expected Behavior per Open Ticket", 1)[1].split("\n## ", 1)[0]
    out = {}
    for part in re.split(r"\n### Ticket ", block)[1:]:
        tid = int(part[:3])
        lines = part.splitlines()
        tools_line = next((l for l in lines if "MCP tools they should use" in l), "")
        first_line = next((l for l in lines if "Boss calls first" in l), "")
        out[tid] = {
            "title": lines[0].strip(),
            "lines": [l for l in lines[1:] if l.strip()],
            "tools": set(re.findall(r"`(\w+)`", tools_line.split("Human")[0])),
            "first": re.sub(r"[^a-z_ ]", "", first_line.split(":**", 1)[-1].split(",")[0].lower()).strip().replace(" ", "_"),
        }
    return out


def md_block(lines: list[str]) -> str:
    """Tiny markdown -> HTML for the expected section (bullets, nested bullets, bold, code)."""
    out, depth = [], 0
    for line in lines:
        m = re.match(r"^(\s*)- (.*)$", line)
        if not m:
            while depth:
                out.append("</ul>"); depth -= 1
            out.append(f"<p>{md_inline(line.strip())}</p>")
            continue
        level = len(m.group(1)) // 2 + 1
        while depth < level:
            out.append("<ul>"); depth += 1
        while depth > level:
            out.append("</ul>"); depth -= 1
        out.append(f"<li>{md_inline(m.group(2))}</li>")
    while depth:
        out.append("</ul>"); depth -= 1
    return "\n".join(out)


# ---------- Build ----------

def build() -> None:
    tickets = {t["id"]: t for t in rows(WORKING_DB, "SELECT * FROM tickets ORDER BY id")}
    approvals = rows(WORKING_DB, "SELECT * FROM approvals ORDER BY id")
    payments = rows(WORKING_DB, "SELECT * FROM payments ORDER BY id")
    drafts = rows(WORKING_DB, "SELECT * FROM drafts ORDER BY id")
    tlog = rows(WORKING_DB, "SELECT * FROM ticket_log ORDER BY id")
    vendors = {v["id"]: v for v in rows(WORKING_DB, "SELECT * FROM vendors")}
    leases = {l["id"]: l for l in rows(WORKING_DB, "SELECT * FROM leases")}
    start_balance = rows(ORIGINAL_DB, "SELECT balance FROM cash_accounts WHERE name='checking'")[0]["balance"]
    end_balance_db = rows(WORKING_DB, "SELECT balance FROM cash_accounts WHERE name='checking'")[0]["balance"]
    records = audit_since_reset()
    expected = expected_sections()

    # ----- Cash ledger, ticket by ticket in the order they resolved -----
    resolved_at = {t: max(l["created_at"] for l in tlog if l["ticket_id"] == t and l["new_status"] == "resolved")
                   for t in tickets}
    pay_by_ref = {(p["kind"], p["ref_id"]): p for p in payments}
    ledger, balance = [], start_balance
    for tid in sorted(tickets, key=lambda t: resolved_at[t]):
        items = []
        for a in [a for a in approvals if a["ticket_id"] == tid]:
            if a["kind"] == "invoice_payment" and a["status"] == "paid":
                p = pay_by_ref[("invoice", a["ref_id"])]
                items.append({"what": f"Paid invoice {a['ref_id']} to {vendors[a['vendor_id']]['name']} "
                                      f"(approval {a['id']}, payment {p['id']}, approved by {p['approved_by']})",
                              "change": -p["amount"]})
            elif a["kind"] == "rent_payment" and a["status"] == "paid":
                p = pay_by_ref[("rent", a["ref_id"])]
                items.append({"what": f"Paid {leases[a['ref_id']]['space_name']} rent to {leases[a['ref_id']]['landlord']} "
                                      f"(lease {a['ref_id']}, approval {a['id']}, payment {p['id']}, approved by {p['approved_by']})",
                              "change": -p["amount"]})
            elif a["kind"] == "purchase_order":
                items.append({"what": f"Purchase order {a['id']}: {a['qty']} × {a['sku']} size {a['size']} from "
                                      f"{vendors[a['vendor_id']]['name']} for {money(a['amount'])}, {a['status']} by {a['decided_by']}. "
                                      "No cash moves when a PO is placed; the vendor bills later.",
                              "change": 0.0})
            elif a["status"] == "rejected":
                items.append({"what": f"Approval {a['id']} ({a['kind']}, {money(a['amount'])}) rejected by {a['decided_by']}; nothing paid",
                              "change": 0.0})
        if not items:
            items.append({"what": "No payment or purchase order was requested for this ticket", "change": 0.0})
        before = balance
        balance = round(balance + sum(i["change"] for i in items), 2)
        ledger.append({"ticket_id": tid, "resolved_at": resolved_at[tid], "items": items,
                       "balance_before": before, "balance_after": balance})

    paid_total = round(sum(p["amount"] for p in payments), 2)
    assert round(start_balance - paid_total, 2) == balance, "ledger and payments table disagree"
    assert balance == end_balance_db, f"ledger ends at {balance}, cash_accounts says {end_balance_db}"

    # ----- Per-ticket actual sections from the audit trail -----
    actual: dict[int, dict] = {}
    for tid in tickets:
        recs = [r for r in records if r["ticket_id"] == tid]
        runs = OrderedDict()
        for r in sorted(recs, key=lambda r: r["started"]):
            runs.setdefault(r["run_id"], []).append(r)
        run_list = []
        for i, (rid, rs) in enumerate(runs.items(), 1):
            owner = next(r for r in rs if r["role"] == "ticket_owner")
            delegations = [{"from": r["agent"], "to": s["to"], "task": s["task"]}
                           for r in rs for s in r["steps"] if s["type"] == "delegate"]
            agents = []
            for r in rs:
                tools = Counter(s["tool"] for s in r["steps"] if s["type"] == "tool_call")
                out = r.get("output") or {}
                agents.append({"agent": r["agent"], "chain": r["chain"], "tools": dict(tools),
                               "summary": out.get("summary") or out.get("decision") or r.get("stop_reason"),
                               "requests": r["usage_this_agent"]["requests"]})
            run_list.append({
                "n": i, "run_id": rid,
                "kind": "First run" if i == 1 else (
                    "Close-out run after human approvals" if any(a["ticket_id"] == tid for a in approvals) else "Second run"),
                "started": owner["started"], "finished": owner["finished"],
                "delegations": delegations, "agents": agents,
                "decision": owner["output"], "usage": owner["usage_ticket_so_far"],
            })
        first_delegate = next((d["to"] for run in run_list for d in run["delegations"]), None)
        used_tools = {t for run in run_list for a in run["agents"] for t in a["tools"]}
        actual[tid] = {"runs": run_list, "first_delegate": first_delegate, "tools": used_tools}

    write_resolved_json(tickets, actual, approvals, payments, drafts, tlog)
    write_desk_html(tickets, expected, actual, approvals, drafts, tlog, ledger, start_balance, end_balance_db, paid_total)
    write_board_html(tickets, actual, tlog)
    print(f"start {money(start_balance)} - paid {money(paid_total)} = {money(balance)}; cash_accounts = {money(end_balance_db)}  OK")


def write_resolved_json(tickets, actual, approvals, payments, drafts, tlog) -> None:
    out = []
    for tid, t in tickets.items():
        contrib: dict[str, list[str]] = OrderedDict()
        for run in actual[tid]["runs"]:
            for a in run["agents"]:
                label = f"Run {run['n']} ({run['kind'].lower()}): {a['summary']}"
                contrib.setdefault(a["agent"], []).append(label)
        human = []
        for a in [a for a in approvals if a["ticket_id"] == tid]:
            pay = next((p for p in payments if a["kind"] != "purchase_order"
                        and p["ref_id"] == a["ref_id"] and p["kind"] == a["kind"].split("_")[0]), None)
            human.append({"approval_id": a["id"], "kind": a["kind"], "amount": a["amount"], "requested_by": a["requested_by"],
                          "decision": a["status"], "decided_by": a["decided_by"], "decided_at": a["decided_at"],
                          "payment_id": pay["id"] if pay else None})
        final_note = [l for l in tlog if l["ticket_id"] == tid][-1]["note"]
        out.append({
            "id": tid,
            "subject": t["subject"],
            "requester": t["requester"],
            "final_status": t["status"],
            "outcome": final_note,
            "agents": [{"agent": k, "contribution": v} for k, v in contrib.items()],
            "human_approvals": human,
            "drafts_on_board": [{"draft_id": d["id"], "to": d["recipient"], "subject": d["subject"], "sent": False}
                                for d in drafts if d["ticket_id"] == tid],
            "runs": [r["run_id"] for r in actual[tid]["runs"]],
        })
    (OUT / "resolved_tickets.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


CSS = """
:root{--navy:#0b1f3a;--blue:#2563eb;--soft:#e8f0fe;--line:#e3e9f2;--muted:#64748b;--green:#15803d}
*{box-sizing:border-box}body{margin:0;font-family:Inter,'Segoe UI',system-ui,sans-serif;background:#f4f7fb;color:#0f172a}
header{background:linear-gradient(90deg,#0b1f3a,#13294b);color:#fff;padding:18px 32px}
header h1{margin:0;font-size:20px}header p{margin:4px 0 0;color:#a9bbd6;font-size:13px}
main{max-width:1200px;margin:0 auto;padding:20px 32px 60px}
.tabs{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}
.tabs label{padding:9px 16px;border-radius:10px;background:#fff;border:1.5px solid var(--line);cursor:pointer;font-weight:600;font-size:14px;color:var(--navy)}
input[name=tab]{display:none}
.panel{display:none}
.card{background:#fff;border-radius:14px;box-shadow:0 1px 2px rgba(11,31,58,.06),0 4px 14px rgba(11,31,58,.06);padding:18px 22px;margin-bottom:16px}
h2{font-size:18px;color:var(--navy);margin:0 0 10px}h3{font-size:15px;color:var(--navy);margin:16px 0 8px}
.badge{display:inline-block;font-size:11.5px;font-weight:700;padding:3px 9px;border-radius:99px;background:#dcfce7;color:var(--green)}
.pill{display:inline-block;font-size:11px;font-weight:700;padding:2px 8px;border-radius:6px;background:var(--soft);color:var(--blue);margin-left:6px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.expected{border-top:4px solid #94a3b8}.actual{border-top:4px solid var(--blue)}
table{width:100%;border-collapse:collapse;font-size:13.5px}th,td{text-align:left;padding:8px 10px;border-top:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.4px;border-top:none}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
code,.mono{font-family:ui-monospace,Consolas,monospace;font-size:12.5px;background:#f1f5f9;padding:1px 5px;border-radius:5px}
.muted{color:var(--muted)}.small{font-size:12.5px}p{line-height:1.5;font-size:14px;margin:6px 0}li{font-size:14px;line-height:1.5}
.ok{color:var(--green);font-weight:700}.neg{color:#b91c1c}.total td{font-weight:800;border-top:2px solid var(--navy)}
.cmp li.match::marker{content:"✓  ";color:var(--green)}.cmp li.diff::marker{content:"△  ";color:#d97706}
details{margin:4px 0}summary{cursor:pointer;color:var(--blue);font-size:13px}
.reflect{border-top:4px solid #7c3aed}.reflect p{max-width:900px}
@media(max-width:900px){.grid{grid-template-columns:1fr}}
"""


def tab_css(ids: list[str]) -> str:
    rules = [f"#tab-{i}:checked~.tabs label[for=tab-{i}]{{background:var(--navy);color:#fff;border-color:var(--navy)}}"
             f"#tab-{i}:checked~#panel-{i}{{display:block}}" for i in ids]
    return "\n".join(rules)


TAB_LABELS = {"cash": "💵 Cash", "reflections": "📝 Reflections"}


def write_desk_html(tickets, expected, actual, approvals, drafts, tlog, ledger, start, end_db, paid_total) -> None:
    ids = [str(t) for t in tickets] + ["cash", "reflections"]
    parts = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>Campus Customs · Desk tickets</title>"
             f"<style>{CSS}\n{tab_css(ids)}</style></head><body>"
             "<header><h1>Campus Customs · Desk tickets</h1>"
             "<p>Expected vs actual agent behavior for each ticket, plus the cash ledger. "
             "Generated by backend/build_reports.py from data/campus_customs_new.db and output/audit_trail.json.</p></header><main>"]
    for i, tid in enumerate(ids):
        parts.append(f"<input type='radio' name='tab' id='tab-{tid}'{' checked' if i == 0 else ''}>")
    parts.append("<div class='tabs'>" + "".join(
        f"<label for='tab-{t}'>{TAB_LABELS.get(t) or '#' + t + ' ' + esc(tickets[int(t)]['subject'])}</label>" for t in ids) + "</div>")

    for tid, t in tickets.items():
        exp, act = expected[tid], actual[tid]
        p = [f"<section class='panel' id='panel-{tid}'>"
             f"<div class='card'><h2>#{tid} {esc(t['subject'])} <span class='badge'>{esc(t['status'])}</span></h2>"
             f"<p class='muted'>{esc(t['requester'])} · {esc(t['type'])}"
             f"{' · ' + esc(t['sku']) + ' size ' + esc(t['size']) + ' qty ' + esc(t['qty']) if t['sku'] else ''}"
             f"{' · lease ' + esc(t['lease_id']) if t['lease_id'] else ''}{' · invoice ' + esc(t['invoice_id']) if t['invoice_id'] else ''}"
             f" · “{esc(t['notes'])}”</p></div>"
             "<div class='grid'>"
             f"<div class='card expected'><h2>Expected</h2><p class='muted small'>Written before the run (Problem 6). Predictions, not instructions.</p>"
             f"{md_block(exp['lines'])}</div>"]

        # Actual: agents, delegations, tools
        a = [f"<div class='card actual'><h2>Actual</h2><p class='muted small'>From this run's audit trail "
             f"({len(act['runs'])} run{'s' if len(act['runs']) != 1 else ''}).</p>"]
        worked = OrderedDict()
        for run in act["runs"]:
            for ag in run["agents"]:
                worked.setdefault(ag["agent"], Counter()).update(ag["tools"])
        a.append("<h3>Which agents worked</h3><ul>" + "".join(
            f"<li><strong>{AGENT_LABEL[k]}</strong>: " + ", ".join(f"<code>{esc(tool)}</code>×{n}" if n > 1 else f"<code>{esc(tool)}</code>"
                                                                  for tool, n in v.items()) + "</li>" for k, v in worked.items()) + "</ul>")
        a.append("<h3>What they delegated</h3>")
        any_del = False
        for run in act["runs"]:
            if run["delegations"]:
                any_del = True
                a.append(f"<p class='small muted'>Run {run['n']} — {run['kind']}</p><ul>" + "".join(
                    f"<li><strong>{AGENT_LABEL[d['from']]} → {AGENT_LABEL[d['to']]}</strong>: {esc(d['task'])}</li>" for d in run["delegations"]) + "</ul>")
            else:
                a.append(f"<p class='small muted'>Run {run['n']} — {run['kind']}: no delegation (the boss closed the ticket with its own tools).</p>")
        if not any_del:
            a.append("<p>None.</p>")
        a.append("<h3>Tools used (all runs)</h3><p>" + " ".join(f"<code>{esc(x)}</code>" for x in sorted(act["tools"])) + "</p>")
        a.append("</div>")
        p.extend(a)
        p.append("</div>")

        # Comparison + outcome
        exp_first, act_first = exp["first"], act["first_delegate"]
        missing, extra = sorted(exp["tools"] - act["tools"]), sorted(act["tools"] - exp["tools"])
        cmp = [f"<li class='{'match' if exp_first == act_first else 'diff'}'>Boss called first: expected "
               f"<strong>{AGENT_LABEL.get(exp_first, exp_first)}</strong>, actual <strong>{AGENT_LABEL.get(act_first, act_first)}</strong>"
               f"{' (the boss sent its delegations in parallel; this was the first one)' if len(act['runs'][0]['delegations']) > 1 else ''}.</li>"]
        cmp.append(f"<li class='{'match' if not missing else 'diff'}'>Expected tools not used: "
                   f"{', '.join(f'<code>{m}</code>' for m in missing) or 'none'}.</li>")
        cmp.append(f"<li class='{'match' if not extra else 'diff'}'>Tools used that were not predicted: "
                   f"{', '.join(f'<code>{m}</code>' for m in extra) or 'none'}.</li>")
        p.append("<div class='card'><h2>Expected vs actual</h2><ul class='cmp'>" + "".join(cmp) + "</ul>")
        p.append("<h3>Outcome</h3>")
        for run in act["runs"]:
            d = run["decision"]
            p.append(f"<p><strong>Run {run['n']} ({run['kind'].lower()}) → {esc(d['final_status'])}:</strong> {esc(d['decision'])}</p>")
        mine = [x for x in approvals if x["ticket_id"] == tid]
        if mine:
            p.append("<h3>Human approvals</h3><table><tr><th>#</th><th>Request</th><th class='num'>Amount</th><th>Decision</th><th>By</th></tr>" + "".join(
                f"<tr><td>{x['id']}</td><td>{esc(x['kind'])} — {esc(x['reason'])}</td><td class='num'>{money(x['amount'])}</td>"
                f"<td>{esc(x['status'])}</td><td>{esc(x['decided_by'])}</td></tr>" for x in mine) + "</table>")
        my_drafts = [d for d in drafts if d["ticket_id"] == tid]
        if my_drafts:
            p.append("<h3>Drafts left on the board (never sent)</h3>" + "".join(
                f"<details><summary>Draft {d['id']} to {esc(d['recipient'])} — “{esc(d['subject'])}”</summary>"
                f"<p style='white-space:pre-wrap'>{esc(d['body'])}</p></details>" for d in my_drafts))
        p.append("</div>")
        p.append("<div class='card reflect'><h2>Reflection</h2><p class='muted small'>Sam's reflections on this ticket "
                 "(full answers are on the Reflections tab).</p>" + "".join(
            f"<h3>Q{q}. {esc(REFLECTIONS[q - 1][0])}</h3><p>{esc(text)}</p>" for q, text in TICKET_REFLECTIONS.get(tid, [])) + "</div>")
        p.append("</section>")
        parts.extend(p)

    # Cash tab
    c = ["<section class='panel' id='panel-cash'><div class='card'><h2>Cash — checking account</h2>"
         "<p class='muted'>Money only goes out. Every payment below was approved by a human on the dashboard; "
         "purchase orders do not move cash when placed.</p>"
         "<table><tr><th>Step</th><th>What happened</th><th class='num'>Change</th><th class='num'>Checking balance</th></tr>"
         f"<tr><td><strong>Start</strong></td><td>Checking balance after the reset (cash_accounts in campus_customs.db)</td>"
         f"<td class='num'></td><td class='num'><strong>{money(start)}</strong></td></tr>"]
    for step in ledger:
        t = tickets[step["ticket_id"]]
        bal = step["balance_before"]
        for j, item in enumerate(step["items"]):
            bal = round(bal + item["change"], 2)
            label = f"<strong>Ticket #{step['ticket_id']}</strong><br><span class='small muted'>{esc(t['subject'])}, resolved {esc(step['resolved_at'][:19])}Z</span>" if j == 0 else ""
            cls = " neg" if item["change"] < 0 else ""
            c.append(f"<tr><td>{label}</td><td>{esc(item['what'])}</td><td class='num{cls}'>{money(item['change']) if item['change'] else '$0.00'}</td>"
                     f"<td class='num'>{money(bal)}</td></tr>")
    c.append(f"<tr class='total'><td>End</td><td>Ending checking balance</td><td class='num neg'>{money(-paid_total)}</td>"
             f"<td class='num'>{money(ledger[-1]['balance_after'])}</td></tr></table>")
    c.append(f"<h3>Math check</h3><p class='mono'>{money(start)} − " + " − ".join(
        money(-i["change"]) for s in ledger for i in s["items"] if i["change"]) + f" = {money(ledger[-1]['balance_after'])}</p>"
             f"<p><span class='ok'>✓ Matches</span> <code>cash_accounts.balance</code> for <code>checking</code> in "
             f"<code>data/campus_customs_new.db</code>: <strong>{money(end_db)}</strong>. "
             f"Total paid out ({money(paid_total)}) equals the sum of the <code>payments</code> table.</p></div></section>")
    parts.extend(c)
    parts.append("<section class='panel' id='panel-reflections'><div class='card reflect'><h2>Reflections</h2>"
                 "<p class='muted'>Written by Sam after the full run (Problem 9).</p>" + "".join(
        f"<h3>{i}. {esc(q)}</h3><p>{esc(a)}</p>" for i, (q, a) in enumerate(REFLECTIONS, 1)) + "</div></section>")
    parts.append("</main></body></html>")
    (OUT / "desk_tickets.html").write_text("\n".join(parts), encoding="utf-8")


def write_board_html(tickets, actual, tlog) -> None:
    shots = OUT / "screenshots"
    parts = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>Campus Customs · Resolved board</title>"
             f"<style>{CSS}\nimg{{width:100%;border-radius:12px;border:1px solid var(--line)}}</style></head><body>"
             "<header><h1>Campus Customs · Resolved board</h1>"
             "<p>Screenshots of the React dashboard (http://localhost:5173 / Vite) with each resolved ticket selected. "
             "Images are embedded so this page opens by double-clicking.</p></header><main>"]
    for tid, t in tickets.items():
        png = shots / f"ticket_{tid}.png"
        data = base64.b64encode(png.read_bytes()).decode()
        note = [l for l in tlog if l["ticket_id"] == tid][-1]["note"]
        parts.append(f"<div class='card'><h2>#{tid} {esc(t['subject'])} <span class='badge'>{esc(t['status'])}</span>"
                     f"<span class='pill'>{len(actual[tid]['runs'])} runs</span></h2><p>{esc(note)}</p>"
                     f"<img alt='Dashboard with ticket {tid} selected' src='data:image/png;base64,{data}'></div>")
    parts.append("</main></body></html>")
    (OUT / "resolved_board.html").write_text("\n".join(parts), encoding="utf-8")


if __name__ == "__main__":
    build()

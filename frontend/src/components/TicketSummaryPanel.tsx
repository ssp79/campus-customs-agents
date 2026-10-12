import { useState } from 'react'
import { STATUS_LABEL, agentMeta } from '../format'
import { Icon } from '../icons'
import type { Draft, Ticket, TicketSummary } from '../types'

/** After a run: the boss's decision, what each agent did, and the drafts left on the board. */
export function TicketSummaryPanel({ ticket, summary, drafts }: {
  ticket: Ticket | null
  summary: TicketSummary | null
  drafts: Draft[]
}) {
  const [openDraft, setOpenDraft] = useState<number | null>(null)
  if (!ticket) {
    return (
      <section className="panel">
        <header className="panel-head"><h2><Icon name="file" /> Run summary</h2></header>
        <p className="empty">Select a ticket to see what each agent did.</p>
      </section>
    )
  }
  const d = summary?.decision
  return (
    <section className="panel fade-in" key={ticket.id}>
      <header className="panel-head">
        <h2><Icon name="file" /> Run summary · #{ticket.id} {ticket.subject}{summary?.runs ? ` · ${summary.runs} run${summary.runs === 1 ? "" : "s"}` : ""}</h2>
        {ticket.running && <span className="badge status-running"><span className="dot pulse" /> Running</span>}
      </header>

      {!summary?.run_id && !ticket.running && <p className="empty">No agent run yet. Press “Run agents” on the ticket.</p>}
      {ticket.running && !d && <p className="empty">The team is working — the summary appears when the run finishes.</p>}

      {d && (
        <div className="decision">
          <div className="decision-head">
            <Icon name="crown" size={16} /> Boss’s final call
            <span className={`badge status-${d.final_status}`}>{STATUS_LABEL[d.final_status] ?? d.final_status}</span>
          </div>
          <p>{d.decision}</p>
          {d.human_actions_needed.length > 0 && (
            <>
              <div className="sub-head">Needs a human</div>
              <ul>{d.human_actions_needed.map((h, i) => <li key={i}>{h}</li>)}</ul>
            </>
          )}
          {d.next_steps.length > 0 && (
            <>
              <div className="sub-head">Next steps</div>
              <ul>{d.next_steps.map((h, i) => <li key={i}>{h}</li>)}</ul>
            </>
          )}
        </div>
      )}

      {summary && summary.agents.length > 0 && (
        <div className="agent-work">
          {summary.agents.map((w) => {
            const meta = agentMeta(w.agent)
            return (
              <div key={w.agent} className="work-row" style={{ '--agent': meta.color } as React.CSSProperties}>
                <div className="agent-avatar small"><Icon name={meta.icon} size={15} /></div>
                <div>
                  <div className="work-name">{meta.label}</div>
                  {w.agent !== 'boss' && w.summaries.map((s, i) => <p key={i} className="work-text">{s}</p>)}
                  {w.agent === 'boss' && w.delegated_to.length > 0 && (
                    <p className="work-text">Delegated to {[...new Set(w.delegated_to)].map((n) => agentMeta(n).label).join(', ')}.</p>
                  )}
                  <div className="chips">
                    {w.tools.map((t) => <span key={t} className="chip">{t}</span>)}
                    {w.approval_ids.map((id) => <span key={`a${id}`} className="chip chip-warn">approval #{id}</span>)}
                    {w.draft_ids.map((id) => <span key={`d${id}`} className="chip chip-good">draft #{id}</span>)}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {drafts.length > 0 && (
        <div className="drafts">
          <div className="sub-head"><Icon name="message" size={14} /> Drafts on the board (never sent)</div>
          {drafts.map((dr) => (
            <div key={dr.id} className="draft">
              <button className="draft-head" onClick={() => setOpenDraft(openDraft === dr.id ? null : dr.id)}>
                <span>#{dr.id} · To {dr.recipient} · “{dr.subject}”</span>
                <span className="muted">{openDraft === dr.id ? 'Hide' : 'Read'}</span>
              </button>
              {openDraft === dr.id && <pre className="draft-body">{dr.body}</pre>}
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

import { useState } from 'react'
import { AGENTS, clock, describe } from '../format'
import { Icon } from '../icons'
import type { TeamEvent } from '../types'

/** The five agents (live status) and the activity feed beneath them. */
export function AgentPanel({ events, selected, focused = false }: {
  events: TeamEvent[]
  selected: number | null
  focused?: boolean // start filtered to the selected ticket (e.g. opened with ?ticket=101)
}) {
  const [onlySelected, setOnlySelected] = useState(focused)
  const visible = events.filter((e) => !onlySelected || selected === null || e.ticket_id === selected)

  const agentState = AGENTS.map((a) => {
    const mine = visible.filter((e) => e.agent === a.name && e.run_id !== 'system')
    const open = mine.filter((e) => e.type === 'agent_start').length - mine.filter((e) => e.type === 'agent_end').length
    const lastLine = [...mine].reverse().map(describe).find((l) => l !== null)
    const tools = mine.filter((e) => e.type === 'tool_call').length
    return { ...a, working: open > 0, lastLine, tools, seen: mine.length > 0 }
  })

  const feed = visible.map((e) => ({ e, line: describe(e) })).filter((x) => x.line !== null).reverse().slice(0, 150)

  return (
    <section className="panel">
      <header className="panel-head">
        <h2><Icon name="activity" /> Agent team</h2>
        <span className="muted">gpt-6-luna · full connectivity</span>
      </header>

      <div className="agent-grid">
        {agentState.map((a) => (
          <div key={a.name} className={`agent-card${a.working ? ' working' : ''}`} style={{ '--agent': a.color } as React.CSSProperties}>
            <div className="agent-avatar"><Icon name={a.icon} size={18} /></div>
            <div className="agent-info">
              <div className="agent-name">
                {a.label}
                <span className={`pill ${a.working ? 'pill-live' : a.seen ? 'pill-done' : 'pill-idle'}`}>
                  {a.working ? <><span className="dot pulse" /> Working</> : a.seen ? 'Done' : 'Idle'}
                </span>
              </div>
              <div className="agent-role">{a.role}</div>
              <div className="agent-last">{a.lastLine ? a.lastLine.text : 'No activity yet'}</div>
              {a.tools > 0 && <div className="agent-tools">{a.tools} tool call{a.tools === 1 ? '' : 's'}</div>}
            </div>
          </div>
        ))}
      </div>

      <div className="feed-head">
        <h3><span className="dot live" /> Live activity</h3>
        <label className="toggle">
          <input type="checkbox" checked={onlySelected} onChange={(e) => setOnlySelected(e.target.checked)} disabled={selected === null} />
          {selected === null ? 'Select a ticket to filter' : `Only ticket #${selected}`}
        </label>
      </div>
      <ol className="feed">
        {feed.length === 0 && <li className="feed-empty">Run a ticket to watch the agents work.</li>}
        {feed.map(({ e, line }) => (
          <li key={e.seq} className={`feed-item tone-${line!.tone}`}>
            <span className="feed-icon" style={{ color: line!.color }}><Icon name={line!.icon} size={15} /></span>
            <span className="feed-time">{clock(e.time)}</span>
            <span className="feed-actor" style={{ color: line!.color }}>{line!.actor}</span>
            {e.ticket_id !== null && <span className="feed-ticket">#{e.ticket_id}</span>}
            <span className="feed-text">{line!.text}</span>
          </li>
        ))}
      </ol>
    </section>
  )
}

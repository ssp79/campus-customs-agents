import { STATUS_LABEL, TICKET_ICON, ticketDetail } from '../format'
import { Icon } from '../icons'
import type { Ticket } from '../types'

export function TicketBoard({ tickets, selected, onSelect, onRun, starting }: {
  tickets: Ticket[]
  selected: number | null
  onSelect: (id: number) => void
  onRun: (id: number) => void
  starting: number | null
}) {
  return (
    <section className="panel">
      <header className="panel-head">
        <h2><Icon name="ticket" /> Ticket board</h2>
        <span className="muted">{tickets.length} tickets</span>
      </header>
      <div className="ticket-list">
        {tickets.map((t) => {
          const busy = t.running || starting === t.id
          const statusKey = busy ? 'running' : t.status
          return (
            <article
              key={t.id}
              className={`ticket-card${selected === t.id ? ' selected' : ''}${busy ? ' busy' : ''}`}
              onClick={() => onSelect(t.id)}
            >
              <div className="ticket-icon"><Icon name={TICKET_ICON[t.type] ?? 'ticket'} size={22} /></div>
              <div className="ticket-body">
                <div className="ticket-top">
                  <span className="ticket-id">#{t.id}</span>
                  <span className={`badge state-${t.state}`}>{t.state === 'resolved' ? 'Resolved' : 'Open'}</span>
                  {/* The detailed status adds information only when it differs from open/resolved. */}
                  {(busy || !['open', 'resolved'].includes(t.status)) && (
                    <span className={`badge status-${statusKey}`}>
                      {busy && <span className="dot pulse" />}
                      {busy ? 'Agents working' : STATUS_LABEL[t.status] ?? t.status}
                    </span>
                  )}
                </div>
                <h3>{t.subject}</h3>
                <div className="ticket-meta">{t.requester} · {t.type.replace('_', ' ')}</div>
                {ticketDetail(t) && <div className="ticket-meta mono">{ticketDetail(t)}</div>}
                {t.notes && <p className="ticket-notes">“{t.notes}”</p>}
              </div>
              <button
                className="btn primary"
                disabled={busy}
                onClick={(e) => { e.stopPropagation(); onRun(t.id) }}
                title="Start the agent team on this ticket"
              >
                <Icon name={busy ? 'refresh' : 'play'} size={16} className={busy ? 'spin' : ''} />
                {busy ? 'Running' : t.state === 'resolved' ? 'Run again' : 'Run agents'}
              </button>
            </article>
          )
        })}
      </div>
    </section>
  )
}

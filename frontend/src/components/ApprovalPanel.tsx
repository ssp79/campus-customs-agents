import { useState } from 'react'
import { APPROVAL_KIND, agentMeta, money } from '../format'
import { Icon } from '../icons'
import type { Approval } from '../types'

const DONE_LABEL: Record<string, string> = { paid: 'Paid', ordered: 'Ordered', rejected: 'Rejected' }

export function ApprovalPanel({ approvals, approver, setApprover, onApprove, onReject, busy }: {
  approvals: Approval[]
  approver: string
  setApprover: (name: string) => void
  onApprove: (a: Approval) => void
  onReject: (a: Approval) => void
  busy: number | null
}) {
  const [showDone, setShowDone] = useState(true)
  const pending = approvals.filter((a) => a.status === 'pending')
  const decided = approvals.filter((a) => a.status !== 'pending').reverse()
  const noName = !approver.trim()

  return (
    <section className="panel">
      <header className="panel-head">
        <h2><Icon name="shield" /> Human approvals</h2>
        <label className="approver">
          <Icon name="user" size={15} />
          <input value={approver} onChange={(e) => setApprover(e.target.value)} placeholder="Your name (required to approve)" />
        </label>
      </header>
      <p className="muted small">
        Agents can only request money. Nothing is paid or ordered until you approve here. Payments refuse if
        checking would go negative; purchase orders refuse while the vendor has an unpaid invoice.
      </p>

      {pending.length === 0 && <p className="empty">No requests waiting on you.</p>}
      <div className="approval-list">
        {pending.map((a) => {
          const kind = APPROVAL_KIND[a.kind]
          return (
            <div key={a.id} className="approval-card fade-in">
              <div className="approval-icon"><Icon name={kind.icon} size={20} /></div>
              <div className="approval-body">
                <div className="approval-top">
                  <strong>{kind.label}</strong>
                  <span className="muted">#{a.id} · ticket #{a.ticket_id} · from {agentMeta(a.requested_by).label}</span>
                </div>
                <div className="approval-amount">{money(a.amount)}</div>
                {a.kind === 'purchase_order' && (
                  <div className="mono small">{a.qty} × {a.sku} size {a.size} · vendor {a.vendor_id}</div>
                )}
                {a.kind === 'invoice_payment' && <div className="mono small">Invoice {a.ref_id} · vendor {a.vendor_id}</div>}
                {a.kind === 'rent_payment' && <div className="mono small">Lease {a.ref_id}</div>}
                <p className="approval-reason">{a.reason}</p>
              </div>
              <div className="approval-actions">
                <button className="btn success" disabled={noName || busy === a.id} onClick={() => onApprove(a)}
                  title={noName ? 'Enter your name first' : ''}>
                  <Icon name="checkCircle" size={16} /> Approve
                </button>
                <button className="btn ghost-danger" disabled={noName || busy === a.id} onClick={() => onReject(a)}>
                  <Icon name="x" size={16} /> Reject
                </button>
              </div>
            </div>
          )
        })}
      </div>

      {decided.length > 0 && (
        <div className="decided">
          <button className="link" onClick={() => setShowDone(!showDone)}>
            {showDone ? 'Hide' : 'Show'} decided requests ({decided.length})
          </button>
          {showDone && (
            <table>
              <tbody>
                {decided.map((a) => (
                  <tr key={a.id}>
                    <td>#{a.id}</td>
                    <td>{APPROVAL_KIND[a.kind].label}</td>
                    <td className="mono">{money(a.amount)}</td>
                    <td><span className={`badge done-${a.status}`}>{DONE_LABEL[a.status] ?? a.status}</span></td>
                    <td className="muted">by {a.decided_by}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </section>
  )
}

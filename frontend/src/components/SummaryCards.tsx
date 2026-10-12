import { useEffect, useRef, useState } from 'react'
import { money } from '../format'
import { Icon, type IconName } from '../icons'
import type { Cash } from '../types'

function Card({ icon, label, value, note, accent, flash }: {
  icon: IconName; label: string; value: string; note: string; accent: string; flash?: boolean
}) {
  return (
    <div className={`stat-card${flash ? ' flash' : ''}`} style={{ '--accent': accent } as React.CSSProperties}>
      <div className="stat-icon"><Icon name={icon} size={22} /></div>
      <div>
        <div className="stat-label">{label}</div>
        <div className="stat-value">{value}</div>
        <div className="stat-note">{note}</div>
      </div>
    </div>
  )
}

export function SummaryCards({ open, resolved, pending, pendingTotal, cash }: {
  open: number; resolved: number; pending: number; pendingTotal: number; cash: Cash | null
}) {
  // Briefly highlight the balance card whenever the balance changes (e.g. after an approved payment).
  const [flash, setFlash] = useState(false)
  const last = useRef<number | null>(null)
  useEffect(() => {
    if (!cash) return
    if (last.current !== null && last.current !== cash.balance) {
      setFlash(true)
      const t = setTimeout(() => setFlash(false), 1600)
      last.current = cash.balance
      return () => clearTimeout(t)
    }
    last.current = cash.balance
  }, [cash])

  return (
    <section className="stats">
      <Card icon="ticket" label="Open tickets" value={String(open)} note="Waiting on the agent team" accent="#2563eb" />
      <Card icon="checkCircle" label="Resolved tickets" value={String(resolved)} note="Agents finished their work" accent="#16a34a" />
      <Card icon="shield" label="Pending approvals" value={String(pending)}
        note={pending ? `${money(pendingTotal)} waiting on a human` : 'Nothing waiting'} accent="#d97706" />
      <Card icon="wallet" label="Checking balance" value={cash ? money(cash.balance) : '—'}
        note={cash ? `As of ${cash.as_of} · shop date ${cash.date_today}` : 'Loading…'} accent="#0b1f3a" flash={flash} />
    </section>
  )
}

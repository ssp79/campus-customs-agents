import { useCallback, useEffect, useRef, useState } from 'react'
import { API_URL, api } from './api'
import { AgentPanel } from './components/AgentPanel'
import { ApprovalPanel } from './components/ApprovalPanel'
import { SummaryCards } from './components/SummaryCards'
import { TicketBoard } from './components/TicketBoard'
import { TicketSummaryPanel } from './components/TicketSummaryPanel'
import { money } from './format'
import { Icon } from './icons'
import type { Approval, Cash, Draft, TeamEvent, Ticket, TicketSummary } from './types'

const EVENT_POLL_MS = 1200
const BOARD_POLL_MS = 4000
const MAX_EVENTS = 1500

type Toast = { text: string; tone: 'good' | 'bad' | 'info' }

export default function App() {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [cash, setCash] = useState<Cash | null>(null)
  const [approvals, setApprovals] = useState<Approval[]>([])
  const [events, setEvents] = useState<TeamEvent[]>([])
  // ?ticket=101 preselects a ticket (used for the board screenshots in output/resolved_board.html).
  const [selected, setSelected] = useState<number | null>(() => {
    const id = Number(new URLSearchParams(window.location.search).get('ticket'))
    return Number.isFinite(id) && id > 0 ? id : null
  })
  const [summary, setSummary] = useState<TicketSummary | null>(null)
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [starting, setStarting] = useState<number | null>(null)
  const [busyApproval, setBusyApproval] = useState<number | null>(null)
  const [approver, setApproverState] = useState(() => localStorage.getItem('approver') ?? '')
  const [toast, setToast] = useState<Toast | null>(null)
  const [online, setOnline] = useState(true)

  const lastSeq = useRef(0)
  const selectedRef = useRef<number | null>(selected)
  const wasRunning = useRef<Set<number>>(new Set())

  const notify = useCallback((text: string, tone: Toast['tone'] = 'info') => {
    setToast({ text, tone })
    window.setTimeout(() => setToast((t) => (t?.text === text ? null : t)), 6000)
  }, [])

  const setApprover = (name: string) => {
    setApproverState(name)
    localStorage.setItem('approver', name)
  }

  const refreshBoard = useCallback(async () => {
    try {
      const [t, c, a] = await Promise.all([api.tickets(), api.cash(), api.approvals()])
      setTickets(t)
      setCash(c)
      setApprovals(a.approvals)
      setOnline(true)
    } catch {
      setOnline(false)
    }
  }, [])

  const loadSummary = useCallback(async (id: number) => {
    try {
      const [s, d] = await Promise.all([api.summary(id), api.drafts(id)])
      if (selectedRef.current === id) {
        setSummary(s)
        setDrafts(d.drafts)
      }
    } catch {
      /* the board poll reports connectivity */
    }
  }, [])

  // Live agent events: poll for anything newer than the last sequence number we saw.
  useEffect(() => {
    const tick = async () => {
      try {
        const page = await api.events(lastSeq.current)
        if (page.last_seq < lastSeq.current) {
          lastSeq.current = 0 // backend restarted; start the feed over
          setEvents([])
          return
        }
        if (page.events.length) {
          lastSeq.current = page.last_seq
          setEvents((prev) => [...prev, ...page.events].slice(-MAX_EVENTS))
          // Something changed on the board (request filed, ticket updated, approval, agent finished).
          if (page.events.some((e) => ['tool_result', 'agent_end', 'error'].includes(e.type))) {
            refreshBoard()
            if (selectedRef.current !== null) loadSummary(selectedRef.current)
          }
        }
      } catch {
        setOnline(false)
      }
    }
    tick()
    const id = window.setInterval(tick, EVENT_POLL_MS)
    return () => window.clearInterval(id)
  }, [refreshBoard, loadSummary])

  useEffect(() => {
    refreshBoard()
    if (selectedRef.current !== null) loadSummary(selectedRef.current)
    const id = window.setInterval(refreshBoard, BOARD_POLL_MS)
    return () => window.clearInterval(id)
  }, [refreshBoard, loadSummary])

  // When a run finishes, say so and load the run summary.
  useEffect(() => {
    const now = new Set(tickets.filter((t) => t.running).map((t) => t.id))
    for (const id of wasRunning.current) {
      if (!now.has(id)) {
        const t = tickets.find((x) => x.id === id)
        notify(`Ticket #${id} finished — ${t?.state === 'resolved' ? 'resolved' : 'still open'}`, 'good')
        if (selectedRef.current === id) loadSummary(id)
      }
    }
    wasRunning.current = now
  }, [tickets, notify, loadSummary])

  const select = (id: number) => {
    selectedRef.current = id
    setSelected(id)
    setSummary(null)
    setDrafts([])
    loadSummary(id)
  }

  const run = async (id: number) => {
    select(id)
    setStarting(id)
    try {
      await api.runTicket(id)
      wasRunning.current.add(id)
      notify(`Agent team started on ticket #${id}`, 'info')
      await refreshBoard()
    } catch (e) {
      notify((e as Error).message, 'bad')
    } finally {
      setStarting(null)
    }
  }

  const approve = async (a: Approval) => {
    setBusyApproval(a.id)
    try {
      const r = await api.approve(a.id, approver.trim())
      notify(
        r.paid
          ? `Paid ${money(Number(r.amount))} — checking is now ${money(Number(r.balance_after))}`
          : `Purchase order #${a.id} placed — expected ${r.expected_arrival}`,
        'good',
      )
    } catch (e) {
      notify(`Refused: ${(e as Error).message}`, 'bad')
    } finally {
      setBusyApproval(null)
      refreshBoard()
    }
  }

  const reject = async (a: Approval) => {
    setBusyApproval(a.id)
    try {
      await api.reject(a.id, approver.trim(), `Rejected on the dashboard by ${approver.trim()}`)
      notify(`Request #${a.id} rejected — nothing was paid`, 'info')
    } catch (e) {
      notify((e as Error).message, 'bad')
    } finally {
      setBusyApproval(null)
      refreshBoard()
    }
  }

  const reset = async () => {
    if (!window.confirm('Reset the working database to the original values? Approvals, drafts and payments are cleared.')) return
    try {
      await api.reset()
      setSummary(null)
      setDrafts([])
      notify('Database reset to the original values', 'info')
      refreshBoard()
    } catch (e) {
      notify((e as Error).message, 'bad')
    }
  }

  const pending = approvals.filter((a) => a.status === 'pending')
  const selectedTicket = tickets.find((t) => t.id === selected) ?? null

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="logo">CC</div>
          <div>
            <h1>Campus Customs</h1>
            <span>Operations Command Center</span>
          </div>
        </div>
        <div className="topbar-right">
          {cash && <span className="shop-date"><Icon name="clock" size={15} /> Shop date {cash.date_today}</span>}
          <span className={`conn ${online ? 'ok' : 'down'}`} title={API_URL}>
            <span className="dot" /> {online ? 'Backend connected' : `Backend offline (${API_URL})`}
          </span>
          <button className="btn ghost" onClick={reset} title="Copy campus_customs.db over the working copy">
            <Icon name="refresh" size={15} /> Reset database
          </button>
        </div>
      </header>

      <main>
        <SummaryCards
          open={tickets.filter((t) => t.state === 'open').length}
          resolved={tickets.filter((t) => t.state === 'resolved').length}
          pending={pending.length}
          pendingTotal={pending.filter((a) => a.kind !== 'purchase_order').reduce((s, a) => s + a.amount, 0)}
          cash={cash}
        />

        <div className="columns">
          <div className="col">
            <TicketBoard tickets={tickets} selected={selected} onSelect={select} onRun={run} starting={starting} />
            <TicketSummaryPanel ticket={selectedTicket} summary={summary} drafts={drafts} />
          </div>
          <div className="col">
            <AgentPanel events={events} selected={selected} focused={new URLSearchParams(window.location.search).has('ticket')} />
          </div>
        </div>

        <ApprovalPanel
          approvals={approvals}
          approver={approver}
          setApprover={setApprover}
          onApprove={approve}
          onReject={reject}
          busy={busyApproval}
        />
      </main>

      {toast && (
        <div className={`toast toast-${toast.tone}`} onClick={() => setToast(null)}>
          <Icon name={toast.tone === 'bad' ? 'alert' : 'checkCircle'} size={18} /> {toast.text}
        </div>
      )}
    </div>
  )
}

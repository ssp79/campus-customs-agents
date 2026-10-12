import type { IconName } from './icons'
import type { AgentName, Approval, TeamEvent, Ticket } from './types'

export const AGENTS: { name: AgentName; label: string; role: string; icon: IconName; color: string }[] = [
  { name: 'boss', label: 'Boss', role: 'Routes tickets, makes the final call', icon: 'crown', color: '#0b1f3a' },
  { name: 'inventory', label: 'Inventory', role: 'Stock, shortfalls, restock vendors', icon: 'box', color: '#0284c7' },
  { name: 'accounting', label: 'Accounting', role: 'Cash, invoices, margins, approvals', icon: 'dollar', color: '#2563eb' },
  { name: 'facilities', label: 'Facilities', role: 'Leases and rent', icon: 'building', color: '#4f46e5' },
  { name: 'customer_service', label: 'Customer Service', role: 'Drafts messages (never sent)', icon: 'message', color: '#0d9488' },
]

export const agentMeta = (name: string) => AGENTS.find((a) => a.name === name) ?? AGENTS[0]

export const money = (n: number) =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 })

export const clock = (iso: string) =>
  new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })

export const STATUS_LABEL: Record<string, string> = {
  open: 'Open',
  in_progress: 'In progress',
  waiting_on_approval: 'Awaiting approval',
  resolved: 'Resolved',
}

export const TICKET_ICON: Record<string, IconName> = {
  customer_order: 'shirt',
  rent_notice: 'home',
  price_override: 'tag',
}

export function ticketDetail(t: Ticket): string {
  const parts: string[] = []
  if (t.sku) parts.push(`${t.sku}${t.size ? ` · size ${t.size}` : ''}${t.qty ? ` · qty ${t.qty}` : ''}`)
  if (t.lease_id) parts.push(`Lease ${t.lease_id}`)
  if (t.invoice_id) parts.push(`Invoice ${t.invoice_id}`)
  return parts.join(' · ')
}

export const APPROVAL_KIND: Record<Approval['kind'], { label: string; icon: IconName }> = {
  invoice_payment: { label: 'Invoice payment', icon: 'file' },
  rent_payment: { label: 'Rent payment', icon: 'home' },
  purchase_order: { label: 'Purchase order', icon: 'cart' },
}

const WRITE_TOOLS = new Set(['request_payment', 'request_purchase_order', 'draft_customer_message', 'update_ticket'])

function argText(args: unknown): string {
  if (!args || typeof args !== 'object') return ''
  return Object.entries(args as Record<string, unknown>)
    .filter(([k]) => !['body', 'reason', 'note'].includes(k))
    .map(([k, v]) => `${k}=${typeof v === 'string' ? v : JSON.stringify(v)}`)
    .join(', ')
}

function short(text: unknown, max = 220): string {
  const s = typeof text === 'string' ? text : JSON.stringify(text)
  return s.length > max ? `${s.slice(0, max - 1)}…` : s
}

export interface FeedLine {
  icon: IconName
  actor: string
  color: string
  text: string
  tone: 'normal' | 'muted' | 'good' | 'warn' | 'bad'
}

/** How one backend event reads in the activity feed. null = not shown (e.g. plain read results). */
export function describe(e: TeamEvent): FeedLine | null {
  const meta = agentMeta(e.agent)
  const d = e.detail
  const base = { actor: meta.label, color: meta.color }

  if (e.run_id === 'system') {
    const result = (d.result ?? {}) as Record<string, unknown>
    const outcome = (result.outcome ?? {}) as Record<string, unknown>
    if (d.tool === 'human_approve') {
      // Events rebuilt after a backend restart carry only the amount, not balance or arrival date.
      if (outcome.paid) return { icon: 'checkCircle', actor: 'Human', color: '#16a34a', tone: 'good',
        text: `${result.approved_by} approved #${result.approval_id}: paid ${money(Number(outcome.amount))}` +
          (outcome.balance_after != null ? `, balance now ${money(Number(outcome.balance_after))}` : '') }
      if (outcome.ordered) return { icon: 'checkCircle', actor: 'Human', color: '#16a34a', tone: 'good',
        text: `${result.approved_by} placed PO #${result.approval_id} (${money(Number(outcome.amount))})` +
          (outcome.expected_arrival ? `, expected ${outcome.expected_arrival}` : '') }
      return { icon: 'alert', actor: 'Human', color: '#d97706', tone: 'warn',
        text: `Approval #${result.approval_id} refused: ${outcome.reason ?? 'not allowed'}` }
    }
    if (d.tool === 'human_reject') return { icon: 'x', actor: 'Human', color: '#dc2626', tone: 'bad',
      text: `${result.rejected_by} rejected #${result.approval_id}` }
    if (d.tool === 'reset_database') return { icon: 'refresh', actor: 'System', color: '#64748b', tone: 'muted',
      text: 'Database reset to the original values' }
    return null
  }

  switch (e.type) {
    case 'agent_start':
      return { ...base, icon: 'play', tone: 'muted', text: `started on ticket ${e.ticket_id}` }
    case 'delegate':
      return { ...base, icon: 'arrowRight', tone: 'normal', text: `→ ${agentMeta(String(d.to)).label}: ${short(d.task, 260)}` }
    case 'delegate_refused':
      return { ...base, icon: 'alert', tone: 'warn', text: `delegation to ${d.to} refused: ${short(d.reason)}` }
    case 'tool_call':
      return { ...base, icon: 'wrench', tone: WRITE_TOOLS.has(String(d.tool)) ? 'normal' : 'muted',
        text: `${d.tool}(${short(argText(d.args), 160)})` }
    case 'tool_result': {
      if (!WRITE_TOOLS.has(String(d.tool))) return null
      const r = (typeof d.result === 'object' && d.result ? d.result : {}) as Record<string, unknown>
      if (d.tool === 'request_payment' || d.tool === 'request_purchase_order')
        return { ...base, icon: 'file', tone: 'good', text: `filed approval #${r.approval_id} for ${money(Number(r.amount))} (waiting on a human)` }
      if (d.tool === 'draft_customer_message')
        return { ...base, icon: 'message', tone: 'good', text: `saved draft #${r.draft_id} (not sent)` }
      if (d.tool === 'update_ticket')
        return { ...base, icon: 'ticket', tone: 'good', text: `ticket ${r.ticket_id}: ${STATUS_LABEL[String(r.old_status)] ?? r.old_status} → ${STATUS_LABEL[String(r.new_status)] ?? r.new_status}` }
      return null
    }
    case 'model_text':
      return { ...base, icon: 'message', tone: 'normal', text: short(d.text, 300) }
    case 'retry':
      return { ...base, icon: 'refresh', tone: 'warn', text: `retrying: ${short(d.reason, 180)}` }
    case 'agent_end': {
      const out = (d.output ?? {}) as Record<string, unknown>
      const said = out.summary ?? out.decision
      return said
        ? { ...base, icon: 'checkCircle', tone: 'good', text: short(said, 400) }
        : { ...base, icon: 'alert', tone: 'bad', text: `stopped: ${short(d.stop_reason)}` }
    }
    case 'error':
      return { ...base, icon: 'alert', tone: 'bad', text: short(d.reason) }
    default:
      return null
  }
}

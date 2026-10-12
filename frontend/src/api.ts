import type { Approval, Cash, Draft, TeamEvent, Ticket, TicketSummary } from './types'

// The FastAPI backend (backend/main.py). Set VITE_API_URL to point somewhere else.
export const API_URL: string = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw new Error(typeof body.detail === 'string' ? body.detail : `${res.status} ${res.statusText}`)
  }
  return body as T
}

const post = (body?: unknown): RequestInit => ({
  method: 'POST',
  body: body === undefined ? undefined : JSON.stringify(body),
})

export const api = {
  tickets: () => request<Ticket[]>('/tickets'),
  runTicket: (id: number) => request<{ run_id: string; ticket_id: number }>(`/tickets/${id}/run`, post()),
  summary: (id: number) => request<TicketSummary>(`/tickets/${id}/summary`),
  events: (since: number) => request<{ events: TeamEvent[]; last_seq: number }>(`/events?since=${since}&limit=500`),
  approvals: () => request<{ approvals: Approval[] }>('/approvals?status=all'),
  approve: (id: number, approvedBy: string) =>
    request<Record<string, unknown>>(`/approvals/${id}/approve`, post({ approved_by: approvedBy })),
  reject: (id: number, rejectedBy: string, note: string) =>
    request<Record<string, unknown>>(`/approvals/${id}/reject`, post({ approved_by: rejectedBy, note })),
  drafts: (ticketId: number) => request<{ drafts: Draft[] }>(`/drafts?ticket_id=${ticketId}`),
  cash: () => request<Cash>('/cash'),
  reset: () => request<{ reset: boolean }>('/reset', post()),
}

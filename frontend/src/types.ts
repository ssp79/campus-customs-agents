// Shapes returned by the FastAPI backend (backend/main.py).

export type AgentName = 'boss' | 'inventory' | 'accounting' | 'facilities' | 'customer_service'

export interface Ticket {
  id: number
  type: string
  requester: string
  subject: string
  sku: string | null
  size: string | null
  qty: number | null
  lease_id: number | null
  invoice_id: number | null
  status: string // open | in_progress | waiting_on_approval | resolved
  state: 'open' | 'resolved'
  notes: string | null
  created_at: string
  running: boolean
}

export interface TeamEvent {
  seq: number
  time: string
  run_id: string
  agent_run_id: string
  agent: AgentName
  ticket_id: number | null
  type: string
  detail: Record<string, unknown>
}

export interface Approval {
  id: number
  kind: 'invoice_payment' | 'rent_payment' | 'purchase_order'
  ticket_id: number | null
  ref_id: number | null
  vendor_id: number | null
  sku: string | null
  size: string | null
  qty: number | null
  amount: number
  reason: string
  requested_by: string
  status: 'pending' | 'paid' | 'ordered' | 'rejected'
  created_at: string
  decided_by: string | null
  decided_at: string | null
  decision_note: string | null
}

export interface Cash {
  account: string
  balance: number
  as_of: string
  date_today: string
}

export interface Draft {
  id: number
  ticket_id: number
  recipient: string
  subject: string
  body: string
  drafted_by: string
  status: string
  created_at: string
}

export interface AgentWork {
  agent: AgentName
  runs: number
  tools: string[]
  delegated_to: string[]
  summaries: string[]
  approval_ids: number[]
  draft_ids: number[]
}

export interface Decision {
  ticket_id: number
  decision: string
  final_status: string
  assigned_to: AgentName[]
  human_actions_needed: string[]
  next_steps: string[]
  approval_ids: number[]
  draft_ids: number[]
}

export interface TicketSummary {
  ticket_id: number
  run_id: string | null
  finished?: string
  runs?: number
  decision: Decision | null
  agents: AgentWork[]
}

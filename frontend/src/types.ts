export type AgentName = 'boss' | 'inventory' | 'accounting' | 'facilities' | 'customer_service'

export interface Ticket {
  id: number
  type: string
  requester: string
  subject: string
  notes: string | null
  sku: string | null
  size: string | null
  qty: number | null
  status: 'open' | 'resolved'
  created_at: string
  last_run: { run_id: string; stop_reason: string; message: string | null; created_at: string } | null
  pending_approvals: number
}

export interface Cash {
  name: string
  balance: number
  date: string
}

export interface Approval {
  id: number
  run_id: string
  ticket_id: number | null
  kind: 'invoice' | 'rent' | 'purchase_order'
  ref_id: number | null
  payee: string
  amount: number
  reference: string | null
  reason: string | null
  status: 'pending' | 'approved' | 'rejected'
  explain?: {
    payee_type: 'supplier' | 'landlord'
    headline: string
    lines: string[]
    stock: { name: string; sku: string; size: string; on_hand: number; needed: number; short: number } | null
  }
}

export interface Fact { statement: string; source: string }

export interface Decision {
  ticket_id: number | null
  assigned_agents: AgentName[]
  decision: string
  reasoning: string[]
  facts: Fact[]
  unknowns: string[]
  approvals_needed: unknown[]
  customer_message: string | null
  next_steps: string[]
}

export type LiveEvent =
  | { i: number; t: number; loop_step: number; type: 'start'; agent: AgentName; chain: AgentName[] }
  | { i: number; t: number; loop_step: number; type: 'thinking'; agent: AgentName }
  | { i: number; t: number; loop_step: number; type: 'tool_call'; agent: AgentName; tool: string; args: Record<string, unknown> }
  | { i: number; t: number; loop_step: number; type: 'tool_result'; agent: AgentName; tool: string; result: string }
  | { i: number; t: number; loop_step: number; type: 'says'; agent: AgentName; text: string }
  | { i: number; t: number; loop_step: number; type: 'delegate'; agent: AgentName; to: AgentName; task: string }
  | { i: number; t: number; loop_step: number; type: 'reply'; agent: AgentName; to: AgentName; said: string }
  | { i: number; t: number; loop_step: number; type: 'refused'; agent: AgentName; to: AgentName; reason: string }
  | { i: number; t: number; loop_step: number; type: 'report'; agent: AgentName; said: string }
  | { i: number; t: number; loop_step: number; type: 'done'; agent: AgentName; stop_reason: string; stop_detail: string | null; decision: string | null }

export interface RunResult {
  run_id: string
  ticket_id: number
  ticket_status?: 'open' | 'resolved'
  stop_reason: string
  stop_detail: string | null
  message?: string
  decision?: Decision | null
  loop_steps?: number
  seconds?: number
  pending_approvals: Approval[]
}

export interface LiveResponse {
  run_id: string
  ticket_id: number
  events: LiveEvent[]
  next: number
  done: boolean
  result: RunResult | null
}

export interface ToolCall {
  agent: AgentName
  chain: string
  loop_step: number
  tool: string
  args: Record<string, unknown>
  result: string | null
}

export interface AgentActivity {
  run_id: string
  ticket_id: number
  stop_reason: string
  message: string | null
  decision: Decision | null
  loop_steps: number
  seconds: number
  created_at: string
  agents: {
    agent: AgentName
    said: (string | null)[]
    tools_used: string[]
    tool_calls: ToolCall[]
    delegated_to: AgentName[]
  }[]
}

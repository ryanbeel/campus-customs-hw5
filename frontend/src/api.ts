import type { AgentActivity, Approval, Cash, LiveResponse, Ticket } from './types'

// The FastAPI backend from Problem 7 (backend/: uvicorn main:app --reload --port 8000).
export const API_URL = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '')

async function call<T>(path: string, method: 'GET' | 'POST' = 'GET'): Promise<T> {
  const res = await fetch(API_URL + path, { method })
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try { detail = (await res.json()).detail ?? detail } catch { /* not JSON */ }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

export const api = {
  tickets: () => call<Ticket[]>('/api/tickets'),
  cash: () => call<Cash>('/api/cash'),
  approvals: () => call<Approval[]>('/api/approvals'),
  start: (ticketId: number) => call<{ run_id: string; ticket_id: number }>(`/api/tickets/${ticketId}/start`, 'POST'),
  live: (runId: string, after: number) => call<LiveResponse>(`/api/runs/${runId}/live?after=${after}`),
  activity: (ticketId: number) => call<AgentActivity>(`/api/tickets/${ticketId}/agents`),
  approve: (id: number) => call<{ checking_balance: number; effect: string }>(`/api/approvals/${id}/approve`, 'POST'),
  reject: (id: number) => call<{ rejected: boolean }>(`/api/approvals/${id}/reject`, 'POST'),
  reset: () => call<{ checking_balance: number; open_tickets: number }>('/api/reset', 'POST'),
}

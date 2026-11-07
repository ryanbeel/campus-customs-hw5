import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { API_URL, api } from './api'
import { COURT, describe } from './court'
import Cat from './components/Cat'
import TicketList from './components/TicketList'
import ThroneRoom from './components/ThroneRoom'
import Chronicle from './components/Chronicle'
import Decree from './components/Decree'
import ApprovalModal from './components/ApprovalModal'
import Treasury from './components/Treasury'
import type { AgentActivity, AgentName, Approval, Cash, LiveEvent, Ticket } from './types'

type Run = { runId: string | null; events: LiveEvent[]; running: boolean; error: string | null; replay?: boolean }

export default function App() {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [cash, setCash] = useState<Cash | null>(null)
  const [approvals, setApprovals] = useState<Approval[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [runs, setRuns] = useState<Record<number, Run>>({})
  const [activity, setActivity] = useState<Record<number, AgentActivity>>({})
  const [offline, setOffline] = useState<string | null>(null)
  const [later, setLater] = useState<Set<number>>(new Set())
  const [sealBusy, setSealBusy] = useState(false)
  const [sealError, setSealError] = useState<string | null>(null)
  const alive = useRef(true)

  const refresh = useCallback(async () => {
    try {
      const [t, c, a] = await Promise.all([api.tickets(), api.cash(), api.approvals()])
      setTickets(t); setCash(c); setApprovals(a); setOffline(null)
    } catch (err) {
      setOffline(err instanceof Error ? err.message : String(err))
    }
  }, [])

  useEffect(() => { alive.current = true; refresh(); return () => { alive.current = false } }, [refresh])

  const loadActivity = useCallback(async (id: number) => {
    try {
      const act = await api.activity(id)
      setActivity(prev => ({ ...prev, [id]: act }))
      return act
    } catch { return null }
  }, [])

  const select = (id: number) => {
    setSelectedId(id)
    const t = tickets.find(x => x.id === id)
    if (t?.last_run && !activity[id]) {
      loadActivity(id).then(act => {
        if (act) setRuns(prev => prev[id] ? prev : { ...prev, [id]: { runId: act.run_id, events: replay(act), running: false, error: null, replay: true } })
      })
    }
  }

  const start = async (id: number) => {
    setSelectedId(id)
    setLater(prev => { const s = new Set(prev); s.delete(id); return s })
    setActivity(prev => { const n = { ...prev }; delete n[id]; return n })
    setRuns(prev => ({ ...prev, [id]: { runId: null, events: [], running: true, error: null } }))
    try {
      const { run_id } = await api.start(id)
      setRuns(prev => ({ ...prev, [id]: { ...prev[id], runId: run_id } }))
      let after = 0
      // Poll the live feed until the team is done.
      while (alive.current) {
        const live = await api.live(run_id, after)
        after = live.next
        if (live.events.length) {
          setRuns(prev => ({ ...prev, [id]: { ...prev[id], events: [...prev[id].events, ...live.events] } }))
        }
        if (live.done) {
          const failed = live.result?.stop_reason === 'error' ? live.result.stop_detail : null
          setRuns(prev => ({ ...prev, [id]: { ...prev[id], running: false, error: failed } }))
          await Promise.all([refresh(), loadActivity(id)])
          break
        }
        await new Promise(r => setTimeout(r, 700))
      }
    } catch (err) {
      setRuns(prev => ({ ...prev, [id]: { ...prev[id], running: false, error: err instanceof Error ? err.message : String(err) } }))
      refresh()
    }
  }

  const reset = async () => {
    if (!window.confirm('Start a fresh day? This puts the database back to its original values (tickets open, $3,400 in checking) and clears past runs from the board.')) return
    try {
      await api.reset()
      setRuns({}); setActivity({}); setLater(new Set()); setSelectedId(null)
      await refresh()
    } catch (err) {
      setOffline(err instanceof Error ? err.message : String(err))
    }
  }

  // A link like ?ticket=101 opens that ticket straight away (used for the resolved-board screenshots).
  const linked = useRef(false)
  useEffect(() => {
    const id = Number(new URLSearchParams(window.location.search).get('ticket'))
    if (!linked.current && id && tickets.some(t => t.id === id)) { linked.current = true; select(id) }
  })

  const selected = tickets.find(t => t.id === selectedId) ?? null
  const run = selectedId !== null ? runs[selectedId] : undefined
  const runningId = Object.entries(runs).find(([, r]) => r.running)?.[0]
  const events = run?.events ?? []
  const running = !!run?.running
  const pending = approvals.filter(a => a.ticket_id === selectedId && a.status === 'pending')
  const seal = !running && selectedId !== null && !later.has(selectedId) ? pending[0] : undefined
  const act = selectedId !== null ? activity[selectedId] : undefined

  const now = useMemo(() => nowLine(events, running), [events, running])

  const decide = async (approve: boolean) => {
    if (!seal) return
    setSealBusy(true); setSealError(null)
    try {
      if (approve) await api.approve(seal.id)
      else await api.reject(seal.id)
      await refresh()
    } catch (err) {
      setSealError(err instanceof Error ? err.message : String(err))
    } finally {
      setSealBusy(false)
    }
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <Cat agent="boss" size={54} title="King Ryan Jr." />
          <div>
            <h1>Ryan Jr.'s Royal Court</h1>
            <p>Campus Customs agent dashboard · shop date {cash?.date ?? '…'}</p>
          </div>
        </div>
        <Treasury balance={cash?.balance ?? null} asOf={cash?.date ?? null} />
        <button className="btn ghost" onClick={reset} disabled={!!runningId} title="Reset the database to its original values">
          🌅 New day (reset)
        </button>
      </header>

      {offline && (
        <div className="banner">
          The castle gates are closed: can't reach the backend at <code>{API_URL}</code> ({offline}). Start it from
          <code>backend/</code> with <code>uvicorn main:app --reload --port 8000</code>, then
          <button className="link-btn" onClick={refresh}>try again</button>.
        </div>
      )}

      <main className="layout">
        <TicketList tickets={tickets} approvals={approvals} selectedId={selectedId} runningId={runningId ? Number(runningId) : null}
                    onSelect={select} onStart={start} />

        <div className="center">
          <div className={`nowbar ${running ? 'live' : ''}`}>
            {selected ? (
              <>
                <span className="now-ticket">Petition #{selected.id} · {selected.subject}</span>
                <span className="now-what">{now}</span>
                {run?.replay && <span className="muted small">Replayed from the last saved run</span>}
              </>
            ) : <span className="now-what">Choose a petition to begin.</span>}
          </div>
          {run?.error && <div className="banner small">The court hit a problem: {run.error}</div>}
          <ThroneRoom events={events} running={running} hasTicket={!!selected} />
          {selected && act && !running && <Decree ticket={selected} activity={act} pendingCount={pending.length} />}
          {selected && !running && pending.length > 0 && later.has(selected.id) && (
            <button className="btn seal-btn wide" onClick={() => setLater(prev => { const s = new Set(prev); s.delete(selected.id); return s })}>
              🔏 {pending.length} payment{pending.length > 1 ? 's' : ''} waiting for your seal
            </button>
          )}
        </div>

        <Chronicle events={events} running={running} />
      </main>

      {seal && (
        <ApprovalModal approval={seal} balance={cash?.balance ?? null} busy={sealBusy} error={sealError}
                       onApprove={() => decide(true)} onReject={() => decide(false)}
                       onLater={() => { setLater(prev => new Set(prev).add(seal.ticket_id ?? -1)); setSealError(null) }} />
      )}
    </div>
  )
}

function nowLine(events: LiveEvent[], running: boolean): string {
  if (!events.length) return running ? 'Summoning the court…' : 'The court is resting.'
  const last = [...events].reverse().find(e => e.type !== 'thinking') ?? events[events.length - 1]
  if (last.type === 'done') return last.stop_reason === 'completed' ? '👑 The King has issued his decree.' : `The court stopped: ${last.stop_reason}`
  const who: AgentName = last.type === 'delegate' || last.type === 'reply' ? last.to : last.agent
  return running ? `${COURT[who].name} is working · ${COURT[last.agent].name} ${describe(last)}` : 'The court is resting.'
}

// Rebuild a simple event list from a saved run, so the board can show a past run.
function replay(act: AgentActivity): LiveEvent[] {
  const out: LiveEvent[] = []
  const push = (e: Omit<LiveEvent, 'i' | 't'> & Record<string, unknown>) =>
    out.push({ ...(e as object), i: out.length, t: 0 } as LiveEvent)
  const calls = act.agents.flatMap(a => a.tool_calls).sort((x, y) => x.loop_step - y.loop_step)
  const started = new Set<string>()
  for (const c of calls) {
    if (!started.has(c.agent)) { started.add(c.agent); push({ type: 'start', agent: c.agent, chain: [], loop_step: c.loop_step }) }
    if (c.tool === 'delegate') push({ type: 'delegate', agent: c.agent, to: c.args.agent as AgentName, task: String(c.args.task ?? ''), loop_step: c.loop_step })
    else push({ type: 'tool_call', agent: c.agent, tool: c.tool, args: c.args, loop_step: c.loop_step })
  }
  for (const a of [...act.agents].reverse()) {
    const said = a.said.find(Boolean)
    if (said) push({ type: 'report', agent: a.agent, said, loop_step: act.loop_steps })
  }
  push({ type: 'done', agent: 'boss', stop_reason: act.stop_reason, stop_detail: null, decision: act.decision?.decision ?? null, loop_step: act.loop_steps })
  return out
}

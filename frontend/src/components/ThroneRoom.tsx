import Cat from './Cat'
import { COURT, COURT_ORDER, clip, describe, toolLabel } from '../court'
import type { AgentName, LiveEvent } from '../types'

// Stage coordinates (the stage keeps this aspect ratio, so lines and cats line up).
const W = 1000
const H = 800
const POS: Record<AgentName, { x: number; y: number }> = {
  boss: { x: 500, y: 150 },
  facilities: { x: 130, y: 530 },
  inventory: { x: 375, y: 530 },
  accounting: { x: 625, y: 530 },
  customer_service: { x: 870, y: 530 },
}

type Props = { events: LiveEvent[]; running: boolean; hasTicket: boolean }

export default function ThroneRoom({ events, running, hasTicket }: Props) {
  // Who's working: the agent behind the latest event (a hand-off makes the receiver active).
  const last = [...events].reverse().find(e => e.type !== 'done')
  const finished = events.some(e => e.type === 'done')
  let active: AgentName | null = null
  if (running && last) active = last.type === 'delegate' ? last.to : last.type === 'reply' ? last.to : last.agent

  // Latest thing each agent said or did.
  const bubbles: Partial<Record<AgentName, { text: string; kind: string }>> = {}
  const joined = new Set<AgentName>()
  const reported = new Set<AgentName>()
  const edges = new Map<string, { from: AgentName; to: AgentName; count: number; last: number }>()
  for (const e of events) {
    if (e.type === 'start') joined.add(e.agent)
    if (e.type === 'report') reported.add(e.agent)
    if (e.type === 'delegate') {
      const key = `${e.agent}>${e.to}`
      const edge = edges.get(key) ?? { from: e.agent, to: e.to, count: 0, last: 0 }
      edges.set(key, { ...edge, count: edge.count + 1, last: e.i })
    }
    if (e.type === 'thinking' && bubbles[e.agent]) continue
    if (e.type === 'done') continue
    const text = e.type === 'tool_call' ? `${toolLabel(e.tool).icon} ${describe(e)}` : describe(e)
    bubbles[e.agent] = { text, kind: e.type }
  }
  // The newest hand-off or reply animates along its line.
  const recent = [...events].reverse().find(e => e.type === 'delegate' || e.type === 'reply')
  const live = running && recent && (recent.type === 'delegate' || recent.type === 'reply')
    ? { from: recent.agent, to: recent.to }
    : null

  return (
    <section className="throne card" aria-label="Throne room">
      <div className="stage" style={{ aspectRatio: `${W} / ${H}` }}>
        <svg className="links" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
          {/* Chain of command: faint lines from the king to every member */}
          {COURT_ORDER.map(a => (
            <line key={a} x1={POS.boss.x} y1={BOSS_FOOT} x2={POS[a].x} y2={POS[a].y - COURT_HEAD}
                  className="link idle" />
          ))}
          {[...edges.values()].map(({ from, to, count }) => {
            const d = pathBetween(from, to)
            const isLive = live && ((live.from === from && live.to === to) || (live.from === to && live.to === from))
            return (
              <g key={`${from}>${to}`}>
                <path d={d} className={`link used ${isLive ? 'live' : ''}`} />
                {count > 1 && <text {...midpoint(from, to)} className="link-count">×{count}</text>}
              </g>
            )
          })}
          {live && (
            <g>
              <path id="live-path" d={pathBetween(live.from, live.to)} fill="none" stroke="none" />
              <g className="scroll-token">
                <circle r="16" fill="#fff6d8" stroke="#a5781f" strokeWidth="3" />
                <text textAnchor="middle" dy="6" fontSize="18">📜</text>
                <animateMotion dur="1.1s" repeatCount="indefinite" rotate="0">
                  <mpath href="#live-path" />
                </animateMotion>
              </g>
            </g>
          )}
        </svg>

        {(['boss', ...COURT_ORDER] as AgentName[]).map(a => {
          const p = POS[a]
          const status = active === a ? 'working' : reported.has(a) ? 'reported' : joined.has(a) ? 'waiting' : 'idle'
          const bubble = bubbles[a]
          return (
            <div key={a} className={`seat seat-${a} ${status}`}
                 style={{ left: `${(p.x / W) * 100}%`, top: `${(p.y / H) * 100}%` }}>
              {bubble && hasTicket && (
                <div className={`bubble bubble-${bubble.kind} ${a === 'boss' ? 'right' : 'below'}`}>
                  {clip(bubble.text, a === 'boss' ? 220 : 120)}
                </div>
              )}
              <div className="cat-wrap">
                {status === 'working' && <div className="halo" />}
                <Cat agent={a} size={a === 'boss' ? 150 : 104} title={COURT[a].name} />
              </div>
              <div className="nameplate">
                <strong>{COURT[a].name}</strong>
                <span>{COURT[a].title}</span>
                <em className={`chip ${status}`}>{STATUS_LABEL[status]}</em>
              </div>
            </div>
          )
        })}

        {!hasTicket && <div className="stage-hint">Pick a petition on the left, then press <b>Summon the court</b>.</div>}
        {hasTicket && !running && !finished && events.length === 0 && (
          <div className="stage-hint">The court is assembled. Press <b>Summon the court</b> to begin.</div>
        )}
      </div>
    </section>
  )
}

const STATUS_LABEL = { working: 'Working', reported: 'Reported', waiting: 'Waiting on help', idle: 'Resting' }

// Lines run in the open gap between the king's nameplate and the court's hats.
const BOSS_FOOT = 330
const COURT_HEAD = 130

function anchor(a: AgentName) {
  const p = POS[a]
  return a === 'boss' ? { x: p.x, y: BOSS_FOOT } : { x: p.x, y: p.y - COURT_HEAD }
}

function pathBetween(from: AgentName, to: AgentName) {
  const a = anchor(from)
  const b = anchor(to)
  if (from === 'boss' || to === 'boss') return `M${a.x} ${a.y} L${b.x} ${b.y}`
  // Court-to-court hand-offs arc over the row.
  const lift = 60 + Math.abs(a.x - b.x) * 0.1
  return `M${a.x} ${a.y} Q${(a.x + b.x) / 2} ${a.y - lift} ${b.x} ${b.y}`
}

function midpoint(from: AgentName, to: AgentName) {
  const a = anchor(from)
  const b = anchor(to)
  const lift = from === 'boss' || to === 'boss' ? 0 : (60 + Math.abs(a.x - b.x) * 0.1) / 2
  return { x: (a.x + b.x) / 2 + 12, y: (a.y + b.y) / 2 - lift }
}

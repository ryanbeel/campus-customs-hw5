import { useEffect, useRef } from 'react'
import Cat from './Cat'
import { COURT, describe, toolLabel } from '../court'
import type { LiveEvent } from '../types'

// The running log of who did and said what, newest at the bottom.
export default function Chronicle({ events, running }: { events: LiveEvent[]; running: boolean }) {
  const list = useRef<HTMLOListElement>(null)
  const shown = events.filter(e => e.type !== 'thinking')
  // Keep the newest entry in view by scrolling the list itself, never the page.
  useEffect(() => { if (list.current) list.current.scrollTop = list.current.scrollHeight }, [shown.length])

  return (
    <section className="chronicle card" aria-label="Royal chronicle">
      <header className="card-head">
        <h2>Royal Chronicle</h2>
        <span className="muted">{running ? 'Live' : shown.length ? `${shown.length} entries` : 'Waiting'}</span>
      </header>
      <ol className="entries" aria-live="polite" ref={list}>
        {shown.length === 0 && <li className="empty">When the court works, every step appears here: who acted, which tool they used, and what they said.</li>}
        {shown.map(e => (
          <li key={e.i} className={`entry entry-${e.type}`}>
            <div className="who">
              <Cat agent={e.agent} size={30} title={COURT[e.agent].name} />
            </div>
            <div className="what">
              <div className="line1">
                <strong>{COURT[e.agent].name}</strong>
                {e.type === 'delegate' && <span className="arrow"> 📯 → {COURT[e.to].name}</span>}
                {e.type === 'reply' && <span className="arrow"> ↩ {COURT[e.to].name}</span>}
                {e.type === 'tool_call' && <span className="tool">{toolLabel(e.tool).icon} <code>{e.tool}</code></span>}
                <span className="time">{e.t.toFixed(1)}s · step {e.loop_step}</span>
              </div>
              <div className="line2">{describe(e)}</div>
            </div>
          </li>
        ))}
      </ol>
    </section>
  )
}

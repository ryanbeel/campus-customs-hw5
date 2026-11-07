import { useEffect, useRef, useState } from 'react'
import { money } from '../court'

// The checking balance. It counts down (with a "- $X" tag) when a payment is approved.
export default function Treasury({ balance, asOf }: { balance: number | null; asOf: string | null }) {
  const [shown, setShown] = useState<number | null>(balance)
  const [delta, setDelta] = useState<number | null>(null)
  const prev = useRef<number | null>(balance)

  useEffect(() => {
    if (balance === null) return
    const from = prev.current
    prev.current = balance
    if (from === null || from === balance) { setShown(balance); return }
    setDelta(balance - from)
    const start = performance.now()
    let frame = 0
    const tick = (now: number) => {
      const k = Math.min(1, (now - start) / 900)
      setShown(from + (balance - from) * (1 - Math.pow(1 - k, 3)))
      if (k < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    const clear = setTimeout(() => setDelta(null), 3500)
    return () => { cancelAnimationFrame(frame); clearTimeout(clear) }
  }, [balance])

  return (
    <div className="treasury" aria-live="polite">
      <span className="coins" aria-hidden="true">💰</span>
      <div>
        <span className="label">Royal Treasury · Checking</span>
        <strong className="amount">{shown === null ? '—' : money(shown)}</strong>
        {asOf && <span className="asof">as of {asOf}</span>}
      </div>
      {delta !== null && <span className={`delta ${delta < 0 ? 'down' : 'up'}`}>{delta < 0 ? '−' : '+'}{money(Math.abs(delta))}</span>}
    </div>
  )
}

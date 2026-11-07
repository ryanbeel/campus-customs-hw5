import { money } from '../court'
import type { Approval, Ticket } from '../types'

type Props = {
  tickets: Ticket[]
  approvals: Approval[]
  selectedId: number | null
  runningId: number | null
  onSelect: (id: number) => void
  onStart: (id: number) => void
}

const TYPE_LABEL: Record<string, string> = {
  customer_order: 'Customer order',
  rent_notice: 'Rent notice',
  price_override: 'Price override',
}

export default function TicketList({ tickets, approvals, selectedId, runningId, onSelect, onStart }: Props) {
  return (
    <section className="petitions card" aria-label="Tickets">
      <header className="card-head">
        <h2>Petitions</h2>
        <span className="muted">{tickets.filter(t => t.status === 'open').length} open</span>
      </header>
      <div className="ticket-list">
        {tickets.map(t => {
          const selected = t.id === selectedId
          const running = t.id === runningId
          return (
            <article key={t.id} className={`ticket ${selected ? 'selected' : ''} ${t.status}`}
                     onClick={() => onSelect(t.id)} tabIndex={0}
                     onKeyDown={e => { if (e.key === 'Enter') onSelect(t.id) }}
                     aria-current={selected}>
              {t.status === 'resolved' && <div className="seal" aria-label="Resolved">RESOLVED</div>}
              <div className="ticket-top">
                <span className="ticket-num">#{t.id}</span>
                <span className="ticket-type">{TYPE_LABEL[t.type] ?? t.type}</span>
              </div>
              <h3>{t.subject}</h3>
              <p className="from">from <b>{t.requester}</b></p>
              <p className="note">“{t.notes}”</p>
              <div className="ticket-foot">
                <span className={`status ${running ? 'working' : t.status}`}>
                  {running ? 'Court at work…' : t.status === 'resolved' ? 'Resolved' : 'Open'}
                </span>
                {approvals.filter(a => a.ticket_id === t.id && a.status === 'pending').map(a => (
                  <span key={a.id} className="status seal-needed">
                    {a.kind === 'rent' ? `Rent ${money(a.amount)} needs your seal` : `Supplier bill ${money(a.amount)} needs your seal`}
                  </span>
                ))}
              </div>
              {selected && (
                <button className="btn primary summon" disabled={runningId !== null}
                        onClick={ev => { ev.stopPropagation(); onStart(t.id) }}>
                  {running ? 'The court is working…' : t.last_run ? '👑 Summon the court again' : '👑 Summon the court'}
                </button>
              )}
            </article>
          )
        })}
      </div>
    </section>
  )
}

import Cat from './Cat'
import { COURT, EXPECTATIONS, clip, toolLabel } from '../court'
import type { AgentActivity, AgentName, Ticket } from '../types'

type Props = { ticket: Ticket; activity: AgentActivity; pendingCount: number }

// The clean summary after a run, plus how it compared with the owner's Problem 6 plan.
export default function Decree({ ticket, activity, pendingCount }: Props) {
  const d = activity.decision
  const usedAgents = activity.agents.map(a => a.agent)
  const usedTools = [...new Set(activity.agents.flatMap(a => a.tools_used))]
  const plan = EXPECTATIONS[ticket.id]
  const completed = activity.stop_reason === 'completed'

  const verdict = !completed
    ? { tone: 'bad', label: 'Not finished', text: `The court stopped early (${activity.stop_reason}).` }
    : pendingCount > 0
      ? { tone: 'wait', label: 'Done, waiting on your seal', text: 'The court finished. A payment is waiting for your approval.' }
      : { tone: 'good', label: 'Success', text: ticket.status === 'resolved' ? 'The court finished and the ticket is resolved.' : 'The court finished its work.' }

  return (
    <section className="decree card" aria-label="Summary">
      <header className="card-head">
        <h2>Royal Decree · Ticket #{ticket.id}</h2>
        <span className={`verdict ${verdict.tone}`}>{verdict.label}</span>
      </header>

      <div className="decree-grid">
        <div className="decree-main">
          <div className="decree-scroll">
            <div className="decree-king"><Cat agent="boss" size={56} title="King Ryan Jr." /></div>
            <div>
              <p className="eyebrow">King Ryan Jr. decrees</p>
              <p className="decision">{d?.decision ?? activity.message ?? 'No decision was returned.'}</p>
              <p className="muted small">{verdict.text} {activity.loop_steps} steps · {activity.seconds.toFixed(1)} seconds</p>
            </div>
          </div>

          {d?.reasoning?.length ? (
            <>
              <h3>Why</h3>
              <ul className="bullets">{d.reasoning.slice(0, 4).map((r, i) => <li key={i}>{r}</li>)}</ul>
            </>
          ) : null}

          <h3>What the court did</h3>
          <ul className="court-did">
            {activity.agents.map(a => (
              <li key={a.agent}>
                <Cat agent={a.agent} size={34} title={COURT[a.agent].name} />
                <div>
                  <strong>{COURT[a.agent].name}</strong>
                  {a.tools_used.length > 0 && (
                    <span className="tools"> {a.tools_used.map(t => <span key={t} title={t}>{toolLabel(t).icon}</span>)}</span>
                  )}
                  {a.delegated_to.length > 0 && (
                    <span className="muted small"> · asked {[...new Set(a.delegated_to)].map(x => COURT[x]?.name ?? x).join(', ')}</span>
                  )}
                  <p>{clip(a.said.find(Boolean) ?? 'No report.', 220)}</p>
                </div>
              </li>
            ))}
          </ul>

          {d?.customer_message && (
            <>
              <h3>Letter to {ticket.requester}</h3>
              <blockquote className="letter">{d.customer_message}</blockquote>
            </>
          )}
          {d?.unknowns?.length ? (
            <p className="muted small"><b>Not in the records:</b> {d.unknowns.slice(0, 3).join(' · ')}</p>
          ) : null}
        </div>

        {plan && (
          <aside className="plan">
            <h3>My plan vs. what happened</h3>
            <Compare label="Agents" expected={plan.agents} actual={usedAgents}
                     name={a => COURT[a as AgentName]?.name ?? a} />
            <Compare label="Tools" expected={plan.tools} actual={usedTools}
                     name={t => `${toolLabel(t).icon} ${t}`} />
            <div className="outcome">
              <p className="eyebrow">I expected</p>
              <p>{plan.outcome}</p>
              <p className="eyebrow">What happened</p>
              <p>{clip(d?.decision ?? activity.message, 260)}</p>
            </div>
            <p className={`plan-score ${verdict.tone}`}>
              {score(plan.agents, usedAgents)} of {plan.agents.length} planned agents and {score(plan.tools, usedTools)} of {plan.tools.length} planned tools showed up.
            </p>
          </aside>
        )}
      </div>
    </section>
  )
}

const score = (expected: string[], actual: string[]) => expected.filter(x => actual.includes(x)).length

function Compare({ label, expected, actual, name }: {
  label: string; expected: string[]; actual: string[]; name: (x: string) => string
}) {
  const extra = actual.filter(x => !expected.includes(x))
  return (
    <div className="compare-row">
      <p className="eyebrow">{label}</p>
      <div className="chips">
        {expected.map(x => (
          <span key={x} className={`pchip ${actual.includes(x) ? 'hit' : 'miss'}`}>
            {actual.includes(x) ? '✓' : '✗'} {name(x)}
          </span>
        ))}
        {extra.map(x => <span key={x} className="pchip extra">+ {name(x)}</span>)}
      </div>
    </div>
  )
}

import Cat from './Cat'
import { money } from '../court'
import type { Approval } from '../types'

type Props = {
  approval: Approval
  balance: number | null
  busy: boolean
  error: string | null
  onApprove: () => void
  onReject: () => void
  onLater: () => void
}

const KIND: Record<Approval['kind'], string> = {
  invoice: 'Pay a supplier bill',
  rent: 'Pay the rent',
  purchase_order: 'Pay a supplier for new stock',
}

const WHO: Record<string, string> = {
  supplier: 'Supplier bill · not a customer refund',
  landlord: 'Landlord · shop rent',
}

// The agents only prepare payments. Nothing is paid until the owner presses the seal.
export default function ApprovalModal({ approval, balance, busy, error, onApprove, onReject, onLater }: Props) {
  const after = balance === null ? null : balance - approval.amount
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="seal-title">
      <div className="modal card">
        <div className="modal-head">
          <Cat agent="accounting" size={70} title="Lady Ledger" />
          <div>
            <p className="eyebrow">Lady Ledger requests the King's seal</p>
            <h2 id="seal-title">{KIND[approval.kind]}: {money(approval.amount)}</h2>
            {approval.explain && <span className={`payee-tag ${approval.explain.payee_type}`}>{WHO[approval.explain.payee_type]}</span>}
          </div>
        </div>
        {approval.explain?.stock && approval.explain.stock.short > 0 && (
          <div className="stock-alert">
            <strong>📦 Out of stock:</strong> {approval.explain.stock.name} size {approval.explain.stock.size} ·{' '}
            {approval.explain.stock.on_hand} on hand, {approval.explain.stock.needed} needed. We need more from the supplier.
          </div>
        )}
        {approval.explain && (
          <div className="whats-going-on">
            <p className="eyebrow">What's going on</p>
            <ul>{approval.explain.lines.map((l, i) => <li key={i}>{l}</li>)}</ul>
          </div>
        )}
        <dl className="seal-facts">
          <dt>Pay to</dt><dd>{approval.payee}</dd>
          <dt>For</dt><dd>{approval.reference ?? '—'}</dd>
          <dt>Lady Ledger's note</dt><dd>{approval.reason ?? '—'}</dd>
          <dt>Treasury now</dt><dd>{balance === null ? '—' : money(balance)}</dd>
          <dt>After paying</dt><dd className={after !== null && after < 0 ? 'neg' : ''}>{after === null ? '—' : money(after)}</dd>
        </dl>
        <p className="muted small">The agents prepared this. Nothing has been paid. Approving records the payment and lowers the checking balance.</p>
        {error && <p className="error">{error}</p>}
        <div className="modal-actions">
          <button className="btn ghost" onClick={onLater} disabled={busy}>Decide later</button>
          <button className="btn" onClick={onReject} disabled={busy}>Reject</button>
          <button className="btn seal-btn" onClick={onApprove} disabled={busy}>{busy ? 'Sealing…' : '🔏 Approve and pay'}</button>
        </div>
      </div>
    </div>
  )
}

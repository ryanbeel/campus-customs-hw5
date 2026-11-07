import type { AgentName, LiveEvent } from './types'

// The royal court: who each agent is on the board.
export const COURT: Record<AgentName, { name: string; title: string; job: string }> = {
  boss: { name: 'King Ryan Jr.', title: 'The Boss', job: 'Reads every petition, sends the court to work, and issues the final decree.' },
  facilities: { name: 'Sir Pawcelot', title: 'Knight of the Keep · Facilities', job: 'Guards the castle: lease, rent and landlord.' },
  inventory: { name: 'Squire Biscuit', title: 'Keeper of the Storeroom · Inventory', job: 'Counts stock by SKU and size and finds who can restock it.' },
  accounting: { name: 'Lady Ledger', title: 'Royal Treasurer · Accounting', job: 'Minds the treasury, invoices and margins, and prepares payments for your seal.' },
  customer_service: { name: 'Jingles the Jester', title: 'Herald of Good Cheer · Customer Service', job: 'Writes kind, fact-checked letters to customers. Always ends with a smile.' },
}

export const COURT_ORDER: AgentName[] = ['facilities', 'inventory', 'accounting', 'customer_service']

// What each MCP tool looks like as a medieval chore.
export const TOOL_LABELS: Record<string, { label: string; icon: string }> = {
  get_tickets: { label: 'reads the petition', icon: '📜' },
  check_inventory: { label: 'counts the storeroom', icon: '📦' },
  find_vendors: { label: 'seeks a merchant to restock', icon: '🛒' },
  get_documents: { label: 'unrolls the scrolls (invoices, leases, payments)', icon: '🗂️' },
  get_financials: { label: 'works the abacus (margins and cash)', icon: '🧮' },
  send_customer_email: { label: 'sends a carrier pigeon (simulated email)', icon: '🕊️' },
  update_inventory: { label: 'updates the storeroom ledger', icon: '✍️' },
  check_order_status: { label: 'checks the order records', icon: '🔎' },
  get_checking_account: { label: 'counts the royal treasury', icon: '💰' },
  delegate: { label: 'summons a member of the court', icon: '📯' },
}

export const toolLabel = (tool: string) => TOOL_LABELS[tool] ?? { label: tool, icon: '🛠️' }

// Problem 6: what the owner expected for each ticket (from output/desk_tickets.html).
export const EXPECTATIONS: Record<number, {
  agents: AgentName[]; tools: string[]; flow: string[]; outcome: string
}> = {
  101: {
    agents: ['boss', 'customer_service', 'accounting', 'inventory'],
    tools: ['check_inventory', 'check_order_status'],
    flow: [
      'Boss reads the ticket and assigns it',
      'Customer Service takes it (looks like a completed sale running late)',
      'Accounting confirms the purchase happened',
      'Inventory checks whether it already shipped',
      'Customer Service tells Tauhid it is on the way and when to expect it',
      'Boss reports back to me',
    ],
    outcome: 'Purchase confirmed and shipped; Tauhid told it is on the way with timing.',
  },
  102: {
    agents: ['boss', 'facilities', 'accounting'],
    tools: ['get_documents'],
    flow: [
      'Boss reads the ticket and assigns it',
      'Facilities checks the rent and lease and confirms we owe it',
      'Accounting updates the books and sets up the payment',
      'Boss reports back to me',
    ],
    outcome: 'Rent confirmed as owed and the payment set up.',
  },
  103: {
    agents: ['boss', 'inventory', 'accounting', 'customer_service'],
    tools: ['check_inventory', 'update_inventory', 'send_customer_email'],
    flow: [
      'Boss sends it to Inventory',
      'Inventory checks we have the hoodies, confirms and updates stock',
      'Accounting records the sale and creates an invoice',
      'Customer Service contacts the Yale AI Club with next steps',
      'Boss reports back to me',
    ],
    outcome: 'Stock confirmed and updated, sale recorded with an invoice, club told next steps.',
  },
}

export const money = (n: number) =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 })

export const clip = (s: string | null | undefined, n = 160) =>
  !s ? '' : s.length > n ? s.slice(0, n - 1).trimEnd() + '…' : s

// One friendly line per live event, for speech bubbles and the chronicle.
export function describe(e: LiveEvent): string {
  switch (e.type) {
    case 'start': return e.agent === 'boss' ? 'takes the throne and reads the petition' : 'steps forward to help'
    case 'thinking': return 'is thinking…'
    case 'tool_call': return `${toolLabel(e.tool).label}${argsText(e.args)}`
    case 'tool_result': return `→ ${clip(e.result, 170)}`
    case 'says': return clip(e.text, 160)
    case 'delegate': return `asks ${COURT[e.to].name}: “${clip(e.task, 150)}”`
    case 'reply': return `reports back to ${COURT[e.to].name}`
    case 'refused': return `couldn't reach ${COURT[e.to].name} (${e.reason})`
    case 'report': return clip(e.said, 180)
    case 'done': return e.stop_reason === 'completed' ? 'issues the royal decree' : `stopped: ${e.stop_reason}`
  }
}

function argsText(args: Record<string, unknown>): string {
  const bits = Object.entries(args ?? {})
    .filter(([, v]) => v !== null && v !== undefined && v !== '' && typeof v !== 'object')
    .slice(0, 3)
    .map(([k, v]) => `${k}=${v}`)
  return bits.length ? ` (${bits.join(', ')})` : ''
}

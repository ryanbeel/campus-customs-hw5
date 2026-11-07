# Campus Customs Agent Harness

A reference for how the Campus Customs agent system works: what each part does, where it lives, and the rules it follows. Everything here describes the system as it runs today.

## What the system does

Campus Customs gets **tickets**: customer orders, bills and requests. A team of five AI agents works each ticket. The **Boss** reads it and hands pieces to **Inventory**, **Accounting**, **Facilities** and **Customer Service**, who can also ask each other for help. The agents look things up and act only through **MCP tools** that read and write the shop's SQLite database. They can **prepare** payments, but **only the owner can approve them**, by clicking in the dashboard. Every step is written to an append-only audit trail.

```
 Owner in the browser                    Backend (FastAPI)                Agents (Pydantic AI)          MCP server            Database
 ┌────────────────────┐  HTTP   ┌──────────────────────────┐  runs   ┌───────────────────┐  MCP   ┌──────────────┐  SQL  ┌───────────────────────┐
 │ React dashboard    │ ──────▶ │ backend/main.py          │ ──────▶ │ Boss → 4 agents   │ ─────▶ │ mcp_server/  │ ────▶ │ data/                 │
 │ frontend/ :5173    │ ◀────── │ routes, approvals, reset │ ◀────── │ (Portkey model)   │ ◀───── │ server.py    │ ◀──── │ campus_customs_new.db │
 └────────────────────┘         └──────────────────────────┘         └───────────────────┘        └──────────────┘       └───────────────────────┘
          │ approve / reject                 │ writes payments only on approval        │ every step
          └──────────────────────────────────┘                                        ▼
                                                                          output/audit_trail.json
```

### A ticket from start to finish

1. In the dashboard, the owner picks a ticket and clicks **Summon the court**, which calls `POST /api/tickets/{id}/start`.
2. The backend starts the team in the background. The Boss reads the ticket with `get_tickets` and delegates to the agents it needs.
3. Each agent calls its MCP tools, reports back, and may delegate to another agent. The dashboard polls `/api/runs/{run_id}/live` and shows every step.
4. The Boss returns a final decision. Any payment Accounting prepared is saved as a **pending approval**, and nothing is paid yet.
5. The owner clicks **Approve and pay** or **Reject**. Only an approval writes to `payments` and lowers checking.
6. When the run is complete and nothing is waiting for approval, the ticket is marked **resolved**.

## At a glance

| Part | Where | What it does |
|---|---|---|
| Working database | `data/campus_customs_new.db` | The live shop data the agents use and change. |
| Original database | `data/campus_customs.db` | Untouched starting data, used by reset. |
| MCP server | `mcp_server/server.py` (FastMCP) | The 9 tools the agents use to read and change data. |
| Agent team | `backend/boss.py`, `inventory.py`, `accounting.py`, `facilities.py`, `customer_service.py` | Five Pydantic AI agents, one file each, with prompts in `backend/prompts/`. |
| Agent engine | `backend/core.py`, `team.py`, `safety.py`, `audit.py`, `models.py` | Model setup, delegation, the agent loop and limits, guardrails, the audit trail and data types. |
| Backend API | `backend/main.py` (FastAPI) | Routes for tickets, runs, live progress, approvals, cash and reset. |
| Dashboard | `frontend/` (React, Vite, TypeScript) | Ryan Jr.'s Royal Court, where the owner runs tickets and approves payments. |
| Audit trail | `output/audit_trail.json` | An append-only record of every run, step, hand-off and owner decision. |

## How to run it

```bash
# Terminal 1, from Homework 5/backend
../.venv/bin/uvicorn main:app --reload --port 8000

# Terminal 2, from Homework 5/frontend
npm run dev        # opens http://localhost:5173
```

- **Model:** the agents use the Portkey key and model in `.env`, which links to the master `.env`.
- **Fresh start:** the dashboard's **New day (reset)** button, or `POST /api/reset`, restores the original data. Checking goes back to $3,400 and all tickets reopen.

## The five agents

Every agent loads its own prompt plus `backend/prompts/shared_rules.md`. Each returns a structured result defined in `models.py`.

| Agent | Dashboard character | Job | MCP tools it holds | Returns |
|---|---|---|---|---|
| **Boss** | King Ryan Jr. (black and white, crowned) | Reads each ticket, decides who works on it, makes the final decision, and reports to the owner with the ending checking balance. | `get_tickets`, `get_checking_account` | `BossDecision`: decision, reasons, facts, unknowns, approvals needed, customer message, next steps |
| **Inventory** | Squire Biscuit | Checks stock by SKU and size, spots shortfalls, finds the restock vendor, and records real stock changes. | `check_inventory`, `find_vendors`, `get_tickets`, `update_inventory` | `SpecialistReport` |
| **Accounting** | Lady Ledger, Royal Treasurer | Manages cash and the books, tracks invoices, calculates margins, and prepares payments for the owner to approve. | `get_documents`, `get_financials`, `find_vendors`, `get_tickets`, `check_order_status`, `get_checking_account` | `SpecialistReport` with `payment_proposals` |
| **Facilities** | Sir Pawcelot, Knight of the Keep | Handles the shop space: the lease, rent and landlord, including checking that a notice matches the lease. | `get_documents`, `get_tickets` | `SpecialistReport` |
| **Customer Service** | Jingles the Jester | Writes polite, fact-checked customer messages that end with a virtual smile, and sends them as simulated emails. | `check_inventory`, `get_tickets`, `send_customer_email`, `check_order_status` | `SpecialistReport` with `customer_message` |

**How they work together**

- **Delegation:** every agent has a `delegate` tool and can hand work to any other agent, so the team is fully connected.
- **No loops:** an agent can't delegate to itself or to an agent already working on the same request, and delegation goes at most 3 levels deep.
- **Failures:** if a helper fails, the agent that asked gets a note and carries on.
- **Shared limits:** the whole team shares **50 agent-loop steps** (model calls) and **3 minutes** per request. The step limit was 20 until Problem 9, when ticket 103 needed a 21st step.
- **Payments:** no agent can pay anything. Accounting fills `payment_proposals`, each with a `kind` (`invoice`, `rent` or `purchase_order`) and a `ref_id`, and the owner decides.

## MCP tools

All 9 tools are in `mcp_server/server.py` (see `mcp_server/README.md`).
- **Read tools:** open the database read-only.
- **Write tools:** only `send_customer_email` and `update_inventory` change data, and each logs every action in its own table.
- **Labels:** values the tools work out, such as a shortfall or margin, are marked `(calculated)`.
- **Missing data:** a tool says when data is missing instead of guessing.

| Tool | Reads | Writes | What it gives the agents | Held by | Helps tickets |
|---|---|---|---|---|---|
| `get_tickets` | `tickets`, `leases`, `invoices`, `vendors`, `payments`, `customer_emails` | none | The ticket with its linked lease or invoice, payments already made, emails already sent, and how past tickets of the same type were resolved. | All five agents | 101, 102, 103 |
| `check_inventory` | `inventory`, `pricing` | none | Stock by SKU and size, aisle, list price, shortfall against a quantity, and other sizes in stock. Unit cost and margin are marked internal-only. | Inventory, Customer Service | 101, 103 |
| `find_vendors` | `vendors`, `invoices`, `inventory`, `pricing` | none | The best restock vendor (one on a past invoice first, then specialty, then fastest), units to order, estimated cost, arrival date, and what we already owe them. If no vendor fits, it says a web search is needed. | Inventory, Accounting | 101, 103 |
| `get_documents` | `invoices`, `vendors`, `leases`, `payments`, `cash_accounts` | none | Invoices with days overdue, leases with days until due, payments, and cash accounts. | Accounting, Facilities | 101, 102, 103 |
| `get_financials` | `pricing`, `inventory`, `cash_accounts`, `invoices`, `leases` | none | Accounting formulas plus margins, stock value, cash after bills, and pricing for an order with or without a discount. Past revenue isn't in the database, and the tool says so. | Accounting | 101, 102, 103 |
| `send_customer_email` | `tickets`, `inventory`, `inventory_changes`, `customer_emails` | `customer_emails` | A **simulated** email: logged and never sent. It refuses non-customer tickets, private shop terms, personal data, duplicates, and "shipping" promises that stock can't cover. | Customer Service | 101, 103 |
| `update_inventory` | `tickets`, `inventory`, `inventory_changes` | `inventory`, `inventory_changes` | Records a sale, restock, return or recount with quantities before and after. It refuses negative stock, the wrong sign, and selling more than a ticket ordered. | Inventory | 101, 103 |
| `check_order_status` | `tickets`, `inventory_changes`, `customer_emails` | none | Whether a sale is recorded (completed, partial or none) and what we told the customer about shipping. `shipment_confirmed` is always false because there's no tracking table. | Customer Service, Accounting | 101, 103 |
| `get_checking_account` | `cash_accounts`, `payments`, `invoices`, `vendors`, `leases`, `approvals` | none | The ending checking balance, every payment out with its payee and running balance, and pending approvals with the balance if they're approved. | Boss, Accounting | 101, 102, 103 |

### Why each tool mattered for each ticket (Problem 9 runs)

| Ticket | Tools used, and what they settled |
|---|---|
| **101** Bulldog tee, size S | `check_inventory` showed **0 in size S** (M, L and XL in stock). `check_order_status` showed **no sale recorded**, so nothing had shipped and nothing was owed back to Tauhid. `find_vendors` and `get_documents` tied **invoice 501** ($840, Bulldog Print Co, a rush reprint of this exact tee, 3 days overdue) to the restock, so Inventory said not to reorder. `get_checking_account` and `get_financials` showed paying it would leave $2,560. `send_customer_email` logged an honest status update to Tauhid. |
| **102** Rent due | `get_tickets` and `get_documents` confirmed the notice matches **lease 1** ($2,400 to Elm City Properties, due 2026-09-02), and `payments` showed it wasn't already paid. `get_checking_account` and `get_financials` showed $2,560 in checking, so paying would leave **$160**. `check_inventory` and `find_vendors` don't apply because a rent notice has no product. |
| **103** 20 hoodies, bulk discount | `check_inventory` showed **8 of 20** size M (12 short). `get_financials` priced 20 at list: $1,160 revenue, $720 gross profit, 62.1% margin. There's no discount policy or rate on record, so no discount was approved. `send_customer_email` logged a "backordered" note to the club. `update_inventory` wasn't called because nothing sold. |

## API routes

`backend/main.py`, run with `uvicorn main:app --reload --port 8000`:

- `GET /api/tickets`: every ticket marked `open` or `resolved`, with its latest run and how many approvals are waiting.
- `POST /api/tickets/{ticket_id}/start`: starts the agent team in the background and returns a `run_id` right away. The dashboard uses this.
- `GET /api/runs/{run_id}/live?after=N`: live events since `N` (who started, tool calls with plain-English results, hand-offs, replies, reports) and the final result once done.
- `POST /api/tickets/{ticket_id}/run`: runs the team and answers only when it's done. This is the same work as `/start`, for scripts and tests.
- `GET /api/tickets/{ticket_id}/agents`: what each agent said, the tools it used with arguments and results, and who it asked for help, for the latest run or a given `run_id`.
- `GET /api/approvals`: payments waiting for the owner (`?status=all` includes past decisions). Each comes with a plain-English `explain`: who gets paid, whether it's a supplier bill (not a customer refund), and the stock situation.
- `POST /api/approvals/{approval_id}/approve`: the owner's approval. It re-checks the invoice, lease or vendor, the amount and the cash, then records the payment, lowers checking, marks the invoice paid or moves the rent to next month, and logs the decision to the audit trail.
- `POST /api/approvals/{approval_id}/reject`: the owner says no. Nothing is paid, and the decision is logged.
- `GET /api/cash`: the current checking balance from `cash_accounts`.
- `POST /api/reset`: copies the original `data/campus_customs.db` over the working database. The audit trail keeps its history.
- `GET /api/health`: shows the server is up and which database it uses.

**Who can call it:** the dashboard page at http://localhost:5173, and any other localhost port in case Vite moves.

## The dashboard

`frontend/` is Ryan Jr.'s Royal Court. The full layout is in `output/design.md`.

**The cast**
- **King Ryan Jr.:** the black-and-white crowned king, playing the Boss.
- **Sir Pawcelot:** a knight, playing Facilities.
- **Squire Biscuit:** a squire, playing Inventory.
- **Lady Ledger:** the treasurer, playing Accounting.
- **Jingles the Jester:** the jester, playing Customer Service.

| Area | What it shows |
|---|---|
| Petitions | The three tickets: open or resolved (with a wax-seal stamp), any bill waiting for approval, and the **Summon the court** button. |
| Throne room | Who's working right now (glow and status chips), hand-offs as gold lines with a moving scroll, and what each agent is doing or saying in speech bubbles. |
| Royal Chronicle | A step-by-step log of every action, tool call, hand-off and report. |
| Royal Decree | The King's decision, his reasons, one line per agent on what it did, and the letter to the customer. |
| My plan vs. what happened | Each expected agent and tool from Problem 6, marked ✓, ✗ or + against the run, plus my expected outcome beside the actual one, and a Success, Waiting on your seal or Not finished verdict. |
| Seal dialog | A prepared payment with who gets paid, a **Supplier bill, not a customer refund** label where it applies, an out-of-stock note, and Approve, Reject or Decide later. |
| Royal Treasury | The checking balance, which counts down when a payment is approved. |

## Approvals and money

1. **Accounting prepares:** a payment proposal comes back in the Boss's `approvals_needed`.
2. **The backend queues it:** it's saved in `approvals` as `pending`, and the same payment is never queued twice. The ticket stays **open**.
3. **The owner decides:** **Approve** writes a `payments` row, lowers `cash_accounts`, and marks the invoice paid or moves the lease's next due date. **Reject** pays nothing.
4. **The ticket resolves:** once nothing is pending and the latest run completed.

**Problem 9 results** (from a fresh reset):
- Start: $3,400.00.
- Ticket 101: supplier bill approved, −$840.00.
- Ticket 102: rent approved, −$2,400.00.
- Ticket 103: no payment.
- End: **$160.00**, which matches `cash_accounts`.

The itemized view is in the **Cash** tab of `output/desk_tickets.html`.

## Safety rules and how they're enforced

| Rule | How it's enforced |
|---|---|
| 1. Protect personal information | `shared_rules.md` forbids sharing customer or shop data. `safety.check_customer_message` rejects customer messages that mention costs, margins, invoices, rent, vendors or the database, or contain emails or long numbers. `send_customer_email` repeats these checks. The audit trail masks emails and long numbers. |
| 2. Never make up facts | All data comes from MCP tools over the database. Agents list each fact with its tool source and put gaps in `unknowns`. The tools say when something isn't recorded, such as past revenue, shipments, discount policy or customer contact details. |
| 3. Time and loop limits | Each request stops after **3 minutes** (`team.py`) or **50 agent-loop steps** shared by the team (`core.py`), with a friendly message. Both were tested with forced small limits. |
| 4. Clean and on topic | `safety.screen_input` catches rude messages, and the team answers "Let's keep it friendly!" without running. Customer messages with inappropriate words are rejected. Customer Service stays on Campus Customs orders. |
| 5. Can't be talked out of its rules | "Ignore your instructions", "admin mode" and similar tricks are flagged, and agents are told to ignore them. Ticket text is treated as information, not instructions. Agents never share the database, customer list or their instructions. |
| 6. Everything is logged | `output/audit_trail.json` only ever adds records: each request's start and end (with why it stopped), every agent-loop step, every hand-off, and every owner approval or rejection. |
| 7. Secrets stay private | `.env` links to the master file. `.gitignore` excludes `.env`, `data/`, the audit trail and `.venv/`. `.env.example` has placeholders only. |
| Money needs a human | No agent can move money. Only the owner's approve click writes to `payments` and `cash_accounts`, after the backend re-checks the bill and the cash. |
| Simulated email, careful stock changes | Emails are logged and never really sent. Stock changes only for a sale, restock, return or recount that really happened, and every change is logged with before and after quantities. |

## Database

`data/campus_customs_new.db` (SQLite). The first nine tables came with the assignment. The last four were added so the agents and dashboard can keep records.

| Table | Rows now | Written by | What it holds |
|---|---|---|---|
| `desk` | 1 | Original data | The shop's current date, 2026-08-31, which every agent uses as "today". |
| `tickets` | 3 | Original data; the backend sets `status` | The requests to work on. |
| `inventory` | 10 | Original data; `update_inventory` | Units on hand by SKU and size, and the aisle. |
| `pricing` | 4 | Original data | Unit cost and list price by SKU. |
| `vendors` | 3 | Original data | Suppliers, their specialty and lead time. |
| `leases` | 1 | Original data; approvals move `next_due` | The shop lease and rent. |
| `cash_accounts` | 1 | Original data; approvals lower `balance` | The checking balance. |
| `invoices` | 1 | Original data; approvals set `status` | Bills we owe. |
| `payments` | 2 | Approve route only | Every payment, with who approved it. |
| `customer_emails` | 2 | `send_customer_email` | Simulated customer emails. |
| `inventory_changes` | 0 | `update_inventory` | A log of every stock change. |
| `agent_runs` | 3 | Backend after each run | Each run's result, agent reports and tool calls. |
| `approvals` | 2 | Backend after each run; the owner's decision | Payments the agents prepared and what the owner decided. |

### Fields and why they matter

### desk

| Field | Why it matters to the agents |
|---|---|
| `date_today` | The shop's current date (2026-08-31), which all agents use instead of the system clock to judge what is due or overdue. |
| `notes` | Shared space for shop-wide context, currently empty. |

### tickets

| Field | Why it matters to the agents |
|---|---|
| `id` | Identifies each ticket so agents can reference the same work when they delegate and report back. |
| `type` | Tells Boss what kind of request this is, which drives who it goes to. |
| `requester` | Tells Customer Service who to address and tells Boss who is asking. |
| `subject` | Gives Boss a quick summary of the request. |
| `sku` | Tells Inventory and Accounting which product to look up. |
| `size` | Combines with `sku` so Inventory checks the exact stock line. |
| `qty` | Tells Inventory how many units are needed, which sets any shortfall. |
| `lease_id` | Points Facilities to the lease behind the ticket. |
| `invoice_id` | Points Accounting to the invoice behind the ticket. |
| `status` | Shows whether a ticket is still open, so agents know what needs work. |
| `notes` | Holds the requester's actual ask in plain words, which structured fields can miss. |
| `created_at` | Shows when the ticket arrived so Boss can see the order and age of the work. |

### inventory

| Field | Why it matters to the agents |
|---|---|
| `sku` | Product ID that links stock to tickets and pricing. |
| `name` | Readable product name for Customer Service messages and agent reports. |
| `size` | Stock is held per size, so a product can be in stock in one size and out in another. |
| `qty` | Units on hand, which Inventory compares to ticket demand to find a shortfall. |
| `location` | Tells staff which aisle to pick from once an order is approved. |

### pricing

| Field | Why it matters to the agents |
|---|---|
| `sku` | Links cost and price to the product on the ticket. |
| `unit_cost` | Lets Accounting calculate margin and estimate restock cost. |
| `list_price` | The starting point for quotes, and for judging how much discount the margin can absorb. |

### vendors

| Field | Why it matters to the agents |
|---|---|
| `id` | Links a vendor to its invoices. |
| `name` | Tells Inventory and Accounting who to order from and pay. |
| `specialty` | The only clue to what a vendor supplies, so Inventory uses it to match products to vendors. |
| `lead_days` | Tells Inventory and Customer Service how long a restock takes, which sets realistic promise dates. |

### leases

| Field | Why it matters to the agents |
|---|---|
| `id` | Links a lease to rent tickets. |
| `space_name` | Tells Facilities which space the rent covers. |
| `landlord` | Lets Facilities confirm that a rent notice came from the real landlord. |
| `monthly_rent` | The amount Facilities passes to Accounting and checks against any notice. |
| `next_due` | The deadline Facilities and Accounting must plan the rent payment around. |
| `notes` | Holds any special lease terms, currently empty. |

### cash_accounts

| Field | Why it matters to the agents |
|---|---|
| `name` | Identifies the account a payment would come from. |
| `balance` | The cash available, which limits what Accounting can propose paying. |
| `date` | Shows how current the balance is. |

### invoices

| Field | Why it matters to the agents |
|---|---|
| `id` | Lets tickets and payments point to a specific bill. |
| `vendor_id` | Links the bill to the vendor being paid. |
| `amount` | The amount Accounting must plan cash for. |
| `due_date` | Lets Accounting spot overdue bills and rank what to pay first. |
| `status` | Shows whether the bill is still unpaid, which helps prevent double payment. |
| `description` | Explains what the bill is for, which is the only link from an invoice to a product. |

### payments

| Field | Why it matters to the agents |
|---|---|
| `id` | Identifies each payment in the record, which is empty today. |
| `kind` | Says what type of item was paid, which tells agents how to read `ref_id`. |
| `ref_id` | Points to the item that was paid, so agents can check whether it was already settled. |
| `amount` | Records how much left the account so Accounting can reconcile cash. |
| `account` | Records which cash account paid. |
| `paid_at` | Records when the money moved, for the audit trail. |
| `approved_by` | Records who approved the payment, which is proof of human sign-off. |

### customer_emails (added for the agents · written by `send_customer_email`)

| Field | Why it matters to the agents |
|---|---|
| `id` | Identifies each logged email. |
| `ticket_id` | Ties the email to the customer's ticket, so agents can see who was told what. |
| `to_name` | The customer's name from the ticket. There's no email address in the database, so none is stored. |
| `subject` | The email's subject line. |
| `body` | The exact words the customer would get, already checked for private shop data. |
| `order_status` | The status the email gives: `shipping`, `ready_for_pickup`, `backordered`, `awaiting_approval` or `update`. |
| `delivery` | Always "SIMULATED", proof that nothing was really sent. |
| `shop_date` | The shop date when it was logged. |
| `logged_at` | The real time it was logged. |

### inventory_changes (added for the agents · written by `update_inventory`)

| Field | Why it matters to the agents |
|---|---|
| `id` | Identifies each stock change. |
| `sku` | The product that changed. |
| `size` | The size that changed. |
| `change` | Units added (positive) or removed (negative). |
| `qty_before` | Stock before the change, so every change can be checked. |
| `qty_after` | Stock after the change. |
| `reason` | `sale`, `restock_received`, `return` or `count_correction`, which explains why stock moved. |
| `ticket_id` | The ticket a sale belongs to, which stops the same order from being counted twice. |
| `note` | Free text explaining the change. |
| `shop_date` | The shop date when it changed. |
| `logged_at` | The real time it changed. |

### agent_runs (added for the dashboard · written by the backend)

| Field | Why it matters |
|---|---|
| `run_id` | Identifies one team run. It matches the audit trail. |
| `ticket_id` | The ticket the run worked on. |
| `stop_reason` / `stop_detail` | How the run ended: `completed`, `timeout`, `loop_limit`, `blocked_by_guardrail` or `error`. |
| `message` | The plain answer shown to the owner. |
| `decision` | The Boss's full decision as JSON. |
| `agents_used` | Which agents took part. |
| `agent_reports` | What each agent handed back, in full. |
| `tool_calls` | Every tool call, with its agent, arguments and result summary. |
| `loop_steps` / `seconds` | How much of the step and time limits the run used. |
| `created_at` | When the run finished. |

### approvals (added for the dashboard · written by the backend)

| Field | Why it matters |
|---|---|
| `id` | Identifies the approval the owner clicks. |
| `run_id` / `ticket_id` | The run and ticket that prepared it. |
| `kind` / `ref_id` | What's being paid: `invoice` with the invoice ID, `rent` with the lease ID, or `purchase_order` with the vendor ID. |
| `payee` / `amount` | Who gets paid and how much. |
| `reference` / `reason` | Accounting's description and reasoning. |
| `status` | `pending`, `approved` or `rejected`. |
| `decided_by` / `decided_at` | Proof of the owner's sign-off. |
| `payment_id` | The `payments` row created when it was approved. |
| `created_at` | When it was prepared. |

## The three tickets

| Ticket | Request | Linked records | Problem 9 outcome |
|---|---|---|---|
| 101 | Tauhid Zaman: 1 Classic Bulldog Tee, size S | `inventory` and `pricing` by SKU and size. Invoice 501 to Bulldog Print Co. | **Resolved.** Out of stock, and no sale recorded, so Tauhid got a status update (simulated). The owner approved the **$840 supplier bill** for the tee reprint. It was not a refund. |
| 102 | Elm City Properties: rent due | Lease 1 | **Resolved.** The notice matched the lease, and the owner approved **$2,400 rent**. The lease's next due date is now 2026-10-02. |
| 103 | Yale AI Club: 20 navy hoodies, size M, bulk discount | `inventory` and `pricing` by SKU and size | **Resolved, with the sale on hold.** Only 8 of 20 in stock and no discount policy, so no discount, no sale and no payment. The club was asked for its timing and discount details. |

The full detail is in `output/resolved_tickets.json`. The comparison with my Problem 6 plan is in `output/desk_tickets.html`, and board screenshots are in `output/resolved_board.html`.

## Audit trail

`output/audit_trail.json` is a JSON list. New records are only ever added to the end, and the reset route never touches it.

| `event` | Written when | Key fields |
|---|---|---|
| `run_start` | A request begins | `run_id`, `ticket_id`, `request`, `input_flags` (rude or injection), `model`, `limits` |
| `agent_step` | Every agent-loop step | `agent`, `chain` (for example `boss > accounting`), `loop_step`, `phase` (`model_request`, `model_response` or `final_output`), `tool_calls`, `tool_results`, `tokens` |
| `delegation` / `delegation_failed` | One agent hands work to another | `from_agent`, `to_agent`, `task` |
| `run_end` | A request ends | `stop_reason`, `stop_detail`, `loop_steps`, `seconds`, `agents_used`, `tools_used`, `approvals_needed`, `reply` |
| `owner_decision` | The owner approves or rejects a payment | `decision`, `approval_id`, `kind`, `payee`, `amount`, `payment_id`, `checking_balance_after` |

**Problem 9 records:**
- Records 826 to 930 are the three real runs (`11ad14f3fa2e`, `3580869f39da` and `1c44dd316554`).
- The two `owner_decision` records after them were copied from the `approvals` table. Before Problem 9, approve clicks were saved in the database but not in the audit trail. They're now logged automatically.
- Earlier records are kept from development and practice runs.

## Output files

| File | What it is |
|---|---|
| `output/harness.md` | This reference. |
| `output/desk_tickets.html` | Ticket plan deck: my expectations compared with what actually happened for each ticket, plus the Cash tab. |
| `output/resolved_tickets.json` | Per ticket: final status, outcome, each agent's contribution, and whether human approval was needed. |
| `output/resolved_board.html` | Screenshots of the React board for each resolved ticket. The images are also in `output/board_screens/`. |
| `output/audit_trail.json` | The append-only log of every run and owner decision. |
| `output/mcp_smoke.json` | Tests of all 9 MCP tools against the database (72 of 72 checks). |
| `output/api_smoke.json` | Tests of the backend routes. |
| `output/design.md` | Dashboard layout and design reasoning. |

## Known limits and gaps

- **Missing data:** the database has **no sales table, shipments or tracking table, discount policy, vendor price list or customer contact details**. Agents say so instead of guessing, which is why ticket 103 couldn't get a discount decision.
- **No real email:** customer emails are **simulated**. They're logged in `customer_emails` and never sent.
- **"Resolved" only counts payments:** it means the run completed and no payment is waiting. It doesn't mean the customer got what they asked for. Ticket 103 is resolved, but the sale is on hold.
- **Same answers on repeat:** Portkey can return cached answers for a repeated request, so re-running a ticket may finish in seconds with the same result.
- **Unenforced links:** the database only enforces three links (`tickets.lease_id`, `tickets.invoice_id`, `invoices.vendor_id`). Matches by SKU, size, account and payment reference depend on the tools and agents matching values correctly.

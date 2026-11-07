# Agent Dashboard Design: Ryan Jr.'s Royal Court

**Problem 8** · React + Vite + TypeScript in `frontend/`, talking to the FastAPI backend from Problem 7.

## Why this design

I wanted a dashboard that's fun to watch but never confusing.

- **The theme makes the agents easy to tell apart.** Each agent is a cat with its own costume and a job title that matches its role, so I always know who's talking.
  - My cat **Ryan Jr.** is the black-and-white **King**, the Boss agent.
  - His court sits below him in a medieval castle.
- **Everything is readable.** Under the costumes, every label is plain English:
  - Tool calls say what they did, for example "counts the storeroom" for `check_inventory`.
  - Tool results are one-line summaries, not raw data.
  - Money is shown in dollars.

## The cast

| Agent | Character | Costume | What they do |
|---|---|---|---|
| Boss | **King Ryan Jr.** | Black and white, gold crown, red cape with ermine collar, scepter | Reads the petition, sends the court to work, issues the final decree |
| Facilities | **Sir Pawcelot**, Knight of the Keep | Grey tabby, knight's helmet with red plume, blue shield | Lease, rent and the landlord |
| Inventory | **Squire Biscuit**, Keeper of the Storeroom | Orange tabby, green squire's cap with a feather, SKU crate | Stock by SKU and size, restock vendor |
| Accounting | **Lady Ledger**, Royal Treasurer | Calico, purple scholar's beret, spectacles, coin purse, quill | Treasury, invoices, margins, payment proposals |
| Customer Service | **Jingles the Jester**, Herald of Good Cheer | Siamese, jester's hat with bells, ruff collar | Kind, fact-checked letters to customers |

## Layout

```
┌────────────────────────────────────────────────────────────────────────────────────┐
│ 👑 Ryan Jr.'s Royal Court      [💰 Royal Treasury · Checking $3,400.00]  [New day] │
├──────────────┬──────────────────────────────────────────────────┬──────────────────┤
│ PETITIONS    │ Now: Petition #102 · Sir Pawcelot is working…    │ ROYAL CHRONICLE  │
│ #101 Bulldog │ ┌──────────────── THRONE ROOM ────────────────┐  │ 🐱 King → Knight │
│ #102 Rent  ◀ │ │              👑 King Ryan Jr.  💬            │  │ 🐱 🗂️ get_docs.. │
│  [Summon the │ │        ╱      │       │        ╲             │  │ 🐱 → lease 1 ... │
│   court]     │ │  Knight   Squire   Treasurer   Jester        │  │ 🐱 reports back  │
│ #103 Hoodies │ │   💬        💬        💬          💬         │  │ …                │
│              │ └──────────────────────────────────────────────┘  │                  │
│              │ ROYAL DECREE: decision · why · what the court  │                  │
│              │ did · letter · MY PLAN VS. WHAT HAPPENED          │                  │
└──────────────┴──────────────────────────────────────────────────┴──────────────────┘
                 🔏 Seal dialog pops up when a payment needs approval
```

**1. Top bar**
- The King's portrait, the title, and the shop date.
- **Royal Treasury:** the live checking balance from `GET /api/cash`. When I approve a payment, it counts down and shows a red "−$2,400.00" tag.
- **New day (reset):** asks first, then calls `POST /api/reset` for a fresh run.

**2. Petitions (left):** the three tickets from `GET /api/tickets`.
- Each card shows the number, type, requester and the customer's note.
- Its status is **Open**, **Court at work…** or **Resolved**, and resolved tickets get a green wax-seal stamp.
- A **Needs your seal** tag appears when a payment is waiting.
- Clicking a card selects it, and **👑 Summon the court** starts the team.

**3. Now bar (top of the center):** one sentence saying who's working right now, for example "Lady Ledger is working · Squire Biscuit asks Lady Ledger…".

**4. Throne room (center):** the King on his throne with the four court members below.
- **Status chips:** each cat shows **Resting**, **Working** (glowing halo and bobbing), **Waiting on help** (it asked someone and is waiting) or **Reported** (done).
- **Speech bubbles:** each cat's latest action or words, such as "📦 counts the storeroom (sku=CC-HOOD-NAVY, size=M, qty_needed=20)", "→ Basic Hoodie Big Yale M: 8 on hand in Aisle A, short 12", a request to another agent, or its final report.
- **Hand-off lines:**
  - Dotted lines show the chain of command.
  - When one agent hands work to another, the line turns gold and stays drawn. Court-to-court hand-offs arc over the row, and repeated hand-offs show a count like "×2".
  - The current hand-off turns purple, and a 📜 scroll travels along it.

**5. Royal Chronicle (right, or below on smaller screens):** the step-by-step log.
- **Each entry:** the agent's portrait and name, then what they did (tool icon and name, a hand-off "📯 → Sir Pawcelot", a reply "↩ King Ryan Jr.", or a report), plus the time and loop step.
- **Colors:** hand-offs are purple, reports green, and the final decree gold.
- **Scrolling:** the list keeps the newest entry in view.

**6. Royal Decree (below the throne room, after a run):** the clean summary.
- The King's decision, a **Success**, **Done, waiting on your seal** or **Not finished** badge, and the steps and seconds used.
- **Why:** the King's top reasons, each tied to a fact.
- **What the court did:** one line per agent with its tool icons, who it asked for help, and what it reported.
- **Letter to the customer:** the Jester's message.
- **Not in the records:** what the database didn't know.

**7. My plan vs. what happened:** the comparison with my Problem 6 expectations from `output/desk_tickets.html`.
- **Agents:** ✓ green for each agent I expected that took part, ✗ red for one I expected that didn't, and + purple for extra agents.
- **Tools:** the same ✓, ✗ and + chips, using the tool names.
- **Outcome:** my expected outcome next to the King's actual decision.
- **Score line:** "X of Y planned agents and X of Y planned tools showed up".

**8. Seal dialog:** pops up when the run prepared a payment.
- **Header:** Lady Ledger asks for the King's seal and shows the amount, payee, what it's for, why, the treasury now, and the treasury after paying.
- **Approve and pay:** calls `POST /api/approvals/{id}/approve`. The treasury counts down and the ticket turns Resolved.
- **Reject:** calls `.../reject`, and nothing is paid.
- **Decide later:** closes the dialog and leaves a "🔏 payment waiting for your seal" button on the board.

## How it works

1. **Load:** the board calls `GET /api/tickets`, `GET /api/cash` and `GET /api/approvals`.
2. **Summon:** `POST /api/tickets/{id}/start` starts the agent team in the background and returns a `run_id` right away.
3. **Watch:** every 0.7 seconds the board calls `GET /api/runs/{run_id}/live?after=N` and adds the new events.
   - **Where events come from:** the backend's agent loop records every step as it happens. That includes each agent starting, thinking, every tool call and its plain-English result, every hand-off and reply, every refused hand-off, and each final report.
   - **What the board does with them:** each event updates the bubbles, status chips, hand-off lines, now bar and chronicle.
4. **Finish:** when the run is done, the board reloads tickets, cash and approvals, then reads `GET /api/tickets/{id}/agents` for the decree and the plan comparison.
5. **Approve:** if a payment is pending, the seal dialog opens.
   - **Agents only prepare:** they never move money.
   - **Approving:** pays, lowers checking, and resolves the ticket once nothing else is waiting.
6. **Replay:** selecting a ticket that already ran, even after a page reload, rebuilds its throne room, chronicle and decree from the saved run, marked "Replayed from the last saved run".
7. **Reset:** "New day" restores the original database: $3,400 in checking and all tickets open.

## How success and my plan are judged

- **Success:** the run stopped with `completed`, and nothing is waiting on me.
  - **Done, waiting on your seal:** completed, but a payment needs my approval.
  - **Not finished:** the run hit the 3-minute limit, the 50-step limit (20 until Problem 9), a guardrail, or an error.
- **Resolved:** the backend marks a ticket resolved when its latest run completed and no payment approvals are pending.
- **Plan comparison:**
  - **Agents and tools:** compared exactly, using the agents and tool calls the run actually made.
  - **Outcome:** shown side by side for me to judge, because whether the result matches my intent is a judgment call. For example, I expected ticket 101 to be "shipped", but the records show no sale.

## Running it

```bash
# Terminal 1: backend (from Homework 5/backend)
../.venv/bin/uvicorn main:app --reload --port 8000

# Terminal 2: board (from Homework 5/frontend)
npm run dev        # opens http://localhost:5173 in the browser
```

- **Where the board looks:** it calls the backend at `http://localhost:8000`. To change that, set `VITE_API_URL` in `frontend/.env.local`.
- **Who can call the backend:** it allows the Vite page at `http://localhost:5173`, plus any other localhost port in case Vite moves.

## Tested

- **What ran:** a test backend on a scratch copy of the original data, so my working database stayed unchanged, with the built board in the browser.
- **Ticket 102:** the seal popped up for $2,400 rent. Approving dropped the treasury from $3,400 to $1,000, and the ticket got the RESOLVED stamp. The plan comparison showed all 3 planned agents and the 1 planned tool.
- **Ticket 103:** I watched it live. The Working halo moved between agents, purple scroll hand-offs appeared (Jingles asking Lady Ledger, for example), and the chronicle filled step by step.
- **Ticket 101:** the seal popped up for the $840 invoice. Approving dropped the treasury from $1,000 to $160. All 4 planned agents and both planned tools showed up.
- **Reload:** replaying past runs worked.
- **Fixes made while testing:**
  - Raw JSON in the bubbles was replaced with one-line summaries from the backend.
  - The hand-off lines were moved so they don't hide behind the nameplates.
  - The chronicle now scrolls inside its own panel.
  - The now bar now names the right agent after a reply.

## Known limits

- **Very fast runs:** Portkey sometimes returns cached answers for a repeated ticket, so a run can finish in a few seconds and the live animation is brief.
- **"Resolved" only counts payments:** on ticket 103 the King left the bulk discount for me to decide, but the ticket still shows Resolved because no payment was pending.
- **Text only:** the board shows what the agents said in text. Customer emails are simulated and never really sent.

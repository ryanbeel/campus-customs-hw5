# Campus Customs MCP Server

## What it does

This server gives every Campus Customs agent (Boss, Inventory, Accounting, Facilities and Customer Service) the same set of tools for reading the shop's data. Agents call the tools instead of querying the database directly, so they all see the same facts.

Five tools only read data and open the database in read-only mode. Two tools, added in Problem 6, can change things, and both log every action in their own table:

- **`send_customer_email`:** simulated. It saves the email and never really sends it.
- **`update_inventory`:** changes stock.

No tool can pay money or change tickets.

All values come from the database. Anything the tools work out from those values is marked `(calculated)`, such as a shortfall, a margin or a number of days overdue. When data is missing, a tool says so instead of filling the gap.

## Database

`data/campus_customs_new.db` is the working copy of the shop database. `data/campus_customs.db` is the untouched original and the server never opens it.

The tools treat `desk.date_today` (2026-08-31) as today, not the computer's clock, so due dates match the shop's timeline.

## Tools

### 1. `check_inventory`

Looks up stock by SKU and size.

- **Inputs, all optional:** `sku`, `size`, `qty_needed` and `out_of_stock_only`.
- **Returns:** units on hand, aisle, list price and a status for each stock line. With `qty_needed` the status is `enough` or `short`, plus the shortfall. Without it the status is `in_stock` or `out_of_stock`.
- **Also returns:**
  - Totals per product, with the sizes in and out of stock, so agents can suggest another size.
  - Unit cost and margin in an `internal` block, which agents must never share with customers.
- **Missing lines:** if a SKU and size combination doesn't exist, it lists the sizes that do instead of guessing.

### 2. `find_vendors`

Finds who to restock from, using the database's vendor list first.

- **Inputs, all optional:** `sku`, `size`, `qty_needed` and `keyword`.
- **How vendors are ranked:**
  - A vendor on a past invoice that names the SKU ranks first.
  - A vendor whose specialty fits the product comes next, and is marked "inferred". For example, a hoodie fits "apparel reprint".
  - Ties go to the shortest lead time.
- **With a size and `qty_needed`:** it also returns units to order, an estimated cost from our `unit_cost`, and the arrival date if ordered today.
- **Every vendor match:** includes open invoices with that vendor, so Accounting sees what we already owe before a new order.
- **No arguments:** it lists all vendors and every out-of-stock line with its matched vendor.
- **No vendor on file:** it returns `web_search_needed: true` and a suggested search phrase. The server doesn't search the web itself. The agent runs the search and must label those results as coming from the web.

### 3. `get_tickets`

Reads tickets and the records they point to.

- **Inputs, all optional:**
  - `status`: `open` (the default), `resolved` (anything not open) or `all`.
  - `ticket_id` and `ticket_type` to narrow the results.
- **Returns each ticket with:**
  - Its linked lease, with days until due.
  - Its linked invoice, with the vendor and days overdue.
  - Any payments already recorded against that invoice or lease.
- **Past resolutions:** `prior_resolutions` lists earlier tickets of the same type that are no longer open, so agents can follow how the shop handled them before. No ticket has been resolved yet, so it currently says so.
- **Payment matching:** it matches payments using `payments.kind = 'invoice'` with the invoice ID, or `'lease'` or `'rent'` with the lease ID. Later problems that record payments should use these `kind` values.

### 4. `get_documents` (added in Problem 5)

Reads the shop's invoices, leases, payments and cash accounts, mainly for Accounting and Facilities.

- **Inputs, all optional:**
  - `doc_type`: `invoices`, `leases`, `payments`, `cash` or `all` (the default).
  - `doc_id` for one record, and `status` to filter invoices, for example `open`.
- **Returns:**
  - Each invoice with its vendor name and days overdue or until due.
  - Each lease with days until rent is due.
  - Every recorded payment, so agents can check whether something is already paid.
  - Every cash account balance.
- **Missing records:** an unknown ID returns `found: false` instead of guessing.

### 5. `get_financials` (added in Problem 5)

Basic accounting formulas applied to the shop's own prices, costs, stock and cash.

- **Inputs, all optional:** `sku`, `qty` and `discount_pct` (0-100).
- **Always returns:**
  - The formulas it uses: margin, margin %, markup %, discounted price, revenue, cost of goods sold, gross profit, the largest discount before a loss, restock cost, and cash after obligations.
  - Cash position: balance, open invoices, next rent, and cash left after both.
- **With no SKU:** margin, markup and stock value at cost and at list price for every product.
- **With a SKU and quantity:** prices that order, showing revenue, discount given, cost of goods, gross profit, margin, and the largest discount before a loss. Add `discount_pct` to see a discount's effect.
- **Revenue history:** the database has no sales table, so past revenue is reported as missing, not estimated.

### 6. `send_customer_email` (added in Problem 6)

Emails a customer about their order. **This is simulated for the homework: nothing is ever really sent.** Each email is saved in a new `customer_emails` table and marked `SIMULATED`.

- **Inputs:** `ticket_id`, `subject`, `body` and `order_status`. The status is one of:
  - `shipping` or `ready_for_pickup`: we have the item and are sending it or holding it.
  - `backordered`: out of stock or short.
  - `awaiting_approval`: waiting on a decision, such as a discount.
  - `update`: anything else.
- **Refuses to send when:**
  - The ticket isn't from a customer. Ticket 102 is from the landlord.
  - The body mentions private shop information, such as costs, margins, invoices, rent, vendors or the database, or contains an email address or long number.
  - The status is `shipping` or `ready_for_pickup` but stock on hand plus units already sold for the ticket don't cover its quantity, so an email can't promise an item we don't have.
- **Duplicates:** the same email for the same ticket is never logged twice.
- **Recipient:** the customer's name from the ticket. The database has no customer email addresses, so none is invented.
- **Visibility:** `get_tickets` now shows each ticket's `emails_sent`.

### 7. `update_inventory` (added in Problem 6)

Changes the units on hand for one SKU and size, for example lowering stock when a sale happens. Every change is logged in a new `inventory_changes` table with the quantity before and after, the reason, the ticket and the time.

- **Inputs:** `sku`, `size`, `change` (negative removes stock), `reason`, and optional `ticket_id` and `note`.
- **Reasons:**
  - `sale`: change must be negative.
  - `restock_received` or `return`: change must be positive.
  - `count_correction`: either direction.
- **Refuses when:**
  - Stock would go below zero.
  - The change is 0 or more than 1,000 units.
  - A sale names a ticket for a different SKU or size.
  - A sale would take more units than the ticket ordered in total. This stops the same sale from being counted twice.

### 8. `check_order_status` (added in Problem 6)

Confirms whether a customer's sale really happened and what we've told them about shipping. It's for tickets where customers ask "did my order go through?" or "has it shipped?".

- **Inputs, all optional:** `ticket_id`, or `sku` and `size`.
- **With a ticket:**
  - Units ordered against units sold for that ticket, and any returns.
  - `transaction_status`: `completed`, `partial` or `no_sale_recorded`, plus `transaction_confirmed`, which is true only when completed.
  - Every email sent to the customer, and `shipment_status`: `customer_told_shipping`, `customer_told_ready_for_pickup` or `no_shipment_record`.
- **With a SKU:** every recorded sale and return of that product, with totals.
- **Honest about missing data:**
  - The database has no sales table and no shipments or tracking table. Sales come from the `inventory_changes` log, which is written only when `update_inventory` records a sale, so earlier sales can't be shown.
  - Shipping status comes from the `customer_emails` log. `shipment_confirmed` therefore always stays false, and the tool says why. Agents may say an order is "on its way" only after a shipping email, and never invent tracking numbers or delivery dates.
- **Non-customer tickets:** a ticket like 102 gets a note that it has no sale or shipment.

### 9. `get_checking_account` (added in Problem 7)

Returns the checking account's balance and activity, so agents can tell the owner the ending balance.

- **Input, optional:** `account` (default `checking`).
- **Returns:**
  - `ending_balance` and the date it's as of, from `cash_accounts`.
  - `activity`: every payment out of the account from `payments`, with kind, payee (looked up from the invoice, lease or vendor), amount, date, who approved it, and the running balance after each one.
  - The opening balance before those payments and the total paid out, so the activity always adds up to the ending balance.
  - `pending_approvals`: payments the agents prepared that are still waiting for the owner, with their total and the balance if they're all approved.
- **Limits:**
  - The database records no deposits or sales cash, so only money going out appears, and the tool says so.
  - An unknown account, such as `savings`, returns `found: false` with the accounts that do exist.
- **Read-only:** the balance only changes when the owner approves a payment through the backend.

### Testing hook

Set `CAMPUS_DB_PATH` to point the server at a scratch copy of the database. The Problem 6 smoke tests use this so they never change real stock.

## Which agents use which tools

| Agent | MCP tools |
|---|---|
| Boss | `get_tickets`, `get_checking_account` |
| Inventory | `check_inventory`, `find_vendors`, `get_tickets`, `update_inventory` |
| Accounting | `get_documents`, `get_financials`, `find_vendors`, `get_tickets`, `check_order_status`, `get_checking_account` |
| Facilities | `get_documents`, `get_tickets` |
| Customer service | `check_inventory`, `get_tickets`, `send_customer_email`, `check_order_status` |

Every agent also has `delegate`, which isn't an MCP tool. It lets any agent hand work to any other agent, so they can always reach the tools they don't hold themselves.

## Tool usage log

Each time a tool helps with a ticket, add one sentence saying which ticket it helped, how the tool was used, and why it was needed. Newest entries go at the bottom.

**Problem 3: test runs while building the server**

- `check_inventory` helped ticket 101 when called with `CC-TEE-WHITE`, size `S` and quantity 1. It was needed to show that size S has 0 units while M, L and XL are in stock, so Customer Service can offer Tauhid Zaman another size.
- `check_inventory` helped ticket 103 when called with `CC-HOOD-NAVY`, size `M` and quantity 20. It was needed to show only 8 are on hand, a shortfall of 12, and the $36 per unit margin that limits any bulk discount.
- `find_vendors` helped ticket 101 when called with `CC-TEE-WHITE`, size `S` and quantity 1. It was needed because it found invoice 501, a rush reprint of this exact tee from Bulldog Print Co, so agents check that order before placing another.
- `find_vendors` helped ticket 103 when called with `CC-HOOD-NAVY`, size `M` and quantity 20. It was needed to name Bulldog Print Co and work out 12 units to order, about $264, arriving 2026-09-05, while flagging the $840 we already owe them.
- `get_tickets` helped tickets 101, 102 and 103 when called with no arguments to list open tickets. It was needed to bring in each ticket's linked invoice or lease and show that no past tickets of the same type have been resolved yet.
- `get_tickets` helped ticket 102 when called with ticket ID 102. It was needed because it's the only tool that reads leases, confirming Elm City Properties is the landlord and the $2,400 rent is due 2026-09-02.

**Problem 4: smoke test through Claude Code over MCP** (full results in `output/mcp_smoke.json`)

- `get_tickets` helped tickets 101, 102 and 103 when Claude Code called it through MCP with no arguments. It was needed so the Boss agent can see all three open tickets with invoice 501 ($840, 3 days overdue) and lease 1 ($2,400, due in 2 days) attached, and all 6 checks matched the database.
- `check_inventory` helped ticket 103 when Claude Code called it with `CC-HOOD-NAVY`, size `M` and quantity 20. It was needed to confirm 8 on hand in Aisle A, a shortfall of 12 and a $36 margin at the $58 list price, and all 4 checks matched the database.
- `find_vendors` helped ticket 101 when Claude Code called it with `CC-TEE-WHITE`, size `S` and quantity 1. It was needed to identify Bulldog Print Co from invoice 501, an arrival date of 2026-09-05 and the $840 we already owe them, and all 5 checks matched the database.

**Problem 5: smoke tests of the new tools** (tests 4 and 5 in `output/mcp_smoke.json`)

- `get_documents` helped ticket 102 when called over MCP with `doc_type` `all`. It was needed to show lease 1 ($2,400 to Elm City Properties, due in 2 days), no recorded payments, $3,400 in checking and invoice 501 3 days overdue, and all 6 checks matched the database.
- `get_financials` helped ticket 103 when called with `CC-HOOD-NAVY`, quantity 20 and a 10% discount. It was needed to show $1,044 revenue, $440 cost and $604 gross profit, a 62.1% largest discount before a loss, and $160 cash left after bills, and all 8 checks matched the database.

**Problem 5: the agent team working the tickets** (runs in `output/audit_trail.json`)

- `get_tickets` helped tickets 101, 102 and 103 when the Boss agent called it with each ticket ID. It was needed so the Boss could see each request and its linked invoice or lease before deciding to delegate to inventory, accounting and customer service (101 and 103) or facilities and accounting (102).
- `get_documents` helped ticket 102 when Facilities called it for the lease and payments, and Accounting for cash. It was needed to confirm the notice matched lease 1 ($2,400, due 2026-09-02) and that no rent was already paid before Accounting proposed the payment.
- `get_financials` helped ticket 102 when Accounting called it with no arguments. It was needed to show that paying the rent and invoice 501 would leave $160, which went into the Boss's reasoning.
- `check_inventory` helped tickets 101 and 103 when Inventory and Customer Service called it with each ticket's SKU, size and quantity. It was needed to confirm tee S is at 0 and hoodie M is 12 short, so Customer Service promised neither an item nor a date.
- `find_vendors` helped tickets 101 and 103 when Inventory called it with the SKU, size and quantity. It was needed to name Bulldog Print Co, flag that invoice 501 may already cover the tee reprint, and price the 12-hoodie restock at about $264.
- `get_financials` helped ticket 103 when Accounting called it with the hoodie SKU, quantity 20 and a 5% discount. It was needed to show $1,102 revenue, $662 gross profit and a 60.1% margin, and that the $264 restock would leave cash $104 short after rent and invoice 501.

**Problem 6: smoke tests of the new tools** (tests 6 and 7 in `output/mcp_smoke.json`, run on a scratch copy of the database)

- `send_customer_email` helped ticket 101 when called with `backordered` and a thank-you note saying size S is out. It was needed to tell Tauhid the honest status, and it logged one simulated email while refusing a duplicate and a `shipping` email for a tee we have 0 of.
- `send_customer_email` helped ticket 103 when called with `shipping` after the restock brought hoodie M to 20. It was needed to show the tool only lets an email promise shipping once stock covers all 20. It had refused the same email when only 8 were on hand, and refused a message mentioning our margin.
- `update_inventory` helped ticket 103 when called with +12 `restock_received` and then -20 `sale` for ticket 103. It was needed to move hoodie M from 8 to 20 to 0, with both changes logged. It then refused a 21st unit for the same ticket, a sale with a positive change, a sale that would take tee S below 0, and a cap sale charged to ticket 101.

**Problem 6: the agent team using the new tools** (run `e3fdefdc14e8` in `output/audit_trail.json`)

- `send_customer_email` helped ticket 101 when the Customer Service agent called it with `backordered` and its drafted note to Tauhid. It was needed to tell the customer the tee is out of stock without promising a date, and it saved email 1 in `customer_emails` as simulated, with nothing really sent.
- `update_inventory` was given to the Inventory agent but correctly not called on ticket 101. Nothing was sold and no restock arrived, so stock stayed at 0, which is the rule in its prompt.

**Problem 6, prompt 2: smoke test of `check_order_status`** (test 8 in `output/mcp_smoke.json`, run on a scratch copy)

- `check_order_status` helped ticket 103 when called four times as the order moved along: no sale, then 8 sold, then 20 sold plus a shipping email. It was needed to show `no_sale_recorded`, then `partial` (8 of 20), then `completed` with `customer_told_shipping`, and to keep `shipment_confirmed` false because the database has no tracking table. All checks matched SQL on the copy.
- `check_order_status` helped ticket 101 when called with ticket ID 101. It was needed to show Tauhid's order has no recorded sale or shipment, only the earlier `backordered` email.
- This test also found a bug in `send_customer_email`: once all 20 hoodies were recorded as sold, stock read 0 and the shipping email was refused. The tool now counts units already sold for the ticket plus units on hand, and tests 6, 7 and 8 were rerun and all pass.

**Problem 6, prompt 2: the agent team answering a status question** (run `9be3fcbb0223` in `output/audit_trail.json`)

- `check_order_status` helped ticket 101 when the Customer Service agent called it after Tauhid asked whether his order went through and shipped. It was needed so the answer came from records, not guesses: no completed sale, no shipment, and an earlier backordered update. Customer Service saw that email and didn't send a duplicate.

**Problem 7: agent runs through the backend routes** (`output/api_smoke.json`, scratch copy)

- `get_tickets`, `get_documents` and `get_financials` helped ticket 102 when `POST /api/tickets/102/run` started the team: Boss, then Facilities, then Accounting. They were needed to confirm lease 1's $2,400 rent and that nothing had been paid, so Accounting could prepare a rent proposal (`kind` rent, `ref_id` 1) that waited for the owner's approval.
- `check_inventory`, `find_vendors`, `check_order_status` and `send_customer_email` helped ticket 101 when `POST /api/tickets/101/run` started the team. They were needed to show tee S at 0, no recorded sale, and Bulldog Print Co as the vendor, and to log a simulated update to Tauhid, while Accounting prepared the $840 invoice 501 payment for approval.

**Problem 7, prompt 2: smoke test of `get_checking_account`** (test 9 in `output/mcp_smoke.json`, scratch copy of the original data)

- `get_checking_account` helped ticket 102 when called before and after the owner approved the $2,400 rent through `POST /api/approvals/{id}/approve`. It was needed to show the ending balance stay at $3,400 while the rent was only pending (with $1,000 shown if approved), then drop to $1,000 with one payment to Elm City Properties approved by the owner. All checks matched SQL.
- `get_checking_account` helped ticket 101 when called with invoice 501 waiting for approval. It was needed to show $840 pending and $160 left if it's approved, so the owner sees the real ending balance before approving.

**Problem 7, prompt 2: agents using `get_checking_account` through the backend** (`checking_tool_agent_check` in `output/api_smoke.json`)

- `get_checking_account` helped ticket 101 when the Boss and Accounting agents called it during `POST /api/tickets/101/run`, after the rent was approved. It was needed so the team worked from the real $1,000 ending balance, not the starting $3,400, when weighing the $840 invoice.

## Running it

From the `Homework 5` folder:

```bash
.venv/bin/python mcp_server/server.py
```

It runs over stdio, the standard way for an agent backend to start an MCP server and talk to it.

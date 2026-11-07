"""Shared building blocks for the agent team: model, MCP tools, delegation and the agent loop.

Every agent file (boss.py, inventory.py, ...) builds its agent from these pieces.
"""

import json
import os
import sys
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.messages import RetryPromptPart, TextPart, ToolCallPart, ToolReturnPart, UserPromptPart
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from audit import append_audit, short
from models import AgentName

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROMPTS_DIR = HERE / "prompts"
MCP_SERVER = ROOT / "mcp_server" / "server.py"

PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
DEFAULT_MODEL = "gpt-5.6-luna"

# Safety limits for one request, shared by the whole team. Env vars allow testing with small values.
MAX_RUN_SECONDS = float(os.getenv("AGENT_MAX_RUN_SECONDS", "180"))  # stop after 3 minutes
MAX_LOOP_STEPS = int(os.getenv("AGENT_MAX_STEPS", "50"))  # stop after 50 agent-loop steps (model calls); was 20 until Problem 9
MAX_DELEGATION_DEPTH = 3  # boss -> agent -> agent -> agent

# PORTKEY_API_KEY and OPENAI_MODEL live in .env in the project root (a link to the master .env).
load_dotenv(ROOT / ".env")


class LoopLimitReached(Exception):
    """The team used all of its agent-loop steps for this request."""


@dataclass
class RunState:
    """One request's shared state: every agent in the run updates the same object."""

    run_id: str
    ticket_id: int | None
    agents: dict[str, Agent]
    tool_access: dict[str, tuple[str, ...]]  # agent -> MCP tools it may call
    mcp: MCPToolset | None = None  # this request's MCP connection
    loop_steps: int = 0
    tools_used: list[str] = field(default_factory=list)
    agents_used: list[str] = field(default_factory=list)
    tool_log: list[dict] = field(default_factory=list)  # every tool call: agent, tool, args, result
    reports: list[dict] = field(default_factory=list)  # what each agent handed back, in full
    events: list[dict] = field(default_factory=list)  # live feed for the dashboard, in order
    started: float = field(default_factory=time.monotonic)

    def emit(self, kind: str, **data) -> None:
        """Add one event to the live feed the dashboard polls while the team works."""
        self.events.append({"i": len(self.events), "type": kind,
                            "t": round(time.monotonic() - self.started, 2), "loop_step": self.loop_steps, **data})


def _money(x) -> str:
    return f"${x:,.2f}" if isinstance(x, (int, float)) else "?"


def summarize(tool: str, content) -> str:
    """One plain-English line for a tool result, for the dashboard's bubbles and chronicle."""
    data = content
    if isinstance(content, str):
        try:
            data = json.loads(content)
        except ValueError:
            return short(content, 200)
    if not isinstance(data, dict):
        return short(data, 200)
    if data.get("found") is False or data.get("sent") is False and not data.get("simulated") \
            or data.get("updated") is False:
        return short(data.get("message") or "nothing found", 200)
    try:
        if tool == "get_tickets":
            return "; ".join(f"#{t['id']} {t['subject']} from {t['requester']} ({t['status']})" for t in data["tickets"])
        if tool == "check_inventory":
            return "; ".join(
                f"{l['name']} {l['size']}: {l['qty']} on hand in {l['location']}"
                + (f", short {l['shortfall (calculated)']}" if l.get("shortfall (calculated)") else "")
                for l in data["lines"])
        if tool == "find_vendors":
            if data.get("web_search_needed"):
                return f"no vendor on file; web search needed: {data.get('suggested_search')}"
            if "recommended" in data:
                r = data.get("restock") or {}
                v = data["vendors"][0]
                extra = (f"; order {r.get('units_to_order (calculated)')} for about "
                         f"{_money(r.get('estimated_cost (calculated)'))}") if r else ""
                return f"{data['recommended']} ({v['lead_days']}-day lead, arrives {v.get('expected_arrival_if_ordered_today (calculated)')}){extra}"
            return f"{len(data.get('vendors', []))} vendors on file"
        if tool == "get_documents":
            bits = []
            for inv in data.get("invoices", []):
                bits.append(f"invoice {inv['id']} {_money(inv['amount'])} to {inv['vendor_name']} ({inv['status']}"
                            + (f", {inv['days_overdue (calculated)']} days overdue" if inv.get("days_overdue (calculated)") else "") + ")")
            for l in data.get("leases", []):
                bits.append(f"lease {l['id']} rent {_money(l['monthly_rent'])} due {l['next_due']}")
            if "payments" in data:
                bits.append(f"{len(data['payments'])} payment(s) recorded")
            for c in data.get("cash_accounts", []):
                bits.append(f"{c['name']} {_money(c['balance'])}")
            return "; ".join(bits) or "no documents"
        if tool == "get_financials":
            cp = data["cash_position"]
            line = f"cash {_money(cp['total_cash (calculated)'])}, after bills {_money(cp['cash_after_obligations (calculated)'])}"
            if "order" in data:
                o = data["order"]
                line += (f"; {o['qty']} at {_money(o['price_per_unit (calculated)'])} = {_money(o['revenue (calculated)'])}, "
                         f"profit {_money(o['gross_profit (calculated)'])} ({o['gross_margin_pct (calculated)']}%)")
            return line
        if tool == "send_customer_email":
            return f"email to {data['to']} saved as '{data['order_status']}' (simulated, not really sent)"
        if tool == "update_inventory":
            return f"{data['sku']} {data['size']}: {data['qty_before']} → {data['qty_after']} ({data['reason']})"
        if tool == "check_order_status":
            if "transaction_status" in data:
                return (f"ticket {data['ticket_id']}: {data['units_sold_recorded']} of {data['units_ordered']} sold "
                        f"({data['transaction_status']}), shipping: {data['shipment_status']}")
            return short(data.get("message") or f"{data.get('units_sold_recorded', 0)} units sold recorded", 200)
        if tool == "get_checking_account":
            return (f"ending balance {_money(data['ending_balance'])}, {len(data['activity'])} payment(s) out, "
                    f"{_money(data['pending_total (calculated)'])} pending → {_money(data['balance_if_all_pending_approved (calculated)'])}")
    except (KeyError, IndexError, TypeError):
        pass
    return short(data, 200)


def said(output: dict) -> str | None:
    """The one line an agent 'says' when it reports back."""
    if output.get("agent") == "customer_service" and output.get("customer_message"):
        return output["customer_message"]
    return output.get("summary") or output.get("decision")


@dataclass
class TeamDeps:
    state: RunState
    chain: tuple[str, ...]  # agents currently working, outermost first, e.g. ("boss", "inventory")


def model_name() -> str:
    return os.getenv("OPENAI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


@lru_cache(maxsize=1)
def build_model() -> OpenAIChatModel:
    key = os.getenv("PORTKEY_API_KEY", "").strip()
    if not key:
        raise RuntimeError("PORTKEY_API_KEY is missing. Link the master .env into the Homework 5 folder.")
    provider = OpenAIProvider(api_key=key, base_url=PORTKEY_BASE_URL)
    return OpenAIChatModel(model_name(), provider=provider)


def load_prompt(agent: str) -> str:
    """The shared rules plus this agent's own prompt file."""
    shared = (PROMPTS_DIR / "shared_rules.md").read_text(encoding="utf-8")
    own = (PROMPTS_DIR / f"{agent}.md").read_text(encoding="utf-8")
    return f"{own}\n\n{shared}"


def new_mcp_toolset() -> MCPToolset:
    """A fresh connection to mcp_server/server.py for one request, shared by every agent in it."""
    # Pass CAMPUS_DB_PATH through so the tools read the same database as the routes (tests use a scratch copy).
    env = {k: os.environ[k] for k in ("PATH", "HOME", "CAMPUS_DB_PATH") if k in os.environ}
    transport = StdioTransport(command=sys.executable, args=[str(MCP_SERVER)], env=env)
    return MCPToolset(Client(transport))


async def delegate(ctx: RunContext[TeamDeps], agent: AgentName, task: str) -> dict | str:
    """Hand a task to another agent on the team and get its report back.

    Args:
        agent: Who should do it: boss, inventory, accounting, facilities or customer_service.
        task: What you need, with the ticket number and any facts they should use.
    """
    chain = ctx.deps.chain
    state = ctx.deps.state
    if agent in chain:
        state.emit("refused", agent=chain[-1], to=agent, reason=f"{agent} is already working on this request")
        return (f"Refused: {agent} is already working on this request ({' > '.join(chain)}). "
                "Finish with what you have.")
    if len(chain) > MAX_DELEGATION_DEPTH:
        state.emit("refused", agent=chain[-1], to=agent, reason="delegation is already 3 levels deep")
        return "Refused: delegation is already 3 levels deep. Finish with what you have."
    state.emit("delegate", agent=chain[-1], to=agent, task=short(task, 400))
    append_audit({
        "event": "delegation",
        "run_id": ctx.deps.state.run_id,
        "ticket_id": ctx.deps.state.ticket_id,
        "loop_step": ctx.deps.state.loop_steps,
        "from_agent": chain[-1],
        "to_agent": agent,
        "task": short(task),
    })
    try:
        output = await run_agent(agent, task, TeamDeps(ctx.deps.state, chain + (agent,)))
    except UnexpectedModelBehavior as err:
        # One helper failing shouldn't sink the whole request; the caller decides what to do.
        append_audit({"event": "delegation_failed", "run_id": ctx.deps.state.run_id,
                      "ticket_id": ctx.deps.state.ticket_id, "from_agent": chain[-1], "to_agent": agent,
                      "error": short(str(err), 200)})
        state.emit("refused", agent=agent, to=chain[-1], reason=f"{agent} could not finish")
        return f"{agent} could not finish this task ({short(str(err), 120)}). Continue without it and say so."
    report = output.model_dump()
    state.emit("reply", agent=agent, to=chain[-1], said=short(said(report) or "", 500))
    return report


async def run_agent(name: str, task: str, deps: TeamDeps) -> BaseModel:
    """Run one agent's loop, auditing every step and enforcing the team's step limit."""
    state = deps.state
    agent = state.agents[name]
    if name not in state.agents_used:
        state.agents_used.append(name)
    base = {"run_id": state.run_id, "ticket_id": state.ticket_id, "agent": name, "chain": " > ".join(deps.chain)}
    pending_calls: dict[str, dict] = {}  # tool_call_id -> tool_log entry waiting for its result
    state.emit("start", agent=name, chain=list(deps.chain))

    allowed = state.tool_access[name]
    tools = state.mcp.filtered(lambda ctx, tool_def: tool_def.name in allowed)
    async with agent.iter(task, deps=deps, toolsets=[tools]) as run:
        async for node in run:
            if Agent.is_model_request_node(node):
                # One agent-loop step = one call to the model. Stop before going over the limit.
                if state.loop_steps >= MAX_LOOP_STEPS:
                    raise LoopLimitReached(f"{name} needed step {state.loop_steps + 1}; limit is {MAX_LOOP_STEPS}")
                state.loop_steps += 1
                parts = node.request.parts
                for p in parts:
                    if isinstance(p, ToolReturnPart) and p.tool_call_id in pending_calls:
                        entry = pending_calls.pop(p.tool_call_id)
                        entry["result"] = short(p.content, 400)
                        if entry["tool"] != "delegate":
                            state.emit("tool_result", agent=name, tool=entry["tool"],
                                       result=summarize(entry["tool"], p.content))
                state.emit("thinking", agent=name)
                append_audit({
                    "event": "agent_step", **base, "loop_step": state.loop_steps, "phase": "model_request",
                    "input": [short(p.content) for p in parts if isinstance(p, UserPromptPart)],
                    "tool_results": [{"tool": p.tool_name, "result": short(p.content)}
                                     for p in parts if isinstance(p, ToolReturnPart)],
                    "retries": [short(p.content, 200) for p in parts if isinstance(p, RetryPromptPart)],
                })
            elif Agent.is_call_tools_node(node):
                parts = node.model_response.parts
                calls = [p for p in parts if isinstance(p, ToolCallPart)]
                state.tools_used.extend(c.tool_name for c in calls)
                for c in calls:
                    if c.tool_name == "final_result":
                        continue
                    entry = {"agent": name, "chain": base["chain"], "loop_step": state.loop_steps,
                             "tool": c.tool_name, "args": c.args_as_dict(), "result": None}
                    state.tool_log.append(entry)
                    pending_calls[c.tool_call_id] = entry
                    if c.tool_name != "delegate":
                        state.emit("tool_call", agent=name, tool=c.tool_name, args=entry["args"])
                text = " ".join(p.content for p in parts if isinstance(p, TextPart)).strip()
                if text:
                    state.emit("says", agent=name, text=short(text, 300))
                append_audit({
                    "event": "agent_step", **base, "loop_step": state.loop_steps, "phase": "model_response",
                    "tool_calls": [{"tool": c.tool_name, "args": short(c.args)} for c in calls],
                    "text": short(" ".join(p.content for p in parts if isinstance(p, TextPart))) or None,
                    "tokens": {"input": node.model_response.usage.input_tokens,
                               "output": node.model_response.usage.output_tokens},
                })
            elif Agent.is_end_node(node):
                report = node.data.output.model_dump()
                state.reports.append({"agent": name, "chain": base["chain"], "loop_step": state.loop_steps,
                                      "output": report})
                state.emit("report", agent=name, said=short(said(report) or "", 600))
                append_audit({
                    "event": "agent_step", **base, "loop_step": state.loop_steps, "phase": "final_output",
                    "output": short(node.data.output, 600),
                })
    return run.result.output

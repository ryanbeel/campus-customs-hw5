"""Data types shared by the Campus Customs agent team."""

from typing import Literal

from pydantic import BaseModel, Field

AgentName = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]

StopReason = Literal["completed", "timeout", "loop_limit", "blocked_by_guardrail", "error"]


class Fact(BaseModel):
    """One fact an agent relied on, with where it came from."""

    statement: str = Field(description="The fact, e.g. 'CC-HOOD-NAVY size M has 8 units on hand'.")
    source: str = Field(description="The MCP tool (and table) it came from, e.g. 'check_inventory (inventory)'.")


class PaymentProposal(BaseModel):
    """A payment Accounting prepared. Nothing is paid until a human approves it."""

    kind: Literal["invoice", "rent", "purchase_order"] = Field(
        description="invoice = pay an open invoice; rent = pay a lease's rent; purchase_order = pay a vendor for new stock."
    )
    ref_id: int | None = Field(
        default=None, description="invoices.id for an invoice, leases.id for rent, vendors.id for a purchase order."
    )
    payee: str
    amount: float
    reference: str = Field(description="What it pays, e.g. 'invoice 501' or 'lease 1 rent due 2026-09-02'.")
    reason: str
    approval_status: Literal["needs_human_approval"] = "needs_human_approval"


class SpecialistReport(BaseModel):
    """What inventory, accounting, facilities or customer service hands back."""

    agent: AgentName
    summary: str = Field(description="Two or three sentences answering the task.")
    facts: list[Fact] = Field(default_factory=list, description="Only facts returned by MCP tools.")
    unknowns: list[str] = Field(default_factory=list, description="Things the database does not say.")
    recommendations: list[str] = Field(default_factory=list)
    payment_proposals: list[PaymentProposal] = Field(default_factory=list)
    customer_message: str | None = Field(
        default=None, description="Customer service only: the draft message to the customer."
    )


class BossDecision(BaseModel):
    """The Boss agent's final answer for one ticket, reported to the owner."""

    ticket_id: int | None = None
    assigned_agents: list[AgentName] = Field(description="Agents the Boss sent work to.")
    decision: str = Field(description="The final decision in one or two sentences.")
    reasoning: list[str] = Field(description="The strongest reasons, each tied to a fact.")
    facts: list[Fact] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    approvals_needed: list[PaymentProposal] = Field(
        default_factory=list, description="Payments waiting for the owner's approval."
    )
    customer_message: str | None = Field(default=None, description="Message to send the customer, if any.")
    next_steps: list[str] = Field(default_factory=list)


class TeamResult(BaseModel):
    """What one team run returns: the decision, or a friendly message if it stopped early."""

    run_id: str
    ticket_id: int | None = None
    stop_reason: StopReason
    stop_detail: str | None = None
    decision: BossDecision | None = None
    message: str = Field(description="Plain message for the person who asked.")
    loop_steps: int
    seconds: float
    agents_used: list[str] = Field(default_factory=list)
    agent_reports: list[dict] = Field(default_factory=list, description="What each agent handed back, in order.")
    tool_calls: list[dict] = Field(default_factory=list, description="Every tool call: agent, tool, args, result.")

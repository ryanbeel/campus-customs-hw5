"""Accounting agent: cash, invoices, margins, and payment proposals for a human to approve."""

from pydantic_ai import Agent, ModelRetry, RunContext

from core import TeamDeps, build_model, delegate, load_prompt
from models import SpecialistReport

# MCP tools this agent may call; core.run_agent applies the filter on each run.
TOOLS = ("get_documents", "get_financials", "find_vendors", "get_tickets", "check_order_status", "get_checking_account")


def build() -> Agent[TeamDeps, SpecialistReport]:
    agent = Agent(
        build_model(),
        name="accounting",
        deps_type=TeamDeps,
        output_type=SpecialistReport,
        instructions=load_prompt("accounting"),
        tools=[delegate],
        retries=2,
    )

    @agent.output_validator
    def check_payments(ctx: RunContext[TeamDeps], output: SpecialistReport) -> SpecialistReport:
        """Payment proposals need a real amount; approval always stays with a human."""
        for p in output.payment_proposals:
            if p.amount <= 0:
                raise ModelRetry(f"Payment to {p.payee} has amount {p.amount}. Use the amount from get_documents.")
            if p.ref_id is None:
                raise ModelRetry(f"Payment to {p.payee} needs ref_id: the invoice id, lease id or vendor id.")
        return output

    return agent

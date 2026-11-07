"""Customer service agent: drafts polite, fact-checked messages to customers."""

from pydantic_ai import Agent, ModelRetry, RunContext

from core import TeamDeps, build_model, delegate, load_prompt
from models import SpecialistReport
from safety import check_customer_message, with_smile

# MCP tools this agent may call; core.run_agent applies the filter on each run.
TOOLS = ("check_inventory", "get_tickets", "send_customer_email", "check_order_status")


def build() -> Agent[TeamDeps, SpecialistReport]:
    agent = Agent(
        build_model(),
        name="customer_service",
        deps_type=TeamDeps,
        output_type=SpecialistReport,
        instructions=load_prompt("customer_service"),
        tools=[delegate],
        retries=2,
    )

    @agent.output_validator
    def check_message(ctx: RunContext[TeamDeps], output: SpecialistReport) -> SpecialistReport:
        """The draft must exist, be safe to send, and end with a virtual smile."""
        if not output.customer_message:
            raise ModelRetry("Write the customer message in customer_message.")
        problem = check_customer_message(output.customer_message)
        if problem:
            raise ModelRetry(problem)
        output.customer_message = with_smile(output.customer_message)
        return output

    return agent

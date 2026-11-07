"""Boss agent: reads each ticket, sends the work to the right agents, and makes the final decision."""

from pydantic_ai import Agent, ModelRetry, RunContext

from core import TeamDeps, build_model, delegate, load_prompt
from models import BossDecision
from safety import check_customer_message, with_smile

# MCP tools this agent may call; core.run_agent applies the filter on each run.
TOOLS = ("get_tickets", "get_checking_account")


def build() -> Agent[TeamDeps, BossDecision]:
    agent = Agent(
        build_model(),
        name="boss",
        deps_type=TeamDeps,
        output_type=BossDecision,
        instructions=load_prompt("boss"),
        tools=[delegate],
        retries=2,
    )

    @agent.output_validator
    def check_customer_reply(ctx: RunContext[TeamDeps], output: BossDecision) -> BossDecision:
        """Customer messages must be safe to send and end with a smile."""
        if output.customer_message:
            problem = check_customer_message(output.customer_message)
            if problem:
                raise ModelRetry(problem)
            output.customer_message = with_smile(output.customer_message)
        return output

    return agent

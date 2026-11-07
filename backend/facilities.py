"""Facilities agent: the shop space, the lease, rent and the landlord."""

from pydantic_ai import Agent

from core import TeamDeps, build_model, delegate, load_prompt
from models import SpecialistReport

# MCP tools this agent may call; core.run_agent applies the filter on each run.
TOOLS = ("get_documents", "get_tickets")


def build() -> Agent[TeamDeps, SpecialistReport]:
    return Agent(
        build_model(),
        name="facilities",
        deps_type=TeamDeps,
        output_type=SpecialistReport,
        instructions=load_prompt("facilities"),
        tools=[delegate],
        retries=2,
    )

"""Inventory agent: stock by SKU and size, shortfalls, and which vendor to restock from."""

from pydantic_ai import Agent

from core import TeamDeps, build_model, delegate, load_prompt
from models import SpecialistReport

# MCP tools this agent may call; core.run_agent applies the filter on each run.
TOOLS = ("check_inventory", "find_vendors", "get_tickets", "update_inventory")


def build() -> Agent[TeamDeps, SpecialistReport]:
    return Agent(
        build_model(),
        name="inventory",
        deps_type=TeamDeps,
        output_type=SpecialistReport,
        instructions=load_prompt("inventory"),
        tools=[delegate],
        retries=2,
    )

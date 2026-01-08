"""Basic example demonstrating skill integration with Pydantic AI.

This example shows how to create an agent with skills and use them
for research tasks.
"""

import asyncio
from pathlib import Path

from pydantic_ai import Agent, RunContext

from pydantic_ai_skills import SkillsToolset


async def main() -> None:
    """Pydantic AI with Agent Skills."""
    # Get the skills directory (examples/skills)
    skills_dir = Path(__file__).parent / 'skills'

    # Initialize Skills Toolset
    skills_toolset = SkillsToolset(directories=[skills_dir])

    # Create agent with skills
    agent = Agent(
        model='openai:gpt-5.2',
        instructions='You are a helpful research assistant.',
        toolsets=[skills_toolset],
    )

    # Add skills instructions to agent (includes skill names and descriptions)
    @agent.instructions
    async def add_skills(ctx: RunContext) -> str | None:
        """Add skills instructions to the agent's context."""
        return await skills_toolset.get_instructions(ctx)

    user_prompt = 'What are the main features of Pydantic AI framework?'

    result = await agent.run(user_prompt)
    print(f'Response:\n\n{result.output}')


if __name__ == '__main__':
    asyncio.run(main())

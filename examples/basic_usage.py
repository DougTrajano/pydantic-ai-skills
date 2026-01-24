"""Basic example demonstrating skill integration with Pydantic AI.

This example shows how to create an agent with skills and use them
for research tasks.
"""

from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext

from pydantic_ai_skills import SkillsToolset

load_dotenv()

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


app = agent.to_web()

if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=7932)

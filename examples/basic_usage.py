"""Basic example demonstrating skill integration with Pydantic AI.

This example shows how to create an agent with skills and use them
for research tasks.
"""

from pathlib import Path

import logfire
import uvicorn
from dotenv import load_dotenv
from pydantic_ai import Agent

from pydantic_ai_skills import SkillsToolset

load_dotenv()

logfire.configure()
logfire.instrument_pydantic_ai()

# Get the skills directory (examples/skills)
skills_dir = Path(__file__).parent / 'skills'

# Initialize Skills Toolset
skills_toolset = SkillsToolset(directories=[skills_dir])

# Create agent with skills
agent = Agent(
    model='gateway/openai:gpt-5.2',
    instructions='You are a helpful research assistant.',
    toolsets=[skills_toolset],
)


app = agent.to_web()

if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=7932)

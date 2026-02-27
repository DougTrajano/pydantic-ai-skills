"""Example of using GitSkillsRegistry to load skills from a remote Git repository.

Demonstrates cloning Anthropic's official skills repository and exposing
the skills to a Pydantic AI agent via SkillsToolset.
"""

import uvicorn
from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext

from pydantic_ai_skills import SkillsToolset
from pydantic_ai_skills.registries.git import GitCloneOptions, GitSkillsRegistry

load_dotenv()

# Clone Anthropic's public skills repo with a shallow, single-branch checkout
# Note: Some skills may require additional dependencies or tools to function properly
registry = GitSkillsRegistry(
    repo_url='https://github.com/anthropics/skills',
    path='skills',
    target_dir='./cached-skills',
    clone_options=GitCloneOptions(depth=1, single_branch=True),
)

# Initialize Skills Toolset backed by the Git registry
skills_toolset = SkillsToolset(registries=[registry])

# Create agent with skills
agent = Agent(
    model='openai:gpt-5.2',
    instructions='You are a helpful assistant with access to a variety of skills.',
    toolsets=[skills_toolset],
)


@agent.instructions
async def add_skills(ctx: RunContext) -> str | None:
    """Add skills instructions to the agent's context."""
    return await skills_toolset.get_instructions(ctx)


app = agent.to_web()

if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=7932)

"""Example of using Pydantic AI with multiple skills directories and tools."""

import datetime

import httpx
import uvicorn
from dotenv import load_dotenv
from langchain_community.tools import DuckDuckGoSearchRun
from pydantic_ai import Agent, RunContext
from pydantic_ai.ext.langchain import tool_from_langchain
from pydantic_ai_filesystem_sandbox import FileSystemToolset

from pydantic_ai_skills import SkillsToolset

load_dotenv()

# Initialize Skills Toolset with the skills directory
skills_toolset = SkillsToolset(
    directories=['./skills', './anthropic-skills']  # Add paths to your skills directories
)

fs_toolset = FileSystemToolset.create_default('./tmp', mode='rw')

search = DuckDuckGoSearchRun()
search_tool = tool_from_langchain(search)

# Create agent with skills as a toolset
agent = Agent(
    model='openai:gpt-5.2',
    instructions='You are a helpful research assistant.',
    instrument=True,
    toolsets=[skills_toolset, fs_toolset],
    tools=[search_tool],
)


@agent.instructions
async def add_skills(ctx: RunContext) -> str | None:
    """Add skills instructions to the agent's context."""
    return await skills_toolset.get_instructions(ctx)


@agent.instructions
def add_today_date() -> str:
    """Add today's date to the agent's context."""
    return f'The date is {datetime.datetime.now().strftime("%B %d, %Y")}.'


@agent.tool_plain(retries=2)
async def fetch_url(url: str, method: str = 'GET', timeout: int = 15) -> str:
    """Fetch the content of a URL.

    Args:
        url (str): The URL to fetch.
        method (str): The HTTP method to use (default is 'GET').
        timeout (int): The timeout for the request in seconds (default is 15).

    Returns:
        str: The content of the URL.
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(method, url)
        response.raise_for_status()
        return response.text


app = agent.to_web()

if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=7932)

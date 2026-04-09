"""Example of using Pydantic AI with multiple skills directories and tools."""

import datetime
from pathlib import Path

import httpx
import logfire
import uvicorn
from dotenv import load_dotenv
from langchain_community.tools import DuckDuckGoSearchRun
from pydantic_ai import Agent
from pydantic_ai.ext.langchain import tool_from_langchain
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai.tools import DeferredToolRequests

from pydantic_ai_skills import SkillsToolset

load_dotenv()

logfire.configure()
logfire.instrument_pydantic_ai()

# Initialize Skills Toolset with the skills directory
script_dir = Path(__file__).parent
skills_toolset = SkillsToolset(directories=[script_dir / 'skills', script_dir / 'anthropic-skills'])

# Create tmp directory for MCP filesystem server
tmp_dir = script_dir / 'tmp'
tmp_dir.mkdir(exist_ok=True)

# Initialize MCP filesystem server
fs_toolset = MCPServerStdio(
    'npx',
    args=['@modelcontextprotocol/server-filesystem', str(tmp_dir)],
    timeout=30,
)

search = DuckDuckGoSearchRun()
search_tool = tool_from_langchain(search)

# Create agent with skills and MCP filesystem toolsets
agent = Agent(
    model='gateway/openai:gpt-5.2',
    instructions='You are a helpful research assistant.',
    toolsets=[skills_toolset, fs_toolset],
    tools=[search_tool],
    output_type=[str, DeferredToolRequests],
)


@agent.instructions
async def add_today_date() -> str:
    """Add today's date to the agent's context."""
    return f'The date is {datetime.datetime.now().strftime("%B %d, %Y")}.'


@agent.tool_plain(retries=2, requires_approval=True)
async def fetch_url(url: str, method: str = 'GET', httpx_timeout: int = 15) -> str:
    """Fetch the content of a URL.

    Args:
        url (str): The URL to fetch.
        method (str): The HTTP method to use (default is 'GET').
        httpx_timeout (int): The timeout for the request in seconds (default is 15).

    Returns:
        str: The content of the URL.
    """
    async with httpx.AsyncClient(timeout=httpx_timeout) as client:
        response = await client.request(method, url)
        response.raise_for_status()
        return response.text


app = agent.to_web()

if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=7932)

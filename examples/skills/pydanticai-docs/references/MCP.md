# MCP (Model Context Protocol) Integration

Pydantic AI can connect to MCP servers and expose their tools to agents. Each MCP server instance is a toolset.

## Key API / Patterns

- `MCPServerStreamableHTTP(url)` — connect to an MCP server over Streamable HTTP
- `MCPServerSSE(url)` — connect via Server-Sent Events (deprecated; prefer Streamable HTTP)
- `MCPServerStdio(command, args)` — connect to a subprocess-based MCP server
- `Agent(model, toolsets=[server])` — register MCP server as a toolset
- `async with agent:` — manage connection lifecycle
- `tool_prefix='prefix'` — prefix all tools from a server to avoid naming conflicts
- `load_mcp_servers('config.json')` — load multiple servers from a JSON config file

## Installation

```bash
pip install "pydantic-ai-slim[mcp]"
```

## Code Example: Streamable HTTP

```python
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStreamableHTTP

server = MCPServerStreamableHTTP('http://localhost:8000/mcp')
agent = Agent('openai:gpt-4o', toolsets=[server])

async def main():
    async with agent:
        result = await agent.run('What is 7 plus 5?')
        print(result.output)
```

## Code Example: Stdio Server

```python
from pydantic_ai.mcp import MCPServerStdio

server = MCPServerStdio('npx', ['-y', '@modelcontextprotocol/server-filesystem', '/tmp'])
agent = Agent('openai:gpt-4o', toolsets=[server])

async def main():
    async with agent:
        result = await agent.run('List the files in /tmp')
        print(result.output)
```

## Multiple Servers with Prefixes

```python
from pydantic_ai.mcp import MCPServerStreamableHTTP

weather = MCPServerStreamableHTTP('http://localhost:3001/mcp', tool_prefix='weather')
calc = MCPServerStreamableHTTP('http://localhost:3002/mcp', tool_prefix='calc')

agent = Agent('openai:gpt-4o', toolsets=[weather, calc])
# Tools exposed as: weather_get_forecast, calc_add, etc.
```

## Config File Loading

```python
from pydantic_ai.mcp import load_mcp_servers

servers = load_mcp_servers('mcp_config.json')
agent = Agent('openai:gpt-4o', toolsets=servers)
```

Config supports `${VAR}` and `${VAR:-default}` env var expansion.

## For Details, See

- Client guide: <https://ai.pydantic.dev/mcp/client/index.md>
- Overview: <https://ai.pydantic.dev/mcp/overview/index.md>
- API reference: <https://ai.pydantic.dev/api/mcp/index.md>

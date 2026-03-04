# Dependencies

Pydantic AI provides first-class dependency injection: strongly typed data and services are passed to tools, system prompts, and output validators via `RunContext[T]`.

## Key API / Patterns

- `RunContext[T]` — parameterized type received as the first argument in tools and prompts
- `ctx.deps` — access the injected dependency value
- `deps_type=MyDeps` — register the dependency type on the Agent constructor (pass the type, not an instance)
- `agent.override(deps=...)` — inject test dependencies without changing production code
- `@agent.system_prompt` / `@agent.instructions` / `@agent.output_validator` — all accept `RunContext` as first arg

## Code Example

```python
from dataclasses import dataclass
import httpx
from pydantic_ai import Agent, RunContext

@dataclass
class MyDeps:
    api_key: str
    http_client: httpx.AsyncClient

agent = Agent('openai:gpt-4o', deps_type=MyDeps)

@agent.system_prompt
async def add_context(ctx: RunContext[MyDeps]) -> str:
    return f'API key ends in: {ctx.deps.api_key[-4:]}'

@agent.tool
async def fetch_resource(ctx: RunContext[MyDeps], path: str) -> str:
    response = await ctx.deps.http_client.get(path)
    return response.text

async def main():
    async with httpx.AsyncClient() as client:
        deps = MyDeps(api_key='sk-abc123', http_client=client)
        result = await agent.run('Fetch /health', deps=deps)
        print(result.output)
```

## Injection Points

Dependencies inject via `RunContext` in three locations:

| Decorator                 | First parameter           |
| ------------------------- | ------------------------- |
| `@agent.system_prompt`    | `ctx: RunContext[MyDeps]` |
| `@agent.tool`             | `ctx: RunContext[MyDeps]` |
| `@agent.output_validator` | `ctx: RunContext[MyDeps]` |

## Testing with Override

```python
with agent.override(deps=test_deps):
    result = agent.run_sync('test prompt')
```

## For Details, See

<https://ai.pydantic.dev/dependencies/index.md>

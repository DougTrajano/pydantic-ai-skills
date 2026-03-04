# Toolsets

A toolset is a collection of tools that can be registered with an agent in a single step. Toolsets enable reuse across agents, dynamic composition, filtering, and prefixing to avoid naming conflicts.

## Key API / Patterns

- `FunctionToolset` — group locally defined functions as a reusable toolset
- `@toolset.tool` / `toolset.add_function(fn)` — add tools to a toolset
- `Agent(model, toolsets=[toolset])` — register at construction time
- `agent.run_sync(prompt, toolsets=[toolset])` — register per run
- `@agent.toolset` — dynamic toolset resolved per run via decorator
- `CombinedToolset([t1, t2])` — merge multiple toolsets
- `toolset.prefixed('prefix')` — prefix all tool names (avoids conflicts)
- `toolset.filtered(lambda ctx, tool: ...)` — filter tools per run context
- `toolset.renamed({'new': 'old'})` — rename tools

## Code Example

```python
from pydantic_ai import Agent, FunctionToolset, RunContext

# Define a reusable toolset
weather_toolset = FunctionToolset()

@weather_toolset.tool
def get_temperature(ctx: RunContext, city: str) -> str:
    """Get current temperature for a city."""
    return f'72°F in {city}'

@weather_toolset.tool
def get_forecast(ctx: RunContext, city: str, days: int) -> str:
    """Get a weather forecast."""
    return f'{days}-day forecast for {city}'

# Register with an agent
agent = Agent('openai:gpt-4o', toolsets=[weather_toolset])
result = agent.run_sync('What is the weather in London?')
```

## Composing Toolsets

```python
from pydantic_ai import CombinedToolset

combined = CombinedToolset([weather_toolset, calendar_toolset])

# Prefix to avoid tool name collisions
prefixed = weather_toolset.prefixed('weather')

# Filter dynamically
filtered = combined.filtered(
    lambda ctx, tool: 'fahrenheit' not in tool.name
)
```

## Tool vs. Toolset

|                     | Tool                          | Toolset                                   |
| ------------------- | ----------------------------- | ----------------------------------------- |
| Scope               | Single function               | Collection of functions                   |
| Registration        | `tools=[fn]` or `@agent.tool` | `toolsets=[toolset]`                      |
| Reuse across agents | Manual                        | Natural — pass the same instance          |
| Composition         | N/A                           | `CombinedToolset`, `prefixed`, `filtered` |

## For Details, See

<https://ai.pydantic.dev/toolsets/index.md>
<https://ai.pydantic.dev/api/toolsets/index.md>

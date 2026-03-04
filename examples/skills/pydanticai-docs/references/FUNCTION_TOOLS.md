# Function Tools

Tools are functions the LLM can call during a run. Pydantic AI inspects function signatures to build the tool schema automatically; docstrings become tool descriptions.

## Key API / Patterns

- `@agent.tool` — tool that receives `RunContext` as its first argument
- `@agent.tool_plain` — tool without `RunContext` (plain function)
- `Tool(fn, takes_ctx=True/False)` — explicit wrapper for constructor-based registration
- `agent = Agent(model, tools=[...])` — register tools at construction time
- Return anything Pydantic can serialize to JSON
- Raise `ModelRetry` inside a tool to ask the model to regenerate

## Code Example

```python
import random
from pydantic_ai import Agent, RunContext, ModelRetry

agent = Agent('openai:gpt-4o', deps_type=str)

@agent.tool_plain
def roll_die() -> str:
    """Roll a six-sided die and return the result."""
    return str(random.randint(1, 6))

@agent.tool
def get_player_name(ctx: RunContext[str]) -> str:
    """Return the current player's name."""
    return ctx.deps

@agent.tool(retries=3)
def unreliable_api(ctx: RunContext[str], query: str) -> str:
    """Call an API that might fail."""
    if not query:
        raise ModelRetry('Please provide a non-empty query')
    return f'Result for {query}'

result = agent.run_sync('Roll the die for me!', deps='Alice')
```

## @agent.tool vs @agent.tool_plain

|                        | `@agent.tool`                   | `@agent.tool_plain`                   |
| ---------------------- | ------------------------------- | ------------------------------------- |
| First parameter        | `ctx: RunContext[DepsType]`     | _(none; starts with business params)_ |
| Access to deps         | Yes (`ctx.deps`)                | No                                    |
| Access to run metadata | Yes (`ctx.retry`, `ctx.run_id`) | No                                    |

## Constructor Registration

```python
from pydantic_ai.tools import Tool

agent = Agent(
    'openai:gpt-4o',
    tools=[
        Tool(roll_die, takes_ctx=False),
        Tool(get_player_name, takes_ctx=True),
    ],
)
```

## For Details, See

<https://ai.pydantic.dev/tools/index.md>
<https://ai.pydantic.dev/tools-advanced/index.md>

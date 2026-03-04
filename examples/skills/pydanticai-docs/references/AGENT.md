# Agents

The `Agent` class is the primary interface for interacting with LLMs. It acts as a container for the model, instructions, tools, output type, and dependencies.

## Key API / Patterns

- `Agent(model, ...)` — constructor; model is a string in `provider:model-name` format
- `agent.run(prompt)` — async; returns `AgentRunResult`
- `agent.run_sync(prompt)` — sync wrapper; returns `AgentRunResult`
- `agent.run_stream(prompt)` — async streaming context manager
- `result.output` — access the final output from a run
- `result.usage()` — token usage and request count
- `@agent.system_prompt` / `@agent.instructions` — dynamic prompt decorators
- `agent.override(model=..., deps=...)` — context manager for testing overrides

## Code Example

```python
from pydantic_ai import Agent

agent = Agent(
    'openai:gpt-4o',
    system_prompt='You are a helpful assistant.',
    retries=2,
)

# Sync run
result = agent.run_sync('What is the capital of France?')
print(result.output)

# Async run
import asyncio
async def main():
    result = await agent.run('What is 2 + 2?')
    print(result.output)

asyncio.run(main())
```

## Constructor Parameters

| Parameter        | Type            | Description                                                     |
| ---------------- | --------------- | --------------------------------------------------------------- |
| `model`          | `str`           | Model identifier (`provider:model-name`)                        |
| `deps_type`      | `Type`          | Dependency type; passed the TYPE not an instance                |
| `output_type`    | `Type`          | Structured output type (Pydantic model, scalar, union)          |
| `system_prompt`  | `str`           | Static system instructions (persisted in `message_history`)     |
| `instructions`   | `str`           | Runtime instructions (excluded when `message_history` provided) |
| `retries`        | `int`           | Default retry count (default: 1)                                |
| `model_settings` | `ModelSettings` | Default model configuration                                     |

## `system_prompt` vs `instructions`

- **`system_prompt`**: Persisted in `message_history`; use when retaining context across multiple agent interactions.
- **`instructions`**: Excluded when explicit `message_history` is provided; recommended for most single-agent use cases where you want fresh instructions each run.

## Run Method Signatures

| Method                         | Returns                                  | Behavior              |
| ------------------------------ | ---------------------------------------- | --------------------- |
| `run(prompt, **kwargs)`        | `Coroutine[AgentRunResult]`              | Async, full execution |
| `run_sync(prompt, **kwargs)`   | `AgentRunResult`                         | Synchronous wrapper   |
| `run_stream(prompt, **kwargs)` | `AsyncContextManager[StreamedRunResult]` | Async streaming       |

Common kwargs: `deps`, `model_settings`, `message_history`, `usage_limits`, `instructions`

## For Details, See

<https://ai.pydantic.dev/agent/index.md>
<https://ai.pydantic.dev/api/agent/index.md>

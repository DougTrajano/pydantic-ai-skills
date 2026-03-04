# Message History

Pydantic AI exposes full message history from every run, enabling multi-turn conversations, persistent chat sessions, and fine-grained context management.

## Key API / Patterns

- `result.all_messages()` — all messages including any prior history passed in
- `result.new_messages()` — only messages from the current run (use this to chain runs)
- `agent.run(..., message_history=result.new_messages())` — pass history to continue a conversation
- `ModelMessagesTypeAdapter` — serialize/deserialize messages to/from JSON
- `history_processors=[fn]` — functions that transform history before each model call (filtering, summarization)

## Multi-Turn Conversation

```python
from pydantic_ai import Agent

agent = Agent('openai:gpt-4o', instructions='Be concise.')

result1 = agent.run_sync('Tell me a joke.')
result2 = agent.run_sync(
    'Explain that joke.',
    message_history=result1.new_messages(),
)
print(result2.output)
```

When `message_history` is provided, no new system prompt is generated — the existing history is assumed to already contain one.

## Persisting to JSON

```python
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessagesTypeAdapter
from pydantic_core import to_jsonable_python

agent = Agent('openai:gpt-4o')
result = agent.run_sync('Hello!')

# Serialize
raw = to_jsonable_python(result.all_messages())

# Restore + continue
restored = ModelMessagesTypeAdapter.validate_python(raw)
result2 = agent.run_sync('Continue.', message_history=restored)
```

## History Processors

```python
def keep_last_5(messages):
    return messages[-5:] if len(messages) > 5 else messages

agent = Agent('openai:gpt-4o', history_processors=[keep_last_5])
```

## Message Types

| Type            | Contents                                               |
| --------------- | ------------------------------------------------------ |
| `ModelRequest`  | `UserPromptPart`, `SystemPromptPart`, `ToolReturnPart` |
| `ModelResponse` | `TextPart`, `ToolCallPart`                             |

Each message includes `timestamp` and `run_id` metadata.

## For Details, See

<https://ai.pydantic.dev/message-history/index.md>
<https://ai.pydantic.dev/api/messages/index.md>

# Structured Output

The `output_type` parameter on `Agent` controls what the agent returns. Pydantic AI uses the model's tool-calling to enforce structure and validates the result.

## Key API / Patterns

- `output_type=MyModel` — Pydantic `BaseModel` subclass for structured output
- `output_type=str` — plain text (default when omitted)
- `output_type=[MyModel, str]` — union: structured or plain text
- `output_type=int | float` — union of scalar types
- `result.output` — access the typed output on `AgentRunResult`
- `@agent.output_validator` — custom async validation; raise `ModelRetry` to retry

## Code Example

```python
from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry, RunContext

class CityInfo(BaseModel):
    city: str
    country: str
    population: int

agent = Agent('openai:gpt-4o', output_type=CityInfo)

@agent.output_validator
async def validate_population(ctx: RunContext, output: CityInfo) -> CityInfo:
    if output.population <= 0:
        raise ModelRetry('Population must be positive')
    return output

result = agent.run_sync('Tell me about London')
print(result.output)         # CityInfo(city='London', country='United Kingdom', ...)
print(result.output.city)    # 'London'
```

## Supported Output Types

| Type               | Example                              |
| ------------------ | ------------------------------------ |
| Pydantic BaseModel | `class Res(BaseModel): name: str`    |
| Scalar             | `output_type=str`, `output_type=int` |
| TypedDict          | `class Res(TypedDict): name: str`    |
| Dataclass          | `@dataclass class Res: name: str`    |
| Union              | `output_type=MyModel \| str`         |
| List/Dict          | `output_type=list[str]`              |

## For Details, See

<https://ai.pydantic.dev/output/index.md>
<https://ai.pydantic.dev/api/output/index.md>

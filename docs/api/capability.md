# SkillsCapability API Reference

`SkillsCapability` integrates pydantic-ai-skills with Pydantic AI's capabilities API.

For pydantic-ai >= 1.71, this is the preferred integration path.

Use this when your agent uses `capabilities=[...]`.

::: pydantic_ai_skills.capability.SkillsCapability
    options:
      show_source: true
      heading_level: 2
      members:
        - __init__
        - get_toolset
        - get_instructions
        - toolset

## Constructor Parameters

`SkillsCapability.__init__()` accepts the same skill loading options as `SkillsToolset`:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `skills` | `list[Skill] \| None` | `None` | Pre-loaded `Skill` objects. |
| `directories` | `list[str \| Path \| SkillsDirectory] \| None` | `None` | Local skill sources. |
| `registries` | `list[SkillRegistry] \| None` | `None` | Remote skill sources. |
| `validate` | `bool` | `True` | Validate discovered skills. |
| `max_depth` | `int \| None` | `3` | Directory discovery depth. |
| `id` | `str \| None` | `None` | Optional toolset id. |
| `instruction_template` | `str \| None` | `None` | Optional custom instruction template. |
| `exclude_tools` | `set[str] \| list[str] \| None` | `None` | Exclude one or more registered tools. |
| `auto_reload` | `bool` | `False` | Re-scan local directories before each run. |

## Behavior Notes

- Internally wraps a `SkillsToolset` for behavior parity.
- `get_toolset()` and `.toolset` expose the wrapped `SkillsToolset` instance.
- Bundles skill tools and skills instructions through the Capability API.
- Avoids manual `@agent.instructions` wiring for `get_instructions(ctx)`.
- Raises `RuntimeError` at instantiation time if capabilities API is unavailable.

## Example

```python
from pydantic_ai import Agent
from pydantic_ai_skills import SkillsCapability

agent = Agent(
    model='openai:gpt-5.2',
    capabilities=[
        SkillsCapability(
            directories=['./skills'],
            auto_reload=True,
        )
    ],
)
```

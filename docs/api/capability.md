# SkillsCapability API Reference

`SkillsCapability` integrates pydantic-ai-skills with Pydantic AI's capabilities API.

This is the preferred integration path. Use it when your agent uses `capabilities=[...]`.

::: pydantic_ai_skills.capability.SkillsCapability
    options:
      show_source: true
      heading_level: 2
      members:
        - __init__
        - from_spec
        - get_serialization_name
        - get_toolset
        - get_instructions
        - get_description
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

## Agent specs

`SkillsCapability` can be used in declarative agent specs loaded with `Agent.from_spec`
or `Agent.from_file`. Register the class via `custom_capability_types` so the spec loader
can resolve the `SkillsCapability` key:

```yaml
# agent.yaml
model: openai:gpt-5.2
capabilities:
  - SkillsCapability:
      directories: ['./skills']
      id: skills
      defer_loading: true
```

```python
from pydantic_ai import Agent
from pydantic_ai_skills import SkillsCapability

agent = Agent.from_file('agent.yaml', custom_capability_types=[SkillsCapability])
```

Only serializable arguments are spec-expressible: `directories` (as path strings),
`validate`, `max_depth`, `id`, `instruction_template`, `exclude_tools`, `auto_reload`,
`description`, and `defer_loading`. Programmatic `skills`, `registries`, and
`SkillsDirectory` instances are not representable in a spec — construct the capability in
Python for those. See [`from_spec`][pydantic_ai_skills.capability.SkillsCapability.from_spec].

# Types API Reference

Type definitions for pydantic-ai-skills.

## Overview

The package uses dataclasses for type-safe skill representation:

- `Skill` - Complete skill with all components (file-based or programmatic)
- `SkillResource` - Resource file or callable within a skill
- `SkillScript` - Executable script (file-based or callable) within a skill

!!! info "File-Based vs Programmatic"
    While these types support both file-based skills (loaded from directories) and programmatic skills (created in Python code), the API reference below focuses on programmatic usage. For file-based skills, see [Creating Skills](../creating-skills.md). For programmatic skills, see [Programmatic Skills](../programmatic-skills.md).

## Type Definitions

::: pydantic_ai_skills.types.Skill
    options:
      show_source: true
      heading_level: 3

::: pydantic_ai_skills.types.SkillResource
    options:
      show_source: true
      heading_level: 3

::: pydantic_ai_skills.types.SkillScript
    options:
      show_source: true
      heading_level: 3

## Usage Examples

### Creating Programmatic Skills

```python
from pydantic_ai import RunContext
from pydantic_ai.toolsets.skills import Skill, SkillResource

# Create a skill with static resources
my_skill = Skill(
    name='my-skill',
    description='A programmatic skill',
    content='Instructions for using this skill...',
    resources=[
        SkillResource(
            name='reference',
            content='## Reference\n\nStatic documentation here...'
        )
    ]
)

# Add dynamic resources
@my_skill.resource
def get_info() -> str:
    """Get dynamic information."""
    return "Dynamic content generated at runtime"

@my_skill.resource
async def get_data(ctx: RunContext[MyDeps]) -> str:
    """Get data from dependencies."""
    return await ctx.deps.fetch_data()

# Add scripts
@my_skill.script
async def process(ctx: RunContext[MyDeps], query: str) -> str:
    """Process a query.

    Args:
        query: The query to process
    """
    result = await ctx.deps.process(query)
    return f"Processed: {result}"
```

### Working with File-Based Skills

```python
from pydantic_ai_skills import SkillsToolset

toolset = SkillsToolset(directories=["./skills"])

# Access skills
for name, skill in toolset.skills.items():
    print(f"\nSkill: {name}")
    print(f"  Description: {skill.description}")

    if skill.uri:  # File-based skill
        print(f"  URI: {skill.uri}")

    # Access metadata
    if skill.metadata and "version" in skill.metadata:
        print(f"  Version: {skill.metadata['version']}")

    # List resources
    if skill.resources:
        print(f"  Resources:")
        for resource in skill.resources:
            print(f"    - {resource.name}")

    # List scripts
    if skill.scripts:
        print(f"  Scripts:")
        for script in skill.scripts:
            print(f"    - {script.name}")
```

### Mixing Programmatic and File-Based Skills

```python
from pydantic_ai import RunContext
from pydantic_ai.toolsets.skills import Skill, SkillsToolset

# Create programmatic skill
custom_skill = Skill(
    name='custom-skill',
    description='Programmatic skill',
    content='Custom instructions...'
)

@custom_skill.script
async def custom_action(ctx: RunContext[MyDeps]) -> str:
    """Perform custom action."""
    return 'Action completed'

# Combine with file-based skills
toolset = SkillsToolset(
    directories=["./skills"],  # File-based skills
    skills=[custom_skill]      # Programmatic skills
)

print(f"Total skills: {len(toolset.skills)}")
```

## Type Structures

### Skill Structure

```
Skill
├── name: str                    # Unique skill identifier
├── description: str             # Brief description
├── content: str                 # Main instructions (markdown)
├── resources: list[SkillResource]  # Additional resources
├── scripts: list[SkillScript]   # Executable scripts
├── uri: str | None             # Base URI (file-based only)
└── metadata: dict[str, Any] | None  # Additional metadata
```

### SkillResource Structure

```
SkillResource
├── name: str                    # Resource identifier
├── description: str | None     # Optional description
├── content: str | None         # Static content (for file-based or inline)
├── function: Callable | None   # Callable function (programmatic)
├── takes_ctx: bool             # Whether function takes RunContext
├── function_schema: FunctionSchema | None  # Schema for callable
└── uri: str | None             # File URI (file-based only)
```

### SkillScript Structure

```
SkillScript
├── name: str                    # Script identifier
├── description: str | None     # Optional description
├── function: Callable | None   # Callable function (programmatic)
├── takes_ctx: bool             # Whether function takes RunContext
├── function_schema: FunctionSchema | None  # Schema for callable
├── uri: str | None             # File URI (file-based only)
└── skill_name: str | None      # Parent skill name
```

## Programmatic vs File-Based

### File-Based Skills

Loaded from filesystem directories:

- `uri` points to file/directory location
- `content` is loaded from `SKILL.md`
- Resources loaded from additional `.md` files
- Scripts loaded from `scripts/` directory and executed via subprocess

### Programmatic Skills

Created in Python code:

- No `uri` (no filesystem location)
- `content` provided directly as string
- Resources can be static content or callable functions
- Scripts are Python functions with RunContext support
- Supports dependency injection via `RunContext`

## See Also

- [SkillsToolset](toolset.md) - Main toolset API
- [Exceptions](exceptions.md) - Exception classes
- [Creating Skills](../creating-skills.md) - How to create file-based skills
- [Programmatic Skills](../programmatic-skills.md) - How to create programmatic skills

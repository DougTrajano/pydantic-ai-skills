# Types API Reference

Type definitions for pydantic-ai-skills.

## Overview

The package uses dataclasses for type-safe skill representation:

- `Skill` - Complete skill with metadata, resources, and scripts
- `SkillResource` - Resource file (content) or callable resource within a skill
- `SkillScript` - Executable script (file or callable function) within a skill
- `SkillWrapper` - Generic decorator return type for `@toolset.skill()` supporting attachment of resources and scripts

!!! info "File-Based vs Programmatic"
    These types support both file-based skills (loaded from directories) and programmatic skills (created in Python code). For file-based skills, see [Creating Skills](../creating-skills.md). For programmatic skills, see [Programmatic Skills](../programmatic-skills.md). For advanced patterns, see [Advanced Features](../advanced.md).

## Skill Class

::: pydantic_ai_skills.types.Skill
    options:
      show_source: true
      heading_level: 3

### Key Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Unique skill identifier. Pattern: `^[a-z0-9]+(-[a-z0-9]+)*$`, max 64 chars. |
| `description` | `str` | Brief description of the skill. Max 1024 characters. |
| `content` | `str` | Main skill instructions in markdown format. |
| `resources` | `list[SkillResource] \| None` | Additional resources (documentation, schemas, data). |
| `scripts` | `list[SkillScript] \| None` | Executable scripts (file-based or callable functions). |
| `uri` | `str \| None` | Base URI/path. Set for file-based skills, None for programmatic. |
| `metadata` | `dict[str, Any] \| None` | Custom metadata (version, author, license, compatibility, etc.). |

### Methods

| Method | Description |
|--------|-------------|
| `@resource` | Decorator to attach a callable resource to the skill. |
| `@script` | Decorator to attach a callable script to the skill. |

## SkillResource Class

::: pydantic_ai_skills.types.SkillResource
    options:
      show_source: true
      heading_level: 3

### Key Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Resource identifier within the skill. |
| `description` | `str \| None` | Optional description of the resource. |
| `content` | `str \| None` | Static content (for static resources or file-based). |
| `function` | `Callable \| None` | Callable function (for programmatic dynamic resources). |
| `takes_ctx` | `bool` | Whether function accepts `RunContext` as first parameter. Auto-detected. |
| `function_schema` | `FunctionSchema \| None` | JSON schema for function parameters (Pydantic AI generated). |
| `uri` | `str \| None` | File URI for file-based resources. |

### File-Based Variants

`FileSkillResource` - Loads resource content from file:
- Auto-detects file type by extension
- Supports: `.md`, `.json`, `.yaml`, `.yml`, `.csv`, `.xml`, `.txt`
- JSON/YAML files are parsed; others returned as text
- Automatically validates path traversal safety

## SkillScript Class

::: pydantic_ai_skills.types.SkillScript
    options:
      show_source: true
      heading_level: 3

### Key Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Script identifier within the skill. |
| `description` | `str \| None` | Optional description of what the script does. |
| `function` | `Callable \| None` | Callable Python function (for programmatic scripts). |
| `takes_ctx` | `bool` | Whether function accepts `RunContext` as first parameter. Auto-detected. |
| `function_schema` | `FunctionSchema \| None` | JSON schema for function parameters. |
| `uri` | `str \| None` | File URI for file-based scripts. |
| `skill_name` | `str \| None` | Parent skill name (auto-set for file-based scripts). |

### File-Based Variants

`LocalSkillScriptExecutor` - Executes file-based scripts:
- Runs Python scripts via subprocess
- Converts dict arguments to CLI flags: `{"query": "test"}` → `--query test`
- Combines stdout/stderr
- Default timeout: 30 seconds
- Execution directory: script's parent folder

`CallableSkillScriptExecutor` - Executes callable functions:
- Runs Python functions directly
- Passes dict arguments as function kwargs
- Supports async functions
- Receives RunContext for dependency access

## SkillWrapper[T] Class

Generic type returned by `@toolset.skill()` decorator that enables type-safe dependency injection and attachment of resources/scripts.

**Generic Parameter**: `T` - The dependency type available in `RunContext[T]`

### Decorators

```python
@skill.resource
def my_resource() -> str:
    """Attach a callable resource."""
    return "..."

@skill.resource
async def context_resource(ctx: RunContext[MyDeps]) -> str:
    """Resource with access to dependencies."""
    return str(ctx.deps)

@skill.script
def my_script() -> str:
    """Attach a callable script."""
    return "..."

@skill.script
async def context_script(ctx: RunContext[MyDeps], param: str) -> str:
    """Script with dependencies and parameters."""
    return f"Executed with {param}"
```

## Utility Functions

### normalize_skill_name()

```python
def normalize_skill_name(name: str) -> str:
    """Convert a name to valid skill name format.

    Rules:
    - Convert underscores to hyphens
    - Convert to lowercase
    - Ensure matches ^[a-z0-9]+(-[a-z0-9]+)*$

    Args:
        name: Input string (e.g., "MySkillName", "my_skill_name")

    Returns:
        Normalized skill name (e.g., "my-skill-name")
    """
```

## Type Structures

### Skill Structure

```
Skill
├── name: str                              # Unique identifier (lowercase, hyphens only)
├── description: str                       # Brief description (max 1024 chars)
├── content: str                           # Main instructions (markdown)
├── resources: list[SkillResource] | None  # Additional resources
├── scripts: list[SkillScript] | None      # Executable scripts
├── uri: str | None                        # Base path (file-based: set, programmatic: None)
└── metadata: dict[str, Any] | None        # Custom fields (version, author, license, etc.)
```

### SkillResource Structure

```
SkillResource
├── name: str                      # Resource identifier
├── description: str | None        # Optional description
├── content: str | None            # Static content
├── function: Callable | None      # Callable (for dynamic resources)
├── takes_ctx: bool                # Requires RunContext
├── function_schema: FunctionSchema| None
└── uri: str | None                # File path (file-based only)
```

### SkillScript Structure

```
SkillScript
├── name: str                      # Script identifier
├── description: str | None        # Optional description
├── function: Callable | None      # Callable (for programmatic)
├── takes_ctx: bool                # Requires RunContext
├── function_schema: FunctionSchema| None
├── uri: str | None                # File path (file-based only)
└── skill_name: str | None         # Parent skill (file-based only)
```

## Common Metadata Fields

When creating skills, these metadata fields are commonly used:

| Field | Type | Purpose |
|-------|------|---------|
| `version` | `str` | Semantic version (e.g., "1.0.0") |
| `author` | `str` | Creator/maintainer |
| `license` | `str` | License identifier (e.g., "Apache-2.0") |
| `compatibility` | `str` | Environment requirements |
| `tags` | `list[str]` | Categorization tags |
| `requires` | `dict[str, str]` | External dependencies |
| `deprecated` | `bool` | Whether skill is deprecated |
| `deprecation_message` | `str` | Explanation if deprecated |

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

- [SkillsToolset](toolset.md) - Main toolset API and initialization
- [Exceptions](exceptions.md) - Exception classes and error handling
- [Advanced Features](../advanced.md) - Decorator patterns and custom executors
- [Creating Skills](../creating-skills.md) - File-based skill creation guide
- [Programmatic Skills](../programmatic-skills.md) - Programmatic skill creation guide

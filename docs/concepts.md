# Core Concepts

Understanding the key concepts behind pydantic-ai-skills will help you build better agent systems.

## Skills

A **skill** is a modular package that extends an agent's capabilities. Skills can be created in two ways:

### File-Based Skills

Each skill is a directory containing:

- `SKILL.md` - Required file with metadata and instructions
- `scripts/` - Optional directory with executable Python scripts
- `resources/` - Optional directory with additional documentation or data files

```markdown
my-skill/
├── SKILL.md # Required: Instructions and metadata
├── scripts/ # Optional: Executable scripts
│ └── my_script.py
└── resources/ # Optional: Additional files
├── reference.md
└── data.json
```

### Programmatic Skills

Skills can also be created programmatically in Python code using the `Skill` class with decorators for resources and scripts. This enables dynamic content generation and dependency access. See [Programmatic Skills](programmatic-skills.md) for details.

## SKILL.md Format

The `SKILL.md` file uses **YAML frontmatter** for metadata and **Markdown** for instructions.

### Minimal Example

````markdown
---
name: my-skill
description: A brief description of what this skill does
---

# My Skill

Detailed instructions for the agent on how to use this skill...

### Required Fields

- `name` - Unique identifier for the skill
- `description` - Brief description (shown in skill listings)

### Optional Fields

You can add any additional metadata:

```yaml
---
name: arxiv-search
description: Search arXiv for research papers
version: 1.0.0
author: Your Name
category: research
tags: [papers, arxiv, academic]
---
```
````

## Progressive Disclosure

The toolset implements **progressive disclosure** - exposing information only when needed:

1. **Initial**: Skill names and descriptions are added to agent's instructions via `@agent.instructions` decorator calling `get_instructions(ctx)`
2. **Loading**: Agent calls `load_skill(name)` to get full instructions when needed
3. **Resources**: Agent calls `read_skill_resource()` for additional documentation
4. **Execution**: Agent calls `run_skill_script()` to execute scripts

This approach:

- Reduces initial context size
- Lets agents discover capabilities dynamically
- Improves token efficiency
- Scales to many skills

## The Four Tools

The `SkillsToolset` provides four tools to agents:

### 1. list_skills()

Lists all available skills with their descriptions.

**Returns**: Formatted markdown with skill names and descriptions

**When to use**: Optional - skills are already listed in the agent's instructions via `get_instructions(ctx)`. Use only if the agent needs to re-check available skills dynamically.

### 2. load_skill(name)

Loads the complete instructions for a specific skill.

**Parameters**:

- `skill_name` (str) - Name of the skill to load

**Returns**: Full SKILL.md content including detailed instructions

**When to use**: When the agent needs detailed instructions for using a skill

### 3. read_skill_resource(skill_name, resource_name)

Reads additional resource files from a skill.

**Parameters**:

- `skill_name` (str) - Name of the skill
- `resource_name` (str) - Resource filename (e.g., "FORMS.md")

**Returns**: Content of the resource file

**When to use**: When a skill references additional documentation or data files

### 4. run_skill_script(skill_name, script_name, args)

Executes a Python script from a skill.

**Parameters**:

- `skill_name` (str) - Name of the skill
- `script_name` (str) - Script name without .py extension
- `args` (list[str], optional) - Command-line arguments

**Returns**: Script output (stdout and stderr combined)

**When to use**: When a skill needs to execute custom code

## SkillsToolset

The `SkillsToolset` class is the main interface for integrating skills with Pydantic AI agents.

### Initialization

```python
from pydantic_ai_skills import SkillsToolset

toolset = SkillsToolset(
    directories=["./skills", "./shared-skills"],
    validate=True,           # Validate skill structure
    max_depth=3,             # Maximum depth for skill discovery
    id="skills"              # Unique identifier
)
```

### Key Methods

- `get_instructions(ctx)` - Get instructions text (automatically injected into agent)
- `get_skill(name)` - Get a specific skill object
- `refresh()` - Re-scan directories for skills (if using SkillsDirectory instances)

### Properties

- `skills` - Dictionary of loaded skills (`dict[str, Skill]`)

## Skill Discovery

Skills are discovered by scanning directories for `SKILL.md` files using the `SkillsDirectory` class:

```python
from pydantic_ai_skills import SkillsDirectory

skill_dir = SkillsDirectory(path="./skills", validate=True)
all_skills = skill_dir.get_skills()

for name, skill in all_skills.items():
    print(f"{name}: {skill.metadata.description}")
```

## Type Safety

The package provides type-safe dataclasses for working with skills:

### SkillMetadata

```python
from pydantic_ai_skills import SkillMetadata

metadata = SkillMetadata(
    name="my-skill",
    description="My skill description",
    extra={"version": "1.0.0", "author": "Me"}
)
```

### Skill

```python
from pydantic_ai_skills import Skill

skill = Skill(
    name="my-skill",
    path=Path("./skills/my-skill"),
    metadata=metadata,
    content="# Instructions...",
    resources=[...],
    scripts=[...]
)
```

### SkillResource

```python
from pydantic_ai_skills import SkillResource

resource = SkillResource(
    name="reference.md",
    path=Path("./skills/my-skill/resources/reference.md"),
    content=None  # Lazy-loaded
)
```

### SkillScript

```python
from pydantic_ai_skills import SkillScript

script = SkillScript(
    name="my_script",
    path=Path("./skills/my-skill/scripts/my_script.py"),
    skill_name="my-skill"
)
```

## Security

The toolset implements security measures:

- **Path Validation**: Scripts and resources must be within the skill directory
- **No Path Traversal**: Attempts to access files outside the skill directory are blocked
- **Script Timeout**: Scripts are killed after the configured timeout
- **Safe Execution**: Scripts run in a subprocess with limited privileges

## Next Steps

- [Creating Skills](creating-skills.md) - Learn how to build skills
- [Skill Patterns](skill-patterns.md) - Common patterns and best practices
- [API Reference](api/toolset.md) - Detailed API documentation

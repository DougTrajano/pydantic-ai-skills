# Core Concepts

Understanding the key concepts behind pydantic-ai-skills will help you build better agent systems.

## Skill Structure

Skills are modular packages that extend agent capabilities. You can create them in two ways:

### File-Based Skills

A directory containing:

- `SKILL.md` - Metadata (YAML frontmatter) and instructions (required)
- `scripts/` - Optional executable Python scripts
- `resources/` - Optional additional documentation or data

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

Alternatively, define skills directly in Python using the `Skill` class with decorators for dynamic resources and scripts. This enables dependency injection and runtime configuration. See [Programmatic Skills](programmatic-skills.md) for details.

### Registry Skills

Skills can also be loaded from remote sources via **skill registries**. For example, `GitSkillsRegistry` clones a Git repository and exposes its skills. Registries support composition (filtering, prefixing, renaming, combining). See [Skill Registries](registries.md) for details.

## SKILL.md Format

Each `SKILL.md` file has **YAML frontmatter** (metadata) followed by **Markdown** (instructions).

**Minimal example:**

```yaml
---
name: my-skill
description: A brief description of what this skill does
---
```

**Required fields:**
- `name` - Unique identifier (lowercase, hyphens, ≤64 chars)
- `description` - Brief summary (≤1024 chars, appears in listings)

**Optional fields:**
```yaml
---
name: arxiv-search
description: Search arXiv for research papers
version: 1.0.0
author: Your Name
category: research
---
```

## Progressive Disclosure

The toolset implements **progressive disclosure** - exposing information only when needed:

1. **Initial**: Skill names and descriptions are added to agent's instructions via `@agent.instructions` decorator calling `get_instructions(ctx)`
2. **Loading**: Agent calls `load_skill(name)` to get full instructions when needed
3. **Resources**: Agent calls `read_skill_resource()` for additional documentation
4. **Execution**: Agent calls `run_skill_script()` to execute scripts

This approach:

Skills use **progressive disclosure** to minimize context:

1. **Discovery**: Skill names/descriptions are added to instructions via `get_instructions()`
2. **Loading**: Agent calls `load_skill(name)` for full instructions when needed
3. **Resources**: Agent calls `read_skill_resource()` for additional files
4. **Execution**: Agent calls `run_skill_script()` to execute code

This reduces token usage, enables dynamic capability discovery, and scales to many skills.
**Returns**: Formatted markdown with skill names and descriptions

**When to use**: Optional - skills are already listed in the agent's instructions via `get_instructions(ctx)`. Use only if the agent needs to re-check available skills dynamically.

### 2. load_skill(name)

Lo# The Four Tools

| Tool | Purpose |
|------|---------|
| `list_skills()` | List all available skills (usually redundant with `get_instructions()`) |
| `load_skill(name)` | Load complete instructions for a skill |
| `read_skill_resource(skill_name, resource_name)` | Read additional files (e.g., forms, reference docs) |
| `run_skill_script(skill_name, script_name, args)` | Execute Python scripts defined in the skill |covery
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
- [Implementation Patterns](patterns.md) - Common patterns and best practices
- [API Reference](api/toolset.md) - Detailed API documentation

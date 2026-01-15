# SkillsToolset API Reference

::: pydantic_ai_skills.toolset.SkillsToolset
options:
members: - **init** - get_instructions - get_skill - skills
show_source: true
heading_level: 2

## Usage Examples

### Initialize with File-Based Skills

```python
from pydantic_ai_skills import SkillsToolset

# Basic initialization
toolset = SkillsToolset(directories=["./skills"])

# Advanced initialization
toolset = SkillsToolset(
    directories=["./skills", "./shared"],
    validate=True,
    max_depth=3,
    id="my-skills"
)
```

### Initialize with Programmatic Skills

```python
from pydantic_ai import RunContext
from pydantic_ai.toolsets.skills import Skill, SkillsToolset

# Create programmatic skill
my_skill = Skill(
    name='custom-skill',
    description='Custom programmatic skill',
    content='Instructions for this skill...'
)

@my_skill.script
async def custom_action(ctx: RunContext[MyDeps]) -> str:
    """Perform a custom action."""
    return await ctx.deps.do_something()

# Initialize toolset with programmatic skill
toolset = SkillsToolset(skills=[my_skill])
```

### Mix File-Based and Programmatic Skills

```python
from pydantic_ai.toolsets.skills import Skill, SkillsToolset

# Create programmatic skills
programmatic_skill = Skill(
    name='runtime-skill',
    description='Created at runtime',
    content='Dynamic skill content...'
)

# Combine both types
toolset = SkillsToolset(
    directories=["./skills"],      # File-based skills
    skills=[programmatic_skill]    # Programmatic skills
)

print(f"Total skills: {len(toolset.skills)}")
```

### Get Skills Instructions

```python
from pydantic_ai import Agent, RunContext
from pydantic_ai_skills import SkillsToolset

toolset = SkillsToolset(directories=["./skills"])

agent = Agent(
    model='openai:gpt-5.2',
    instructions="You are a helpful assistant.",
    toolsets=[toolset]
)

@agent.instructions
async def add_skills(ctx: RunContext) -> str | None:
    """Add skills instructions to the agent's context."""
    return await toolset.get_instructions(ctx)
```

**What the instructions contain**:

- List of all available skills with their names and descriptions
- Instructions on how to use the four skill tools (`load_skill`, `read_skill_resource`, `run_skill_script`, `list_skills`)
- Best practices for progressive disclosure (load only what's needed when needed)

This enables the agent to discover and select skills without calling `list_skills()` first, following Anthropic's approach to skill exposure.

### Access Skills

```python
# Get all skills
all_skills = toolset.skills

# Get specific skill
skill = toolset.get_skill("arxiv-search")

print(f"Name: {skill.name}")
print(f"Description: {skill.metadata.description}")
print(f"Scripts: {[s.name for s in skill.scripts]}")
```

## Tools Provided

The `SkillsToolset` automatically registers four tools with agents:

### list_skills()

Lists all available skills with descriptions.

**Returns**: Formatted markdown string

**Example**:

```markdown
# Available Skills

## arxiv-search

Search arXiv for research papers (scripts: arxiv_search)

## web-research

Structured approach to web research
```

### load_skill(skill_name: str)

Loads full instructions for a specific skill.

**Parameters**:

- `skill_name` (str): Name of the skill to load

**Returns**: Full skill content including metadata and instructions

### read_skill_resource(skill_name: str, resource_name: str)

Reads a resource file from a skill.

**Parameters**:

- `skill_name` (str): Name of the skill
- `resource_name` (str): Resource filename (e.g., "REFERENCE.md")

**Returns**: Resource file content

### run_skill_script(skill_name: str, script_name: str, args: list[str] | None = None)

Executes a skill script.

**Parameters**:

- `skill_name` (str): Name of the skill
- `script_name` (str): Script name without .py extension
- `args` (list[str], optional): Command-line arguments

**Returns**: Script output (stdout and stderr)

**Raises**:

- `SkillScriptExecutionError`: If script execution fails or times out

## See Also

- [Types Reference](types.md) - Type definitions
- [Exceptions Reference](exceptions.md) - Exception classes
- [Creating Skills](../creating-skills.md) - How to create file-based skills
- [Programmatic Skills](../programmatic-skills.md) - How to create programmatic skills

# SkillsToolset API Reference

::: pydantic_ai_skills.toolset.SkillsToolset
options:
members: - **init** - get_instructions - get_skill - skills
show_source: true
heading_level: 2

## Constructor Parameters

The `SkillsToolset.__init__()` accepts the following parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `skills` | `list[Skill] \| None` | `None` | Pre-loaded Skill objects. Can be combined with `directories`. |
| `directories` | `list[str \| Path \| SkillsDirectory] \| None` | `None` | Directories or SkillsDirectory instances to discover skills from. Defaults to `["./skills"]` if neither `skills` nor `directories` provided. |
| `registries` | `list[SkillRegistry] \| None` | `None` | List of [SkillRegistry](registries.md) instances (e.g. `GitSkillsRegistry`) to load skills from. Can be combined with `skills` and `directories`. Registries have the lowest priority. |
| `validate` | `bool` | `True` | Validate skill structure during discovery. Used when creating SkillsDirectory from str/Path entries. |
| `max_depth` | `int \| None` | `3` | Maximum depth for skill discovery. `None` for unlimited depth. Used when creating SkillsDirectory from str/Path entries. |
| `id` | `str \| None` | `None` | Unique identifier for this toolset. |
| `instruction_template` | `str \| None` | `None` | Custom instruction template for skills system prompt. Must include `{skills_list}` placeholder. If None, uses default template. |

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `skills` | `dict[str, Skill]` | Dictionary of all available skills, keyed by skill name. |

### Methods

| Method | Description |
|--------|-------------|
| `get_skill(skill_name: str) -> Skill` | Retrieve a specific skill by name. Raises `SkillNotFoundError` if not found. |
| `get_instructions(ctx: RunContext[Any]) -> str` | Returns formatted system prompt with skills instructions. Used via `@agent.instructions`. |

## Usage Examples

### Initialize with File-Based Skills

```python
from pydantic_ai_skills import SkillsToolset

# Basic initialization - defaults to ./skills directory
toolset = SkillsToolset()

# Explicit single directory
toolset = SkillsToolset(directories=["./skills"])

# Multiple directories
toolset = SkillsToolset(
    directories=["./skills", "./shared", "./custom"],
    validate=True,
    max_depth=3,
    id="my-skills"
)

# Using SkillsDirectory instances directly
from pydantic_ai.toolsets.skills import SkillsDirectory

skills_dir = SkillsDirectory(
    path="./skills",
    validate=True,
    max_depth=3
)
toolset = SkillsToolset(directories=[skills_dir])
```

### Initialize with Git Registry

```python
from pydantic_ai_skills import SkillsToolset
from pydantic_ai_skills.registries import GitSkillsRegistry, GitCloneOptions

# Clone a remote Git repository and load its skills
registry = GitSkillsRegistry(
    repo_url='https://github.com/anthropics/skills',
    path='skills',
    target_dir='./anthropics-skills',
    clone_options=GitCloneOptions(depth=1, single_branch=True),
)

toolset = SkillsToolset(registries=[registry])

# Combine with local skills
toolset = SkillsToolset(
    directories=['./skills'],
    registries=[registry],
)
```

See [Skill Registries](../registries.md) for composition patterns (filtering, prefixing, combining).

### Initialize with Programmatic Skills

```python
from pydantic_ai import RunContext
from pydantic_ai.toolsets.skills import Skill, SkillsToolset

# Create a simple programmatic skill
my_skill = Skill(
    name='custom-skill',
    description='Custom programmatic skill',
    content='Instructions for this skill...'
)

# Initialize toolset with programmatic skill
toolset = SkillsToolset(skills=[my_skill])

# Use the @skill() decorator to define skills inline
skills = SkillsToolset()

@skills.skill()
def data_analyzer() -> str:
    """Analyze data from various sources."""
    return "Provide data analysis capabilities..."

@data_analyzer.resource
def get_schema() -> str:
    """Get available schema information."""
    return "## Schema\n\nAvailable columns..."

@data_analyzer.script
async def analyze(ctx: RunContext[MyDeps], query: str) -> str:
    """Run analysis query."""
    return await ctx.deps.database.execute(query)
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

# Combine both types in a single toolset
toolset = SkillsToolset(
    directories=["./skills"],        # File-based skills from directory
    skills=[programmatic_skill],     # Programmatic skills
    max_depth=3                       # Limit directory discovery depth
)

# Programmatic skills can also be added via decorator
@toolset.skill()
def extra_skill() -> str:
    return "Additional dynamically-defined skill..."

print(f"Total skills loaded: {len(toolset.skills)}")
```

### Custom Instruction Template

```python
from pydantic_ai import Agent
from pydantic_ai.toolsets.skills import SkillsToolset

custom_instructions = """\
You have specialized skills available for specific domains.

Each skill includes instructions, resources, and executable scripts.

Available skills:
{skills_list}

Use `load_skill` to explore any skill that's relevant to the user's request.
"""

toolset = SkillsToolset(
    directories=["./skills"],
    instruction_template=custom_instructions
)

agent = Agent(
    model='openai:gpt-4o',
    toolsets=[toolset]
)
```

### Use @skill() Decorator

```python
from pydantic_ai.toolsets.skills import SkillsToolset

skills = SkillsToolset(directories=["./skills"])

@skills.skill(
    name='custom-analyzer',  # Override function name
    license='Apache-2.0',
    compatibility='Python 3.10+',
    metadata={'version': '1.0.0', 'author': 'my-team'}
)
def data_analyzer() -> str:
    """Analyze data from various sources."""
    return """
# Data Analysis Skill

Use this skill to analyze datasets and generate insights.

## Instructions

Load the full skill with `load_skill` to see available resources and scripts.
"""

# Now 'data-analyzer' skill is registered and available to agents
```

### Get Skills Instructions for Agent

```python
from pydantic_ai import Agent, RunContext
from pydantic_ai_skills import SkillsToolset

toolset = SkillsToolset(directories=["./skills"])

agent = Agent(
    model='openai:gpt-4o',
    instructions="You are a helpful assistant.",
    toolsets=[toolset]
)

@agent.instructions
async def add_skills(ctx: RunContext) -> str | None:
    """Inject skills instructions into agent context."""
    return toolset.get_instructions(ctx)

# The agent will receive skill metadata in system prompt
result = agent.run_sync('Analyze the quarterly data')
```

The instructions include:
- List of available skills with descriptions
- How to use the four skill tools
- Best practices for progressive disclosure

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

### run_skill_script(skill_name: str, script_name: str, args: dict[str, Any] | None = None)

Executes a skill script with optional arguments.

**Parameters**:

- `skill_name` (str): Name of the skill
- `script_name` (str): Name of the script within the skill
- `args` (dict[str, Any], optional): Dictionary of arguments to pass to the script
  - For file-based scripts: Converted to command-line flags (e.g., `{"query": "test"}` → `--query test`)
  - For callable scripts: Passed as function arguments

**Returns**: String output from script execution

**Raises**:

- `SkillNotFoundError`: If the skill doesn't exist
- `SkillScriptNotFoundError`: If the script doesn't exist in the skill
- `SkillScriptExecutionError`: If script execution fails or times out

**Example**:

```python
# Agent calls the tool
agent.run_sync('Run the arxiv search script with query "machine learning"')

# Internally calls:
# result = await toolset.run_skill_script(
#     'arxiv-search',
#     'arxiv_search',
#     {'query': 'machine learning'}
# )
```

## Decorator: @toolset.skill()

The `@toolset.skill()` decorator enables defining skills directly on the toolset instance.

**Signature**:

```python
def skill(
    func: Callable[[], str] | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    license: str | None = None,
    compatibility: str | None = None,
    metadata: dict[str, Any] | None = None,
    resources: list[SkillResource] | None = None,
    scripts: list[SkillScript] | None = None,
) -> SkillWrapper[Any]
```

**Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `func` | `Callable[[], str]` | Function returning skill instructions/content. Used as decorator. |
| `name` | `str \| None` | Override skill name (default: normalize function name). Must match `^[a-z0-9]+(-[a-z0-9]+)*$`, max 64 chars. |
| `description` | `str \| None` | Skill description (default: function docstring). Max 1024 chars. |
| `license` | `str \| None` | License identifier (e.g., "Apache-2.0"). |
| `compatibility` | `str \| None` | Environment/dependency requirements (e.g., "Requires git, docker"). Max 500 chars. |
| `metadata` | `dict[str, Any] \| None` | Custom metadata fields (e.g., version, author, tags). |
| `resources` | `list[SkillResource] \| None` | Initial resources to attach. Can be extended with `@skill.resource`. |
| `scripts` | `list[SkillScript] \| None` | Initial scripts to attach. Can be extended with `@skill.script`. |

**Returns**: `SkillWrapper[Any]` - Decorated skill that supports `@skill.resource` and `@skill.script` decorators

**Example**:

```python
from pydantic_ai.toolsets.skills import SkillsToolset

skills = SkillsToolset()

@skills.skill(
    name='data-analyzer',
    license='MIT',
    compatibility='Python 3.10+',
    metadata={'version': '1.0.0', 'author': 'data-team'}
)
def my_analyzer() -> str:
    """Analyze and process data."""
    return "# Data Analysis Skill\n\nUse for data analysis tasks."

# Extended with resources and scripts
@my_analyzer.resource
def get_schema() -> str:
    return "## Schema\n\nDatabase schema information..."

@my_analyzer.script
async def analyze_data(query: str) -> str:
    return f"Analyzed: {query}"
```

See [Advanced Features](../advanced.md) for detailed decorator documentation.

## See Also

- [Advanced Features](../advanced.md) - Skill decorators, custom templates, dependency injection
- [Skill Registries](../registries.md) - Load skills from Git repos and remote sources
- [Types Reference](types.md) - Type definitions and data structures
- [Registries Reference](registries.md) - Registry API documentation
- [Exceptions Reference](exceptions.md) - Exception classes

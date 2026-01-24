# Advanced Features

Advanced patterns and features for sophisticated skill systems.

## Skill Decorator Pattern

### @toolset.skill() Decorator

The `@toolset.skill()` decorator enables defining skills directly on a `SkillsToolset` instance. This approach is ideal when:

- Skills are tightly coupled with your agent initialization
- You want to define skills inline without separate files
- Skills depend on runtime dependencies available in your agent

### Basic Example

```python
from pydantic_ai import Agent, RunContext
from pydantic_ai.toolsets.skills import SkillsToolset

skills = SkillsToolset()

@skills.skill()
def data_analyzer() -> str:
    """Analyze data from various sources."""
    return """
# Data Analysis Skill

Use this skill to analyze datasets, generate statistical insights, and create visualizations.

## Instructions

1. Load the skill with `load_skill`
2. Access available resources with `read_skill_resource`
3. Execute analysis scripts with `run_skill_script`

## Key Capabilities

- Statistical summaries and distributions
- Correlation and trend analysis
- Data transformation and aggregation
- Report generation
"""

agent = Agent(
    model='openai:gpt-4o',
    toolsets=[skills]
)

result = agent.run_sync('Analyze the quarterly sales data')
```

### Decorator Parameters

```python
@toolset.skill(
    name='custom-name',           # Override function name (default: normalize_skill_name(func_name))
    description='...',             # Override docstring-based description
    license='Apache-2.0',          # License information
    compatibility='Python 3.10+',  # Environment requirements
    metadata={'version': '1.0'},   # Custom metadata fields
    resources=[...],               # Initial resources
    scripts=[...]                  # Initial scripts
)
def my_skill() -> str:
    return "..."
```

#### Parameters Explained

| Parameter | Type | Required | Notes |
|-----------|------|----------|-------|
| `name` | `str` | No | Defaults to function name with underscores converted to hyphens. Must match pattern `^[a-z0-9]+(-[a-z0-9]+)*$` and be ≤64 chars. |
| `description` | `str` | No | Extracted from function docstring if not provided. Max 1024 characters. |
| `license` | `str` | No | License identifier (e.g., "Apache-2.0", "MIT"). Included in skill metadata. |
| `compatibility` | `str` | No | Environment/dependency requirements (e.g., "Requires git, docker, internet access"). Max 500 chars. |
| `metadata` | `dict` | No | Custom key-value pairs preserved in skill metadata. Useful for versioning or custom properties. |
| `resources` | `list[SkillResource]` | No | Initial resources attached to the skill. Can be extended with `@skill.resource`. |
| `scripts` | `list[SkillScript]` | No | Initial scripts attached to the skill. Can be extended with `@skill.script`. |

### Adding Resources and Scripts

The decorator returns a `SkillWrapper` that allows further decorating resources and scripts:

```python
@skills.skill()
def data_analyzer() -> str:
    return "Analyze data from various sources..."

# Add dynamic resources
@data_analyzer.resource
def get_schema() -> str:
    """Get the data schema."""
    return "## Schema\n\nColumns: id, name, value, timestamp"

@data_analyzer.resource
async def get_available_tables(ctx: RunContext[MyDeps]) -> str:
    """Get available database tables (with runtime context)."""
    tables = await ctx.deps.database.list_tables()
    return f"Available tables:\n" + "\n".join(tables)

# Add executable scripts
@data_analyzer.script
async def analyze_query(ctx: RunContext[MyDeps], query: str) -> str:
    """Execute an analysis query."""
    result = await ctx.deps.database.execute(query)
    return str(result)
```

### How Skill Names Are Derived

The decorator automatically converts function names to valid skill names:

```python
@skills.skill()
def my_data_tool() -> str:
    # Skill name: "my-data-tool"
    return "..."

@skills.skill()
def MySkill() -> str:
    # Skill name: "myskill" (lowercased, hyphens added between camelCase)
    return "..."

@skills.skill(name='custom-name')
def function_with_explicit_name() -> str:
    # Skill name: "custom-name" (uses provided name)
    return "..."
```

## Custom Instruction Templates

### Customizing Agent Instructions

By default, `SkillsToolset` injects a standard instruction template that explains the progressive disclosure pattern. You can customize this for your specific use case:

```python
from pydantic_ai import Agent
from pydantic_ai.toolsets.skills import SkillsToolset

custom_template = """\
You have access to specialized skills for domain-specific knowledge.

## How to Use Skills

Each skill contains:
- **Instructions**: Guidelines on when and how to use the skill
- **Resources**: Reference documentation and data
- **Scripts**: Executable functions for specific tasks

Always follow this workflow:
1. Call `list_skills` to see available skills
2. Call `load_skill` to understand the skill's capabilities
3. Use `read_skill_resource` for specific reference material
4. Execute scripts with `run_skill_script` when needed

## Available Skills

{skills_list}

## Tips

- Load skills only when relevant to the user's request
- Consult resources before calling scripts
- Check skill descriptions to understand their scope
"""

toolset = SkillsToolset(
    directories=['./skills'],
    instruction_template=custom_template
)

agent = Agent(
    model='openai:gpt-4o',
    toolsets=[toolset]
)
```

### Template Variables

Your custom template **must include** the `{skills_list}` placeholder, which is automatically replaced with formatted skill information:

```
{skills_list}  # Replaced with XML-formatted list of available skills
```

The skills list includes:
- Skill name, description, and URI
- List of available resources
- List of available scripts
- Full skill instructions

### Default Template

If you don't provide a custom template, the default is used:

```python
DEFAULT_INSTRUCTION_TEMPLATE = """\
Here is a list of skills that contain domain specific knowledge on a variety of topics.
Each skill comes with a description of the topic and instructions on how to use it.
When a user asks you to perform a task that falls within the domain of a skill, use the `load_skill` tool to acquire the full instructions.

<available_skills>
{skills_list}
</available_skills>

Use progressive disclosure: load only what you need, when you need it:

- First, use `load_skill` tool to read the full skill instructions
- To read additional resources within a skill, use `read_skill_resource` tool
- To execute skill scripts, use `run_skill_script` tool
"""
```

## Dependency Injection via RunContext

### Using RunContext in Resources and Scripts

Both `@skill.resource` and `@skill.script` decorated functions can optionally accept a `RunContext[DepsType]` parameter to access dependencies. The toolset automatically detects this by inspecting the function signature.

### Example: Database Access

```python
from typing import TypedDict
from pydantic_ai import RunContext
from pydantic_ai.toolsets.skills import SkillsToolset

class MyDeps(TypedDict):
    """Dependencies available in RunContext."""
    database: Database
    cache: Cache
    logger: Logger

skills = SkillsToolset()

@skills.skill()
def database_skill() -> str:
    return "Query and analyze database content"

# Resource with context - accesses the database dependency
@database_skill.resource
async def get_current_schema(ctx: RunContext[MyDeps]) -> str:
    """Fetch current schema from the database."""
    schema = await ctx.deps.database.get_schema()
    return f"## Current Schema\n{schema}"

# Script with context - executes queries with database access
@database_skill.script
async def execute_query(
    ctx: RunContext[MyDeps],
    query: str,
    limit: int = 100
) -> str:
    """Execute a SQL query against the database."""
    result = await ctx.deps.database.query(query, limit=limit)

    # Log the execution
    await ctx.deps.logger.info(f"Executed query: {query[:50]}...")

    # Cache the result
    cache_key = f"query:{query}"
    await ctx.deps.cache.set(cache_key, result, ttl=3600)

    return str(result)
```

### Type-Safe Dependency Access

The `RunContext` is generic over your dependency type, enabling type-safe access:

```python
# When passing dependencies to your agent
from pydantic_ai import Agent

agent = Agent(
    model='openai:gpt-4o',
    deps=MyDeps(
        database=my_database,
        cache=my_cache,
        logger=my_logger
    ),
    toolsets=[skills]
)

result = agent.run_sync('Query the user database', deps=agent.deps)
```

### Signature Detection

The decorator automatically determines if a function takes context:

```python
# ✓ Automatically detected as needing context
@skill.resource
async def needs_context(ctx: RunContext[MyDeps]) -> str:
    return str(ctx.deps)

# ✓ Correctly detected as not needing context
@skill.resource
def static_resource() -> str:
    return "Static content"

# ✓ Works with sync functions too
@skill.script
def sync_script(ctx: RunContext[MyDeps]) -> str:
    return str(ctx.deps)
```

## Custom Script Executors

### Creating Custom Executors

For advanced use cases, you can provide custom script executors that handle script execution differently than the built-in local executor. This enables:

- Remote execution (cloud functions, etc.)
- Sandboxing or containerized execution
- Custom security policies
- Integration with external systems

### Executor Interface

Custom executors must implement the `SkillScriptExecutor` protocol:

```python
from typing import Protocol, Any

class SkillScriptExecutor(Protocol):
    """Protocol for custom script execution."""

    async def execute(
        self,
        script: SkillScript,
        args: dict[str, Any] | None = None
    ) -> str:
        """Execute a skill script.

        Args:
            script: The script to execute
            args: Optional arguments to pass to the script

        Returns:
            String output from the script
        """
        ...
```

### Example: Remote Execution

```python
from pydantic_ai.toolsets.skills import SkillScript, CallableSkillScriptExecutor
import httpx

class RemoteExecutor:
    """Execute scripts on a remote server."""

    def __init__(self, server_url: str):
        self.server_url = server_url

    async def execute(self, script: SkillScript, args: dict | None = None) -> str:
        """Send script execution request to remote server."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.server_url}/execute",
                json={
                    "script_name": script.name,
                    "args": args or {}
                }
            )
            return response.text

# Use in custom script definitions
from pydantic_ai.toolsets.skills import SkillScript

remote_executor = RemoteExecutor("https://api.example.com")

script = SkillScript(
    name='remote-analysis',
    description='Run analysis on remote server',
    function=None,
    executor=remote_executor  # Custom executor
)
```

### Example: Sandboxed Execution

```python
import subprocess
from pathlib import Path

class SandboxedExecutor:
    """Execute Python scripts in isolated sandboxes."""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    async def execute(self, script: SkillScript, args: dict | None = None) -> str:
        """Execute script in sandbox."""
        # Convert args to environment variables
        env = {f"ARG_{k.upper()}": str(v) for k, v in (args or {}).items()}

        try:
            result = subprocess.run(
                ["sandbox", "--timeout", str(self.timeout), script.name],
                capture_output=True,
                text=True,
                env={**os.environ, **env},
                timeout=self.timeout + 5
            )
            return result.stdout or result.stderr
        except subprocess.TimeoutExpired:
            return f"ERROR: Script execution timed out after {self.timeout}s"
```

## Metadata Management

### Custom Metadata Fields

You can attach arbitrary metadata to skills for custom use cases:

```python
@skills.skill(
    metadata={
        'version': '1.0.0',
        'author': 'data-team',
        'tags': ['analytics', 'database', 'reporting'],
        'supported_formats': ['csv', 'json', 'parquet'],
        'min_pydantic_ai_version': '0.1.0'
    }
)
def advanced_analytics() -> str:
    return "Advanced analytics skill..."
```

### Accessing Metadata

Metadata is preserved in the `Skill` object and accessible via:

```python
skill = toolset.get_skill('advanced-analytics')

# Access via skill attributes
if hasattr(skill, 'metadata') and skill.metadata:
    version = skill.metadata.get('version', '0.0.0')
    tags = skill.metadata.get('tags', [])
```

### Recommended Metadata Fields

Common metadata patterns:

| Field | Type | Purpose |
|-------|------|---------|
| `version` | `str` | Semantic version for the skill |
| `author` | `str` | Team or person who maintains the skill |
| `tags` | `list[str]` | Categorization tags for discovery |
| `requires` | `dict[str, str]` | External dependencies and versions |
| `deprecated` | `bool` | Mark skills as deprecated |
| `deprecation_message` | `str` | Explanation and alternative if deprecated |
| `breaking_changes` | `str` | Document breaking changes in versions |
| `supported_models` | `list[str]` | Models this skill works best with |

## Mixed Skill Scenarios

### Combining Programmatic and File-Based Skills

The real power comes when combining both approaches:

```python
from pydantic_ai import Agent
from pydantic_ai.toolsets.skills import SkillsToolset, Skill

# Create programmatic skills
skills = SkillsToolset(
    directories=['./skills', './custom-skills'],  # File-based skills
    max_depth=3  # Limit discovery depth
)

# Add decorator-defined skills to the same toolset
@skills.skill()
def runtime_analyzer() -> str:
    return "Analyze runtime metrics and performance data"

@runtime_analyzer.resource
async def get_metrics(ctx: RunContext[MyDeps]) -> str:
    metrics = await ctx.deps.monitoring.get_current()
    return f"Current metrics:\n{metrics}"

# Now agent has access to both:
# - File-based skills from ./skills and ./custom-skills
# - Programmatically defined runtime_analyzer skill
agent = Agent(
    model='openai:gpt-4o',
    toolsets=[skills]
)
```

### Skill Precedence and Conflicts

When multiple skills have the same name:

1. **Programmatic skills** (defined via `@decorator`) take precedence
2. **File-based skills** are loaded in directory order
3. **Duplicate detection**: If a duplicate is detected, a warning is issued and the new skill is registered

```python
# This will warn if a skill named 'data-analyzer' exists in ./skills
@skills.skill(name='data-analyzer')
def conflicting_skill() -> str:
    return "..."
```

### Dynamic Skill Registration

You can programmatically register skills after toolset creation (though typically skills are defined at initialization):

```python
from pydantic_ai.toolsets.skills import Skill

# Create toolset
toolset = SkillsToolset()

# Register a new programmatic skill
new_skill = Skill(
    name='dynamically-added',
    description='Added after initialization',
    content='This skill was registered dynamically'
)
toolset._register_skill(new_skill)  # Internal method, use with caution
```

> **Note**: Direct manipulation of internal `_register_skill()` is not recommended for production code. Define skills at initialization time for better clarity and maintainability.

## See Also

- [Programmatic Skills](./programmatic-skills.md) - Detailed guide to programmatic skill creation
- [API Reference - SkillsToolset](./api/toolset.md) - Complete API documentation
- [Implementation Patterns](./patterns.md) - Common design patterns and best practices

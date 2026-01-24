# Programmatic Skills

Create skills directly in Python code for dynamic capabilities that require runtime dependencies, custom logic, or configuration-based generation.

## Overview

Programmatic skills let you:

- Create skills using Python dataclasses instead of files
- Add static resources with inline content
- Register dynamic resources via `@skill.resource` decorator
- Register executable scripts via `@skill.script` decorator
- Access dependencies through `RunContext`

## Creating a Basic Programmatic Skill

```python
from pydantic_ai.toolsets.skills import Skill, SkillResource, SkillsToolset

# Create a skill with static resources
my_skill = Skill(
    name='my-skill',
    description='A programmatic skill example',
    content="""Use this skill for example tasks.

## Instructions

1. Call the `get_info` resource to understand available data
2. Use `process_data` script with your query
""",
    resources=[
        SkillResource(
            name='reference',
            content='## Reference\n\nStatic reference documentation here...'
        )
    ]
)

# Initialize toolset with the programmatic skill
skills_toolset = SkillsToolset(skills=[my_skill])
```

## Adding Dynamic Resources

Use the `@skill.resource` decorator to create resources that generate content dynamically:

```python
from pydantic_ai import RunContext
from pydantic_ai.toolsets.skills import Skill

my_skill = Skill(
    name='database-skill',
    description='Database query and analysis',
    content='Use this skill for database operations.'
)

@my_skill.resource
def get_schema() -> str:
    """Get current database schema."""
    return "## Schema\n\nTables: users, orders, products"

@my_skill.resource
async def get_connection_info(ctx: RunContext[MyDeps]) -> str:
    """Get database connection information from dependencies."""
    db_info = await ctx.deps.get_db_info()
    return f"Connected to: {db_info}"
```

### Resource Features

- **Optional RunContext**: Resources can optionally take `RunContext[DepsType]` as first argument
- **Auto-detection**: The `takes_ctx` parameter is automatically detected from function signature
- **Async Support**: Resources can be sync or async functions
- **Type Safety**: Function signatures are analyzed for proper parameter types

## Adding Executable Scripts

Use the `@skill.script` decorator to create executable scripts:

```python
from pydantic_ai import RunContext
from pydantic_ai.toolsets.skills import Skill

my_skill = Skill(
    name='data-processor',
    description='Process and analyze data',
    content='Use scripts to load and query data.'
)

@my_skill.script
async def load_dataset(ctx: RunContext[MyDeps]) -> str:
    """Load the dataset into memory."""
    await ctx.deps.load_data()
    return 'Dataset loaded successfully'

@my_skill.script
async def run_query(ctx: RunContext[MyDeps], query: str, limit: int = 10) -> str:
    """Execute a query on the loaded dataset.

    Args:
        query: SQL query string to execute
        limit: Maximum number of results to return
    """
    results = await ctx.deps.execute_query(query, limit)
    return format_results(results)
```

### Script Features

- **Named Arguments**: Scripts accept named parameters matching function signature
- **Default Values**: Parameters can have default values
- **Type Annotations**: Use type hints for better validation
- **Docstrings**: Function docstrings become script descriptions for the LLM
- **RunContext Access**: First parameter can be `RunContext[DepsType]` for dependencies

## Complete Example: HR Analytics Agent

Here's a complete example showing all features:

```python
import datetime
import sqlite3
from dataclasses import dataclass, field

import datasets
from pydantic_ai import Agent, RunContext
from pydantic_ai.toolsets.skills import Skill, SkillResource, SkillsToolset

@dataclass
class AnalystDeps:
    """Dependencies for the HR analytics agent."""
    hf_dataset_name: str = 'dougtrajano/hr-synthetic-database'
    hf_dataset_subsets: list[str] = field(
        default_factory=lambda: ['business_units', 'departments', 'jobs', 'employees']
    )
    db: sqlite3.Connection | None = field(default=None)

    def get_db_tables(self) -> list[str]:
        """Get list of tables in database."""
        if self.db is None:
            return []
        cursor = self.db.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        return [row[0] for row in cursor.fetchall()]

# Static resource with schema documentation
schema_resource = SkillResource(
    name='table-schemas',
    uri='table-schemas.md',
    content="""## Database Schema

### Business Units
- `id` (string): Unique identifier
- `name` (string): Business unit name
- `director_job_id` (string): Reference to director's job

### Departments
- `id` (string): Unique identifier
- `name` (string): Department name
- `manager_job_id` (string): Reference to manager
- `business_unit_id` (string): Foreign key to business_units

### Jobs
- `id` (string): Unique identifier
- `name` (string): Job title
- `job_level` (string): Entry, Mid, Senior, Executive
- `job_family` (string): Engineering, Sales, etc.

### Employees
- `id` (string): Unique identifier
- `job_id` (string): Foreign key to jobs
- `first_name` / `last_name` (string): Employee name
- `birth_date` (string): YYYY-MM-DD format
"""
)

# Create skill with metadata and static resources
hr_skill = Skill(
    name='hr-analytics-skill',
    description='HR analytics with employee, department, and job data',
    content="""Use this skill for HR data analysis.

**Workflow:**
1. Call `load_dataset` script to initialize database
2. Use `get_context` resource for dataset overview
3. Reference `table-schemas` resource for field definitions
4. Execute `run_query` script with SQL to analyze data
""",
    resources=[schema_resource]
)

# Add dynamic resource
@hr_skill.resource
def get_context() -> str:
    """Provide high-level context about the dataset."""
    return (
        'The HR dataset has 4 tables: business_units, departments, '
        'jobs, and employees. Tables are linked via foreign keys.'
    )

# Add scripts with RunContext access
@hr_skill.script
async def load_dataset(ctx: RunContext[AnalystDeps]) -> str:
    """Load HuggingFace dataset into in-memory SQLite database."""
    if ctx.deps.db is None:
        ctx.deps.db = sqlite3.connect(':memory:', check_same_thread=False)

    loaded_tables = []
    for subset in ctx.deps.hf_dataset_subsets:
        if subset not in ctx.deps.get_db_tables():
            dataset = datasets.load_dataset(
                ctx.deps.hf_dataset_name,
                name=subset,
                split='train'
            )
            df = dataset.to_pandas()
            df.to_sql(subset, ctx.deps.db, if_exists='replace', index=False)
            loaded_tables.append(subset)

    if loaded_tables:
        return f'Loaded tables: {", ".join(loaded_tables)}'
    return 'Dataset already loaded'

@hr_skill.script
async def run_query(ctx: RunContext[AnalystDeps], query: str) -> str:
    """Execute SQL query on the HR dataset.

    Args:
        query: SQL query string (use table names: business_units,
               departments, jobs, employees)
    """
    if ctx.deps.db is None:
        return 'Error: Dataset not loaded. Run load_dataset first.'

    try:
        cursor = ctx.deps.db.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]

        if not rows:
            return 'Query executed. No rows returned.'

        # Format as table
        col_widths = [
            max(len(str(col)), max(len(str(row[i])) for row in rows))
            for i, col in enumerate(columns)
        ]
        header = ' | '.join(col.ljust(col_widths[i]) for i, col in enumerate(columns))
        separator = '-+-'.join('-' * width for width in col_widths)
        result_lines = [header, separator]

        for row in rows:
            result_lines.append(
                ' | '.join(str(item).ljust(col_widths[i]) for i, item in enumerate(row))
            )

        return '\n'.join(result_lines)

    except sqlite3.Error as e:
        return f'SQL Error: {e}'

# Create toolset and agent
skills_toolset = SkillsToolset(skills=[hr_skill])

agent = Agent(
    model='openai:gpt-4o',
    deps_type=AnalystDeps,
    instructions='You are an expert HR data analyst.',
    toolsets=[skills_toolset]
)

@agent.instructions
async def add_skills(ctx: RunContext) -> str | None:
    """Inject skill instructions via progressive disclosure."""
    return await skills_toolset.get_instructions(ctx)

@agent.instructions
def add_today_date() -> str:
    """Provide current date context."""
    return f'Today is {datetime.datetime.now().strftime("%B %d, %Y")}.'

# Run the agent
result = await agent.run(
    "What is the average salary by department?",
    deps=AnalystDeps()
)
print(result.output)
```

## Mixing File-Based and Programmatic Skills

You can combine both approaches in the same toolset:

```python
from pydantic_ai.toolsets.skills import Skill, SkillsToolset

# Programmatic skill
my_skill = Skill(
    name='programmatic-skill',
    description='Created in code',
    content='Instructions here...'
)

@my_skill.script
async def my_script(ctx: RunContext[MyDeps]) -> str:
    return 'Script output'

# Mix with file-based skills
skills_toolset = SkillsToolset(
    directories=["./skills"],  # File-based skills
    skills=[my_skill]          # Programmatic skills
)
```

## Implementation Details

### Resource and Script Execution

When the agent calls a resource or script:

1. **Function Schema Generation**: On registration, Pydantic AI analyzes the function signature to generate a JSON schema
2. **RunContext Detection**: The system auto-detects if the function takes `RunContext` as first parameter
3. **Parameter Validation**: Arguments are validated against the function schema
4. **Execution**: The function is called with validated arguments and optional context
5. **Return Handling**: Return values can be any type (str, dict, list, etc.)

### Type Safety

Programmatic skills leverage Pydantic AI's type-safe function schema generation:

```python
from pydantic_ai import RunContext
from pydantic_ai.toolsets.skills import Skill

my_skill = Skill(name='typed-skill', description='Type-safe skill', content='...')

@my_skill.script
async def typed_script(
    ctx: RunContext[MyDeps],
    query: str,           # Required string parameter
    limit: int = 10,      # Optional with default
    verbose: bool = False # Optional with default
) -> dict[str, Any]:      # Return type annotation
    """Execute a typed query.

    Args:
        query: Search query string
        limit: Maximum results to return
        verbose: Include detailed output
    """
    results = await ctx.deps.search(query, limit)
    return {'results': results, 'count': len(results)}
```

The function signature becomes the schema, ensuring:

- Required parameters are validated
- Default values are respected
- Type annotations guide validation
- Docstrings provide descriptions

### Custom Decorators

You can customize resource and script registration:

```python
@my_skill.resource(
    name='custom-name',           # Override function name
    description='Custom desc',    # Override docstring
    takes_ctx=True,               # Explicitly set RunContext usage
    docstring_format='google'     # Specify docstring style
)
def my_resource(ctx: RunContext[MyDeps]) -> str:
    return 'Custom resource'

@my_skill.script(
    name='custom-script',
    description='Custom script description'
)
async def my_script(ctx: RunContext[MyDeps], arg: str) -> str:
    return f'Processed: {arg}'
```

## Advanced: Using @toolset.skill() Decorator

For concise skill definition directly on a `SkillsToolset`, use the `@toolset.skill()` decorator:

```python
from pydantic_ai import Agent, RunContext
from pydantic_ai.toolsets.skills import SkillsToolset

skills = SkillsToolset()

@skills.skill(
    name='analytics',
    license='MIT',
    metadata={'version': '1.0.0'}
)
def analytics_skill() -> str:
    """Analyze application data."""
    return """# Analytics Skill

Provides analytics and reporting capabilities."""

# Add resources and scripts
@analytics_skill.resource
async def metrics(ctx: RunContext[AppDeps]) -> str:
    """Current system metrics."""
    return await ctx.deps.get_metrics()

@analytics_skill.script
async def report(ctx: RunContext[AppDeps], period: str = 'week') -> str:
    """Generate report for period."""
    return await ctx.deps.database.generate_report(period)

# Create agent with decorator-defined skill
agent = Agent(
    model='openai:gpt-4o',
    toolsets=[skills],
    deps=AppDeps(...)
)
```

See [Advanced Features](advanced.md) for full decorator documentation.

## Mixing Skill Types

Combine file-based and programmatic skills in a single toolset:

```python
from pydantic_ai.toolsets.skills import SkillsToolset

skills = SkillsToolset(directories=['./skills'])

@skills.skill()
def runtime_config() -> str:
    return "Access runtime configuration"

@runtime_config.resource
async def env_info(ctx: RunContext[AppDeps]) -> str:
    return f"Environment: {ctx.deps.environment}"

agent = Agent(model='openai:gpt-4o', toolsets=[skills])
```

## Parameter Types for Resources and Scripts

### Simple Typed Parameters

```python
@skill.resource
def get_config(setting: str) -> str:
    """Get configuration value."""
    return f"Value: {config[setting]}"

@skill.script
def calculator(expression: str) -> str:
    """Calculate expression using Python's numexpr library.

    Expression should be a single line mathematical expression
    that solves the problem.

    Examples:
        "37593 * 67" for "37593 times 67"
        "37593**(1/5)" for "37593^(1/5)"
    """
    import math
    import numexpr

    local_dict = {'pi': math.pi, 'e': math.e}
    return str(
        numexpr.evaluate(
            expression.strip(),
            global_dict={},  # restrict access to globals
            local_dict=local_dict,  # add common mathematical functions
        )
    )
```

### With RunContext and Multiple Parameters

```python
@skill.resource
async def fetch_data(
    ctx: RunContext[AppDeps],
    dataset: str,
    filters: dict | None = None
) -> str:
    """Fetch data with optional filters."""
    return await ctx.deps.database.fetch(dataset, filters)
```

## Best Practices

### Resource Guidelines

- Use resources for **context and documentation** that agents need to understand capabilities
- Keep resources **focused and concise** - return only what's needed
- Make resources **idempotent** - safe to call multiple times
- Use **clear names** that describe what the resource provides
- Document parameters in docstrings for LLM understanding

### Script Guidelines

- Use scripts for **actions and computations** that transform data or state
- **Validate inputs** and provide clear error messages
- Keep scripts **stateless** when possible - prefer passing data via dependencies
- Use **meaningful return values** - structured data or formatted text
- Document **parameters clearly** in docstrings for better LLM understanding

### Dependency Management

- Access dependencies via `ctx.deps` in resources and scripts
- Keep dependencies **minimal and focused** for the skill's purpose
- Consider **lazy loading** expensive resources (databases, large datasets)
- Use TypedDict for dependency type safety

### Testing Programmatic Skills

Test resources and scripts independently:

```python
import pytest
from pydantic_ai import RunContext
from pydantic_ai.toolsets.skills import Skill

@pytest.fixture
def skill():
    skill = Skill(name='test-skill', description='Test', content='Test skill')

    @skill.resource
    def get_data() -> str:
        return 'test data'

    @skill.script
    async def process(ctx: RunContext[MyDeps], value: str) -> str:
        return f'processed: {value}'

    return skill

def test_resource(skill):
    resource = skill.resources[0]
    result = resource.function()
    assert result == 'test data'

@pytest.mark.asyncio
async def test_script(skill):
    script = skill.scripts[0]
    ctx = create_mock_context(MyDeps())
    result = await script.function(ctx, 'test')
    assert result == 'processed: test'
```

## When to Use Which Approach

### Use Programmatic Skills When You Need:

- **Dynamic Content**: Generate resources based on runtime state
- **Dependency Access**: Leverage shared dependencies (databases, APIs)
- **Type Safety**: IDE autocomplete and type checking
- **Complex Logic**: Sophisticated algorithms in Python
- **Direct Testing**: Unit test resources and scripts

### Use File-Based Skills When You Need:

- **Simplicity**: Quick creation without code
- **Portability**: Share skills as standalone directories
- **Version Control**: Track instruction changes easily
- **Non-Python Scripts**: Execute scripts in other languages
- **Separation**: Keep instructions separate from application code

### Use Decorator Pattern (@toolset.skill()) When You Need:

- **Inline Definition**: Define skills at agent initialization
- **Runtime Generation**: Create skills based on configuration
- **Conciseness**: Minimal boilerplate for simple skills
- **Integrated Approach**: Skills bundled with agent logic

## Advantages Over File-Based Skills

**Use programmatic skills when you need:**

- **Dynamic Content**: Generate resources based on runtime state
- **Dependency Access**: Leverage shared dependencies (databases, APIs)
- **Type Safety**: Benefit from IDE autocomplete and type checking
- **Complex Logic**: Implement sophisticated algorithms in Python
- **Testing**: Unit test resources and scripts directly

**Use file-based skills when you need:**

- **Simplicity**: Quick creation without Python code
- **Portability**: Share skills as standalone directories
- **Version Control**: Track changes to instruction documents easily
- **Non-Python Scripts**: Execute scripts in other languages
- **Separation**: Keep instructions separate from application code

## See Also

- [Creating Skills](creating-skills.md) - File-based skill creation
- [Advanced Features](advanced.md) - Decorator patterns and dependency injection
- [Implementation Patterns](patterns.md) - Common design patterns
- [API Reference](api/types.md) - Detailed API documentation for `Skill`, `SkillResource`, and `SkillScript`
- [Examples](https://github.com/dougtrajano/pydantic-ai-skills/tree/main/examples) - More examples in the repository

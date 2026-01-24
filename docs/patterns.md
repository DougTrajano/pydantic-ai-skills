# Implementation Patterns

Common design patterns and best practices for skill systems.

## Skill Selection Patterns

### When to Use File-Based Skills

Best for:
- **Large, stable skills** shared across projects
- **Public/open-source skills**
- **Complex resource files** (forms, templates, docs)
- **Team collaboration** with centralized organization

```python
from pydantic_ai import Agent
from pydantic_ai.toolsets.skills import SkillsToolset

# File-based approach: organize skills in directory structure
# ./skills/
#   ├── data-analysis/
#   │   ├── SKILL.md
#   │   ├── reference.md
#   │   └── scripts/
#   │       └── analyze.py
#   └── web-research/
#       ├── SKILL.md
#       └── scripts/

toolset = SkillsToolset(directories=['./skills'])
agent = Agent(model='openai:gpt-4o', toolsets=[toolset])
```

### When to Use Programmatic Skills

Best for:
- **Runtime-generated skills** based on configuration
- **Skills requiring runtime dependencies** (databases, APIs)
- **Dynamic resource generation** that changes per session
- **Application-specific skills** tightly coupled with logic

```python
from pydantic_ai import RunContext
from pydantic_ai.toolsets.skills import SkillsToolset

class MyDeps:
    database: Database
    config: Config

skills = SkillsToolset()

@skills.skill()
def database_analysis() -> str:
    """Analyze data in database."""
    return "Use database resources and scripts to analyze data"

@database_analysis.resource
async def get_schema(ctx: RunContext[MyDeps]) -> str:
    """Get schema from actual database."""
    schema = await ctx.deps.database.get_schema()
    return f"## Current Schema\n{schema}"

agent = Agent(
    model='openai:gpt-4o',
    toolsets=[skills],
    deps=MyDeps(database=my_db, config=my_config)
)
```

### Mixed Approach

Combine both for flexibility:

```python
from pydantic_ai.toolsets.skills import SkillsToolset

# Mix file-based and programmatic skills
toolset = SkillsToolset(
    directories=['./skills'],              # Stable, reusable skills
    max_depth=2                            # Reasonable discovery depth
)

# Add runtime-specific skills
@toolset.skill(
    name='runtime-monitor',
    metadata={'version': '1.0.0'}
)
def monitoring() -> str:
    return "Monitor application runtime metrics"

@monitoring.resource
async def get_metrics(ctx: RunContext[MyDeps]) -> str:
    metrics = await ctx.deps.monitoring.current_metrics()
    return f"## Metrics\n{metrics}"

agent = Agent(model='openai:gpt-4o', toolsets=[toolset])
```

## Resource Parameter Patterns

### Static Resources

Use for reference documentation and fixed content:

```python
from pydantic_ai.toolsets.skills import Skill, SkillResource

skill = Skill(
    name='reference-skill',
    description='Provide reference documentation',
    content='Main instructions...',
    resources=[
        SkillResource(
            name='api-reference',
            description='Complete API reference',
            content='''
## API Reference

### GET /users
Retrieve all users...

### POST /users
Create a new user...
'''
        ),
        SkillResource(
            name='examples',
            description='Code examples',
            content='''
## Examples

```python
# Example 1: Basic usage
client = APIClient()
users = client.get_users()
```
'''
        )
    ]
)
```

### Dynamic Resources with Context

Use for resources that depend on runtime state:

```python
from typing import TypedDict
from pydantic_ai import RunContext
from pydantic_ai.toolsets.skills import SkillsToolset

class MyDeps(TypedDict):
    database: Database
    cache: Cache

skills = SkillsToolset()

@skills.skill()
def data_skill() -> str:
    return "Database and cache management"

# Resource that fetches current schema
@data_skill.resource
async def get_current_schema(ctx: RunContext[MyDeps]) -> str:
    """Get latest schema from database."""
    schema = await ctx.deps.database.get_schema()
    # Could also cache this
    await ctx.deps.cache.set('schema', schema, ttl=3600)
    return f"## Current Schema\n{schema}"

# Resource that lists available tables
@data_skill.resource
async def get_tables(ctx: RunContext[MyDeps]) -> str:
    """Get available tables."""
    tables = await ctx.deps.database.list_tables()
    return "## Available Tables\n" + "\n".join(f"- {t}" for t in tables)
```

### Parameterized Resources

Resources can accept parameters for dynamic content:

```python
from pydantic_ai.toolsets.skills import SkillsToolset

skills = SkillsToolset()

@skills.skill()
def query_skill() -> str:
    return "Execute database queries"

@query_skill.resource
def documentation(topic: str = "general") -> str:
    """Get documentation for a topic."""
    docs = {
        "general": "General query documentation...",
        "aggregation": "Aggregation query documentation...",
        "joins": "Join query documentation..."
    }
    return docs.get(topic, "Topic not found")
```

## Script Execution Patterns

### Simple Synchronous Scripts

For simple, stateless operations:

```python
from pydantic_ai.toolsets.skills import SkillsToolset

skills = SkillsToolset()

@skills.skill()
def text_processing() -> str:
    return "Process text data"

@text_processing.script
def count_words(text: str) -> str:
    """Count words in text."""
    words = len(text.split())
    return f"Word count: {words}"

@text_processing.script
def reverse_text(text: str) -> str:
    """Reverse text."""
    return text[::-1]
```

### Asynchronous Scripts with Context

For scripts requiring dependencies:

```python
from pydantic_ai import RunContext
from pydantic_ai.toolsets.skills import SkillsToolset

class MyDeps:
    database: Database
    logger: Logger

skills = SkillsToolset()

@skills.skill()
def analytics() -> str:
    return "Perform data analytics"

@analytics.script
async def analyze_user_data(
    ctx: RunContext[MyDeps],
    user_id: int,
    metric: str = "sales"
) -> str:
    """Analyze user data by metric."""
    # Access dependencies via context
    await ctx.deps.logger.info(f"Analyzing user {user_id}")

    data = await ctx.deps.database.query(f"""
        SELECT {metric} FROM users WHERE id = ?
    """, (user_id,))

    result = sum(data)
    await ctx.deps.logger.info(f"Analysis complete: {result}")

    return f"Analysis result: {result}"
```

### Chaining Scripts

Design scripts that can be composed:

```python
@analytics.script
async def prepare_data(ctx: RunContext[MyDeps], dataset: str) -> str:
    """Prepare raw data for analysis."""
    raw = await ctx.deps.database.fetch_raw(dataset)
    cleaned = await ctx.deps.database.clean(raw)
    return f"Prepared {len(cleaned)} records"

@analytics.script
async def run_analysis(ctx: RunContext[MyDeps], dataset: str) -> str:
    """Run analysis on prepared data."""
    # In real usage, agent would call prepare_data first
    prepared = await ctx.deps.database.load_prepared(dataset)
    results = analyze(prepared)
    return format_results(results)

@analytics.script
async def export_results(ctx: RunContext[MyDeps], dataset: str, format: str) -> str:
    """Export analysis results."""
    results = await ctx.deps.database.load_results(dataset)

    if format == "json":
        output = json.dumps(results)
    elif format == "csv":
        output = convert_to_csv(results)
    else:
        return f"Unknown format: {format}"

    return output
```

## Error Handling

### Catching Skill Errors

```python
from pydantic_ai.toolsets.skills import SkillsToolset
from pydantic_ai_skills import (
    SkillNotFoundError,
    SkillResourceNotFoundError,
    SkillScriptNotFoundError,
    SkillScriptExecutionError
)

toolset = SkillsToolset(directories=['./skills'])

# Handle missing skills
try:
    skill = toolset.get_skill('non-existent')
except SkillNotFoundError as e:
    print(f"Skill not found: {e}")

# Handle missing resources/scripts in tools
try:
    resource = toolset._find_skill_resource(skill, 'unknown-resource')
    if resource is None:
        raise SkillResourceNotFoundError(...)
except SkillResourceNotFoundError as e:
    print(f"Resource not found: {e}")
```

### Graceful Degradation

```python
from pydantic_ai import Agent, RunContext
from pydantic_ai.toolsets.skills import SkillsToolset
from pydantic_ai_skills import SkillNotFoundError

toolset = SkillsToolset(directories=['./skills'])

agent = Agent(model='openai:gpt-4o', toolsets=[toolset])

@agent.tool
async def safe_load_skill(ctx: RunContext, skill_name: str) -> str:
    """Load skill with graceful fallback."""
    try:
        skill = toolset.get_skill(skill_name)
        return f"Loaded {skill_name}: {skill.description}"
    except SkillNotFoundError:
        available = list(toolset.skills.keys())
        return f"Skill '{skill_name}' not found. Available: {available}"

result = agent.run_sync('Use the arxiv-search skill or let me know what skills are available')
```

### Timeout Handling

For long-running scripts:

```python
from pydantic_ai import RunContext
from pydantic_ai.toolsets.skills import SkillsToolset
from pydantic_ai_skills import SkillScriptExecutionError

class MyDeps:
    database: Database

skills = SkillsToolset()

@skills.skill()
def long_running() -> str:
    return "Execute long-running operations"

@long_running.script
async def expensive_query(
    ctx: RunContext[MyDeps],
    query: str
) -> str:
    """Execute expensive database query.

    Note: This script has a default 30-second timeout.
    For longer operations, increase timeout or break into chunks.
    """
    try:
        result = await asyncio.wait_for(
            ctx.deps.database.execute_complex(query),
            timeout=25  # Leave 5s buffer
        )
        return str(result)
    except asyncio.TimeoutError:
        return "ERROR: Query exceeded time limit. Try with filters or smaller dataset."
```

## Dependency Management

### Structured Dependency Types

Use TypedDict for clear dependency contracts:

```python
from typing import TypedDict
from pydantic_ai import Agent, RunContext
from pydantic_ai.toolsets.skills import SkillsToolset

class MyDeps(TypedDict):
    """Dependencies available to skills."""
    database: Database
    cache: Cache
    logger: Logger
    config: AppConfig

skills = SkillsToolset()

@skills.skill()
def db_skill() -> str:
    return "Database operations"

@db_skill.resource
async def get_status(ctx: RunContext[MyDeps]) -> str:
    """Get database status with full type hints."""
    # Type checker knows db_skill.database is Database
    status = await ctx.deps.database.health_check()

    # Log the check
    await ctx.deps.logger.info(f"Health check: {status}")

    return f"Database status: {status}"

# Initialize agent with deps
agent = Agent(
    model='openai:gpt-4o',
    toolsets=[skills],
    deps=MyDeps(
        database=my_database,
        cache=my_cache,
        logger=my_logger,
        config=app_config
    )
)
```

### Optional Dependencies

Handle optional dependencies gracefully:

```python
from typing import Optional

class MyDeps(TypedDict, total=False):
    """Dependencies with optional fields."""
    database: Database      # Required
    cache: Optional[Cache]  # Optional
    logger: Optional[Logger]  # Optional

@db_skill.resource
async def get_cached_status(ctx: RunContext[MyDeps]) -> str:
    """Get status with optional caching."""
    status = await ctx.deps.database.health_check()

    # Cache if available
    if 'cache' in ctx.deps and ctx.deps['cache']:
        await ctx.deps['cache'].set('db_status', status)

    return f"Database status: {status}"
```

### Lazy Initialization

Defer expensive setup:

```python
from pydantic_ai.toolsets.skills import SkillsToolset

skills = SkillsToolset()

@skills.skill()
def expensive_skill() -> str:
    return "Use expensive resources"

@expensive_skill.resource
async def get_expensive_resource(ctx: RunContext[MyDeps]) -> str:
    """Lazy-load expensive resource only when needed."""
    # First call initializes, subsequent calls reuse
    if not hasattr(ctx.deps, '_expensive_resource'):
        ctx.deps._expensive_resource = await initialize_expensive_resource()

    return str(ctx.deps._expensive_resource)
```

## Testing Patterns

### Unit Testing Skills

```python
import pytest
from pydantic_ai import RunContext
from pydantic_ai.toolsets.skills import Skill, SkillsToolset

class MockDeps:
    def __init__(self):
        self.data = {"test": "value"}

def test_skill_resource():
    """Test a skill resource independently."""
    skill = Skill(
        name='test-skill',
        description='Test skill',
        content='Test'
    )

    @skill.resource
    async def my_resource(ctx: RunContext[MockDeps]) -> str:
        return ctx.deps.data['test']

    # Test the resource
    mock_deps = MockDeps()
    ctx = RunContext(deps=mock_deps)

    result = asyncio.run(my_resource(ctx))
    assert result == "value"

def test_skill_in_toolset():
    """Test skill integration with toolset."""
    skill = Skill(
        name='test-skill',
        description='Test skill',
        content='Test content'
    )

    toolset = SkillsToolset(skills=[skill])

    # Verify skill is registered
    assert 'test-skill' in toolset.skills
    assert toolset.get_skill('test-skill').description == 'Test skill'
```

### Integration Testing

```python
import pytest
from pydantic_ai import Agent
from pydantic_ai.toolsets.skills import SkillsToolset

@pytest.fixture
def test_skills():
    """Create test skills."""
    skills = SkillsToolset()

    @skills.skill()
    def test_skill() -> str:
        return "Test skill for integration testing"

    @test_skill.script
    def test_script(value: int) -> str:
        return f"Result: {value * 2}"

    return skills

@pytest.mark.asyncio
async def test_agent_with_skills(test_skills):
    """Test agent interaction with skills."""
    agent = Agent(
        model='openai:gpt-4o',
        toolsets=[test_skills]
    )

    # Agent can access skills
    result = await agent.run('List available skills')
    assert 'test-skill' in result.data
```

## See Also

- [Advanced Features](./advanced.md) - Decorator patterns and custom executors
- [Programmatic Skills](./programmatic-skills.md) - Creating skills in code
- [Creating Skills](./creating-skills.md) - File-based skill creation

"""Programmatic Skills Example: HR Analytics Agent.

Demonstrates how to create agent skills programmatically using decorators
for resources and scripts, enabling progressive disclosure of specialized
expertise without saturating the agent's context.

Key concepts demonstrated:
- Skill creation with metadata and static resources
- Dynamic resources via @skill.resource decorator
- Executable scripts via @skill.script decorator
- Context-aware script execution with dependencies
"""

import datetime
import sqlite3
from dataclasses import dataclass, field

import datasets
import uvicorn
from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai._run_context import RunContext

from pydantic_ai_skills import Skill, SkillResource, SkillsToolset

load_dotenv()


@dataclass
class AnalystDeps:
    """Dependencies for the HR analytics agent.

    Manages database connection and dataset configuration for progressive
    data loading and querying capabilities.
    """

    hf_dataset_name: str = 'dougtrajano/hr-synthetic-database'
    hf_dataset_subsets: list[str] = field(
        default_factory=lambda: ['business_units', 'departments', 'jobs', 'employees', 'compensations']
    )
    db: sqlite3.Connection | None = field(default=None)

    def get_db_tables(self) -> list[str]:
        """Get list of tables currently loaded in the SQLite database."""
        if self.db is None:
            return []
        cursor = self.db.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        return [row[0] for row in cursor.fetchall()]


# Static resource providing database schema reference (loaded on-demand)
schema_skill_resource = SkillResource(
    name='table-schemas',
    uri='table-schemas.md',
    content="""The HR dataset contains relationally-linked tables modeling organizational structure.

#### Business Units
- `id` (string): Unique identifier
- `name` (string): Business unit name
- `description` (string): Description
- `director_job_id` (string): Reference to director's job ID

#### Departments
- `id` (string): Unique identifier
- `name` (string): Department name
- `description` (string): Description
- `manager_job_id` (string): Reference to manager's job ID
- `business_unit_id` (string): Foreign key to business_units

#### Jobs
- `id` (string): Unique identifier
- `name` (string): Job title
- `description` (string): Description
- `job_level` (string): Hierarchical level (Entry, Mid, Senior, Executive)
- `job_family` (string): Functional category (Engineering, Sales, etc.)
- `contract_type` (string): Contract type (Full-time, Part-time, Contract)
- `workplace_type` (string): Work arrangement (On-site, Remote, Hybrid)

#### Employees
- `id` (string): Unique identifier
- `job_id` (string): Foreign key to jobs
- `department_id` / `business_unit_id` (string): Foreign keys (nullable)
- `first_name` / `last_name` (string): Employee name
- `birth_date` (string): YYYY-MM-DD
- `gender`, `ethnicity`, `education_level`, `education_field` (string): Demographics
- `generation` (string): Generational cohort (Gen Z, Millennial, etc.)

#### Compensations
- `id` (string): Unique identifier
- `employee_id` (string): Foreign key to employees
- `annual_base_salary` (float): Base salary
- `annual_bonus_amount` / `annual_commission_amount` (float, nullable): Additional compensation
- `rate_type` (string): Salary or hourly
- `total_compensation` (float): Total annual compensation
""",
)

# Create skill with core metadata and static resources
hr_analytics_skill = Skill(
    name='hr-analytics-skill',
    description=(
        'Comprehensive HR analytics capability with employee, department, job, '
        'and compensation data across business units. Supports SQL queries on '
        'organizational structure and workforce metrics.'
    ),
    content="""Use this skill for HR data analysis tasks including:

- Organizational structure analysis (business units, departments, reporting chains)
- Workforce demographics and composition
- Compensation analysis and equity assessments
- Job family and level distribution
- Employee lifecycle metrics

**Workflow:**
1. Call `load_dataset` script to initialize the in-memory database
2. Use `get_context` resource for dataset overview
3. Reference `table-schemas` resource for detailed field definitions
4. Execute `run_query` script with SQL to analyze data

**Query Tips:**
- All tables are available: business_units, departments, jobs, employees, compensations
- Use JOIN operations to combine data across relationships
- Filter by job_level, job_family, contract_type for targeted analysis
- Aggregate by department, business_unit for organizational insights.
""",
    resources=[schema_skill_resource],
)


@hr_analytics_skill.resource
def get_context() -> str:
    """Provide high-level context about the HR analytics dataset structure.

    This dynamic resource is invoked when the agent needs dataset orientation
    without loading full schema details.
    """
    return (
        'The HR analytics dataset models a complete organizational structure with '
        '5 interconnected tables: business_units (strategic divisions), departments '
        '(functional units), jobs (position definitions), employees (personnel records), '
        'and compensations (pay details). Tables link via foreign keys enabling '
        'hierarchical and relational queries. Use table-schemas resource for full field specs.'
    )


@hr_analytics_skill.script
async def load_dataset(ctx: RunContext[AnalystDeps]) -> str:
    """Load HuggingFace HR dataset into in-memory SQLite database.

    Initializes database connection and loads all dataset subsets as tables.
    Idempotent: skips already-loaded tables.

    Returns status message confirming successful load.
    """
    # Initialize database if needed
    if ctx.deps.db is None:
        ctx.deps.db = sqlite3.connect(':memory:', check_same_thread=False)

    loaded_tables = []
    # Load each subset as a separate table
    for subset in ctx.deps.hf_dataset_subsets:
        if subset not in ctx.deps.get_db_tables():
            dataset = datasets.load_dataset(ctx.deps.hf_dataset_name, name=subset, split='train')
            df = dataset.to_pandas()
            df.to_sql(subset, ctx.deps.db, if_exists='replace', index=False)
            loaded_tables.append(subset)

    if loaded_tables:
        return f'HR dataset loaded. Tables created: {", ".join(loaded_tables)}'
    return 'HR dataset already loaded. All tables available.'


@hr_analytics_skill.script
async def run_query(ctx: RunContext[AnalystDeps], query: str) -> str:  # noqa: D417
    """Execute SQL query on the HR dataset and return formatted results.

    Args:
        query: SQL query string (use table names: business_units, departments,
               jobs, employees, compensations)

    Returns:
        Formatted table with query results or error message.

    Example queries:
    - SELECT COUNT(*) FROM employees
    - SELECT department_id, AVG(total_compensation) FROM compensations
      JOIN employees ON compensations.employee_id = employees.id GROUP BY department_id
    """
    if ctx.deps.db is None:
        return 'Error: HR dataset not loaded. Run load_dataset script first.'

    try:
        cursor = ctx.deps.db.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]

        # Format results as table
        if not rows:
            return 'Query executed successfully. No rows returned.'

        col_widths = [max(len(str(col)), max(len(str(row[i])) for row in rows)) for i, col in enumerate(columns)]
        header = ' | '.join(col.ljust(col_widths[i]) for i, col in enumerate(columns))
        separator = '-+-'.join('-' * width for width in col_widths)
        result_lines = [header, separator]

        for row in rows:
            result_lines.append(' | '.join(str(item).ljust(col_widths[i]) for i, item in enumerate(row)))

        return '\n'.join(result_lines)

    except sqlite3.Error as e:
        return f'SQL Error: {e}\n\nEnsure table names are correct and query syntax is valid.'


# Initialize toolset with programmatic skill
skills_toolset = SkillsToolset(skills=[hr_analytics_skill])

# Create agent with HR analytics capabilities and dependencies
agent = Agent(
    model='openai:gpt-5.2',
    deps_type=AnalystDeps,
    instructions='You are an expert HR data analyst.',
    toolsets=[skills_toolset],
)


@agent.instructions
async def add_skills(ctx: RunContext) -> str | None:
    """Inject skill instructions into agent context via progressive disclosure."""
    return await skills_toolset.get_instructions(ctx)


@agent.instructions
def add_today_date() -> str:
    """Provide current date context for time-sensitive analyses."""
    return f'Today is {datetime.datetime.now().strftime("%B %d, %Y")}.'


# Export agent as FastAPI web application
app = agent.to_web(deps=AnalystDeps())

if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=7932)

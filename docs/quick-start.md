# Quick Start

This guide walks you through creating and using agents with skills support, from basic to advanced usage.

## Basic Usage

### 1. Create Your First Skill

Create `./skills/pydanticai-docs/SKILL.md`:

````markdown
---
name: pydanticai-docs
description: Quick reference for Pydantic AI framework
---

# Pydantic AI Docs

Quick reference for building agents with Pydantic AI.

## Instructions

For detailed information, fetch the full docs at:
https://ai.pydantic.dev/llms-full.txt

## Quick Examples

**Basic Agent:**

```python
from pydantic_ai import Agent

agent = Agent('openai:gpt-5.2')
result = agent.run_sync('Your question')
```
````

**With Tools:**

```python
@agent.tool
async def my_tool(ctx: RunContext[str]) -> str:
    return ctx.deps
```

### 2. Create an Agent with Skills

Create `agent.py`:

```python
import asyncio
from pydantic_ai import Agent, RunContext
from pydantic_ai_skills import SkillsToolset

async def main():
    # Initialize skills
    skills_toolset = SkillsToolset(directories=["./skills"])

    # Create agent
    agent = Agent(
        model='openai:gpt-5.2',
        instructions="You are a helpful assistant.",
        toolsets=[skills_toolset]
    )

    # Add skills instructions to agent
    @agent.instructions
    async def add_skills(ctx: RunContext) -> str | None:
        """Add skills instructions to the agent's context."""
        return await skills_toolset.get_instructions(ctx)

    # Run the agent
    result = await agent.run("How do I create a Pydantic AI agent with tools?")
    print(result.output)

if __name__ == "__main__":
    asyncio.run(main())
```

### 3. Set Your API Key

```bash
export OPENAI_API_KEY="your-api-key-here"
```

### 4. Run the Agent

```bash
python agent.py
```

The agent will use the pydanticai-docs skill to answer your question!

## How It Works

When you run the agent:

1. **Toolset Initialization**: Scans `./skills/` and discovers available skills
2. **Tool Registration**: Registers four core tools:
   - `list_skills()` - Lists all available skills
   - `load_skill(name)` - Loads a specific skill's instructions
   - `read_skill_resource(skill_name, resource_name)` - Reads additional files
   - `run_skill_script(skill_name, script_name, args)` - Executes scripts
3. **Instructions Addition**: Skills overview is added to agent via `get_instructions(ctx)` decorator
4. **Agent Execution**: Agent uses tools to discover, load, and apply skills as needed

## Add a Script-Based Skill

Create a skill that executes Python scripts:

```markdown
./skills/
└── calculator/
    ├── SKILL.md
    └── scripts/
        └── calculate.py
```

**SKILL.md**:

````markdown
---
name: calculator
description: Perform calculations using Python
---

# Calculator Skill

Use the `calculate` script to perform mathematical operations.

## Usage

```python
run_skill_script(
    skill_name="calculator",
    script_name="calculate",
    args=["2 + 2"]
)
```
````

**scripts/calculate.py**:

```python
import sys

if len(sys.argv) < 2:
    print("Usage: calculate.py <expression>")
    sys.exit(1)

expression = sys.argv[1]
try:
    result = eval(expression)
    print(f"Result: {result}")
except Exception as e:
    print(f"Error: {e}")
```

## Advanced Examples

### Programmatic Skills

Create skills directly in Python code for dynamic capabilities:

```python
from pydantic_ai import Agent, RunContext
from pydantic_ai.toolsets.skills import Skill, SkillsToolset

# Create a programmatic skill
my_skill = Skill(
    name='data-processor',
    description='Process and analyze data',
    content='Use this skill for data analysis tasks.'
)

# Add dynamic resources and scripts
@my_skill.resource
def get_schema() -> str:
    """Get current data schema."""
    return "Available fields: id, name, value, timestamp"

@my_skill.script
async def process_data(ctx: RunContext[MyDeps], query: str) -> str:
    """Process data based on query."""
    results = await ctx.deps.process(query)
    return f"Processed {len(results)} records"

# Use with toolset
skills_toolset = SkillsToolset(skills=[my_skill])
```

Learn more in the [Programmatic Skills](programmatic-skills.md) guide.

### Multiple Skill Directories

Load skills from multiple locations:

```python
from pydantic_ai_skills import SkillsToolset

skills_toolset = SkillsToolset(
    directories=[
        "./skills/research",    # Domain-specific skills
        "./skills/data",        # Data processing skills
        "./shared-skills",      # Shared across projects
    ],
    validate=True,
    script_timeout=60
)

print(f"Loaded {len(skills_toolset.skills)} skills")
for name, skill in skills_toolset.skills.items():
    print(f"- {name}: {skill.metadata.description}")
```

### Research Assistant

An agent specialized for searching academic papers:

```python
import asyncio
from pydantic_ai import Agent
from pydantic_ai_skills import SkillsToolset

async def main():
    skills_toolset = SkillsToolset(directories=["./examples/skills"])

    agent = Agent(
        model='openai:gpt-5.2',
        instructions="You are a research assistant specializing in academic papers.",
        toolsets=[skills_toolset]
    )

    @agent.instructions
    async def add_skills(ctx: RunContext) -> str | None:
        """Add skills instructions to the agent's context."""
        return await skills_toolset.get_instructions(ctx)

    result = await agent.run(
        "Find the 5 most recent papers on transformer architectures"
    )
    print(result.output)

if __name__ == "__main__":
    asyncio.run(main())
```

### Dynamic Skill Refresh

Reload skills after filesystem changes:

```python
import asyncio
from pydantic_ai import Agent
from pydantic_ai_skills import SkillsToolset

async def main():
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

    # Use agent
    result = await agent.run("What skills are available?")
    print(result.output)

    # ... User adds new skill to ./skills/ ...

    # To pick up new skills, recreate the toolset and agent
    toolset = SkillsToolset(directories=["./skills"])
    agent = Agent(
        model='openai:gpt-5.2',
        instructions="You are a helpful assistant.",
        toolsets=[toolset]
    )

    @agent.instructions
    async def add_skills_again(ctx: RunContext) -> str | None:
        """Add skills instructions to the agent's context."""
        return await toolset.get_instructions(ctx)

    print(f"\nReloaded. Now have {len(toolset.skills)} skills")

    result = await agent.run("What skills are available now?")
    print(result.output)

if __name__ == "__main__":
    asyncio.run(main())
```

> **Note:** To pick up new skills after modifying the filesystem, you'll need to recreate the `SkillsToolset` instance or restart your application.

### Programmatic Skill Access

Access skills directly without an agent:

```python
from pydantic_ai_skills import SkillsToolset

toolset = SkillsToolset(directories=["./skills"])

# Get a specific skill
skill = toolset.get_skill("arxiv-search")

print(f"Skill: {skill.name}")
print(f"Description: {skill.metadata.description}")
print(f"Content: {len(skill.content)} characters")

# List scripts
if skill.scripts:
    print("\nScripts:")
    for script in skill.scripts:
        print(f"  - {script.name} ({script.path})")

# List resources
if skill.resources:
    print("\nResources:")
    for resource in skill.resources:
        print(f"  - {resource.name}")
```

### Custom Discovery

Use the discovery function directly:

```python
from pydantic_ai_skills import discover_skills

# Discover skills without creating a toolset
skills = discover_skills(
    directories=["./skills", "./more-skills"],
    validate=True
)

# Filter by category
research_skills = [
    s for s in skills
    if s.metadata.extra.get("category") == "research"
]

print(f"Found {len(research_skills)} research skills")
```

### Jupyter Notebook Usage

```python
# Cell 1: Setup
from pydantic_ai import Agent
from pydantic_ai_skills import SkillsToolset

skills_toolset = SkillsToolset(directories=["./skills"])
agent = Agent(
    model='openai:gpt-5.2',
    instructions="You are a data analysis assistant.",
    toolsets=[skills_toolset]
)

@agent.instructions
async def add_skills(ctx: RunContext) -> str | None:
    """Add skills instructions to the agent's context."""
    return await skills_toolset.get_instructions(ctx)

# Cell 2: Explore skills
for name, skill in skills_toolset.skills.items():
    print(f"{name}: {skill.metadata.description}")

# Cell 3: Use agent
result = await agent.run("Analyze the data in data.csv")
print(result.output)
```

## Example Skills

The repository includes several example skills in `examples/skills/`:

### ArXiv Search

- **Type**: Script-based skill
- **Features**: Search academic papers using Python script
- **Location**: `examples/skills/arxiv-search/`

### Web Research

- **Type**: Instruction-only skill
- **Features**: Structured research methodology
- **Location**: `examples/skills/web-research/`

### Pydantic AI Docs

- **Type**: Documentation reference skill
- **Features**: Quick access to Pydantic AI documentation
- **Location**: `examples/skills/pydanticai-docs/`

## Try the Examples

```bash
git clone https://github.com/dougtrajano/pydantic-ai-skills.git
cd pydantic-ai-skills
pip install -e .
pip install jupyter

# Run the example notebook
jupyter notebook examples/test_notebook.ipynb
```

## Next Steps

- [Core Concepts](concepts.md) - Understand the architecture
- [Creating Skills](creating-skills.md) - Build your own skills
- [API Reference](api/toolset.md) - Detailed API documentation

# Pydantic AI Skills

A standardized, composable framework for building and managing Agent Skills within the Pydantic AI ecosystem.

## What are Agent Skills?

Agent Skills are **modular collections of instructions, scripts, tools, and resources** that enable AI agents to progressively discover, load, and execute specialized capabilities for domain-specific tasks.

Think of skills as packages that extend your agent's capabilities without hardcoding every possible feature into your agent's instructions.

## Key Features

- **🔍 Progressive Discovery**: Agents can list available skills and load only what they need
- **📦 Modular Design**: Each skill is a self-contained directory with instructions and resources
- **🛠️ Script Execution**: Skills can include executable Python scripts
- **📚 Resource Management**: Support for additional documentation and data files
- **🔒 Type-Safe**: Built on Pydantic AI's type-safe foundation
- **🚀 Easy Integration**: Simple toolset interface for Pydantic AI agents

## Quick Example

```python
from pydantic_ai import Agent, RunContext
from pydantic_ai_skills import SkillsToolset

# Initialize Skills Toolset with skill directories
skills_toolset = SkillsToolset(directories=["./skills"])

# Create agent with skills
agent = Agent(
    model='openai:gpt-5.2',
    instructions="You are a helpful research assistant.",
    toolsets=[skills_toolset]
)

# Add skills instructions to agent
@agent.instructions
async def add_skills(ctx: RunContext) -> str | None:
    """Add skills instructions to the agent's context."""
    return await skills_toolset.get_instructions(ctx)

# Use agent - skills tools are automatically available
result = await agent.run(
    "What are the last 3 papers on arXiv about machine learning?"
)
print(result.output)
```

## How It Works

1. **Discovery**: The toolset scans specified directories for skills (folders with `SKILL.md` files)
2. **Registration**: Skills are registered as tools on your agent
3. **Progressive Loading**: Agents can:
   - List all available skills with `list_skills()`
   - Load detailed instructions with `load_skill(name)`
   - Read additional resources with `read_skill_resource(skill_name, resource_name)`
   - Execute scripts with `run_skill_script(skill_name, script_name, args)`

## Why Use Skills?

**Instead of this** (hardcoded capabilities):

```python
agent = Agent(
    instructions="""You are a research assistant.
    You can search arXiv, PubMed, analyze data...
    [thousands of lines of instructions for every possible task]"""
)
```

**Do this** (progressive discovery):

```python
skills_toolset = SkillsToolset(directories=["./skills"])
agent = Agent(
    instructions="You are a research assistant.",
    toolsets=[skills_toolset]
)
# Agent discovers and loads only the skills it needs
```

## Benefits

- **Maintainability**: Update skills independently without changing agent code
- **Scalability**: Add new capabilities by creating new skill folders
- **Clarity**: Keep instructions focused and organized
- **Reusability**: Share skills across different agents
- **Testing**: Test skills in isolation

## Security considerations

We strongly recommend that you use Skills only from trusted sources: those you created yourself or obtained from trusted sources. Skills provide AI Agents with new capabilities through instructions and code, and while this makes them powerful, it also means a malicious Skill can direct agents to invoke tools or execute code in ways that don't match the Skill's stated purpose.

!!! warning

    If you must use a Skill from an untrusted or unknown source, exercise extreme caution and thoroughly audit it before use. Depending on what access agents have when executing the Skill, malicious Skills could lead to data exfiltration, unauthorized system access, or other security risks.

## Next Steps

- [Installation](installation.md) - Get started with pydantic-ai-skills
- [Quick Start](quick-start.md) - Build your first skill-enabled agent
- [Creating Skills](creating-skills.md) - Learn how to create custom skills
- [Programmatic Skills](programmatic-skills.md) - Create skills in Python code
- [API Reference](api/toolset.md) - Detailed API documentation

## References

This package is inspired by:

- [Introducing Agent Skills | Claude](https://www.anthropic.com/news/agent-skills)
- [Using skills with Deep Agents](https://blog.langchain.com/using-skills-with-deep-agents/)

## License

MIT © Douglas Trajano 2025

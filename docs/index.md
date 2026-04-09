# Pydantic AI Skills

A standardized, composable framework for building and managing Agent Skills within the Pydantic AI ecosystem.

## What are Agent Skills?

Agent Skills are **modular collections of instructions, scripts, and resources** that extend AI agents with specialized capabilities. Instead of hardcoding features, skills are discovered and loaded on-demand, keeping your agent's context lean and focused.

## Key Features

- **Progressive Discovery**: Load skills only when needed, reducing token usage
- **Modular Design**: Self-contained skill directories with instructions and resources
- **Skill Registries**: Discover and install skills from Git repositories and other remote sources
- **Script Execution**: Include Python scripts that agents can execute
- **Resource Management**: Support for documentation and data files
- **Type-Safe**: Built on Pydantic AI's type-safe foundation
- **Simple Integration**: Drop-in toolset for Pydantic AI agents
- **Capabilities Integration**: Preferred on pydantic-ai >= 1.71 via `SkillsCapability` and `capabilities=[...]`

## Quick Example

```python
from pydantic_ai import Agent
from pydantic_ai_skills import SkillsCapability

# Create agent with skills (preferred on pydantic-ai >= 1.71)
agent = Agent(
    model='openai:gpt-5.2',
    instructions="You are a helpful research assistant.",
    capabilities=[SkillsCapability(directories=['./skills'])],
)

# Use agent - skills tools are automatically available
result = await agent.run(
    "What are the last 3 papers on arXiv about machine learning?"
)
print(result.output)
```

## Capabilities API Example (pydantic-ai >= 1.71)

`SkillsCapability` is the preferred integration path on pydantic-ai >= 1.71.

It bundles `SkillsToolset` behavior and instruction injection through Pydantic AI's Capability API.
If you use `SkillsToolset` directly:

- For pydantic-ai < 1.74, you must add an instructions hook to inject the skills instructions into the agent's context.
- On pydantic-ai >= 1.74, this is automatic.

```python
from pydantic_ai import Agent
from pydantic_ai_skills import SkillsCapability

agent = Agent(
    model='openai:gpt-5.2',
    capabilities=[
        SkillsCapability(directories=['./skills'])
    ],
)
```

## Direct SkillsToolset Example

For earlier versions of Pydantic AI, you can use `SkillsToolset`.

```python
from pydantic_ai import Agent, RunContext
from pydantic_ai_skills import SkillsToolset

skills_toolset = SkillsToolset(directories=['./skills'])

agent = Agent(
    model='openai:gpt-5.2',
    instructions='You are a helpful research assistant.',
    toolsets=[skills_toolset],
)

# For pydantic-ai<1.74, you must add an instructions hook to inject the skills instructions into the agent's context
# On pydantic-ai >= 1.74, this is automatic and you can omit the following instructions hook
# @agent.instructions
# async def add_skills(ctx: RunContext) -> str | None:
#     return await skills_toolset.get_instructions(ctx)
```

## How It Works

1. **Discovery**: The toolset scans specified directories for skills (folders with `SKILL.md` files)
2. **Registration**: Skills are registered as tools on your agent
3. **Progressive Loading**: Agents can:
   - List all available skills with `list_skills()`
   - Load detailed instructions with `load_skill(name)`
   - Read additional resources with `read_skill_resource(skill_name, resource_name)`
   - Execute scripts with `run_skill_script(skill_name, script_name, args)`

## Benefits

- **Cleaner Prompts**: Keep agent instructions focused instead of concatenating every possible feature
- **Scalability**: Add new capabilities by creating new skill folders
- **Maintainability**: Update skills independently without touching agent code
- **Reusability**: Share skills across multiple agents and projects
- **Efficiency**: Reduce token usage by loading skills only when needed
- **Testability**: Test and debug skills in isolation

## Security considerations

We strongly recommend that you use Skills only from trusted sources: those you created yourself or obtained from trusted sources. Skills provide AI Agents with new capabilities through instructions and code, and while this makes them powerful, it also means a malicious Skill can direct agents to invoke tools or execute code in ways that don't match the Skill's stated purpose.

!!! warning

    If you must use a Skill from an untrusted or unknown source, exercise extreme caution and thoroughly audit it before use. Depending on what access agents have when executing the Skill, malicious Skills could lead to data exfiltration, unauthorized system access, or other security risks.

## llms.txt

The Pydantic AI Skills documentation is available in the [llms.txt](https://llmstxt.org/) format. This format is defined in Markdown and is suited for LLMs, AI coding assistants, and agents.

Two formats are available:

- [`llms.txt`](/llms.txt): a file containing a brief description of the project, along with links to the different sections of the documentation. The structure of this file is described in detail [here](https://llmstxt.org/#format).
- [`llms-full.txt`](/llms-full.txt): Similar to `llms.txt`, but with the linked documentation content included inline. This file may be too large for some LLMs.

As of today, these files are not automatically leveraged by most IDEs or coding agents, but they can use them if you provide a link or the full text.

## Next Steps

- [Quick Start](quick-start.md) - Build your first skill-enabled agent
- [Creating Skills](creating-skills.md) - Learn how to create custom skills
- [Programmatic Skills](programmatic-skills.md) - Create skills in Python code
- [Skill Registries](registries.md) - Load skills from Git repositories and remote sources
- [API Reference](api/toolset.md) - Detailed API documentation

## References

This package is inspired by:

- [Agent Skills Specification](https://agentskills.io/specification)
- [Using skills with Deep Agents](https://blog.langchain.com/using-skills-with-deep-agents/)
Note

⚠️ **Only use skills from trusted sources.** Since skills provide agents with new capabilities through instructions and executable code, malicious skills could direct agents to invoke tools unexpectedly or access sensitive data. Always audit skills before use. See [Security & Deployment](security.md) for detailed guidance

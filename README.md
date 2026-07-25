# pydantic-ai-skills

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=DougTrajano_pydantic-ai-skills&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=DougTrajano_pydantic-ai-skills)

[Agent Skills](https://agentskills.io/home) for [Pydantic AI](https://ai.pydantic.dev/).

A skill is a folder with a `SKILL.md` file, optional reference docs, and optional scripts. Your agent
sees only the name and description of each skill until it needs more, then loads the instructions,
resources, and scripts on demand — keeping context small while the library grows.

📖 **[Full documentation](https://dougtrajano.github.io/pydantic-ai-skills)** — including
[video tutorials](https://dougtrajano.github.io/pydantic-ai-skills/quick-start/#video-tutorials).

## Installation

```bash
pip install pydantic-ai-skills
```

## Quick Start

Point a `SkillsCapability` at one or more skill directories and add it to your agent:

```python
from pydantic_ai import Agent
from pydantic_ai_skills import SkillsCapability

agent = Agent(
    model='gateway/openai:gpt-5.2',
    instructions='You are a helpful research assistant.',
    capabilities=[SkillsCapability(directories=['./skills'])],
)

result = await agent.run('What are the last 3 papers on arXiv about machine learning?')
print(result.output)
```

`SkillsToolset` is the same thing as a toolset, for agents built around `toolsets=[...]`:

```python
from pydantic_ai_skills import SkillsToolset

agent = Agent(model='gateway/openai:gpt-5.2', toolsets=[SkillsToolset(directories=['./skills'])])
```

Both inject the skill catalog into the agent's instructions automatically and expose four tools:

| Tool | Purpose |
| --- | --- |
| `list_skills()` | List available skills (optional — the catalog is already in the prompt) |
| `load_skill(name)` | Read a skill's full instructions |
| `read_skill_resource(skill_name, resource_name)` | Read a bundled file such as `REFERENCE.md` |
| `run_skill_script(skill_name, script_name, args)` | Run a bundled script with named arguments |

See [Quick Start](https://dougtrajano.github.io/pydantic-ai-skills/quick-start/).

## Anatomy of a Skill

```md
my-skill/
├── SKILL.md      # Required: YAML frontmatter + Markdown instructions
├── REFERENCE.md  # Optional: extra docs, read on demand
├── scripts/      # Optional: executable scripts
└── resources/    # Optional: templates, data files
```

```markdown
---
name: my-skill
description: Brief description of what this skill does and when to use it
---

# My Skill

## When to Use This Skill

Use this skill when you need to...

## Instructions

1. Step 1
2. Step 2
```

`name` (max 64 chars, lowercase letters, numbers and hyphens) and `description` (max 1024 chars) are
required; other frontmatter fields are yours to use. See
[Creating Skills](https://dougtrajano.github.io/pydantic-ai-skills/creating-skills/).

## Beyond the Filesystem

- **[Programmatic skills](https://dougtrajano.github.io/pydantic-ai-skills/programmatic-skills/)** — define skills in Python with decorators or dataclasses.
- **[Registries](https://dougtrajano.github.io/pydantic-ai-skills/registries/)** — load skills from Git repositories, S3, or custom sources, and compose them (combine, filter, prefix, rename).
- **[Skill selection](https://dougtrajano.github.io/pydantic-ai-skills/advanced/#selecting-which-skills-to-expose)** — give each agent a subset of a shared library with `include` / `exclude`.
- **[Advanced features](https://dougtrajano.github.io/pydantic-ai-skills/advanced/)** — `reload()` / `auto_reload`, `exclude_tools`, deferred loading, recursive discovery.

## Why This and Not `pydantic-ai-harness`

The harness's own `Skills` capability is a minimal reader: it injects `SKILL.md` instructions but
[does not enumerate, read, or execute bundled files](https://github.com/pydantic/pydantic-ai-harness/tree/main/pydantic_ai_harness/skills).
`pydantic-ai-skills` implements the full package — bundled resources, script execution, remote
registries, programmatic skills, and reload at runtime — so skills that ship a reference document or
a script (including those in [Anthropic's skills repository](https://github.com/anthropics/skills))
run as written. Feature-by-feature comparison:
[Why pydantic-ai-skills](https://dougtrajano.github.io/pydantic-ai-skills/comparison/).

## Security

Only use skills from sources you trust. Skills give agents new capabilities through instructions and
code, so a malicious skill can direct an agent to invoke tools or execute code in ways that don't
match its stated purpose — with risks including data exfiltration and unauthorized system access.
Audit any skill from an unknown source before use. See
[Security & Deployment](https://dougtrajano.github.io/pydantic-ai-skills/security/).

## Related Resources

- [Agent Skills Specification](https://agentskills.io/specification)
- [Anthropic Agent Skills docs](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview) and [best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- [Agent Skills Cookbook](https://github.com/anthropics/claude-cookbooks/tree/main/skills)
- [Pydantic AI Documentation](https://ai.pydantic.dev/)

## Contributing

Contributions are welcome — see [Contributing](https://dougtrajano.github.io/pydantic-ai-skills/contributing/).

## Acknowledgments

Thanks to **Anthropic** for the [Agent Skills](https://agentskills.io/home) open format, the
**Pydantic AI team** for the framework, and the **community** for feedback and contributions.

This project was highly inspired by [pydantic-deepagents](https://github.com/vstorm-co/pydantic-deepagents),
which provided foundational ideas and patterns for agent skills and progressive disclosure in Pydantic AI.

## License

MIT License — see [LICENSE](LICENSE).

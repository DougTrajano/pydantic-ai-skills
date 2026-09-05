# pydantic-ai-skills

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=DougTrajano_pydantic-ai-skills&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=DougTrajano_pydantic-ai-skills)

Remote skill registries and bundled-file execution for [Agent Skills](https://agentskills.io/home)
in [Pydantic AI](https://ai.pydantic.dev/).

**Agent Skills** are modular packages of instructions, resources, and scripts that teach an agent to
handle a specialized task. On disk, a skill is just a folder: a `SKILL.md` file holding a name, a
description, and Markdown instructions, plus any reference documents and executable scripts the task
needs.

Your agent starts out seeing only the name and description of each skill. When a task calls for one,
it loads that skill's full instructions, and reads a reference document or runs a script only if it
actually needs to. This is *progressive disclosure*: your skill library can grow without every skill
paying for space in the prompt.

📖 **[Full documentation](https://dougtrajano.github.io/pydantic-ai-skills)** — including
[video tutorials](https://dougtrajano.github.io/pydantic-ai-skills/quick-start/#video-tutorials).

## How This Relates to `pydantic-ai-harness`

[`pydantic-ai-harness`](https://github.com/pydantic/pydantic-ai-harness) ships a `Skills` capability
that reads `SKILL.md` packages from local directories and turns each into a deferred Pydantic AI
capability. It stops there by design — it
[does not enumerate, read, or execute bundled files](https://github.com/pydantic/pydantic-ai-harness/tree/main/pydantic_ai_harness/skills),
and it has no notion of a remote source.

`pydantic-ai-skills` is the companion that fills those gaps. It **requires harness and delegates to
it**, so `SKILL.md` parsing, validation, the catalog and instruction rendering are all upstream's,
and adds:

- **Remote registries** — Git and S3 sources, with composition (filter, prefix, rename, merge).
- **Bundled files** — `read_skill_resource` and `run_skill_script`, so a skill that ships a
  reference document or a script (including those in
  [Anthropic's skills repository](https://github.com/anthropics/skills)) runs as written.
- **Sandboxed execution** — keep untrusted scripts off the host.
- **`${SKILL_DIR}` resolution** — harness leaves the placeholder in place; this substitutes the path.
- **Programmatic skills** — skills defined in Python, in the same catalog.

If your skills are instructions and nothing else, use harness directly — it is a smaller dependency
and identical behaviour. Feature-by-feature:
[comparison](https://dougtrajano.github.io/pydantic-ai-skills/comparison/).

> **Upgrading from v1?** v2 is a clean break: `SkillsToolset`, `SkillsDirectory`, `reload()` and the
> `list_skills` / `load_skill` tools are gone, replaced by harness and Pydantic AI's own
> `load_capability`. See the
> [migration guide](https://dougtrajano.github.io/pydantic-ai-skills/migration-v2/).

## Installation

```bash
uv add pydantic-ai-skills
```

Millennials may continue to use `pip install pydantic-ai-skills`. It still works, like your Spotify
playlist from 2013.

## Quick Start

Point a `SkillsCapability` at one or more skill libraries and add it to your agent:

```python
from pydantic_ai import Agent
from pydantic_ai_skills import SkillsCapability

agent = Agent(
    model='gateway/openai:gpt-5.2',
    instructions='You are a helpful research assistant.',
    capabilities=[SkillsCapability('./skills')],
)

result = await agent.run('What are the last 3 papers on arXiv about machine learning?')
print(result.output)
```

Or pull them from a repository:

```python
from pydantic_ai_skills import GitSkillsRegistry, SkillsCapability

capability = SkillsCapability(
    './skills',
    registries=[GitSkillsRegistry('https://github.com/anthropics/skills', path='skills')],
)
```

Each skill becomes its own **deferred capability**: the model sees names and descriptions up front,
loads the ones it needs with Pydantic AI's built-in `load_capability`, then reaches that skill's
files with the two tools this package adds:

| Tool | Purpose |
| --- | --- |
| `read_skill_resource(skill_name, resource_name)` | Read a bundled file such as `references/FORMS.md` |
| `run_skill_script(skill_name, script_name, args)` | Run a bundled script with named arguments |

Both stay behind the same boundary as the skill's instructions: by default they refuse a skill the
model has not loaded.

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

`name` (max 64 chars, lowercase letters, numbers and hyphens; it must match the directory) and
`description` (max 1024 chars) are the fields the runtime acts on. Other frontmatter is accepted but
inert — including behavioural fields such as `allowed-tools`, which do **not** restrict anything
here. See
[Creating Skills](https://dougtrajano.github.io/pydantic-ai-skills/creating-skills/).

## Beyond the Filesystem

- **[Programmatic skills](https://dougtrajano.github.io/pydantic-ai-skills/programmatic-skills/)** — define skills in Python with decorators or dataclasses.
- **[Registries](https://dougtrajano.github.io/pydantic-ai-skills/registries/)** — load skills from Git repositories, S3, or custom sources, and compose them (combine, filter, prefix, rename).
- **[Skill selection](https://dougtrajano.github.io/pydantic-ai-skills/advanced/#selecting-which-skills-to-expose)** — give each agent a subset of a shared library with `include` / `exclude`.
- **[Sandboxing](https://dougtrajano.github.io/pydantic-ai-skills/sandbox/)** — run a skill's scripts in a container or virtual filesystem instead of on the host.
- **[Advanced features](https://dougtrajano.github.io/pydantic-ai-skills/advanced/)** — custom script executors, `${SKILL_DIR}` resolution, and rebuild strategies.

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

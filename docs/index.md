# pydantic-ai-skills

Remote skill registries and bundled-file execution for [Pydantic AI](https://ai.pydantic.dev/)
Agent Skills.

[`pydantic-ai-harness`](https://github.com/pydantic/pydantic-ai-harness) ships a `Skills`
capability that reads [Agent Skill](https://agentskills.io/specification) packages from local
directories and turns each `SKILL.md` into a deferred Pydantic AI capability. It stops there, by
design — its README is explicit:

> `Skills` does not enumerate, read, or execute those files. Relative paths and placeholders such
> as `${CLAUDE_SKILL_DIR}` remain unchanged in the loaded instructions.

This package is the companion that fills the gaps. It hands discovery, validation and instruction
rendering to harness — so a skill behaves identically either way — and adds the parts harness
leaves out.

## What this adds

| | harness `Skills` | with `pydantic-ai-skills` |
| --- | --- | --- |
| Reads `SKILL.md` packages | ✅ | ✅ *(harness does it)* |
| Skill catalog and on-demand instructions | ✅ | ✅ *(harness does it)* |
| `include` / `exclude` selection | ✅ | ✅ *(harness does it)* |
| Skills from a Git repository | ❌ | ✅ [`GitSkillsRegistry`](registries.md#git) |
| Skills from an S3 bucket | ❌ | ✅ [`S3SkillsRegistry`](registries.md#s3) |
| Composing sources (filter, prefix, rename, merge) | ❌ | ✅ [registry composition](registries.md#composition) |
| Reading bundled `references/` and `assets/` | ❌ | ✅ `read_skill_resource` |
| Running bundled `scripts/` | ❌ | ✅ `run_skill_script` |
| Sandboxed script execution | ❌ | ✅ [sandbox executors](sandbox.md) |
| `${SKILL_DIR}` resolved in instructions | ❌ | ✅ [`resolve_skill_dir`](concepts.md#skill_dir) |
| Skills defined in Python | ❌ | ✅ [programmatic skills](programmatic-skills.md) |

## Install

```bash
pip install pydantic-ai-skills          # core, including harness
pip install "pydantic-ai-skills[git]"   # + Git registries
pip install "pydantic-ai-skills[s3]"    # + S3 registries
```

See [Installation](installation.md) for the full list of extras.

## Use it

```python
from pydantic_ai import Agent
from pydantic_ai_skills import GitSkillsRegistry, SkillsCapability

agent = Agent(
    'anthropic:claude-sonnet-4-6',
    capabilities=[
        SkillsCapability(
            '.agents/skills',
            registries=[
                GitSkillsRegistry(
                    'https://github.com/anthropics/skills',
                    path='skills',
                ),
            ],
        ),
    ],
)

result = agent.run_sync('Fill in the tax form in ./forms and summarize what you entered.')
print(result.output)
```

The model sees each skill's name and description up front, loads the ones it needs with
Pydantic AI's own `load_capability` tool, then reaches that skill's bundled files with
`read_skill_resource` and `run_skill_script`.

## Where to go next

- **[Quick Start](quick-start.md)** — a working agent in a few minutes.
- **[Core Concepts](concepts.md)** — progressive disclosure, and who does what.
- **[Creating Skills](creating-skills.md)** — writing a skill package.
- **[Skill Registries](registries.md)** — Git, S3, and composing sources.
- **[Programmatic Skills](programmatic-skills.md)** — skills defined in Python.
- **[Sandboxing](sandbox.md)** — keeping untrusted scripts off the host.
- **[Security](security.md)** — the trust model, and what it does not cover.
- **[Migrating from v1](migration-v2.md)** — what changed in 2.0 and why.

## Upgrading from v1

v2 is a clean break. `SkillsToolset`, `SkillsDirectory`, `discover_skills`, `reload()` and the
`list_skills` / `load_skill` tools are gone — harness or Pydantic AI now provide each of them.
[Migrating from v1](migration-v2.md) maps every removed symbol to its replacement.

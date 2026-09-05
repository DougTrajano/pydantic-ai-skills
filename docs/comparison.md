# pydantic-ai-skills and pydantic-ai-harness

There is more than one way to give a Pydantic AI agent Agent Skills. This page explains how the
pieces fit together and which one you actually need.

## The three layers

### Core `Capability`

Pydantic AI's [on-demand capabilities](https://ai.pydantic.dev/capabilities/) let you define a
capability in Python and hide its instructions and tools behind a framework-managed
`load_capability` tool:

```python
from pydantic_ai.capabilities import Capability

refunds = Capability(
    id='refunds',
    description='Refund policy tools and instructions.',
    instructions='Check the refund policy before answering refund questions.',
    defer_loading=True,
)
```

This is the right tool when your instructions and tools live in Python and you want nothing else.
It is not an Agent Skills implementation: no `SKILL.md`, no bundled resources, no portable package.

### harness `Skills`

[`pydantic-ai-harness`](https://github.com/pydantic/pydantic-ai-harness) reads Agent Skill packages
from local directories and turns each one into exactly the deferred `Capability` above:

```python
from pydantic_ai import Agent
from pydantic_ai_harness import Skills

agent = Agent('anthropic:claude-sonnet-4-6', capabilities=[Skills('.agents/skills')])
```

**If that is all you need, use it directly.** It is a smaller dependency and this package adds
nothing to a skill that is only instructions.

### pydantic-ai-skills

Use this package when you need something `Skills` deliberately does not do:

- Your skills live in a **Git repository or an S3 bucket** rather than on the local filesystem.
- You compose skills from **several sources** that need filtering, prefixing, or merging.
- Your skills ship **bundled files** — `references/`, `assets/`, `scripts/` — that the model has to
  read or execute.
- You want those scripts to run in a **sandbox** rather than on the host.
- Some of your skills are **defined in Python** and should sit in the same catalog.

It does not reimplement the first layer. `SkillsCapability` constructs a harness `Skills` and
re-emits the capabilities it produces, so `SKILL.md` parsing, name validation, the catalog, and the
`# Skill: <name>` instruction rendering are all upstream's.

## Feature comparison

| | `pydantic-ai-skills` | harness `Skills` | Core `Capability` |
| --- | --- | --- | --- |
| Reads `SKILL.md` packages | ✅ *(via harness)* | ✅ | ❌ |
| Skill catalog (level 1) | ✅ *(via harness)* | ✅ | ✅ |
| Instructions on demand (level 2) | ✅ *(via harness)* | ✅ | ✅ |
| `include` / `exclude` selection | ✅ *(via harness)* | ✅ | n/a |
| Deferred loading via `load_capability` | ✅ | ✅ | ✅ opt-in |
| Declarative agent specs | ✅ | ✅ | ✅ |
| Bundled resources (level 3) | ✅ `read_skill_resource` | ❌ not loaded | ❌ |
| Bundled script execution | ✅ `run_skill_script` | ❌ not executed | ❌ |
| Sandboxed script execution | ✅ | ❌ | ❌ |
| `${SKILL_DIR}` resolution | ✅ | ❌ left in place | ❌ |
| Git registries | ✅ | ❌ | ❌ |
| S3 registries | ✅ | ❌ | ❌ |
| Registry composition | ✅ filter, prefix, rename, merge | ❌ | ❌ |
| Programmatic skills in Python | ✅ | ❌ | ✅ |

## The practical difference: level 3

[Progressive disclosure](concepts.md) has three levels. Metadata is always in the prompt,
instructions load on demand, and **bundled resources and scripts load only when the skill actually
needs them**.

An implementation that stops after level 2 gives the model a skill's instructions but no way to act
on them. Consider a typical published skill:

```text
pdf-processing/
├── SKILL.md          # "Consult FORMS.md, then run scripts/fill_form.py"
├── FORMS.md
└── scripts/
    └── fill_form.py
```

With `Skills` alone the model receives instructions naming two files it cannot open and a script it
cannot run. It will improvise — usually by writing its own worse version of `fill_form.py`, or by
inventing what `FORMS.md` probably says. With this package the same instructions resolve: the model
reads `FORMS.md` through `read_skill_resource` and runs the script through `run_skill_script`.

That is the whole reason this package exists. If your skills are instructions and nothing else,
you do not need it.

## Using both

You do not choose one *or* the other — this package requires harness and uses it internally. What
you can do is run `Skills` directly for libraries that need nothing extra, and `SkillsCapability`
for the ones that do:

```python
from pydantic_ai import Agent
from pydantic_ai_harness import Skills
from pydantic_ai_skills import GitSkillsRegistry, SkillsCapability

agent = Agent(
    'anthropic:claude-sonnet-4-6',
    capabilities=[
        # Instructions-only house skills: harness is enough.
        Skills('.agents/prompts'),
        # Published skills with scripts, pulled from a repository.
        SkillsCapability(
            registries=[GitSkillsRegistry('https://github.com/anthropics/skills', path='skills')],
        ),
    ],
)
```

Skill names have to be unique across everything an agent loads, since each becomes a capability id.
Use [`prefixed()`](registries.md#prefixing-and-renaming) when two sources collide.

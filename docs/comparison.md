# Why pydantic-ai-skills

There is more than one way to give a Pydantic AI agent Agent Skills. This page explains what
`pydantic-ai-skills` does, how it differs from the alternatives, and when each one is the better
fit.

## The alternatives

### Core `Capability` with `defer_loading`

Pydantic AI's core [on-demand capabilities](https://ai.pydantic.dev/capabilities/) let you define a
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

This is the right tool when your instructions and tools live in Python. It is not an Agent Skills
implementation: there is no `SKILL.md`, no bundled resources, and no portable skill package.

### `pydantic-ai-harness` `Skills`

[`pydantic-ai-harness`](https://github.com/pydantic/pydantic-ai-harness) ships a `Skills` capability
that scans skill libraries and turns each `SKILL.md` into one deferred core capability. It is a
deliberately minimal reader: it parses the frontmatter and Markdown body and, in its own words,
does not enumerate, read, or execute bundled files such as `references/`, `assets/`, or `scripts/`.

```python
from pydantic_ai_harness.skills import Skills

agent = Agent('anthropic:claude-sonnet-4-6', capabilities=[Skills('.agents/skills')])
```

### `pydantic-ai-skills`

This library implements the whole Agent Skills package — metadata, instructions, bundled resources,
and executable scripts — plus discovery from remote registries and skills defined in Python.

## Feature comparison

| | `pydantic-ai-skills` | harness `Skills` | Core `Capability` |
| --- | --- | --- | --- |
| Reads `SKILL.md` packages | ✅ | ✅ | ❌ |
| Skill metadata catalog (level 1) | ✅ | ✅ | ✅ |
| Instructions on demand (level 2) | ✅ | ✅ | ✅ |
| Bundled resources (level 3) | ✅ `read_skill_resource` | ❌ not loaded | ❌ |
| Bundled script execution | ✅ `run_skill_script` | ❌ not executed | ❌ |
| `include` / `exclude` selection | ✅ | ✅ | n/a |
| Programmatic skills in Python | ✅ decorators and dataclasses | ❌ | ✅ |
| Remote registries (Git, S3) | ✅ | ❌ | ❌ |
| Registry composition | ✅ combine, filter, prefix, rename | ❌ | ❌ |
| Reload without restarting | ✅ `reload()` / `auto_reload` | ❌ snapshot at construction | ❌ |
| Recursive discovery | ✅ up to `max_depth` | ❌ immediate children only | n/a |
| Path traversal and symlink containment | ✅ | ❌ explicitly not a boundary | n/a |
| Per-tool restriction | ✅ `exclude_tools` | n/a | n/a |
| Deferred loading via `load_capability` | ✅ `defer_loading=True` | ✅ always deferred | ✅ opt-in |
| Declarative agent specs | ✅ | ✅ | ✅ |

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

With instruction-only loading the model reads that guidance, then has no `FORMS.md` and no way to
run `fill_form.py`. Relative paths and placeholders such as `${CLAUDE_SKILL_DIR}` stay unresolved in
the loaded text. `pydantic-ai-skills` exposes `read_skill_resource` and `run_skill_script`, so
skills written this way — including those in Anthropic's
[skills repository](https://github.com/anthropics/skills) — run as published.

If script execution is not appropriate in your deployment, turn it off explicitly rather than
losing resource reads with it:

```python
SkillsCapability(directories=['./skills'], exclude_tools=['run_skill_script'])
```

## Choosing which skills to expose

A shared library can serve several agents. `include` and `exclude` scope the catalog per agent:

```python
from pydantic_ai_skills import SkillsCapability

research = SkillsCapability(directories=['./skills'], include=['arxiv-search', 'web-research'])
support = SkillsCapability(directories=['./skills'], exclude=['arxiv-search'])
```

| Configuration | Skills in the catalog |
| --- | --- |
| Neither option | All discovered skills |
| `include=['a', 'b']` | Only `a` and `b` |
| `include=[]` | No skills |
| `exclude=['a', 'b']` | All except `a` and `b` |
| `exclude=[]` | All discovered skills |

Notes:

- `include` and `exclude` cannot be combined; doing so raises `ValueError`.
- A name matching no discovered skill raises `ValueError` at construction, so typos surface early.
- Selection applies to every source: programmatic skills, directories, and registries.
- `reload()` and `auto_reload` re-apply the selection.
- Passing a bare string (`include='arxiv-search'`) raises `TypeError` rather than matching each
  character.

Both options are available on `SkillsToolset` and `SkillsCapability`, and in agent specs:

```yaml
capabilities:
  - SkillsCapability:
      directories: ['./skills']
      include:
        - arxiv-search
        - web-research
```

Selection controls catalog exposure. It is not a filesystem permission or an access-control
boundary — see [Security](security.md).

## Which should you use?

Use **core `Capability`** when instructions and tools are written in Python and you do not need a
portable skill format.

Use **harness `Skills`** when you only need instruction text injected on demand, your skills are
plain `SKILL.md` files with no bundled files, and you already depend on the harness.

Use **`pydantic-ai-skills`** when skills carry bundled resources or scripts, come from a Git or S3
registry, are generated in Python, need to change while the process runs, or when you want path
traversal and symlink containment on the loading path.

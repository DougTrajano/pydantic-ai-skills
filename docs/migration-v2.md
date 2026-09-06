# Migrating from v1

v2 is a clean break. There are no deprecation shims: the removed APIs are gone in 2.0.

## Why

v1 implemented all of Agent Skills itself — discovery, `SKILL.md` parsing, validation, the catalog,
instruction injection, and its own `list_skills` / `load_skill` tools.
[`pydantic-ai-harness`](https://github.com/pydantic/pydantic-ai-harness) now ships a `Skills`
capability that does the first five, and Pydantic AI's `load_capability` does the sixth. Keeping a
parallel implementation meant guaranteed drift.

So v2 delegates all of it and keeps only what harness deliberately does not do: remote sources,
bundled files, sandboxed script execution, and Python-defined skills. See
[pydantic-ai-skills and pydantic-ai-harness](comparison.md) for the division of labour.

## The short version

```python
# v1
from pydantic_ai_skills import SkillsToolset

agent = Agent(model, toolsets=[SkillsToolset(directories=['./skills'])])

# v2
from pydantic_ai_skills import SkillsCapability

agent = Agent(model, capabilities=[SkillsCapability('./skills')])
```

## Requirements

| | v1 | v2 |
| --- | --- | --- |
| `pydantic-ai-slim` | `>=1.105` | `>=2.38` |
| `pydantic-ai-harness` | not used | `>=0.28`, required |
| Python | `>=3.10` | `>=3.10` |

harness sets a `pydantic-ai-slim>=2.37` floor of its own; this package needs 2.38 for
`AbstractCapability.visit_and_replace`, which `SkillsCapability` overrides.

## Removed, and what replaces it

| v1 | v2 |
| --- | --- |
| `SkillsToolset` | `SkillsCapability`, passed via `capabilities=` |
| `list_skills` tool | The deferred-capability catalog, in the prompt |
| `load_skill` tool | Pydantic AI's `load_capability` |
| `SkillsDirectory` | Pass the directory path straight to `SkillsCapability` |
| `discover_skills()` | harness discovers; `packages.index_libraries()` indexes bundled files |
| `parse_skill_md()` | harness parses; `_parsing.parse_skill_md` remains internal |
| `validate_skill_metadata()` | harness validates, always |
| `Skill.from_file()` | harness loads directory-backed skills |
| `instruction_template=` | harness renders `# Skill: <name>` |
| `max_depth=` | Immediate children only, matching harness |
| `validate=` | harness always validates |
| `exclude_tools=` | `resources=False` / `scripts=False` |
| `reload()`, `auto_reload=` | Construct a new `SkillsCapability` |
| `defer_loading=` on the capability | Every skill is individually deferred |
| `SkillRegistry.search/get/install/update` | `SkillRegistry.sync()` |
| `SkillRegistry.get_skills()` | `skill_infos()` / `skill_names()` |
| `script_executor=` on a registry | `script_executor=` on `SkillsCapability` |
| `validate=` on a registry | harness validates |

## New in v2

| | |
| --- | --- |
| `LocalSkillsRegistry` | A local directory that can take part in composition |
| `GitSkillsRegistry.revision()` | The commit SHA the local clone is on |
| `S3SkillsRegistry.revision(name)` | The newest object modification time for a skill |
| `require_loaded=` | Refuse file reads for a skill the model has not loaded |
| `resolve_skill_dir=` | Substitute `${SKILL_DIR}` / `${CLAUDE_SKILL_DIR}` in instructions |
| `list_bundled_files=` | Append the names of a skill's resources and scripts to its instructions |
| `SkillRegistry.__or__` | `a \| b` builds a `CombinedRegistry` |

## Walking through the changes

### Toolset to capability

```python
# v1
SkillsToolset(
    directories=['./skills'],
    registries=[registry],
    skills=[my_skill],
    include=['pdf'],
)

# v2 — same options, on a capability
SkillsCapability(
    './skills',
    registries=[registry],
    skills=[my_skill],
    include=['pdf'],
)
```

`directories` is now the first positional parameter and accepts a single path as well as a list.

### Behavioural change: how a skill is loaded

In v1 the model called `load_skill('pdf-processing')`. In v2 it calls
`load_capability(id='pdf-processing')` — Pydantic AI's own tool, injected automatically when any
deferred capability is present.

Nothing needs changing in your skills, but if you have prompts or evals that name `load_skill`,
update them.

### Behavioural change: recursive discovery

v1 searched up to `max_depth` levels for `SKILL.md`. v2 looks only at a library's **immediate
children**, matching harness. If you relied on nesting:

```text
skills/                    skills/
└── vendor/          →     ├── vendor-pdf/
    └── pdf/               └── vendor-xlsx/
        └── SKILL.md
```

Or keep the layout and pass each subdirectory as its own library:

```python
SkillsCapability(['./skills/vendor', './skills/internal'])
```

### Behavioural change: name validation

harness validates skill names strictly and rejects a `SKILL.md` whose frontmatter `name` disagrees
with its directory. v1 only warned. A skill that loaded with a warning in v1 may now raise at
construction — the fix is to make the two agree, or drop the `name` key and let it be derived from
the directory.

### Registries

```python
# v1
skills = registry.get_skills()
await registry.install('pdf', './installed')
results = await registry.search('pdf')

# v2
library = registry.sync()            # -> Path to a skill library
names = registry.skill_names()
infos = registry.skill_infos()       # name, description, directory
```

`sync()` subsumes `install` and `update`: it clones or pulls, downloads or re-syncs, and returns the
directory. It is synchronous, and safe to call repeatedly.

Cloning is now lazy — v1 cloned in `__init__` when `auto_install=True`; v2 clones on the first
`sync()`. Constructing a registry no longer touches the network.

The composition wrappers changed shape too. They now stage real directories, and a
`filtered()` predicate receives a
[`SkillInfo`](api/registries.md) rather than a full `Skill`:

```python
# v1
registry.filtered(lambda skill: 'pdf' in skill.name.lower())

# v2
registry.filtered(lambda info: 'pdf' in info.name)
```

`prefixed()` and `renamed()` now rewrite each staged package's frontmatter `name`, because harness
requires it to match the directory.

### Script executors

The executor moved from the source to the capability, so one setting covers every skill regardless
of where it came from:

```python
# v1
GitSkillsRegistry(url, script_executor=OpenSandboxScriptExecutor())

# v2
SkillsCapability(
    registries=[GitSkillsRegistry(url)],
    script_executor=OpenSandboxScriptExecutor(),
)
```

### Reloading

```python
# v1
toolset = SkillsToolset(directories=['./skills'], auto_reload=True)
toolset.reload()

# v2 — rebuild
def build_agent() -> Agent:
    return Agent(model, capabilities=[SkillsCapability('./skills')])
```

For a long-lived server, rebuild on a redeploy or a schedule and swap the agent. See
[Snapshots](concepts.md#snapshots).

### Agent specs

```yaml
# v1
capabilities:
  - SkillsCapability:
      directories: ['./skills']
      max_depth: 3
      validate: true
      defer_loading: true

# v2
capabilities:
  - SkillsCapability:
      directories: ['./skills']
      include: ['pdf-processing']
```

`max_depth`, `validate`, `instruction_template`, `exclude_tools`, `auto_reload` and `defer_loading`
are no longer accepted. `resources`, `scripts`, `require_loaded`, `resolve_skill_dir` and
`list_bundled_files` are.

## If you were only using level 1 and 2

If your skills are instructions and nothing else — no `references/`, no `scripts/`, no remote
sources — you do not need this package at all. Use harness directly:

```python
from pydantic_ai_harness import Skills

agent = Agent('anthropic:claude-sonnet-4-6', capabilities=[Skills('./skills')])
```

That is a smaller dependency and identical behaviour. This package is worth taking on only for
[what it adds](comparison.md#feature-comparison).

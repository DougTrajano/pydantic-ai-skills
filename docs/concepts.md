# Core Concepts

## Progressive disclosure

An [Agent Skill](https://agentskills.io/specification) is a directory of instructions and
supporting files. The point of the format is that an agent should not carry all of it in context
all of the time. Skills load in three levels:

| Level | What the model gets | When | Provided by |
| --- | --- | --- | --- |
| 1. Metadata | Each skill's name and description | Always in the prompt | harness `Skills` |
| 2. Instructions | The `SKILL.md` body | When the model calls `load_capability` | harness `Skills` |
| 3. Bundled files | `references/`, `assets/`, `scripts/` | When the model calls `read_skill_resource` or `run_skill_script` | this package |

Level 1 costs a line or two per skill, so a hundred skills stay affordable. Level 2 costs a page,
and only for the skills a task actually touches. Level 3 costs nothing until a specific file is
needed.

## Who does what

`SkillsCapability` is a composite. It owns the parts of the pipeline harness does not:

```text
  registries ──sync()──► local directories ─┐
                                            ├──► harness Skills ──► one deferred
  directories ──────────────────────────────┘                       Capability per skill
                                                                          │
  index the same directories ──► bundled files ──► read_skill_resource ◄──┘
                                                   run_skill_script
```

1. **Registries are synced.** Each [`SkillRegistry`](registries.md) materializes its skills into a
   local directory. A Git registry clones, an S3 registry downloads, a composed registry stages a
   new directory from its children's output.
2. **harness discovers and validates.** The synced directories and any local ones are handed to
   `pydantic_ai_harness.Skills`, which scans each library's immediate children, validates the
   `SKILL.md` frontmatter, applies `include`/`exclude`, and produces one deferred
   `Capability` per skill.
3. **Bundled files are indexed.** The same directories are scanned for each skill's resources and
   scripts, keyed by the skill's name — the same name harness gave the capability.
4. **The catalog is re-emitted.** Each capability harness produced is passed through, with
   `${SKILL_DIR}` resolved in its instructions when the skill has a directory, and its
   [bundled files listed](#bundled-file-inventory) at the end of them.

Everything happens at construction time. See [Snapshots](#snapshots) below.

## Deferred capabilities, not a `load_skill` tool

Every skill is a *deferred capability*: the model sees its id and description in a catalog, and
loads it by calling Pydantic AI's built-in `load_capability` tool. v1 of this package shipped its
own `list_skills` and `load_skill` tools; both are gone, because the framework now does it.

That matters beyond tidiness. Because a skill is a real capability, its instructions participate in
Pydantic AI's instruction ordering, message history records what was loaded, and
`RunContext.active_capability_ids` knows which skills are live — which is what the
[`require_loaded`](#require_loaded) gate reads.

## The two tools this package adds

Both take the skill's name as their first argument, so one pair of tools serves every skill:

- **`read_skill_resource(skill_name, resource_name, args=None)`** — reads a bundled text file, named
  by its path relative to the skill directory (`references/FORMS.md`). For a
  [programmatic skill](programmatic-skills.md) it can also invoke a callable resource.
- **`run_skill_script(skill_name, script_name, args=None)`** — runs a bundled script
  (`scripts/fill_form.py`) through the configured
  [script executor](sandbox.md), and returns its output.

They are always visible, while each skill stays deferred. Per-skill toolsets were the obvious
alternative and do not work: two loaded skills would contribute two tools with the same name.

### `require_loaded`

Because the tools are always visible, something has to stop the model reading a skill's files
without loading the skill. `require_loaded=True` (the default) checks
`RunContext.active_capability_ids` and refuses with a `ModelRetry` that names the capability to load:

```text
Skill 'pdf-processing' is not loaded. Call load_capability with id='pdf-processing' first,
then read its files.
```

Set `require_loaded=False` when a skill's files should be reachable without loading its
instructions first.

### Bundled-file inventory

Both tools resolve names against the index, whose keys are skill-relative paths
(`scripts/aggregate.py`). A `SKILL.md`, though, usually names its own files in prose — "run the
aggregate script" — so a model calling `run_skill_script` has nothing exact to copy and guesses.

`SkillsCapability` closes that gap by appending the package's real names to the skill's
instructions:

```text
## Bundled files

Read with `read_skill_resource`, using these exact `resource_name` values:

- `references/NOTES.md`

Run with `run_skill_script`, using these exact `script_name` values:

- `scripts/aggregate.py`
```

Because it rides on the *instructions*, it stays behind `load_capability`: the model pays for the
listing only once it has loaded that skill, never in the always-on catalog. Long packages are
truncated after 50 entries per kind.

Pass `list_bundled_files=False` for skills whose `SKILL.md` already lists its files.

As a fallback, both tools also accept an unambiguous shorthand: `aggregate` or `aggregate.py`
resolves to `scripts/aggregate.py` when exactly one indexed name matches. Two files sharing a name
resolve to neither — the `ModelRetry` names both candidates and asks for the full path.

### `${SKILL_DIR}`

Published skills often write paths as `${SKILL_DIR}/scripts/run.py` or `${CLAUDE_SKILL_DIR}/...`.
harness passes those through untouched, which leaves the model holding a literal placeholder.
`SkillsCapability` substitutes the skill's real directory when it re-emits the instructions:

```python
SkillsCapability('.agents/skills', resolve_skill_dir=True)  # the default
```

Pass `resolve_skill_dir=False` to get exactly what harness rendered.

## Skill packages

A skill is an **immediate child** of a library directory containing a `SKILL.md`:

```text
.agents/skills/            ← the library (what you pass)
├── pdf-processing/        ← a skill package
│   ├── SKILL.md
│   ├── FORMS.md
│   ├── references/
│   │   └── LAYOUT.md
│   └── scripts/
│       └── fill_form.py
└── data-analysis/
    └── SKILL.md
```

Pass the **library**, not a skill package. Nesting is not searched: `pdf-processing/vendor/SKILL.md`
does not become a second skill. This mirrors harness exactly, so the indexed files and the catalog
can never disagree about what a skill is.

See [Creating Skills](creating-skills.md) for the `SKILL.md` format and how resources and scripts
are discovered.

## Snapshots

Discovery runs once, when `SkillsCapability` is constructed — registries sync, harness scans,
files are indexed. Nothing re-reads the filesystem during a run.

v1 had `reload()` and `auto_reload`; both are gone. To pick up changes, build a new capability and a
new agent:

```python
def build_agent() -> Agent:
    return Agent('anthropic:claude-sonnet-4-6', capabilities=[SkillsCapability('./skills')])


# On a redeploy, or on a schedule:
agent = build_agent()
```

This is harness's model too, and it is the honest one: an agent's tools and instructions are fixed
for the run, so a mid-run reload was never coherent.

## Where skills come from

| Source | Use | Docs |
| --- | --- | --- |
| A local directory | Skills committed alongside your application | [Creating Skills](creating-skills.md) |
| `GitSkillsRegistry` | Skills published in a repository | [Registries](registries.md#git) |
| `S3SkillsRegistry` | Skills distributed through object storage | [Registries](registries.md#s3) |
| `LocalSkillsRegistry` | A local directory that needs composing | [Registries](registries.md#local) |
| `skills=[...]` | Skills defined in Python | [Programmatic Skills](programmatic-skills.md) |

They all land in one catalog. Names must be unique across every source, since each becomes a
capability id; [`prefixed()`](registries.md#prefixing-and-renaming) resolves collisions.

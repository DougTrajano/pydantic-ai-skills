# SkillsCapability API Reference

`SkillsCapability` is the entry point. Pass it to an agent's `capabilities=[...]`.

It is a composite over
[`pydantic-ai-harness`](https://github.com/pydantic/pydantic-ai-harness)'s `Skills`: harness
discovers and validates the skill packages and renders their instructions, while this capability
syncs remote registries, indexes bundled files, resolves `${SKILL_DIR}`, and adds Python-defined
skills. See [Core Concepts](../concepts.md#who-does-what) for the division of labour.

::: pydantic_ai_skills.SkillsCapability
    options:
      show_source: true
      heading_level: 2
      members:
        - __init__
        - skill_names
        - packages
        - apply
        - visit_and_replace
        - get_toolset
        - from_spec
        - get_serialization_name

## Constructor parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `directories` | `str \| Path \| Sequence[str \| Path]` | `()` | Skill-library paths. A library is the *parent* of the skill packages. |
| `registries` | `Sequence[SkillRegistry]` | `()` | Remote sources, synced to local libraries at construction. |
| `skills` | `Sequence[Skill \| SkillWrapper]` | `()` | Skills defined in Python. |
| `include` | `Collection[str] \| None` | `None` | Exact names to expose. Cannot be combined with `exclude`. |
| `exclude` | `Collection[str] \| None` | `None` | Exact names to omit. Cannot be combined with `include`. |
| `script_executor` | `SkillScriptExecutor \| None` | `None` | Where bundled scripts run. Defaults to local subprocesses. |
| `exclude_resources` | `Sequence[str] \| None` | `None` | Extra glob patterns excluded from resource discovery. |
| `resources` | `bool` | `True` | Register `read_skill_resource`. |
| `scripts` | `bool` | `True` | Register `run_skill_script`. |
| `require_loaded` | `bool` | `True` | Refuse bundled-file calls for a skill the model has not loaded. |
| `resolve_skill_dir` | `bool` | `True` | Substitute `${SKILL_DIR}` / `${CLAUDE_SKILL_DIR}` in instructions. |
| `id` | `str \| None` | `None` | Stable identifier for the capability carrying the file tools. |

At least one of `directories`, `registries` or `skills` must be given.

## Tools

`SkillsCapability` registers two tools. The catalog and instruction loading are Pydantic AI's own
`load_capability`, not something this package provides.

| Tool | Signature | Purpose |
|------|-----------|---------|
| `read_skill_resource` | `(skill_name, resource_name, args=None)` | Read a bundled text file, or invoke a callable resource. |
| `run_skill_script` | `(skill_name, script_name, args=None)` | Execute a bundled script through the configured executor. |

Both are omitted entirely when no skill ships files of the matching kind.

## Agent specs

`SkillsCapability` works with Pydantic AI's
[YAML and JSON agent specs](https://ai.pydantic.dev/core-concepts/agent-spec/):

```yaml
model: anthropic:claude-sonnet-4-6
capabilities:
  - SkillsCapability:
      directories: ['./skills']
      include: ['pdf-processing']
      scripts: false
```

```python
agent = Agent.from_file('agent.yaml', custom_capability_types=[SkillsCapability])
```

Registries, programmatic skills and custom executors cannot be expressed in a spec — construct the
capability in Python for those.

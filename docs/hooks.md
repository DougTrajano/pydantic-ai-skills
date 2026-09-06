# Hooks Around Skill Loading

You can intercept the moment an agent loads a skill — before and after — using Pydantic AI's
[hooks](https://ai.pydantic.dev/core-concepts/hooks/). No special support is required from this
library.

## Why this works

Every skill is a **deferred capability**, and the model loads one by calling Pydantic AI's built-in
`load_capability` tool with the skill's name as `id`. That is an ordinary tool call, so the standard
tool-execution hooks fire around it.

The tools involved:

| Tool | Provided by | Fires when |
|------|-------------|------------|
| `load_capability` | Pydantic AI | the model loads a skill's instructions |
| `read_skill_resource` | this package | the model reads a bundled file |
| `run_skill_script` | this package | the model executes a bundled script |

There is no `list_skills` tool to hook: the catalog is injected as instructions, not fetched. And
there is no `load_skill` tool — v1 had one, but the framework's `load_capability` replaced it. If
you are porting hooks from v1, see [Migrating from v1](migration-v2.md).

## Quick start

Register a `Hooks` capability alongside your skills, filtering each hook to the tool by name. The
hook callbacks take keyword-only `call`, `tool_def`, and `args`; the `before` hook returns the
(possibly modified) args, and the `after` hook returns the (possibly modified) result.

```python
from pydantic_ai import Agent
from pydantic_ai.capabilities import Hooks
from pydantic_ai_skills import SkillsCapability

hooks = Hooks()


@hooks.on.before_tool_execute(tools=['load_capability'])
async def before_load(ctx, *, call, tool_def, args):
    """Runs just before a skill's instructions are loaded."""
    print(f'About to load: {args["id"]}')
    return args


@hooks.on.after_tool_execute(tools=['load_capability'])
async def after_load(ctx, *, call, tool_def, args, result):
    """Runs once the instructions have been loaded."""
    print(f'Loaded: {args["id"]}')
    return result


agent = Agent(
    'anthropic:claude-sonnet-4-6',
    capabilities=[SkillsCapability('./skills'), hooks],
)
```

The argument is `id`, not `skill_name` — `load_capability` is the framework's tool and takes the
capability id, which for a skill is its name.

!!! warning "`load_capability` is shared"
    Every deferred capability in the agent loads through the same tool, not just skills. If your
    agent has other deferred capabilities, check the id before acting:

    ```python
    SKILL_NAMES = set(capability.skill_names)


    @hooks.on.before_tool_execute(tools=['load_capability'])
    async def before_load(ctx, *, call, tool_def, args):
        if args['id'] in SKILL_NAMES:
            audit_log.record('skill_loaded', args['id'])
        return args
    ```

## Auditing bundled-file access

The tools this package adds take `skill_name` as their first argument, so filtering is direct:

```python
@hooks.on.before_tool_execute(tools=['run_skill_script'])
async def before_script(ctx, *, call, tool_def, args):
    audit_log.record('script_run', skill=args['skill_name'], script=args['script_name'])
    return args
```

This is the seam for policy enforcement — refusing scripts from particular skills, rate-limiting
execution, or recording what ran. It is *not* a security boundary on its own; see
[Security](security.md).

## Blocking a load

Raise from a `before` hook to stop the tool running. Use `ModelRetry` when the model can recover:

```python
from pydantic_ai import ModelRetry

ALLOWED = {'pdf-processing', 'data-analysis'}


@hooks.on.before_tool_execute(tools=['load_capability'])
async def restrict(ctx, *, call, tool_def, args):
    if args['id'] not in ALLOWED:
        raise ModelRetry(f'{args["id"]} is not available in this context.')
    return args
```

For a fixed allowlist, `include=` on the capability is simpler and cheaper — the skill never reaches
the catalog at all:

```python
SkillsCapability('./skills', include=['pdf-processing', 'data-analysis'])
```

Reach for a hook when the decision depends on run state — the user's permissions, a quota, the time
of day — rather than being known at construction.

## Observing without intercepting

If all you want is telemetry, Pydantic AI's
[instrumentation](https://ai.pydantic.dev/logfire/) already records every tool call with its
arguments, including `load_capability`. Reach for hooks when you need to *change* behaviour.

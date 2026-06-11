# Hooks Around Skill Loading

You can intercept the moment an agent loads a skill — before and after — using Pydantic AI's
[hooks](https://ai.pydantic.dev/core-concepts/hooks/). No special support is required from this
library: skill loading is a **regular tool call** named `load_skill`, so the standard
tool-execution hooks fire around it.

## Why this works

Both `SkillsToolset` and `SkillsCapability` register the same four tools on the agent:

| Tool | Fires when |
|------|------------|
| `list_skills` | the agent enumerates available skills |
| `load_skill` | the agent loads a skill's full instructions |
| `read_skill_resource` | the agent reads a skill resource |
| `run_skill_script` | the agent executes a skill script |

"The agent decides to load a skill" means it calls the `load_skill` tool with a `skill_name`.
That is the only observable decision point — the available-skills list is injected as instructions,
and the model commits by calling the tool. Hooking `load_skill` is the correct (and only) seam.

## Quick start

Register a `Hooks` capability alongside your skills, filtering each hook to the `load_skill` tool by
name. The hook callbacks take keyword-only `call`, `tool_def`, and `args`; the `before` hook returns
the (possibly modified) args, and the `after` hook returns the (possibly modified) result.

```python
from pydantic_ai import Agent
from pydantic_ai.capabilities import Hooks
from pydantic_ai_skills import SkillsCapability

hooks = Hooks()


@hooks.on.before_tool_execute(tools=['load_skill'])
async def before_load_skill(ctx, *, call, tool_def, args):
    """Runs just before a skill is loaded."""
    print(f'About to load skill: {args["skill_name"]}')
    return args  # must return the args dict (modify it to rewrite the request)


@hooks.on.after_tool_execute(tools=['load_skill'])
async def after_load_skill(ctx, *, call, tool_def, args, result):
    """Runs after the skill instructions are returned to the model."""
    print(f'Loaded {args["skill_name"]} ({len(result)} chars)')
    return result  # must return the result (modify it to rewrite what the model sees)


agent = Agent(
    'openai:gpt-5.2',
    capabilities=[
        SkillsCapability(directories=['./skills']),
        hooks,
    ],
)
```

!!! note "`SkillsToolset` works the same way"
    If you integrate via `toolsets=[SkillsToolset(...)]` instead of `capabilities=[...]`, the hook
    setup is identical — the tool names are the same. Just keep the `Hooks` instance in
    `capabilities=[...]` and your toolset in `toolsets=[...]`.

## The tool-execution hook family

Each phase of a tool call has a matching hook, all of which accept the `tools=[...]` filter:

| Hook | Fires | Use for |
|------|-------|---------|
| `before_tool_validate` | raw JSON args parsed | inspect/reject a `skill_name` before validation |
| `before_tool_execute` | just before the load runs | logging, auth checks, **aborting** the load |
| `after_tool_execute` | the load returned | auditing, **rewriting** the loaded instructions |
| `wrap_tool_execute` | around the call | timing, `try`/`finally`, retries |
| `tool_execute_error` | the load raised | error handling / fallback results |

The same pattern targets `run_skill_script` and `read_skill_resource` — handy for gating script
execution or auditing resource reads:

```python
@hooks.on.before_tool_execute(tools=['run_skill_script'])
async def audit_script(ctx, *, call, tool_def, args):
    print(f'Running {args["script_name"]} from {args["skill_name"]}')
    return args
```

## Blocking a skill load

Raise `SkipToolExecution` from a `before_tool_execute` hook to prevent the load and feed a message
back to the model instead of running the tool:

```python
from pydantic_ai import SkipToolExecution

ALLOWED = {'data-analysis', 'reporting'}


@hooks.on.before_tool_execute(tools=['load_skill'])
async def gate_skill_loads(ctx, *, call, tool_def, args):
    skill_name = args['skill_name']
    if skill_name not in ALLOWED:
        raise SkipToolExecution(
            f"Skill '{skill_name}' is not permitted in this context."
        )
    return args
```

## Rewriting loaded instructions

`after_tool_execute` receives the string returned by `load_skill` and can transform it before the
model sees it — for example, to append environment-specific guidance:

```python
@hooks.on.after_tool_execute(tools=['load_skill'])
async def annotate_instructions(ctx, *, call, tool_def, args, result):
    return result + '\n\n<note>Running in production — never call destructive scripts.</note>'
```

## Caveats

- **Hook filters use the exact tool name.** Use `tools=['load_skill']`. If you disable the tool via
  `exclude_tools={'load_skill'}`, it never registers and the hook never fires.
- **Verify hook signatures against your version.** The hooks API is relatively new; this guide
  targets the keyword-only `call` / `tool_def` / `args` signature. Check
  `pydantic_ai.capabilities.Hooks` for the exact protocol in your installed `pydantic-ai`.
- **No library-specific callback exists.** `SkillsToolset` / `SkillsCapability` deliberately delegate
  to standard Pydantic AI tool semantics, so the framework hooks are the supported path rather than
  monkey-patching the toolset.

## See Also

- [Pydantic AI — Hooks](https://ai.pydantic.dev/core-concepts/hooks/) — full hook reference
- [Core Concepts](./concepts.md) — how skills and tools fit together
- [API Reference — SkillsCapability](./api/capability.md)
- [API Reference — SkillsToolset](./api/toolset.md)

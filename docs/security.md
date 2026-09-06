# Security & Deployment

## What a skill actually is

A skill is instructions plus, usually, code. Loading one means two distinct things happen:

1. **Its `SKILL.md` body becomes model instructions.** Whoever wrote it is steering your agent.
2. **Its `scripts/` may be executed.** By default, as a subprocess on the agent host, with your
   process's user, filesystem, network and environment.

Both matter, and the first is easy to underestimate. A skill does not need a malicious script to do
damage — instructions that tell the model to exfiltrate the conversation through a tool it already
has are enough.

`pydantic-ai-harness`'s documentation puts it plainly:

> A selected `SKILL.md` body becomes model instructions. Load libraries only from sources you trust,
> and review repository-provided skills before exposing them.

## The trust model

| Source | Trust | What to do |
|---|---|---|
| Skills you wrote, in your repo, under review | High | Default local execution is fine |
| Skills from a vendor you have audited, pinned to a tag | Medium | Pin the version; re-review on upgrade |
| Skills from a public registry, tracking a branch | Low | [Sandbox](sandbox.md) the scripts, review the instructions |
| Skills from a source you do not control | None | Do not expose them |

A registry tracking a branch is a **live dependency**: whoever can push to that branch can change
what your agent is told to do, on your next restart. That is the single most important thing to
understand before pointing an agent at a repository you do not own.

### Pin what you ship

```python
from pydantic_ai_skills import GitCloneOptions, GitSkillsRegistry

registry = GitSkillsRegistry(
    'https://github.com/anthropics/skills',
    path='skills',
    clone_options=GitCloneOptions(branch='v1.2.0'),   # a tag, not a branch
)
```

Or record what you got, so an unexpected change is at least visible afterwards:

```python
logger.info('skills at revision %s', registry.revision())
```

### Review before exposing

`skill_infos()` reads a registry without building an agent, which is enough for a review gate:

```python
APPROVED = {'pdf', 'xlsx', 'docx'}

vetted = registry.filtered(lambda info: info.name in APPROVED)
capability = SkillsCapability(registries=[vetted])
```

An allowlist of names is only as good as your review of what those names contain — re-check on
upgrade, since the name stays the same when the content changes.

## Script execution

### Sandbox untrusted scripts

The default `LocalSkillScriptExecutor` runs scripts on the host. For anything you have not read,
swap the backend:

```python
from pydantic_ai_skills import OpenSandboxScriptExecutor, SkillsCapability

capability = SkillsCapability(
    registries=[registry],
    script_executor=OpenSandboxScriptExecutor(),
)
```

One executor covers every skill the capability exposes, so a source added later cannot quietly fall
back to host execution. See [Sandboxing](sandbox.md) for both bundled implementations and their
trade-offs.

### Bound the runtime

```python
from pydantic_ai_skills import LocalSkillScriptExecutor

LocalSkillScriptExecutor(timeout=30)
```

Without a timeout a hung script hangs the agent run.

### Control the environment

Scripts inherit the environment you give them, and nothing more than you give them:

```python
executor = LocalSkillScriptExecutor(
    env_vars={'AWS_REGION': 'us-east-1'},
    context_env_vars_extractor=lambda ctx: {'TENANT_ID': ctx.deps.tenant_id},
)
```

Do not pass credentials a skill does not need. A script that receives `AWS_SECRET_ACCESS_KEY`
because it was in the ambient environment can use it.

### Turning execution off entirely

```python
SkillsCapability('./skills', scripts=False)
```

This is a real boundary — the tool is not registered, so the model cannot call it. Weigh it against
a sandbox: a skill whose instructions describe running a script it cannot run tends to make the model
improvise something worse.

## Containment this package does enforce

These are properties of the implementation, not advice:

- **Symlink escape.** A resource or script whose path resolves outside its skill directory is
  skipped with a `UserWarning`, during both indexing and sandbox staging. Without this, a skill
  could hand the model, or execute, an arbitrary file on the host.
- **Path traversal on copy.** Staging a composed registry and downloading S3 objects both reject
  destinations that would escape the target directory, so a crafted skill name or object key cannot
  write outside the cache.
- **Credential masking.** A Git token is never in `repr()` or in an error message, and `.git`
  metadata (which can carry a tokenized clone URL) is excluded from sandbox staging.
- **SSH key permissions.** A key file readable by group or other produces a warning.

## Containment this package does *not* provide

Be clear about the gaps:

- **`exclude` is not access control.** It keeps a skill out of the model's catalog. The files remain
  on disk and readable by everything else in the process.
- **Directory paths are not a jail.** Passing `./skills` chooses where discovery starts. It does not
  confine anything, and normal symlink resolution applies to the library path itself. If you need
  filesystem containment, run the agent in an environment that provides it.
- **`require_loaded` is a disclosure boundary, not a permission.** It keeps the model from reading a
  skill's files before loading the skill. It does not stop a loaded skill from doing anything.
- **Frontmatter restrictions are inert.** harness accepts `allowed-tools`, `disable-model-invocation`,
  `model` and similar fields for compatibility but does not implement them, warning at construction.
  A skill that declares `allowed-tools: [Read]` is **not** restricted here. Never treat a skill's own
  frontmatter as a sandbox.
- **Instructions are not validated.** Nothing scans a `SKILL.md` body for prompt injection. Review it.

## Auditing

Every skill load is a `load_capability` tool call, and every file access is a
`read_skill_resource` or `run_skill_script` call. Both are ordinary tool calls, so Pydantic AI's
[instrumentation](https://ai.pydantic.dev/logfire/) records them with their arguments.

For an enforcement point rather than a record, use [hooks](hooks.md):

```python
from pydantic_ai import ModelRetry
from pydantic_ai.capabilities import Hooks

hooks = Hooks()
SKILL_NAMES = set(capability.skill_names)


@hooks.on.before_tool_execute(tools=['load_capability'])
async def audit_load(ctx, *, call, tool_def, args):
    if args['id'] in SKILL_NAMES:
        audit_log.record('skill_loaded', skill=args['id'], user=ctx.deps.user_id)
    return args


@hooks.on.before_tool_execute(tools=['run_skill_script'])
async def gate_scripts(ctx, *, call, tool_def, args):
    if not ctx.deps.user.may_run_scripts:
        raise ModelRetry('Script execution is not available for this user.')
    audit_log.record('script_run', skill=args['skill_name'], script=args['script_name'])
    return args
```

Hooks run in your process and can be bypassed by nothing the model does — but they gate *tool
calls*, not what a script does once running. Sandboxing is the boundary for the latter.

## Production deployment

### Configuration

Make the trust decisions explicit and reviewable, rather than defaults inherited by accident:

```python
from dataclasses import dataclass, field

from pydantic_ai_skills import (
    LocalSkillScriptExecutor,
    OpenSandboxScriptExecutor,
    SkillsCapability,
    SkillRegistry,
)


@dataclass
class SkillsConfig:
    directories: list[str] = field(default_factory=list)
    registries: list[SkillRegistry] = field(default_factory=list)
    include: list[str] | None = None
    sandbox_scripts: bool = True
    script_timeout: int = 30


def build_capability(config: SkillsConfig) -> SkillsCapability:
    executor = (
        OpenSandboxScriptExecutor(timeout=config.script_timeout)
        if config.sandbox_scripts
        else LocalSkillScriptExecutor(timeout=config.script_timeout)
    )
    return SkillsCapability(
        config.directories,
        registries=config.registries,
        include=config.include,
        script_executor=executor,
    )
```

### Fail fast at startup

Construction validates everything: malformed frontmatter, mismatched names, duplicates, unknown
`include` entries, unreachable registries. Let it fail rather than starting an agent with half a
catalog:

```python
def startup() -> Agent:
    capability = build_capability(config)   # raises on any misconfiguration
    logger.info('exposing %d skills: %s', len(capability.skill_names), capability.skill_names)
    return Agent(settings.model, capabilities=[capability])
```

An agent silently missing half its skills is harder to diagnose than one that refuses to start.

### Health check

```python
def check_skills(capability: SkillsCapability) -> dict:
    return {
        'skills': capability.skill_names,
        'with_scripts': [
            name for name, package in capability.packages.items() if package.scripts
        ],
    }
```

### Picking up upstream changes

Discovery is a construction-time snapshot, so a running process never re-reads a registry. Rebuild
on a redeploy, or on a schedule — see [Advanced Features](advanced.md#picking-up-changes-to-skills).

Treat each rebuild as re-taking the dependency: whatever the upstream branch says now is what your
agent will be told next.

## Checklist

Before pointing an agent at skills you did not write:

- [ ] Read the `SKILL.md` bodies, not just the names and descriptions
- [ ] Read the `scripts/`
- [ ] Pin a tag or commit rather than tracking a branch
- [ ] Sandbox script execution, or turn it off
- [ ] Set a script timeout
- [ ] Pass only the environment variables the skills need
- [ ] Narrow the catalog with `include`
- [ ] Log skill loads and script runs
- [ ] Decide, deliberately, what should happen when the registry is unreachable

## See also

- [Sandboxing](sandbox.md) — the two bundled executors and their trade-offs
- [Hooks](hooks.md) — gating and auditing skill loads
- [Registries](registries.md) — pinning, caching, and offline sources
- [Advanced Features](advanced.md) — selection and rebuild strategies

# Advanced Features

## Selecting which skills to expose

A skill directory grows. Not every agent should see everything in it.

```python
from pydantic_ai_skills import SkillsCapability

# Only these
SkillsCapability('./skills', include=['pdf-processing', 'data-analysis'])

# Everything except these
SkillsCapability('./skills', exclude=['experimental', 'internal-debug'])

# Nothing
SkillsCapability('./skills', include=[])
```

| Configuration | Skills in the catalog |
|---|---|
| Neither | All discovered skills |
| `include=['a', 'b']` | Only `a` and `b` |
| `include=[]` | No skills |
| `exclude=['a', 'b']` | All except `a` and `b` |

The two cannot be combined, and a name matching nothing raises at construction — so a typo fails
where you can see it, rather than silently narrowing the catalog.

Selection covers every source: `include=['my-python-skill']` works for a skill passed via `skills=`
just as it does for one on disk.

!!! warning "This is catalog exposure, not access control"
    `exclude` keeps a skill out of the prompt. It is not a filesystem permission and not a security
    boundary — the files are still on disk and still readable by anything else in the process. See
    [Security](security.md).

### Selection by source

To give different agents different subsets of the *same* registry, filter the registry rather than
the capability:

```python
from pydantic_ai_skills import GitSkillsRegistry, SkillsCapability

source = GitSkillsRegistry('https://github.com/anthropics/skills', path='skills')

docs_agent = SkillsCapability(registries=[source.filtered(lambda info: 'doc' in info.description)])
data_agent = SkillsCapability(registries=[source.filtered(lambda info: 'data' in info.name)])
```

See [Registries](registries.md#composition) for the full composition story.

## Picking up changes to skills

Discovery is a snapshot taken at construction. There is no `reload()`, and no `auto_reload` — v1 had
both, and neither was coherent: an agent's instructions and tools are fixed for a run.

Rebuild instead:

```python
from pydantic_ai import Agent
from pydantic_ai_skills import SkillsCapability


def build_agent() -> Agent:
    return Agent('anthropic:claude-sonnet-4-6', capabilities=[SkillsCapability('./skills')])


agent = build_agent()
```

For a long-lived server, rebuild on a redeploy, or on a schedule, and swap the reference:

```python
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

state: dict[str, Agent] = {}


async def refresh_hourly() -> None:
    while True:
        await asyncio.sleep(3600)
        state['agent'] = build_agent()  # registries re-sync here


@asynccontextmanager
async def lifespan(app: FastAPI):
    state['agent'] = build_agent()
    task = asyncio.create_task(refresh_hourly())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)
```

Rebuilding also re-syncs every registry, which is how you pick up new skills published upstream.
Note that a registry's `sync()` does real work — a `git pull`, an S3 listing — so rebuild on a
schedule you would be happy to see in your egress logs.

## Skills defined in Python

The `@skill` decorator builds a skill from a function returning its instructions:

```python
from pydantic_ai import Agent, RunContext
from pydantic_ai_skills import SkillsCapability, skill


@skill(metadata={'version': '1.0.0'}, license='MIT')
def analytics() -> str:
    """Analyze application data and generate reports."""
    return """
    Use this skill for questions about usage and revenue.
    Read the `schema` resource before writing a query, then run `report`.
    """


@analytics.resource
async def schema(ctx: RunContext[AppDeps]) -> str:
    """The current warehouse schema."""
    return await ctx.deps.database.get_schema()


@analytics.script
async def report(ctx: RunContext[AppDeps], period: str = 'week') -> str:
    """Generate a usage report for a period."""
    return await ctx.deps.database.generate_report(period)


agent = Agent(
    'openai:gpt-5.2',
    deps_type=AppDeps,
    capabilities=[SkillsCapability(skills=[analytics])],
)
```

The name comes from the function (`analytics`), the description from its docstring. Both can be
overridden with `name=` and `description=`.

Because these are ordinary Python functions, they get dependency injection, type checking, and
direct unit testing — see [Programmatic Skills](programmatic-skills.md).

## Dependency injection via `RunContext`

Any resource or script on a programmatic skill can take `RunContext` as its first parameter and
reach the agent's dependencies:

```python
from dataclasses import dataclass

from pydantic_ai import Agent, RunContext
from pydantic_ai_skills import Skill, SkillsCapability


@dataclass
class AppDeps:
    database: DatabaseConn
    tenant_id: str


tenant_data = Skill(
    name='tenant-data',
    description='Query the current tenant\'s records.',
    content='Read `summary` first, then run `query` with a SQL string.',
)


@tenant_data.resource
async def summary(ctx: RunContext[AppDeps]) -> str:
    """A summary of the tenant's data."""
    return await ctx.deps.database.summarize(ctx.deps.tenant_id)


@tenant_data.script
async def query(ctx: RunContext[AppDeps], sql: str) -> str:
    """Run a read-only query scoped to the tenant."""
    return str(await ctx.deps.database.execute(sql, tenant=ctx.deps.tenant_id))


agent = Agent(
    'openai:gpt-5.2',
    deps_type=AppDeps,
    capabilities=[SkillsCapability(skills=[tenant_data])],
)
result = await agent.run('How many records do we have?', deps=AppDeps(db, tenant_id='acme'))
```

Scoping by `ctx.deps` is the right way to keep one tenant's data away from another's — far better
than hoping the model respects an instruction saying so.

File-based scripts do not receive `RunContext`; they run as subprocesses. To pass request-scoped
values to them, see [environment variables](creating-skills.md#script-environment-variables).

## Custom script executors

`run_skill_script` routes every file-based script through a
[`SkillScriptExecutor`][pydantic_ai_skills.SkillScriptExecutor]. The protocol is structural — one
`async def run(script, args=None, ctx=None)` — so anything matching it works:

```python
from typing import Any

from pydantic_ai_skills import SkillScript, SkillsCapability


class RemoteExecutor:
    """Run scripts on a worker instead of the agent host."""

    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint

    async def run(
        self,
        script: SkillScript,
        args: dict[str, Any] | None = None,
        ctx: Any | None = None,
    ) -> str:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.endpoint,
                json={'uri': script.uri, 'args': args or {}},
                timeout=60,
            )
            return response.text


capability = SkillsCapability('./skills', script_executor=RemoteExecutor('https://worker/run'))
```

One executor covers every skill the capability exposes, wherever it came from. In v1 the executor
lived on each source, which made it easy to add a registry and quietly fall back to host execution.

Two executors ship with the package for keeping untrusted scripts off the host — see
[Sandboxing](sandbox.md). `CallableSkillScriptExecutor` wraps a plain callable, which is useful for
tests:

```python
from pydantic_ai_skills import CallableSkillScriptExecutor

recorded = []


def fake_run(script, args=None, ctx=None):
    recorded.append((script.name, args))
    return 'stubbed output'


capability = SkillsCapability('./skills', script_executor=CallableSkillScriptExecutor(fake_run))
```

## Turning off the file tools

```python
SkillsCapability('./skills', scripts=False)                     # no run_skill_script
SkillsCapability('./skills', resources=False)                   # no read_skill_resource
SkillsCapability('./skills', resources=False, scripts=False)    # neither
```

With both off this behaves like harness `Skills` on its own — at which point, use harness directly.

Prefer a [sandbox executor](sandbox.md) over `scripts=False` when the problem is trust rather than
capability: a skill whose instructions describe running a script it cannot run tends to make the
model improvise.

Both tools are also omitted automatically when no skill ships files of that kind, so a capability
over instructions-only skills adds nothing to the model's tool list.

## Gating file access on the loaded skill

By default the file tools refuse a skill the model has not loaded:

```text
Skill 'pdf-processing' is not loaded. Call load_capability with id='pdf-processing' first,
then read its files.
```

That keeps bundled files behind the same boundary as the skill's instructions. Turn it off when a
skill's files should be reachable regardless:

```python
SkillsCapability('./skills', require_loaded=False)
```

This reads `RunContext.active_capability_ids`, which is refreshed from message history before each
request — so a skill loaded in an earlier step is visible, and only a call issued in the *same* step
as the load is refused, with a retry the model can act on.

## Listing a skill's bundled files

The file tools key on skill-relative paths (`scripts/aggregate.py`), while a `SKILL.md` names its
own files however its author wrote the prose. `SkillsCapability` appends the real names to the
skill's instructions so the model reads them instead of guessing:

```python
SkillsCapability('./skills')                              # inventory appended (the default)
SkillsCapability('./skills', list_bundled_files=False)    # instructions as harness rendered them
```

The listing rides on the instructions, so it stays behind `load_capability` and costs nothing for
skills the model never loads. Only kinds whose tool is registered are listed — `scripts=False`
drops the script block — and each kind is truncated after 50 entries.

Independently of the listing, both tools accept an unambiguous shorthand: `aggregate` and
`aggregate.py` both reach `scripts/aggregate.py`. When two files share a name, neither is chosen;
the retry names both and asks for the full path. See
[Bundled-file inventory](concepts.md#bundled-file-inventory).

## Resolving `${SKILL_DIR}`

Published skill packages often write paths as `${SKILL_DIR}/scripts/run.py` or
`${CLAUDE_SKILL_DIR}/...`. harness passes the placeholder through untouched. `SkillsCapability`
substitutes the skill's real directory:

```python
SkillsCapability('./skills')                            # resolved (the default)
SkillsCapability('./skills', resolve_skill_dir=False)   # exactly what harness rendered
```

Turn it off when you want byte-identical instructions to a plain `Skills` setup, or when the literal
placeholder means something to your own tooling.

## Skill metadata

Extra `SKILL.md` frontmatter keys are accepted, but nothing in the runtime reads them — harness acts
only on `name` and `description`.

```yaml
---
name: pdf-processing
description: Fill and extract PDF forms.
version: 2.1.0
owner: platform-team
---
```

Treat those as documentation for your own tooling. In particular, the behavioural fields other Agent
Skills clients define — `allowed-tools`, `model`, `hooks`, `disable-model-invocation` and friends —
are accepted and **inert**; harness warns about them at construction. A skill relying on
`allowed-tools` to restrict itself is not restricted here.

For metadata the runtime *does* act on, use [programmatic skills](programmatic-skills.md), where
`metadata=` is yours to read back.

## Mixed sources

Local directories, registries, and Python-defined skills all land in one catalog:

```python
from pydantic_ai_skills import GitSkillsRegistry, S3SkillsRegistry, SkillsCapability, skill


@skill
def runtime_config() -> str:
    """Read the deployment's runtime configuration."""
    return 'Consult the deployment config before answering environment questions.'


capability = SkillsCapability(
    './skills',                                    # committed alongside the app
    registries=[
        GitSkillsRegistry(                         # published upstream
            'https://github.com/anthropics/skills',
            path='skills',
        ).prefixed('anthropic-'),
        S3SkillsRegistry(bucket='acme-skills'),    # distributed internally
    ],
    skills=[runtime_config],                       # defined in Python
)
```

Names must be unique across all of them, since each becomes a capability id. A programmatic skill
shadowing a directory-backed one wins with a warning; two registries colliding are resolved by
`CombinedRegistry` or by prefixing, as above.

## See also

- [Core Concepts](concepts.md) — what runs when, and who does what
- [Registries](registries.md) — remote sources and composition
- [Sandboxing](sandbox.md) — keeping untrusted scripts off the host
- [Hooks](hooks.md) — intercepting skill loads and file access
- [Security](security.md) — the trust model
- [Migrating from v1](migration-v2.md) — hot-reload, instruction templates, and what replaced them

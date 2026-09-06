# Implementation Patterns

Recipes for common situations. Each one states the problem first, so you can tell whether it is
yours.

## Skill selection

### Give each agent only what it needs

A shared skill directory serves several agents, but each should see a subset — a hundred catalog
entries in the prompt is a hundred entries the model has to read past.

```python
from pydantic_ai import Agent
from pydantic_ai_skills import SkillsCapability

support = Agent(
    'openai:gpt-5.2',
    capabilities=[SkillsCapability('./skills', include=['refunds', 'order-lookup'])],
)
research = Agent(
    'openai:gpt-5.2',
    capabilities=[SkillsCapability('./skills', include=['arxiv-search', 'web-research'])],
)
```

An `include` name matching nothing raises at construction, so a renamed skill breaks the build
rather than silently shrinking an agent's catalog.

### Keep work-in-progress skills out

```python
SkillsCapability('./skills', exclude=['draft-invoice-parser'])
```

Better still, keep drafts in a separate directory and add it only in development:

```python
libraries = ['./skills']
if settings.environment == 'development':
    libraries.append('./skills-draft')

capability = SkillsCapability(libraries)
```

### Different subsets of the same remote source

Filter the registry rather than the capability, so each agent's copy is staged independently:

```python
from pydantic_ai_skills import GitSkillsRegistry

source = GitSkillsRegistry('https://github.com/anthropics/skills', path='skills')

office = SkillsCapability(registries=[source.filtered(lambda info: info.name in {'pdf', 'xlsx', 'docx'})])
```

## Writing descriptions the model can act on

The description is the *only* thing the model sees before loading a skill. It answers one question:
should I load this?

```yaml
# Too vague — the model cannot tell when this applies
description: Helps with documents.

# Better — says what it does and when to reach for it
description: >
  Fill and extract data from PDF forms. Use when the user asks to complete a form,
  read values out of a filled PDF, or merge PDFs.
```

The Agent Skills limit is 1,024 characters; harness warns above it rather than truncating. Two
skills with overlapping descriptions is the usual cause of the model loading the wrong one — make
the boundary explicit in both.

## Scripts

### Argument marshalling

`run_skill_script` passes `args` to the script as `--key value` pairs, so `argparse` works as
written:

```python
args = {'query': 'transformers', 'max_results': 3, 'verbose': True, 'tags': ['ml', 'nlp']}
```

becomes:

```text
--query transformers --max_results 3 --verbose --tags ml --tags nlp
```

Booleans become bare flags when true and are omitted when false; lists repeat the flag; `None` is
omitted. Document the arguments in `SKILL.md` — the model chooses them from your prose, not from a
schema.

### Print results, not prose

Script stdout goes back to the model verbatim. Structured output is easier for it to use than a
sentence:

```python
# Good
print(json.dumps({'papers': papers, 'total': len(papers)}, indent=2))

# Worse — the model has to parse English to find the numbers
print(f'I found {len(papers)} papers, the first is {papers[0]["title"]}')
```

### Fail loudly

A script that swallows an error and prints nothing leaves the model guessing. Exit non-zero and
write to stderr; both reach the model:

```python
try:
    result = fetch(args.url)
except TimeoutError:
    print(f'Timed out fetching {args.url}', file=sys.stderr)
    sys.exit(1)
```

### Bound the runtime

The local executor accepts a timeout, so one hung script does not hang the run:

```python
from pydantic_ai_skills import LocalSkillScriptExecutor, SkillsCapability

capability = SkillsCapability(
    './skills',
    script_executor=LocalSkillScriptExecutor(timeout=30),
)
```

## Error handling

The tools this package registers raise `pydantic_ai.ModelRetry` for anything the model can fix — an
unknown skill, resource, or script name, or a skill it has not loaded yet. The message names what is
available, so the model can correct itself within the agent's retry budget:

```text
Resource 'FORMS.md' not found in skill 'pdf-processing'.
Available resources: ['references/FORMS.md', 'references/LAYOUT.md'].
Use the exact name from the skill instructions.
```

Genuine failures — a script exiting non-zero, an unreadable file — are returned as output rather
than raised, so the model can react to them.

Construction-time problems are different: a malformed `SKILL.md`, a mismatched name, a duplicate,
an unknown `include` entry, or a registry that cannot reach its source all raise immediately. That
is deliberate — a misconfigured catalog should fail at startup, not halfway through a user's
request.

```python
try:
    capability = SkillsCapability('./skills', registries=[registry])
except ValueError as exc:
    logger.error('skill configuration is invalid: %s', exc)
    raise
```

## Dependency management

### Request-scoped values in a file-based script

File-based scripts are subprocesses and never see `RunContext`. Pass per-request values through the
environment:

```python
from pydantic_ai_skills import LocalSkillScriptExecutor, SkillsCapability

executor = LocalSkillScriptExecutor(
    env_vars={'AWS_REGION': 'us-east-1'},                       # static
    context_env_vars_extractor=lambda ctx: {                    # per run
        'REQUEST_ID': ctx.deps.request_id,
        'TENANT_ID': ctx.deps.tenant_id,
    },
)

capability = SkillsCapability('./skills', script_executor=executor, deps_type=AppDeps)
```

Scope the *data* by tenant, not just the instructions. A script that reads `TENANT_ID` and filters
on it is a boundary; a `SKILL.md` asking the model to only look at one tenant is not.

### Shared connections in a programmatic skill

When a skill needs a database handle or an API client, define it in Python and reach through
`ctx.deps`:

```python
from pydantic_ai import RunContext
from pydantic_ai_skills import Skill

analytics = Skill(
    name='analytics',
    description='Answer questions about product usage.',
    content='Read `schema`, then run `query` with a read-only SQL string.',
)


@analytics.script
async def query(ctx: RunContext[AppDeps], sql: str) -> str:
    """Run a read-only query."""
    return str(await ctx.deps.database.execute(sql))
```

## Testing

### Assert on the catalog, not the model

What you want to know is that the right skills are exposed with the right files. That needs no
model:

```python
from pydantic_ai_skills import SkillsCapability


def test_support_agent_exposes_only_support_skills() -> None:
    capability = SkillsCapability('./skills', include=['refunds', 'order-lookup'])

    assert capability.skill_names == ['order-lookup', 'refunds']


def test_pdf_skill_ships_its_script() -> None:
    package = SkillsCapability('./skills').packages['pdf-processing']

    assert 'scripts/fill_form.py' in package.scripts_by_name
```

Because an unknown `include` raises, a test that merely constructs the capability already catches a
renamed or deleted skill.

### Drive the tools without a provider

Use `FunctionModel` to script the exact tool calls you want to exercise:

```python
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel


async def test_the_model_can_read_a_skill_resource(tmp_path) -> None:
    steps = [
        ToolCallPart('load_capability', {'id': 'pdf-processing'}),
        ToolCallPart(
            'read_skill_resource',
            {'skill_name': 'pdf-processing', 'resource_name': 'references/FORMS.md'},
        ),
    ]
    calls: list[int] = []

    def model_fn(messages, info):
        calls.append(1)
        step = len(calls) - 1
        if step < len(steps):
            return ModelResponse(parts=[steps[step]])
        return ModelResponse(parts=[TextPart('done')])

    agent = Agent(FunctionModel(model_fn), capabilities=[SkillsCapability('./skills')])
    result = await agent.run('fill in the form')

    assert result.output == 'done'
```

Note `load_capability` takes `id` — it is Pydantic AI's tool, not one this package registers.

!!! warning "`TestModel` does not work here"
    `TestModel` calls every registered tool with synthesized arguments, which means calling
    `load_capability` with an id that does not exist and blowing the retry budget. Use
    `FunctionModel` for anything involving deferred capabilities.

### Stub script execution

```python
from pydantic_ai_skills import CallableSkillScriptExecutor, SkillsCapability

recorded = []


def fake_run(script, args=None, ctx=None):
    recorded.append((script.name, args))
    return '{"papers": []}'


capability = SkillsCapability('./skills', script_executor=CallableSkillScriptExecutor(fake_run))
```

This keeps tests fast and hermetic, and lets you assert on the arguments the model chose.

## Registries

### Cache the clone

The default is a temporary directory that dies with the process, which means re-cloning on every
start. Point it somewhere durable:

```python
GitSkillsRegistry(
    'https://github.com/anthropics/skills',
    path='skills',
    target_dir='~/.cache/agent-skills',
)
```

The second `sync()` becomes a `git pull`.

### Pin what you shipped

`sync()` tracks a moving branch. Record what a deployment actually ran with:

```python
registry = GitSkillsRegistry('https://github.com/anthropics/skills', path='skills')
capability = SkillsCapability(registries=[registry])

logger.info('skills at %s: %s', registry.revision(), capability.skill_names)
```

To pin rather than record, clone a tag with `GitCloneOptions(branch='v1.2.0')`.

### Survive an unreachable source at startup

A registry that cannot reach its source raises during construction, which will take your process
down with it. Decide deliberately whether that is what you want:

```python
def build_capability() -> SkillsCapability:
    try:
        return SkillsCapability('./skills', registries=[remote])
    except (ValueError, RuntimeError) as exc:
        logger.warning('remote skills unavailable, continuing with local only: %s', exc)
        return SkillsCapability('./skills')
```

Degrading like this changes what the agent can do, so log it loudly. For a deployment that must not
drift, prefer failing fast — an agent silently missing half its skills is harder to diagnose than
one that refuses to start.

### Air-gapped deployments

Mirror the repository at build time and turn off fetching at run time:

```python
GitSkillsRegistry(
    'https://github.com/anthropics/skills',
    target_dir='/opt/skills-mirror',
    auto_install=False,   # sync() never reaches the network
)
```

### Resolve a name collision

Two registries shipping a `pdf` skill cannot both be exposed — each name becomes a capability id.
`CombinedRegistry` picks the first and warns. To keep both:

```python
combined = internal.prefixed('acme-') | public.prefixed('anthropic-')
```

## See also

- [Core Concepts](concepts.md) — what runs when
- [Registries](registries.md) — the full composition story
- [Sandboxing](sandbox.md) — untrusted scripts
- [Security](security.md) — the trust model
- [Advanced Features](advanced.md) — selection, executors, and rebuild strategies

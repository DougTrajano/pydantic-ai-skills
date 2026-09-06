---
description: Review pydantic-ai and pydantic-ai-harness releases published since the last watch entry, and record a verdict in .github/upstream-watch.md
allowed-tools: Bash, Read, Grep, Glob, Edit, Write, WebFetch
---

# Upstream watch

Two upstream projects can break this package without any change here:

- **pydantic-ai** — it wraps the framework and imports several of its **private** symbols,
  which no deprecation policy protects.
- **pydantic-ai-harness** — a **required runtime dependency** since v2.
  [`SkillsCapability`](../../pydantic_ai_skills/capability.py) is built directly on its
  public `Skills` class, and harness is on `0.x` releases where
  [its own README](https://github.com/pydantic/pydantic-ai-harness#version-policy) says the
  API may change between minor releases.

This routine is the standing review that catches both. It produces one entry in
`.github/upstream-watch.md` and, when action is needed, the issue or PR that fixes it.

Run it weekly, or on demand before a release.

## 1. Establish the lower bound

Read the **top entry** of `.github/upstream-watch.md`. Its two "checked through" tags are
the lower bound for this run — you are reviewing everything published *after* them. Note
today's date for the new entry heading.

## 2. Collect the releases

```bash
gh release list --repo pydantic/pydantic-ai --limit 40
gh release list --repo pydantic/pydantic-ai-harness --limit 20
```

Everything newer than the lower bound is in scope **for both repositories**. The
`pydantic-ai` `v1.x` backport line is *not*: `pyproject.toml` declares
`pydantic-ai-slim>=2.38`, so v1 is no longer a supported configuration. (Entries before
2026-09 reviewed it because the floor was then `>=1.105` — that is why the log mentions it.)

Read each release body with `gh release view <tag> --repo <repo>`. When a release note is
ambiguous about what a PR actually touched, open the PR's file list rather than guessing —
past entries in the log did exactly this, and it is what turned a scary-sounding release
note into a confident "no action".

## 3. Assess impact against what this package actually uses

Two narrow surfaces. Check each release against them specifically.

### 3a. pydantic-ai private imports

The real risk — no deprecation policy protects these:

- `pydantic_ai._function_schema` → `FunctionSchema`, `function_schema`, used in
  [types.py](../../pydantic_ai_skills/types.py)
- `pydantic_ai._griffe` → `doc_descriptions`, called in
  [types.py](../../pydantic_ai_skills/types.py) as
  `doc_descriptions(f, sig, docstring_format='auto')` — verify the *signature and return
  shape*, not just that the module still exists
- `pydantic_ai._utils` → `is_async_callable`, `run_in_executor`, used in
  [local.py](../../pydantic_ai_skills/local.py)
- `pydantic_ai.tools.GenerateToolJsonSchema` (public, but tracked alongside them)

[tests/test_pydantic_ai_compat.py](../../tests/test_pydantic_ai_compat.py) is the tripwire
for these. If a symbol moved, that test is what must be updated — keep it in sync with what
the code actually imports.

One annotation is **not** covered by that tripwire and cannot be:
[types.py](../../pydantic_ai_skills/types.py) annotates four decorators as
`_function_schema.DocstringFormat`, which does not exist at runtime — `DocstringFormat` is
public (`pydantic_ai.tools`) and `_function_schema` only re-exports it under
`if TYPE_CHECKING`. The annotation resolves for mypy and never evaluates at runtime because
`types.py` uses `from __future__ import annotations`. So an upstream release that drops that
`TYPE_CHECKING` import would break `mypy` here while every test still passes. Check it by
running `mypy`, not by running `pytest`. (Pre-dates v2; noted here because release notes
will never mention a `TYPE_CHECKING` import.)

Also relevant on the pydantic-ai side:

- **`AbstractCapability`** — the base class behind `SkillsCapability`, which overrides
  `apply` and `visit_and_replace` to expose one deferred leaf per skill, and `get_toolset`
  to contribute the bundled-file tools. The invariants those overrides rely on are recorded
  in [AGENTS.md](../../AGENTS.md); a change to how a container's contributions are collected
  reaches them.
- **`AbstractToolset` and `RunContext`** — every tool in
  [_toolset.py](../../pydantic_ai_skills/_toolset.py) takes `ctx: RunContext[Any]` first,
  and the `require_loaded` gate reads `ctx.active_capability_ids`.

### 3b. The harness `Skills` surface

`SkillsCapability` constructs `pydantic_ai_harness.Skills` and re-emits the leaves it
produces. What it depends on, all of it public:

- `Skills.__init__` — `directories` positionally, `include` / `exclude` keyword-only
- `Skills.apply()` yields `pydantic_ai.capabilities.Capability` leaves, each with an `id`
  equal to the skill's **directory name**, a `get_instructions()` returning a `list[str]`,
  and **no toolset** of its own
- harness discovers only the **immediate children** of a library, validates that a
  `SKILL.md`'s frontmatter `name` matches its directory, and rejects a library that is
  itself a skill package

[tests/test_harness_compat.py](../../tests/test_harness_compat.py) pins every one of these.
**Running the suite against a new harness release is the fastest way to check it** — that
file is designed to fail loudly rather than let a change surface as odd runtime behaviour.

Two harness changes would **silently change behaviour rather than fail a test**, so read
release notes for them specifically:

- **harness starts loading bundled files or resolving `${SKILL_DIR}`.** Today it
  deliberately does neither, which is the gap this package fills. If that changes,
  `read_skill_resource` / `run_skill_script` and the placeholder substitution in
  `capability.py` would overlap or conflict with harness's own, and `SkillsCapability`
  would need to stop adding them.
- **harness changes how it derives a skill's name from a directory.**
  [packages.py](../../pydantic_ai_skills/packages.py)'s `index_libraries` and
  [_parsing.py](../../pydantic_ai_skills/_parsing.py)'s `validate_skill_name` both mirror
  that rule. If they desynchronize, the bundled-file tools stop finding packages for skills
  that are on the model's catalog — the model sees a skill it cannot read the files of.

### 3c. Harness sets this package's `pydantic-ai-slim` floor

A harness release that raises its own floor may require raising `pydantic-ai-slim` in
[pyproject.toml](../../pyproject.toml) *and* the `floor` pin in the `deps` matrix axis of
[ci.yml](../../.github/workflows/ci.yml).

**The two must move together.** Pinning `pydantic-ai-slim` alone becomes unsatisfiable as
soon as harness raises its floor past that pin — which is why the CI axis is
`floor` / `latest` over the pair rather than three `pydantic-ai-slim` pins.

Not in scope, and worth stating explicitly in the verdict so the next run doesn't re-triage
it: model providers, the local dev web chat UI (`Agent.to_web()`, `clai web`), `web_fetch`,
MCP client support, and durable-execution engines (Temporal, DBOS, Prefect). Harness
features this package does not touch — compaction, spend limits, `Shell`, `FileSystem`,
`CodeMode` — are also out of scope, but say so per release rather than dismissing harness
wholesale: only the `Skills` surface above is load-bearing here.

## 4. Verify empirically when anything looks close

Do not settle a real question by reading release notes alone.

```bash
uv pip install --system --upgrade "pydantic-ai-harness[skills]" pydantic-ai-slim && pytest
```

**Test the declared floor in a clean virtualenv, not by downgrading in place.** Repeated
`--ignore-installed` installs leave a mixed tree that reports one version while running
another, which silently invalidates the result:

```bash
python -m venv /tmp/floor && /tmp/floor/bin/pip install -e ".[test,git,s3]" \
  "pydantic-ai-harness[skills]==0.28.1" "pydantic-ai-slim==2.38.0"
/tmp/floor/bin/python -m pytest
```

This is not a formality. During the v2 work the floor was set to `pydantic-ai-slim` 2.37
because that was harness 0.28's own floor — but `AbstractCapability.visit_and_replace`,
which `SkillsCapability` overrides, only exists from 2.38. Nothing caught it until the
suite was actually run at the declared floor in a clean environment. **Adopting a floor
because a dependency declares it is a guess; running the suite against it is the check.**

Note also that CI's lint job runs `mypy` through pre-commit, in an environment where
*neither* pydantic-ai nor harness is installed — so it type-checks against `Any` and
catches different errors than a local `mypy` does. Reproduce it with
`pre-commit run --all-files` rather than a bare `mypy` when a lint failure looks puzzling.

## 5. Record the entry

Prepend a new `## YYYY-MM-DD` section to `.github/upstream-watch.md`, above the previous
top entry, following the existing format exactly:

- **pydantic/pydantic-ai**: checked through `<tag>` (published `<date>`), reviewed `<range>`
- **pydantic/pydantic-ai-harness**: checked through `<tag>` (published `<date>`), reviewed `<range>`
- **Verdict**: what you concluded and *why*, naming the specific releases, PR numbers, and
  symbols you checked.

Write the verdict so a future reader can tell whether you actually verified something or
merely assumed it. A vague "no breaking changes" entry is worse than useless — it looks like
coverage while providing none. Always close by confirming the status of both the
private-symbol surface and the harness `Skills` surface.

The log is append-only. **Do not edit past entries** — entries before 2026-09 conclude that
harness is out of scope because this package did not depend on it, which was true when they
were written. Leave them as the record of what was known at the time.

## 6. Open the PR

Branch, commit the log entry, and open a PR. If the review found real impact, file the issue
or include the fix, and reference it from the verdict.

**Do not skip the entry when the verdict is "no action".** The log's value is the unbroken
chain of lower bounds; a missing week silently widens the next run's range.

---
description: Review pydantic-ai and pydantic-ai-harness releases published since the last watch entry, and record a verdict in .github/upstream-watch.md
allowed-tools: Bash, Read, Grep, Glob, Edit, Write, WebFetch
---

# Upstream watch

This package wraps Pydantic AI and imports several of its **private** symbols, so an
upstream release can break it without any change here. This routine is the standing
review that catches that. It produces one entry in `.github/upstream-watch.md` and,
when action is needed, the issue or PR that fixes it.

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

Everything newer than the lower bound is in scope, **including the `v1.x` backport line** —
`pyproject.toml` declares `pydantic-ai-slim>=1.105`, and CI tests against `1.105.0`, so a
v1 backport that breaks the floor breaks a supported configuration.

Read each release body with `gh release view <tag> --repo <repo>`. When a release note is
ambiguous about what a PR actually touched, open the PR's file list rather than guessing —
past entries in the log did exactly this, and it is what turned a scary-sounding release
note into a confident "no action".

## 3. Assess impact against what this package actually uses

The surface that can break is narrow. Check each release against it specifically:

- **Private imports** (the real risk — no deprecation policy protects these):
  - `pydantic_ai._function_schema` → `FunctionSchema`, `function_schema`
  - `pydantic_ai._griffe` → `doc_descriptions`, called in
    [pydantic_ai_skills/toolset.py](../../pydantic_ai_skills/toolset.py) as
    `doc_descriptions(f, sig, docstring_format='auto')` — verify the *signature and return
    shape*, not just that the module still exists
  - `pydantic_ai._utils` → `is_async_callable`, `run_in_executor`, used in
    [pydantic_ai_skills/local.py](../../pydantic_ai_skills/local.py)
  - `pydantic_ai.tools.GenerateToolJsonSchema` (public, but tracked alongside them)

  [tests/test_pydantic_ai_compat.py](../../tests/test_pydantic_ai_compat.py) is the tripwire
  for these. If a symbol moved, that test is what must be updated — keep it in sync with
  what the code actually imports.

- **`AbstractToolset` / `AbstractCapability`** — the base classes behind `SkillsToolset` and
  `SkillsCapability`. Note that `SkillsCapability` is deliberately a thin delegating wrapper
  that forwards to `SkillsToolset`; changes to capability *internals* usually don't reach it.

- **Tool registration and `RunContext`** — every tool in `toolset.py` takes
  `ctx: RunContext[Any]` first.

Not in scope, and worth stating explicitly in the verdict so the next run doesn't re-triage
it: model providers, the local dev web chat UI (`Agent.to_web()`, `clai web`), `web_fetch`,
MCP client support, and anything in `pydantic-ai-harness` (this package does not depend on
it — it is tracked only because upstream ships them together).

## 4. Verify empirically when anything looks close

Do not settle a real question by reading release notes alone:

```bash
uv pip install --system --upgrade pydantic-ai-slim && pytest
uv pip install --system "pydantic-ai-slim==1.105.0" && pytest   # the declared floor
```

## 5. Record the entry

Prepend a new `## YYYY-MM-DD` section to `.github/upstream-watch.md`, above the previous
top entry, following the existing format exactly:

- **pydantic/pydantic-ai**: checked through `<tag>` (published `<date>`), reviewed `<range>`
- **pydantic/pydantic-ai-harness**: checked through `<tag>` (published `<date>`), reviewed `<range>`
- **Verdict**: what you concluded and *why*, naming the specific releases, PR numbers, and
  symbols you checked.

Write the verdict so a future reader can tell whether you actually verified something or
merely assumed it. A vague "no breaking changes" entry is worse than useless — it looks like
coverage while providing none. Always close by confirming the private-symbol status.

## 6. Open the PR

Branch, commit the log entry, and open a PR. If the review found real impact, file the issue
or include the fix, and reference it from the verdict.

**Do not skip the entry when the verdict is "no action".** The log's value is the unbroken
chain of lower bounds; a missing week silently widens the next run's range.

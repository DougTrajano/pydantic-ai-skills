# Review rubric

The standard a change to `pydantic-ai-skills` is held to. It is the source of truth for two
reviewers:

- the **AI reviewer** in [`.github/workflows/ai-review.yml`](workflows/ai-review.yml), which runs
  after CI passes on a pull request;
- the **`pre-push-review` skill** in [`.claude/skills/pre-push-review/`](../.claude/skills/pre-push-review/SKILL.md),
  which an agent runs locally before pushing.

Both apply the judgment below. Neither re-derives it from its own priors.

## What this reviewer is for

The deterministic gates already run: ruff, ruff-format, mypy, the test suite on Python 3.10–3.14
against three pydantic-ai versions, the coverage floor, `mkdocs build --strict`, actionlint, zizmor
and SonarCloud. **Do not spend a finding on anything a gate already enforces.** Review the things a
linter cannot see: whether the change is correct, whether it preserves this package's invariants,
and whether it is tested where it matters.

## Severity scale

| Severity | Meaning |
| --- | --- |
| `critical` | Data loss, a security hole, or a break in the documented public API. |
| `high` | A concrete bug: an input or state exists that produces a wrong result or an unhandled exception. |
| `medium` | Correct today, but fragile: a missing test for changed behavior, an invariant upheld only by accident, a silent failure mode. |
| `low` | Readability or maintainability that materially affects the next reader. |
| `nitpick` | Preference. **Do not file these** — they are what erodes trust in the reviewer. |

Verdict mapping: any `critical` or `high` → `REQUEST_CHANGES`. Otherwise → `COMMENT`. No findings →
`APPROVE`.

## Evidence bar

- A finding names a file, a line, and a **concrete trigger**: the input or state that makes it fail.
  If you cannot state the trigger, drop the finding.
- If you need to hedge with "might", "could" or "possibly", it is not ready.
- Before posting, switch sides: assume the finding is wrong and try to refute it. Post it only if it
  survives your own strongest counter-argument. A false positive costs more than a missed finding.
- Reporting nothing is a valid, common outcome. Say so plainly.

## Repository invariants

These are the properties that break quietly. Check each one that the diff touches — they are
restated from [`AGENTS.md`](../AGENTS.md), which remains authoritative.

1. **Skill source priority is programmatic > directories > registries.** Programmatic names are
   protected; within directories, last wins with a `UserWarning`; registries never override an
   existing name. A change to `_collect_dir_skills_into` or `_load_registry_skills` that reorders or
   short-circuits this is `high`.
2. **`SkillsCapability` stays a delegating wrapper over `SkillsToolset`.** Behavior added to the
   capability instead of the toolset makes the two integration paths diverge — `high`.
3. **Registry failures degrade, they don't raise.** A `get_skills()` error must stay caught and
   warned.
4. **Path-traversal and symlink checks in discovery and load paths must not regress.** A resource or
   script path that escapes its skill directory is `critical`.
5. **Script discovery covers supported extensions *and* any executable file** — not Python only.
6. **AnyIO process stream readers handle `anyio.EndOfStream` explicitly.**
7. **New code must work against the floor**, `pydantic-ai-slim>=1.105`, not just latest. A symbol or
   keyword argument that only exists in 2.x, used unconditionally, is `high` — CI's floor matrix
   entry is the proof.
8. **Private pydantic-ai imports** (`pydantic_ai._function_schema`, `_griffe`, `_utils`) stay
   mirrored in [`tests/test_pydantic_ai_compat.py`](../tests/test_pydantic_ai_compat.py). A new
   private import with no matching assertion there is `medium`.
9. **Optional extras are imported lazily** — `gitpython` (`[git]`) and `boto3` (`[s3]`) — and raise
   an `ImportError` naming the extra. A module-level import of either is `high`.
10. **Every tool function registered in `toolset.py` takes `ctx: RunContext[Any]` first.**
11. **Skill names**: `lowercase-with-hyphens`, ≤64 chars, no `anthropic`/`claude` reserved words.

## Tests

A behavior change with no test is a `medium` finding, and the comment must name the test that is
missing — file, name, and the case it would cover. "Add tests" on its own is not a finding.

Do not flag: coverage percentages (the floor is a CI gate), `asyncio` markers (`pytest.ini` sets
`asyncio_mode = auto`, so `@pytest.mark.asyncio` must *not* be added), or test style that matches
the surrounding file.

## What NOT to flag

- **Style** — ruff and ruff-format own it. Quote style, import order, line length, formatting.
- **Typing** — mypy owns it.
- **Docstring presence** for `D100`/`D102`/`D104`/`D105`/`D107`, which this repo ignores on purpose.
- **Coverage numbers** — the CI floor reports them deterministically.
- **Single-quoted strings** — that is the configured house style, not a mistake.
- **"Consider extracting a helper"** with no defect behind it.
- **Speculative performance** with no measurement and no hot path.
- **Anything already flagged in an unresolved thread on the same lines**, or resolved with a
  maintainer reply. Do not re-litigate a decision.
- **The diff restated back at the author.** No summaries of what the PR does.
- **Pre-existing problems the diff merely moved.** Note them in the review body at most once.

## Comment quality

One issue per comment. State the problem, then the concrete fix. Use a ```suggestion block only when
you can give a replacement that actually differs from the current line. Order findings by severity,
highest first. Cap inline comments at 30 per review; if more survive, keep the most severe 30 and
summarize the rest in the body.

# AGENTS.md

**pydantic-ai-skills** is a Python package that implements the full [Agent Skills specification](https://agentskills.io/home) for [Pydantic AI](https://ai.pydantic.dev/), enabling modular skill discovery, bundled resources, script execution, remote registries, and runtime reload for AI agents.

This file provides guidance to coding agents (Claude Code, etc.) when working with code in this repository. `CLAUDE.md` is a symlink to this file — edit this one.

## Scope

Python library (>=3.10) implementing the [Agent Skills specification](https://agentskills.io/home) for [Pydantic AI](https://ai.pydantic.dev/). Ships the full skill package — bundled resources, script execution, remote registries, programmatic skills, runtime reload — not just `SKILL.md` injection.

Keep this file to agent-critical defaults. Task-specific detail belongs in [docs/](docs/) (see [Link, Don't Duplicate](#link-dont-duplicate)).

## Commands

```bash
pip install -e ".[test,git,s3,dev]"   # full dev install
pytest                                # all tests (coverage is on by default via pytest.ini)
pytest tests/test_toolset.py -v       # one file
pytest tests/test_toolset.py::test_name -v  # one test
pytest -m "not slow"                  # skip slow markers
pre-commit run --all-files            # what CI's lint job runs: ruff, ruff-format, mypy, actionlint, zizmor
ruff check pydantic_ai_skills/ && ruff format pydantic_ai_skills/
mkdocs build --strict                 # what CI's docs job runs, needs pip install -e ".[docs]"
mkdocs serve                          # docs preview
```

`pytest.ini` sets `asyncio_mode = auto` — do **not** add `@pytest.mark.asyncio`.

## Quality Gates

Full description in [docs/contributing.md](docs/contributing.md#quality-gates). What matters here:

- **Hooks run these for you.** [.claude/hooks/](.claude/hooks/) lints every `*.py` and
  `.github/workflows/*.yml` you edit, blocks git commands that bypass a gate (`--no-verify`, bare
  `--force`, pushing to `main`), and runs the test suite before a session ends. A blocked hook is
  the gate talking — fix what it reports, don't work around it.
- **`Checks passed` is the required check** in CI; it aggregates lint, the 5×3 test matrix (with a
  coverage floor) and the strict docs build.
- **An AI reviewer comments on the pull request** once CI passes, against
  [.github/review-rubric.md](.github/review-rubric.md). Run the `pre-push-review` skill first and
  the review has nothing left to say.

## Architecture

Layers, in dependency order:

| Module | Role |
| --- | --- |
| [types.py](pydantic_ai_skills/types.py) | `Skill`, `SkillResource`, `SkillScript`, `SkillWrapper`; name normalization |
| [_parsing.py](pydantic_ai_skills/_parsing.py) | `SKILL.md` frontmatter parsing |
| [directory.py](pydantic_ai_skills/directory.py) | Filesystem discovery: `SkillsDirectory`, `discover_skills` |
| [local.py](pydantic_ai_skills/local.py) | Script execution via AnyIO subprocess; file-backed resources/scripts |
| [registries/](pydantic_ai_skills/registries/) | `SkillRegistry` ABC + Git/S3 sources + composition wrappers (filtered/prefixed/renamed/combined) |
| [toolset.py](pydantic_ai_skills/toolset.py) | `SkillsToolset` — the real implementation; registers the 4 tools, builds instructions |
| [capability.py](pydantic_ai_skills/capability.py) | `SkillsCapability` — thin `AbstractCapability` wrapper that delegates to `SkillsToolset` |

The four tools exposed to the model: `list_skills`, `load_skill`, `read_skill_resource`, `run_skill_script`.

Invariants to preserve:

- **Skill source priority is programmatic > directories > registries.** Programmatic names are protected (directory skills with the same name are skipped); within directories, last wins with a `UserWarning`; registries never override an existing name. See `_collect_dir_skills_into` and `_load_registry_skills` in [toolset.py](pydantic_ai_skills/toolset.py).
- **`SkillsCapability` stays a delegating wrapper** over `SkillsToolset` so both integration paths behave identically. Add behavior to the toolset, not the capability.
- **Registry failures degrade, they don't raise** — `get_skills()` errors are caught and warned.

## Conventions and Pitfalls

- Every tool function registered in [toolset.py](pydantic_ai_skills/toolset.py) takes `ctx: RunContext[Any]` as its first parameter.
- Single-quoted strings, line length 120, Google-style docstrings (Ruff enforces; `D100`/`D102`/`D104`/`D105`/`D107` are ignored — see [pyproject.toml](pyproject.toml)).
- Skill names: `lowercase-with-hyphens`, max 64 chars, no `anthropic`/`claude` reserved words.
- Do not regress path-traversal and symlink checks in discovery and load paths.
- Script discovery covers supported extensions **and** any executable file — not Python only.
- AnyIO process stream readers must handle `anyio.EndOfStream` explicitly.
- This package imports private pydantic-ai symbols (`pydantic_ai._function_schema`, `_griffe`, `_utils`). [tests/test_pydantic_ai_compat.py](tests/test_pydantic_ai_compat.py) exists so an upstream move fails loudly — keep it in sync with what the code actually imports.
- CI runs Python 3.10–3.14 × pydantic-ai-slim `1.105.0` / `2.0.0` / `latest`. New code must work against the floor (`pydantic-ai-slim>=1.105`), not just latest.
- `gitpython` (`[git]`) and `boto3` (`[s3]`) are optional extras — import them lazily and raise a clear `ImportError` naming the extra, as [registries/s3.py](pydantic_ai_skills/registries/s3.py) does.

## Working Style

- Prefer small, surgical diffs. Every changed line should trace to the request; don't refactor or reformat adjacent code, and mention unrelated dead code rather than deleting it.
- Match surrounding style in [pydantic_ai_skills/](pydantic_ai_skills/) even where you'd write it differently.
- Add or update tests in [tests/](tests/) for any behavior change.
- If the request is ambiguous or a simpler approach exists, say so before implementing.

## Link, Don't Duplicate

- Concepts and architecture: [docs/concepts.md](docs/concepts.md)
- Creating filesystem skills: [docs/creating-skills.md](docs/creating-skills.md)
- Programmatic skills: [docs/programmatic-skills.md](docs/programmatic-skills.md)
- Registries and composition: [docs/registries.md](docs/registries.md)
- Security model: [docs/security.md](docs/security.md)
- Advanced patterns: [docs/advanced.md](docs/advanced.md)
- Contribution workflow: [docs/contributing.md](docs/contributing.md)
- API reference: [docs/api/](docs/api/)

External:

- Pydantic AI integration details: https://ai.pydantic.dev/llms.txt
- Agent Skills specification: https://agentskills.io/home

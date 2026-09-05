# AGENTS.md

**pydantic-ai-skills** adds remote skill registries and bundled-file execution to [Pydantic AI](https://ai.pydantic.dev/) Agent Skills. It builds on [`pydantic-ai-harness`](https://github.com/pydantic/pydantic-ai-harness), which owns `SKILL.md` discovery, validation and instruction rendering.

This file provides guidance to coding agents (Claude Code, etc.) when working with code in this repository. `CLAUDE.md` is a symlink to this file — edit this one.

## Scope

Python library (>=3.10) that **complements** harness's `Skills` capability rather than reimplementing it. What this package owns: Git/S3 registries and their composition, the bundled `references/`/`scripts/` layer, sandboxed script execution, `${SKILL_DIR}` resolution, and skills defined in Python.

If a change would duplicate something harness already does, it belongs upstream, not here.

Keep this file to agent-critical defaults. Task-specific detail belongs in [docs/](docs/) (see [Link, Don't Duplicate](#link-dont-duplicate)).

## Commands

```bash
pip install -e ".[test,git,s3,dev]"   # full dev install
pytest                                # all tests (coverage is on by default via pytest.ini)
pytest tests/test_capability.py -v    # one file
pytest tests/test_capability.py::test_name -v  # one test
pytest -m "not slow"                  # skip slow markers
pre-commit run --all-files            # what CI's lint job runs: ruff + ruff-format + mypy
ruff check pydantic_ai_skills/ && ruff format pydantic_ai_skills/
mkdocs serve                          # docs, needs pip install -e ".[docs]"
```

`pytest.ini` sets `asyncio_mode = auto` — do **not** add `@pytest.mark.asyncio`.

## Architecture

Layers, in dependency order:

| Module | Role |
| --- | --- |
| [types.py](pydantic_ai_skills/types.py) | `Skill`, `SkillResource`, `SkillScript`, `SkillWrapper`, the `@skill` decorator; name normalization |
| [_parsing.py](pydantic_ai_skills/_parsing.py) | Minimal frontmatter reading — only what runs *before* harness sees a library |
| [packages.py](pydantic_ai_skills/packages.py) | `index_libraries`, `SkillPackage` — the bundled-file index |
| [local.py](pydantic_ai_skills/local.py) | Script execution via AnyIO subprocess; file-backed resources/scripts |
| [registries/](pydantic_ai_skills/registries/) | `SkillRegistry` ABC + Git/S3/Local sources + composition wrappers (filtered/prefixed/renamed/combined) |
| [_toolset.py](pydantic_ai_skills/_toolset.py) | `SkillFilesToolset` — the two model-facing tools |
| [capability.py](pydantic_ai_skills/capability.py) | `SkillsCapability` — the composite over harness's `Skills` |

The two tools exposed to the model: `read_skill_resource`, `run_skill_script`. Loading a skill's instructions is Pydantic AI's own `load_capability`, not something this package registers.

Invariants to preserve:

- **harness owns levels 1 and 2.** `SkillsCapability` constructs `pydantic_ai_harness.Skills` and re-emits its leaves. Never reimplement `SKILL.md` parsing, validation, naming, or the catalog, and never import from `pydantic_ai_harness.skills._loader` — only the public `Skills` surface, pinned by [tests/test_harness_compat.py](tests/test_harness_compat.py).
- **`get_toolset()` must stay on the capability, not on a leaf.** pydantic-ai collects toolsets from a container's direct children (`CombinedCapability.get_toolset`) and does *not* recurse through `apply()`. A toolset parked on a leaf is silently never registered.
- **`apply()` must visit `self` when a toolset is contributed.** The run's capability registry is built from `apply()`, and `CapabilityOwnedToolset` raises at first tool call if the owner is missing from it.
- **Discovery mirrors harness exactly** — immediate children of a library containing `SKILL.md`. `index_libraries` and harness must never disagree about what a skill is, or the file tools cannot find packages for skills on the catalog.
- **Skill source priority is programmatic > directories/registries.** A programmatic skill shadowing a directory-backed one wins with a `UserWarning`, and the harness leaf is dropped so no duplicate capability id reaches the run.
- **Registries return directories, not `Skill` objects.** `sync()` is the whole contract; anything that parses a `SKILL.md` in a registry is a smell.

## Conventions and Pitfalls

- Every tool function registered in [_toolset.py](pydantic_ai_skills/_toolset.py) takes `ctx: RunContext[Any]` as its first parameter.
- Single-quoted strings, line length 120, Google-style docstrings (Ruff enforces; `D100`/`D102`/`D104`/`D105`/`D107` are ignored — see [pyproject.toml](pyproject.toml)). **Test functions need docstrings too** (`D103` applies to `tests/`).
- Skill names: `lowercase-with-hyphens`, max 64 chars, no consecutive or leading/trailing hyphens. `_parsing.validate_skill_name` mirrors harness's rule — keep the two in step.
- Do not regress path-traversal and symlink checks in indexing, staging, or download paths.
- Script discovery covers supported extensions **and** any executable file — not Python only.
- AnyIO process stream readers must handle `anyio.EndOfStream` explicitly.
- Never write `executor or LocalSkillScriptExecutor()` — use `is None`. A falsey custom executor (a pool that is empty at index time) must not silently fall back to running untrusted scripts on the host.
- This package imports private pydantic-ai symbols (`pydantic_ai._function_schema`, `_griffe`, `_utils`). [tests/test_pydantic_ai_compat.py](tests/test_pydantic_ai_compat.py) exists so an upstream move fails loudly — keep it in sync with what the code actually imports. [tests/test_harness_compat.py](tests/test_harness_compat.py) plays the same role for harness, which is on 0.x and documents that its API may change between minor releases.
- CI runs Python 3.10–3.14 against a floor/latest pair of `pydantic-ai-harness` + `pydantic-ai-slim`. New code must work against the floor (`pydantic-ai-harness>=0.28`, `pydantic-ai-slim>=2.38`), not just latest. The two move together because harness sets a slim floor of its own.
- `gitpython` (`[git]`) and `boto3` (`[s3]`) are optional extras — import them lazily and raise a clear `ImportError` naming the extra, as [registries/s3.py](pydantic_ai_skills/registries/s3.py) does.
- `TestModel` does not work with deferred capabilities: it calls `load_capability` with a synthesized id and exhausts the retry budget. Use `FunctionModel` to script tool calls.

## Working Style

- Prefer small, surgical diffs. Every changed line should trace to the request; don't refactor or reformat adjacent code, and mention unrelated dead code rather than deleting it.
- Match surrounding style in [pydantic_ai_skills/](pydantic_ai_skills/) even where you'd write it differently.
- Add or update tests in [tests/](tests/) for any behavior change.
- If the request is ambiguous or a simpler approach exists, say so before implementing.

## Link, Don't Duplicate

- Concepts and the division of labour with harness: [docs/concepts.md](docs/concepts.md)
- How this compares to harness alone: [docs/comparison.md](docs/comparison.md)
- Creating filesystem skills: [docs/creating-skills.md](docs/creating-skills.md)
- Programmatic skills: [docs/programmatic-skills.md](docs/programmatic-skills.md)
- Registries and composition: [docs/registries.md](docs/registries.md)
- Security model: [docs/security.md](docs/security.md)
- Advanced patterns: [docs/advanced.md](docs/advanced.md)
- v1 → v2 migration: [docs/migration-v2.md](docs/migration-v2.md)
- Contribution workflow: [docs/contributing.md](docs/contributing.md)
- API reference: [docs/api/](docs/api/)

External:

- Pydantic AI integration details: https://ai.pydantic.dev/llms.txt
- pydantic-ai-harness Skills: https://github.com/pydantic/pydantic-ai-harness/tree/main/pydantic_ai_harness/skills
- Agent Skills specification: https://agentskills.io/home

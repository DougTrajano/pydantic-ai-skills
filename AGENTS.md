# Project Guidelines

## Scope

This repository is a Python library (Python >=3.10) implementing the Agent Skills specification for Pydantic AI.

Use this file for agent-critical defaults only. For detailed user docs, link to the docs site content in [docs/](docs/).

## Code Style

- Match existing style in [pydantic_ai_skills/](pydantic_ai_skills/).
- Use single quotes for Python strings (enforced by Ruff config in [pyproject.toml](pyproject.toml)).
- Keep line length <= 120.
- Use Google-style docstrings for public APIs.
- Prefer small, surgical diffs over broad refactors.

## Architecture

Core boundaries:

- Discovery layer: [pydantic_ai_skills/directory.py](pydantic_ai_skills/directory.py)
- Type layer (dataclasses and normalization): [pydantic_ai_skills/types.py](pydantic_ai_skills/types.py)
- Tool integration layer: [pydantic_ai_skills/toolset.py](pydantic_ai_skills/toolset.py)
- Local execution and script dispatch: [pydantic_ai_skills/local.py](pydantic_ai_skills/local.py)
- Capability adapter for pydantic-ai >=1.71: [pydantic_ai_skills/capability.py](pydantic_ai_skills/capability.py)
- Registry implementations and composition wrappers: [pydantic_ai_skills/registries/](pydantic_ai_skills/registries/)

Behavioral constraints to preserve:

- Keep `SkillsCapability` import-safe on older pydantic-ai versions (runtime error on use, not import-time crash).
- Keep capability behavior delegated to `SkillsToolset` for parity.
- Registry priority order is programmatic > directories > registries.

## Build and Test

Primary commands:

```bash
pip install -e ".[test]"
pip install -e ".[git]"
pytest
ruff check pydantic_ai_skills/
ruff format pydantic_ai_skills/
```

Docs commands:

```bash
pip install -e ".[docs]"
mkdocs serve
mkdocs build
```

Testing notes:

- `pytest.ini` uses `asyncio_mode = auto` (do not require `@pytest.mark.asyncio`).
- Keep/add tests in [tests/](tests/) for behavior changes.
- Useful targeted runs: `pytest tests/test_toolset.py -v`, `pytest -m "not slow"`.

## Conventions and Pitfalls

- Every tool function registered in [pydantic_ai_skills/toolset.py](pydantic_ai_skills/toolset.py) must accept `ctx: RunContext[Any]` first.
- Skill names must follow the normalized spec format (`lowercase-with-hyphens`, max 64, no `anthropic`/`claude` reserved words).
- Do not regress path traversal and symlink safety checks in discovery/load paths.
- Script discovery must include supported extensions and executable files (not Python-only).
- AnyIO process stream readers should handle `anyio.EndOfStream` explicitly.

## Link, Do Not Duplicate

Prefer linking to existing docs for task-specific details:

- Concepts and architecture: [docs/concepts.md](docs/concepts.md)
- Creating filesystem skills: [docs/creating-skills.md](docs/creating-skills.md)
- Programmatic skills: [docs/programmatic-skills.md](docs/programmatic-skills.md)
- Registries and composition: [docs/registries.md](docs/registries.md)
- Security model: [docs/security.md](docs/security.md)
- Advanced patterns: [docs/advanced.md](docs/advanced.md)
- Contribution workflow: [docs/contributing.md](docs/contributing.md)
- API references: [docs/api/toolset.md](docs/api/toolset.md), [docs/api/capability.md](docs/api/capability.md), [docs/api/types.md](docs/api/types.md), [docs/api/registries.md](docs/api/registries.md), [docs/api/exceptions.md](docs/api/exceptions.md)

External reference for Pydantic AI integration details:

- https://ai.pydantic.dev/llms.txt

Official Agent Skills specification documentation:

- https://agentskills.io/home

## Behavioral Guidelines for AI Coding Agents

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:

- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:

- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:

```md
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

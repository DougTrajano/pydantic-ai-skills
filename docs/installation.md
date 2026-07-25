# Installation

## Requirements

- Python 3.10 or newer

## Install

```bash
pip install pydantic-ai-skills
```

This pulls in everything needed to discover skills from the filesystem, load their instructions
and resources, and run their scripts:

- `pydantic-ai-slim` — the Pydantic AI agent framework
- `pyyaml` — parses `SKILL.md` YAML frontmatter
- `anyio` — async process handling for script execution

No extras are required for the core workflow described in the [Quick Start](quick-start.md).

## Optional extras

Some features depend on additional packages. Install the matching extra:

| Extra | Install | Enables |
| --- | --- | --- |
| `git` | `pip install "pydantic-ai-skills[git]"` | `GitSkillsRegistry` — load skills from Git repositories |
| `s3` | `pip install "pydantic-ai-skills[s3]"` | `S3SkillsRegistry` — load skills from S3 buckets |
| `test` | `pip install "pydantic-ai-skills[test]"` | pytest and coverage tooling |
| `dev` | `pip install "pydantic-ai-skills[dev]"` | ruff, mypy, and pre-commit |
| `docs` | `pip install "pydantic-ai-skills[docs]"` | MkDocs and the docs toolchain |
| `examples` | `pip install "pydantic-ai-skills[examples]"` | dependencies used by the bundled examples |

Extras can be combined:

```bash
pip install "pydantic-ai-skills[git,s3]"
```

See [Skill Registries](registries.md) for what the `git` and `s3` extras unlock.

## Install from source

```bash
git clone https://github.com/dougtrajano/pydantic-ai-skills.git
cd pydantic-ai-skills
pip install -e .
```

Setting up a development environment instead? See [Contributing](contributing.md).

## Verify the installation

```bash
python -c "from importlib.metadata import version; print(version('pydantic-ai-skills'))"
```

## Model provider credentials

`pydantic-ai-skills` does not talk to model providers itself — Pydantic AI does. Install and
configure whichever provider your agent uses, for example:

```bash
pip install "pydantic-ai-slim[openai]"
export OPENAI_API_KEY=...
```

See the [Pydantic AI models documentation](https://ai.pydantic.dev/models/) for the full list.

## Next steps

- [Quick Start](quick-start.md) — build your first agent with skills
- [Creating Skills](creating-skills.md) — write a `SKILL.md` package
- [Why pydantic-ai-skills](comparison.md) — how this compares to the alternatives

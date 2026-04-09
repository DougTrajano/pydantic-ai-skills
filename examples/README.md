# Examples

This folder contains runnable examples demonstrating how to use `pydantic-ai-skills` in different scenarios. Each script spins up a Pydantic AI agent as a web server using [uvicorn](https://www.uvicorn.org/) on `http://127.0.0.1:7932`.

## Contents

| File | Description |
|------|-------------|
| `basic_usage.py` | Minimal setup: one skills directory loaded via `SkillsToolset`. |
| `advanced_usage.py` | Multiple skills directories, DuckDuckGo search tool, `httpx` URL fetcher, and a filesystem sandbox. |
| `git_registry_usage.py` | Loads skills from a remote Git repository using `GitSkillsRegistry` (clones Anthropic's public skills repo). |
| `programatic_skills.py` | Defines a skill entirely in Python using `@skill.resource` / `@skill.script` decorators — HR Analytics Agent backed by a HuggingFace dataset. |

### Bundled skills

| Path | Skills |
|------|--------|
| `skills/` | `web-research`, `arxiv-search`, `pydanticai-docs` |
| `anthropic-skills/` | Anthropic's official skill collection (algorithmic-art, canvas-design, docx, pdf, pptx, slack-gif-creator, webapp-testing, and more) |

## Prerequisites

### Python version

Python **3.10** or higher is required.

### Dependency group

Install the `examples` optional dependency group from the project root:

```bash
pip install -e ".[examples]"
# or with uv
uv sync --extra examples
```

See [`pyproject.toml`](../pyproject.toml) for the full up-to-date list of packages included in this group.

## Environment variables

Create an `examples/.env` file (or export the variables in your shell) before running any example.

### Required

| Variable | Description |
|----------|-------------|
| `PYDANTIC_AI_GATEWAY_API_KEY` | API key for the [Pydantic AI Gateway](https://ai.pydantic.dev/), which proxies the `gateway/openai:*` model strings used by all examples. |

### Optional

| Variable | Description |
|----------|-------------|
| `LOGFIRE_TOKEN` | [Logfire](https://logfire.pydantic.dev/) write token for tracing and observability. If omitted, traces are printed to the console but **not** sent to logfire.dev (a credential warning may appear). Set `LOGFIRE_SEND_TO_LOGFIRE=false` to suppress the warning entirely. |

### Example `.env` file

```dotenv
# Pydantic AI Gateway (required)
PYDANTIC_AI_GATEWAY_API_KEY="your-gateway-api-key"

# Logfire observability (optional)
LOGFIRE_TOKEN="your-logfire-token"
```

## Running an example

```bash
# from the repo root
python -m examples.basic_usage
```

The agent will be available at `http://127.0.0.1:7932`.

## Compatibility Note

- On pydantic-ai >= 1.74, `SkillsToolset.get_instructions()` is injected automatically by the agent graph.
- On pydantic-ai < 1.74, add a manual `@agent.instructions` hook that returns `await SkillsToolset.get_instructions(ctx)`.

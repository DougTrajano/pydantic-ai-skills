# Models and Providers

Pydantic AI supports multiple LLM providers via a `provider:model-name` string format. The model string is passed as the first argument to `Agent(...)`.

## Provider Quick Reference

| Provider                     | Model string format                     | Env var                 | Install extra                   |
| ---------------------------- | --------------------------------------- | ----------------------- | ------------------------------- |
| OpenAI                       | `openai:<model>`                        | `OPENAI_API_KEY`        | `pydantic-ai-slim[openai]`      |
| Anthropic                    | `anthropic:<model>`                     | `ANTHROPIC_API_KEY`     | `pydantic-ai-slim[anthropic]`   |
| Google (Generative Language) | `google-gla:<model>`                    | `GOOGLE_API_KEY`        | `pydantic-ai-slim[google]`      |
| Google (Vertex AI)           | `google-vertex:<model>`                 | `GOOGLE_API_KEY` or ADC | `pydantic-ai-slim[google]`      |
| xAI                          | `xai:<model>`                           | `XAI_API_KEY`           | `pydantic-ai-slim[openai]`      |
| Groq                         | `groq:<model>`                          | `GROQ_API_KEY`          | `pydantic-ai-slim[groq]`        |
| Mistral                      | `mistral:<model>`                       | `MISTRAL_API_KEY`       | `pydantic-ai-slim[mistral]`     |
| Cohere                       | `cohere:<model>`                        | `CO_API_KEY`            | `pydantic-ai-slim[cohere]`      |
| Bedrock (AWS)                | `bedrock:<model>`                       | AWS credentials         | `pydantic-ai-slim[bedrock]`     |
| OpenRouter                   | `openrouter:<provider/model>`           | `OPENROUTER_API_KEY`    | `pydantic-ai-slim[openrouter]`  |
| Ollama (local)               | via `OpenAIChatModel` + custom base_url | none                    | `pydantic-ai-slim[openai]`      |
| Hugging Face                 | `huggingface:<model>`                   | `HF_TOKEN`              | `pydantic-ai-slim[huggingface]` |
| Cerebras                     | `cerebras:<model>`                      | `CEREBRAS_API_KEY`      | `pydantic-ai-slim[cerebraas]`   |

## Common Model Names

| Provider  | Example models                                               |
| --------- | ------------------------------------------------------------ |
| OpenAI    | `gpt-4o`, `gpt-4o-mini`, `o3`, `o4-mini`                     |
| Anthropic | `claude-sonnet-4-5`, `claude-sonnet-4-6`, `claude-haiku-3-5` |
| Google    | `gemini-2.5-flash`, `gemini-3-pro-preview`                   |
| Groq      | `llama-3.3-70b-versatile`, `mixtral-8x7b-32768`              |
| Mistral   | `mistral-large-latest`, `codestral-latest`                   |

## Basic Usage

```python
from pydantic_ai import Agent

# OpenAI (OPENAI_API_KEY must be set)
agent = Agent('openai:gpt-4o')

# Anthropic (ANTHROPIC_API_KEY must be set)
agent = Agent('anthropic:claude-sonnet-4-5')

# Google Gemini (GOOGLE_API_KEY must be set)
agent = Agent('google-gla:gemini-2.5-flash')
```

## ModelSettings

Pass `ModelSettings` to control inference parameters:

```python
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

agent = Agent(
    'openai:gpt-4o',
    model_settings=ModelSettings(temperature=0.2, max_tokens=1024),
)
```

Common fields: `temperature`, `max_tokens`, `top_p`, `timeout`.

## For Details, See

- Overview: <https://ai.pydantic.dev/models/overview/index.md>
- OpenAI: <https://ai.pydantic.dev/models/openai/index.md>
- Anthropic: <https://ai.pydantic.dev/models/anthropic/index.md>
- Google: <https://ai.pydantic.dev/models/google/index.md>
- Groq: <https://ai.pydantic.dev/models/groq/index.md>
- Mistral: <https://ai.pydantic.dev/models/mistral/index.md>
- Bedrock: <https://ai.pydantic.dev/models/bedrock/index.md>
- OpenRouter: <https://ai.pydantic.dev/models/openrouter/index.md>

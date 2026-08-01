# Upstream Watch Log

Tracks the last `pydantic-ai` / `pydantic-ai-harness` releases reviewed by the weekly
upstream-watch routine. Newest entry first. The top entry's tags are the lower bound
for the next run.

## 2026-08-01

- **pydantic/pydantic-ai**: checked through `v2.22.0` (published 2026-08-01T02:27:00Z)
- **pydantic/pydantic-ai-harness**: checked through `v0.15.0` (published 2026-08-01)
- **Verdict**: No action needed. Nothing in this window changes the private symbols this
  package imports (`pydantic_ai._function_schema`, `pydantic_ai._griffe`, `pydantic_ai._utils`)
  or the public `AbstractToolset` / `AbstractCapability` / `RunContext` / tool-registration
  surface this package depends on. See the corresponding PR for full triage notes.

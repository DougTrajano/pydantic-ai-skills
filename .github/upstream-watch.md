# Upstream Watch Log

Tracks the last `pydantic-ai` / `pydantic-ai-harness` releases reviewed by the weekly
upstream-watch routine. Newest entry first. The top entry's tags are the lower bound
for the next run.

## 2026-08-07

- **pydantic/pydantic-ai**: checked through `v2.26.0` (published 2026-08-06). Reviewed
  `v2.23.0`–`v2.26.0`.
- **pydantic/pydantic-ai-harness**: checked through `v0.18.0` (published 2026-08-05).
  Reviewed `v0.17.0`–`v0.18.0`.
- **Verdict**: No action needed. The two `AbstractCapability` bug fixes in `v2.23.0`
  (capability container rebinding via `dataclasses.replace`, and `wrap_run_event_stream`
  / node hooks now firing under `agent.iter()`) don't touch anything `SkillsCapability`
  does — it's a plain dataclass (no custom `__init__` to break rebinding) and implements
  none of the node/event-stream hooks. `v2.26.0`'s new tool-deferral machinery
  (`ToolAvailabilityDeltaPart`, native per-provider deferral channels) is transparent to
  us: `SkillsCapability` already used the existing `defer_loading`/`id` fields, and their
  semantics are unchanged. `RunContext.cancel()` and `AgentRun.cancel()` are additive.
  The private symbols this package imports (`pydantic_ai._function_schema`,
  `pydantic_ai._griffe.doc_descriptions`, `pydantic_ai._utils.is_async_callable` /
  `run_in_executor`) are unchanged. `pydantic-ai-harness` releases (browser-use agent
  delegation, spend limits) are irrelevant — this package has no dependency on
  `pydantic-ai-harness`. See the corresponding PR for full triage notes.

## 2026-08-01

- **pydantic/pydantic-ai**: checked through `v2.22.0` (published 2026-08-01T02:27:00Z)
- **pydantic/pydantic-ai-harness**: checked through `v0.15.0` (published 2026-08-01)
- **Verdict**: No action needed. Nothing in this window changes the private symbols this
  package imports (`pydantic_ai._function_schema`, `pydantic_ai._griffe`, `pydantic_ai._utils`)
  or the public `AbstractToolset` / `AbstractCapability` / `RunContext` / tool-registration
  surface this package depends on. See the corresponding PR for full triage notes.

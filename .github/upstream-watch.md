# Upstream Watch Log

Tracks the last `pydantic-ai` / `pydantic-ai-harness` releases reviewed by the weekly
upstream-watch routine. Newest entry first. The top entry's tags are the lower bound
for the next run.

## 2026-08-14

- **pydantic/pydantic-ai**: checked through `v2.30.0` (published 2026-08-13). Reviewed
  `v2.27.0`–`v2.30.0`, plus the `v1` backport line `v1.107.2`–`v1.107.5`.
- **pydantic/pydantic-ai-harness**: checked through `v0.20.0` (published 2026-08-13).
  Reviewed `v0.18.1` and `v0.20.0`.
- **Verdict**: No action needed. `v1.107.2`/`v2.27.1`/`v1.107.4`/`v2.28.0`/`v1.107.5`/`v2.30.0`
  are security fixes to the local dev web chat UI (`Agent.to_web()`, `clai web`) and the
  `web_fetch` tool's download size — this package doesn't wrap either. `v2.29.0`'s FastMCP
  4 / MCP SDK v2 support in `MCPToolset` and new model providers (Snowflake, Crusoe, Azure
  AI Voice Live) aren't used here. `v2.29.0`'s "include parameter descriptions in rendered
  tool signatures" (#6487) only touches `function_signature.py` and `tools.py`, confirmed by
  reading the PR's file list directly — `_griffe.py` and `doc_descriptions()`'s signature and
  return shape are untouched, so `pydantic_ai_skills/toolset.py`'s
  `doc_descriptions(f, sig, docstring_format='auto')` call keeps working as-is. `v2.30.0`'s
  deferred-tool availability gate (#7271, #7442 — a fail-closed load→reveal→call ordering
  enforced via `ModelRetry`) is explicitly documented upstream as non-breaking for
  `AbstractCapability`/`AbstractToolset` implementers; `SkillsCapability` just forwards
  `defer_loading`/`id` to the base class and implements no deferral logic of its own, so
  nothing here depends on the old ordering. The private symbols this package imports
  (`pydantic_ai._function_schema`, `pydantic_ai._griffe.doc_descriptions`,
  `pydantic_ai._utils.is_async_callable` / `run_in_executor`) are unchanged.
  `pydantic-ai-harness` releases (realtime speech support, compaction estimator tweaks) are
  irrelevant — this package has no dependency on `pydantic-ai-harness`. See the corresponding
  PR for full triage notes.

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

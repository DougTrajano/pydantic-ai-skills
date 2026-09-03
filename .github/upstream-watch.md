# Upstream Watch Log

Tracks the last `pydantic-ai` / `pydantic-ai-harness` releases reviewed by the weekly
upstream-watch routine. Newest entry first. The top entry's tags are the lower bound
for the next run.

## 2026-08-28

- **pydantic/pydantic-ai**: checked through `v2.35.3` (published 2026-08-28). Reviewed
  `v2.34.0`–`v2.35.3`.
- **pydantic/pydantic-ai-harness**: checked through `v0.27.0` (published 2026-08-27).
  Reviewed `v0.25.0`–`v0.27.0`.
- **Verdict**: No action needed. Confirmed by diffing `v2.33.0...v2.35.3` in a local clone
  (`git diff --stat` against `pydantic_ai/_function_schema.py`, `_griffe.py`, `_utils.py`,
  `toolsets/abstract.py`, `toolsets/function.py`, `capabilities/`, `tools.py`): the three
  private symbols this package imports (`pydantic_ai._function_schema.FunctionSchema`/
  `function_schema`, `pydantic_ai._griffe.doc_descriptions`,
  `pydantic_ai._utils.is_async_callable`/`run_in_executor`) have zero diff across the whole
  window — untouched. `v2.35.0` (#7454, "deprecate `RunContext.capability_loaded`/
  `available_capability_ids` in favor of `capability_active`/`active_capability_ids`") does
  rename fields on `RunContext` and ripples through `CombinedCapability`'s internal
  `_ctx_for_available_cap`→`_ctx_for_active_cap` plumbing, but `SkillsCapability` never reads
  either old or new name (confirmed by grep: it only implements `get_toolset`,
  `get_instructions`, and `get_description`, none of the `before_run`/`after_run`/
  `prepare_tools`/etc. hooks `CombinedCapability` threads `capability_active` through), so the
  rename is fully transparent here. `v2.35.0` (#7759, "tool descriptions explicitly set to
  empty now remain empty rather than defaulting to the docstring") changed
  `Tool.__init__`'s `description = description or self.function_schema.description` to
  `description if description is not None else ...` in `tools.py` — the four tools this
  package registers (`list_skills`, `load_skill`, `read_skill_resource`, `run_skill_script`)
  are all added via the bare `@self.tool` decorator with no explicit `description=` argument,
  so this only changes behavior for callers that pass `description=''`, which this package
  never does. `v2.34.0`'s `#7679` ("Add a LangChain migration skill") only adds a `SKILL.md`
  under pydantic-ai's own `.claude/`-style repo tooling for an internal migration guide — not
  a change to any Agent Skills *support* in the library itself, and doesn't overlap with this
  package's skill discovery. The remaining `v2.34.0`–`v2.35.3` items (GLM-5.3/Heroku model
  support, `TestModel` JSON Schema edge cases, `VercelAIAdapter`/`VercelProvider`/`CohereModel`
  fixes, Bedrock guardrail traces and structured-output routing, Temporal cancellation and
  metric export changes, `dbos` extra dependency capping) touch model providers, evaluation
  helpers, and Temporal/durable-execution integrations this package doesn't use. `#6937`
  ("honor agent tool retry budget for `load_capability`") only affects the agent's own
  built-in `load_capability` tool implementation, which `SkillsCapability` doesn't override.
  `pydantic-ai-harness` `v0.25.0`–`v0.27.0` (compaction/spend-store internals, `Shell` spawn
  failure handling, release-gate tooling, doc snippet checks) are entirely harness-internal —
  this package has no dependency on `pydantic-ai-harness`, so these are tracked but out of
  scope as usual; none mention Agent Skills, `SKILL.md`, or skill discovery. Verified
  empirically: `pytest` passes identically against both `pydantic-ai-slim==2.35.3` (latest)
  and `pydantic-ai-slim==1.105.0` (the declared floor) — 550 passed, 1 pre-existing failure
  (`test_discover_skills_os_error_handling`, the same `chmod(0o000)`-as-root artifact noted in
  prior entries, unrelated to pydantic-ai and identical on both versions). `pre-commit run
  --all-files` (ruff, ruff-format, mypy) is clean. The private symbols this package imports
  are unchanged in both signature and behavior for this package's usage.

## 2026-08-21

- **pydantic/pydantic-ai**: checked through `v2.33.0` (published 2026-08-20). Reviewed
  `v2.32.0`–`v2.33.0`.
- **pydantic/pydantic-ai-harness**: checked through `v0.24.0` (published 2026-08-19).
  Reviewed `v0.23.0`–`v0.24.0`.
- **Verdict**: No action needed. `v2.32.0`–`v2.33.0` migrate pydantic-ai's own HTTP layer
  (including the Anthropic provider) from `httpx` to `httpx2` (#7351, #7657) — this package
  declares `httpx>=0.28.0` only under the `examples` extra and never imports it, so the
  migration doesn't reach it. The remaining feature/bugfix items (model-name suggestions,
  xAI/OpenRouter provider changes, instrumentation v6, `RunContext.cancel()` fixes,
  `FunctionModel` callable handling, Bedrock/DeepSeek/Temporal provider fixes) touch model
  providers, span instrumentation, and `pydantic_evals`/Temporal integrations this package
  doesn't use. Confirmed by diffing `v2.31.1...v2.33.0` in a local clone
  (`git diff --stat` against `_function_schema.py`, `_griffe.py`, `_utils.py`,
  `capabilities/capability.py`, `toolsets/abstract.py`, `toolsets/function.py`): only
  `_utils.py`, `capabilities/hooks.py`, and `toolsets/function.py` changed, all from a single
  PR (#7557, "Run sync hooks in thread pool and enforce timeout for blocking sync tools").
  That PR adds an `abandon_threads_on_cancel()` context manager and wires it into
  `run_in_executor()` and `FunctionToolset`'s per-tool timeout handling; `run_in_executor()`
  and `is_async_callable()` keep the exact signatures this package calls in
  `pydantic_ai_skills/local.py`, the new behavior only activates inside that context manager
  (which `SkillsToolset`/`local.py` never enter), and `SkillsToolset` (a `FunctionToolset`
  subclass) doesn't override the touched timeout-handling method — so the change is fully
  transparent here. `#7571` (tool-result message ordering for Bedrock) and `#7572` (unknown-tool
  retry message filtering) were checked directly against their file lists and confirmed to
  touch only `_agent_graph.py`/`messages.py`/`tool_manager.py` internals, not
  `AbstractCapability`, `AbstractToolset`, `RunContext`, or `defer_loading` semantics.
  `pydantic-ai-harness` `v0.23.0` (`ManagedPrompt` baggage/`FallbackCompaction`) and `v0.24.0`
  (serializer presets, `FileSystem` path/failure handling, `PlaywrightBrowser` and
  `YouSearch`/`YouResearch` capabilities) are entirely harness-internal — this package has no
  dependency on `pydantic-ai-harness`, so these are tracked but out of scope as usual.
  Verified empirically: `pytest` passes identically against both `pydantic-ai-slim==2.33.0`
  (latest) and `pydantic-ai-slim==1.105.0` (the declared floor) — 550 passed, 1 pre-existing
  failure (`test_discover_skills_os_error_handling`, a `chmod(0o000)` permission simulation
  that has no effect when tests run as root in this environment; unrelated to pydantic-ai and
  identical on both versions). `pre-commit run --all-files` (ruff, ruff-format, mypy) is clean.
  The private symbols this package imports
  (`pydantic_ai._function_schema.FunctionSchema`/`function_schema`,
  `pydantic_ai._griffe.doc_descriptions`, `pydantic_ai._utils.is_async_callable`/
  `run_in_executor`) are unchanged in signature and behavior for this package's usage.

## 2026-08-18

- **pydantic/pydantic-ai**: checked through `v2.31.1` (published 2026-08-18). Reviewed
  `v2.31.0`–`v2.31.1`.
- **pydantic/pydantic-ai-harness**: checked through `v0.22.0` (published 2026-08-18).
  Reviewed `v0.21.0`–`v0.22.0`.
- **Verdict**: No action needed. `v2.31.0` (#7292 `UIEventStream`/`AGUIEventStream`,
  #7018 `FallbackModel` span attribution, #7464 Temporal sandbox passthrough) and `v2.31.1`
  (#7374 Bedrock structured-output denylist, #7469 Gemini `thinking_level` fallback) only
  touch AG-UI event streaming, span/telemetry attribution, Temporal workflow sandboxing, and
  model-provider-specific request shaping — none of it is in `SkillsToolset`/`SkillsCapability`,
  tool registration, or `RunContext`. `pydantic-ai-harness` `v0.21.0` (#591, #626, #627) is
  docs/marketing only, and `v0.22.0` (#364 protected-pattern read-only walkers, #439
  `PromptInjectionDefender`, #593 `CodeMode`/`run_code` shell-tool folding, #639 doc model-name
  updates) is entirely harness-internal (`CodeMode`, walkers, prompt-injection defense) —
  this package has no dependency on `pydantic-ai-harness`, so these are tracked but out of
  scope as usual. The private symbols this package imports
  (`pydantic_ai._function_schema.FunctionSchema`/`function_schema`,
  `pydantic_ai._griffe.doc_descriptions`, `pydantic_ai._utils.is_async_callable`/
  `run_in_executor`) are unchanged in this window; no PR touched `_function_schema.py`,
  `_griffe.py`, or `_utils.py`.

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

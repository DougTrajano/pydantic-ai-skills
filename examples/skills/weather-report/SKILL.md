---
name: weather-report
description: Report typical weather for a city and month from bundled climate normals, or fetch current conditions from the OpenWeather API. Use when asked about the weather, the climate of a place, or what to expect in a given month.
compatibility: climate_lookup needs only the standard library and runs in a sandbox; live_weather needs internet access and an OPENWEATHER_API_KEY
---

# Weather Report Skill

Two ways to answer a weather question, chosen by whether live data is needed.

This skill also doubles as the test case for sandbox executors: one script is
pure computation over a bundled resource, the other needs the network. Running
both through a sandbox shows it executing real work while still refusing egress.

## When to Use This Skill

- "What is the weather usually like in Tokyo in July?" → `climate_lookup`
- "How warm does Cairo get in summer?" → `climate_lookup`
- "What is the weather in London right now?" → `live_weather`

## Skill Scripts

### climate_lookup

Reads `resources/climate_normals.json` and reports monthly averages. No network,
standard library only, so it behaves identically on the host and inside a sandbox.

- `city` (required): One of `london`, `tokyo`, `sydney`, `cairo`, `reykjavik`
- `month` (optional): Month name or number; omit for the full year
- `units` (optional): `c` (default) or `f`

Exits with code 2 for an unknown city or month.

### live_weather

Calls the OpenWeather API for current conditions.

- `city` (required): City name, e.g. `London`
- `units` (optional): `metric` (default) or `imperial`
- `timeout` (optional): Request timeout in seconds, default 10

Requires `OPENWEATHER_API_KEY` in the environment. Exits 2 when the key is
missing, 1 when the API is unreachable or returns an error.

## Data Source

`resources/climate_normals.json` holds approximate monthly normals for a handful
of cities, included so the skill works offline. It is illustrative demo data, not
an authoritative climate record. Use `live_weather` for anything real.

## Sandbox Behaviour

Under `LocalSandboxScriptExecutor`:

- `climate_lookup` produces **byte-identical output** to running on the host,
  including the bundled resource read through `../resources/`.
- `live_weather` fails twice over. It exits 2 first, because host environment
  variables are not forwarded into the sandbox, so `OPENWEATHER_API_KEY` is
  absent. Even with a key it could not succeed: LocalSandbox runs Pyodide under
  Deno without `--allow-net`, so `urllib` has no `https` handler and any request
  is refused. Neither is configurable — `ExecutionPreset` does not grant network
  access.

That contrast is the useful test: same skill, same executor, real work runs while
secrets and egress stay out.

Under `OpenSandboxScriptExecutor`, `live_weather` works if the container image
has network access and the key is passed via `env_vars={'OPENWEATHER_API_KEY': ...}`.

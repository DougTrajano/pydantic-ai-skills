# Operational workflows

## Project discovery and details

```bash
sonar list projects
sonar list projects --query <name-or-key> --page 1 --page-size 500
```

The output is JSON. Use the exact `projects[].key`, not the display name. Continue pagination while another page exists.

Combine dedicated commands with read-only API calls for a project snapshot:

```bash
sonar api get "/api/components/show?component=<URL_ENCODED_PROJECT_KEY>"
sonar api get "/api/measures/component?component=<URL_ENCODED_PROJECT_KEY>&metricKeys=ncloc,coverage,duplicated_lines_density,bugs,vulnerabilities,code_smells,security_hotspots"
sonar quality-gate status --project <PROJECT_KEY> --format json --all
sonar api get "/api/project_analyses/search?project=<URL_ENCODED_PROJECT_KEY>&ps=20"
sonar api get "/api/project_branches/list?project=<URL_ENCODED_PROJECT_KEY>"
```

Endpoint and metric availability vary by Cloud/Server version and permissions. If unavailable, inspect `/api/webservices/list` or the instance's Web API page. Do not treat a missing metric as zero.

Summarize returned key/name/visibility, analysis date and branch/PR, quality-gate verdict and failed conditions, core measures, and issue counts under the stated filters.

## Issues and quality gate

```bash
sonar list issues --project <PROJECT_KEY> --format json
sonar list issues --project <PROJECT_KEY> --statuses OPEN,CONFIRMED --severities HIGH,BLOCKER --format toon
sonar list issues --project <PROJECT_KEY> --branch <BRANCH> --page 1 --page-size 500 --format json
sonar list issues --project <PROJECT_KEY> --pull-request <PR_ID> --format json

sonar quality-gate status --project <PROJECT_KEY> --format json --all
sonar qg status --project <PROJECT_KEY> --branch <BRANCH> --format table --all
sonar quality-gate status --project <PROJECT_KEY> --pull-request <PR_ID> --format json --all
```

`quality-gate` and `qg` are aliases. Branch and pull request are mutually exclusive. Without `--all`, only failed conditions appear.

Issue severities depend on mode: MQR uses `INFO`, `LOW`, `MEDIUM`, `HIGH`, `BLOCKER`; Standard Experience uses `INFO`, `MINOR`, `MAJOR`, `CRITICAL`, `BLOCKER`. Status filters are `OPEN`, `CONFIRMED`, `FALSE_POSITIVE`, `ACCEPTED`, and `FIXED`.

## Changed-code analysis

Inspect scope first:

```bash
git status --short
git diff --name-only
git diff --cached --name-only
```

Then choose one scope:

```bash
sonar analyze --file src/example.py --format json
sonar analyze --file src/a.py --file src/b.py --depth DEEP --format json
sonar analyze --staged --format json
sonar analyze --base main --format json
sonar analyze --project <PROJECT_KEY> --format json
sonar analyze agentic --project <PROJECT_KEY> --branch <BRANCH> --format json
```

`STANDARD` is optimized for a narrow file check; `DEEP` provides cross-file context. One `--file` defaults to STANDARD; other scopes default to DEEP. `--force` bypasses large-change confirmation and should not be used casually.

This may send relevant code to server-side analysis. For a traditional full-project scan that publishes a complete analysis, inspect build/CI files for the existing SonarScanner command. Do not substitute `sonar analyze` without confirming intent.

## Secrets and dependency risks

```bash
sonar analyze secrets src/config.ts
sonar analyze secrets src/ scripts/
sonar analyze secrets --stdin

sonar analyze dependency-risks --project <PROJECT_KEY> --format json
sonar analyze dependency-risks --statuses active --min-severity HIGH --format toon
sonar analyze dependency-risks --statuses to_fix --format table
```

With secrets, positional arguments are file/directory paths and `--stdin` reads standard input. A findings-specific nonzero exit means secrets were detected, not necessarily a crash. Never repeat secret values.

Dependency raw statuses are `new`, `open`, `confirm`, `accept`, `safe`, `fixed`. Presets: `active` = new/open/confirm; `to_fix` adds accept; `all` includes every status. Values combine as a union. Manifests are uploaded to SonarQube; SCA entitlement/edition requirements apply.

## Remediation

Preview eligible issues, resolve exact keys, then run only with user intent:

```bash
sonar remediate --project <PROJECT_KEY> --issues <ISSUE_KEY_1>,<ISSUE_KEY_2>
```

Non-interactive use requires `--issues` and accepts at most 20 keys. This is Cloud-only. Review local edits and rerun the same analysis scope.

## Authenticated API

```bash
sonar api <get|post|patch|put|delete> "/endpoint?query=value"
sonar api post "/endpoint" --data '{"field":"value"}'
sonar api get "/api/webservices/list"
sonar api get "/api/system/status"
sonar api get "/api/favorites/search"
```

The endpoint starts with `/`. The CLI selects form or JSON encoding and adapts supported v1/v2 routing. Use GET by default; POST/PATCH/PUT/DELETE are remote mutations. Never create or return tokens unless explicitly requested and secure delivery exists. Use `--verbose` only for debugging and redact output.

## Integrations and context

Inspect target help and existing config before running `sonar integrate git|claude|copilot|codex|antigravity|cursor`. Git supports pre-commit/pre-push; dependency-risk pre-commit requires a project and is not global. Agent targets may install hooks, MCP config, Vortex analysis, and Context Augmentation. Prefer project-specific installation for one repository; global installation changes user-wide config.

`sonar context [action] [args...]` passes through to the separately installed Context Augmentation binary. Discover actions using `sonar context --help` after an eligible project-scoped agent integration. Do not invent actions from older releases.

## Diagnostics and maintenance

```bash
sonar system status --json
sonar update --status
```

`sonar update` installs software. `sonar system reset` removes credentials, managed binaries, integrations, and caches while preserving telemetry settings. Neither should be run as a troubleshooting experiment without explicit authorization.

## Sources

- [SonarQube CLI v1.7.0 command reference](https://raw.githubusercontent.com/SonarSource/sonarqube-cli/master/docs/llms.txt)
- [SonarQube CLI README](https://github.com/SonarSource/sonarqube-cli/blob/master/README.md)
- [SonarQube Cloud Web API](https://docs.sonarsource.com/sonarqube-cloud/appendices/web-api)
- [SonarQube Server Web API](https://docs.sonarsource.com/sonarqube-server/extension-guide/web-api)

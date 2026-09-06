---
name: sonarqube
description: >-
  Operate SonarQube-enabled repositories through the SonarQube CLI (`sonar`): verify authentication, discover project
  keys, inspect project metadata, issues, measures, and quality gates, analyze changed code, scan secrets and dependency
  risks, call authenticated APIs, trigger remediation, configure integrations, and troubleshoot the CLI. Use whenever
  the user mentions SonarQube, SonarQube Cloud/SonarCloud, Sonar project details, quality gates, Sonar issues, `sonar`
  commands, agentic analysis, dependency risks, secrets scanning, or Sonar integrations, even if they do not explicitly
  name this skill. Do not use for generic static analysis unrelated to SonarQube.
compatibility: >-
  Requires the SonarQube CLI executable `sonar`; commands were verified against v1.7.0. Some operations require Git, a
  SonarQube Cloud plan or Server edition, or product-specific entitlements.
---

# SonarQube CLI

Use the installed `sonar` CLI as the source of truth for a SonarQube-enabled project. Prefer structured, read-only inspection before analysis or mutation, and make the final response state the project, branch or pull request, command scope, and result.

## Start with a preflight

Run these checks from the repository or worktree the user placed in scope:

```bash
command -v sonar
sonar --version
sonar auth status
```

If the task involves installation state, integrations, or a confusing auth error, also run `sonar system status --json`.

Treat `sonar auth status` as the authoritative credential check. Do not infer authentication merely from a saved config file. In a sandbox, container, SSH session, or background agent, OS Keychain access may fail even though authentication works in the user's interactive terminal. Explain that distinction and use the environment-variable route in [authentication.md](references/authentication.md) when the user has made credentials available; never retrieve, print, or persist a token yourself.

The CLI is evolving. If the installed version differs from the reference snapshot or a command rejects an option, run `sonar --help` and `sonar <command> --help`, then follow the installed help. Read [commands.md](references/commands.md) when selecting flags or when the user asks what the CLI supports.

## Resolve the project before querying it

Use the exact project key, not the display name. Resolve it in this order:

1. Use a project key explicitly supplied by the user.
2. Inspect `sonar.projectKey` in `sonar-project.properties` at the repository root.
3. Inspect SonarQube for IDE connected-mode binding under `.sonarlint/`, such as `.sonarlint/connectedMode.json`.
4. Let the CLI auto-detect when the command supports it.
5. Search accessible projects with `sonar list projects -q <name-or-key>` and disambiguate multiple matches before continuing.

Do not silently choose among multiple project matches. Read [workflows.md](references/workflows.md) for project-detail, issue, quality-gate, and API recipes.

## Choose the correct analysis

| Intent | Command | Important behavior |
| --- | --- | --- |
| Analyze one or more changed source files | `sonar analyze --file <path>` | One file defaults to `STANDARD`; multiple files default to `DEEP`. `--file` is repeatable. |
| Analyze uncommitted Git changes | `sonar analyze` | Requires a Git repository and may run server-side analysis. |
| Analyze staged files | `sonar analyze --staged` | Uses `git diff --cached`. |
| Compare with a base ref | `sonar analyze --base <ref>` | Analyze the change set relative to the named ref. |
| Request explicit cross-file analysis | `sonar analyze --depth DEEP` | More context and potentially more time/data transfer. |
| Invoke the explicit Vortex route | `sonar analyze agentic ...` | Server-side analysis; limitations and entitlements apply. |
| Scan files for hardcoded secrets | `sonar analyze secrets <paths...>` | Scans paths or `--stdin`; treat a findings exit code as a finding, not an infrastructure failure. |
| Analyze dependency manifests | `sonar analyze dependency-risks` | Uploads manifests for security/license analysis; product entitlement may be required. |
| Run a traditional full-project CI scan | Project's existing scanner/build command | `sonar analyze` is not a replacement for every SonarScanner, Maven, Gradle, or .NET full-project pipeline. Inspect repository config and use the existing workflow only when requested. |

Before server-side analysis, inspect the selected files or Git change set so the scope is known. Avoid `--force` unless the user has explicitly accepted bypassing the large-change-set confirmation. Prefer `--format json` for deterministic parsing and retain the command exit status.

After fixing findings, rerun the same analysis scope. Do not expand from a file scan to the entire change set without saying so.

If the selected Git scope is empty, report that no files were analyzed. An empty change set is not evidence that the repository is clean.

## Prefer dedicated read commands

Use the narrowest command that answers the question:

```bash
sonar list projects -q <query>
sonar list issues --project <key> --format json
sonar quality-gate status --project <key> --format json --all
```

Add exactly one of `--branch <name>` or `--pull-request <id>` when needed. They are mutually exclusive for quality-gate status. Paginate project and issue results rather than assuming the first page is complete.

For an agent-facing issue summary, `--format toon` is compact. Use JSON when filtering, joining, or producing exact counts; use table or CSV only when that presentation is requested.

Use `sonar api get ...` when dedicated commands do not expose enough detail. Start with read-only GET requests and consult the connected instance's API description when endpoint support is uncertain:

```bash
sonar api get "/api/webservices/list"
```

API v1/v2 availability differs by Cloud region and Server version. The CLI rewrites supported v2 paths between Cloud and Server, but the server remains the authority. URL-encode project keys and other user-controlled query values.

## Handle state-changing commands deliberately

These commands can change local files, credentials, CLI state, code, or remote SonarQube state:

- `sonar remediate`
- `sonar api post|patch|put|delete ...`
- `sonar integrate ...`
- `sonar auth login|logout`
- `sonar config telemetry ...`
- `sonar update`
- `sonar system reset`

Resolve exact targets and explain the effect before running them. Browser login must be performed manually by the user; agents cannot authenticate themselves. Never pass tokens in command arguments, logs, committed files, or chat output.

For `sonar remediate`, preview eligible issue keys with `sonar list issues`, limit the selection to the requested issues, and note that non-interactive use requires `--issues` with at most 20 comma-separated keys.

For `sonar integrate`, inspect existing hooks and agent configuration first because the command writes project or global configuration. Use `--non-interactive` only after all choices are known. Do not combine project selection with global mode where the installed help marks them mutually exclusive.

Treat `sonar system reset --force` as destructive: it removes tokens, managed binaries, integrations, and cached files. Run it only when the user explicitly asks for a reset. Likewise, run `sonar auth logout`, telemetry changes, or an update only on explicit request.

## Report results clearly

For inspection tasks, report:

- CLI version and authenticated target without exposing credentials
- resolved project key and how it was resolved
- branch or pull request scope
- the requested result, including pagination or filters
- any product/edition limitation or incomplete API response
- a compact `Queries run` list naming the dedicated commands and GET endpoints used, so the result is auditable without exposing credentials

For analysis tasks, report files/change-set scope, depth, issue counts grouped usefully, exit status, and the next concrete remediation step. Never reproduce detected secret values; report only type and safe location metadata.

## Troubleshoot methodically

When a command fails:

1. Run its `--help` and compare flags with the installed version.
2. Recheck `sonar auth status` and `sonar system status --json`.
3. Confirm Cloud region or Server URL, organization, exact project key, branch/PR, and permissions.
4. Distinguish authentication, entitlement/edition, network/proxy/TLS, Git-scope, and no-findings outcomes.
5. Use `sonar api ... --verbose` only when needed and redact sensitive request or response data before reporting it.

Read [authentication.md](references/authentication.md) for credential and network guidance, [workflows.md](references/workflows.md) for complete operational recipes, and [commands.md](references/commands.md) for the v1.7.0 command inventory.

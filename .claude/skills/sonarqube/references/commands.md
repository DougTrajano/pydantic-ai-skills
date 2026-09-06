# SonarQube CLI v1.7.0 command inventory

Captured from installed `sonar` v1.7.0 help and SonarSource's v1.7.0 agent reference on 2026-09-05. Prefer installed `--help` when versions differ.

## Global and authentication

```text
sonar --help
sonar --version
sonar <command> --help
sonar auth login [-s|--server <server>] [-o|--org <org>]
sonar auth logout
sonar auth status
```

`login` uses browser authentication and the system keychain; agents cannot complete it for the user. Server selects a self-hosted URL, Cloud EU (`https://sonarcloud.io`, default), or Cloud US (`https://sonarqube.us`). Organization selects a Cloud organization. Logout removes the active connection token; status verifies it.

## Analysis

```text
sonar analyze [options]
sonar analyze agentic [options]
```

Shared scope options:

- `--file <path>`: specific file, repeatable.
- `--staged`: staged files (`git diff --cached`).
- `--base <ref>`: files changed relative to a ref.
- `-p, --project <project>`: override detected project key.
- `--force`: skip large-change confirmation.
- `--depth STANDARD|DEEP`: one-file default STANDARD; otherwise DEEP.
- `--format text|json`: default text.

`sonar analyze agentic` also has `--branch <branch>` and invokes server-side Vortex analysis.

```text
sonar analyze secrets [--stdin] [paths...]
```

Paths may be files/directories; `--stdin` reads standard input.

```text
sonar analyze dependency-risks [options]
```

- `-p, --project <project>`: auto-detected if omitted.
- `--format json|toon|table`: default table.
- `--statuses <statuses>`: raw values/presets, comma-separated.
- `--min-severity BLOCKER|HIGH|MEDIUM|LOW|INFO`.

Raw statuses: `new`, `open`, `confirm`, `accept`, `safe`, `fixed`. Presets: `active` = new/open/confirm; `to_fix` adds accept; `all` includes every status. Values combine as a union.

## Remediation

```text
sonar remediate [-p|--project <project>] [--issues <issueIds>]
```

Cloud-only. `--issues` accepts at most 20 comma-separated keys and is required without a TTY.

## Projects and issues

```text
sonar list projects [-q|--query <query>] [--page <number>] [--page-size <1-500>]
sonar list issues [options]
```

Issue options:

- `-p, --project <project>`
- `--statuses OPEN,CONFIRMED,FALSE_POSITIVE,ACCEPTED,FIXED`
- `--severities <comma-separated values appropriate to server mode>`
- `--format json|toon|table|csv` (default JSON)
- `--branch <branch>`
- `--pull-request <id>`
- `--page-size <1-500>` (default 500)
- `--page <number>` (default 1)

## Quality gate

```text
sonar quality-gate status [options]
sonar qg status [options]
```

The names are aliases. Options: `-p|--project`, `--format json|table`, exactly one of `--branch`/`--pull-request`, and `--all` to include passing conditions.

## Authenticated Web API

```text
sonar api [-d|--data <json>] [-v|--verbose] <method> <endpoint>
```

Methods: `get`, `post`, `patch`, `put`, `delete`. Endpoint starts with `/` and may contain query parameters. `--data` is a JSON string; the CLI chooses form or JSON body. The CLI adapts supported v1/v2 paths between Cloud and Server.

## Integrations

```text
sonar integrate git [options]
sonar integrate claude [options]
sonar integrate copilot [options]
sonar integrate codex [options]
sonar integrate antigravity [options]
sonar integrate cursor [options]
```

Git options: `--hook pre-commit|pre-push`, `--force`, `--non-interactive`, `--global`, `--dependency-risks`, and `-p|--project`. Dependency risks require a project and are not supported globally.

Agent options: `-p|--project`, `--non-interactive`, `-g|--global`. Inspect installed help for project/global exclusivity.

Effects by target:

- `claude`: secrets hooks, Vortex analysis, MCP Server.
- `copilot`: secrets hooks, Vortex analysis, MCP Server.
- `codex`: UserPromptSubmit secret-scanning hook.
- `antigravity`: secrets hooks, prompt-secret instructions, Vortex Context.
- `cursor`: MCP Server, secrets hooks, Vortex analysis.

## Context Augmentation

```text
sonar context [action] [args...]
```

Passthrough to the separately installed `sonar-context-augmentation` binary. Bare invocation and `--help` are forwarded. Eligible project-scoped integrations install it; the wrapper does not auto-install it. Discover actions dynamically with `sonar context --help`.

## Configuration, diagnostics, reset, and update

```text
sonar config telemetry --enabled
sonar config telemetry --disabled
sonar system status [--json]
sonar system reset [--force]
sonar update [--status] [--force]
```

System status covers auth, binaries, integrations, cache, network, health, and recommendations. Reset removes tokens, managed binaries, integrations, and caches while preserving telemetry settings. Update status is read-only; bare update installs latest; update force reinstalls latest.

## Sources

- [Current agent command reference](https://raw.githubusercontent.com/SonarSource/sonarqube-cli/master/docs/llms.txt)
- [Interactive command reference](https://sonarsource.com/sonarqube/cli/commands.html)

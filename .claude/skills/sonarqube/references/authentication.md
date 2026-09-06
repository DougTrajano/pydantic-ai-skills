# Authentication and environment

## Interactive authentication

Use `sonar auth status` to verify the active connection and token. `sonar auth login` opens a browser and saves credentials in the operating system keychain; it must be completed by the user, not an agent.

```bash
sonar auth login                                  # Cloud EU (default)
sonar auth login --server https://sonarqube.us    # Cloud US
sonar auth login --server https://sonarqube.example.com
```

For SonarQube Cloud, `--org <organization-key>` selects the organization. User tokens are required; project, global, or scoped organization tokens may not work for the CLI login workflow.

`sonar auth logout` removes the active connection token and may revoke a CLI-created token server-side. Run logout only on explicit user request.

## Automation and agent sessions

Prefer environment variables in CI, containers, SSH sessions, background tasks, and coding-agent sandboxes because those environments may not have access to the user's OS Keychain.

For SonarQube Cloud:

```text
SONARQUBE_CLI_TOKEN=<secret user token>
SONARQUBE_CLI_ORG=<organization key>
```

For self-hosted SonarQube Server:

```text
SONARQUBE_CLI_TOKEN=<secret user token>
SONARQUBE_CLI_SERVER=https://sonarqube.example.com
```

Set the complete pair. A token without its organization or server selector may cause the CLI to fall back to keychain credentials. Use a secret store or another user-approved injection mechanism. Never place tokens in tracked files, command-line arguments, or output.

After environment injection, verify without printing variables:

```bash
sonar auth status
sonar system status --json
```

Cloud EU is `https://sonarcloud.io`; Cloud US is `https://sonarqube.us`. An organization key is required for Cloud operations, while self-hosted automation requires its Server URL.

## Network and telemetry

`sonar system status --json` reports effective proxy, CA certificate, and client-certificate state with credentials redacted. Use it before guessing at TLS or connectivity failures.

The CLI supports enterprise proxy, custom CA, and mutual-TLS configuration through environment variables. Because the exact variable set is version-dependent, inspect the current official environment-variable documentation or installed CLI status rather than inventing names.

Telemetry and error reporting share the persisted toggle:

```bash
sonar config telemetry --enabled
sonar config telemetry --disabled
```

Use `DO_NOT_TRACK=1` to disable telemetry for one process/session without changing persisted configuration. Change telemetry only when requested.

## Common failures

- **Keychain unavailable:** If an agent is unauthenticated while the user's terminal works, explain process isolation and offer environment-variable auth. Do not ask the user to log in repeatedly.
- **Invalid token:** Confirm a non-expired user token, intended Cloud region/organization or Server, and project access.
- **Correct auth, missing project:** Run `sonar list projects -q <query>`, verify the exact key, and check Browse/analysis permissions.

## Sources

- [SonarQube CLI README](https://github.com/SonarSource/sonarqube-cli/blob/master/README.md)
- [SonarQube CLI command reference for agents](https://github.com/SonarSource/sonarqube-cli/blob/master/docs/llms.txt)
- [SonarQube CLI quickstart](https://docs.sonarsource.com/sonarqube-cli/quickstart-guide)

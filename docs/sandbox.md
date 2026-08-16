# Sandboxing

By default, file-based skill scripts run as local subprocesses via `LocalSkillScriptExecutor` — with the same user, filesystem, network and environment as your agent process. That is fine for skills you wrote and reviewed. It is not fine for skills pulled from a Git or S3 registry, or for any script whose contents you have not read.

Sandboxing swaps the execution backend without changing anything about how skills are authored or discovered.

## The extension point

Everything plugs in through the [`SkillScriptExecutor`][pydantic_ai_skills.SkillScriptExecutor] protocol:

```python
from typing import Any

from pydantic_ai_skills import SkillScript


class MySandboxExecutor:
    async def run(
        self,
        script: SkillScript,
        args: dict[str, Any] | None = None,
        ctx: Any | None = None,
    ) -> Any:
        ...
```

The protocol is structural — no base class to import, no registration step. Pass an instance as `script_executor`:

```python
from pydantic_ai_skills import SkillsDirectory, SkillsToolset

directory = SkillsDirectory(path="./skills", script_executor=MySandboxExecutor())
toolset = SkillsToolset(directories=[directory])
```

!!! note "Executors are per skill source"
    `SkillsToolset(directories=["./skills"])` builds a `SkillsDirectory` with the default local executor. To use a sandbox, construct the `SkillsDirectory` yourself and pass it in.

## Two reference implementations

!!! warning "These ship as examples, not as library code"
    Both executors live in [`examples/`](https://github.com/DougTrajano/pydantic-ai-skills/tree/main/examples), which is **not** part of the installed wheel — `pip install "pydantic-ai-skills[opensandbox]"` gives you the SDK, not the executor. Each example is self-contained, so copy the single file into your own project and import it from there. The snippets below use `myapp.*` to make that explicit; the extras exist so you can install the provider SDK the executor depends on.

Each is a complete, runnable agent example — one file holding the executor plus an `Agent` wired through `SkillsCapability`, serving on `http://127.0.0.1:7932`:

```bash
python -m examples.sandbox_localsandbox
```

They load the same `examples/skills` directory as every other example, so only the `script_executor=` argument differs from `basic_usage_capability.py`. The executor class is the part you copy and adapt. Both stage the **whole skill folder** into the sandbox — `SKILL.md`, `resources/`, `scripts/` and anything else — and run the script with its own directory as the working directory, so sibling modules, `../resources/data.json` and bundled data files resolve exactly as they do locally. Both return output in the same format as local execution, so switching backends does not change what the model sees.

Symlinks that resolve outside the skill folder are skipped with a warning during staging. Discovery already rejects them, but staging re-walks the folder, and following such a link would copy an arbitrary host file *into* the sandbox where the script could read it back out.

### OpenSandbox — container isolation

[OpenSandbox](https://github.com/opensandbox-group/OpenSandbox) runs each script in a container. Strongest isolation of the two, and a full CPython environment with real third-party packages.

```bash
pip install "pydantic-ai-skills[opensandbox]"
```

It talks to a server, so configure an endpoint first:

```bash
osb config set connection.domain localhost:8080
osb config set connection.protocol http
osb config set connection.api_key <your-api-key>
```

```python
from pydantic_ai_skills import SkillsDirectory

from myapp.sandbox_opensandbox import OpenSandboxScriptExecutor

executor = OpenSandboxScriptExecutor(
    image="opensandbox/code-interpreter:v1.1.0",
    timeout=30,
)
directory = SkillsDirectory(path="./skills", script_executor=executor)
```

### LocalSandbox — no container runtime

[LocalSandbox](https://github.com/coplane/localsandbox) combines just-bash and Pyodide over a SQLite-backed virtual filesystem. Nothing touches the host filesystem and no container runtime is needed, which makes it a good fit for local development and CI.

```bash
pip install "pydantic-ai-skills[localsandbox]"
```

```python
from pydantic_ai_skills import SkillsDirectory

from myapp.sandbox_localsandbox import LocalSandboxScriptExecutor

directory = SkillsDirectory(path="./skills", script_executor=LocalSandboxScriptExecutor())
```

There is **no CPython binary on `PATH`** inside LocalSandbox, so the executor takes two paths:

| Script type | Backend | Notes |
|---|---|---|
| `.sh`, `.bash`, `.zsh` | just-bash | Normal `--flag value` argv. |
| `.py` | Pyodide | Pyodide has no `sys.argv`; the executor injects one and runs the staged file with `runpy.run_path(..., run_name='__main__')`, so `argparse` and `if __name__ == '__main__'` work as written. `sys.exit(N)` is captured and reported as the exit code. |

Anything else raises a `ValueError` before a sandbox is provisioned.

Limitations to weigh: Pyodide ships a subset of the ecosystem, so scripts importing packages without Pyodide wheels will fail (`preload_packages=` helps for those that have them); subprocesses, sockets and host filesystem access are unavailable by design; and `abash` accepts no per-command timeout or environment — use `preset=` to choose a resource-limit profile.

## Lifecycle

Both executors create a **fresh sandbox per script run** and tear it down afterwards, so one skill invocation cannot observe another's state. Sandbox startup is not free, so both accept `reuse_sandbox=True` to keep a single sandbox warm across runs:

```python
executor = OpenSandboxScriptExecutor(reuse_sandbox=True)
...
await executor.aclose()  # LocalSandboxScriptExecutor exposes close()
```

This is a real trade-off, not a tuning knob: with reuse, files written by one script are visible to the next. Prefer the default when scripts come from a registry or are otherwise untrusted.

## Writing your own provider

The protocol is deliberately small, so adding a backend is mostly plumbing:

1. Derive the skill root and stage it. **Not** `Path(script.uri).parent` — that is the `scripts/` directory for the usual layout, which would leave out `SKILL.md` and `resources/`. `script.name` is relative to the skill folder (`scripts/run.py`), so walk that many levels up from the script file; both examples do this in `skill_root_for`.
2. Skip symlinks that resolve outside the skill root, or staging will copy host files into the sandbox. Both examples do this in `iter_stageable_files`.
3. Build the command. Reuse `LocalSkillScriptExecutor._build_args` for the `--flag value` marshalling rather than reimplementing the bool/list/`None` rules.
4. Execute with the script's own directory as the working directory, so relative paths behave as they do locally, and collect stdout, stderr and the exit code.
5. Format with `LocalSkillScriptExecutor._format_output(stdout_chunks, stderr_chunks, exit_code)` so the returned string matches local execution.

Follow the optional-dependency pattern used by both examples: import the SDK lazily inside a helper and raise an `ImportError` naming the extra that provides it.

## See also

- [Security](security.md) — the broader threat model, including path traversal, timeouts and tool access control.
- [Advanced](advanced.md#custom-script-executors) — custom executors for non-sandbox use cases such as remote execution and in-process debugging.

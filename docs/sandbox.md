# Sandbox Environment

Run skill scripts inside an isolated sandbox powered by [localsandbox](https://github.com/coplane/localsandbox), providing a Python execution environment (via Pyodide/WebAssembly) that cannot affect the host filesystem or processes.

## When to Use

| Executor | Best for |
|---|---|
| `LocalSkillScriptExecutor` (default) | Trusted scripts that need full Python package support (`pip` packages, file I/O, network) |
| `LocalSandboxSkillScriptExecutor` | Untrusted or agent-generated code; scripts limited to standard library and Pyodide packages |

## Prerequisites

`LocalSandboxSkillScriptExecutor` requires two things before use:

**1. Deno runtime** — localsandbox uses a Deno/TypeScript shim under the hood.

=== "macOS"
    ```bash
    brew install deno
    ```
=== "Linux / Windows"
    See the [Deno installation guide](https://deno.land/#installation).

**2. localsandbox Python package** — install the optional `sandbox` extra:

```bash
pip install pydantic-ai-skills[sandbox]
```

## Basic Usage

`LocalSandboxSkillScriptExecutor` is a drop-in replacement for the default
`LocalSkillScriptExecutor`. Pass it as `script_executor` when constructing a
`SkillsDirectory`:

```python
from pydantic_ai import Agent
from pydantic_ai_skills import SkillsToolset, SkillsDirectory
from pydantic_ai_skills.sandbox import LocalSandboxSkillScriptExecutor

executor = LocalSandboxSkillScriptExecutor(timeout=60)

toolset = SkillsToolset(
    directories=[
        SkillsDirectory(path='./skills', script_executor=executor)
    ]
)

agent = Agent(model='openai:gpt-4o', toolsets=[toolset])
result = await agent.run('Run the data-summary skill.')
```

Arguments are forwarded to scripts as `--key value` named flags — identical to how
`LocalSkillScriptExecutor` works — so existing skill scripts need no changes.

> **Note:** Only named arguments are supported. Positional arguments are not supported by the Agent Skills specification.

## Configuration

```python
from localsandbox import ExecutionPreset
from pydantic_ai_skills.sandbox import LocalSandboxSkillScriptExecutor

executor = LocalSandboxSkillScriptExecutor(
    timeout=60,                          # execution timeout in seconds (default: 30)
    preset=ExecutionPreset.STRICT,       # sandbox execution limits (default: NORMAL)
    preload_packages=['numpy', 'pandas'],# Pyodide packages to load (default: None)
)
```

### Execution Presets

| Preset | Max Loop Iterations | Max Commands |
|---|---|---|
| `ExecutionPreset.STRICT` | 100 | 500 |
| `ExecutionPreset.NORMAL` (default) | 1 000 | 5 000 |
| `ExecutionPreset.PERMISSIVE` | 10 000 | 50 000 |

### Shared Sandbox (Advanced)

By default a fresh sandbox is created for each script execution. To share state
(filesystem, KV store) across multiple executions, pass a pre-created
`LocalSandbox` instance:

```python
from localsandbox import LocalSandbox
from pydantic_ai_skills.sandbox import LocalSandboxSkillScriptExecutor

async with LocalSandbox() as sandbox:
    executor = LocalSandboxSkillScriptExecutor(sandbox=sandbox)
    # All script executions reuse the same sandbox instance
    toolset = SkillsToolset(
        directories=[SkillsDirectory(path='./skills', script_executor=executor)]
    )
    result = await agent.run('...')
```

## Limitations

| Limitation | Details |
|---|---|
| **Package support** | Limited to Python standard library and [Pyodide packages](https://pyodide.org/en/stable/usage/packages-in-pyodide.html). `pip install` packages (e.g. `arxiv`, `httpx`) are **not** available. |
| **Network access** | Pyodide/WASM does not support outbound network calls by default. |
| **Deno dependency** | Deno must be installed on `PATH` at runtime. Not suitable for environments that cannot install Deno. |
| **Beta status** | localsandbox has not been security-audited. Do not use for fully untrusted code execution in production. |
| **File path prefix** | Sandbox filesystem paths must start with `/data`. Scripts are executed in an isolated virtual filesystem. |

## Comparison Example

```python
# Default — uses host Python, full package access
from pydantic_ai_skills import SkillsDirectory, LocalSkillScriptExecutor

directory = SkillsDirectory(
    path='./skills',
    script_executor=LocalSkillScriptExecutor(timeout=30),
)

# Sandboxed — uses Pyodide, isolated filesystem
from pydantic_ai_skills.sandbox import LocalSandboxSkillScriptExecutor

directory = SkillsDirectory(
    path='./skills',
    script_executor=LocalSandboxSkillScriptExecutor(timeout=30),
)
```

"""Example running skill scripts inside a LocalSandbox virtual filesystem.

This example shows how to create an agent whose skill scripts execute in
a [LocalSandbox](https://github.com/coplane/localsandbox) virtual
filesystem (just-bash + Pyodide, no container runtime) rather than a local subprocess. Only the
`script_executor=` argument differs from `basic_usage_capability.py`.

Requires `pip install -e ".[examples,localsandbox]"`.

Note:
    `arxiv-search` is the only bundled skill with a script, and it needs the
    `arxiv` package plus network access, so it cannot run under Pyodide. The resource-only skills (`pydanticai-docs`,
    `web-research`) work normally, since resources are read on the host.
"""

from pathlib import Path

import logfire
import uvicorn
from dotenv import load_dotenv
from pydantic_ai import Agent

from pydantic_ai_skills import LocalSandboxScriptExecutor, SkillsCapability, SkillsDirectory

load_dotenv()

logfire.configure()
logfire.instrument_pydantic_ai()

# Get the skills directory (examples/skills)
skills_dir = Path(__file__).parent / 'skills'

# Initialize Skills Capability with skill scripts sandboxed via LocalSandbox
skills_capability = SkillsCapability(
    directories=[SkillsDirectory(path=skills_dir, script_executor=LocalSandboxScriptExecutor())],
)

# Create agent with skills capability
agent = Agent(
    model='gateway/openai:gpt-5.2',
    instructions='You are a helpful research assistant.',
    capabilities=[skills_capability],
)

app = agent.to_web()

if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=7932)

"""Example running skill scripts inside an OpenSandbox container.

This example shows how to create an agent whose skill scripts execute in
an [OpenSandbox](https://github.com/opensandbox-group/OpenSandbox)
container rather than a local subprocess. Only the
`script_executor=` argument differs from `basic_usage_capability.py`.

Requires `pip install -e ".[examples,opensandbox]"`.

Also requires a reachable OpenSandbox server:

    osb config set connection.domain localhost:8080
    osb config set connection.protocol http
    osb config set connection.api_key <your-api-key>

Note:
    `arxiv-search` is the only bundled skill with a script, and it needs the
    `arxiv` package, so it runs only if the container image provides it. The resource-only skills (`pydanticai-docs`,
    `web-research`) work normally, since resources are read on the host.
"""

from pathlib import Path

import logfire
import uvicorn
from dotenv import load_dotenv
from pydantic_ai import Agent

from pydantic_ai_skills import OpenSandboxScriptExecutor, SkillsCapability, SkillsDirectory

load_dotenv()

logfire.configure()
logfire.instrument_pydantic_ai()

# Get the skills directory (examples/skills)
skills_dir = Path(__file__).parent / 'skills'

# Initialize Skills Capability with skill scripts sandboxed via OpenSandbox
skills_capability = SkillsCapability(
    directories=[SkillsDirectory(path=skills_dir, script_executor=OpenSandboxScriptExecutor())],
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

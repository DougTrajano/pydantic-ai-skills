"""Sandbox example demonstrating LocalSandboxSkillScriptExecutor with Pydantic AI.

This example runs skill scripts inside an isolated Pyodide/WASM sandbox instead
of the host Python interpreter, protecting the host environment from script
side effects.

Prerequisites:
    - Deno runtime on PATH: brew install deno
    - Python package:       pip install pydantic-ai-skills[sandbox]

The ``text-utils`` skill used here is intentionally limited to the Python
standard library so it is fully compatible with Pyodide.

Usage:
    python examples/sandbox_usage.py
    # Then open http://127.0.0.1:7933 and ask:
    # "Count the words in: The quick brown fox jumps over the lazy dog"
"""

from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext

from pydantic_ai_skills import SkillsDirectory, SkillsToolset
from pydantic_ai_skills.sandbox import LocalSandboxSkillScriptExecutor

load_dotenv()

# Sandboxed executor: scripts run inside Pyodide/WASM, not on the host interpreter
executor = LocalSandboxSkillScriptExecutor(timeout=30)

# Point to the bundled text-utils skill (stdlib-only, Pyodide-compatible)
skills_dir = Path(__file__).parent / 'skills' / 'text-utils'

skills_toolset = SkillsToolset(
    directories=[
        SkillsDirectory(path=skills_dir, script_executor=executor),
    ]
)

agent = Agent(
    model='openai:gpt-4o',
    instructions='You are a helpful text analysis assistant.',
    toolsets=[skills_toolset],
)


@agent.instructions
async def add_skills(ctx: RunContext) -> str | None:
    return await skills_toolset.get_instructions(ctx)


app = agent.to_web()

if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=7933)

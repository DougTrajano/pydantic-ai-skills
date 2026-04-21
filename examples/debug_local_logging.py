"""Debug file-based skill scripts in-process with local logging.

This example demonstrates a development-only pattern for debugging script files
with breakpoints by replacing subprocess execution with an in-process callable
executor. It also writes a local execution log for quick diagnostics.
"""

from __future__ import annotations

import asyncio
import io
import json
import runpy
import sys
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic_ai_skills import CallableSkillScriptExecutor, SkillsDirectory

EXAMPLES_DIR = Path(__file__).parent
TMP_DIR = EXAMPLES_DIR / 'tmp'
SKILL_DIR = TMP_DIR / 'debug-logging-skill'
LOG_FILE = TMP_DIR / 'debug-local-executor.log'


def _append_log(message: str) -> None:
    """Append one line to the local debug log file."""
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    with LOG_FILE.open('a', encoding='utf-8') as f:
        f.write(f'[{timestamp}] {message}\n')


def _write_demo_skill_files() -> Path:
    """Create a self-contained demo skill used by this example."""
    scripts_dir = SKILL_DIR / 'scripts'
    scripts_dir.mkdir(parents=True, exist_ok=True)

    skill_md = """---
name: debug-logging-skill
description: Skill used to demonstrate in-process debugging for scripts.
---

Use this skill to test local script execution while debugging.
"""

    script_py = """#!/usr/bin/env python3
import json
import sys


def main() -> None:
    # Set a breakpoint on the line below when running this example in a debugger.
    payload = {
        'argv': sys.argv[1:],
        'message': 'Script executed in-process',
    }
    print(json.dumps(payload))


if __name__ == '__main__':
    main()
"""

    (SKILL_DIR / 'SKILL.md').write_text(skill_md, encoding='utf-8')
    script_path = scripts_dir / 'echo_args.py'
    script_path.write_text(script_py, encoding='utf-8')
    return script_path


def _args_to_argv(args: dict[str, Any] | None) -> list[str]:
    """Convert named args into CLI-style arguments for the script."""
    if not args:
        return []

    argv: list[str] = []
    for key, value in args.items():
        argv.append(f'--{key}')
        if isinstance(value, dict | list | tuple):
            argv.append(json.dumps(value))
        else:
            argv.append(str(value))
    return argv


async def _in_process_executor(*, script: Any, args: dict[str, Any] | None = None) -> str:
    """Run a discovered script file in-process and capture output.

    This is intentionally development-oriented and mirrors subprocess behavior
    only enough for local debugging and trace logging.
    """
    # Keep this executor async to match common custom executor signatures.
    await asyncio.sleep(0)

    if not getattr(script, 'uri', None):
        raise ValueError('Script has no URI')

    script_uri = str(script.uri)
    argv = _args_to_argv(args)
    _append_log(f'start script={script.name} uri={script_uri} args={args or {}}')

    stdout_stream = io.StringIO()
    stderr_stream = io.StringIO()
    original_argv = sys.argv[:]

    try:
        sys.argv = [script_uri, *argv]
        with redirect_stdout(stdout_stream), redirect_stderr(stderr_stream):
            runpy.run_path(script_uri, run_name='__main__')
    finally:
        sys.argv = original_argv

    stdout_output = stdout_stream.getvalue().strip()
    stderr_output = stderr_stream.getvalue().strip()
    _append_log(f'finish script={script.name} stdout_len={len(stdout_output)} stderr_len={len(stderr_output)}')

    if stdout_output and stderr_output:
        return f'{stdout_output}\nSTDERR:\n{stderr_output}'
    return stdout_output or stderr_output or ''


async def main() -> None:
    """Run the demo skill script with an in-process callable executor."""
    script_path = _write_demo_skill_files()

    # Clear previous run logs for a clean demonstration.
    if LOG_FILE.exists():
        LOG_FILE.unlink()

    executor = CallableSkillScriptExecutor(func=_in_process_executor)
    skills_dir = SkillsDirectory(path=TMP_DIR, script_executor=executor, validate=True)

    skill = skills_dir.load_skill(str(SKILL_DIR.resolve()))
    script = next(s for s in skill.scripts if s.name.endswith('echo_args.py'))

    output = await script.run(None, args={'query': 'debug', 'limit': 3})

    print('Debug demo finished.')
    print(f'Script file: {script_path}')
    print(f'Log file: {LOG_FILE}')
    print('Script output:')
    print(output)


if __name__ == '__main__':
    asyncio.run(main())

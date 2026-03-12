"""Sandboxed skill script executor using localsandbox.

This module provides:
- LocalSandboxSkillScriptExecutor: Execute scripts inside an isolated localsandbox environment

Requires:
    localsandbox package (optional): pip install pydantic-ai-skills[sandbox]
    Deno runtime: https://deno.land

Note:
    Scripts executed in the sandbox are limited to Python standard library and
    Pyodide-supported packages. Third-party packages like ``arxiv`` or
    ``requests`` are not available unless they ship as Pyodide wheels.

Implementations:
- [`LocalSandboxSkillScriptExecutor`][pydantic_ai_skills.LocalSandboxSkillScriptExecutor]: Execute scripts in an isolated Pyodide sandbox
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import anyio

from .exceptions import SkillScriptExecutionError
from .types import SkillScript


class LocalSandboxSkillScriptExecutor:
    """Execute skill scripts inside an isolated localsandbox environment.

    Uses Pyodide (WebAssembly) for Python execution, providing an isolated filesystem
    and protecting the host environment from script side effects. Command-line arguments
    are injected via ``sys.argv`` to match the behaviour of
    [`LocalSkillScriptExecutor`][pydantic_ai_skills.LocalSkillScriptExecutor].

    Note:
        Scripts are limited to the Python standard library and Pyodide-supported packages.
        Third-party packages (e.g. ``arxiv``, ``requests``) are not available unless they
        ship as Pyodide wheels. Use ``preload_packages`` to load Pyodide-compatible packages.

    Requires:
        - ``localsandbox`` package: ``pip install pydantic-ai-skills[sandbox]``
        - Deno runtime on ``PATH``: ``brew install deno`` (macOS) or see https://deno.land

    Example:
        ```python
        from pydantic_ai_skills import SkillsDirectory
        from pydantic_ai_skills.sandbox import LocalSandboxSkillScriptExecutor

        executor = LocalSandboxSkillScriptExecutor(timeout=60)
        directory = SkillsDirectory(path='./skills', script_executor=executor)
        ```

    Attributes:
        timeout: Execution timeout in seconds.
    """

    def __init__(
        self,
        timeout: int = 30,
        preset: Any = None,
        preload_packages: list[str] | None = None,
        sandbox: Any | None = None,
    ) -> None:
        """Initialize the sandboxed script executor.

        Args:
            timeout: Execution timeout in seconds (default: 30).
            preset: ``localsandbox.ExecutionPreset`` controlling sandbox execution limits.
                Accepts the enum value or ``None`` to use ``ExecutionPreset.NORMAL``.
            preload_packages: Pyodide packages to preload before script execution
                (e.g. ``['numpy', 'pandas']``). Only Pyodide-compatible packages are supported.
            sandbox: Pre-created ``LocalSandbox`` instance for sharing state across multiple
                executions. When ``None`` (default), a fresh sandbox is created per execution.

        Raises:
            ImportError: If ``localsandbox`` is not installed or Deno is absent.
        """
        try:
            from localsandbox import LocalSandbox as _LocalSandbox  # noqa: F401
        except ImportError as e:
            raise ImportError(
                'localsandbox is required for LocalSandboxSkillScriptExecutor.\n'
                'Install it with: pip install pydantic-ai-skills[sandbox]\n'
                'Also ensure Deno is installed on your PATH: https://deno.land'
            ) from e

        self.timeout = timeout
        self._preload_packages = preload_packages
        self._shared_sandbox = sandbox

        if preset is None:
            from localsandbox import ExecutionPreset

            self._preset = ExecutionPreset.NORMAL
        else:
            self._preset = preset

    def _build_argv(self, script_name: str, args: dict[str, Any] | None) -> list[str]:
        """Build sys.argv list from args dict (mirrors LocalSkillScriptExecutor rules).

        Args:
            script_name: Script filename used as argv[0].
            args: Named arguments dict.

        Returns:
            List of strings forming the argv vector.
        """
        argv: list[str] = [script_name]
        if not args:
            return argv
        for key, value in args.items():
            if isinstance(value, bool):
                if value:
                    argv.append(f'--{key}')
            elif isinstance(value, list):
                for item in value:
                    argv.append(f'--{key}')
                    argv.append(str(item))
            elif value is not None:
                argv.append(f'--{key}')
                argv.append(str(value))
        return argv

    async def run(
        self,
        script: SkillScript,
        args: dict[str, Any] | None = None,
    ) -> Any:
        """Run a skill script inside a localsandbox environment.

        The script file is read from disk, a ``sys.argv`` preamble is prepended to
        simulate CLI argument passing, and the combined code is executed via
        ``aexecute_python``.

        Args:
            script: The script to run. Must have a ``uri`` attribute pointing to a
                Python source file on disk.
            args: Named arguments as a dictionary (same conversion rules as
                [`LocalSkillScriptExecutor`][pydantic_ai_skills.LocalSkillScriptExecutor]):
                boolean ``True`` emits flag only, ``False``/``None`` omits it,
                lists repeat the flag, other types are converted to strings.

        Returns:
            Combined stdout and stderr output from sandboxed execution.

        Raises:
            SkillScriptExecutionError: If execution fails, times out, or the script has no URI.
        """
        if script.uri is None:
            raise SkillScriptExecutionError(f"Script '{script.name}' has no URI for sandbox execution")

        script_path = Path(script.uri)

        try:
            source = script_path.read_text(encoding='utf-8')
        except OSError as e:
            raise SkillScriptExecutionError(f"Failed to read script '{script.name}': {e}") from e

        preamble = f'import sys\nsys.argv = {json.dumps(self._build_argv(script_path.name, args))}\n'
        code = preamble + source

        from localsandbox import LocalSandbox

        try:
            result = None

            if self._shared_sandbox is not None:
                with anyio.move_on_after(self.timeout) as scope:
                    result = await self._shared_sandbox.aexecute_python(
                        code,
                        preload_packages=self._preload_packages,
                    )
                if scope.cancelled_caught or result is None:
                    raise SkillScriptExecutionError(f"Script '{script.name}' timed out after {self.timeout} seconds")
            else:
                with anyio.move_on_after(self.timeout) as scope:
                    with LocalSandbox(preset=self._preset) as sb:
                        result = await sb.aexecute_python(
                            code,
                            preload_packages=self._preload_packages,
                        )
                if scope.cancelled_caught or result is None:
                    raise SkillScriptExecutionError(f"Script '{script.name}' timed out after {self.timeout} seconds")

        except SkillScriptExecutionError:
            raise
        except Exception as e:
            raise SkillScriptExecutionError(f"Failed to execute script '{script.name}' in sandbox: {e}") from e

        output = result.stdout or ''
        if result.stderr:
            output += f'\n\nStderr:\n{result.stderr}'
        if result.error:
            output += f'\n\nError:\n{result.error}'

        return output.strip() or '(no output)'

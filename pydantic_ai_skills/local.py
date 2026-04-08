"""Filesystem-based skill resources, scripts, and executors.

This module provides:
- FileBasedSkillResource: File-based skill resource implementation
- FileBasedSkillScript: File-based skill script implementation
- LocalSkillScriptExecutor: Execute scripts using local subprocesses
- CallableSkillScriptExecutor: Wrap a callable in the executor interface
- Factory functions for creating file-based resources and scripts

Implementations:
- [`LocalSkillScriptExecutor`][pydantic_ai_skills.LocalSkillScriptExecutor]: Execute scripts using local subprocesses
- [`CallableSkillScriptExecutor`][pydantic_ai_skills.CallableSkillScriptExecutor]: Wrap a callable in the executor interface
- [`FileBasedSkillResource`][pydantic_ai_skills.FileBasedSkillResource]: File-based resource with disk loading
- [`FileBasedSkillScript`][pydantic_ai_skills.FileBasedSkillScript]: File-based script with subprocess execution
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import signal
import subprocess as _subprocess
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import anyio
import anyio.abc
import yaml
from pydantic_ai._utils import is_async_callable, run_in_executor

from .exceptions import SkillResourceLoadError, SkillScriptExecutionError
from .types import SkillResource, SkillScript


@dataclass
class FileBasedSkillResource(SkillResource):
    """A file-based skill resource that loads content from disk.

    This subclass extends SkillResource to add filesystem support.
    The uri attribute points to the file location and serves as the unique identifier.
    """

    async def load(self, ctx: Any, args: dict[str, Any] | None = None) -> Any:
        """Load resource content from file.

        JSON and YAML files are parsed; falls back to text if parsing fails.
        Other file types are returned as UTF-8 text.

        Args:
            ctx: RunContext for accessing dependencies (unused for file-based resources).
            args: Named arguments (unused for file-based resources).

        Returns:
            Parsed dict (JSON/YAML) or UTF-8 text string.

        Raises:
            SkillResourceLoadError: If file cannot be read or path is invalid.
        """
        if not self.uri:
            raise SkillResourceLoadError(f"Resource '{self.name}' has no URI")

        resource_path = Path(self.uri)

        try:
            content = resource_path.read_text(encoding='utf-8')
        except OSError as e:
            raise SkillResourceLoadError(f"Failed to read resource '{self.name}': {e}") from e

        file_extension = Path(self.name).suffix.lower()

        if file_extension == '.json':
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return content

        elif file_extension in ('.yaml', '.yml'):
            try:
                return yaml.safe_load(content)
            except yaml.YAMLError:
                return content

        return content


class LocalSkillScriptExecutor:
    """Execute skill scripts using local subprocesses.

    Executes file-based scripts as subprocesses with args passed as command-line named arguments.
    Dictionary keys are used exactly as provided (e.g., {"max-papers": 5} becomes --max-papers 5).
    A shebang line is used first when present and resolvable, then suffix-based fallback
    is used for compatibility. Other files are executed directly.
    Uses anyio.open_process with custom output collection and timeout handling for
    async-compatible subprocess execution.

    Note:
        All scripts must accept named arguments. Positional arguments are not supported.

    Attributes:
        timeout: Execution timeout in seconds.
    """

    _SHELL_INTERPRETERS: dict[str, list[str]] = {
        '.sh': ['sh'],
        '.bash': ['bash'],
        '.zsh': ['zsh'],
        '.fish': ['fish'],
        '.bat': ['cmd', '/c'],
        '.cmd': ['cmd', '/c'],
    }

    def __init__(
        self,
        python_executable: str | Path | None = None,
        timeout: int = 30,
    ) -> None:
        """Initialize the local script executor.

        Args:
            python_executable: Path to Python executable. If None, uses sys.executable.
            timeout: Execution timeout in seconds (default: 30).
        """
        self._python_executable = str(python_executable) if python_executable else sys.executable
        self.timeout = timeout

    @staticmethod
    def _resolve_interpreter(interpreter: str) -> str | None:
        """Resolve a shebang interpreter to an executable path."""
        if Path(interpreter).is_absolute():
            path = Path(interpreter)
            return str(path) if path.exists() else None
        return shutil.which(interpreter)

    def _extract_shebang_command(self, script_path: Path) -> list[str] | None:
        """Return an interpreter command from shebang if present and resolvable."""
        try:
            with script_path.open('rb') as handle:
                first_line = handle.readline()
        except OSError:
            return None

        if not first_line.startswith(b'#!'):
            return None

        shebang = first_line[2:].decode('utf-8', errors='ignore').strip()
        if not shebang:
            return None

        parts = shlex.split(shebang)
        if not parts:
            return None

        if Path(parts[0]).name == 'env':
            idx = 1
            while idx < len(parts) and parts[idx].startswith('-'):
                idx += 1
            if idx >= len(parts):
                return None
            interpreter = parts[idx]
            interpreter_args = parts[idx + 1 :]
        else:
            interpreter = parts[0]
            interpreter_args = parts[1:]

        resolved = self._resolve_interpreter(interpreter)
        if not resolved:
            return None

        return [resolved, *interpreter_args]

    def _build_command(self, script_path: Path) -> list[str]:
        """Build subprocess command using shebang-first dispatch with compatibility fallback."""
        shebang_command = self._extract_shebang_command(script_path)
        if shebang_command:
            return [*shebang_command, str(script_path)]

        suffix = script_path.suffix.lower()
        if suffix == '.py':
            return [self._python_executable, str(script_path)]
        if suffix == '.ps1':
            powershell = shutil.which('pwsh') or shutil.which('powershell')
            if powershell:
                return [powershell, '-File', str(script_path)]
        if suffix in self._SHELL_INTERPRETERS:
            return [*self._SHELL_INTERPRETERS[suffix], str(script_path)]
        return [str(script_path)]

    @staticmethod
    def _build_args(cmd: list[str], args: dict[str, Any]) -> None:
        """Append named arguments to cmd in-place."""
        for key, value in args.items():
            if isinstance(value, bool):
                if value:
                    cmd.append(f'--{key}')
            elif isinstance(value, list):
                for item in cast(list[Any], value):
                    cmd.append(f'--{key}')
                    cmd.append(str(item))
            elif value is not None:
                cmd.append(f'--{key}')
                cmd.append(str(value))

    @staticmethod
    def _format_output(stdout_chunks: list[bytes], stderr_chunks: list[bytes], return_code: int) -> str:
        """Decode and combine stdout, stderr, and exit code into a single string."""
        output = b''.join(stdout_chunks).decode('utf-8', errors='replace')
        stderr_output = b''.join(stderr_chunks).decode('utf-8', errors='replace')
        if stderr_output:
            output += f'\n\nStderr:\n{stderr_output}'
        if return_code != 0:
            output += f'\n\nScript exited with code {return_code}'
        return output.strip() or '(no output)'

    async def _drain_stream(self, stream: anyio.abc.ByteReceiveStream | None, chunks: list[bytes]) -> None:
        """Drain a process output stream into chunks until EOF."""
        if stream is None:
            return

        while True:
            try:
                chunk = await stream.receive()
            except anyio.EndOfStream:
                break

            if chunk == b'':
                break

            chunks.append(chunk)

    async def _collect_output(
        self,
        process: anyio.abc.Process,
        stdout_chunks: list[bytes],
        stderr_chunks: list[bytes],
    ) -> int:
        """Read stdout/stderr concurrently, then wait for the process to exit."""
        async with anyio.create_task_group() as io_tg:
            io_tg.start_soon(self._drain_stream, process.stdout, stdout_chunks)
            io_tg.start_soon(self._drain_stream, process.stderr, stderr_chunks)

        return await process.wait()

    @staticmethod
    def _kill_process(process: anyio.abc.Process, use_process_group: bool) -> None:
        """Terminate a process and its process group when possible."""
        if use_process_group:
            try:
                # Validate PID before calling os.getpgid
                if process.pid and process.pid > 0:
                    pgid = os.getpgid(process.pid)
                    if pgid > 0:
                        os.killpg(pgid, signal.SIGKILL)
                        return
            except (OSError, ValueError):
                # Process no longer exists or group doesn't exist
                pass
        try:
            process.kill()
        except OSError:
            # Process already terminated
            pass

    async def _run_with_timeout(
        self,
        process: anyio.abc.Process,
        stdout_chunks: list[bytes],
        stderr_chunks: list[bytes],
        use_process_group: bool,
    ) -> tuple[int, bool]:
        """Collect process output while enforcing timeout."""
        return_code = 0
        timed_out = False

        def _kill() -> None:
            nonlocal timed_out
            timed_out = True
            self._kill_process(process, use_process_group)

        async with anyio.create_task_group() as tg:

            async def _kill_after_timeout() -> None:
                await anyio.sleep(self.timeout)
                _kill()

            async def _run() -> None:
                nonlocal return_code
                return_code = await self._collect_output(process, stdout_chunks, stderr_chunks)
                tg.cancel_scope.cancel()

            tg.start_soon(_kill_after_timeout)
            tg.start_soon(_run)

        return return_code, timed_out

    async def _start_process(
        self,
        cmd: list[str],
        cwd: str,
        use_process_group: bool,
        script_name: str,
    ) -> anyio.abc.Process:
        """Start script subprocess and normalize startup errors."""
        try:
            return await anyio.open_process(
                cmd,
                stdin=_subprocess.DEVNULL,
                stdout=_subprocess.PIPE,
                stderr=_subprocess.PIPE,
                cwd=cwd,
                start_new_session=use_process_group,
            )
        except OSError as e:
            raise SkillScriptExecutionError(f"Failed to execute script '{script_name}': {e}") from e

    async def run(
        self,
        script: SkillScript,
        args: dict[str, Any] | None = None,
    ) -> Any:
        """Run a skill script locally using subprocess.

        Args:
            script: The script to run.
            args: Named arguments as a dictionary.
                Boolean True emits flag only, False/None omits it,
                lists repeat the flag for each item, other types convert to string.

        Returns:
            Combined stdout and stderr output.

        Raises:
            SkillScriptExecutionError: If execution fails or times out.
        """
        if script.uri is None:
            raise SkillScriptExecutionError(f"Script '{script.name}' has no URI for subprocess execution")

        script_path = Path(script.uri)
        cmd = self._build_command(script_path)
        if args:
            self._build_args(cmd, args)

        cwd = str(script_path.parent)
        use_process_group = sys.platform != 'win32'
        process = await self._start_process(cmd, cwd, use_process_group, script.name)

        stdout_chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []
        return_code = 0
        timed_out = False

        try:
            return_code, timed_out = await self._run_with_timeout(
                process=process,
                stdout_chunks=stdout_chunks,
                stderr_chunks=stderr_chunks,
                use_process_group=use_process_group,
            )
        finally:
            try:
                await process.aclose()
            except OSError:
                pass

        if timed_out:
            raise SkillScriptExecutionError(f"Script '{script.name}' timed out after {self.timeout} seconds")

        return self._format_output(stdout_chunks, stderr_chunks, return_code)


class CallableSkillScriptExecutor:
    """Wraps a callable in a script executor interface.

    Allows users to provide custom execution logic for file-based scripts
    instead of using subprocess execution. Useful for remote execution, sandboxed
    execution, or other custom scenarios.

    Example:
        ```python
        from pydantic_ai.toolsets.skills import CallableSkillScriptExecutor, SkillsDirectory

        async def my_executor(script, args=None):
            # Custom execution logic - script.uri contains the file path
            return f"Executed {script.name} at {script.uri} with {args}"

        executor = CallableSkillScriptExecutor(func=my_executor)
        directory = SkillsDirectory(path="./skills", script_executor=executor)
        ```
    """

    def __init__(self, func: Callable[..., Any]) -> None:
        """Initialize the callable executor.

        Args:
            func: Callable that executes scripts. Can be sync or async.
                Should accept keyword arguments: script (SkillScript) and args (dict[str, Any] | None),
                and return the script output as a string. The script's uri attribute contains the file path.
        """
        self._func = func
        self._is_async = is_async_callable(func)

    async def run(
        self,
        script: SkillScript,
        args: dict[str, Any] | None = None,
    ) -> Any:
        """Run using the wrapped callable.

        Args:
            script: The script to run.
            args: Named arguments as a dictionary.

        Returns:
            Script output (can be any type like str, dict, etc.).
        """
        if self._is_async:
            function = cast(Callable[..., Awaitable[Any]], self._func)
            return await function(script=script, args=args)
        else:
            return await run_in_executor(self._func, script=script, args=args)


def create_file_based_resource(
    name: str,
    uri: str,
    description: str | None = None,
) -> FileBasedSkillResource:
    """Create a file-based resource.

    Args:
        name: Resource name (e.g., "FORMS.md", "data.json").
        uri: Path to the resource file.
        description: Optional resource description.

    Returns:
        FileBasedSkillResource instance.
    """
    return FileBasedSkillResource(
        name=name,
        uri=uri,
        description=description,
    )


@dataclass
class FileBasedSkillScript(SkillScript):
    """A file-based skill script that executes via subprocess.

    This subclass extends SkillScript to add subprocess execution support.
    The uri attribute points to the Python script file and serves as the unique identifier.

    Attributes:
        executor: Executor for running the script.
    """

    executor: LocalSkillScriptExecutor | CallableSkillScriptExecutor = LocalSkillScriptExecutor()

    async def run(self, ctx: Any, args: dict[str, Any] | None = None) -> Any:
        """Execute script file via subprocess.

        Args:
            ctx: RunContext for accessing dependencies (unused for file-based scripts).
            args: Named arguments passed as command-line arguments.
                Argument conversion rules:
                - Boolean True: emits flag only (e.g., --verbose)
                - Boolean False or None: omits the flag
                - List: repeats flag for each item (e.g., --item a --item b)
                - Other: converts to string (e.g., --query test)

        Returns:
            Script output (stdout + stderr).

        Raises:
            SkillScriptExecutionError: If execution fails.
        """
        if not self.uri:
            raise SkillScriptExecutionError(f"Script '{self.name}' has no URI")

        return await self.executor.run(self, args)


def create_file_based_script(
    name: str,
    uri: str,
    skill_name: str,
    executor: LocalSkillScriptExecutor | CallableSkillScriptExecutor,
    description: str | None = None,
) -> FileBasedSkillScript:
    """Create a file-based script with executor.

    Args:
        name: Script name (includes .py extension).
        uri: Path to the script file.
        skill_name: Name of the parent skill.
        executor: Executor for running the script.
        description: Optional script description.

    Returns:
        FileBasedSkillScript instance.
    """
    return FileBasedSkillScript(
        name=name,
        uri=uri,
        skill_name=skill_name,
        description=description,
        executor=executor,
    )

"""Run skill scripts inside an OpenSandbox container.

Implements the [`SkillScriptExecutor`][pydantic_ai_skills.SkillScriptExecutor]
protocol on top of [OpenSandbox](https://github.com/opensandbox-group/OpenSandbox),
so file-based skill scripts execute in a remote container instead of a local
subprocess.

Lifecycle: a fresh sandbox is created for every script run and killed afterwards,
so runs cannot observe each other's state. Pass ``reuse_sandbox=True`` to keep one
sandbox warm across runs — much faster, but state leaks between skill invocations.

Staging: the whole skill directory (the script's parent folder) is uploaded, so
sibling modules and bundled data files resolve exactly as they do locally.

Requirements:
    pip install "pydantic-ai-skills[opensandbox]"

OpenSandbox talks to a server, so a reachable endpoint must be configured first:

    osb config set connection.domain localhost:8080
    osb config set connection.protocol http
    osb config set connection.api_key <your-api-key>

Example:
    ```python
    from pydantic_ai_skills import SkillsDirectory

    from examples.sandbox_opensandbox import OpenSandboxScriptExecutor

    executor = OpenSandboxScriptExecutor(image='opensandbox/code-interpreter:v1.1.0')
    directory = SkillsDirectory(path='./skills', script_executor=executor)
    ```
"""

from __future__ import annotations

import shlex
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic_ai_skills import LocalSkillScriptExecutor, SkillScript, SkillScriptExecutor

if TYPE_CHECKING:
    from opensandbox import Sandbox

# Suffix -> interpreter, resolved inside the sandbox rather than on the host.
_SANDBOX_INTERPRETERS: dict[str, list[str]] = {
    '.py': ['python3'],
    '.sh': ['sh'],
    '.bash': ['bash'],
    '.zsh': ['zsh'],
    '.fish': ['fish'],
}


def _require_opensandbox() -> Any:
    """Import the opensandbox SDK, or explain which extra installs it."""
    try:
        from opensandbox import Sandbox as _Sandbox
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ImportError(
            'OpenSandboxScriptExecutor requires the "opensandbox" package. '
            'Install it with: pip install "pydantic-ai-skills[opensandbox]"'
        ) from exc

    return _Sandbox


class OpenSandboxScriptExecutor(SkillScriptExecutor):
    """Execute file-based skill scripts inside an OpenSandbox container.

    Attributes:
        timeout: Per-script execution timeout in seconds.
    """

    def __init__(
        self,
        image: str = 'opensandbox/code-interpreter:v1.1.0',
        *,
        timeout: int = 30,
        workdir: str = '/tmp/skills',
        env_vars: dict[str, str] | None = None,
        reuse_sandbox: bool = False,
        sandbox_timeout: timedelta = timedelta(minutes=10),
    ) -> None:
        """Initialize the OpenSandbox executor.

        Args:
            image: Container image used for each sandbox.
            timeout: Per-script execution timeout in seconds.
            workdir: Directory inside the sandbox that the skill folder is staged into.
            env_vars: Environment variables exported to the script process.
            reuse_sandbox: Keep a single sandbox alive across runs instead of
                creating and killing one per run. Faster, but runs share state.
            sandbox_timeout: Lifetime of the sandbox itself, passed to ``Sandbox.create``.
        """
        self.timeout = timeout
        self._image = image
        self._workdir = workdir.rstrip('/') or '/tmp/skills'
        self._env_vars = dict(env_vars or {})
        self._reuse_sandbox = reuse_sandbox
        self._sandbox_timeout = sandbox_timeout
        self._sandbox: Sandbox | None = None
        # Reused for its host-independent argument marshalling and output formatting.
        self._formatter = LocalSkillScriptExecutor()

    async def _get_sandbox(self) -> Sandbox:
        """Return the sandbox to run in, creating one when needed."""
        if self._reuse_sandbox and self._sandbox is not None:
            return self._sandbox

        sandbox_cls = _require_opensandbox()
        sandbox: Sandbox = await sandbox_cls.create(
            self._image,
            env=self._env_vars or None,
            timeout=self._sandbox_timeout,
        )
        if self._reuse_sandbox:
            self._sandbox = sandbox
        return sandbox

    async def _stage_skill_folder(self, sandbox: Sandbox, skill_folder: Path) -> None:
        """Upload every file in the skill folder into the sandbox workdir."""
        from opensandbox.models import WriteEntry

        entries: list[WriteEntry] = []
        for path in sorted(skill_folder.rglob('*')):
            if not path.is_file():
                continue
            relative = path.relative_to(skill_folder).as_posix()
            entries.append(
                WriteEntry(
                    path=f'{self._workdir}/{relative}',
                    data=path.read_bytes(),
                    mode=0o755 if path.stat().st_mode & 0o111 else 0o644,
                )
            )

        if entries:
            await sandbox.files.write_files(entries)

    def _build_command(self, script_path: Path, skill_folder: Path, args: dict[str, Any] | None) -> str:
        """Build the shell command line executed inside the sandbox."""
        relative = script_path.relative_to(skill_folder).as_posix()
        remote_path = f'{self._workdir}/{relative}'

        interpreter = _SANDBOX_INTERPRETERS.get(script_path.suffix.lower())
        cmd = [*interpreter, remote_path] if interpreter else [remote_path]

        if args:
            # Reuse the built-in bool/list/None marshalling rules.
            self._formatter._build_args(cmd, args)

        return shlex.join(cmd)

    async def run(
        self,
        script: SkillScript,
        args: dict[str, Any] | None = None,
        ctx: Any | None = None,
    ) -> Any:
        """Run a skill script inside an OpenSandbox container.

        Args:
            script: The script to run; ``script.uri`` must point at a local file.
            args: Named arguments, marshalled with the same rules as
                [`LocalSkillScriptExecutor`][pydantic_ai_skills.LocalSkillScriptExecutor].
            ctx: Unused; accepted for protocol compatibility.

        Returns:
            Combined stdout and stderr, formatted like local execution.

        Raises:
            ValueError: If the script has no URI configured.
        """
        if script.uri is None:
            raise ValueError(f"Script '{script.name}' has no URI for sandbox execution")

        script_path = Path(script.uri)
        skill_folder = script_path.parent
        command = self._build_command(script_path, skill_folder, args)

        # _get_sandbox raises the ImportError naming the extra, so import the SDK
        # models only once a sandbox exists.
        sandbox = await self._get_sandbox()
        from opensandbox.models.execd import RunCommandOpts

        try:
            await self._stage_skill_folder(sandbox, skill_folder)
            execution = await sandbox.commands.run(
                command,
                opts=RunCommandOpts(
                    working_directory=self._workdir,
                    timeout=timedelta(seconds=self.timeout),
                    envs=self._env_vars or None,
                ),
            )
        finally:
            if not self._reuse_sandbox:
                await sandbox.kill()

        stdout = ''.join(message.text for message in execution.logs.stdout)
        stderr = ''.join(message.text for message in execution.logs.stderr)
        return self._formatter._format_output([stdout.encode()], [stderr.encode()], execution.exit_code or 0)

    async def aclose(self) -> None:
        """Kill the reused sandbox, if one is alive."""
        if self._sandbox is not None:
            await self._sandbox.kill()
            self._sandbox = None

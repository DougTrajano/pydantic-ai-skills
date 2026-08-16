"""Script executor interface.

This module provides:
- SkillScriptExecutor: Structural protocol implemented by every script executor

Implementations shipped with this package:
- [`LocalSkillScriptExecutor`][pydantic_ai_skills.LocalSkillScriptExecutor]: Execute scripts using local subprocesses
- [`CallableSkillScriptExecutor`][pydantic_ai_skills.CallableSkillScriptExecutor]: Wrap a callable in the executor interface

The protocol is intentionally structural: any object exposing a matching
``run`` coroutine satisfies it, so custom executors do not need to subclass
anything.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    # Runtime import would be circular: types.py references this protocol.
    from .types import SkillScript

__all__ = ['SkillScriptExecutor']


@runtime_checkable
class SkillScriptExecutor(Protocol):
    """Protocol for objects that execute file-based skill scripts.

    Implement this to run skill scripts somewhere other than a local
    subprocess — a container sandbox, a remote worker, or an in-process
    debugger. Pass the instance as ``script_executor`` to ``SkillsDirectory``
    or ``discover_skills``.

    Example:
        ```python
        from typing import Any

        from pydantic_ai_skills import SkillScript, SkillsDirectory


        class EchoExecutor:
            async def run(
                self,
                script: SkillScript,
                args: dict[str, Any] | None = None,
                ctx: Any | None = None,
            ) -> Any:
                return f'Would run {script.uri} with {args}'


        directory = SkillsDirectory(path='./skills', script_executor=EchoExecutor())
        ```
    """

    async def run(
        self,
        script: SkillScript,
        args: dict[str, Any] | None = None,
        ctx: Any | None = None,
    ) -> Any:
        """Run a skill script.

        Args:
            script: The script to run. For file-based scripts, ``script.uri``
                holds the path to the script file.
            args: Named arguments for the script, or None.
            ctx: Optional run context, forwarded from the agent run.

        Returns:
            The script output. Executors used with ``run_skill_script``
            should return a string.
        """
        ...

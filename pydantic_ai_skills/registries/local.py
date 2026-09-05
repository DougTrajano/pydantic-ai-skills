"""Local directory registry.

Provides :class:`LocalSkillsRegistry`, which presents a directory already on disk as a
registry so it can take part in composition.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic_ai_skills.registries._base import SkillRegistry

__all__ = ['LocalSkillsRegistry']


@dataclass
class LocalSkillsRegistry(SkillRegistry):
    """A registry backed by a skill library already present on the filesystem.

    Passing a local directory straight to `SkillsCapability(directories=...)` is simpler
    and does the same thing. Use this when a local library needs to be *composed* — merged
    with a remote one, prefixed, or filtered — since composition operates on registries.

    Attributes:
        path: The skill-library directory. Its immediate children are skill packages.

    Example:
        ```python
        from pydantic_ai_skills import GitSkillsRegistry
        from pydantic_ai_skills.registries import LocalSkillsRegistry

        # Local skills take precedence over the ones published upstream.
        combined = LocalSkillsRegistry('./skills') | GitSkillsRegistry(
            'https://github.com/anthropics/skills', path='skills'
        )
        ```
    """

    path: str | Path

    def sync(self) -> Path:
        """Return the library directory, checking that it exists.

        Raises:
            ValueError: When the path does not exist or is not a directory.
        """
        library = Path(self.path).expanduser()
        if not library.exists():
            raise ValueError(f'Skill library directory does not exist: {library}')
        if not library.is_dir():
            raise ValueError(f'Skill library path is not a directory: {library}')
        return library

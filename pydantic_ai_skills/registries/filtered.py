"""Filtered registry composition.

Provides :class:`FilteredRegistry`, a wrapper that restricts which skills a registry
exposes. Follows the same pattern as Pydantic AI's ``FilteredToolset``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pydantic_ai_skills._parsing import SkillInfo, read_skill_info
from pydantic_ai_skills.registries._staging import copy_skill_directory, staging_directory
from pydantic_ai_skills.registries.wrapper import WrapperRegistry

__all__ = ['FilteredRegistry']


@dataclass
class FilteredRegistry(WrapperRegistry):
    """A registry that exposes only the skills matching a predicate.

    Syncs the wrapped registry, then stages a library containing just the packages for
    which ``predicate(info)`` is ``True``. The wrapped registry's own copy is never
    modified.

    Example:
        ```python
        pdf_only = registry.filtered(lambda info: 'pdf' in info.name)
        ```
    """

    predicate: Callable[[SkillInfo], bool]

    def sync(self) -> Path:
        """Stage a library holding only the skills that pass the predicate."""
        source = self.wrapped.sync()
        staged = staging_directory(self.target_dir)

        for child in sorted(source.iterdir()):
            if not child.is_dir():
                continue
            info = read_skill_info(child)
            if info is None or not self.predicate(info):
                continue
            copy_skill_directory(child, staged, info.name)

        return staged

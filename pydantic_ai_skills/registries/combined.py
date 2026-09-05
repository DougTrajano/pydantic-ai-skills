"""Combined registry composition.

Provides :class:`CombinedRegistry`, an aggregate that presents several registries as a
single library. Follows the same pattern as Pydantic AI's ``CombinedToolset``.
"""

from __future__ import annotations

import warnings
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from pydantic_ai_skills._parsing import read_skill_info
from pydantic_ai_skills.registries._base import SkillRegistry
from pydantic_ai_skills.registries._staging import copy_skill_directory, staging_directory

__all__ = ['CombinedRegistry']


@dataclass
class CombinedRegistry(SkillRegistry):
    """A registry that merges several registries into one library.

    Every child is synced and its packages staged into a single directory. Earlier
    registries win on a duplicate skill name, and the shadowed one is reported with a
    `UserWarning` — merging silently would hand harness a library whose contents depend on
    directory iteration order.

    Passing the merged library to `SkillsCapability` is equivalent to passing each child's
    own library, except that this resolves the collisions itself rather than letting
    harness reject the duplicate.

    Attributes:
        registries: The registries to merge, in precedence order.
        target_dir: Where to stage the merged library. When None, a process-lifetime
            temporary directory is used.

    Example:
        ```python
        from pydantic_ai_skills.registries import CombinedRegistry

        combined = CombinedRegistry(registries=[internal_registry, public_registry])
        ```
    """

    registries: Sequence[SkillRegistry]
    target_dir: str | Path | None = field(default=None, kw_only=True)

    def sync(self) -> Path:
        """Sync every child registry and stage their skills into one library."""
        staged = staging_directory(self.target_dir)
        claimed: dict[str, SkillRegistry] = {}

        for registry in self.registries:
            source = registry.sync()
            for child in sorted(source.iterdir()):
                if not child.is_dir():
                    continue
                info = read_skill_info(child)
                if info is None:
                    continue
                if owner := claimed.get(info.name):
                    warnings.warn(
                        f"Skill '{info.name}' is provided by more than one registry; keeping the one from "
                        f'{owner!r} and skipping {registry!r}. Use `.prefixed()` or `.renamed()` to expose both.',
                        UserWarning,
                        stacklevel=2,
                    )
                    continue
                claimed[info.name] = registry
                copy_skill_directory(child, staged, info.name)

        return staged

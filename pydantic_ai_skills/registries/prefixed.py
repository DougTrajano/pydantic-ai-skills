"""Prefixed registry composition.

Provides :class:`PrefixedRegistry`, a wrapper that prepends a prefix to every skill name
so libraries from different sources can coexist without colliding.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic_ai_skills._parsing import read_skill_info, rewrite_skill_name, validate_skill_name
from pydantic_ai_skills.registries._staging import copy_skill_directory, staging_directory
from pydantic_ai_skills.registries.wrapper import WrapperRegistry

__all__ = ['PrefixedRegistry']


@dataclass
class PrefixedRegistry(WrapperRegistry):
    """A registry that prepends a prefix to every skill name.

    Because harness derives a skill's name from its directory — and rejects a `SKILL.md`
    whose frontmatter `name` disagrees with it — renaming means staging the package under
    the new directory name *and* rewriting that key. Both happen here.

    Example:
        ```python
        anthropic = registry.prefixed('anthropic-')
        # the "pdf" skill is exposed to the model as "anthropic-pdf"
        ```
    """

    prefix: str

    def sync(self) -> Path:
        """Stage a library whose skills are all renamed with the prefix.

        Raises:
            ValueError: When the prefix yields a name harness would reject.
        """
        source = self.wrapped.sync()
        staged = staging_directory(self.target_dir)

        for child in sorted(source.iterdir()):
            if not child.is_dir():
                continue
            info = read_skill_info(child)
            if info is None:
                continue

            new_name = validate_skill_name(
                f'{self.prefix}{info.name}',
                context=f'Prefixing {info.name!r} with {self.prefix!r}',
            )
            staged_skill = copy_skill_directory(child, staged, new_name)
            rewrite_skill_name(staged_skill / 'SKILL.md', new_name)

        return staged

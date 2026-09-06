"""Renamed registry composition.

Provides :class:`RenamedRegistry`, a wrapper that exposes selected skills under different
names.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pydantic_ai_skills._parsing import read_skill_info, rewrite_skill_name, validate_skill_name
from pydantic_ai_skills.registries._staging import copy_skill_directory, staging_directory
from pydantic_ai_skills.registries.wrapper import WrapperRegistry

__all__ = ['RenamedRegistry']


@dataclass
class RenamedRegistry(WrapperRegistry):
    """A registry that exposes skills under names from a mapping.

    Skills the map does not mention keep their original name. As with
    :class:`~pydantic_ai_skills.registries.prefixed.PrefixedRegistry`, renaming stages the
    package under its new directory name and rewrites the frontmatter `name` so harness
    finds the two in agreement.

    Attributes:
        name_map: Mapping of ``{new_name: original_name}``.

    Example:
        ```python
        registry.renamed({'anthropic-pdf': 'pdf'})
        ```
    """

    name_map: dict[str, str] = field(default_factory=dict)

    def sync(self) -> Path:
        """Stage a library with the mapped skills renamed.

        Raises:
            ValueError: When a new name is one harness would reject, when the map names an
                original skill this registry does not hold, or when two skills would end
                up sharing a name.
        """
        source = self.wrapped.sync()
        staged = staging_directory(self.target_dir)

        renames = {original: new for new, original in self.name_map.items()}
        available = {
            info.name: info for child in sorted(source.iterdir()) if child.is_dir() if (info := read_skill_info(child))
        }

        unknown = sorted(set(renames) - set(available))
        if unknown:
            noun = 'skill' if len(unknown) == 1 else 'skills'
            available_text = ', '.join(sorted(available)) or '(none)'
            raise ValueError(f'Unknown {noun} in name_map: {", ".join(unknown)}. Available skills: {available_text}.')

        staged_names: dict[str, str] = {}
        for original, info in available.items():
            new_name = renames.get(original, original)
            if new_name != original:
                new_name = validate_skill_name(new_name, context=f'Renaming {original!r}')
            if previous := staged_names.get(new_name):
                raise ValueError(f'Renaming would give {previous!r} and {original!r} the same name {new_name!r}.')
            staged_names[new_name] = original

            staged_skill = copy_skill_directory(info.directory, staged, new_name)
            if new_name != original:
                rewrite_skill_name(staged_skill / 'SKILL.md', new_name)

        return staged

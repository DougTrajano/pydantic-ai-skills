"""Skill registries for discovering and installing skills from remote sources.

Available registries:
- :class:`~pydantic_ai_skills.registries.git.GitSkillsRegistry`: Clone a Git repository
  and expose its skills.

Composition wrappers:
- :class:`~pydantic_ai_skills.registries.wrapper.WrapperRegistry`: Base delegation wrapper.
- :class:`~pydantic_ai_skills.registries.filtered.FilteredRegistry`: Filter by predicate.
- :class:`~pydantic_ai_skills.registries.prefixed.PrefixedRegistry`: Prefix skill names.
- :class:`~pydantic_ai_skills.registries.renamed.RenamedRegistry`: Rename skills via map.
- :class:`~pydantic_ai_skills.registries.combined.CombinedRegistry`: Aggregate registries.

Abstract base:
- :class:`~pydantic_ai_skills.registries._base.SkillRegistry`: ABC all registries implement.
"""

from pydantic_ai_skills.registries._base import SkillRegistry
from pydantic_ai_skills.registries.combined import CombinedRegistry
from pydantic_ai_skills.registries.filtered import FilteredRegistry
from pydantic_ai_skills.registries.git import GitCloneOptions, GitSkillsRegistry
from pydantic_ai_skills.registries.prefixed import PrefixedRegistry
from pydantic_ai_skills.registries.renamed import RenamedRegistry
from pydantic_ai_skills.registries.wrapper import WrapperRegistry

__all__ = [
    'SkillRegistry',
    'WrapperRegistry',
    'FilteredRegistry',
    'PrefixedRegistry',
    'RenamedRegistry',
    'CombinedRegistry',
    'GitSkillsRegistry',
    'GitCloneOptions',
]

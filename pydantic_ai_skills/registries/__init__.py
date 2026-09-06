"""Skill registries: sources that materialize skill libraries on the local filesystem.

A registry fetches Agent Skill packages from wherever they live and lays them out as a
directory :class:`~pydantic_ai_skills.SkillsCapability` can hand to
`pydantic-ai-harness`'s `Skills`. Parsing, validating and rendering the packages inside
that directory is harness's job, not a registry's.

Available registries:
- :class:`~pydantic_ai_skills.registries.git.GitSkillsRegistry`: Clone a Git repository
  and expose its skills.
- :class:`~pydantic_ai_skills.registries.s3.S3SkillsRegistry`: Download skills from an S3
  bucket (or S3-compatible store such as MinIO).
- :class:`~pydantic_ai_skills.registries.local.LocalSkillsRegistry`: Present a directory
  already on disk, so it can take part in composition.

Composition wrappers, which stage a new library rather than mutating the one they wrap:
- :class:`~pydantic_ai_skills.registries.wrapper.WrapperRegistry`: Base delegation wrapper.
- :class:`~pydantic_ai_skills.registries.filtered.FilteredRegistry`: Filter by predicate.
- :class:`~pydantic_ai_skills.registries.prefixed.PrefixedRegistry`: Prefix skill names.
- :class:`~pydantic_ai_skills.registries.renamed.RenamedRegistry`: Rename skills via map.
- :class:`~pydantic_ai_skills.registries.combined.CombinedRegistry`: Merge registries.

Abstract base:
- :class:`~pydantic_ai_skills.registries._base.SkillRegistry`: ABC all registries implement.
"""

from pydantic_ai_skills.registries._base import SkillRegistry
from pydantic_ai_skills.registries.combined import CombinedRegistry
from pydantic_ai_skills.registries.filtered import FilteredRegistry
from pydantic_ai_skills.registries.git import GitCloneOptions, GitSkillsRegistry
from pydantic_ai_skills.registries.local import LocalSkillsRegistry
from pydantic_ai_skills.registries.prefixed import PrefixedRegistry
from pydantic_ai_skills.registries.renamed import RenamedRegistry
from pydantic_ai_skills.registries.s3 import S3SkillsRegistry
from pydantic_ai_skills.registries.wrapper import WrapperRegistry

__all__ = [
    'CombinedRegistry',
    'FilteredRegistry',
    'GitCloneOptions',
    'GitSkillsRegistry',
    'LocalSkillsRegistry',
    'PrefixedRegistry',
    'RenamedRegistry',
    'S3SkillsRegistry',
    'SkillRegistry',
    'WrapperRegistry',
]

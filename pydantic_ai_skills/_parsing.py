"""Minimal `SKILL.md` reading, for the two jobs harness's loader cannot do for us.

`pydantic-ai-harness` is the authority on parsing and validating `SKILL.md`: it decides
what a skill is called, whether its frontmatter is well-formed, and what reaches the
model. This module exists only for the work that happens *before* harness sees a library:

- Reading a package's `name` and `description` so a
  [`FilteredRegistry`][pydantic_ai_skills.registries.FilteredRegistry] predicate has
  something to filter on.
- Rewriting the `name` key when
  [`PrefixedRegistry`][pydantic_ai_skills.registries.PrefixedRegistry] or
  [`RenamedRegistry`][pydantic_ai_skills.registries.RenamedRegistry] stages a package
  under a different directory name, since harness requires the two to agree.

[`validate_skill_name`][pydantic_ai_skills._parsing.validate_skill_name] mirrors harness's
own naming rule so a bad prefix fails where the caller can see it, rather than deep inside
`Skills(...)`.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

__all__ = [
    'SkillInfo',
    'parse_skill_md',
    'read_skill_info',
    'rewrite_skill_name',
    'validate_skill_name',
]

#: Longest skill name harness accepts.
MAX_SKILL_NAME_LENGTH = 64


def parse_skill_md(content: str) -> tuple[dict[str, Any], str]:
    """Parse a SKILL.md file into frontmatter and instructions.

    Lenient by design: a file with no frontmatter, or with an unclosed block, yields an
    empty mapping rather than raising, because harness reports those cases with a better
    message when it reads the same file.

    Args:
        content: Full content of the SKILL.md file.

    Returns:
        Tuple of (frontmatter_dict, instructions_markdown).

    Raises:
        ValueError: If YAML parsing fails or frontmatter is not a mapping.
    """
    lines = content.split('\n')

    # Frontmatter must open at line 0
    if not lines or lines[0].rstrip() != '---':
        return {}, content.strip()

    # Linear scan for the closing --- (no backtracking risk)
    closing_idx: int | None = None
    for i in range(1, len(lines)):
        if lines[i].rstrip() == '---':
            closing_idx = i
            break

    if closing_idx is None:
        return {}, content.strip()

    frontmatter_yaml = '\n'.join(lines[1:closing_idx]).strip()
    instructions = '\n'.join(lines[closing_idx + 1 :]).strip()

    if not frontmatter_yaml:
        return {}, instructions

    try:
        frontmatter = yaml.safe_load(frontmatter_yaml)
    except yaml.YAMLError as e:
        raise ValueError(f'Failed to parse YAML frontmatter: {e}') from e

    if not isinstance(frontmatter, dict):
        raise ValueError(f'YAML frontmatter must be a mapping, got {type(frontmatter).__name__}')
    return frontmatter, instructions


@dataclass(frozen=True)
class SkillInfo:
    """The catalog fields of one skill package, as seen before harness validates it.

    This is what a [`FilteredRegistry`][pydantic_ai_skills.registries.FilteredRegistry]
    predicate receives. It is deliberately shallow — no bundled files, no instructions
    body — because filtering happens while staging directories, well before any skill is
    handed to an agent.

    Attributes:
        name: The package's directory name, NFKC-normalized. This, not the frontmatter
            `name`, is what harness will call the skill.
        description: The frontmatter `description`, or an empty string when the file has
            none. harness rejects a missing description later; filtering does not.
        directory: The package directory.
    """

    name: str
    description: str
    directory: Path


def read_skill_info(skill_dir: Path) -> SkillInfo | None:
    """Read the catalog fields of the skill package at `skill_dir`.

    Args:
        skill_dir: A skill package directory (the one holding `SKILL.md`).

    Returns:
        The package's [`SkillInfo`][pydantic_ai_skills._parsing.SkillInfo], or None when
        there is no readable `SKILL.md`. Malformed frontmatter yields an info with an
        empty description rather than raising: harness reports it properly at the point
        the library is loaded, and failing here would break filtering on the *other*
        skills in the same registry.
    """
    skill_file = skill_dir / 'SKILL.md'
    if not skill_file.is_file():
        return None

    try:
        frontmatter, _ = parse_skill_md(skill_file.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        frontmatter = {}

    return SkillInfo(
        name=unicodedata.normalize('NFKC', skill_dir.name),
        description=str(frontmatter.get('description') or ''),
        directory=skill_dir,
    )


def validate_skill_name(name: str, *, context: str) -> str:
    """Validate and normalize a skill name against harness's rule.

    Mirrors `pydantic_ai_harness.skills`'s naming rule so a name this package *generates*
    — by prefixing or renaming — fails with a message naming the operation that produced
    it, instead of surfacing later as an opaque error from `Skills(...)`.

    Args:
        name: The candidate name.
        context: What produced the name, used in the error message.

    Returns:
        The NFKC-normalized name.

    Raises:
        ValueError: When the name is not one harness would accept.
    """
    normalized = unicodedata.normalize('NFKC', name)
    if (
        not normalized
        or len(normalized) > MAX_SKILL_NAME_LENGTH
        or normalized != normalized.lower()
        or normalized.startswith('-')
        or normalized.endswith('-')
        or '--' in normalized
        or not all(character.isalnum() or character == '-' for character in normalized)
    ):
        raise ValueError(
            f'{context} produced the invalid skill name {name!r}; expected at most '
            f'{MAX_SKILL_NAME_LENGTH} lowercase letters or numbers and single hyphens, '
            'without a leading or trailing hyphen.'
        )
    return normalized


def rewrite_skill_name(skill_file: Path, name: str) -> None:
    """Rewrite the frontmatter `name` of `skill_file` in place.

    harness requires a `SKILL.md`'s `name` to match its parent directory, so staging a
    package under a new directory name means updating the frontmatter to agree. A file
    whose frontmatter carries no `name` is left alone — harness derives the name from the
    directory in that case, which is already correct.

    Args:
        skill_file: Path to the `SKILL.md` to rewrite.
        name: The new skill name, which must equal the parent directory's name.
    """
    content = skill_file.read_text(encoding='utf-8')
    lines = content.split('\n')
    if not lines or lines[0].rstrip() != '---':
        return

    for index in range(1, len(lines)):
        stripped = lines[index].rstrip()
        if stripped == '---':
            return  # End of frontmatter with no `name` key: nothing to rewrite.
        if stripped.startswith('name:'):
            lines[index] = f'name: {name}'
            with skill_file.open('w', encoding='utf-8') as handle:
                handle.write('\n'.join(lines))
            return

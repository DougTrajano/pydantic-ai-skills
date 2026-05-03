"""Pure parsing and validation helpers for SKILL.md files.

These functions have no dependency on types.py or local.py, making them safe
to import from types.py without creating circular imports.
"""

from __future__ import annotations

import re
import warnings
from typing import Any

import yaml

from .exceptions import SkillValidationError

# agentskills.io naming convention: lowercase letters, numbers, and hyphens only (no consecutive hyphens)
SKILL_NAME_PATTERN = re.compile(r'^[a-z0-9]+(-[a-z0-9]+)*$')
RESERVED_WORDS = {'anthropic', 'claude'}


def parse_skill_md(content: str) -> tuple[dict[str, Any], str]:
    """Parse a SKILL.md file into frontmatter and instructions.

    Args:
        content: Full content of the SKILL.md file.

    Returns:
        Tuple of (frontmatter_dict, instructions_markdown).

    Raises:
        SkillValidationError: If YAML parsing fails.
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
        return frontmatter, instructions
    except yaml.YAMLError as e:
        raise SkillValidationError(f'Failed to parse YAML frontmatter: {e}') from e


def validate_skill_metadata(
    frontmatter: dict[str, Any],
    instructions: str,
    uri: str | None = None,
) -> bool:
    """Validate skill metadata against Anthropic's requirements.

    Emits warnings for any validation issues found.

    Args:
        frontmatter: Parsed YAML frontmatter.
        instructions: The skill instructions content.
        uri: Optional URI or path identifying the skill source for diagnostics.

    Returns:
        True if validation passed with no issues, False if warnings were emitted.
    """
    is_valid = True
    name = frontmatter.get('name', '')
    description = frontmatter.get('description', '')
    location = f' ({uri})' if uri else ''

    # Validate name format
    if name:
        if len(name) > 64:
            warnings.warn(
                f"Skill name '{name}'{location} exceeds 64 characters ({len(name)} chars) recommendation."
                f' Consider shortening it.',
                UserWarning,
                stacklevel=2,
            )
            is_valid = False
        elif not SKILL_NAME_PATTERN.match(name):
            warnings.warn(
                f"Skill name '{name}'{location} should contain only lowercase letters, numbers, and hyphens",
                UserWarning,
                stacklevel=2,
            )
            is_valid = False
        # Check for reserved words
        for reserved in RESERVED_WORDS:
            if reserved in name:
                warnings.warn(
                    f"Skill name '{name}'{location} contains reserved word '{reserved}'",
                    UserWarning,
                    stacklevel=2,
                )
                is_valid = False

    # Validate description
    if description and len(description) > 1024:
        warnings.warn(
            f"Skill '{name}'{location}: description exceeds 1024 characters ({len(description)} chars)",
            UserWarning,
            stacklevel=2,
        )
        is_valid = False

    # Validate compatibility (if provided)
    compatibility = frontmatter.get('compatibility', '')
    if compatibility and len(compatibility) > 500:
        warnings.warn(
            f"Skill '{name}'{location}: compatibility exceeds 500 characters ({len(compatibility)} chars)",
            UserWarning,
            stacklevel=2,
        )
        is_valid = False

    # Validate instructions length (Anthropic recommends under 500 lines)
    lines = instructions.split('\n')
    if len(lines) > 500:
        warnings.warn(
            f"Skill '{name}'{location}: SKILL.md body exceeds recommended 500 lines ({len(lines)} lines). "
            f'Consider splitting into separate resource files.',
            UserWarning,
            stacklevel=2,
        )
        is_valid = False

    return is_valid

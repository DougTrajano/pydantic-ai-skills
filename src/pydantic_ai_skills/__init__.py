"""Anthropic Agent Skills for pydantic-ai.

This package provides reusable skills for Anthropic agents using pydantic-ai.
"""

from pydantic_ai_skills.skills import (
    Skill,
    TextProcessingSkill,
    DataExtractionSkill,
    SkillRegistry,
    create_default_registry,
)

__version__ = "0.1.0"

__all__ = [
    "Skill",
    "TextProcessingSkill",
    "DataExtractionSkill",
    "SkillRegistry",
    "create_default_registry",
]


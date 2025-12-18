"""Anthropic Agent Skills for pydantic-ai."""

from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field


class Skill(BaseModel):
    """Base class for Anthropic Agent Skills."""

    name: str = Field(..., description="The name of the skill")
    description: str = Field(..., description="A description of what the skill does")
    parameters: Dict[str, Any] = Field(
        default_factory=dict, description="Parameters schema for the skill"
    )

    def execute(self, **kwargs) -> Any:
        """Execute the skill with the given parameters.
        
        Args:
            **kwargs: Parameters for skill execution
            
        Returns:
            The result of executing the skill
        """
        raise NotImplementedError("Subclasses must implement execute method")

    def to_anthropic_tool(self) -> Dict[str, Any]:
        """Convert the skill to Anthropic tool format.
        
        Returns:
            Dictionary representation suitable for Anthropic API
        """
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": self.parameters,
                "required": list(self.parameters.keys()) if self.parameters else [],
            },
        }


class TextProcessingSkill(Skill):
    """Skill for text processing operations."""

    name: str = "text_processing"
    description: str = "Process and analyze text content"
    parameters: Dict[str, Any] = Field(
        default_factory=lambda: {
            "text": {
                "type": "string",
                "description": "The text to process",
            },
            "operation": {
                "type": "string",
                "description": "The operation to perform (e.g., 'uppercase', 'lowercase', 'word_count')",
            },
        }
    )

    def execute(self, text: str, operation: str) -> Any:
        """Execute text processing operation.
        
        Args:
            text: The text to process
            operation: The operation to perform
            
        Returns:
            Processed text or analysis result
        """
        if operation == "uppercase":
            return text.upper()
        elif operation == "lowercase":
            return text.lower()
        elif operation == "word_count":
            return len(text.split())
        elif operation == "char_count":
            return len(text)
        else:
            raise ValueError(f"Unknown operation: {operation}")


class DataExtractionSkill(Skill):
    """Skill for extracting structured data from text."""

    name: str = "data_extraction"
    description: str = "Extract structured data from unstructured text"
    parameters: Dict[str, Any] = Field(
        default_factory=lambda: {
            "text": {
                "type": "string",
                "description": "The text to extract data from",
            },
            "data_type": {
                "type": "string",
                "description": "The type of data to extract (e.g., 'email', 'phone', 'date')",
            },
        }
    )

    def execute(self, text: str, data_type: str) -> List[str]:
        """Extract data from text.
        
        Args:
            text: The text to extract data from
            data_type: The type of data to extract
            
        Returns:
            List of extracted data items
        """
        import re

        if data_type == "email":
            pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
            return re.findall(pattern, text)
        elif data_type == "phone":
            pattern = r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"
            return re.findall(pattern, text)
        elif data_type == "url":
            pattern = r"https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&/=]*)"
            return re.findall(pattern, text)
        else:
            raise ValueError(f"Unknown data type: {data_type}")


class SkillRegistry:
    """Registry for managing Anthropic Agent Skills."""

    def __init__(self):
        """Initialize the skill registry."""
        self._skills: Dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        """Register a skill.
        
        Args:
            skill: The skill to register
        """
        self._skills[skill.name] = skill

    def unregister(self, skill_name: str) -> None:
        """Unregister a skill.
        
        Args:
            skill_name: The name of the skill to unregister
        """
        if skill_name in self._skills:
            del self._skills[skill_name]

    def get(self, skill_name: str) -> Optional[Skill]:
        """Get a skill by name.
        
        Args:
            skill_name: The name of the skill to retrieve
            
        Returns:
            The skill if found, None otherwise
        """
        return self._skills.get(skill_name)

    def list_skills(self) -> List[str]:
        """List all registered skill names.
        
        Returns:
            List of skill names
        """
        return list(self._skills.keys())

    def to_anthropic_tools(self) -> List[Dict[str, Any]]:
        """Convert all skills to Anthropic tool format.
        
        Returns:
            List of tool definitions for Anthropic API
        """
        return [skill.to_anthropic_tool() for skill in self._skills.values()]

    def execute_skill(self, skill_name: str, **kwargs) -> Any:
        """Execute a skill by name.
        
        Args:
            skill_name: The name of the skill to execute
            **kwargs: Parameters for skill execution
            
        Returns:
            The result of executing the skill
            
        Raises:
            ValueError: If the skill is not found
        """
        skill = self.get(skill_name)
        if skill is None:
            raise ValueError(f"Skill not found: {skill_name}")
        return skill.execute(**kwargs)


def create_default_registry() -> SkillRegistry:
    """Create a registry with default skills.
    
    Returns:
        A SkillRegistry with default skills registered
    """
    registry = SkillRegistry()
    registry.register(TextProcessingSkill())
    registry.register(DataExtractionSkill())
    return registry

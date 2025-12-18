"""Tests for pydantic-ai-skills."""

import pytest
from pydantic_ai_skills import (
    Skill,
    TextProcessingSkill,
    DataExtractionSkill,
    SkillRegistry,
    create_default_registry,
)


class TestSkill:
    """Tests for the Skill base class."""

    def test_skill_to_anthropic_tool(self):
        """Test conversion to Anthropic tool format."""
        skill = TextProcessingSkill()
        tool = skill.to_anthropic_tool()
        
        assert tool["name"] == "text_processing"
        assert tool["description"] == "Process and analyze text content"
        assert "input_schema" in tool
        assert tool["input_schema"]["type"] == "object"
        assert "properties" in tool["input_schema"]


class TestTextProcessingSkill:
    """Tests for TextProcessingSkill."""

    def test_uppercase_operation(self):
        """Test uppercase operation."""
        skill = TextProcessingSkill()
        result = skill.execute(text="hello world", operation="uppercase")
        assert result == "HELLO WORLD"

    def test_lowercase_operation(self):
        """Test lowercase operation."""
        skill = TextProcessingSkill()
        result = skill.execute(text="HELLO WORLD", operation="lowercase")
        assert result == "hello world"

    def test_word_count_operation(self):
        """Test word count operation."""
        skill = TextProcessingSkill()
        result = skill.execute(text="hello world test", operation="word_count")
        assert result == 3

    def test_char_count_operation(self):
        """Test character count operation."""
        skill = TextProcessingSkill()
        result = skill.execute(text="hello", operation="char_count")
        assert result == 5

    def test_invalid_operation(self):
        """Test invalid operation raises ValueError."""
        skill = TextProcessingSkill()
        with pytest.raises(ValueError, match="Unknown operation"):
            skill.execute(text="test", operation="invalid")


class TestDataExtractionSkill:
    """Tests for DataExtractionSkill."""

    def test_email_extraction(self):
        """Test email extraction."""
        skill = DataExtractionSkill()
        text = "Contact us at info@example.com or support@test.org"
        result = skill.execute(text=text, data_type="email")
        
        assert len(result) == 2
        assert "info@example.com" in result
        assert "support@test.org" in result

    def test_phone_extraction(self):
        """Test phone number extraction."""
        skill = DataExtractionSkill()
        text = "Call 555-123-4567 or 555.987.6543"
        result = skill.execute(text=text, data_type="phone")
        
        assert len(result) == 2
        assert "555-123-4567" in result
        assert "555.987.6543" in result

    def test_url_extraction(self):
        """Test URL extraction."""
        skill = DataExtractionSkill()
        text = "Visit https://example.com or http://test.org"
        result = skill.execute(text=text, data_type="url")
        
        assert len(result) == 2
        assert "https://example.com" in result
        assert "http://test.org" in result

    def test_invalid_data_type(self):
        """Test invalid data type raises ValueError."""
        skill = DataExtractionSkill()
        with pytest.raises(ValueError, match="Unknown data type"):
            skill.execute(text="test", data_type="invalid")


class TestSkillRegistry:
    """Tests for SkillRegistry."""

    def test_register_skill(self):
        """Test registering a skill."""
        registry = SkillRegistry()
        skill = TextProcessingSkill()
        
        registry.register(skill)
        assert "text_processing" in registry.list_skills()

    def test_unregister_skill(self):
        """Test unregistering a skill."""
        registry = SkillRegistry()
        skill = TextProcessingSkill()
        
        registry.register(skill)
        registry.unregister("text_processing")
        assert "text_processing" not in registry.list_skills()

    def test_get_skill(self):
        """Test getting a skill by name."""
        registry = SkillRegistry()
        skill = TextProcessingSkill()
        registry.register(skill)
        
        retrieved_skill = registry.get("text_processing")
        assert retrieved_skill is not None
        assert retrieved_skill.name == "text_processing"

    def test_get_nonexistent_skill(self):
        """Test getting a nonexistent skill returns None."""
        registry = SkillRegistry()
        assert registry.get("nonexistent") is None

    def test_execute_skill(self):
        """Test executing a skill through the registry."""
        registry = SkillRegistry()
        registry.register(TextProcessingSkill())
        
        result = registry.execute_skill(
            "text_processing",
            text="hello",
            operation="uppercase"
        )
        assert result == "HELLO"

    def test_execute_nonexistent_skill(self):
        """Test executing a nonexistent skill raises ValueError."""
        registry = SkillRegistry()
        with pytest.raises(ValueError, match="Skill not found"):
            registry.execute_skill("nonexistent", text="test")

    def test_to_anthropic_tools(self):
        """Test converting all skills to Anthropic tools format."""
        registry = SkillRegistry()
        registry.register(TextProcessingSkill())
        registry.register(DataExtractionSkill())
        
        tools = registry.to_anthropic_tools()
        assert len(tools) == 2
        
        tool_names = [tool["name"] for tool in tools]
        assert "text_processing" in tool_names
        assert "data_extraction" in tool_names


class TestDefaultRegistry:
    """Tests for the default registry."""

    def test_create_default_registry(self):
        """Test creating a registry with default skills."""
        registry = create_default_registry()
        
        skills = registry.list_skills()
        assert "text_processing" in skills
        assert "data_extraction" in skills

    def test_default_skills_work(self):
        """Test that default skills are functional."""
        registry = create_default_registry()
        
        # Test text processing
        result = registry.execute_skill(
            "text_processing",
            text="test",
            operation="uppercase"
        )
        assert result == "TEST"
        
        # Test data extraction
        result = registry.execute_skill(
            "data_extraction",
            text="Email: test@example.com",
            data_type="email"
        )
        assert "test@example.com" in result

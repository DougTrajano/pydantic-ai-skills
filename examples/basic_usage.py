"""Example usage of pydantic-ai-skills."""

from pydantic_ai_skills import (
    create_default_registry,
    TextProcessingSkill,
    DataExtractionSkill,
)


def main():
    """Demonstrate usage of pydantic-ai-skills."""
    # Create a registry with default skills
    registry = create_default_registry()

    print("Registered skills:", registry.list_skills())
    print()

    # Example 1: Text processing
    print("=== Text Processing Example ===")
    result = registry.execute_skill(
        "text_processing", text="Hello World", operation="uppercase"
    )
    print(f"Uppercase: {result}")

    result = registry.execute_skill(
        "text_processing", text="Hello World", operation="word_count"
    )
    print(f"Word count: {result}")
    print()

    # Example 2: Data extraction
    print("=== Data Extraction Example ===")
    sample_text = "Contact us at info@example.com or support@test.org. Call 555-123-4567."
    
    emails = registry.execute_skill(
        "data_extraction", text=sample_text, data_type="email"
    )
    print(f"Extracted emails: {emails}")

    phones = registry.execute_skill(
        "data_extraction", text=sample_text, data_type="phone"
    )
    print(f"Extracted phone numbers: {phones}")
    print()

    # Example 3: Convert to Anthropic tools format
    print("=== Anthropic Tools Format ===")
    tools = registry.to_anthropic_tools()
    for tool in tools:
        print(f"Tool: {tool['name']}")
        print(f"  Description: {tool['description']}")
        print(f"  Parameters: {list(tool['input_schema']['properties'].keys())}")
        print()


if __name__ == "__main__":
    main()

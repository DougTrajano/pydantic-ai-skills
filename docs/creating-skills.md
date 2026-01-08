# Creating Skills

This guide covers everything you need to know to create effective skills for your Pydantic AI agents.

## Basic Skill Structure

Every skill must have at minimum:

```markdown
my-skill/
└── SKILL.md
```

The `SKILL.md` file contains:

1. **YAML frontmatter** with metadata
2. **Markdown content** with instructions

## Writing SKILL.md

### Minimal Example

```markdown
---
name: my-skill
description: A brief description of what this skill does
---

# My Skill

Instructions for the agent on how to use this skill...
```

### Required Fields

- `name`: Unique identifier (lowercase, hyphens for spaces)
- `description`: Brief summary (appears in skill listings)

### Naming Conventions

Following Anthropic's skill naming conventions (logged as warnings if violated):

**Name Requirements:**

- Use only lowercase letters, numbers, and hyphens
- Maximum 64 characters
- Avoid reserved words like "anthropic" or "claude"

**Description Requirements:**

- Maximum 1024 characters
- Clear and concise summary of functionality

**Example Good Names:**

- `arxiv-search` ✅
- `web-research` ✅
- `data-analyzer` ✅

**Example Bad Names:**

- `ArxivSearch` ❌ (uppercase)
- `arxiv_search` ❌ (underscores)
- `my-super-amazing-incredible-skill-that-does-everything` ❌ (too long)

**Validation:**
The toolset validates skills on load and logs warnings for violations. Skills with warnings will still load, but you should fix the issues for better compatibility.

**Instruction Length:**
Skills with instructions exceeding 500 lines will trigger a warning suggesting you split content into separate resource files. This follows Anthropic's recommendations for keeping skills focused and manageable.

### Best Practices for Instructions

**✅ Do:**

- Use clear, action-oriented language
- Provide specific examples
- Break down complex workflows into steps
- Specify when to use the skill
- Include example inputs/outputs

**❌ Don't:**

- Write vague or ambiguous instructions
- Assume the agent knows implicit context
- Create circular dependencies between skills
- Include sensitive information (API keys, passwords)

### Example: Well-Written Instructions

```markdown
---
name: arxiv-search
description: Search arXiv for research papers
---

# arXiv Search Skill

## When to Use

Use this skill when you need to:

- Find recent preprints in physics, math, or computer science
- Search for papers not yet published in journals
- Access cutting-edge research

## Instructions

To search arXiv, use the `run_skill_script` tool with:

1. **skill_name**: "arxiv-search"
2. **script_name**: "arxiv_search"
3. **args**:
   - First argument: Your search query (e.g., "neural networks")
   - `--max-papers`: Optional, defaults to 10

## Examples

Search for 5 papers on machine learning:

```python
run_skill_script(
    skill_name="arxiv-search",
    script_name="arxiv_search",
    args=["machine learning", "--max-papers", "5"]
)
```

## Output Format

The script returns a formatted list with:

- Paper title
- Authors
- arXiv ID
- Abstract

## Adding Scripts

Scripts enable skills to perform custom operations that aren't available as standard agent tools.

### Script Location

Place scripts in either:

- `scripts/` subdirectory (recommended)
- Directly in the skill folder

```markdown
my-skill/
├── SKILL.md
└── scripts/
├── process_data.py
└── fetch_info.py
```

### Writing Scripts

Scripts should:

- Accept command-line arguments via `sys.argv`
- Print output to stdout
- Exit with code 0 on success, non-zero on error
- Handle errors gracefully

#### Example Script

```python
#!/usr/bin/env python3
"""Example skill script."""

import sys
import json

def main():
    if len(sys.argv) < 2:
        print("Usage: process_data.py <input>")
        sys.exit(1)

    input_data = sys.argv[1]

    try:
        # Process the input
        result = process(input_data)

        # Output results
        print(json.dumps(result, indent=2))

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

def process(data):
    # Your processing logic here
    return {"processed": data.upper()}

if __name__ == "__main__":
    main()
```

### Script Best Practices

**✅ Do:**

- Provide clear usage messages
- Validate input arguments
- Use JSON for structured output
- Handle errors gracefully
- Keep scripts focused on one task
- Document expected inputs/outputs in SKILL.md

**❌ Don't:**

- Make network calls without timeouts
- Write to files outside the skill directory
- Require interactive input
- Use environment-specific paths
- Leave debugging print statements

## Adding Resources

Resources are additional files that provide supplementary information.

### Resource Location

```markdown
my-skill/
├── SKILL.md
├── REFERENCE.md          # Additional .md files
└── resources/            # Resources subdirectory
    ├── examples.json
    ├── templates.txt
    └── data.csv
```

### When to Use Resources

Use resources for:

- **Large reference documents**: API schemas, data dictionaries
- **Templates**: Form templates, code snippets
- **Example data**: Sample inputs/outputs
- **Supplementary docs**: Detailed guides too long for SKILL.md

### Referencing Resources in SKILL.md

```markdown
---
name: api-client
description: Work with the XYZ API
---

# API Client Skill

For detailed API reference, use:

```python
read_skill_resource(
    skill_name="api-client",
    resource_name="API_REFERENCE.md"
)
```

For request templates:

```python
read_skill_resource(
    skill_name="api-client",
    resource_name="resources/templates.json"
)
```

## Organizing Multiple Skills

### Flat Structure

Good for small projects:

```markdown
skills/
├── skill-one/
│ └── SKILL.md
├── skill-two/
│ └── SKILL.md
└── skill-three/
└── SKILL.md
```

### Categorized Structure

Good for large projects:

```markdown
skills/
├── research/
│ ├── arxiv-search/
│ │ └── SKILL.md
│ └── pubmed-search/
│ └── SKILL.md
├── data-processing/
│ ├── csv-analyzer/
│ │ └── SKILL.md
│ └── json-validator/
│ └── SKILL.md
└── communication/
└── email-sender/
└── SKILL.md
```

Use both directories in your toolset:

```python
toolset = SkillsToolset(directories=[
    "./skills/research",
    "./skills/data-processing",
    "./skills/communication"
])
```

## Skill Metadata

Add useful metadata to help organize and discover skills:

```yaml
---
name: my-skill
description: Brief description
version: 1.0.0
author: Your Name
category: data-processing
tags: [csv, data, analysis]
license: MIT
created: 2025-01-15
updated: 2025-01-20
---
```

Access metadata programmatically:

```python
skill = toolset.get_skill("my-skill")
print(skill.metadata.extra["version"])  # "1.0.0"
print(skill.metadata.extra["category"])  # "data-processing"
```

## Testing Skills

### Manual Testing

```python
from pydantic_ai_skills import SkillsToolset

# Load skills
toolset = SkillsToolset(directories=["./skills"])

# Check discovery
print(f"Found {len(toolset.skills)} skills")

# Get specific skill
skill = toolset.get_skill("my-skill")
print(f"Name: {skill.name}")
print(f"Path: {skill.path}")
print(f"Scripts: {[s.name for s in skill.scripts]}")
print(f"Resources: {[r.name for r in skill.resources]}")

# Test script execution
import subprocess
import sys

result = subprocess.run(
    [sys.executable, str(skill.scripts[0].path), "test-arg"],
    capture_output=True,
    text=True
)
print(f"Output: {result.stdout}")
```

### Integration Testing

Test with a real agent:

```python
import asyncio
from pydantic_ai import Agent, RunContext
from pydantic_ai_skills import SkillsToolset

async def test_skill():
    toolset = SkillsToolset(directories=["./skills"])

    agent = Agent(
        model='openai:gpt-5.2',
        instructions="You are a test assistant.",
        toolsets=[toolset]
    )

    @agent.instructions
    async def add_skills(ctx: RunContext) -> str | None:
        """Add skills instructions to the agent's context."""
        return await toolset.get_instructions(ctx)

    result = await agent.run("Test my-skill with input: test data")
    print(result.output)

if __name__ == "__main__":
    asyncio.run(test_skill())
```

## Common Patterns

### Pattern 1: Instruction-Only Skills

**Use when**: The skill provides methodology or best practices without executable code.

**Structure**:

```markdown
web-research/
└── SKILL.md
```

**Example**:

```markdown
---
name: web-research
description: Structured approach to conducting comprehensive web research
---

# Web Research Skill

## Process

### Step 1: Create Research Plan

Before conducting research:

1. Analyze the research question
2. Break it into 2-5 distinct subtopics
3. Determine expected information from each

### Step 2: Gather Information

For each subtopic:

1. Use web search tools with clear queries
2. Target 3-5 searches per subtopic
3. Organize findings as you gather them

### Step 3: Synthesize Results

Combine findings:

1. Summarize key information per subtopic
2. Identify connections between subtopics
3. Present cohesive narrative with citations
```

**When to use**:

- Process guidelines
- Best practices
- Methodology instructions
- Workflow templates

### Pattern 2: Script-Based Skills

**Use when**: The skill needs to execute custom code or interact with external services.

**Structure**:

```markdown
arxiv-search/
├── SKILL.md
└── scripts/
    └── arxiv_search.py
```

**Example SKILL.md**:

```markdown
---
name: arxiv-search
description: Search arXiv for research papers
---

# arXiv Search Skill

## Usage

Use the `run_skill_script` tool to search arXiv:

```python
run_skill_script(
    skill_name="arxiv-search",
    script_name="arxiv_search",
    args=["machine learning", "--max-papers", "10"]
)
```

## Arguments

- **query** (required): Search query string
- `--max-papers`: Maximum results (default: 10)

**Example Script**:

```python
#!/usr/bin/env python3
import sys
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('query', help='Search query')
    parser.add_argument('--max-papers', type=int, default=10)

    args = parser.parse_args()

    # Perform search
    results = search_arxiv(args.query, args.max_papers)

    # Output results
    for paper in results:
        print(f"Title: {paper['title']}")
        print(f"Authors: {paper['authors']}")
        print(f"URL: {paper['url']}")
        print()

if __name__ == "__main__":
    main()
```

**When to use**:

- API integrations
- Data processing
- File operations
- External tool execution

### Pattern 3: Documentation Reference Skills

**Use when**: The skill provides access to external documentation.

**Structure**:

```markdown
pydanticai-docs/
└── SKILL.md
```

**Example**:

```markdown
---
name: pydanticai-docs
description: Access Pydantic AI framework documentation
---

# Pydantic AI Documentation Skill

## When to Use

Use this skill for questions about:

- Creating agents
- Defining tools
- Working with models
- Structured outputs

## Instructions

### For General Documentation

The complete Pydantic AI documentation is available at:
https://ai.pydantic.dev/

Fetch it using your web search or URL fetching tools.

### For Quick Reference

Key concepts:

- **Agents**: Create with `Agent(model, instructions, tools)`
- **Tools**: Decorate with `@agent.tool` or `@agent.tool_plain`
- **Models**: Format as `provider:model-name`
- **Output**: Use `result_type` parameter for structured output
```

**When to use**:

- Documentation shortcuts
- Quick reference guides
- Link aggregation
- Knowledge base access

### Pattern 4: Multi-Resource Skills

**Use when**: The skill needs extensive documentation broken into logical sections.

**Structure**:

```markdown
api-integration/
├── SKILL.md
├── API_REFERENCE.md
└── resources/
    ├── examples.json
    └── schemas/
        ├── request.json
        └── response.json
```

**Example SKILL.md**:

```markdown
---
name: api-integration
description: Integrate with XYZ API
---

# API Integration Skill

## Quick Start

For detailed API reference:

```python
read_skill_resource(
    skill_name="api-integration",
    resource_name="API_REFERENCE.md"
)
```

For request examples:

```python
read_skill_resource(
    skill_name="api-integration",
    resource_name="resources/examples.json"
)
```

## Basic Usage

1. Load the API reference
2. Review examples
3. Use the appropriate schema

**When to use**:

- Complex APIs
- Multiple related documents
- Template collections
- Reference data

### Pattern 5: Hybrid Skills

**Use when**: Combining instructions with scripts and resources.

**Structure**:

```markdown
data-analyzer/
├── SKILL.md
├── REFERENCE.md
├── scripts/
│ ├── analyze.py
│ └── visualize.py
└── resources/
└── sample_data.csv
```

**Example**:

```markdown
---
name: data-analyzer
description: Analyze CSV data files
---

# Data Analyzer Skill

## Workflow

### Step 1: Review Sample Format

```python
read_skill_resource(
    skill_name="data-analyzer",
    resource_name="resources/sample_data.csv"
)
```

### Step 2: Run Analysis

```python
run_skill_script(
    skill_name="data-analyzer",
    script_name="analyze",
    args=["data.csv", "--output", "json"]
)
```

### Step 3: Generate Visualization

```python
run_skill_script(
    skill_name="data-analyzer",
    script_name="visualize",
    args=["data.csv", "--type", "histogram"]
)
```

For detailed methods, see:

```python
read_skill_resource(
    skill_name="data-analyzer",
    resource_name="REFERENCE.md"
)
```

**When to use**:

- Complex workflows
- Multi-step processes
- Teaching/tutorial scenarios

### Skill Design Best Practices

#### Skill Granularity

**Too Broad** ❌:

```markdown
general-research/
└── SKILL.md # Covers web search, arxiv, pubmed, datasets...
```

**Too Narrow** ❌:

```markdown
arxiv-search-physics/
arxiv-search-cs/
arxiv-search-math/
```

**Just Right** ✅:

```markdown
arxiv-search/
└── SKILL.md # Single focused capability
```

#### Naming Guidelines

**Good Names**:

- `arxiv-search` - Clear, descriptive
- `csv-analyzer` - Action-oriented
- `api-client` - Generic but scoped

**Poor Names**:

- `skill1` - Not descriptive
- `the_super_amazing_tool` - Too long
- `ArxivSearchTool` - Use kebab-case

#### Description Guidelines

**Good Descriptions**:

- "Search arXiv for research papers in physics, math, and CS"
- "Analyze CSV files and generate statistics"
- "Structured approach to web research"

**Poor Descriptions**:

- "Useful tool" - Too vague
- "Does stuff" - Not informative
- (300 character description) - Too long

#### Progressive Complexity

Start simple, add complexity as needed:

**Version 1** - Instructions only:

```markdown
---
name: api-client
description: Call the XYZ API
---

Use your HTTP tools to call https://api.example.com/v1/...
```

**Version 2** - Add reference:

```markdown
api-client/
├── SKILL.md
└── API_REFERENCE.md
```

**Version 3** - Add scripts:

```markdown
api-client/
├── SKILL.md
├── API_REFERENCE.md
└── scripts/
    └── make_request.py
```

### Anti-Patterns to Avoid

#### ❌ Circular Dependencies

Don't create skills that depend on each other:

```markdown
# skill-a/SKILL.md

To use this skill, first load skill-b...

# skill-b/SKILL.md

This skill requires skill-a to be loaded...
```

#### ❌ Hardcoded Secrets

Never include API keys or passwords:

```markdown
API_KEY = "sk-1234567890abcdef"
```

Instead, document how to configure:

```markdown
Set your API key as an environment variable:

```bash
export XYZ_API_KEY="your-key-here"
```

or set them in the environment where the agent runs.

#### ❌ Overly Generic Skills

Avoid "catch-all" skills:

```markdown
---
name: general-helper
description: Does various things
---

This skill can help with:
- Web search
- Data analysis
- API calls
- File operations
- ...
```

Create focused, single-purpose skills instead

## Next Steps

- [Examples](examples/index.md) - Real-world skill examples
- [API Reference](api/toolset.md) - API documentation

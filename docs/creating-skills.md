# Creating Skills

This guide covers creating effective **file-based skills** for Pydantic AI agents.

!!! tip "Programmatic Skills"
    Skills can also be created in Python code using the `Skill` class. See [Programmatic Skills](programmatic-skills.md) for dynamic resources and dependency injection.

## Basic Skill Structure

Every file-based skill must have at minimum:

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

Follow Anthropic's skill naming conventions:

- **Name**: lowercase, hyphens only, ≤64 chars (no "anthropic" or "claude")
- **Description**: ≤1024 chars, clear and concise

**Valid**: `arxiv-search`, `web-research`, `data-analyzer`
**Invalid**: `ArxivSearch`, `arxiv_search`, `very-long-skill-name-exceeds-limit`

The toolset logs warnings for violations but skills will still load.

### Best Practices for Instructions

**✅ Do:**
- Use clear, action-oriented language
- Provide specific examples
- Break down complex workflows
- Specify when to use the skill

**❌ Don't:**
- Write vague instructions
- Assume implicit context
- Create circular skill dependencies
- Include API keys or sensitive data

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
- Validate input arguments
- Return structured output (JSON preferred)
- Handle errors gracefully
- Document expected inputs/outputs in SKILL.md
- Use timeouts for external calls

**❌ Don't:**
- Make network calls without timeouts
- Write to files outside the skill directory
- Require interactive input
- Use environment-specific paths

### Script Argument Handling

When agents call scripts via `run_skill_script()`, arguments are converted to command-line flags:

```python
# Agent calls:
run_skill_script(
    skill_name='data-analyzer',
    script_name='analyze',
    args={'query': 'SELECT * FROM users', 'limit': '100', 'format': 'json'}
)

# Your script receives command-line arguments:
# python analyze.py --query "SELECT * FROM users" --limit 100 --format json
```

**Argument Mapping Rules:**

- Dictionary keys become flag names: `--key value`
- String values are passed as-is
- Numeric values are converted to strings
- Boolean `True` becomes flag without value: `--flag`
- Boolean `False` omits the flag entirely
- Lists become multiple flag occurrences: `--item a --item b`

**Example Script with Arguments:**

```python
#!/usr/bin/env python3
"""Data analyzer script with argument handling."""

import sys
import argparse
import json

def main():
    parser = argparse.ArgumentParser(description='Analyze data')
    parser.add_argument('--query', required=True, help='SQL query to execute')
    parser.add_argument('--limit', type=int, default=100, help='Result limit')
    parser.add_argument('--format', choices=['json', 'csv'], default='json')
    parser.add_argument('--explain', action='store_true', help='Show execution plan')

    args = parser.parse_args()

    try:
        # Execute query (example)
        results = execute_query(args.query, args.limit)

        # Format output
        if args.format == 'json':
            output = json.dumps(results, indent=2)
        else:
            output = convert_to_csv(results)

        print(output)
        sys.exit(0)

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

def execute_query(query, limit):
    # Your implementation here
    return [{"id": 1, "name": "test"}]

def convert_to_csv(data):
    # Your CSV conversion here
    return "id,name\n1,test"

if __name__ == "__main__":
    main()
```

### Parsing and Output Formats

**JSON Output (Recommended):**

```python
import json

result = {
    "success": True,
    "data": [
        {"id": 1, "value": 100},
        {"id": 2, "value": 200}
    ],
    "count": 2,
    "metadata": {"query": "user_data", "timestamp": "2025-01-23"}
}

print(json.dumps(result, indent=2))
```

**Plain Text Output:**

```python
output = """Analysis Results
================

Total records: 42
Average value: 123.45
Range: [10, 456]

Top 3 results:
1. Item A - 456
2. Item B - 234
3. Item C - 189
"""
print(output)
```

**CSV Output:**

```python
import csv
import sys

data = [
    {"id": 1, "name": "Alice", "score": 95},
    {"id": 2, "name": "Bob", "score": 87}
]

writer = csv.DictWriter(sys.stdout, fieldnames=['id', 'name', 'score'])
writer.writeheader()
writer.writerows(data)
```

### Error Handling in Scripts

**Communicate Errors Clearly:**

```python
#!/usr/bin/env python3
"""Example error handling."""

import sys
import json

def main():
    try:
        # Validate inputs first
        data = validate_input(sys.argv[1:])

        # Perform operation
        result = process(data)

        # Output results
        print(json.dumps({"status": "success", "result": result}))

    except ValueError as e:
        # Input validation error
        print(json.dumps({
            "status": "error",
            "type": "validation_error",
            "message": str(e)
        }), file=sys.stderr)
        sys.exit(1)

    except TimeoutError as e:
        # Operation timeout
        print(json.dumps({
            "status": "error",
            "type": "timeout",
            "message": "Operation exceeded time limit"
        }), file=sys.stderr)
        sys.exit(2)

    except Exception as e:
        # Unexpected error
        print(json.dumps({
            "status": "error",
            "type": "internal_error",
            "message": str(e)
        }), file=sys.stderr)
        sys.exit(3)

def validate_input(args):
    if not args:
        raise ValueError("Missing required arguments")
    return args[0]

def process(data):
    return f"Processed: {data}"

if __name__ == "__main__":
    main()
```

**Document Exit Codes:**

In your `SKILL.md`, document what exit codes mean:

```markdown
## Script: analyze

Executes data analysis with exit codes:

- **0**: Success
- **1**: Validation error (bad input)
- **2**: Timeout (operation too slow)
- **3**: System error (unexpected failure)

### Examples

```python
# Successful analysis
run_skill_script('data-skill', 'analyze', {'query': 'SELECT count(*) FROM users'})
# Returns: {"count": 42, "time_ms": 123}

# Invalid input (exits with code 1)
run_skill_script('data-skill', 'analyze', {'query': 'INVALID SQL'})
# Returns: ERROR: Syntax error in SQL query
```
```

### Timeout Management

Scripts have a default **30-second timeout**. Design scripts accordingly:

```python
#!/usr/bin/env python3
"""Long-running operation with timeout awareness."""

import sys
import time

def main():
    operation = sys.argv[1] if len(sys.argv) > 1 else 'quick'

    try:
        if operation == 'quick':
            result = quick_operation()  # < 1 second
        elif operation == 'medium':
            result = medium_operation()  # ~5 seconds
        elif operation == 'bulk':
            result = bulk_operation()  # Could take 20+ seconds, with checkpoints
        else:
            raise ValueError(f"Unknown operation: {operation}")

        print(result)

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

def quick_operation():
    return "Quick result"

def medium_operation():
    time.sleep(5)
    return "Medium result"

def bulk_operation():
    """Bulk operation with progress checkpoints."""
    results = []

    # Process in chunks with time checks
    for chunk in range(10):
        # Check if we're approaching timeout (leave 5s buffer)
        current_time = time.time()
        if current_time > start_time + 25:
            return f"Partial: processed {chunk}/10 chunks before timeout"

        # Process chunk
        results.append(f"chunk_{chunk}")
        time.sleep(2)

    return f"Complete: {len(results)} chunks processed"

if __name__ == "__main__":
    start_time = time.time()
    main()
```

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

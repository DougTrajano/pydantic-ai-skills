# pydantic-ai-skills

A standardized, composable framework for building and managing Agent Skills within the Pydantic AI ecosystem.

**Agent Skills** are modular collections of instructions, scripts, tools, and resources that enable AI agents to progressively discover, load, and execute specialized capabilities for domain-specific tasks.

This package implements the [Agent Skills specification](https://agentskills.io/) for Pydantic AI using a tool-calling approach, maintaining full compatibility with the specification while adapting the loading mechanism for Pydantic AI's architecture. It is also compatible with [Anthropic's Agent Skills framework](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview).

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=DougTrajano_pydantic-ai-skills&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=DougTrajano_pydantic-ai-skills)

## Features

- **Progressive Disclosure** - Load skill information only when needed, reducing token usage
- **Anthropic-Compatible** - Skills are structurally compatible with Anthropic's Agent Skills
- **Type-Safe** - Built with Python dataclasses and type hints
- **Validation** - Automatic validation of skill metadata and structure
- **Multiple Directories** - Load skills from multiple sources
- **Security** - Path traversal prevention and safe script execution

Full documentation available at: [https://dougtrajano.github.io/pydantic-ai-skills](https://dougtrajano.github.io/pydantic-ai-skills)

> **🚀 Native Integration in Pydantic AI**
>
> We're collaborating with the Pydantic AI team to introduce Agent Skills natively into the platform. Follow the progress in [PR #3780](https://github.com/pydantic/pydantic-ai/pull/3780).

## Installation

```bash
pip install pydantic-ai-skills
```

For development:

```bash
pip install pydantic-ai-skills[test]  # Includes pytest and coverage tools
```

## Video Tutorials

Learn how to use pydantic-ai-skills through these video tutorials:

### Basic Usage

Get started with your first skill and agent:

<video controls style="max-width:100%; border-radius:8px">
  <source src="docs/assets/basic_usage.mp4" type="video/mp4">
</video>

### Advanced Usage

Master advanced integration patterns:

<video controls style="max-width:100%; border-radius:8px">
  <source src="docs/assets/advanced_usage.mp4" type="video/mp4">
</video>

### Programmatic Skills

Create dynamic skills with Python:

<video controls style="max-width:100%; border-radius:8px">
  <source src="docs/assets/programmatic_skills.mp4" type="video/mp4">
</video>

## Quick Start

```python
from pydantic_ai import Agent, RunContext
from pydantic_ai_skills import SkillsToolset

# Initialize Skills Toolset with one or more skill directories
skills_toolset = SkillsToolset(directories=["./skills"])

# Create agent with skills as a toolset
agent = Agent(
    model='openai:gpt-4o',
    instructions='You are a helpful research assistant.',
    toolsets=[skills_toolset]
)

# Add skills instructions to agent (includes skill names and descriptions)
@agent.instructions
async def add_skills(ctx: RunContext) -> str | None:
    """Add skills instructions to the agent's context."""
    return await skills_toolset.get_instructions(ctx)

# Use agent - skills tools are available for the agent to call
user_prompt = "What are the last 3 papers on arXiv about machine learning?"

nodes = []
async with agent.iter(user_prompt) as agent_run:
    async for node in agent_run:
        nodes.append(node)
        print(node)
```

**Output:**

````python
UserPromptNode(user_prompt='What are the last 3 papers on arXiv about machine learning?', instructions_functions=[], system_prompts=('You are a helpful research assistant.',), system_prompt_functions=[SystemPromptRunner(function=<function add_skills_to_system_prompt at 0x110e951c0>, dynamic=False, _takes_ctx=False, _is_async=False)], system_prompt_dynamic_functions={})
ModelRequestNode(request=ModelRequest(parts=[SystemPromptPart(content='You are a helpful research assistant.', timestamp=datetime.datetime(2025, 12, 18, 23, 27, 16, 616893, tzinfo=datetime.timezone.utc)), SystemPromptPart(content="# Skills\n\nYou have access to skills that extend your capabilities. Skills are modular packages\ncontaining instructions, resources, and scripts for specialized tasks.\n\n## Available Skills\n\nThe following skills are available to you. Use them when relevant to the task:\n\n- **arxiv-search**: Search arXiv preprint repository for papers in physics, mathematics, computer science, quantitative biology, and related fields.\n- **pydanticai-docs**: Use this skill for requests related to Pydantic AI framework - building agents, tools, dependencies, structured outputs, and model integrations.\n- **web-research**: Use this skill for requests related to web research; it provides a structured approach to conducting comprehensive web research.\n## How to Use Skills\n\n**Progressive disclosure**: Load skill information only when needed.\n\n1. **When a skill is relevant to the current task**: Use `load_skill(skill_name)` to read the full instructions.\n2. **For additional documentation**: Use `read_skill_resource(skill_name, resource_name)` to read FORMS.md, REFERENCE.md, or other resources.\n3. **To execute skill scripts**: Use `run_skill_script(skill_name, script_name, args)` with appropriate command-line arguments.\n\n**Best practices**:\n- Select skills based on task relevance and descriptions listed above\n- Use progressive disclosure: load only what you need, when you need it, starting with load_skill\n- Follow the skill's documented usage patterns and examples\n", timestamp=datetime.datetime(2025, 12, 18, 23, 27, 16, 617375, tzinfo=datetime.timezone.utc)), UserPromptPart(content='What are the last 3 papers on arXiv about machine learning?', timestamp=datetime.datetime(2025, 12, 18, 23, 27, 16, 617384, tzinfo=datetime.timezone.utc))]))
CallToolsNode(model_response=ModelResponse(parts=[ToolCallPart(tool_name='load_skill', args='{"skill_name":"arxiv-search"}', tool_call_id='call_WGBvmGWJQvOliYoG5AeP6BMh')], usage=RequestUsage(input_tokens=717, output_tokens=17, details={'accepted_prediction_tokens': 0, 'audio_tokens': 0, 'reasoning_tokens': 0, 'rejected_prediction_tokens': 0}), model_name='gpt-4o-2024-08-06', timestamp=datetime.datetime(2025, 12, 18, 23, 27, 16, tzinfo=TzInfo(0)), provider_name='openai', provider_details={'finish_reason': 'tool_calls'}, provider_response_id='chatcmpl-CoHgqj5YugHHE2ZJvnQtXx3U74Uib', finish_reason='tool_call'))
ModelRequestNode(request=ModelRequest(parts=[ToolReturnPart(tool_name='load_skill', content='# Skill: arxiv-search\n**Description:** Search arXiv preprint repository for papers in physics, mathematics, computer science, quantitative biology, and related fields.\n**Path:** /Users/dougtrajano/Library/CloudStorage/OneDrive-Personal/dev/vscode/macbook/GitHub/pydantic-ai-skills/examples/skills/arxiv-search\n\n**Available Scripts:**\n- arxiv_search\n\n---\n\n# arXiv Search Skill\n\nThis skill provides access to arXiv, a free distribution service and open-access archive for scholarly articles in physics, mathematics, computer science, quantitative biology, quantitative finance, statistics, electrical engineering, systems science, and economics.\n\n## When to Use This Skill\n\nUse this skill when you need to:\n\n- Find preprints and recent research papers before journal publication\n- Search for papers in computational biology, bioinformatics, or systems biology\n- Access mathematical or statistical methods papers relevant to biology\n- Find machine learning papers applied to biological problems\n- Get the latest research that may not yet be in PubMed\n\n## Skill Scripts\n\n### arxiv_search\n\nThe `arxiv_search` script accepts the following arguments:\n\n- First argument (required): Search query string (e.g., "neural networks protein structure", "single cell RNA-seq")\n- `--max-papers` (optional): Maximum number of papers to retrieve (default: 10)\n\n### Usage Pattern\n\nUse the `run_skill_script` tool to execute the `arxiv_search` script. For example:\n\n```python\nrun_skill_script(\n    skill_name="arxiv-search",\n    script_name="arxiv_search",\n    args=["your search query", "--max-papers", "5"]\n)\n```\n\nSearch for computational biology papers (default 10 results):\n\n```python\nrun_skill_script(\n    skill_name="arxiv-search",\n    script_name="arxiv_search",\n    args=["protein folding prediction"]\n)\n```\n\n## Output Format\n\nThe script returns formatted results with:\n\n- **Title**: Paper title\n- **Summary**: Abstract/summary text\n- **URL**: Direct link to the paper on arXiv\n\nEach paper is separated by blank lines for readability.\n\n## Features\n\n- **Relevance sorting**: Results ordered by relevance to query\n- **Fast retrieval**: Direct API access with no authentication required\n- **Simple interface**: Clean, easy-to-parse output\n- **No API key required**: Free access to arXiv database\n\n## Dependencies\n\nThis skill requires the `arxiv` Python package. If not installed, you\'ll see an error message.\n\nTo install the package:\n\n```bash\npip install arxiv\n```\n\nThe package is not included by default since it\'s skill-specific. Install it when you first use this skill.\n\n## Notes\n\n- arXiv is particularly strong for:\n  - Computer science (cs.LG, cs.AI, cs.CV)\n  - Quantitative biology (q-bio)\n  - Statistics (stat.ML)\n  - Physics and mathematics\n- Papers are preprints and may not be peer-reviewed\n- Results include both recent uploads and older papers\n- Best for computational/theoretical work in biology', tool_call_id='call_WGBvmGWJQvOliYoG5AeP6BMh', timestamp=datetime.datetime(2025, 12, 18, 23, 27, 17, 430875, tzinfo=datetime.timezone.utc))]))
CallToolsNode(model_response=ModelResponse(parts=[ToolCallPart(tool_name='run_skill_script', args='{"skill_name":"arxiv-search","script_name":"arxiv_search","args":["machine learning","--max-papers","3"]}', tool_call_id='call_oDXHSlx4bpoV3Frm8fvWU8j4')], usage=RequestUsage(input_tokens=1395, output_tokens=38, details={'accepted_prediction_tokens': 0, 'audio_tokens': 0, 'reasoning_tokens': 0, 'rejected_prediction_tokens': 0}), model_name='gpt-4o-2024-08-06', timestamp=datetime.datetime(2025, 12, 18, 23, 27, 17, tzinfo=TzInfo(0)), provider_name='openai', provider_details={'finish_reason': 'tool_calls'}, provider_response_id='chatcmpl-CoHgraqy3S9OKCsFIP0Y3c1Sg6tqC', finish_reason='tool_call'))
ModelRequestNode(request=ModelRequest(parts=[ToolReturnPart(tool_name='run_skill_script', content='Title: Changing Data Sources in the Age of Machine Learning for Official Statistics\nSummary: Data science has become increasingly essential for the production of official statistics, as it enables the automated collection, processing, and analysis of large amounts of data. With such data science practices in place, it enables more timely, more insightful and more flexible reporting. However, the quality and integrity of data-science-driven statistics rely on the accuracy and reliability of the data sources and the machine learning techniques that support them. In particular, changes in data sources are inevitable to occur and pose significant risks that are crucial to address in the context of machine learning for official statistics.\n  This paper gives an overview of the main risks, liabilities, and uncertainties associated with changing data sources in the context of machine learning for official statistics. We provide a checklist of the most prevalent origins and causes of changing data sources; not only on a technical level but also regarding ownership, ethics, regulation, and public perception. Next, we highlight the repercussions of changing data sources on statistical reporting. These include technical effects such as concept drift, bias, availability, validity, accuracy and completeness, but also the neutrality and potential discontinuation of the statistical offering. We offer a few important precautionary measures, such as enhancing robustness in both data sourcing and statistical techniques, and thorough monitoring. In doing so, machine learning-based official statistics can maintain integrity, reliability, consistency, and relevance in policy-making, decision-making, and public discourse.\nURL: http://arxiv.org/abs/2306.04338v1\n\nTitle: DOME: Recommendations for supervised machine learning validation in biology\nSummary: Modern biology frequently relies on machine learning to provide predictions and improve decision processes. There have been recent calls for more scrutiny on machine learning performance and possible limitations. Here we present a set of community-wide recommendations aiming to help establish standards of supervised machine learning validation in biology. Adopting a structured methods description for machine learning based on data, optimization, model, evaluation (DOME) will aim to help both reviewers and readers to better understand and assess the performance and limitations of a method or outcome. The recommendations are formulated as questions to anyone wishing to pursue implementation of a machine learning algorithm. Answers to these questions can be easily included in the supplementary material of published papers.\nURL: http://arxiv.org/abs/2006.16189v4\n\nTitle: Learning Curves for Decision Making in Supervised Machine Learning: A Survey\nSummary: Learning curves are a concept from social sciences that has been adopted in the context of machine learning to assess the performance of a learning algorithm with respect to a certain resource, e.g., the number of training examples or the number of training iterations. Learning curves have important applications in several machine learning contexts, most notably in data acquisition, early stopping of model training, and model selection. For instance, learning curves can be used to model the performance of the combination of an algorithm and its hyperparameter configuration, providing insights into their potential suitability at an early stage and often expediting the algorithm selection process. Various learning curve models have been proposed to use learning curves for decision making. Some of these models answer the binary decision question of whether a given algorithm at a certain budget will outperform a certain reference performance, whereas more complex models predict the entire learning curve of an algorithm. We contribute a framework that categorises learning curve approaches using three criteria: the decision-making situation they address, the intrinsic learning curve question they answer and the type of resources they use. We survey papers from the literature and classify them into this framework.\nURL: http://arxiv.org/abs/2201.12150v2', tool_call_id='call_oDXHSlx4bpoV3Frm8fvWU8j4', timestamp=datetime.datetime(2025, 12, 18, 23, 27, 18, 930364, tzinfo=datetime.timezone.utc))]))
CallToolsNode(model_response=ModelResponse(parts=[TextPart(content='Here are the last three papers from arXiv about machine learning:\n\n1. **Title:** Changing Data Sources in the Age of Machine Learning for Official Statistics\n   - **Summary:** This paper discusses the increasing importance of data science in official statistics production, highlighting risks and uncertainties related to changing data sources in machine learning contexts. It covers issues like concept drift, bias, and data validity, and offers measures to maintain the reliability and integrity of machine learning-based statistics.\n   - **URL:** [Link to Paper](http://arxiv.org/abs/2306.04338v1)\n\n2. **Title:** DOME: Recommendations for supervised machine learning validation in biology\n   - **Summary:** The paper provides a set of community-wide recommendations for machine learning validation in biology, emphasizing the importance of a structured methods description using DOME (data, optimization, model, evaluation). These guidelines aim to improve the scrutiny of machine learning performance and facilitate better understanding and assessment of methods.\n   - **URL:** [Link to Paper](http://arxiv.org/abs/2006.16189v4)\n\n3. **Title:** Learning Curves for Decision Making in Supervised Machine Learning: A Survey\n   - **Summary:** This survey covers the concept of learning curves in machine learning, which assess algorithm performance concerning resources like training examples. The paper categorizes learning curve approaches based on decision-making situations, and it surveys literature to classify various models within this framework.\n   - **URL:** [Link to Paper](http://arxiv.org/abs/2201.12150v2)')], usage=RequestUsage(input_tokens=2177, cache_read_tokens=1408, output_tokens=322, details={'accepted_prediction_tokens': 0, 'audio_tokens': 0, 'reasoning_tokens': 0, 'rejected_prediction_tokens': 0}), model_name='gpt-4o-2024-08-06', timestamp=datetime.datetime(2025, 12, 18, 23, 27, 19, tzinfo=TzInfo(0)), provider_name='openai', provider_details={'finish_reason': 'stop'}, provider_response_id='chatcmpl-CoHgtHBD9LUsRKbILVar99GtAGKHM', finish_reason='stop'))
End(data=FinalResult(output='Here are the last three papers from arXiv about machine learning:\n\n1. **Title:** Changing Data Sources in the Age of Machine Learning for Official Statistics\n   - **Summary:** This paper discusses the increasing importance of data science in official statistics production, highlighting risks and uncertainties related to changing data sources in machine learning contexts. It covers issues like concept drift, bias, and data validity, and offers measures to maintain the reliability and integrity of machine learning-based statistics.\n   - **URL:** [Link to Paper](http://arxiv.org/abs/2306.04338v1)\n\n2. **Title:** DOME: Recommendations for supervised machine learning validation in biology\n   - **Summary:** The paper provides a set of community-wide recommendations for machine learning validation in biology, emphasizing the importance of a structured methods description using DOME (data, optimization, model, evaluation). These guidelines aim to improve the scrutiny of machine learning performance and facilitate better understanding and assessment of methods.\n   - **URL:** [Link to Paper](http://arxiv.org/abs/2006.16189v4)\n\n3. **Title:** Learning Curves for Decision Making in Supervised Machine Learning: A Survey\n   - **Summary:** This survey covers the concept of learning curves in machine learning, which assess algorithm performance concerning resources like training examples. The paper categorizes learning curve approaches based on decision-making situations, and it surveys literature to classify various models within this framework.\n   - **URL:** [Link to Paper](http://arxiv.org/abs/2201.12150v2)'))
````

## Creating Skills

Skills are filesystem-based directories with a `SKILL.md` file containing YAML frontmatter and Markdown instructions.

### Basic Skill Structure

```md
my-skill/
└── SKILL.md # Required: Main instructions and metadata
```

### Extended Skill Structure

```md
my-skill/
├── SKILL.md # Required: Main instructions and metadata
├── FORMS.md # Optional: Form-filling guides
├── REFERENCE.md # Optional: Detailed API reference
├── scripts/ # Optional: Python scripts
│ ├── script1.py
│ └── script2.py
└── resources/ # Optional: Additional files
├── templates/
└── data.json
```

### Minimal SKILL.md

```markdown
---
name: my-skill
description: Brief description of what this skill does and when to use it
---

# My Skill

## When to Use This Skill

Use this skill when you need to:

- Do specific task A
- Handle scenario B
- Process data type C

## Instructions

1. Step 1
2. Step 2
3. Step 3
```

### Metadata Requirements

Following [Anthropic's specifications](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview#skill-structure):

**Required fields:**

- `name`: Skill identifier (max 64 chars, lowercase letters/numbers/hyphens only)
- `description`: Brief description (max 1024 chars)

You can also include optional fields to help you manage and categorize skills (`version`, `author`, `tags`, etc.). These are not used by the agent.

**Validation:**

- ✅ Names must use lowercase letters, numbers, and hyphens only
- ✅ Names cannot contain reserved words: "anthropic", "claude"
- ✅ SKILL.md body should be under 500 lines (warning if exceeded)
- ✅ Descriptions must be under 1024 characters

## How Skills Work

### Progressive Disclosure (Anthropic's Approach)

Skills implement **progressive disclosure** - loading information in stages:

#### Level 1: Metadata (Always Loaded)

- All skill names and descriptions are included in the system prompt
- Enables skill discovery without tool calls
- Minimal token overhead

#### Level 2: Instructions (Loaded When Needed)

- Agent calls `load_skill(name)` to read full instructions
- Only loaded when skill is relevant to the task

#### Level 3: Resources (Loaded As Needed)

- Agent calls `read_skill_resource(skill_name, resource_name)` for additional docs
- Only loaded when referenced or required

### Tool-Calling Adaptation

**Anthropic's Implementation:**

- Claude uses `bash` commands to read files from filesystem
- Skills exist as directories in a VM environment

**Our Implementation:**

- Uses tool-calling instead of bash commands
- Skills are discovered and loaded via Pydantic AI tools
- Maintains the same progressive disclosure pattern
- Skills are structurally compatible with Anthropic's format

## Available Tools

The `SkillsToolset` provides four tools to agents:

### 1. `list_skills()`

List all available skills with descriptions, resources, and scripts.

**Note:** With the enhanced system prompt, this tool is optional since all metadata is pre-loaded.

### 2. `load_skill(name)`

Load the full instructions for a specific skill.

```python
# Agent calls this when a skill is relevant
result = await load_skill(ctx, "arxiv-search")
```

### 3. `read_skill_resource(skill_name, resource_name)`

Read additional resource files (FORMS.md, REFERENCE.md, etc.).

```python
# Agent loads resources only when needed
result = await read_skill_resource(ctx, "pdf-processing", "FORMS.md")
```

### 4. `run_skill_script(skill_name, script_name, args)`

Execute a skill script with command-line arguments.

```python
# Agent executes scripts with arguments
result = await run_skill_script(
    ctx,
    "arxiv-search",
    "arxiv_search",
    ["machine learning", "--max-papers", "5"]
)
```

## System Prompt

The `SkillsToolset` automatically injects skill instructions into the agent's system prompt via the `get_instructions()` method. This includes:

- All skill metadata (name + description) for discovery
- Instructions on how to use skill tools effectively

This follows Anthropic's approach where all metadata is pre-loaded, enabling agents to select skills without calling `list_skills()`.

The automatic injection happens when you add the toolset to an agent - no additional decorator is needed.

## Security considerations

We strongly recommend that you use Skills only from trusted sources: those you created yourself or obtained from trusted sources. Skills provide AI Agents with new capabilities through instructions and code, and while this makes them powerful, it also means a malicious Skill can direct agents to invoke tools or execute code in ways that don't match the Skill's stated purpose.

> If you must use a Skill from an untrusted or unknown source, exercise extreme caution and thoroughly audit it before use. Depending on what access agents have when executing the Skill, malicious Skills could lead to data exfiltration, unauthorized system access, or other security risks.

## Related Resources

- [Anthropic Agent Skills Documentation](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
- [Anthropic Agent Skills Best Practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- [Pydantic AI Documentation](https://ai.pydantic.dev/)
- [Agent Skills Cookbook](https://github.com/anthropics/claude-cookbooks/tree/main/skills)
- [Introducing Agent Skills | Claude](https://www.claude.com/blog/skills)
- [Using skills with Deep Agents](https://blog.langchain.com/using-skills-with-deep-agents/)
- [vstorm-co/pydantic-deepagents](https://github.com/vstorm-co/pydantic-deepagents)

## Acknowledgments

- **Anthropic** - For the Agent Skills framework and documentation.
- **Pydantic AI Team** - For the excellent agent framework.
- **Community** - For feedback and contributions.

> This project was highly inspired by [pydantic-deepagents](https://github.com/vstorm-co/pydantic-deepagents), which provided foundational ideas and patterns for agent skill implementation and progressive disclosure in the Pydantic AI. We gratefully acknowledge their work and contributions to the community.

## Contributing

Contributions are welcome! Please see [Contributing - Pydantic AI - Agent Skills](https://dougtrajano.github.io/pydantic-ai-skills/contributing/).

## License

MIT License - see [LICENSE](LICENSE) file for details.
